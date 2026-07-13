# API Gateway-specific Nomad job template
# Based on api-gateway.tempalte.nomad with improvements

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

  # Ensure tasks run on different hosts
  constraint {
    distinct_hosts = true
  }

  # Spread tasks across nodes
  spread {
    attribute = "${node.unique.name}"
    weight    = 50
  }

  # Update strategy
  # health_check = "checks" # deployment waits for service check blocks to pass; "task_states" = only wait for task running.
  # health_check = "task_states" so deployment does not wait on service checks. The service check blocks in this job still run:
  #                 Nomad runs them, reports status to Consul (if used), and they show in the Nomad/Consul UI for monitoring—they just do not gate the update strategy.
  update {
    stagger      = "10s"
    max_parallel = 1
    health_check = "checks"
    min_healthy_time = "10s"
    healthy_deadline = "3m"
    progress_deadline = "10m"
    auto_revert = true
    auto_promote = false
    canary = 0
  }

  group "${__SERVICE__}-${__ENVIRONMENT__}" {
    count = ${__COUNT__} # ${__COUNT__:-1} # envsubst will only ever replace references to environment variables in the form of ${VAR} or $VAR. Special shell features like ${VAR:-default} are not supported.

    network {
      port "http" {
        # Dynamic port allocation
      }
    }

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
          server_address = "${CI_REGISTRY}"
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
      }

      # Template for service discovery (e.g., data-service URL)
      # Uses Nomad service discovery to find the data-service
      template {
        data        = <<EOF
        DATA_SERVICE_URL={{- range nomadService "${__DATA_SERVICE__}-${__ENVIRONMENT__}" }}http://{{ .Address }}:{{ .Port }}{{- end }}
        EOF
        destination = "local/data-service-url.env"
        env         = true
        change_mode = "restart"
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
          path     = "/health"
          interval = "10s"
          timeout  = "2s"
          method   = "GET"
        }

        # Readiness check
        check {
          type     = "http"
          port     = "http"
          path     = "/ready"
          interval = "10s"
          timeout  = "2s"
          method   = "GET"
        }
      }

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
  }
}

