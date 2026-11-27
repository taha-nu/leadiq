variable "project" {
  type    = string
  default = "leadiq"
}

variable "region" {
  description = "The AWS Academy Sandbox only allows us-east-1"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "Sandbox allows t2/t3 nano, micro and small"
  type        = string
  default     = "t3.small"
}

variable "instance_profile" {
  description = "Pre-made instance profile in AWS Academy"
  type        = string
  default     = "LabInstanceProfile"
}

variable "repo_url" {
  description = "Public repo the server clones (compose file + monitoring config)"
  type        = string
  default     = "https://github.com/taha-nu/leadiq.git"
}

variable "allowed_cidr" {
  description = "Who may open the app (0.0.0.0/0 = everyone)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "alert_email" {
  description = "Email for CloudWatch alarms (optional)"
  type        = string
  default     = ""
}
