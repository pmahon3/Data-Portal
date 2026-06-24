variable "database_url" {
  type        = string
  description = "Async SQLAlchemy Postgres URL, for example postgresql+asyncpg://user:password@host:5432/database"
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

job "storage-events-worker" {
  datacenters = ["rmcintos-cedar-cloud"]
  type        = "service"

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
        DATABASE_URL = var.database_url
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
