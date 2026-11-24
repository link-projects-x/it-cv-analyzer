terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      # 6.28.0 added aws_lambda_permission.invoked_via_function_url (CHANGELOG), needed by the API function URL
      version = ">= 6.28, < 7.0"
    }
  }

  # Local state for the first apply. Move to an S3 backend with locking once the team shares this stack:
  # backend "s3" {
  #   bucket       = "<state bucket>"
  #   key          = "dou-cv-analyzer/terraform.tfstate"
  #   region       = "us-east-1"
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project = var.project
    }
  }
}
