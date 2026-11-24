# Zips are built by scripts/build_lambdas.sh into dist/. Run it before `terraform apply`.
locals {
  dist = "${path.module}/../dist"
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/aws/lambda/${var.project}-scraper"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "parser" {
  name              = "/aws/lambda/${var.project}-parser"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "cv" {
  name              = "/aws/lambda/${var.project}-cv"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "scraper" {
  function_name    = "${var.project}-scraper"
  role             = aws_iam_role.scraper.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "scraper.handler.lambda_handler"
  filename         = "${local.dist}/scraper.zip"
  source_code_hash = filebase64sha256("${local.dist}/scraper.zip")
  timeout          = 900 # Lambda maximum. Local full run on 2026-10-31: 23-40 vacancies per minute, ~7 min for 237.
  # The run stops 30 s before the timeout and the next run continues from where it stopped.
  memory_size      = 256

  environment {
    variables = {
      BUCKET        = aws_s3_bucket.data.bucket
      CATEGORY      = "AI/ML"
      MAX_NEW       = tostring(var.scraper_max_new)
      DELAY_SECONDS = "1.0"
    }
  }

  depends_on = [aws_cloudwatch_log_group.scraper]
}

resource "aws_lambda_function" "parser" {
  function_name                  = "${var.project}-parser"
  role                           = aws_iam_role.parser.arn
  runtime                        = "python3.13"
  architectures                  = ["arm64"]
  handler                        = "parser.handler.lambda_handler"
  filename                       = "${local.dist}/parser.zip"
  source_code_hash               = filebase64sha256("${local.dist}/parser.zip")
  timeout                        = 120 # one vacancy per invocation; the default 3 s is too short for an LLM call
  memory_size                    = 512
  reserved_concurrent_executions = var.parser_reserved_concurrency

  environment {
    variables = {
      BUCKET   = aws_s3_bucket.data.bucket
      MODEL_ID = var.model_id
      EFFORT   = var.parser_effort
    }
  }

  depends_on = [aws_cloudwatch_log_group.parser]
}

resource "aws_lambda_function" "cv" {
  function_name    = "${var.project}-cv"
  role             = aws_iam_role.cv.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "cv.handler.lambda_handler"
  filename         = "${local.dist}/cv.zip"
  source_code_hash = filebase64sha256("${local.dist}/cv.zip")
  timeout                        = 120 # one CV per invocation: text extraction + one LLM call
  memory_size                    = 512
  reserved_concurrent_executions = var.cv_reserved_concurrency

  environment {
    variables = {
      BUCKET    = aws_s3_bucket.data.bucket
      MODEL_ID  = var.model_id
      EFFORT    = var.cv_effort
      DELETE_CV = tostring(var.cv_delete_after_parse)
    }
  }

  depends_on = [aws_cloudwatch_log_group.cv]
}

resource "aws_cloudwatch_event_rule" "scrape" {
  name                = "${var.project}-scrape-daily"
  schedule_expression = var.scrape_schedule
}

resource "aws_cloudwatch_event_target" "scrape" {
  rule = aws_cloudwatch_event_rule.scrape.name
  arn  = aws_lambda_function.scraper.arn
}

# Alarm when the parser starts failing (unhandled errors; handled failures go to failed/ in S3)
resource "aws_cloudwatch_metric_alarm" "parser_errors" {
  alarm_name          = "${var.project}-parser-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.parser.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

# --- step 3: indexer, matcher, HTTP API ------------------------------------

resource "aws_cloudwatch_log_group" "indexer" {
  name              = "/aws/lambda/${var.project}-indexer"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "matcher" {
  name              = "/aws/lambda/${var.project}-matcher"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.project}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "indexer" {
  function_name    = "${var.project}-indexer"
  role             = aws_iam_role.indexer.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "indexer.handler.lambda_handler"
  filename         = "${local.dist}/indexer.zip"
  source_code_hash = filebase64sha256("${local.dist}/indexer.zip")
  timeout          = 300 # reads every processed/*.json; embeds changed vacancies in batches of 96
  memory_size      = 512

  environment {
    variables = {
      BUCKET              = aws_s3_bucket.data.bucket
      EMBEDDING_MODEL_ID  = var.embedding_model_id
      EMBEDDING_DIMENSION = tostring(var.embedding_dimension)
    }
  }

  depends_on = [aws_cloudwatch_log_group.indexer]
}

# matcher and api run from the same zip with different handlers
resource "aws_lambda_function" "matcher" {
  function_name    = "${var.project}-matcher"
  role             = aws_iam_role.matcher.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "api.handler.match_handler"
  filename         = "${local.dist}/api.zip"
  source_code_hash = filebase64sha256("${local.dist}/api.zip")
  timeout                        = 120  # one profile per invocation; a serverless salary endpoint may cold-start
  memory_size                    = 1024 # cosine over the whole index in pure Python; Lambda CPU scales with memory
  reserved_concurrent_executions = var.matcher_reserved_concurrency

  environment {
    variables = {
      BUCKET              = aws_s3_bucket.data.bucket
      EMBEDDING_MODEL_ID  = var.embedding_model_id
      EMBEDDING_DIMENSION = tostring(var.embedding_dimension)
      SALARY_ENDPOINT     = var.enable_salary_endpoint ? aws_sagemaker_endpoint.salary[0].name : ""
    }
  }

  depends_on = [aws_cloudwatch_log_group.matcher]
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.project}-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "api.handler.http_handler"
  filename         = "${local.dist}/api.zip"
  source_code_hash = filebase64sha256("${local.dist}/api.zip")
  timeout                        = 10 # S3 calls only
  memory_size                    = 256
  reserved_concurrent_executions = var.api_reserved_concurrency

  environment {
    variables = {
      BUCKET = aws_s3_bucket.data.bucket
      # label:sha256 pairs; the codes themselves never reach AWS (scripts/new_access_code.py)
      ACCESS_CODES           = join(",", [for label, digest in var.access_code_hashes : "${label}:${digest}"])
      DAILY_UPLOADS_PER_CODE = tostring(var.daily_uploads_per_code)
      DAILY_UPLOADS_TOTAL    = tostring(var.daily_uploads_total)
    }
  }

  depends_on = [aws_cloudwatch_log_group.api]
}

# HTTPS endpoint for the browser. AWS does not authenticate it (auth NONE): the function checks the access code in the
# Authorization header and the daily quotas itself (services/api/api/access.py), and reserved concurrency caps
# parallel invocations. CORS preflight is answered by Lambda from this configuration.
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = [var.web_origin]
    allow_methods = ["GET", "POST"]
    allow_headers = ["content-type", "authorization"]
    max_age       = 3600
  }
}

resource "aws_cloudwatch_event_rule" "index" {
  name                = "${var.project}-index-daily"
  schedule_expression = var.index_schedule
}

resource "aws_cloudwatch_event_target" "index" {
  rule = aws_cloudwatch_event_rule.index.name
  arn  = aws_lambda_function.indexer.arn
}

# Unhandled matcher errors (throttling, network); handled failures go to failed-match/ in S3
resource "aws_cloudwatch_metric_alarm" "matcher_errors" {
  alarm_name          = "${var.project}-matcher-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.matcher.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}
