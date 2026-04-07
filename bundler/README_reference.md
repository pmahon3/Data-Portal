# Bundler Reference: generation, layout, and regeneration details

This document is the detailed companion to `README_dev.md`.
Use `README_dev.md` for the quick start and day-to-day commands.

## High-level layout

The Bundler code is intentionally split into **three** parts:

- `bundler/bundler_app/`
  - **Non-generated** (human-owned) “domain/business logic” package.
  - This is where you should spend most of your time: orchestration, job logic, persistence, integrations, etc.
  - `uv`  managed package (natively)

- `bundler/openapi.yaml`
  - **Source of truth** for the HTTP API contract (OpenAPI 3.x).
  - Changing the API starts here.

- `bundler/<app_name>_server_gen/` (for example `bundler/bundler_app_server_gen/`)
  - **Generated** FastAPI server stub produced by OpenAPI Generator (`openapi-generator-cli` using `python-fastapi`).
  - Contains:
    - generated routers (`openapi_server/apis/*`)
    - generated Pydantic models (`openapi_server/models/*`)
    - a hook point for implementations (`openapi_server/impl/*`)
    - Protect that implementation folder from overwrite via:
    - `.openapi-generator-ignore` with `src/openapi_server/impl/**`
  - `bundler/Makefile` and `bundler/scripts/patch_*.py`
    - OpenAPI generator templates default to Python 3.7-oriented artifacts (for example Docker base image).
    - `bundler/scripts/` and Makefile patch steps adjust generated files to project conventions (including Python version alignment).
    - A Makefile is incudled for various wrappers and patches related to the regenertaion. Generate via `make generate-openapi APP_DIR=<app_dir>` (uses OpenAPI Generator CLI under the hood).
    - Patched to be a `uv` managed package, including matching the `.python-version` from `bundler_app`

### Why split the code this way?

- Generated server code (`bundler_app_server_gen`) is great for keeping the API contract consistent and reproducible from the spec [`openapi.yaml`](openapi.yaml), accomodating for frequent updates. The development is API-driven instead of code-driven.
- Business logic `bundler_app` should be stable, testable, and not at risk during regeneration. The separation ensures that complex business logic does not overlap with api end point logic.
- The generated server stub becomes a thin HTTP adapter that calls into `bundler_app`.

## How server generation is invoked

OpenAPI Generator (`openapi-generator-cli -g python-fastapi ...`) produces a scaffold that is effectively a ready-to-run Python 3.7-oriented template by default (for example the generated `Dockerfile` starts from `python:3.7` unless patched).

In this repo, `bundler/scripts/` is responsible for patching that generated output to the project conventions (notably Python version alignment and related config updates in `setup.cfg`, `pyproject.toml`, and dependency files).

The Makefile-driven workflow depends on `uv`/`uvx` for dependency management, syncing, and OpenAPI generation command invocation.

You can still run generation via the PyCharm OpenAPI plugin if desired, but you must run the patch flow afterward.

```bash
make all APP_DIR=bundler_app SKIP_GENERATE=1
```

## What gets regenerated vs what you own

In `bundler/<app_name>_server_gen/src/openapi_server/`:

- **Generated** (safe to overwrite on regen):
  - `apis/` (route functions, request/response wiring)
  - `models/` (request/response schemas)
  - `main.py`, configuration helpers, etc. (depends on template)

- **Your code (should be preserved)**:
  - `impl/` (implementation hook points that the generated routers call)
  - and/or code in `bundler/bundler_app/` (recommended long-term home for business logic)

## Where business logic goes

### The generated route layer (`apis/`)

Generated route functions live under:

- `bundler/<app_name>_server_gen/src/openapi_server/apis/`

They define FastAPI routes and then delegate to an implementation class. The delegation mechanism is:

- `openapi_server.apis.default_api` imports modules under `openapi_server.impl`
- then it calls the **first discovered** subclass of `BaseDefaultApi`:

> It calls `BaseDefaultApi.subclasses[0]()`.

This is a key design: **generated routers do not contain business logic**.

### The implementation hook (`impl/`)

Your endpoint-specific implementation should be written under:

- `bundler/<app_name>_server_gen/src/openapi_server/impl/`

Typical pattern:

- create exactly **one** concrete subclass of `BaseDefaultApi`
- implement the required methods (e.g., `create_bundle`, `get_health`, etc.)
- inside those methods, call into `bundler_app` (the real service code)

