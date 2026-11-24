output "bucket" {
  value = aws_s3_bucket.data.bucket
}

output "scraper_function" {
  value = aws_lambda_function.scraper.function_name
}

output "parser_function" {
  value = aws_lambda_function.parser.function_name
}

output "cv_function" {
  value = aws_lambda_function.cv.function_name
}

output "api_url" {
  description = "Base URL of the HTTP API (VITE_API_URL for the web app)."
  value       = aws_lambda_function_url.api.function_url
}

output "indexer_function" {
  value = aws_lambda_function.indexer.function_name
}

output "matcher_function" {
  value = aws_lambda_function.matcher.function_name
}

output "api_function" {
  value = aws_lambda_function.api.function_name
}

output "salary_endpoint" {
  value = var.enable_salary_endpoint ? aws_sagemaker_endpoint.salary[0].name : null
}
