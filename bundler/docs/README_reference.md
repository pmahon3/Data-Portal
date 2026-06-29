# Bundler Reference: generation, layout, and regeneration details

This document is the detailed companion to [`README_dev.md`](README_dev.md).
Use [`README_dev.md`](README_dev.md) for the quick start and day-to-day commands.
For a short orientation (mental model, command cheat sheet), see [`../getting-started.md`](../getting-started.md). For commands without Make, see [`../quickstart.md`](../quickstart.md).

## High-level layout

The recommended description of the three-part layout (**`bundler_core/`**, **`openapi.source.yaml`**, **`bundler_server/`** + protected **`core/`**, Makefile and `uv` workflow) and **why** the repo splits them is in **[`README_dev.md` → High-level layout](README_dev.md#high-level-layout)**. This reference focuses on generator defaults, Make variables, and regeneration details below.

## `openapitools.json` and defaults

Regeneration is configured in **`bundler/openapitools.json`** under **`generator-cli.generators.<key>`** (the Makefile uses **`OPENAPI_GENERATOR_KEY`**, default **`bundler-server-fastapi`**). Typical fields for this repo:

| Field | Role in this repo |
|--------|-------------------|
| **`inputSpec`** | OpenAPI document (e.g. **`openapi.source.yaml`**, relative to `bundler/`). |
| **`output`** | Generated server tree. **Tracked** config uses **`#{cwd}/`**: when you run Make from **`bundler/`**, **`#{cwd}`** expands to that directory, so the **`bundler_server`** package is emitted **into `bundler/`** alongside `bundler_core/`. The Makefile normalizes **`#{cwd}`** to **`$(CURDIR)`** for tooling. |
| **`additionalProperties.sourceFolder`** | Prefix for Python sources under **`output`**. **Tracked** value is **`""`**, so packages such as **`bundler_server/`** sit at the top level of the output folder. |
| **`additionalProperties.packageName`** | Import package for generated code (**`bundler_server`** in the tracked config). |
| **`additionalProperties.fastapiImplementationPackage`** | Subpackage for your implementations (**`core`** → `bundler_server.core`). |

**`OPENAPI_TOOLS_CONFIG`** defaults to **`bundler/openapitools.json`** (anchored via **`APP_DIR`** in **`make/vars.mk`**), so **`jq`** can read the config when the shell cwd is not **`bundler/`**; **`#{cwd}`** / **`$(CURDIR)`** behavior for **`output`** remains as in the table row above.

If a key is **missing** from JSON, **`make/vars.mk`** (included by **`Makefile`**) supplies **`jq` `//`** fallbacks: **`sourceFolder`** → **`src`**, **`output`** → **`$(APP_CORE_NAME)`** (sibling-style directory name), **`packageName`** → **`openapi_server`**, **`fastapiImplementationPackage`** → **`impl`**. Prefer setting values explicitly in **`openapitools.json`** so behavior does not depend on those defaults. (Avoid relying on `// ""` in `jq`: an empty string does not trigger `//`; defaults are the literals in that file’s `jq` expression.)

## Where business logic goes

### The generated route layer (`apis/`)

Generated route functions live under:

- `bundler/bundler_server/apis/`

They define FastAPI routes and then delegate to an implementation class. The delegation mechanism is:

- `bundler_server.apis.default_api` imports the package **`bundler_server.core`**
- then it calls the **first discovered** subclass of `BaseDefaultApi`:

> It calls `BaseDefaultApi.subclasses[0]()`.

This is a key design: **generated routers do not contain business logic**.

### The implementation hook (`core/`)

Your endpoint-specific implementation should be written under:

- `bundler/bundler_server/core/`

Typical pattern:

- create exactly **one** concrete subclass of `BaseDefaultApi`
- implement the required methods (e.g., `create_bundle`, `get_health`, etc.)
- inside those methods, call into `bundler_core` (the real service code)

### The stable business layer (`bundler_core/`)

The recommended long-term structure is:

- `bundler_server/core/` contains only minimal HTTP-to-domain “glue”
- the real logic (jobs, storage, domain objects, orchestration) lives in `bundler/bundler_core/`

This makes OpenAPI regeneration low-risk: you mostly update adapter signatures, not core logic.

#### “Sibling layout” and imports: how `bundler_server/core` calls `bundler_core`

It is normal in Python for packages to live as **siblings** on disk (here: `bundler_server/` and `bundler_core/` under `bundler/`).

What matters is not the folder layout but whether the business package is **importable** at runtime.

Then `bundler_server/core` can do normal imports (this repo’s core library is the **`bundler_core`** import package, mapped from the `bundler_core/src/` tree at build time; see **`bundler_core/pyproject.toml`**):

```python
from bundler_core import some_function
```

##### Recommended import strategy

1. Make sure `bundler/bundler_core` is a proper Python package (it has `pyproject.toml` and importable modules).
2. Install it into the environment used to run the server stub.

#### What happens to `bundler_server/core/` on regenerate?

By default, OpenAPI Generator may overwrite files in the output directory.

That means **your `core/` code can be overwritten** unless you protect it.

### Protection mechanism: `.openapi-generator-ignore`

OpenAPI Generator supports an ignore file:

- `bundler/.openapi-generator-ignore` (at the **output root**; with **`output`** `#{cwd}/`, that is the `bundler/` directory)

This repo ignores:

```gitignore
bundler_server/core/**
```

This enables the desired workflow:

- regenerate the server stub as often as needed
- keep your `bundler_server/core/` tree intact
- only update adapter signatures when the spec changes

## Makefile requirements

Shared Make variables (`APP_CORE_DIR` validation, `OPENAPI_*`, `CORE_SOURCE_PATH`, `SKIP_*`) live in **`make/vars.mk`** (included from **`Makefile`**). **`CORE_SOURCE_PATH`** prefers `realpath --relative-to` from the generated server tree back to `APP_CORE_DIR`, and falls back to a sibling-style `../<app_core_name>` when that flag is unavailable (e.g. stock macOS `realpath`); on macOS the Makefile expects **`grealpath`** from **GNU coreutils** for that relative path. For `openapitools.json` keys, **`#{cwd}`**, and **`jq`** field defaults, see **`openapitools.json` and defaults** (above). The `check-tools` target requires **`uv`**, **`uvx`**, **`npx`**, **`jq`**, **`sed`**, **`ed`**, and **`cut`** on `PATH`; targets also invoke **`uv`** / **`uv run`** and **`realpath`** / **`grealpath`** where used.

## Dev dependency copy behavior

Before adding dev requirements in the generated server directory, the Makefile
copies the source dev requirements file from `APP_CORE_DIR` into the resolved
OpenAPI output folder (`OPENAPI_OUTPUT_FOLDER`, derived from `openapitools.json`;
when **`output`** is `#{cwd}/` and you run from `bundler/`, this resolves to **`.`** (the `bundler/` tree)):

```bash
cp "$(APP_CORE_DIR)/requirements-dev.txt" "$(OPENAPI_OUTPUT_FOLDER)/requirements-dev.txt"
```

This happens in the `add-dev-deps` step, then `uv add --dev -r requirements-dev.txt`
is executed with `--directory "$(OPENAPI_OUTPUT_FOLDER)"`.

## Other details

### Other Make commands

- Regenerate server only:
  - `make generate-openapi APP_CORE_DIR=bundler_core`
- Patch generated files/config:
  - `make -f Makefile -f make/bootstrap.mk patch APP_CORE_DIR=bundler_core`
- Sync `uv` environment:
  - `make sync APP_CORE_DIR=bundler_core`

- Run tests (generated server per `openapitools.json`, then `APP_CORE_DIR`):
  - `make test APP_CORE_DIR=bundler_core`
- Export pinned requirements:
  - `make -f Makefile -f make/bootstrap.mk export-pinned APP_CORE_DIR=bundler_core`
- Restore / delete generated server tree (see `clean` recipe; refuses unsafe `OPENAPI_OUTPUT_FOLDER` values):
  - `make clean APP_CORE_DIR=bundler_core`

The underlying `openapi-generator-cli` command shape, when called from PyCharm, is

```bash
  /Applications/PyCharm.app/Contents/jbr/Contents/Home/bin/java \
  -jar ~/Library/Caches/JetBrains/PyCharm2025.3/openapi/codegen/<cache-id>/openapi-generator-cli-7.7.0.jar \
  generate \
  -g python-fastapi \
  -i bundler/openapi.source.yaml \
  -o bundler \
  --additional-properties=
```

Notes:

- **`-g python-fastapi`**: generator target = FastAPI **server stub** (not a client SDK).
- **`-i ...`**: input OpenAPI spec file.
  - In this repo, the hand-owned canonical spec path is `bundler/openapi.source.yaml` (`inputSpec` in `openapitools.json`). The generator may still emit `openapi.yaml` inside the output tree as a copy.
  - You may see alternative paths depending on how PyCharm was configured during generation.
- **`-o ...`**: output directory (what gets overwritten on regeneration).
  - In this repo, **tracked** `openapitools.json` uses **`"output": "#{cwd}/"`**; when the working directory is **`bundler/`**, output is **`bundler/`** itself (the `bundler_server` package appears under that tree). If you use a dedicated subdirectory instead, point **`-o`** there and match **`openapitools.json`**.
- **`--additional-properties=...`**: generator-specific options (this repo sets `packageName`, `fastapiImplementationPackage`, etc. via `openapitools.json`; PyCharm may show a different shape).
- The generated test stub file (`tests/test_default_api.py`) is usually not overwritten if it already exists (generator behavior).

### Important detail: `BaseDefaultApi.subclasses[0]()` (first discovered implementation)

The generated router selects the implementation using:

- the first imported/discovered subclass of `BaseDefaultApi`

Implications:

- If you define **multiple** subclasses across modules, which one ends up at index 0 can become order-dependent.
- To keep behavior deterministic:
  - Prefer creating **exactly one** implementation subclass.
  - If you need multiple implementations (e.g., mocks), make selection explicit (e.g., an environment variable, or a single “dispatcher” impl that delegates internally).
