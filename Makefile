PROJECT_NAME := nova-sonic-strands
AWS_REGION := us-east-1
ENVIRONMENT := dev
ECR_REPO := $(PROJECT_NAME)-backend

.PHONY: help init plan apply destroy build push deploy frontend-build frontend-deploy

help:
	@echo "Nova Sonic 2 + Strands Pattern"
	@echo ""
	@echo "Infrastructure:"
	@echo "  init     - Initialize Terraform"
	@echo "  plan     - Plan infrastructure changes"
	@echo "  apply    - Apply infrastructure"
	@echo "  destroy  - Destroy infrastructure"
	@echo ""
	@echo "Backend:"
	@echo "  build    - Build Docker image"
	@echo "  push     - Push to ECR"
	@echo "  deploy   - Force new ECS deployment"
	@echo ""
	@echo "Frontend:"
	@echo "  frontend-build  - Build frontend"
	@echo "  frontend-deploy - Deploy to S3 + invalidate CloudFront"

# --- Infrastructure ---

init:
	cd infrastructure && terraform init

plan:
	cd infrastructure && terraform plan

apply:
	cd infrastructure && terraform apply

destroy:
	cd infrastructure && terraform destroy

# --- Backend ---

build:
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text))
	$(eval ECR_URI := $(ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO))
	cd backend && docker build --platform linux/arm64 -t $(ECR_URI):latest .

push: build
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text))
	$(eval ECR_URI := $(ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO))
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
	docker push $(ECR_URI):latest

deploy:
	$(eval CLUSTER := $(shell cd infrastructure && terraform output -raw ecs_cluster_name))
	$(eval SERVICE := $(shell cd infrastructure && terraform output -raw ecs_service_name))
	aws ecs update-service --cluster $(CLUSTER) --service $(SERVICE) --force-new-deployment --region $(AWS_REGION)

# --- Frontend ---

frontend-build:
	$(eval WS_URL := $(shell cd infrastructure && terraform output -raw websocket_url))
	cd frontend && VITE_WS_URL=$(WS_URL) npm run build

frontend-deploy: frontend-build
	$(eval BUCKET := $(shell cd infrastructure && terraform output -raw static_assets_bucket))
	$(eval CF_ID := $(shell cd infrastructure && terraform output -raw cloudfront_distribution_id))
	aws s3 sync frontend/dist s3://$(BUCKET) --delete --region $(AWS_REGION)
	aws cloudfront create-invalidation --distribution-id $(CF_ID) --paths "/*"
