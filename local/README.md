# Local Development

**Last Updated:** 2026-08-27

Run the frontend and backend locally for hot reload, while keeping their supporting services in Docker.

## Prerequisites

- Docker with Compose v2
- Python 3.12+
- Node.js 20+

## 1. Start supporting services

From the repository root, create `local/.env` if needed and start the dependencies:

```bash
cp local/.env.example local/.env
cd local
docker compose up -d --build keycloak minio mongodb mongo-express postgres java-bundler
```

Configure the `minio` hostname and `bundles` bucket as described in the [quickstart](../docs/quickstart.md#configure-minio).

## 2. Run the backend locally

In `backend/.env`, use host-accessible service addresses and local paths:

```dotenv
AMS_RELOAD=true
ENFORCER_MODEL=./core/services/policies/casbin/model.conf
ENFORCER_POLICY=./core/services/policies/casbin/policy.csv
USER_POLICIES=./data/policies
INSTANCE_CONFIGS=./data/configs
DATABASE_URL=postgresql+asyncpg://objtree_app:1q2w3e4r@localhost:5432/inn_objtree
MONGO_HOST=localhost
MONGO_PORT=27017
JAVA_BUNDLER_URL=http://localhost:8888
```

Also copy the `SECRET_ENCRYPTION_KEY` value from `local/.env` into `backend/.env`.

Create a virtual environment and install dependencies:

```bash
cd backend
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Or on macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Load `backend/.env` on Windows PowerShell:

```powershell
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
    }
}
python server.py
```

Or on macOS/Linux:

```bash
set -a
source .env
set +a
python server.py
```

The backend reloads when Python files change. API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## 3. Run the frontend locally

In another terminal:

```bash
cd frontend
npm ci
npm start
```

The frontend reloads when source files change and is available at [http://localhost:3000](http://localhost:3000). Its development proxy sends API requests to `http://localhost:8000`.

## Run only one service locally

- Frontend only: from `local/`, start the Docker backend with `docker compose up -d --build backend`, then run the frontend locally.
- Backend only: start the supporting services from step 1, then run the backend locally.

Do not start a Docker service and its local version at the same time; they use the same ports.

## Stop

Stop the local frontend and backend with `Ctrl+C`, then stop the Docker services:

```bash
cd local
docker compose down
```

## Troubleshooting

- Check dependencies with `docker compose ps` and `docker compose logs -f <service>` from `local/`.
- If the backend cannot reach a database, confirm its PostgreSQL, MongoDB, and bundler hosts are set to `localhost`.
- If authentication fails, confirm Keycloak is healthy and available at [http://localhost:8080](http://localhost:8080).
- If port `3000` or `8000` is already in use, stop the corresponding Docker container or local process.
