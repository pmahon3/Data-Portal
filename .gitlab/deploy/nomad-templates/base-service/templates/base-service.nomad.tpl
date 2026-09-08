# Base Nomad job pack template for any service
# This template uses Nomad Pack variables ([[ var "…" . ]]) for substitution.
# Defaults live in variables.hcl; CI overrides via the vars file from nomad_deploy.sh.
# Copy this pack into <service>/deploy and specialize (ports, env, Traefik PathPrefix, health paths).
# Legacy envsubst twin: ../base-service.template.nomad (${__VARIABLE__}).

job "[[ var "service" . ]]-[[ var "environment" . ]]" {
  datacenters = [[ var "datacenters" . | toStringList ]]
  namespace   = "[[ var "namespace" . ]]"
  type        = "service"

  # Constraints to avoid specific nodes
  # ${meta.role} / ${meta.node_class} are Nomad interpolations (left literal for the agent).
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
    # ${node.unique.name} is a Nomad interpolation (left literal for the agent).
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

  group "[[ var "service" . ]]-[[ var "environment" . ]]" {
    # At least `count=2` instances are needed for true zero-downtime
    # Default for count is in variables.hcl (pack defaults; override via --var / var-file).
    count = [[ var "count" . ]]

    shutdown_delay = "10s" # Keep the alloc alive briefly on stop so Nomad can deregister the service before killing the task and give Traefik time to stop sending traffic.

    network {
      port "http" {
        # Dynamic port allocation (can be overridden in service-specific templates)
      }
    }

    task "[[ var "service" . ]]-[[ var "environment" . ]]" {
      driver = "[[ var "job_driver" . ]]"

      config {
        image        = "[[ var "image_name" . ]]:[[ var "image_tag" . ]]"
        force_pull   = "[[ var "image_force_pull" . ]]"
        ports        = ["http"]
        network_mode = "bridge"

        # Registry authentication (if needed)
        auth {
          username       = "[[ var "registry_username" . ]]"
          password       = "[[ var "registry_password" . ]]"
          server_address = "[[ var "registry_server" . ]]"
        }

        # Disable Docker's native HEALTHCHECK; Nomad doesn't use it for its own health monitoring, so disabling avoids redundant health checks.
        # Nomad health monitoring is via `check` block.
        healthchecks {
          disable = true
        }
      }

      # Environment variables (service-specific templates should extend this)
      env {
        CI_ENVIRONMENT_NAME = "[[ var "environment" . ]]"
        SERVICE_NAME        = "[[ var "service" . ]]"
      }

      template {
        # runtime_env may embed pack snippets; tpl evaluates them against pack vars
        data        = <<EOF
[[ tpl (var "runtime_env" .) . ]]
        EOF
        destination = "local/runtime.env"
        env         = true
        change_mode = "restart"
      }

      template {
        # runtime_secrets from __RUNTIME_SECRETS__; tpl like runtime_env
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
          [[ tpl (var "runtime_secrets" .) . ]]
          EOF
      }

      # Resources (can be overridden; defaults in variables.hcl)
      resources {
        cpu    = [[ var "resource_cpu" . ]]
        memory = [[ var "resource_memory" . ]]
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
    # Tags: built here from enable_traefik / hostname / public_domain (pack path).
    # - External access (enable_traefik=true): Traefik Host() router tags
    # - Internal only: service name tag (service discovery)
    # Specialize in service packs (e.g. backend PathPrefix, frontend public_domain OR).
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

      # Health check
      check {
        type     = "http"
        port     = "http"
        path     = "[[ var "health_check_path" . ]]"
        interval = "10s"
        timeout  = "2s"
        method   = "GET"
      }

      # Readiness check
      check {
        type     = "http"
        port     = "http"
        path     = "[[ var "readiness_check_path" . ]]"
        interval = "10s"
        timeout  = "2s"
        method   = "GET"
      }
    }
  }
}
