output "ecr_repository_url" {
  description = "ECR repository URL for backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.backend.name
}

output "alb_dns_name" {
  value = aws_lb.backend.dns_name
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.main.domain_name
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "static_assets_bucket" {
  value = aws_s3_bucket.static_assets.id
}

output "site_url" {
  value = var.domain_name != "" ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "websocket_url" {
  value = var.domain_name != "" ? "wss://${var.domain_name}/interact-s2s" : "wss://${aws_cloudfront_distribution.main.domain_name}/interact-s2s"
}
