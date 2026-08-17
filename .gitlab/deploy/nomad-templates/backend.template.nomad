# Backend-specific Nomad job template
# Extends base-service.template.nomad with backend-specific configurations
# Based on data-service.template.nomad with improvements

job "${__SERVICE__}-${__ENVIRONMENT__}" {
  datacenters = ${__DATACENTERS__}
  namespace   = "${__NAMESPACE__}"
  type        = "service"

  # Constraints to avoid specific nodes
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

  # Ensure tasks run on different hosts
  constraint {
    distinct_hosts = true
  }

  # Spread tasks across nodes
  spread {
    attribute = "${node.unique.name}"
    weight    = 50
  }

  # Constraint for data volumes (if needed)
  # constraint {
  #   attribute = "${meta.role}"
  #   operator  = "set_contains"
  #   value     = "data-volume"
  # }

  # Update strategy
  # health_check = "checks" # deployment waits for service check blocks to pass; "task_states" = only wait for task running.
  # health_check = "task_states" so deployment does not wait on service checks. The service check blocks in this job still run: 
  #                 Nomad runs them, reports status to Consul (if used), and they show in the Nomad/Consul UI for monitoring—they just do not gate the update strategy.
  update {
    stagger      = "10s"
    max_parallel = 1
    health_check = "task_states"
    min_healthy_time = "10s"
    healthy_deadline = "3m"
    progress_deadline = "10m"
    auto_revert = true
    auto_promote = false
    canary = 0
  }

  group "${__SERVICE__}-${__ENVIRONMENT__}" {
    count = ${__COUNT__} # ${__COUNT__:-1} # envsubst will only ever replace references to environment variables in the form of ${VAR} or $VAR. Special shell features like ${VAR:-default} are not supported.
    
    shutdown_delay = "10s" # Keep the alloc alive briefly on stop so Nomad can deregister the service before killing the task and give Traefik time to stop sending traffic.

    network {
      port "http" {
        to = 8000
      }
    }

    # Volume mounts (if needed - uncomment and configure)
    # volume "data-${__ENVIRONMENT__}" {
    #   type      = "host"
    #   source    = "data-${__ENVIRONMENT__}"
    #   read_only = false
    # }

    task "${__SERVICE__}-${__ENVIRONMENT__}" {
      driver = "${__JOB_DRIVER__}"

      config {
        image        = "${__IMAGE_NAME__}:${__IMAGE_TAG__}"
        force_pull   = "${__IMAGE_FORCE_PULL__}"
        ports        = ["http"]
        network_mode = "bridge"
        
        # Registry authentication (if needed)
        auth {
          username       = "${__USERNAME__}"
          password       = "${__PASSWORD__}"
          server_address = "${__CI_REGISTRY__}"
        }

        # Disable Docker's native HEALTHCHECK; Nomad doesn't use it for its own health monitoring, so disabling avoids redundant health checks.
        healthchecks {
          disable = true
        }
      }

      # Environment variables
      env {
        CI_ENVIRONMENT_NAME = "${__ENVIRONMENT__}"
        SERVICE_NAME        = "${__SERVICE__}"
        SERVER_PORT         = "${NOMAD_PORT_http}"
        # Database and service URLs (set via GitLab CI variables or Nomad service discovery)
        # DATABASE_URL = "${DATABASE_URL}"
      }

      # Dynamic runtime environment variables
      # __RUNTIME_ENV__ should contain newline-separated KEY=VALUE pairs
      # Example: KEYCLOAK_DOMAIN=https://keycloak.example.com
      #          KEYCLOAK_REALM=ams-portal
      #          KEYCLOAK_UI_CLIENT_ID=ams-portal-ui
      #          AMS_HOST=0.0.0.0
      #          LOG_LEVEL=INFO
      template {
        data        = <<EOF
${__RUNTIME_ENV__}
        EOF
        destination = "local/runtime.env"
        env         = true
        change_mode = "restart"
      }

      # Template for service discovery (e.g., database URL or other service URLs)
      # Example: API Gateway discovering data-service
      # template {
      #   data        = <<EOF
      #   DATA_SERVICE_URL={{- range nomadService "data-service-${__ENVIRONMENT__}" }}http://{{ .Address }}:{{ .Port }}{{- end }}
      #   EOF
      #   destination = "local/service-url.env"
      #   env         = true
      #   change_mode = "restart"
      # }

      template {
        # https://www.hashicorp.com/en/blog/nomad-secrets-consumption-patterns-nomad-variables
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
          SECRET_ENCRYPTION_KEY = "${__SECRET_ENCRYPTION_KEY__}"
          EOF
      }

      # Volume mounts (if needed - uncomment and configure)
      # volume_mount {
      #   volume      = "data-${__ENVIRONMENT__}"
      #   destination = "/data"
      #   read_only   = false
      # }

      # Resources
      resources {
        cpu    = ${__RESOURCE_CPU__} # ${__RESOURCE_CPU__:-1000} # envsubst will only ever replace references to environment variables in the form of ${VAR} or $VAR. Special shell features like ${VAR:-default} are not supported.
        memory = ${__RESOURCE_MEMORY__} # ${__RESOURCE_MEMORY__:-1024}
      }

      # Restart policy
      restart {
        attempts = 3
        interval = "5m"
        delay    = "15s"
        mode     = "delay"
      }
    }

    # Service definition
    # - Review Apps: Need Traefik tags for external access (testing)
    # - Production/Staging/Development: Simple tags for internal service discovery
    service {
      name                = "${__SERVICE__}-${__ENVIRONMENT__}"
      provider            = "nomad"
      port                = "http"
      tags                = ${__SERVICE_TAGS__}
      enable_tag_override = true

      # Health check
      check {
        type     = "http"
        port     = "http"
        path     = "/${__HEALTH_BASE__}/health"
        interval = "10s"
        timeout  = "2s"
        method   = "GET"
      }

      # Readiness check
      check {
        type     = "http"
        port     = "http"
        path     = "/${__HEALTH_BASE__}/ready"
        interval = "10s"
        timeout  = "2s"
        method   = "GET"
      }
    }
  }
}

