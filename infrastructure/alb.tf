data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-${var.environment}"
  description = "Allow HTTP from CloudFront"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTP from CloudFront"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-alb-sg" }
}

resource "aws_lb" "backend" {
  name               = "${var.project_name}-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  idle_timeout               = 3600
  drop_invalid_header_fields = true

  tags = { Name = "${var.project_name}-alb" }
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-tg-${var.environment}"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 10
    matcher             = "200"
  }

  deregistration_delay = 30
  tags                 = { Name = "${var.project_name}-tg" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.backend.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Access denied"
      status_code  = "403"
    }
  }

  tags = { Name = "${var.project_name}-http-listener" }
}

resource "aws_lb_listener_rule" "cloudfront_verified" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 1

  condition {
    http_header {
      http_header_name = "X-CloudFront-Secret"
      values           = [random_password.cloudfront_secret.result]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  tags = { Name = "${var.project_name}-cf-verified-rule" }
}
