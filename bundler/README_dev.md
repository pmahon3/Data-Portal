# Bundler Development Quick Start

This document explains how the Bundler service is structured, how the FastAPI server stub is generated from the OpenAPI spec, and where to put business logic so regeneration does **not** wipe your work.

The build uses [`uv`](https://github.com/astral-sh/uv) for Python packaging and dependency resolution and [`npx`]() for running the [`openapi-generator-cli`](https://openapi-generator.tech/docs/installation/#npm); see **Required tools** (and **Installing `uv`**) below once you know what needs to be on your system.

For architecture and deep regeneration details, see `README_reference.md`.

## 1) Run the full workflow

From `bundler/`:

```bash
cd bundler
APP_DIR=bundler_app make all
```

`APP_DIR` is required and should point to your business-logic package directory.

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
  - A Makefile is included for wrappers and patches around regeneration. Generate via `make generate-openapi APP_DIR=<app_dir>` (OpenAPI Generator CLI via `npx -y @openapitools/openapi-generator-cli`, as in **How server generation is invoked** below).
  - Patched to be a `uv` managed package, including matching the `.python-version` from `bundler_app`

### Why split the code this way?

- Generated server code (`bundler_app_server_gen`) is great for keeping the API contract consistent and reproducible from the spec [`openapi.yaml`](openapi.yaml), accomodating for frequent updates. The development is API-driven instead of code-driven.
- Business logic `bundler_app` should be stable, testable, and not at risk during regeneration. The separation ensures that complex business logic does not overlap with api end point logic.
- The generated server stub becomes a thin HTTP adapter that calls into `bundler_app`.

## How server generation is invoked

Server stub generation uses the **OpenAPI Generator CLI** via **npm**, not a Python- or `uv`-only wrapper:

```bash
npx -y @openapitools/openapi-generator-cli
```

That matches what `make generate-openapi` runs (see `bundler/Makefile`). The `@openapitools/openapi-generator-cli` package tracks the upstream tool and exposes the **full CLI** (global properties, `--type-mappings`, additional generator flags, etc.). Lighter options (e.g. invoking the JAR by hand, or Python-only shims) tend to support **fewer** knobs, so this repo standardizes on `npx`.

`make all APP_DIR=<app_dir>` runs:

1. `check-tools`
2. `generate-openapi` (unless skipped)
3. `patch`
4. `sync`
5. `test`

## Skip regeneration

If you already generated code and only want patch/sync/test:

```bash
make all APP_DIR=bundler_app SKIP_GENERATE=1
```

## Required tools

The workflow is driven by **`bundler/Makefile`**, so you need **`make`** (GNU Make is what this repo is written for). On your PATH you should also have:

- **`uv`** (and **`uvx`**, which ships with `uv`) — Python packaging, scripts, and tools the Makefile runs via `uv run` / `uvx` (for example `uvx yq` when patching generated Docker assets).
- **`npx`** (from Node.js / npm) — used to run **`npx -y @openapitools/openapi-generator-cli`** for OpenAPI codegen, as described above.

The Makefile’s `check-tools` target also expects **`sed`** and **`ed`**.

**Windows:** Recipes use **POSIX shell** features and typical Unix CLI tools (`sed`, `ed`, `printf`, shell conditionals, etc.). A plain **cmd.exe** or **PowerShell** session often will **not** run these targets reliably. Prefer **WSL2**, **Git Bash**, **MSYS2**, or another Unix-like environment where `make` invokes a compatible shell, or run the same steps from a Linux/macOS machine or container.

Install **Node.js** so **`npx`** is available. For **`uv`** / **`uvx`**, use **Installing `uv`** next.

### Installing `uv`

If you do not already have [`uv`](https://github.com/astral-sh/uv) installed, follow the [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/#installation-methods) or run:

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
```

`uv` must be on your shell `PATH` (which also makes **`uvx`** available) before running Bundler `make` targets.

## Contribution guide (quick)

- **Changing the HTTP API**: edit `bundler/openapi.yaml`, then run `make generate-openapi APP_DIR=<app_dir>`.
- **Implementing/altering behavior**: edit `bundler/<app_dir>/` (business logic) and `<app_name>_server_gen/.../impl/` (adapter glue).
- **Do not edit generated routers/models** under `<app_name>_server_gen/src/openapi_server/apis` and `.../models`—those will be overwritten.
