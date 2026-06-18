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
