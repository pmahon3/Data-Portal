# OpenAPI regeneration: what changes, what stays, and how to refresh

This document complements **`README_patch.md`** (why **`bundler/make`** exists and how Docker/uv patching works). Here the focus is **codegen churn**, **`.openapi-generator-ignore`**, and **when to touch which files**.

Regeneration is driven from the **`bundler/`** tree: **`openapitools.json`**, **`openapi.source.yaml`**, and **`make generate-openapi`** / **`make build`** (see the parent **`Makefile`**). The generator output directory is whatever **`output`** resolves to for your generator key (often under **`bundler/`**, e.g. this server stub directory).

---

## Three buckets of files in the generated server tree

### 1. Generator-owned (will be overwritten)

Anything **not** matched by **`.openapi-generator-ignore`** is overwritten on the next **`openapi-generator-cli generate`**: Pydantic models, routers, generated API stubs, **`main.py`**, stock tests the template emits, etc.

**When they change:** you edit **`bundler/openapi.source.yaml`** (or change generator version / **`openapitools.json`** / generator options), then run **`make generate-openapi`** (or **`make build`**). Expect **large diffs**; do not keep long-lived business logic in these files unless you accept re-merging on every regen or you widen ignore rules.

### 2. Hand-owned (not overwritten by codegen)

**`.openapi-generator-ignore`** lists paths the generator must **not** touch. In this repo the implementation island is:

```text
bundler_server/core/**
bundler_server/observability/**
```

So everything under **`bundler/bundler_server/core/`** (for example **`default_api_impl.py`**) and **`bundler/bundler_server/observability/`** (metrics/actuator shell) stays under your control across regenerations. Ops Python deps live in hand-owned **`requirements-observability.txt`** (wired by **`make add-deps`**), not in generated **`requirements.txt`**.

**When they change:** when **you** edit them, or when you deliberately re-import generated stubs (workflow below).

### 3. Generated but normalized (patch scripts, not ignore)

After codegen, **`make/bootstrap.mk`** (with **`Makefile`**) runs patch scripts under **`bundler/make/`** to align **`pyproject.toml`**, **`requirements.txt`**, **`setup.cfg`**, and optionally Docker metadata with **uv**-oriented conventions. See **`README_patch.md`**.

**When they change:** after a regen that touches those scaffold files, re-run the relevant **`patch-*`** targets (or full **`patch`**) so transforms apply again.

---

## “Un-ignore → regenerate → re-ignore” workflow

Use this when a path is **ignored** (often under **`bundler_server/core/`**) but you **want the generator to emit a fresh version once** from the updated OpenAPI document—for example to pick up new imports or signature changes from a template—then return to hand-maintaining the file.

1. **Commit or stash** current work (especially **`bundler_server/core/`** and any other edits you rely on).
2. **Edit `.openapi-generator-ignore`**: remove or comment out the pattern that hides the file, or add a **`!`** negation for a single path (same semantics as **`.gitignore`**).
3. **Regenerate** from **`bundler/`** (e.g. **`make generate-openapi`** with **`SKIP_GENERATE=0`**).
4. **Merge** your previous hand edits onto the new generated content (or refactor so only a thin layer is regenerated and behavior stays in **`bundler_core`**).
5. **Restore the ignore rule** so the next **`generate`** does not wipe your edits again.
6. Re-run **tests** and, if needed, **`make -f Makefile -f make/bootstrap.mk patch-…`** so patched scaffold files stay consistent.

**Why re-ignore matters:** without it, the next generation pass **overwrites** that file and you lose stable hand-owned code.

**Alternative:** keep files **always** generator-owned and confine customization to **`bundler_server/core/`** and **`bundler_core`** only—best when spec churn is high.

---

## What usually changes in which scenario

| Trigger | Typical churn |
|--------|----------------|
| **`bundler/openapi.source.yaml`** contract change | Models, route stubs, wiring; **`bundler_server/core/`** unchanged if handlers only delegate to **`bundler_core`**. |
| **OpenAPI Generator version** or **`openapitools.json`** changes | Broad scaffold diffs; **`make/`** may need updates. |
| **Core business logic only** | **`bundler_core`** (and **`bundler_server/core/`**); no server regen if the HTTP contract is unchanged. |
| **`make clean`** (from **`bundler/Makefile`**) | Removes paths listed under **`$(OPENAPI_OUTPUT_FOLDER)/.openapi-generator/FILES`**, then **`git restore`** that output tree—intended to reset **generated** layers to the last committed tree. Treat **`clean`** as resetting the **codegen** tree, not as deleting hand-owned work, unless those paths are listed in **`FILES`** and you have no backup. |

---

## Practical rules for this repo

- **Spec / generated surface** → assume it can be regenerated; keep stable behavior in **`bundler_server/core/`** and in **`bundler_core`**, not in generated routers you do not ignore.
- **uv / metadata / Docker baseline** → rely on **`make/`** after regen (see **`README_patch.md`**), not one-off edits to generated files you cannot defend in review.
- **“Refresh one generated file that lives behind ignore”** → temporary **un-ignore** (or delete that file + regen), merge, then **re-ignore**.

For patch philosophy and Docker commands, see **`README_patch.md`**.
