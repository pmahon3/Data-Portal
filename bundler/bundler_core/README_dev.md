# Bundler app — developer guide

This document describes how to work on the `bundler_core` Python package inside the INN Data Portal monorepo. The package exposes **library APIs** (health helpers, bundle creation/status/download logic). **HTTP** is implemented separately (in the generated **`bundler_server`** package under `bundler/`), not in this package.

## Prerequisites

- **Python**: 3.10 or later (the project is configured with `requires-python = ">=3.10"`).
- **uv**: Python package/dependency manager used across this repo.
  - Install from the official instructions (`curl`/`pipx`/`brew`, as preferred).
- **Git**: for version control.
- Optional but common on macOS:
  - `brew` for installing system tools.
  - A global Commitizen or Node.js installation is fine; see notes below about multiple Commitizens.

You do **not** need to create or activate virtual environments manually. `uv` manages environments per project.

## Project layout

From the repo root, this package lives at `bundler/bundler_core/`:

```text
bundler/bundler_core/
  __init__.py     # workspace shim: ``__path__`` → ``src/`` + project root (for ``bundler_core.tests``); not shipped in the wheel
  src/
    __init__.py
    api.py
    health.py
    bundles.py
    …
  tests/
    test_health.py
    test_bundles.py
    test_openapi_contract.py
  README.md
  README_dev.md
  pyproject.toml
  requirements.txt
  requirements-dev.txt
```

- `__init__.py` (workspace root): extends ``bundler_core.__path__`` to **both** ``src/`` (library code) and this project directory so subpackage ``bundler_core.tests`` resolves for pytest; re-exports from ``api`` when this tree is on ``sys.path`` (not in the wheel).
- `src/__init__.py`: re-exports the full public surface from `api.py`.
- `src/api.py`: public facade; imports from `health`, `bundles`, and related modules.
- `src/bundles.py`: bundle request model, deterministic keys, in-memory prototype state, archive build.
- `tests/`: pytest suite calling package functions directly (no ASGI server required).

## Installing dependencies

From the repo root:

```bash
cd bundler/bundler_core
uv sync
```

`uv sync` will create and populate a managed environment for the `bundler_core` project using `pyproject.toml` and `uv.lock`.

If the workspace `uv.lock` is out of date, update it from this directory:

```bash
cd bundler/bundler_core
uv lock
uv sync
```

### Requirements text files

In addition to `uv`'s lock file, the project maintains plain-text requirements files for documentation and interoperability:

- `requirements.txt` – **runtime** dependencies
  - Unpinned spec (human-maintained) section listing top-level runtime packages.
  - Regenerate `requirements-pinned.txt` after changes (see below).
- `requirements-dev.txt` – **development** dependencies
  - Includes runtime plus dev-only packages (pytest, httpx, Commitizen, etc.) in an unpinned spec section.

The authoritative source of truth for dependency resolution is still:

- `bundler/bundler_core/pyproject.toml` (declared dependencies and groups), and
- `bundler/bundler_core/uv.lock` (exact resolved versions).

The `requirements*.txt` files are intended for:

- Quickly seeing which runtime vs dev dependencies exist.
- Providing a familiar interface for tools that expect requirements files.
- Allowing another environment to approximate the same setup without using `uv`.

To regenerate pinned runtime requirements (optional when bumping dependencies):

```bash
cd bundler/bundler_core
uv pip compile requirements.txt -o requirements-pinned.txt
```

You can check exported files into version control if you want a text-based, pinned view alongside `uv.lock`.

## Running tests

Tests are written with `pytest`. From `bundler/bundler_core`:

```bash
cd bundler/bundler_core
uv sync
uv run python -m pytest tests
```

Or without syncing first (ephemeral tools; must include **`pytest-cov`** because **`pytest.toml`** enables coverage):

```bash
cd bundler/bundler_core
uv run --with pytest --with pytest-cov python -m pytest tests
```

Coverage and other pytest defaults are configured in **`pytest.toml`**.

