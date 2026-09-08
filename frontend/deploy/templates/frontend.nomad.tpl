job "[[ var "service" . ]]-[[ var "environment" . ]]" {
  datacenters = [[ var "datacenters" . | toStringList ]]
  namespace   = "[[ var "namespace" . ]]"
  type        = "service"

  constraint {
    attribute = "${meta.role}"
    operator  = "!="
    value     = "rcg-ingress"
  }

  constraint {
    attribute = "${meta.role}"
    operator  = "!="
    value     = "ingress-server"
  }

  constraint {
    attribute = "${meta.role}"
    operator  = "!="
    value     = "nfs-server"
  }

  constraint {
    attribute = "${meta.node_class}"
    value     = "prod"
  }

  constraint {
    distinct_hosts = true
  }

  spread {
    attribute = "${node.unique.name}"
    weight    = 50
  }

  update {
    stagger           = "10s"
    max_parallel      = 1
    health_check      = "checks"
    min_healthy_time  = "10s"
    healthy_deadline  = "3m"
    progress_deadline = "10m"
    auto_revert       = true
    auto_promote      = false
    canary            = 0
  }

  group "[[ var "service" . ]]-[[ var "environment" . ]]" {
    count = [[ var "count" . ]]

    shutdown_delay = "10s"

    network {
      port "http" {
        to = 80
      }
    }

    task "[[ var "service" . ]]-[[ var "environment" . ]]" {
      driver = "[[ var "job_driver" . ]]"

      config {
        image        = "[[ var "image_name" . ]]:[[ var "image_tag" . ]]"
        force_pull   = "[[ var "image_force_pull" . ]]"
        ports        = ["http"]
        network_mode = "bridge"

        auth {
          username       = "[[ var "registry_username" . ]]"
          password       = "[[ var "registry_password" . ]]"
          server_address = "[[ var "registry_server" . ]]"
        }

        healthchecks {
          disable = true
        }
      }

      env {
        CI_ENVIRONMENT_NAME = "[[ var "environment" . ]]"
        SERVICE_NAME        = "[[ var "service" . ]]"
        SERVER_PORT         = "${NOMAD_PORT_http}"
      }

      template {
        # runtime_env may embed pack snippets; tpl evaluates them against pack vars.
        # API_GATEWAY (Pack/tpl): use Nomad service discovery of the backend job
        # (cluster-internal Address:Port), not a public Traefik http://…NOMAD_DOMAIN URL.
        # Pack expands [[ var "environment" . ]]; Nomad later expands {{ range nomadService }}.
        # Skip the default when CI runtime_env already sets API_GATEWAY=…
        data        = <<EOF
[[ tpl (var "runtime_env" .) . ]]
[[- if not (contains "API_GATEWAY=" (var "runtime_env" .)) ]]
API_GATEWAY=http://{{- range nomadService "backend-[[ var "environment" . ]]" }}{{ .Address }}:{{ .Port }}{{- end }}
[[- end ]]
        EOF
        destination = "local/runtime.env"
        env         = true
        change_mode = "restart"
      }

      template {
        # runtime_secrets from __SECRETS_BACKEND__ (via __RUNTIME_SECRETS__); tpl like runtime_env
        destination = "${NOMAD_SECRETS_DIR}/env.vars"
        env         = true
        change_mode = "restart"
        data        = <<EOF
          {{- if nomadVarExists "nomad/jobs" -}}
            {{- with nomadVar "nomad/jobs" -}}
            #SECRET_ONE = {{ .secret_author }}
            #SECRET_TWO  = {{ .role }}
            {{- end -}}
          {{- else -}}
            # Nomad variable path was missing, skipping optional secrets
          {{- end -}}

          # This will now always render, regardless of Nomad's variable store status
          # SECRET_ENCRYPTION_KEY = "[[ var "secret_encryption_key" . ]]"
          [[ tpl (var "runtime_secrets" .) . ]]
          EOF
      }

      resources {
        cpu    = [[ var "resource_cpu" . ]]
        memory = [[ var "resource_memory" . ]]
      }

      restart {
        attempts = 3
        interval = "5m"
        delay    = "15s"
        mode     = "delay"
      }
    }

    service {
      name                = "[[ var "service" . ]]-[[ var "environment" . ]]"
      provider            = "nomad"
      port                = "http"
      tags = [
        "[[ var "service" . ]]",
[[- if var "enable_traefik" . ]]
        "traefik.enable=true",
[[-   if ne (var "public_domain" .) "" ]]
        "traefik.http.routers.[[ var "router_name" . ]].rule=Host(`[[ var "hostname" . ]]`) || Host(`[[ var "public_domain" . ]]`)",
[[-   else ]]
        "traefik.http.routers.[[ var "router_name" . ]].rule=Host(`[[ var "hostname" . ]]`)",
[[-   end ]]
        "traefik.http.routers.[[ var "router_name" . ]].entrypoints=websecure",
        "traefik.http.routers.[[ var "router_name" . ]].tls=true",
[[- end ]]
      ]
      enable_tag_override = true

      check {
        type     = "http"
        port     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
        method   = "GET"
      }

      check {
        type     = "http"
        port     = "http"
        path     = "/ready"
        interval = "10s"
        timeout  = "2s"
        method   = "GET"
      }
    }
  }
}
