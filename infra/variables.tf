variable "project" {
  type    = string
  default = "dou-cv-analyzer"
}

variable "region" {
  description = "Must be a region where the Bedrock model in var.model_id is available."
  type        = string
  default     = "us-east-1"
}

variable "model_id" {
  description = "Bedrock model ID for vacancy and CV parsing."
  type        = string
  default     = "anthropic.claude-haiku-5-5"
}

variable "parser_effort" {
  description = "output_config.effort for the parser LLM call: low | medium | high."
  type        = string
  default     = "low"
}

variable "cv_effort" {
  description = "output_config.effort for the cv LLM call: low | medium | high."
  type        = string
  default     = "low"
}

variable "cv_delete_after_parse" {
  description = "Delete cv/<uuid>.* after a successful parse. The profile in profiles/ stays."
  type        = bool
  default     = true
}

variable "scrape_schedule" {
  description = "EventBridge schedule for the scraper (UTC)."
  type        = string
  default     = "cron(0 5 * * ? *)"
}

variable "scraper_max_new" {
  description = "Max new vacancies the scraper downloads per run."
  type        = number
  default     = 300
}

variable "parser_reserved_concurrency" {
  description = <<-EOT
    Caps parallel parser invocations (and so parallel Bedrock calls). null = no reservation.
    New accounts often have a total Lambda concurrency of 10, and AWS refuses a reservation that
    leaves fewer than 10 unreserved, so keep null until the account limit is raised.
  EOT
  type        = number
  default     = null
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "budget_limit_usd" {
  type    = number
  default = 20
}

variable "budget_email" {
  description = "Email for budget alerts at 50%, 80% and 100% of budget_limit_usd."
  type        = string
}

variable "embedding_model_id" {
  description = <<-EOT
    Bedrock embedding model ID for the indexer and the matcher; both must use the same one.
    Assumption: cohere.embed-v4:0, taken from the code example on the Bedrock user guide page "Cohere Embed v4"
    (us-east-1). Check the ID and model access in the Bedrock console for var.region before applying.
    An inference profile ID (us.…, eu.…, apac.…, global.…) also works; IAM then grants the profile ARN.
  EOT
  type        = string
  default     = "cohere.embed-v4:0"
}

variable "embedding_dimension" {
  description = "output_dimension of the embedding call. Changing it re-embeds every vacancy on the next index run."
  type        = number
  default     = 1024
  validation {
    condition     = contains([256, 512, 1024, 1536], var.embedding_dimension)
    error_message = "Cohere Embed v4 accepts 256, 512, 1024 or 1536."
  }
}

variable "index_schedule" {
  description = "EventBridge schedule for the indexer (UTC). One hour after var.scrape_schedule, so the day's new vacancies are parsed."
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "web_origin" {
  description = "Origin of the web app, allowed by CORS on the API function URL and on the S3 upload POST."
  type        = string
  default     = "http://localhost:5173"
}

variable "upload_retention_days" {
  description = "Days after which cv/, failed-cv/, matches/, failed-match/, jobs/ and quota/ objects expire."
  type        = number
  default     = 7
}

variable "enable_salary_endpoint" {
  description = <<-EOT
    Create the SageMaker serverless salary endpoint from dist/model.tar.gz (ml/salary/train.py, then ml/salary/package.sh).
    false: no SageMaker resources; the matcher returns a deterministic fake salary block with model_version "fake-disabled".
  EOT
  type        = bool
  default     = false
}

variable "salary_image_uri" {
  description = <<-EOT
    SageMaker scikit-learn 1.9-0 inference image (scikit-learn 1.9.0, Python 3.12, x86). The default is the us-east-1
    URI from the SageMaker Python SDK image config (registry account 683313688378); other regions use other accounts.
  EOT
  type        = string
  default     = "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.9-0-cpu-py3"
}

variable "salary_memory_mb" {
  description = "Serverless endpoint memory."
  type        = number
  default     = 2048
  validation {
    condition     = contains([1024, 2048, 3072, 4096, 5120, 6144], var.salary_memory_mb)
    error_message = "Serverless endpoints accept 1024 to 6144 MB in 1024 MB steps."
  }
}

variable "salary_max_concurrency" {
  description = "Serverless endpoint max concurrent invocations (1-200)."
  type        = number
  default     = 2
}

variable "access_code_hashes" {
  description = <<-EOT
    Who may call the HTTP API: label -> SHA-256 hex of that person's access code. Generate with
    scripts/new_access_code.py <label>. Empty map = every API request is refused.
  EOT
  type        = map(string)
  default     = {}
  sensitive   = true

  validation {
    condition = alltrue([
      for label, digest in var.access_code_hashes : can(regex("^[a-z0-9-]{1,32}$", label)) && can(regex("^[0-9a-f]{64}$", digest))
    ])
    error_message = "Labels must match ^[a-z0-9-]{1,32}$ and values must be 64-character lowercase SHA-256 hex."
  }
}

variable "daily_uploads_per_code" {
  description = "Max CV uploads per access code per UTC day."
  type        = number
  default     = 10
}

variable "daily_uploads_total" {
  description = "Max CV uploads for all codes together per UTC day."
  type        = number
  default     = 40
}

variable "api_reserved_concurrency" {
  description = <<-EOT
    Caps parallel API invocations (the function URL has no throttling of its own). null = no reservation.
    Same account-limit caveat as parser_reserved_concurrency: a new account with a total of 10 cannot reserve any.
  EOT
  type        = number
  default     = null
}

variable "cv_reserved_concurrency" {
  description = "Caps parallel CV parsing (each one is a Claude call). null = no reservation; see api_reserved_concurrency."
  type        = number
  default     = null
}

variable "matcher_reserved_concurrency" {
  description = "Caps parallel matching (embeddings + salary calls). null = no reservation; see api_reserved_concurrency."
  type        = number
  default     = null
}
