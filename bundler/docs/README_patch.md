# Patched OpenAPI generated FastAPI server — why patch, and Docker (uv)

## Why `bundler/make` exists

The standard **python-fastapi** generator in OpenAPI Generator does **not** natively scaffold a server that is pre-configured for the **uv** build tool. By default it emits legacy-oriented project layout (for example `requirements.txt`, `setup.cfg`, or older `setup.py`-style flows), not a uv-first `pyproject.toml` workflow.

You can address that gap in two ways:

1. **Patch the generated tree** after codegen so it matches project conventions (Python version alignment, dependency metadata, uv-friendly `pyproject.toml`, and related files).
2. **Maintain custom Mustache templates** for the generator so emitted files already match those conventions, avoiding post-hoc edits (higher upfront cost, tighter coupling to generator internals).

This repo follows **option (1)**. The **`bundler/make`** helpers implement those post-generation patches. They are invoked from the bundler Make workflow (see `Makefile` / `make/bootstrap.mk` in `bundler/`), not from this directory alone.

### How often patching matters

The patch steps are **static and predictable**: they run the same small scripts against known paths in the generated tree, so outcomes are easy to review in diffs.

You reach for them mainly when **bootstrapping from scratch** (first generation of this server stub) or when **inputs change enough that the scaffold drifts**—for example upgrading the OpenAPI Generator version, refreshing major generated files, or moving the Python / dependency baseline so generated metadata must be realigned with uv.

After that initial alignment, **re-running the full patch pipeline is optional**. Day-to-day work on hand-owned files (for example under `bundler_server/core/`) can stay **fully manual** (via `make` or manual calls); you only need the scripts again when you choose to regenerate and re-normalize the tree.

## Docker: uv-specific files

Alongside patching, this tree includes **uv-oriented** container definitions that are **not** produced by the stock generator output as the primary path:

- `Dockerfile.uv`
- `docker-compose.uv.yaml`

Use them together with the generated `docker-compose.yaml` when you want an image/compose stack aligned with uv (see commands below).

**Local development (uvicorn)** is documented in **[`../quickstart.md`](../quickstart.md)** (step 5) and **[`../getting-started.md`](../getting-started.md#run-the-api-locally-uvicorn)**.

## Running with Docker

To build the image, run from the **OpenAPI output directory** (with **tracked** `openapitools.json`, that is **`bundler/`** when you generate from that folder; the compose files live next to `bundler_server/`):

```bash
docker compose -f docker-compose.yaml -f docker-compose.uv.yaml build
```

To run the server in a container:

```bash
docker compose -f docker-compose.yaml -f docker-compose.uv.yaml up --build
```

Open your browser at `http://localhost:8080/docs/` to see the docs.
