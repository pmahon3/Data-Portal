variable "database_url" {
  type        = string
  description = "Async SQLAlchemy Postgres URL, for example postgresql+asyncpg://user:password@host:5432/database"
}

variable "object_storage_endpoint_url" {
  type        = string
  description = "S3-compatible object storage endpoint URL used to verify create events"
}

variable "object_storage_access_key_id" {
  type        = string
  description = "S3-compatible object storage access key ID used to verify create events"
}

variable "object_storage_secret_access_key" {
  type        = string
  description = "S3-compatible object storage secret access key used to verify create events"
}

variable "object_storage_region" {
  type        = string
  description = "S3-compatible object storage region used to verify create events"
  default     = ""
}

variable "worker_image" {
  type        = string
  description = "Docker image for the storage events worker"
  default     = "registry.rcg.sfu.ca/rcg/inn-data-portal/storage-events-worker:latest"
}

variable "registry_username" {
  type        = string
  description = "Container registry username"
  default     = "INN-Data-Portal"
}

variable "registry_password" {
  type        = string
  description = "Container registry password or token"
}

variable "registry_server" {
  type        = string
  description = "Container registry server address"
  default     = "https://registry.rcg.sfu.ca"
}

# `var` variables cannot be used to dynamically populate a nomad job name. 
# since this job is not used in an automated pipeline, we accept the compromise 
# substitute using a different mechanism
job "storage-events-worker-${__ENVIRONMENT__}" {
  datacenters = ["rmcintos-fir-cloud"]
  namespace   = "apps"
  type        = "service"

  constraint {
    attribute = "${meta.node_class}"
    value     = "prod"
  }

  group "storage-events-group" {
    count = 1

    task "process-storage-events" {
      driver = "docker"

      config {
        image      = var.worker_image
        force_pull = true
        args       = ["--watch", "--batch-size", "1000", "--interval", "5"]

        auth {
          username       = var.registry_username
          password       = var.registry_password
          server_address = var.registry_server
        }
      }

      env = {
        DATABASE_URL                      = var.database_url
        OBJECT_STORAGE_ENDPOINT_URL       = var.object_storage_endpoint_url
        OBJECT_STORAGE_ACCESS_KEY_ID      = var.object_storage_access_key_id
        OBJECT_STORAGE_SECRET_ACCESS_KEY  = var.object_storage_secret_access_key
        OBJECT_STORAGE_REGION             = var.object_storage_region
      }

      resources {
        cpu    = 500
        memory = 512
      }

      restart {
        attempts = 3
        interval = "5m"
        delay    = "30s"
        mode     = "delay"
      }
    }
  }
}
