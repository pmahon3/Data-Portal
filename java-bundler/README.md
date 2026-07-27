# Java Bundler

Spring Boot service for creating ZIP archives from presigned source URLs.

## Build Locally

From the repository root:

```bash
docker build -f java-bundler/Dockerfile -t java-bundler:local java-bundler
```

Run locally:

```bash
docker run --rm -p 8888:8888 java-bundler:local
```

Health check:

```bash
curl http://localhost:8888/actuator/health
```

## Build And Push Production Image

Set the image tag you want to publish:

```bash
export IMAGE=registry.rcg.sfu.ca/rcg/inn-data-portal/java-bundler:latest
```

Build and push:

```bash
docker build -f java-bundler/Dockerfile -t "$IMAGE" java-bundler
docker push "$IMAGE"
```

For a release-specific tag:

```bash
export IMAGE=registry.rcg.sfu.ca/rcg/inn-data-portal/java-bundler:<tag>
docker build -f java-bundler/Dockerfile -t "$IMAGE" java-bundler
docker push "$IMAGE"
```

## Deploy With Nomad

Nomad job:

```text
deployment/java-bundler/java-bundler.nomad
```


## Backend Configuration

To route backend bundle requests to the Java bundler in production, set:

```bash
BUNDLER_PROVIDER=java
JAVA_BUNDLER_URL='http://{{- range nomadService "java-bundler" }}{{ .Address }}:{{ .Port }}{{- end }}'
```

To route back to the Python bundler:

```bash
BUNDLER_PROVIDER=python
PYTHON_BUNDLER_URL='http://{{- range nomadService "bundler-staging" }}{{ .Address }}:{{ .Port }}{{- end }}'
```

## Runtime Settings

The Java bundler reads Spring Boot settings from `application.properties`.
In Nomad or Docker, set these as environment variables.

### Archive And Worker Settings

```text
BUNDLER_ARCHIVE_TEMP_DIR
```

Directory where local ZIP files and temporary staging files are written.
For local development this can be your Desktop; in production this should be a durable/shared path if multiple instances need access to local artifacts.

```text
BUNDLER_ARCHIVE_STRATEGY
```

Archive implementation to use:

```text
current | batch | streaming | hybrid
```

The default strategy is:

```text
hybrid
```

Worker pool settings:

```text
BUNDLER_WORKER_THREADS
BUNDLER_WORKER_QUEUE_CAPACITY
```

Download concurrency and retry settings:

```text
BUNDLER_DOWNLOAD_THREADS
BUNDLER_DOWNLOAD_PARALLELISM
BUNDLER_DOWNLOAD_CONNECT_TIMEOUT_SECONDS
BUNDLER_DOWNLOAD_REQUEST_TIMEOUT_SECONDS
BUNDLER_DOWNLOAD_MAX_ATTEMPTS
BUNDLER_DOWNLOAD_RETRY_DELAY_MILLIS
```

### Job Metadata Database

The Java bundler stores job metadata in PostgreSQL. ZIP bytes are not stored in the database.

```text
BUNDLER_JOBS_POSTGRES_JDBC_URL
BUNDLER_JOBS_POSTGRES_USERNAME
BUNDLER_JOBS_POSTGRES_PASSWORD
BUNDLER_JOBS_SCHEMA_MODE
```

Use `BUNDLER_JOBS_SCHEMA_MODE=none` when `schema.sql` owns table creation.

Instance and claim settings:

```text
BUNDLER_INSTANCE_ID
BUNDLER_JOB_LOCK_DURATION_SECONDS
BUNDLER_JOB_CLAIM_SCAN_ENABLED
BUNDLER_JOB_CLAIM_SCAN_DELAY_MILLIS
BUNDLER_JOB_CLAIM_SCAN_BATCH_SIZE
```

`BUNDLER_INSTANCE_ID` identifies which Java bundler instance owns a processing job.
The lock is refreshed while a job is actively processing, so long-running bundles are not reclaimed by another instance.

### Object Storage For Completed Bundles

Completed ZIP files are uploaded to S3-compatible object storage.
The database stores only the object key, and download requests generate a fresh presigned URL.

```text
BUNDLER_OUTPUT_OBJECT_STORAGE_ENDPOINT
BUNDLER_OUTPUT_OBJECT_STORAGE_REGION
BUNDLER_OUTPUT_OBJECT_STORAGE_BUCKET
BUNDLER_OUTPUT_OBJECT_STORAGE_KEY_PREFIX
BUNDLER_OUTPUT_OBJECT_STORAGE_ACCESS_KEY_ID
BUNDLER_OUTPUT_OBJECT_STORAGE_SECRET_ACCESS_KEY
BUNDLER_OUTPUT_OBJECT_STORAGE_PATH_STYLE_ACCESS
BUNDLER_OUTPUT_OBJECT_STORAGE_PRESIGNED_URL_EXPIRATION_SECONDS
```

`BUNDLER_OUTPUT_OBJECT_STORAGE_BUCKET` is the bucket where completed ZIP bundles are uploaded.

`BUNDLER_OUTPUT_OBJECT_STORAGE_KEY_PREFIX` is the folder/prefix inside that bucket, for example `bundles`.

`BUNDLER_OUTPUT_OBJECT_STORAGE_PATH_STYLE_ACCESS=true` creates URLs like:

```text
http://host/bucket/key
```

Set it to `false` for virtual-host style S3 URLs when your object-storage endpoint supports that.

The object-storage endpoint must be reachable by the browser if frontend users are expected to download directly from the returned presigned URL.

### Retention Settings

Terminal jobs and their artifacts are cleaned up by the retention scheduler.

```text
BUNDLER_JOB_RETENTION_ENABLED
BUNDLER_JOB_COMPLETED_RETENTION_HOURS
BUNDLER_JOB_RETENTION_INITIAL_DELAY_MILLIS
BUNDLER_JOB_RETENTION_SCAN_DELAY_MILLIS
BUNDLER_JOB_RETENTION_BATCH_SIZE
```

Retention deletes:

```text
local ZIP file
uploaded object-storage ZIP
bundle job metadata
bundle job file rows
```

### Backend Bundle Settings

The backend generates presigned source-file URLs and sends them to Java bundler.
For large bundles, source-file URLs need to live long enough for Java bundler to download late files.

```text
BUNDLE_SOURCE_URL_EXPIRATION_SECONDS
```

Default:

```text
7200
```

## Bundle Workflow

1. The frontend sends selected file and folder IDs to the backend.

2. The backend resolves the selected files from the file-tree database, checks read permissions, and creates presigned source-file URLs.

3. The backend creates a Java bundler job by calling `POST /bundles`.

4. Java bundler stores the job metadata and file list in PostgreSQL with status `pending`.

5. A Java bundler worker claims the job by setting status `processing`, `locked_by`, and `lock_expires_at`.

6. The archive strategy downloads the source files from their presigned URLs and writes them into a local ZIP file.

7. Java bundler uploads the completed ZIP to the configured object-storage bucket.

8. Java bundler marks the job `complete` and stores the uploaded object key in PostgreSQL.

9. The frontend polls job status while the bundle is being prepared.

10. When the job is complete, the frontend asks the backend for the bundle download URL.

11. The backend asks Java bundler for a fresh presigned object-storage URL.

12. The browser downloads the ZIP directly from object storage.

13. Later, retention cleanup removes old local ZIPs, uploaded ZIP objects, and completed job metadata.

Useful timing fields are stored on each completed job:

```text
archive_duration_millis
upload_duration_millis
total_duration_millis
archive_started_at
archive_completed_at
upload_started_at
upload_completed_at
```
