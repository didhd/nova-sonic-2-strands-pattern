variable "aws_region" {
  description = "AWS region (Nova Sonic requires us-east-1)"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "nova-sonic-strands"
}

variable "ecr_image_tag" {
  description = "Docker image tag"
  type        = string
  default     = "latest"
}

variable "domain_name" {
  description = "Custom domain name"
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID"
  type        = string
  default     = ""
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.1.0.0/16"
}

variable "container_port" {
  description = "Backend container port"
  type        = number
  default     = 8080
}
