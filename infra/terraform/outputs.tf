output "dashboard_url" {
  value = "http://${aws_instance.app.public_ip}:8501"
}

output "api_docs_url" {
  value = "http://${aws_instance.app.public_ip}:8000/docs"
}

output "grafana_url" {
  value = "http://${aws_instance.app.public_ip}:3000"
}

output "dvc_remote" {
  description = "Use with: dvc remote add -d -f storage <value>"
  value       = "s3://${aws_s3_bucket.dvc.bucket}/dvc"
}
