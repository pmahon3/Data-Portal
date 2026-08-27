# Base Nomad job template for any service
# This template uses envsubst variables (${__VARIABLE__}) for substitution
# Variables are set in the GitLab CI pipeline

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

  # Spread tasks across nodes; the stanza is used to influence Nomad's scheduling decisions. 
  # Its purpose is to distribute (spread) the task groups across different nodes rather than letting Nomad pack them all onto a single server.
  spread {
    # Property to use when deciding how to spread the tasks.
    attribute = "${node.unique.name}" 
    # How "important" this rule is compared to other scheduling factors (like resource availability or other affinity rules).
    # 50 is a moderate preference. It says "I would really like these to be on different nodes, but if a node is too full or there's a much better reason to put them together, you can ignore this rule."
    weight    = 50 
  }

  # Update strategy
  # The update stanza is Nomad's safety net. It controls how the job transitions from "Old Version" to "New Version."
  # Use update to control how you push changes, and restart to control how the system recovers from failure
  # You just finished a new feature and want to deploy it without taking your whole site down. 
  # `update` tells Nomad, "Don't kill all 10 instances at once. Update them 2 at a time (max_parallel = 2), wait for them to be healthy
  update {
    # This is the "One at a time" rule. Nomad will only update 1 instance 
    # (allocation) at a time to ensure you don't take down all instances at once. default 1.
    # In the `group` block, at least `count=2` instances are needed for true zero-downtime
    max_parallel = 1

    # This is the "Wait between" rule. After finishing one instance, 
    # Nomad waits 30 seconds before starting the next one. default 30s. 
    # This setting is being deprecated, and is equivalent to min_healthy_time
    stagger = "30s"

    # This tells Nomad to use the health checks defined in your 'service' 
    # stanza to determine if the new version is actually working. default: "checks"
    # health_check = "checks" # deployment waits for service check blocks to pass; "task_states" = only wait for task running.
    # health_check = "task_states" so deployment does not wait on service checks. The service check blocks in this job still run:
    #                 Nomad runs them, reports status to Consul (if used), and they show in the Nomad/Consul UI for monitoring—they just do not gate the update strategy.
    health_check = "checks"

    # Once a new instance starts, it must stay "Healthy" (passing its health checks) 
    # for at least 10 seconds before Nomad considers it a success. default: "10s".
    min_healthy_time = "10s"

    # If the new instance hasn't become healthy within 5 minutes, 
    # Nomad marks the deployment as failed. default: "5m".
    healthy_deadline = "5m"

    # If the entire deployment (all instances) hasn't finished 
    # successfully in 10 minutes, the whole update is marked as failed. default: "10m"
    progress_deadline = "10m"

    # This is the "Panic Button." If the update fails (due to deadlines), 
    # Nomad will automatically kill the broken new version and re-deploy the 
    # last known good version. default: false
    auto_revert = true

    # Used with canaries. If set to false, a human must manually run 
    # 'nomad job promote' after checking the canary to continue the deploy. default: false
    auto_promote = false

    # This starts exactly one "test" instance of the new code alongside 
    # the old ones. It stops there and waits for you to verify it. default: 0.
    canary = 0
  }

  group "${__SERVICE__}-${__ENVIRONMENT__}" {
    # At least `count=2` instances are needed for true zero-downtime
    count = ${__COUNT__} # ${__COUNT__:-1} # envsubst will only ever replace references to environment variables in the form of ${VAR} or $VAR. Special shell features like ${VAR:-default} are not supported.
    
    shutdown_delay = "10s" # Keep the alloc alive briefly on stop so Nomad can deregister the service before killing the task and give Traefik time to stop sending traffic.

    network {
      port "http" {
        # Dynamic port allocation (can be overridden in service-specific templates)
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
          server_address = "${__CI_REGISTRY__}"
        }

        # Disable Docker's native HEALTHCHECK; Nomad doesn't use it for its own health monitoring, so disabling avoids redundant health checks.
        # Nomad health monitoring is via `check` block.
        healthchecks {
          disable = true
        }
      }

      # Environment variables (service-specific templates should extend this)
      env {
        CI_ENVIRONMENT_NAME = "${__ENVIRONMENT__}"
        SERVICE_NAME        = "${__SERVICE__}"
      }

      # Resources (can be overridden)
      resources {
        cpu    = ${__RESOURCE_CPU__} # ${__RESOURCE_CPU__:-500} # envsubst will only ever replace references to environment variables in the form of ${VAR} or $VAR. Special shell features like ${VAR:-default} are not supported.
        memory = ${__RESOURCE_MEMORY__} # ${__RESOURCE_MEMORY__:-512}
      }

      # Restart policy: Nomad restarts this task when it exits or fails. Restarts are
      # Update strategy. Batch jobs restart `tasks`. In contrast, Service jobs updates at the `job` level.
      # in-place (same allocation). After attempts are exhausted, the allocation fails.
      # lives at the task level (or inherited from the group). It triggers automatically if your application crashes on its own
      # "If this specific process dies, try to restart it immediately on the same server up to 3 times (attempts = 3) before giving up"
      restart {
        # Max restarts before this allocation is considered failed.
        attempts = 3
        # Time window for counting attempts; counter resets after this period.
        interval = "5m"
        # Wait before each restart attempt (e.g. let dependencies recover).
        delay    = "15s"
        # mode="delay": wait another interval then restart (can loop forever if interval is short).
        # mode="fail": mark allocation failed after attempts exhausted & stops restarting the task in it. It does not disable future runs of the job.
        mode     = "fail"
      }
    }

    # Service definition
    # Tags are set via __SERVICE_TAGS__ variable (generated by deployment script)
    # - External access: Full Traefik tags for routing
    # - Internal only: Simple tags like ["api"]
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
        path     = "${__HEALTH_CHECK_PATH__:-/health}"
        interval = "10s"
        timeout  = "2s"
        method   = "GET"
      }

      # Readiness check
      check {
        type     = "http"
        port     = "http"
        path     = "${__READINESS_CHECK_PATH__:-/ready}"
        interval = "10s"
        timeout  = "2s"
        method   = "GET"
      }
    }
  }
}

