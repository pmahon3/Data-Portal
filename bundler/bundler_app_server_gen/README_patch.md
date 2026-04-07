# Patched OpenAPI generated FastAPI server — Docker (uv)

Patched Docker setup using `Dockerfile.uv` and `docker-compose.uv.yaml` instead of the default generated `Dockerfile` and `docker-compose.yaml`.

## Running with Docker

To build the image, execute the following from the root directory:

```bash
docker compose -f docker-compose.yaml -f docker-compose.uv.yaml build
```

To run the server in a container:

```bash
docker compose -f docker-compose.yaml -f docker-compose.uv.yaml up --build
```

Open your browser at `http://localhost:8080/docs/` to see the docs.
