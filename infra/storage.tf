data "aws_caller_identity" "current" {}

# raw/dou-<id>.html        scraper output, metadata: url, scraped-at, category
# processed/dou-<id>.json  parser output, contracts/vacancy.schema.json
# failed/dou-<id>.json     parser failures with the reason
# cv/<uuid>.<pdf|docx|txt> uploaded CVs, deleted after a successful parse (var.cv_delete_after_parse)
# profiles/<uuid>.json     cv output, contracts/profile.schema.json
# failed-cv/<uuid>.json    cv failures with the reason; the CV stays in cv/
# index/vacancies.jsonl    indexer output: one vacancy + embedding per line
# jobs/<uuid>.json         api: job marker (created_at, format, size), written by POST /uploads
# matches/<uuid>.json      matcher output, contracts/match-response.schema.json
# failed-match/<uuid>.json matcher failures with the reason
# models/salary/<md5>.tar.gz  salary model for SageMaker (only with var.enable_salary_endpoint)
resource "aws_s3_bucket" "data" {
  bucket = "${var.project}-data-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# A bucket has one notification configuration, so every Lambda trigger lives in this resource.
# The address stays raw_to_parser so the existing state entry is updated, not replaced.
resource "aws_s3_bucket_notification" "raw_to_parser" {
  bucket = aws_s3_bucket.data.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.parser.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/"
    filter_suffix       = ".html"
  }

  # One block per extension: a filter takes a single suffix
  dynamic "lambda_function" {
    for_each = [".pdf", ".docx", ".txt"]
    content {
      lambda_function_arn = aws_lambda_function.cv.arn
      events              = ["s3:ObjectCreated:*"]
      filter_prefix       = "cv/"
      filter_suffix       = lambda_function.value
    }
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.matcher.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "profiles/"
    filter_suffix       = ".json"
  }

  depends_on = [
    aws_lambda_permission.s3_invokes_parser,
    aws_lambda_permission.s3_invokes_cv,
    aws_lambda_permission.s3_invokes_matcher,
  ]
}

# Upload-related objects expire after var.upload_retention_days. profiles/ has no rule and stays.
resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  dynamic "rule" {
    for_each = ["cv/", "failed-cv/", "matches/", "failed-match/", "jobs/", "quota/"]
    content {
      id     = "expire-${trimsuffix(rule.value, "/")}"
      status = "Enabled"
      filter {
        prefix = rule.value
      }
      expiration {
        days = var.upload_retention_days
      }
    }
  }
}

# The browser uploads the CV straight to S3 with the presigned POST from the API
resource "aws_s3_bucket_cors_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  cors_rule {
    allowed_methods = ["POST"]
    allowed_origins = [var.web_origin]
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}
