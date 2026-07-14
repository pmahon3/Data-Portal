variable "database_url" {
  type        = string
  description = "Async SQLAlchemy Postgres URL, for example postgresql+asyncpg://user:password@host:5432/database"
}

variable "cleanup_image" {
  type        = string
  description = "Docker image for the storage events cleanup job"
  default     = "registry.rcg.sfu.ca/rcg/inn-data-portal/storage-events-cleanup:latest"
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

job "storage-events-cleanup" {
  datacenters = ["rmcintos-cedar-cloud"]
  type        = "batch"

  periodic {
    crons            = ["30 2 * * *"]
    prohibit_overlap = true
  }

  group "storage-events-cleanup-group" {
    count = 1

    task "cleanup-storage-events" {
      driver = "docker"

      config {
        image      = var.cleanup_image
        force_pull = true
        args       = ["--retention-days", "30"]

        auth {
          username       = var.registry_username
          password       = var.registry_password
          server_address = var.registry_server
        }
      }

      env = {
        DATABASE_URL = var.database_url
      }

      resources {
        cpu    = 250
        memory = 256
      }

      restart {
        attempts = 1
        interval = "10m"
        delay    = "30s"
        mode     = "fail"
      }
    }
  }
}
