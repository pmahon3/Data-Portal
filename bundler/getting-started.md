# Getting started with the Bundler service (human-maintained)

The file [`README.md`](README.md) in this directory is **generated** by OpenAPI Generator. It is **not** the canonical developer guide.

## Start here (what to read)

| Your goal | Read this | Stop when… |
|-----------|-----------|------------|
| **Just run it** | [`quickstart.md`](quickstart.md) or [`docs/README_dev.md` → Run the full workflow](docs/README_dev.md#1-run-the-full-workflow) | Commands work locally |
| **Daily dev** (where to edit, tests) | [`docs/README_dev.md`](docs/README_dev.md) — layout, contribution, testing | You know where API vs domain vs adapter code lives |
| **First-week orientation** (generator, tree, config) | **This file** through [`openapitools.json`](#this-repository-openapitoolsjson), then skim README_dev for tools/tests | Placeholders map to `bundler_server/` and `bundler_core/` |
| **Bundle behavior** (states, retries, HTTP flow) | [`docs/state-machine.md`](docs/state-machine.md), [`docs/bundle-request-flow.md`](docs/bundle-request-flow.md) | No layout detour needed |
| **Regen / Make debugging** | [`openapitools.json`](#this-repository-openapitoolsjson) here, then [`docs/README_reference.md`](docs/README_reference.md) | Edge case resolved |
| **Docker / uv patch** | [`docs/README_patch.md`](docs/README_patch.md) | — |

> **New to the repo?** Follow **First-week orientation** (this file). **Returning dev?** Jump to **Daily dev** in README_dev.

**Customization:** Where files land, the Python import package name, and the implementation subpackage are all driven by **OpenAPI Generator** options. In this repo they are set in **[`openapitools.json`](openapitools.json)** (keys under `generator-cli.generators.<generator-key>`, for example `bundler-server-fastapi`). The CLI is usually invoked via `npx @openapitools/openapi-generator-cli` (see the [`Makefile`](Makefile)). Changing `output`, `inputSpec`, `additionalProperties`, and related fields **re-shapes** paths and imports. The sections below describe **typical defaults** first, then **this repository’s** explicit choices.

In this guide, the generator is assumed to use create a skeleton for a `FastAPI` python server.

---

## Doc map (pick your depth)

| Document | Purpose |
|----------|---------|
| **[`quickstart.md`](quickstart.md)** | **Simple path without _Make_** — copy/paste `npx` / `uv` commands |
| **This file** | Orientation, mental model, **typical tree (with inlined ownership/regeneration notes)**, commands, **`make all`** expansion, **run API locally (uvicorn)** |
| [`docs/README_dev.md`](docs/README_dev.md) | Quick start, required tools, contribution pointers |
| [`docs/README_patch.md`](docs/README_patch.md) | Why `uv` patching exists; **Docker** (`docker-compose.yaml` + `docker-compose.uv.yaml`, `Dockerfile.uv`) |
| [`docs/README_reference.md`](docs/README_reference.md) | **`jq`** fallbacks, Make variables, `.openapi-generator-ignore`, regen edge cases (after [`openapitools.json`](#this-repository-openapitoolsjson) intro here) |
| [`docs/README_API_VERSIONING.md`](docs/README_API_VERSIONING.md) | Changing `/v1`, `/v2`, unversioned routes |
| [`docs/state-machine.md`](docs/state-machine.md) | Bundle job states, transitions, dedupe, retry policy |
| [`docs/bundle-request-flow.md`](docs/bundle-request-flow.md) | End-to-end HTTP and worker sequence diagrams |

---

## Mental model (one diagram)

Use placeholders that match OpenAPI Generator **`additionalProperties`** (see next section). **`{output}`** is the generator output directory from **`openapitools.json`**.

```text
openapi.source.yaml  ──►  OpenAPI Generator  ──►  {output}/{packageName}/  (when sourceFolder is empty)
                   or ──►  {output}/{sourceFolder}/{packageName}/  (when sourceFolder is set, often "src")
                                                          │
                                                          ▼
                                               …/{packageName}/{fastapiImplementationPackage}/  (often hand-owned if ignored)
                                                          │
                                                          ▼
                                               bundler_core/  (this repo: domain / business logic; sibling package)
```

**In this repository:** `packageName` is **`bundler_server`**, `fastapiImplementationPackage` is **`core`**, `sourceFolder` is empty, and `output` is **`#{cwd}/`**, so with `make` run from `bundler/` the diagram collapses to `bundler_server/` and `bundler_server/core/` under `bundler/`, plus sibling **`bundler_core/`**.

For what each tree owns and why the repo splits contract, generated HTTP, and domain logic, see [`docs/README_dev.md` → High-level layout](docs/README_dev.md#high-level-layout). Bundle job runtime behavior is in [`docs/state-machine.md`](docs/state-machine.md) and [`docs/bundle-request-flow.md`](docs/bundle-request-flow.md).

---

## Configuration: typical defaults and this repository

### A. Typical defaults (generator + this Makefile)

OpenAPI Generator’s **`python-fastapi`** generator reads **`additionalProperties`** from your config. Upstream templates often assume **`src`**, **`openapi_server`**, and **`impl`** when keys are omitted; this Makefile’s **[`make/vars.mk`](make/vars.mk)** supplies its own fallbacks via **`jq`**. Prefer setting values explicitly in **`openapitools.json`** — see [**This repository (`openapitools.json`)**](#this-repository-openapitoolsjson) below for this repo’s choices. For **`jq`** fallback literals, **`OPENAPI_*`** Make variables, and edge cases, see [`docs/README_reference.md` → `openapitools.json` and defaults](docs/README_reference.md#openapitoolsjson-and-defaults).

### Typical generated tree (schematic)

Paths use the same placeholders as above. **`{output}`** is the generator output directory. **`{sourceFolder}`** may be empty. **Ownership, regeneration, and where to work** are inlined on each line as `# …` comments (not shell syntax—just annotations in this diagram).

```text
openapi.source.yaml                    # YOU OWN — contract; edit here, then regenerate. Not under {output}.

{output}/                                # GENERATOR ROOT — everything below is relative to this unless noted
  {sourceFolder}/                        # optional; e.g. "src". When empty, skip this whole segment (this repo: empty)
    {packageName}/
      apis/                              # GENERATED — overwritten on regen; route shells (e.g. BaseDefaultApi)
        default_api_base.py              # GENERATED `BaseDefaultApi` class — a FastAPI skeleton with routing and typing
      models/                            # GENERATED — overwritten; Pydantic models
      {fastapiImplementationPackage}/    # YOU OWN when paths are in {output}/.openapi-generator-ignore — skipped on regen
        default_api_impl.py              # implements/ inherits from generated bases; wrapper logic calling business logic lives here (this repo: see bundler_server/core/** in [.openapi-generator-ignore](.openapi-generator-ignore))
      main.py                            # GENERATED — overwritten; ASGI app factory
      tests/                             # often GENERATED under the package — regen-sensitive (this repo: bundler_server/tests/)
        test_default_api.py              # typical starter; use as a skeleton for specific test_*.py
      …
  openapi.yaml                           # GENERATED if emitted — overwritten (copy/derived spec; version-dependent)
  README.md                              # often GENERATED at output root — overwritten; add to ignore only if you want a stable human README (generator then stops updating it)
  pyproject.toml                         # GENERATED / Makefile-patched — see [README_patch.md](docs/README_patch.md)
  Dockerfile                             # GENERATED (typical)
  docker-compose.yaml                    # GENERATED (typical)
  …
  bundler_core/                          # YOU OWN — not emitted as this tree path by the server generator; domain + [bundler_core/tests/](bundler_core/tests/)
  tests/                                 # YOU OWN in this repo — HTTP/contract tests ([bundler/tests/](tests/)) at {output} root, sibling of {packageName}/ (distinct from {packageName}/tests/ above)
```

> **Tip:** **Empty `sourceFolder`:** the generator places **`{packageName}/`** directly under **`{output}/`** (no `src/` in between). **This repo** uses that layout.

> **Editing generated files:** See [`docs/README_dev.md` → Contribution guide (quick)](docs/README_dev.md#contribution-guide-quick). For route/version quirks after regen, see [`docs/README_API_VERSIONING.md`](docs/README_API_VERSIONING.md).

## This repository (`openapitools.json`)

**Your first look at [`openapitools.json`](openapitools.json)** — these values collapse the mental-model placeholders above into concrete paths. For **`jq`** fallbacks and Make variable wiring, see [`docs/README_reference.md` → `openapitools.json` and defaults](docs/README_reference.md#openapitoolsjson-and-defaults).

This repo sets them explicitly (generator key **`bundler-server-fastapi`**). The tracked file is shaped like this (abbreviated; the real file also sets `"$schema"`, `"spaces"`, and the full `generator-cli` wrapper):

```json
{
  "generator-cli": {
    "version": "7.21.0",
    "generators": {
      "bundler-server-fastapi": {
        "generatorName": "python-fastapi",
        "inputSpec": "openapi.source.yaml",
        "output": "#{cwd}/",
        "additionalProperties": {
          "sourceFolder": "",
          "packageName": "bundler_server",
          "fastapiImplementationPackage": "core",
          "packageVersion": "1.0.0",
          "serverPort": "8080"
        },
        "typeMappings": {
          "file": "bytes",
          "binary": "bytes"
        }
      }
    }
  }
}
```

| Property | Value here | Effect |
|----------|------------|--------|
| `output` | `#{cwd}/` | With `make` from `bundler/`, generated files land **in `bundler/`** next to `bundler_core/`. |
| `additionalProperties.sourceFolder` | `""` (empty) | No `src/` segment; **`bundler_server/`** sits directly under **`bundler/`**. |
| `additionalProperties.packageName` | `bundler_server` | Import package for generated modules. |
| `additionalProperties.fastapiImplementationPackage` | `core` | Hand-written adapters under **`bundler_server/core/`** (e.g. `default_api_impl.py`). |

---

## Patching and `uv` in one paragraph

OpenAPI Generator’s **`python-fastapi`** target emits a **pip/Poetry-friendly** scaffold. This repository standardizes on **`uv`** for speed and reproducible installs, so small **patch scripts** under `bundler/make/` normalize generated metadata. That is a **migration/bootstrap** concern, not something you repeat for every feature change.

**Escape hatch:** If your organization mandates plain `pip`, you can still use the generated `requirements.txt` patterns; `uv` can export requirements-style artifacts for compatibility (see [`docs/README_patch.md`](docs/README_patch.md) and [`make/bootstrap.mk`](make/bootstrap.mk)).

---

## Commands without reading the Makefile

Run these from the **`bundler/`** directory unless your team documents otherwise.

| Command | When to use it |
|---------|----------------|
| `make all APP_CORE_DIR=bundler_core` | Full loop: check tools, generate server (unless skipped), wire `bundler_core` into the server project, `uv sync`, run **both** test suites (server tree + core). |
| `make all APP_CORE_DIR=bundler_core SKIP_GENERATE=1` | You already have generated code; run dependency wiring + sync + tests only. |
| `make generate-openapi APP_CORE_DIR=bundler_core` | Regenerate the FastAPI stub from `openapi.source.yaml` only. |
| `make sync APP_CORE_DIR=bundler_core` | Refresh the `uv` environment after dependency changes. |
| `make test APP_CORE_DIR=bundler_core` | Run pytest for the server **`tests/`** tree under `OPENAPI_OUTPUT_FOLDER`, then for **`bundler_core`**. |
| `make clean APP_CORE_DIR=bundler_core` | Remove generated files listed by the generator manifest and restore tracked stub state (see Makefile; refuses unsafe output paths). |
| Run API locally | **`uv run uvicorn …`** after **`make sync …`** — see [Run the API locally (uvicorn)](#run-the-api-locally-uvicorn) (last section). |
| Run API in Docker (uv-oriented Compose) | From **`bundler/`**: `docker compose -f docker-compose.yaml -f docker-compose.uv.yaml build`, then `docker compose -f docker-compose.yaml -f docker-compose.uv.yaml up --build` — then **`http://localhost:8080/docs/`**. Combines the generated **`docker-compose.yaml`** with repo **`Dockerfile.uv`** and **`docker-compose.uv.yaml`**; see [Docker: uv-specific files](docs/README_patch.md#docker-uv-specific-files) and [Running with Docker](docs/README_patch.md#running-with-docker) in [`docs/README_patch.md`](docs/README_patch.md). |

**Optional / less frequent** (patch generator output for `uv`, Python version alignment, etc.):

```bash
make -f Makefile -f make/bootstrap.mk patch APP_CORE_DIR=bundler_core
```

See [`docs/README_patch.md`](docs/README_patch.md) for why this exists and how often you need it.

> **Tip:** Windows note. The Make recipes assume a **Unix-like** environment. Prefer WSL2, Git Bash, MSYS2, or a Linux container if you are on Windows. See [`docs/README_dev.md`](docs/README_dev.md).

---

## Regeneration vs AI (non-prescriptive)

- **Regeneration** answers: “Does my **checked-in contract** compile to a **known** Python HTTP layer?” It is repeatable and diff-friendly.
- **AI** can help author **`openapi.source.yaml`** or explore implementations in **`bundler_core`**, but it does not remove **review** obligations—same as for generator output or any other contribution.

Pick either or both; the repo does not require AI for builds.

---

## Required tools (short list)

You need **GNU Make**, **uv** (includes **uvx**), **npx** (Node.js), and several POSIX utilities (**jq**, **sed**, **ed**, **cut**). On macOS, **grealpath** (GNU coreutils) may be required for some path logic. Details and install links are in [`docs/README_dev.md`](docs/README_dev.md).

---

## What `make all` runs (expanded, no patching)

For a **short** description of the same stages (without shell-level detail), see the numbered list under **`make all`** in [`docs/README_dev.md`](docs/README_dev.md).

This section mirrors **[`Makefile`](Makefile)** only: target **`all`** depends on **`build`**, **`sync`**, and **`test`**, where **`build`** = **`generate-openapi`** + **`add-deps`** + **`add-dev-deps`**. It does **not** include optional **`make/bootstrap.mk`** patching or `export-pinned`.

For day-to-day work, prefer **`make all APP_CORE_DIR=bundler_core`** (see [Commands without reading the Makefile](#commands-without-reading-the-makefile)) unless you are debugging an individual step.

The snippets below use the same **placeholders** Make resolves from [`openapitools.json`](openapitools.json) and [`make/vars.mk`](make/vars.mk) (run `make -n test APP_CORE_DIR=bundler_core` from `bundler/` to print resolved values). **`OPENAPI_GENERATOR_KEY`** defaults to **`bundler-server-fastapi`**.

**0. Tool check** (same idea as target `check-tools`): ensure `uv`, `uvx`, `npx`, `jq`, `sed`, `ed`, and `cut` are on your `PATH`.

**1. Generate** (`generate-openapi`):

```bash
# From bundler/ (so openapitools.json paths match).
npx -y @openapitools/openapi-generator-cli version
npx -y @openapitools/openapi-generator-cli generate --generator-key "${OPENAPI_GENERATOR_KEY:-bundler-server-fastapi}"
```

**2. Wire runtime dependency** (`add-deps`):

> **Note:** In `uv` commands, **`--directory <path>`** (or **`-C <path>`**) means: run the rest of the command **as if** you had **`cd <path>`** first, then invoked the natural `uv …` form in that project root (here, the generated server / **`OPENAPI_OUTPUT_FOLDER`** tree). The same applies to the other **`uv add`**, **`uv sync`**, and **`uv run`** lines that the Makefile runs with **`--directory "$(OPENAPI_OUTPUT_FOLDER)"`** or **`--directory "$(APP_CORE_DIR)"`**.
>
> **Note:** For readability, **steps 2–5** and the **concrete example** below show `uv` **without** **`--directory …`**, using **`cd`** into **`${OPENAPI_OUTPUT_FOLDER}`** or **`${APP_CORE_DIR}`** instead. The [`Makefile`](Makefile) always passes **`--directory`**, so **`make all`** and related targets stay correct **no matter which directory you run `make` from**—you do not have to `cd` first when using Make.
>
> **Note:** **`--no-sync` (on `uv add`):** **`uv add … --no-sync`** updates project metadata (for example dependency entries / lock bookkeeping) **without** fully resolving or downloading the environment in that same invocation—it **defers** resolve and install until you run **`uv sync`**. The Makefile uses **`--no-sync`** on the **`add-deps`** and **`add-dev-deps`** **`uv add`** steps so several dependency edits can be queued, then **`sync`** performs one explicit resolve/download pass.

```bash
cd "${OPENAPI_OUTPUT_FOLDER}"
uv add "${CORE_SOURCE_PATH}" --no-sync
uv add --no-sync -r requirements.txt
# Hand-owned ops deps (not OpenAPI-generated); see requirements-observability.txt
uv add --no-sync -r requirements-observability.txt
```

**3. Wire dev dependencies** (`add-dev-deps`):

```bash
# Still in OPENAPI_OUTPUT_FOLDER
cp "${APP_CORE_DIR}/requirements-dev.txt" requirements-dev.txt
uv add --dev --no-sync -r requirements-dev.txt
```

**4. Sync and dev-edit dependency** (`sync`):

```bash
# Still in OPENAPI_OUTPUT_FOLDER
uv sync
uv add --dev ${CORE_SOURCE_PATH}
```

**5. Tests** (`test`): this Makefile runs **pytest** via **`uv run`**, not a `uv test` subcommand.

> **Note:** **`--with` (on `uv run`):** **`uv run --with <package>`** makes that package available **only for that command** (together with the project environment), **without** adding it as a new runtime dependency in **`pyproject.toml`**. **`--with pytest`** and **`--with pytest-cov`** match the [`Makefile`](Makefile) so **`make test`** can run **`pytest`** and coverage even when those are only dev dependencies.

```bash
# Still in OPENAPI_OUTPUT_FOLDER
uv run --with pytest --with pytest-cov \
  python -m pytest tests --cov="${OPENAPI_IMPL_COV_PATH}"

cd "${APP_CORE_DIR}"
uv run --with pytest --with pytest-cov \
  python -m pytest tests
```

### This repository (typical values)

With **`APP_CORE_DIR=bundler_core`**, current [`openapitools.json`](openapitools.json), and `make` run from **`bundler/`**, `make` resolves roughly:

| Placeholder | Example value |
|-------------|----------------|
| `OPENAPI_OUTPUT_FOLDER` | `.` |
| `CORE_SOURCE_PATH` | `./bundler_core` |
| `OPENAPI_IMPL_COV_PATH` | `/bundler_server/core` (leading slash comes from an empty `sourceFolder` in the Makefile’s `OPENAPI_IMPL_COV_PATH` join) |

So the **`uv`** steps match (same **`cd`** simplification as above; with **`OPENAPI_OUTPUT_FOLDER`** = **`.`**, stay in **`bundler/`** after step 1):

```bash
# After codegen (step 1); current directory: bundler/ (same as OPENAPI_OUTPUT_FOLDER when it is ".")
uv add "./bundler_core" --no-sync
uv add --no-sync -r requirements.txt
uv add --no-sync -r requirements-observability.txt
cp bundler_core/requirements-dev.txt requirements-dev.txt
uv add --dev --no-sync -r requirements-dev.txt
uv sync
uv add --dev ./bundler_core
# Same --with meaning as in step 5 above
uv run --with pytest --with pytest-cov \
  python -m pytest tests --cov="/bundler_server/core"
cd bundler_core
uv run --with pytest --with pytest-cov \
  python -m pytest tests
```

**Note:** Some `uv` releases expose **`uv test`** or similar; **`make test` here still uses `uv run … python -m pytest`** so flags like **`--cov`** stay explicit and match CI/local behavior.

---

## Run the API locally (uvicorn)

Work from the **OpenAPI output directory** (with **tracked** [`openapitools.json`](openapitools.json), that is **`bundler/`** when you generate from that folder). Install dependencies first (**`make sync APP_CORE_DIR=bundler_core`** or equivalent after **`make build`** / **`make all`**).

```bash
cd bundler   # if not already there
uv run uvicorn bundler_server.main:app --reload --host 0.0.0.0 --port 8080
# or
uv run uvicorn bundler_server.observability.app:app --reload --host 0.0.0.0 --port 8080

```

- **ASGI app:** **`bundler_server.observability.app:app`** (hand-owned shell over generated [`bundler_server/main.py`](bundler_server/main.py); adds `/metrics` and `/actuator/*`).
- **Port `8080`:** matches **`serverPort`** in [`openapitools.json`](openapitools.json) and the Docker docs in [`docs/README_patch.md`](docs/README_patch.md).
- **Docs UI:** open **`http://localhost:8080/docs/`** (Swagger UI).

For the same API in containers, use **Docker Compose** with the uv overlay — see the **Run API in Docker** row in [Commands without reading the Makefile](#commands-without-reading-the-makefile) and [`docs/README_patch.md`](docs/README_patch.md).