Tests use `import bundler_core as api` (and `bundler_core.bundles` where needed) and exercise **functions** in process. They do **not** start an HTTP server and do **not** require anything to listen on a port.

The test suite currently includes:

- `tests/test_health.py`: `health()` return value.
- `tests/test_bundles.py`: create/get/download, dedupe, complete-state idempotency.
- `tests/test_openapi_contract.py`: deterministic bundle fingerprint key behavior.
- `tests/test_state_transitions.py`: worker lifecycle transitions, illegal paths, and `failed → pending` re-queue.
- `tests/test_bundle_zip_paths.py`: archive path layout and ZIP content rules.
- `tests/test_failure_classification.py`: exception → retry policy kind mapping (`transient` / `permanent` / `unknown`).
- `tests/test_bundle_retry.py`: failed-job retry orchestration (re-enqueue, fresh URLs, retry limits).

For the split between domain tests here and HTTP contract tests under `bundler/tests/`, see [`../docs/README_dev.md`](../docs/README_dev.md#testing-boundaries-and-separation-of-concerns).

## Validating the OpenAPI contract

The canonical OpenAPI contract for the Bundler **HTTP** service lives at `bundler/openapi.source.yaml` (see `openapitools.json` `inputSpec`). This library does not serve OpenAPI; validation is for the spec file itself.

To validate that a spec file is syntactically and semantically valid OpenAPI (using the pinned `openapi-spec-validator` dev dependency), run from `bundler/bundler_core`:

```bash
cd bundler/bundler_core
uv run python -m openapi_spec_validator ../openapi.source.yaml
```

Adjust the path if your canonical spec lives elsewhere.

## Commitizen and conventional commits

The `bundler_core` subcomponent uses **Commitizen** (Python version) with **Conventional Commits** to standardize commit messages.

Relevant configuration is in `bundler/bundler_core/pyproject.toml`:

- `[tool.commitizen]` with:
  - `name = "cz_conventional_commits"`
  - `tag_format = "bundler-v$version"`
  - `version = "0.1.0"` and `update_changelog_on_bump = true`

### Making commits for `bundler_core`

Recommended workflow from the repo root:

```bash
# stage changes (example)
git add bundler/bundler_core

# create a conventional commit using bundler_core's Commitizen config
uv run --directory bundler/bundler_core cz
```

This will:

- Use the **Python** Commitizen installed as a dev dependency of `bundler_core`.
- Use the configuration in `bundler/bundler_core/pyproject.toml`.
- Guide you through creating a Conventional Commit message, such as:
  - `feat(bundler): add bundler health endpoint`
  - `fix(bundler): handle invalid bundle request`

### Coexistence with globally installed Commitizen

If the host machine has Commitizen installed globally (for example via `brew install commitizen`), there are effectively **two** Commitizen tools available:

- A global (often Node.js-based) Commitizen, on your shell `PATH`.
- The Python Commitizen installed in `bundler_core`'s uv-managed environment.

To avoid confusion:

- **Always use `uv run --directory bundler/bundler_core cz`** (or equivalent scripts) when committing for this package.
  - This guarantees that the Python Commitizen from the `bundler_core` environment and its config are used.
- Avoid calling bare `cz` / `commitizen` from the shell unless you explicitly intend to use the global tool.

The two installations do not share configuration and do not interfere with each other as long as you invoke the correct one via `uv`.

## Typical development workflow

From the repo root:

```bash
# 1. Sync dependencies (once or when pyproject/uv.lock changes)
cd bundler/bundler_core
uv sync

# 2. Run tests as needed (``pytest.toml`` includes coverage; dev env has ``pytest-cov``)
uv run python -m pytest tests



# 3. Stage and commit changes with Commitizen
git add bundler/bundler_core
uv run --directory bundler/bundler_core cz

# 4. Push as normal
git push
```

To run the generated OpenAPI server, follow [`../quickstart.md`](../quickstart.md) or [`../docs/README_dev.md`](../docs/README_dev.md); this package does not ship `uvicorn` or an ASGI `app` object.
