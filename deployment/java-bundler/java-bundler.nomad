variable "java_bundler_image" {
  type        = string
  description = "Docker image for the Java bundler service"
  default     = "registry.rcg.sfu.ca/rcg/inn-data-portal/java-bundler:s3upload"
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

variable "archive_temp_dir" {
  type        = string
  description = "Directory where Java bundler writes local ZIPs and temporary staged downloads"
  default     = "/mnt/bundler"
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

variable "download_connect_timeout_seconds" {
  type        = number
  description = "HTTP connect timeout for source-file downloads"
  default     = 5
}

variable "download_request_timeout_seconds" {
  type        = number
  description = "Per-source-file HTTP request timeout"
  default     = 300
}

variable "download_max_attempts" {
  type        = number
  description = "Maximum download attempts per source file"
  default     = 3
}

variable "download_retry_delay_millis" {
  type        = number
  description = "Delay between source-file download retries"
  default     = 500
}

variable "jobs_postgres_username" {
  type        = string
  description = "PostgreSQL username for Java bundler job metadata"
}

variable "jobs_postgres_password" {
  type        = string
  description = "PostgreSQL password for Java bundler job metadata"
}

variable "jobs_schema_mode" {
  type        = string
  description = "Hibernate schema mode. Use none when schema.sql owns DDL."
  default     = "none"
}

variable "job_lock_duration_seconds" {
  type        = number
  description = "Seconds a worker owns a claimed job before another instance may retry it"
  default     = 7200
}

variable "job_claim_scan_enabled" {
  type        = bool
  description = "Enable scanning PostgreSQL for pending or expired bundle jobs"
  default     = true
}

variable "job_claim_scan_delay_millis" {
  type        = number
  description = "Delay between claim-scan runs"
  default     = 5000
}

variable "job_claim_scan_batch_size" {
  type        = number
  description = "Maximum claimable jobs to queue per scan"
  default     = 20
}

variable "job_retention_enabled" {
  type        = bool
  description = "Enable cleanup of old completed or failed bundle jobs and artifacts"
  default     = true
}

variable "job_completed_retention_hours" {
  type        = number
  description = "Hours to retain terminal bundle jobs and artifacts"
  default     = 168
}

variable "job_retention_initial_delay_millis" {
  type        = number
  description = "Delay before first retention cleanup run"
  default     = 60000
}

variable "job_retention_scan_delay_millis" {
  type        = number
  description = "Delay between retention cleanup runs"
  default     = 3600000
}

variable "job_retention_batch_size" {
  type        = number
  description = "Maximum terminal jobs to clean up per retention run"
  default     = 100
}

variable "output_object_storage_endpoint" {
  type        = string
  description = "S3-compatible endpoint for completed bundle archives"
  default     = ""
}

variable "output_object_storage_region" {
  type        = string
  description = "S3-compatible region for completed bundle archives"
  default     = "us-east-1"
}

variable "output_object_storage_bucket" {
  type        = string
  description = "Bucket for completed bundle archives"
  default     = ""
}

variable "output_object_storage_key_prefix" {
  type        = string
  description = "Object key prefix for completed bundle archives"
  default     = "bundles"
}

variable "output_object_storage_access_key_id" {
  type        = string
  description = "Access key ID for completed bundle archive uploads"
  default     = ""
}

variable "output_object_storage_secret_access_key" {
  type        = string
  description = "Secret access key for completed bundle archive uploads"
  default     = ""
}

variable "output_object_storage_path_style_access" {
  type        = bool
  description = "Use path-style S3 access for completed bundle archive URLs"
  default     = true
}

variable "output_object_storage_presigned_url_expiration_seconds" {
  type        = number
  description = "Seconds completed bundle presigned download URLs remain valid"
  default     = 3600
}

job "java-bundler" {
  datacenters = ["rmcintos-fir-cloud"]
  namespace   = "apps"
  type        = "service"

  group "java-bundler-group" {
    count = 3

    volume "bundler_tmp" {
      type            = "csi"
      source          = "bundler-nfs"
      read_only       = false
      access_mode     = "multi-node-multi-writer"
      attachment_mode = "file-system"
    }

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

      volume_mount {
        volume      = "bundler_tmp"
        destination = "/mnt/bundler"
        read_only   = false
      }

      env = {
        SERVER_PORT = "8888"
        BUNDLER_INSTANCE_ID = "${NOMAD_ALLOC_ID}"

        BUNDLER_ARCHIVE_STRATEGY = "${var.archive_strategy}"
        BUNDLER_ARCHIVE_TEMP_DIR = "${var.archive_temp_dir}"

        BUNDLER_WORKER_THREADS        = "${var.worker_threads}"
        BUNDLER_WORKER_QUEUE_CAPACITY = "${var.worker_queue_capacity}"

        BUNDLER_DOWNLOAD_THREADS     = "${var.download_threads}"
        BUNDLER_DOWNLOAD_PARALLELISM = "${var.download_parallelism}"

        BUNDLER_DOWNLOAD_CONNECT_TIMEOUT_SECONDS = "${var.download_connect_timeout_seconds}"
        BUNDLER_DOWNLOAD_REQUEST_TIMEOUT_SECONDS = "${var.download_request_timeout_seconds}"
        BUNDLER_DOWNLOAD_MAX_ATTEMPTS            = "${var.download_max_attempts}"
        BUNDLER_DOWNLOAD_RETRY_DELAY_MILLIS      = "${var.download_retry_delay_millis}"

        BUNDLER_JOB_LOCK_DURATION_SECONDS       = "${var.job_lock_duration_seconds}"
        BUNDLER_JOB_CLAIM_SCAN_ENABLED          = "${var.job_claim_scan_enabled}"
        BUNDLER_JOB_CLAIM_SCAN_DELAY_MILLIS     = "${var.job_claim_scan_delay_millis}"
        BUNDLER_JOB_CLAIM_SCAN_BATCH_SIZE       = "${var.job_claim_scan_batch_size}"
        BUNDLER_JOB_RETENTION_ENABLED           = "${var.job_retention_enabled}"
        BUNDLER_JOB_COMPLETED_RETENTION_HOURS   = "${var.job_completed_retention_hours}"
        BUNDLER_JOB_RETENTION_INITIAL_DELAY_MILLIS = "${var.job_retention_initial_delay_millis}"
        BUNDLER_JOB_RETENTION_SCAN_DELAY_MILLIS = "${var.job_retention_scan_delay_millis}"
        BUNDLER_JOB_RETENTION_BATCH_SIZE        = "${var.job_retention_batch_size}"

        BUNDLER_OUTPUT_OBJECT_STORAGE_ENDPOINT          = "${var.output_object_storage_endpoint}"
        BUNDLER_OUTPUT_OBJECT_STORAGE_REGION            = "${var.output_object_storage_region}"
        BUNDLER_OUTPUT_OBJECT_STORAGE_BUCKET            = "${var.output_object_storage_bucket}"
        BUNDLER_OUTPUT_OBJECT_STORAGE_KEY_PREFIX        = "${var.output_object_storage_key_prefix}"
        BUNDLER_OUTPUT_OBJECT_STORAGE_ACCESS_KEY_ID     = "${var.output_object_storage_access_key_id}"
        BUNDLER_OUTPUT_OBJECT_STORAGE_SECRET_ACCESS_KEY = "${var.output_object_storage_secret_access_key}"
        BUNDLER_OUTPUT_OBJECT_STORAGE_PATH_STYLE_ACCESS = "${var.output_object_storage_path_style_access}"
        BUNDLER_OUTPUT_OBJECT_STORAGE_PRESIGNED_URL_EXPIRATION_SECONDS = "${var.output_object_storage_presigned_url_expiration_seconds}"
      }

      template {
        destination = "secrets/java-bundler.env"
        env         = true
        change_mode = "restart"

        data = <<EOH
BUNDLER_JOBS_POSTGRES_JDBC_URL="jdbc:postgresql://{{ range nomadService 1 "apps" "postgres-db-staging" }}{{ .Address }}:{{ .Port }}{{ end }}/inn_application"
BUNDLER_JOBS_POSTGRES_USERNAME="${var.jobs_postgres_username}"
BUNDLER_JOBS_POSTGRES_PASSWORD="${var.jobs_postgres_password}"
BUNDLER_JOBS_SCHEMA_MODE="${var.jobs_schema_mode}"
EOH
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
