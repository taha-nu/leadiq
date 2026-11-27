# LeadIQ on AWS (AWS Academy Sandbox): one EC2 server running the Docker
# Compose stack (API, dashboard, Prometheus, Grafana), an S3 bucket as the
# DVC remote, and CloudWatch alarms with SNS email alerts.
#
# The Sandbox only allows EC2, S3, CloudWatch, SNS and the pre-made LabRole /
# LabInstanceProfile (no ECS or ECR), and deletes everything when the lab
# session ends.
#
#   terraform init
#   terraform apply      # about 5 minutes until the app answers
#   terraform destroy    # or let the session end

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = var.project } }
}

data "aws_caller_identity" "me" {}

# ---------------------------------------------------------------- S3 (DVC remote)
resource "aws_s3_bucket" "dvc" {
  bucket        = "${var.project}-dvc-${data.aws_caller_identity.me.account_id}" # names are global
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "dvc" {
  bucket                  = aws_s3_bucket.dvc.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------- Networking
# The default VPC keeps this simple: a public IP, no NAT gateway or load balancer
data "aws_vpc" "default" { default = true }

resource "aws_security_group" "app" {
  name        = "${var.project}-app"
  description = "LeadIQ API, dashboard and Grafana"
  vpc_id      = data.aws_vpc.default.id

  dynamic "ingress" {
    for_each = { api = 8000, dashboard = 8501, grafana = 3000 }
    content {
      description = ingress.key
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = [var.allowed_cidr]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------------------------------------------------------------- EC2 server
# Latest Amazon Linux 2023
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = var.instance_profile # pre-made LabInstanceProfile
  user_data              = templatefile("${path.module}/user_data.sh.tftpl", { repo_url = var.repo_url })

  root_block_device {
    volume_size = 20 # GB, room for the Docker images
    volume_type = "gp3"
  }

  tags = { Name = "${var.project}-server" }
}

# ---------------------------------------------------------------- CloudWatch + SNS
resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email # AWS sends a confirmation email first
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.project}-cpu-high"
  alarm_description   = "LeadIQ server CPU above 80% for 10 minutes"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  dimensions          = { InstanceId = aws_instance.app.id }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "status_check" {
  alarm_name          = "${var.project}-server-down"
  alarm_description   = "LeadIQ server failed its EC2 status check"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  dimensions          = { InstanceId = aws_instance.app.id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
