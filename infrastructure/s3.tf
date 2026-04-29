resource "aws_s3_bucket" "static_assets" {
  bucket = "${var.project_name}-static-${var.environment}"
}

resource "aws_s3_bucket_public_access_block" "static_assets" {
  bucket                  = aws_s3_bucket.static_assets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "cloudfront_logs" {
  bucket = "${var.project_name}-cf-logs-${var.environment}"
}

resource "aws_s3_bucket_public_access_block" "cloudfront_logs" {
  bucket                  = aws_s3_bucket.cloudfront_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudfront_logs" {
  bucket = aws_s3_bucket.cloudfront_logs.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_ownership_controls" "cloudfront_logs" {
  bucket = aws_s3_bucket.cloudfront_logs.id
  rule { object_ownership = "BucketOwnerPreferred" }
}

resource "aws_s3_bucket_lifecycle_configuration" "cloudfront_logs" {
  bucket = aws_s3_bucket.cloudfront_logs.id
  rule {
    id     = "expire-old-logs"
    status = "Enabled"
    filter {}
    expiration { days = 90 }
  }
}

resource "aws_cloudfront_origin_access_control" "static_assets" {
  name                              = "${var.project_name}-static-oac"
  description                       = "OAC for frontend static assets"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "random_password" "cloudfront_secret" {
  length  = 32
  special = false
}
