# Quickstart

Run the AMS Data Portal locally with Docker.

**Last Updated:** 2026-08-27

## Prerequisites

- Git
- Docker with Compose v2

## Start the portal

From the repository root:

```bash
cp local/.env.example local/.env
cd local
docker compose up -d --build
```

The values in `.env.example` are for local development only. Change them before using the portal in a shared environment.

> For development, run the frontend, backend, or both locally for hot reload while keeping supporting services in Docker. See the [local development guide](../local/README.md).

Check that the services are ready:

```bash
docker compose ps
```

## Configure MinIO

Add this entry to your hosts file so bundle download links using the `minio` hostname work in your browser:

```text
127.0.0.1 minio
```

The hosts file is `/etc/hosts` on macOS/Linux and `C:\Windows\System32\drivers\etc\hosts` on Windows. Administrator access is required to edit it.

> This applies only when adding an S3-compatible storage instance, such as MinIO, running in the local Docker environment. Docker containers can resolve the service hostname minio, but your browser cannot unless it is mapped to 127.0.0.1 in your hosts file. Remote S3 services and AWS S3 are not affected.

Then:

1. Open the [MinIO Console](http://minio:9001).
2. Sign in with `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from `local/.env`.
3. Select **Create Bucket** and create a bucket named `bundles`.

## Services

| Service | Local address |
|---------|---------------|
| Frontend | [http://localhost:3000](http://localhost:3000) |
| Backend | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Keycloak | [http://localhost:8080](http://localhost:8080) |
| MinIO | [Console](http://minio:9001), [API](http://minio:9000) |
| Mongo Express | [http://localhost:8081](http://localhost:8081) |
| Java Bundler | [http://localhost:8888](http://localhost:8888) |

## Stop the portal

```bash
docker compose down
```

## Troubleshooting

- Check service state with `docker compose ps`.
- View logs with `docker compose logs -f <service>`.
- If bundling fails, confirm that the `bundles` bucket exists in MinIO.
- If you cannot resolve minio hostname, confirm that it resolves to localhost in your hosts file
- If database tables are missing, initialize PostgreSQL with the [backend schema](../backend/core/db/postgres/scripts/schema.sql) and [bundler schema](../java-bundler/src/main/resources/schema.sql).
- To reset all local data, run `docker compose down -v`, then start the portal again.
- If projects are missing or unavailable, confirm that the projects group claim is configured. See the [projects documentation](../docs/diagrams/README.md).
- If the frontend entrypoint cannot be found or executed, confirm that the entrypoint file uses LF line endings.

## More guides

- [Local development](../local/README.md)
- [Backend API reference](./api-reference.md)
- [Java Bundler](../java-bundler/README.md)
- [Python Bundler quickstart](../bundler/quickstart.md)
