# Object Storage Notifications Tools

Small helper tools for managing Arbutus/Ceph object storage bucket notifications.

These scripts are intended for operational setup and testing. They configure a bucket notification topic to emit both object creation and object removal events, then provide a simple way to test those events and parse saved webhook payloads.

## Prerequisites

Install the AWS CLI and make sure it is available as `aws`:

```bash
aws --version
```

AWS credentials must already be configured through an AWS profile, GitLab CI/CD variables, or another credential provider supported by the AWS CLI.

## Configuration

Provide configuration through environment variables. In GitLab CI/CD, define these as CI/CD variables. For local runs, export them in your shell.

Required variables:

```bash
AWS_PROFILE=arbutus-rrp-rmcintos
AWS_REGION=us-east-1
S3_ENDPOINT=https://object-arbutus.alliancecan.ca
BUCKET_NAME=inn-test
TOPIC_ARN=arn:aws:sns:default:account-id:topic-name
NOTIFICATION_ID=upload-and-delete-events
```

Do not put AWS access keys, secret keys, passwords, or webhook secrets in this directory.

For a local shell, you can use `config.example.env` as a reference and export the values manually.

## Webhook Authentication

The backend webhook route is:

```text
POST /api/object-storage/events
```

When `OBJECT_STORAGE_WEBHOOK_SECRET` is configured, the receiver accepts either:

```http
X-Webhook-Secret: <secret>
```

or a URL query parameter:

```text
https://<portal-host>/api/object-storage/events?webhook_secret=<URL_ENCODED_SECRET>
```

The query parameter form is intended for object storage notification services
that cannot send custom HTTP headers. Prefer HTTPS and a high-entropy secret.
URLs may be logged by proxies or application infrastructure, so avoid reusing
this secret anywhere else.

## Create Or Update Ceph Notification Topic

Some Ceph/RGW deployments do not support topic creation through the standard
`aws sns create-topic` command. If `aws sns list-topics` or `aws sns
create-topic` returns a generic `Unknown` error, create the topic with a signed
Ceph API request instead.

First, prepare the webhook URL and load the AWS credentials from the configured
profile:

```bash
export WEBHOOK_SECRET="<same value as OBJECT_STORAGE_WEBHOOK_SECRET>"
export WEBHOOK_URL="https://<portal-host>/api/object-storage/events?webhook_secret=${WEBHOOK_SECRET}"

export AWS_ACCESS_KEY_ID="$(aws configure get aws_access_key_id --profile "$AWS_PROFILE")"
export AWS_SECRET_ACCESS_KEY="$(aws configure get aws_secret_access_key --profile "$AWS_PROFILE")"
```

If `WEBHOOK_SECRET` contains characters such as `+`, `/`, `=`, `&`, `?`, `%`,
or spaces, URL-encode it before building `WEBHOOK_URL`. A hex secret generated
with `openssl rand -hex 32` does not need additional encoding.

Create or update the topic:

```bash
curl -i -X POST "$S3_ENDPOINT/" \
  --aws-sigv4 "aws:amz:${AWS_REGION}:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "Action=CreateTopic" \
  --data-urlencode "Name=${NOTIFICATION_ID}" \
  --data-urlencode "Attributes.entry.1.key=push-endpoint" \
  --data-urlencode "Attributes.entry.1.value=${WEBHOOK_URL}" \
  --data-urlencode "Attributes.entry.2.key=verify-ssl" \
  --data-urlencode "Attributes.entry.2.value=true" \
  --data-urlencode "Attributes.entry.3.key=persistent" \
  --data-urlencode "Attributes.entry.3.value=true"
```

Copy the `TopicArn` value from the XML response and export it before applying
the bucket notification configuration:

```bash
export TOPIC_ARN="<TopicArn returned by CreateTopic>"
```

## Read Current Notification Configuration

```bash
./get_notification_config.sh
```

## Apply Create And Remove Notifications

```bash
./apply_create_remove_notifications.sh
```

This applies both events to the configured topic:

```text
s3:ObjectCreated:*
s3:ObjectRemoved:*
```

Important: `put-bucket-notification-configuration` replaces the whole bucket notification configuration. If a bucket already has other notification rules that must stay active, add them to the generated configuration before applying changes.

## Test Create And Remove Events

```bash
./test_create_remove_events.sh
```

The script uploads a timestamped object under `notification-tests/`, confirms it exists, deletes it, then lists the prefix again. Check the webhook receiver to confirm both create and remove events arrived.

## Parse A Saved Ceph Event Payload

```bash
python3 parse_ceph_event.py sample-event.json
```

The parser reads `Records[]` and prints normalized JSON lines with:

```text
event_id
event_time
event_type
action
bucket
object_key
size
etag
```

Events are classified by prefix:

```text
ObjectCreated:* -> created
ObjectRemoved:* -> removed
anything else -> unknown
```

## Rename And Move Behavior

S3-compatible storage does not have a true rename or move operation. Rename and move are normally implemented as copy/create plus delete/remove:

```text
ObjectCreated event for the new key
ObjectRemoved event for the old key
```
