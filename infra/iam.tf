data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  logs_statement = {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project}-*:*"]
  }
}

# --- scraper: read/write raw/ only -----------------------------------------

resource "aws_iam_role" "scraper" {
  name               = "${var.project}-scraper"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "scraper" {
  statement {
    actions   = local.logs_statement.actions
    resources = local.logs_statement.resources
  }
  statement {
    sid       = "RawObjects"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/raw/*"]
  }
  statement {
    # HeadObject on a missing key returns 403 instead of 404 without ListBucket
    sid       = "ListForHeadObject"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*"]
    }
  }
}

resource "aws_iam_role_policy" "scraper" {
  role   = aws_iam_role.scraper.id
  policy = data.aws_iam_policy_document.scraper.json
}

# --- parser: read raw/, write processed/ and failed/, call Claude ----------

resource "aws_iam_role" "parser" {
  name               = "${var.project}-parser"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "parser" {
  statement {
    actions   = local.logs_statement.actions
    resources = local.logs_statement.resources
  }
  statement {
    sid       = "ReadRaw"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/raw/*"]
  }
  statement {
    sid     = "WriteResults"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/processed/*",
      "${aws_s3_bucket.data.arn}/failed/*",
    ]
  }
  statement {
    # Claude through the Bedrock Mantle endpoint (Anthropic SDK AnthropicBedrockMantle).
    # Action and ARN format from the AWS Service Authorization Reference for bedrock-mantle.
    sid       = "ClaudeInference"
    actions   = ["bedrock-mantle:CreateInference", "bedrock-mantle:CountTokens"]
    resources = ["arn:aws:bedrock-mantle:${var.region}:${data.aws_caller_identity.current.account_id}:project/*"]
  }
}

resource "aws_iam_role_policy" "parser" {
  role   = aws_iam_role.parser.id
  policy = data.aws_iam_policy_document.parser.json
}

# --- cv: read and delete cv/, write profiles/ and failed-cv/, call Claude --

resource "aws_iam_role" "cv" {
  name               = "${var.project}-cv"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "cv" {
  statement {
    actions   = local.logs_statement.actions
    resources = local.logs_statement.resources
  }
  statement {
    # DeleteObject: the CV is removed after a successful parse (DELETE_CV)
    sid       = "ReadAndDeleteCv"
    actions   = ["s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.data.arn}/cv/*"]
  }
  statement {
    sid     = "WriteResults"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/profiles/*",
      "${aws_s3_bucket.data.arn}/failed-cv/*",
    ]
  }
  statement {
    # As in the parser role, without CountTokens: the cv code does not call it
    sid       = "ClaudeInference"
    actions   = ["bedrock-mantle:CreateInference"]
    resources = ["arn:aws:bedrock-mantle:${var.region}:${data.aws_caller_identity.current.account_id}:project/*"]
  }
}

resource "aws_iam_role_policy" "cv" {
  role   = aws_iam_role.cv.id
  policy = data.aws_iam_policy_document.cv.json
}

# --- EventBridge rule -> scraper ------------------------------------------

resource "aws_lambda_permission" "schedule_invokes_scraper" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scraper.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.scrape.arn
}

resource "aws_lambda_permission" "s3_invokes_parser" {
  statement_id   = "AllowS3"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.parser.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.data.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_lambda_permission" "s3_invokes_cv" {
  statement_id   = "AllowS3"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.cv.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.data.arn
  source_account = data.aws_caller_identity.current.account_id
}

# --- step 3 ----------------------------------------------------------------

locals {
  # An inference profile ID (us.cohere.embed-v4:0) routes to the foundation model in several regions, so the policy
  # needs the profile ARN and the model ARN in any region. A plain model ID needs only the model ARN in var.region.
  embedding_is_profile = can(regex("^(us|eu|apac|global)\\.", var.embedding_model_id))
  embedding_model_arns = local.embedding_is_profile ? [
    "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.embedding_model_id}",
    "arn:aws:bedrock:*::foundation-model/${replace(var.embedding_model_id, "/^[a-z]+\\./", "")}",
  ] : ["arn:aws:bedrock:${var.region}::foundation-model/${var.embedding_model_id}"]
  salary_endpoint_arn = "arn:aws:sagemaker:${var.region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.project}-salary"
}

# --- indexer: read processed/, read/write index/, embed --------------------

resource "aws_iam_role" "indexer" {
  name               = "${var.project}-indexer"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "indexer" {
  statement {
    actions   = local.logs_statement.actions
    resources = local.logs_statement.resources
  }
  statement {
    sid     = "ReadVacanciesAndIndex"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/processed/*",
      "${aws_s3_bucket.data.arn}/index/*",
    ]
  }
  statement {
    sid       = "WriteIndex"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/index/*"]
  }
  statement {
    # Lists processed/; existence of index/vacancies.jsonl is checked with a prefix listing
    sid       = "ListVacanciesAndIndex"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["processed/*", "index/*"]
    }
  }
  statement {
    sid       = "Embeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = local.embedding_model_arns
  }
}

resource "aws_iam_role_policy" "indexer" {
  role   = aws_iam_role.indexer.id
  policy = data.aws_iam_policy_document.indexer.json
}

# --- matcher: read profiles/ and index/, write matches/ and failed-match/ --

resource "aws_iam_role" "matcher" {
  name               = "${var.project}-matcher"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "matcher" {
  statement {
    actions   = local.logs_statement.actions
    resources = local.logs_statement.resources
  }
  statement {
    sid     = "ReadProfileAndIndex"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/profiles/*",
      "${aws_s3_bucket.data.arn}/index/*",
    ]
  }
  statement {
    sid     = "WriteResults"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/matches/*",
      "${aws_s3_bucket.data.arn}/failed-match/*",
    ]
  }
  statement {
    # Existence checks are prefix listings (services/api/api/store.py)
    sid       = "ListForExists"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["profiles/*", "index/*"]
    }
  }
  statement {
    sid       = "Embeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = local.embedding_model_arns
  }
  dynamic "statement" {
    for_each = var.enable_salary_endpoint ? [1] : []
    content {
      sid       = "SalaryEndpoint"
      actions   = ["sagemaker:InvokeEndpoint"]
      resources = [local.salary_endpoint_arn]
    }
  }
}

resource "aws_iam_role_policy" "matcher" {
  role   = aws_iam_role.matcher.id
  policy = data.aws_iam_policy_document.matcher.json
}

# --- api: write jobs/, sign uploads to cv/, read job state ----------------

resource "aws_iam_role" "api" {
  name               = "${var.project}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "api" {
  statement {
    actions   = local.logs_statement.actions
    resources = local.logs_statement.resources
  }
  statement {
    # jobs/: the job marker. cv/: the presigned POST is signed with this role, so the upload needs PutObject here.
    # quota/: one empty marker per upload, counted for the daily limits.
    sid     = "WriteJobAndUpload"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/jobs/*",
      "${aws_s3_bucket.data.arn}/cv/*",
      "${aws_s3_bucket.data.arn}/quota/*",
    ]
  }
  statement {
    sid     = "ReadJobState"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/jobs/*",
      "${aws_s3_bucket.data.arn}/matches/*",
      "${aws_s3_bucket.data.arn}/failed-cv/*",
    ]
  }
  statement {
    sid       = "ListForExists"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["jobs/*", "cv/*", "profiles/*", "matches/*", "failed-cv/*", "failed-match/*", "quota/*"]
    }
  }
}

resource "aws_iam_role_policy" "api" {
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_lambda_permission" "s3_invokes_matcher" {
  statement_id   = "AllowS3"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.matcher.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.data.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_lambda_permission" "schedule_invokes_indexer" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.indexer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.index.arn
}

# Function URL with auth NONE: since October 2025 a new function URL needs both statements
# (AWS Lambda docs, "Control access to Lambda function URLs").
resource "aws_lambda_permission" "public_invokes_api_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "public_invokes_api_via_url" {
  statement_id             = "FunctionURLInvokeAllowPublicAccess"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "*"
  invoked_via_function_url = true
}
