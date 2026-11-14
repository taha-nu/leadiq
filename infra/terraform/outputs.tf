output "dvc_remote" {
  description = "Use with: dvc remote add -d storage <value>"
  value       = "s3://${aws_s3_bucket.dvc.bucket}/dvc"
}

output "ecr_api" {
  value = aws_ecr_repository.repo["api"].repository_url
}

output "ecr_dashboard" {
  value = aws_ecr_repository.repo["dashboard"].repository_url
}

output "github_deploy_role_arn" {
  description = "Save as the AWS_DEPLOY_ROLE_ARN secret in GitHub"
  value       = aws_iam_role.github_deploy.arn
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service" {
  value = aws_ecs_service.app.name
}
