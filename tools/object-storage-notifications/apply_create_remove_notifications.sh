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
  TOPIC_ARN
  NOTIFICATION_ID
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required environment variable: $var_name" >&2
    exit 1
  fi
done

tmp_config="$(mktemp)"
trap 'rm -f "$tmp_config"' EXIT

cat > "$tmp_config" <<JSON
{
  "TopicConfigurations": [
    {
      "Id": "$NOTIFICATION_ID",
      "TopicArn": "$TOPIC_ARN",
      "Events": [
        "s3:ObjectCreated:*",
        "s3:ObjectRemoved:*"
      ]
    }
  ]
}
JSON

echo "Applying notification configuration to bucket: $BUCKET_NAME"
echo "Endpoint: $S3_ENDPOINT"
echo "Topic ARN: $TOPIC_ARN"

aws --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --endpoint-url "$S3_ENDPOINT" \
  s3api put-bucket-notification-configuration \
  --bucket "$BUCKET_NAME" \
  --notification-configuration "file://$tmp_config"

echo
echo "Current notification configuration:"

aws --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --endpoint-url "$S3_ENDPOINT" \
  s3api get-bucket-notification-configuration \
  --bucket "$BUCKET_NAME"