### The stable business layer (`bundler_app/`)

The recommended long-term structure is:

- `impl/` contains only minimal HTTP-to-domain “glue”
- the real logic (jobs, storage, domain objects, orchestration) lives in `bundler/bundler_app/`

This makes OpenAPI regeneration low-risk: you mostly update adapter signatures, not core logic.

#### “Sibling layout” and imports: how `impl/` calls `bundler_app`

It’s normal in Python for projects/packages to be “siblings” on disk (e.g., `bundler_app_server` and `bundler_app`).

What matters is not the folder layout but whether the business package is **importable** at runtime.

Then `impl/` can do normal imports:

```python
from bundler.app.some_module import some_function
```

##### Recommended import strategy

1. Make sure `bundler/bundler_app` is a proper Python package (it has `pyproject.toml` and importable modules).
2. Install it into the environment used to run the server stub.

#### What happens to `impl/` on regenerate?

By default, OpenAPI Generator may overwrite files in the output directory.

That means **your `impl/` code can be overwritten** unless you protect it.

### Protection mechanism: `.openapi-generator-ignore`

OpenAPI Generator supports an ignore file:

- `bundler/<app_name>_server_gen/.openapi-generator-ignore`

Add ignore patterns so your implementation code is not touched. For example:

```gitignore
# Keep human-written implementation code
src/openapi_server/impl/**
```

This enables the desired workflow:

- regenerate the server stub as often as needed
- keep your `impl/` intact
- only update your impl signatures when the spec changes

## Makefile requirements

The target `check-tools` validates required tools before running the main targets. Current required tools are `uv`, `uvx` in addition to common shell commands (e.g. `realpath`).

## Dev dependency copy behavior

Before adding dev requirements in the generated server directory, the Makefile
copies the source dev requirements file from `APP_DIR`:

```bash
cp "$(APP_DIR)/requirements-dev.txt" "$(APP_DIR_GEN)/requirements-dev.txt"
```

This happens in the `patch-dev-deps` step, then `uv add --dev -r requirements-dev.txt`
is executed inside `$(APP_DIR_GEN)`.

## Other details

### Other Make commands

- Regenerate server only:
  - `make generate-openapi APP_DIR=bundler_app`
- Patch generated files/config:
  - `make patch APP_DIR=bundler_app`
- Sync `uv` environment:
  - `make sync APP_DIR=bundler_app`

- Run tests:
  - `make test APP_DIR=bundler_app`
- Export pinned requirements:
  - `make export-pinned APP_DIR=bundler_app`
- Show clean command (dry-run):
  - `make clean APP_DIR=bundler_app`

The underlying `openapi-generator-cli` command shape, when called from PyCharm`, is

```bash
  /Applications/PyCharm.app/Contents/jbr/Contents/Home/bin/java \
  -jar ~/Library/Caches/JetBrains/PyCharm2025.3/openapi/codegen/<cache-id>/openapi-generator-cli-7.7.0.jar \
  generate \
  -g python-fastapi \
  -i bundler/openapi.yaml \
  -o bundler/<app_name>_server_gen \
  --additional-properties=
```

Notes:

- **`-g python-fastapi`**: generator target = FastAPI **server stub** (not a client SDK).
- **`-i ...`**: input OpenAPI spec file.
  - In this repo, the canonical spec path is `bundler/openapi.yaml`.
  - You may see alternative paths depending on how PyCharm was configured during generation.
- **`-o ...`**: output directory (what gets overwritten on regeneration).
  - In this repo, the generated server stub lives in `bundler/<app_name>_server_gen/`.
- **`--additional-properties=...`**: generator-specific options (left blank in the current Makefile call).
- The generated test stub file (`tests/test_default_api.py`) is usually not overwritten if it already exists (generator behavior).

### Important detail: `BaseDefaultApi.subclasses[0]()` (first discovered implementation)

The generated router selects the implementation using:

- the first imported/discovered subclass of `BaseDefaultApi`

Implications:

- If you define **multiple** subclasses across modules, which one ends up at index 0 can become order-dependent.
- To keep behavior deterministic:
  - Prefer creating **exactly one** implementation subclass.
  - If you need multiple implementations (e.g., mocks), make selection explicit (e.g., an environment variable, or a single “dispatcher” impl that delegates internally).
