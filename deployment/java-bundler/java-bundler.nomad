variable "java_bundler_image" {
  type        = string
  description = "Docker image for the Java bundler service"
  default     = "registry.rcg.sfu.ca/rcg/inn-data-portal/java-bundler:latest"
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

variable "archive_strategy" {
  type        = string
  description = "Java bundler archive strategy: current, batch, streaming, or hybrid"
  default     = "hybrid"
}

variable "worker_threads" {
  type        = number
  description = "Number of bundle worker threads"
  default     = 5
}

variable "worker_queue_capacity" {
  type        = number
  description = "Maximum number of queued bundle jobs"
  default     = 100
}

variable "download_threads" {
  type        = number
  description = "Global download executor thread count"
  default     = 8
}

variable "download_parallelism" {
  type        = number
  description = "Maximum concurrent downloads per bundle"
  default     = 4
}

job "java-bundler" {
  datacenters = ["rmcintos-cedar-cloud"]
  type        = "service"

  group "java-bundler-group" {
    count = 1

    network {
      port "http" {
        to = 8888
      }
    }

    task "java-bundler" {
      driver = "docker"

      config {
        image      = var.java_bundler_image
        force_pull = true
        ports      = ["http"]

        auth {
          username       = var.registry_username
          password       = var.registry_password
          server_address = var.registry_server
        }
      }

      env = {
        SERVER_PORT = "8888"

        BUNDLER_ARCHIVE_STRATEGY = "${var.archive_strategy}"
        BUNDLER_ARCHIVE_TEMP_DIR = "/tmp/bundler"

        BUNDLER_WORKER_THREADS        = "${var.worker_threads}"
        BUNDLER_WORKER_QUEUE_CAPACITY = "${var.worker_queue_capacity}"

        BUNDLER_DOWNLOAD_THREADS     = "${var.download_threads}"
        BUNDLER_DOWNLOAD_PARALLELISM = "${var.download_parallelism}"

        BUNDLER_DOWNLOAD_CONNECT_TIMEOUT_SECONDS = "5"
        BUNDLER_DOWNLOAD_REQUEST_TIMEOUT_SECONDS = "60"
        BUNDLER_DOWNLOAD_MAX_ATTEMPTS            = "3"
        BUNDLER_DOWNLOAD_RETRY_DELAY_MILLIS      = "500"
      }

      resources {
        cpu    = 1000
        memory = 1024
      }

      service {
        name     = "java-bundler"
        provider = "nomad"
        port     = "http"
        tags = [
          "bundler",
          "java-bundler"
        ]

        check {
          name     = "java-bundler-health"
          type     = "http"
          path     = "/actuator/health"
          interval = "30s"
          timeout  = "5s"
        }
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
