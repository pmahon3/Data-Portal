#!/usr/bin/env bash
# Exit on errors, unset variables, and failed pipeline commands.
set -euo pipefail

if ! command -v aws >/dev/null 2>&1; then
  echo "Missing required command: aws. Install AWS CLI first." >&2
  exit 1
fi

required_vars=(
  AWS_PROFILE
  AWS_REGION
  S3_ENDPOINT
  BUCKET_NAME
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required environment variable: $var_name" >&2
    exit 1
  fi
done

aws --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --endpoint-url "$S3_ENDPOINT" \
  s3api get-bucket-notification-configuration \
  --bucket "$BUCKET_NAME"
