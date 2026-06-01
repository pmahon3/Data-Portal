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

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
object_key="notification-tests/create-remove-test-$timestamp.txt"
tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

printf 'create remove event test %s\n' "$timestamp" > "$tmp_file"

echo "Uploading test object: s3://$BUCKET_NAME/$object_key"
aws --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --endpoint-url "$S3_ENDPOINT" \
  s3 cp "$tmp_file" "s3://$BUCKET_NAME/$object_key"

echo
echo "Confirming uploaded object exists:"
aws --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --endpoint-url "$S3_ENDPOINT" \
  s3 ls "s3://$BUCKET_NAME/$object_key"

echo
echo "Deleting test object: s3://$BUCKET_NAME/$object_key"
aws --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --endpoint-url "$S3_ENDPOINT" \
  s3 rm "s3://$BUCKET_NAME/$object_key"

echo
echo "Listing notification-tests/ prefix after delete:"
aws --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --endpoint-url "$S3_ENDPOINT" \
  s3 ls "s3://$BUCKET_NAME/notification-tests/" || true

echo
echo "Check the webhook receiver for ObjectCreated and ObjectRemoved events for:"
echo "$object_key"
