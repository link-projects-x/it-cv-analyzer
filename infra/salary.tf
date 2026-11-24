# SageMaker serverless endpoint for the salary model (ml/salary). Created only with var.enable_salary_endpoint = true;
# otherwise the matcher returns a fake salary block (model_version "fake-disabled") and nothing here exists.
#
# Before apply: train with the pinned versions and package (ml/salary/README.md -> SageMaker):
#   python ml/salary/train.py && ml/salary/package.sh      # -> dist/model.tar.gz

locals {
  salary_model_tar = "${local.dist}/model.tar.gz"
  # fileexists first: with the endpoint disabled the archive does not have to exist
  salary_model_md5 = fileexists(local.salary_model_tar) ? filemd5(local.salary_model_tar) : ""
  salary_suffix    = substr(local.salary_model_md5, 0, 8)
  # <account>.dkr.ecr.<region>.amazonaws.com/<repository>:<tag>
  salary_image_registry   = split(".", var.salary_image_uri)[0]
  salary_image_region     = split(".", var.salary_image_uri)[3]
  salary_image_repository = split(":", split("/", var.salary_image_uri)[1])[0]
}

resource "aws_s3_object" "salary_model" {
  count  = var.enable_salary_endpoint ? 1 : 0
  bucket = aws_s3_bucket.data.id
  key    = "models/salary/${local.salary_model_md5}.tar.gz" # new key per archive: a SageMaker model is immutable
  source = local.salary_model_tar
  etag   = local.salary_model_md5

  lifecycle {
    precondition {
      condition     = local.salary_model_md5 != ""
      error_message = "dist/model.tar.gz is missing: run ml/salary/train.py and ml/salary/package.sh."
    }
  }
}

data "aws_iam_policy_document" "sagemaker_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "salary" {
  count              = var.enable_salary_endpoint ? 1 : 0
  name               = "${var.project}-salary"
  assume_role_policy = data.aws_iam_policy_document.sagemaker_assume.json
}

# Assumption: these are the permissions a SageMaker execution role needs to pull the AWS image, read the model
# archive and write endpoint logs and metrics. Not checked against a live endpoint.
data "aws_iam_policy_document" "salary" {
  statement {
    sid       = "ReadModel"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/models/salary/*"]
  }
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid       = "PullImage"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
    resources = ["arn:aws:ecr:${local.salary_image_region}:${local.salary_image_registry}:repository/${local.salary_image_repository}"]
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/Endpoints/${var.project}-salary*"]
  }
  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "salary" {
  count  = var.enable_salary_endpoint ? 1 : 0
  role   = aws_iam_role.salary[0].id
  policy = data.aws_iam_policy_document.salary.json
}

resource "aws_sagemaker_model" "salary" {
  count              = var.enable_salary_endpoint ? 1 : 0
  name               = "${var.project}-salary-${local.salary_suffix}"
  execution_role_arn = aws_iam_role.salary[0].arn

  primary_container {
    image          = var.salary_image_uri
    model_data_url = "s3://${aws_s3_bucket.data.bucket}/${aws_s3_object.salary_model[0].key}"
    # Archive layout from ml/salary/package.sh: model files at the root, handlers in code/
    environment = {
      SAGEMAKER_PROGRAM             = "inference.py"
      SAGEMAKER_SUBMIT_DIRECTORY    = "/opt/ml/model/code"
      SAGEMAKER_CONTAINER_LOG_LEVEL = "20"
      SAGEMAKER_REGION              = var.region
    }
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_iam_role_policy.salary]
}

resource "aws_sagemaker_endpoint_configuration" "salary" {
  count = var.enable_salary_endpoint ? 1 : 0
  name  = "${var.project}-salary-${local.salary_suffix}"

  production_variants {
    variant_name = "AllTraffic"
    model_name   = aws_sagemaker_model.salary[0].name

    serverless_config {
      max_concurrency   = var.salary_max_concurrency
      memory_size_in_mb = var.salary_memory_mb
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_sagemaker_endpoint" "salary" {
  count                = var.enable_salary_endpoint ? 1 : 0
  name                 = "${var.project}-salary"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.salary[0].name
}
