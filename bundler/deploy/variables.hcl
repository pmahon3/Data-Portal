variable "service" {
  description = "Service name (used in job/group/task/service names)."
  type        = string
  default     = "bundler"
}

variable "environment" {
  description = "Deployment environment suffix (e.g. staging, review-my-branch)."
  type        = string
  default     = "staging"
}

variable "datacenters" {
  description = "Nomad datacenters eligible for placement."
  type        = list(string)
  default     = ["dc1"]
}

variable "namespace" {
  description = "Nomad namespace."
  type        = string
  default     = "default"
}

variable "count" {
  description = "Number of group instances."
  type        = number
  default     = 1
}

variable "job_driver" {
  description = "Task driver."
  type        = string
  default     = "docker"
}

variable "image_name" {
  description = "Container image repository (without tag)."
  type        = string
  default     = "bundler"
}

variable "image_tag" {
  description = "Container image tag."
  type        = string
  default     = "latest"
}

variable "image_force_pull" {
  description = "Whether Docker should always pull the image."
  type        = string
  default     = "true"
}

variable "registry_username" {
  description = "Container registry username."
  type        = string
  default     = ""
}

variable "registry_password" {
  description = "Container registry password."
  type        = string
  default     = ""
}

variable "registry_server" {
  description = "Container registry server address."
  type        = string
  default     = ""
}

variable "resource_cpu" {
  description = "CPU MHz reserved for the task."
  type        = number
  default     = 1000
}

variable "resource_memory" {
  description = "Memory MB reserved for the task."
  type        = number
  default     = 1024
}

variable "health_check_path" {
  description = "HTTP liveness path. Observability app only; not injected by CI."
  type        = string
  default     = "/actuator/health/live"
}

variable "readiness_check_path" {
  description = "HTTP readiness path. Observability app only; not injected by CI."
  type        = string
  default     = "/actuator/health/ready"
}

variable "runtime_env" {
  description = "Newline-separated KEY=VALUE pairs. May contain pack template snippets (e.g. [[ var \"nomad_environment_url\" . ]]) evaluated via tpl at render time."
  type        = string
  default     = ""
}

variable "runtime_secrets" {
  description = "Newline-separated secret KEY=VALUE pairs for NOMAD_SECRETS_DIR (from __SECRETS_BUNDLER__). May contain pack [[ var … ]] snippets via tpl."
  type        = string
  default     = ""
}

variable "api_gateway" {
  description = "Declared because nomad_deploy_pack.sh always writes this var. Unused by the bundler job."
  type        = string
  default     = ""
}

variable "nomad_environment_url" {
  description = "Public https URL for this deployment (Traefik host)."
  type        = string
  default     = ""
}

variable "enable_traefik" {
  description = "When true, emit Traefik router tags for external access."
  type        = bool
  default     = false
}

variable "router_name" {
  description = "Traefik router name (sanitized), e.g. bundler-staging."
  type        = string
  default     = "bundler"
}

variable "hostname" {
  description = "Primary public hostname for Traefik Host() (no scheme)."
  type        = string
  default     = ""
}
