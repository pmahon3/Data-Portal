variable "service" {
  description = "Service name (used in job/group/task/service names)."
  type        = string
  default     = "backend"
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
  default     = "backend"
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

variable "health_base" {
  description = "URL path prefix for health/ready checks (without leading slash)."
  type        = string
  default     = "api"
}

variable "runtime_env" {
  description = "Newline-separated KEY=VALUE pairs. May contain pack template snippets (e.g. [[ var \"nomad_environment_url\" . ]]) evaluated via tpl at render time."
  type        = string
  default     = ""
}

variable "api_gateway" {
  description = "Backend public base URL for frontend proxy / API clients (optional)."
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
  description = "Traefik router name (sanitized), e.g. backend-staging."
  type        = string
  default     = "backend"
}

variable "environment_sanitized" {
  description = "DNS/path-safe environment slug (used in Traefik PathPrefix)."
  type        = string
  default     = "default"
}

variable "hostname" {
  description = "Primary public hostname for Traefik Host() (no scheme)."
  type        = string
  default     = ""
}

variable "public_domain" {
  description = "Optional extra hostname OR'd into the Traefik Host rule (from PUBLIC_DOMAIN)."
  type        = string
  default     = ""
}

variable "secret_encryption_key" {
  description = "Application secret encryption key (from CI/Nomad Variables)."
  type        = string
  default     = ""
}
