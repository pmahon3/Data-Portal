# API versioning: where to change things (Bundler)

This document is for developers who can build and run the project but are **not** deep in OpenAPI Generator. It answers: **when we add or change a versioned API surface (e.g. a new `/v3`), what files do I touch?**

## Mental model

- **One OpenAPI document** is the contract: `bundler/openapi.source.yaml` (OpenAPI Generator may also write `bundler/openapi.yaml` or similar under the configured **output** directory; with **`"output": "#{cwd}/"`** and Make run from `bundler/`, that is under **`bundler/`**. Regenerate from the same source via `openapitools.json` `inputSpec`).
- **Path prefixes** carry the version:
  - `/v1/...` — legacy; may be marked `deprecated` in the spec when you want to retire it.
  - `/v2/...` — explicit revision.
  - Unversioned paths (`/health`, `/bundles`, …) — **always mean “current”** (today: same behavior as v2). When you ship a newer revision, unversioned routes should follow **latest** behavior; versioned routes stay stable until removed from the spec.
- **`info.version`** (e.g. `0.2.0`) is the **document revision**, not the same thing as `/v1` vs `/v2`. Bump it when the published contract meaningfully changes.

You do **not** need to master every `openapi-generator-cli` flag to do version work—you need to know **which files are generated** vs **which you own**.

## Source of truth

| Role | File / area |
|------|----------------|
| **Contract** (paths, methods, status codes, schemas, `deprecated`, `operationId`) | `bundler/openapi.source.yaml` |
| **HTTP adapter implementation** (map HTTP ↔ domain, branch by version if needed) | `bundler/bundler_server/core/default_api_impl.py` |
| **Domain / business logic** (bundles, idempotency, zip, etc.) | `bundler_core/` (import package **`bundler_core`**, from the `src/` tree via setuptools `package-dir`; see `bundler_core/pyproject.toml`) |

## Generated vs hand-maintained (server package)

Under `bundler/bundler_server/` (generated package; see `openapitools.json` for **`output`**, **`packageName`**, **`fastapiImplementationPackage`**):

| Area | Typical treatment |
|------|-------------------|
| `bundler_server/apis/default_api.py` | **Generated** by OpenAPI Generator. Defines routes and delegates to `BaseDefaultApi.subclasses[0]()`. After regeneration you may need a **small manual fix** (see below). |
| `bundler_server/apis/default_api_base.py` | **Generated** — abstract methods per `operationId`. |
| `bundler_server/main.py` | **Generated** — `FastAPI(title=..., version=...)` from `info`. |
| `bundler_server/models/*.py` | **Generated** from `components/schemas`. |
| `bundler_server/core/default_api_impl.py` | **Hand-written** — your `DefaultApiImpl(BaseDefaultApi)` implementation. **This is the main place for version-specific behavior** without re-running the generator for every logic tweak. |

If you add a **new** version prefix (e.g. `/v3`) or new operations, you will **regenerate** so `default_api.py` / `default_api_base.py` / models stay aligned with the spec—then re-apply any documented post-regeneration steps.

## Adding or changing a version: checklist

### 1. Change the contract (`bundler/openapi.source.yaml`)

- Add or adjust paths under `/vN/...`.
- Give each operation a **unique** `operationId` (e.g. `createBundleV3`). Duplicate `operationId` values across paths break or confuse code generation.
- If the JSON shape changes, add or update `components/schemas` and reference them from the right path.
- Mark old operations `deprecated: true` when you want that reflected in docs (e.g. Swagger UI).

### 2. Regenerate the Python FastAPI stub (when needed)

Regeneration updates `default_api.py`, `default_api_base.py`, models, and `main.py` to match the spec. Follow the repo’s usual **generate → patch → sync** flow (see [`README_dev.md`](README_dev.md)); generated files live under **`bundler/bundler_server/`** with the **tracked** `openapitools.json` settings.

You do **not** need to memorize generator internals; treat it as “compile the contract into Python stubs.”

### 3. Post-regeneration fix for `202` responses (this repo)

The **python-fastapi** generator may omit `status_code=202` on route decorators even when the OpenAPI success response is `202`. FastAPI then defaults to **200** for successful JSON responses.

After each regeneration of `default_api.py`, confirm that **POST** `.../bundles` and **GET** `.../bundles/{bundleId}` (for each version prefix you support) include `status_code=202` on the `@router.post` / `@router.get` decorators where the contract says `202`. If they are missing, add them (match the pattern already used in the file).

### 4. Implement behavior in `default_api_impl.py`

- The generated base class will expose methods such as `create_bundle_v2`, `create_bundle_v3`, `create_bundle` (unversioned “current”), etc.
- Depending on your needs, **you choose** how to structure differences:
  - **Separate** private helpers per version (e.g. `_create_bundle_v2` vs `_create_bundle_v3`), or
  - **One** helper with a `version` / `api_version` parameter when most logic is shared, or
  - **Inline** differences in the public methods if the split is small.
- Point **unversioned** methods (`create_bundle`, `get_bundle`, …) at **“latest”** behavior (e.g. delegate to the same code as the highest supported version you want to expose as current).

Push **reusable** rules into `bundler_core` (`src/bundles.py`, etc.) when the behavior is not HTTP-specific.

### 5. Tests

- Bundle contract tests live under **`bundler/tests/`**: `bundler/tests/common.py` (shared paths/payloads), `bundler/tests/test_v1.py` (`/v1/...`), and `bundler/tests/test_v2.py` (`/v2/...` and unversioned “current” paths via `@pytest.mark.parametrize`).
- Extend or add cases there when paths or behavior change.
- If you monkeypatch domain calls, patch symbols imported in `default_api_impl.py` (e.g. `bundler_create_bundle_job`), not generated `apis/` code.

## Minimal “new developer” summary

1. **Contract** → `bundler/openapi.source.yaml`
2. **Regenerate** stubs when paths/schemas/operationIds change
3. **Re-apply** `status_code=202` on bundle create/status routes in `default_api.py` if the generator drops them
4. **Behavior** → `default_api_impl.py` (+ `bundler_core` for core logic)

That is the full loop for introducing a new **v-version** without becoming an OpenAPI Generator expert.
