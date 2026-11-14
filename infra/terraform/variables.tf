variable "project" {
  type    = string
  default = "leadiq"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "github_repo" {
  description = "owner/name of the GitHub repo allowed to deploy"
  type        = string
  default     = "taha-nu/leadiq"
}

variable "desired_count" {
  description = "Running copies of the app. 0 = stopped (no Fargate cost), 1 = running"
  type        = number
  default     = 0
}

variable "canary_weight" {
  description = "Share of requests sent to the canary model, if one is deployed"
  type        = number
  default     = 0.1
}

variable "allowed_cidr" {
  description = "Who may open the API and dashboard (0.0.0.0/0 = everyone)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "alert_email" {
  description = "Email for CloudWatch alarms (optional)"
  type        = string
  default     = ""
}
