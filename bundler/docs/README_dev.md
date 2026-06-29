# Bundler Development Quick Start

> **Note:** [`README.md`](README.md) in this directory is **generated** by OpenAPI Generator (stock template). It is not contributor-maintained onboarding. For the command-only simple path, read **[`../quickstart.md`](../quickstart.md)**; for orientation, read **[`../getting-started.md`](../getting-started.md)** or **this file**.

This document explains how the Bundler service is structured, how the FastAPI server stub is generated from the OpenAPI spec, and where to put business logic so regeneration does **not** wipe your work.

The build uses [`uv`](https://github.com/astral-sh/uv) for Python packaging and dependency resolution and [`npx`](https://docs.npmjs.com/cli/v8/commands/npx) for running the [`openapi-generator-cli`](https://openapi-generator.tech/docs/installation/#npm); see **Required tools** (and **Installing `uv`**) below once you know what needs to be on your system.

## Doc map

| Document | Purpose |
|----------|---------|
| [`../quickstart.md`](../quickstart.md) | **Happy path without Make** — copy/paste `npx` / `uv` commands |
| [`../getting-started.md`](../getting-started.md) | Mental model, generated vs owned, command cheat sheet |
| **This file** | Quick start, tools, test layout |
| [`README_patch.md`](README_patch.md) | Why patching exists (`uv` vs stock generator) |
| [`README_reference.md`](README_reference.md) | Regeneration details, Make variables |
| [`README_API_VERSIONING.md`](README_API_VERSIONING.md) | `/v1`, `/v2`, unversioned routes |
| [`README_regeneration_file.md`](README_regeneration_file.md) | Regeneration churn, `.openapi-generator-ignore`, un-ignore workflow |

For architecture and deep regeneration details, see [`README_reference.md`](README_reference.md).

## 1) Run the full workflow

**Prefer explicit commands?** See **[`../quickstart.md`](../quickstart.md)** — same simple path without reading the Makefile.

From `bundler/` with Make:

```bash
cd bundler
APP_CORE_DIR=bundler_core make all
```

`APP_CORE_DIR` is required and should point to your business-logic package directory (path relative to `bundler/`, e.g. `bundler_core`).

## High-level layout

The Bundler code is intentionally split into **three** parts (see [`openapitools.json`](openapitools.json) for the exact generator settings):

- `bundler/bundler_core/`
  - **Non-generated** (human-owned) “domain/business logic” package.
  - This is where you should spend most of your time: orchestration, job logic, persistence, integrations, etc.
  - `uv` managed package (natively).

- `bundler/openapi.source.yaml`
  - **Source of truth** for the HTTP API contract (OpenAPI 3.x).
  - Changing the API starts here.

- `bundler/bundler_server/` (generated Python package, emitted **into `bundler/`** when `output` is `#{cwd}/` and you run Make from `bundler/`)
  - **Generated** FastAPI server stub produced by OpenAPI Generator (`openapi-generator-cli`, `python-fastapi`).
  - Contains:
    - generated routers (`bundler_server/apis/*`)
    - generated Pydantic models (`bundler_server/models/*`)
    - **hand-written** HTTP adapter implementations under `bundler_server/core/*` (protected from overwrite via [`.openapi-generator-ignore`](.openapi-generator-ignore))
  - The repo [`Makefile`](Makefile) and [`make/`](make/) scripts wrap codegen, `uv` wiring, and optional patches. Generate via `make generate-openapi APP_CORE_DIR=bundler_core` (OpenAPI Generator CLI via `npx -y @openapitools/openapi-generator-cli`, as in **How server generation is invoked** below).
  - After codegen, the tree is adjusted for a `uv`-managed workflow (see [`README_patch.md`](README_patch.md)).

### Why split the code this way?

- Generated server code under **`bundler_server`** keeps the HTTP layer consistent and reproducible from the spec [`openapi.source.yaml`](openapi.source.yaml), including when the contract changes often. Development stays API-driven instead of only code-driven.
- Business logic in **`bundler_core`** stays stable, testable, and not at risk during regeneration. The separation keeps complex domain rules out of generated routers.
- The generated server stub stays a thin HTTP adapter: **`bundler_server/core`** maps requests and responses; **`bundler_core`** owns behavior.

For **`openapitools.json`** field semantics, **`vars.mk`** fallbacks, and deeper regeneration mechanics, see [`README_reference.md`](README_reference.md#openapitoolsjson-and-defaults).

## How server generation is invoked

Server stub generation uses the **OpenAPI Generator CLI** via **npm**, not a Python- or `uv`-only wrapper:

```bash
npx -y @openapitools/openapi-generator-cli
```

That matches what `make generate-openapi` runs (see `bundler/Makefile`). The `@openapitools/openapi-generator-cli` package tracks the upstream tool and exposes the **full CLI** (global properties, `--type-mappings`, additional generator flags, etc.). Lighter options (e.g. invoking the JAR by hand, or Python-only shims) tend to support **fewer** knobs, so this repo standardizes on `npx`.

`make all APP_CORE_DIR=<path-to-core-package>` runs (from `bundler/`, e.g. `APP_CORE_DIR=bundler_core`):

1. `check-tools` (via `generate-openapi`)
2. `generate-openapi` (unless `SKIP_GENERATE=1`)
3. `build` (`add-deps` and `add-dev-deps` after codegen)
4. `sync`
5. `test`

For the optional **patch** to enable `uv` support flow (Mustache/uv normalization scripts), use `make -f Makefile -f make/bootstrap.mk patch APP_CORE_DIR=...` (see `make/bootstrap.mk`).

## Skip regeneration

If you already generated code and only want patch/sync/test:

```bash
make all APP_CORE_DIR=bundler_core SKIP_GENERATE=1
```

## Required tools

The workflow is driven by **`bundler/Makefile`** (it includes **`make/vars.mk`** for shared variables; see **`README_reference.md`** → *Makefile requirements* / *openapitools.json and defaults*). You need **`make`** (GNU Make is what this repo is written for). On your PATH you should also have:

- **`uv`** (and **`uvx`**, which ships with `uv`) — Python packaging, scripts, and tools the Makefile runs via `uv run` / `uvx` (for example `uvx yq` when patching generated Docker assets).
- **`npx`** (from Node.js / npm) — used to run **`npx -y @openapitools/openapi-generator-cli`** for OpenAPI codegen, as described above.

The Makefile’s `check-tools` target (run via `generate-openapi` and other targets that depend on it) expects **`uv`**, **`uvx`**, **`npx`**, **`jq`**, **`sed`**, **`ed`**, and **`cut`** on your `PATH`.

**Windows:** Recipes use **POSIX shell** features and typical Unix CLI tools (`sed`, `ed`, `printf`, shell conditionals, etc.). A plain **cmd.exe** or **PowerShell** session often will **not** run these targets reliably. Prefer **WSL2**, **Git Bash**, **MSYS2**, or another Unix-like environment where `make` invokes a compatible shell, or run the same steps from a Linux/macOS machine or container.

Install **Node.js** so **`npx`** is available. For **`uv`** / **`uvx`**, see **Installing `uv`** next.

### Installing `uv`

If you do not already have [`uv`](https://github.com/astral-sh/uv) installed, follow the [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/#installation-methods) or run:

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
```

`uv` must be on your shell `PATH` (which also makes **`uvx`** available) before running Bundler `make` targets.

## Contribution guide (quick)

- **Changing the HTTP API**: edit `bundler/openapi.source.yaml`, then run `make generate-openapi APP_CORE_DIR=bundler_core` (or your core path).
- **Implementing/altering behavior**: edit `bundler/bundler_core/` (domain) and `bundler/bundler_server/core/` (HTTP adapter glue).
- **Do not edit generated routers/models** under `bundler_server/apis/` and `bundler_server/models/` by hand—those will be overwritten on regeneration.

## Testing boundaries and separation of concerns

Use the two test suites for different questions:

- `bundler/bundler_core/tests/` (core/domain tests)
  - Validates business behavior directly: state transitions, dedupe, archive path rules, and bundle workflow internals.
  - Uses stubs/monkeypatches at the domain layer to keep tests deterministic and independent from external HTTP.
  - `tests/test_bundles.py` boundary: verifies public bundle domain API behavior
    (create/get/download responses, dedupe, and not-found handling), while explicit
    lifecycle transition semantics live in `tests/test_state_transitions.py` and
    archive-path/content rules live in `tests/test_bundle_zip_paths.py`.

- `bundler/tests/` (HTTP contract tests)
  - Validates API contract behavior of the generated FastAPI adapter: endpoint status codes, payload validation, and HTTP error mapping.
  - Focuses on protocol-level expectations (`202/409/404/422/...`) rather than deep archive-building semantics.

Practical rule of thumb:

- If the question is **"Does bundling logic do the right thing?"** → add/update tests in `bundler_core/tests`.
- If the question is **"Does the HTTP endpoint return the right status/body?"** → add/update tests in `bundler/tests`.

From `bundler/`, **`make test APP_CORE_DIR=bundler_core`** runs the server test suite under `OPENAPI_OUTPUT_FOLDER` (from `openapitools.json`), then **`bundler_core`**, each with a single pytest invocation (with **`pytest-cov`**). Server coverage uses **`--cov`** from the Makefile (`OPENAPI_IMPL_COV_PATH`); server pytest defaults (e.g. ignoring the generated stub test) live in **`pytest.toml`**. Core coverage and other pytest defaults come from **`bundler_core/pytest.toml`**.
