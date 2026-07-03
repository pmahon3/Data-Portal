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

The Nomad job exposes the main Spring Boot settings as environment variables:

```text
BUNDLER_ARCHIVE_STRATEGY=current|batch|streaming|hybrid
BUNDLER_WORKER_THREADS
BUNDLER_WORKER_QUEUE_CAPACITY
BUNDLER_DOWNLOAD_THREADS
BUNDLER_DOWNLOAD_PARALLELISM
BUNDLER_DOWNLOAD_CONNECT_TIMEOUT_SECONDS
BUNDLER_DOWNLOAD_REQUEST_TIMEOUT_SECONDS
BUNDLER_DOWNLOAD_MAX_ATTEMPTS
BUNDLER_DOWNLOAD_RETRY_DELAY_MILLIS
```

The default strategy in the Nomad job is:

```text
hybrid
```
