#!/usr/bin/env python3
"""Patch ``pyproject.toml`` using tomlkit: project metadata from ``setup.cfg``.

Assumes ``patch_setup_cfg.py`` has already run successfully (``setup.cfg`` is patched).

Usage:
```bash
    SERVER_PYTHON_VERSION=3.12 python3 make/patch_pyproject_toml.py \
        bundler_app_server_w/pyproject.toml
```

Sample input:
```toml
[build-system]
...
[tool.black]
...
[tool.isort]
...
skip_gitignore = true

```

Metadata mapping (from ``setup.cfg`` ``[metadata]``):

- ``name`` -> ``[project].name``
- ``version`` -> ``[project].version``
- ``description`` -> ``[project].description``
- ``long_description = file: <path>`` -> ``[project].readme`` (string path, e.g. ``"README.md"``)
- ``keywords`` -> ``[project].keywords`` (INI continuation lines merged by ConfigParser; one keyword per line after split)
- ``classifiers`` (block) -> ``[project].classifiers`` (array of strings)
- ``requires-python`` is set from ``requires_python(SERVER_PYTHON_VERSION)``, not copied raw from ``python_requires``.

Sample output (abridged):
```toml
[project]
name = "openapi_server" # from setup.cfg [metadata] name
version = "0.1.0" # from setup.cfg [metadata] version
description = "API contract for the Bundler service." # from setup.cfg [metadata] description
readme = "README.md" # parsed from setup.cfg [metadata] long_description = file: README.md
keywords = ["OpenAPI Bundler Service"] # from setup.cfg [metadata] keywords
classifiers = [ # parser from setup.cfg [metadata] classifiers
    "Operating System :: OS Independent", 
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "bundler>=0.1.0", # from subsequent `uv add bundler` command
]
requires-python = ">=3.12,<3.13"

[build-system]
...

```

# /// script
# dependencies = [
#   "tomlkit",
# ]
# ///

"""

from __future__ import annotations

import argparse
import configparser
import os
import re
from pathlib import Path

import tomlkit  # type: ignore[reportMissingImports]


def python_version() -> str:
    value = os.environ.get("SERVER_PYTHON_VERSION", "3.12").strip()
    if not re.fullmatch(r"\d+\.\d+", value):
        raise ValueError("SERVER_PYTHON_VERSION must look like '3.12'")
    return value


def requires_python(version: str) -> str:
    major, minor = (int(x) for x in version.split("."))
    return f">={major}.{minor},<{major}.{minor + 1}"


def _parse_long_description_readme(value: str) -> str | None:
    value = value.strip()
    m = re.match(r"^file:\s*(.+)$", value, re.I)
    if m:
        return m.group(1).strip()
    return None


def _metadata_section_text(raw: str) -> str:
    """Return lines belonging to ``[metadata]`` until the next ``[...]`` section."""
    m = re.search(r"(?ms)^\[metadata\]\s*\n(.*?)(?=^\[)", raw)
    if m:
        return m.group(1)
    m = re.search(r"(?ms)^\[metadata\]\s*\n(.*)\Z", raw)
    return m.group(1) if m else ""


PYTEST_IGNORE_GENERATED_DEFAULT_API = "--ignore=tests/test_default_api.py"


def _addopts_as_strings(value: object | None) -> list[str]:
    """Normalize pytest ``addopts`` (string or array) to a list of flag strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [p for p in value.split() if p]
    return [str(x) for x in value]


def _write_pytest_toml(output_dir: Path) -> None:
    """Ensure ``pytest.toml`` exists with ``[pytest]`` and the generated-stub ignore."""
    path = output_dir / "pytest.toml"
    ignore = PYTEST_IGNORE_GENERATED_DEFAULT_API

    if path.is_file():
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.parse(
            '[pytest]\nminversion = "9.0"\naddopts = []\n'
        )

    if "pytest" not in doc or not isinstance(doc["pytest"], tomlkit.items.Table):
        doc["pytest"] = tomlkit.table()
    py = doc["pytest"]
    if "minversion" not in py:
        py["minversion"] = "9.0"
    opts = _addopts_as_strings(py["addopts"] if "addopts" in py else None)
    if ignore not in opts:
        opts.append(ignore)
    py["addopts"] = opts

    out = tomlkit.dumps(doc)
    if not out.endswith("\n"):
        out += "\n"
    path.write_text(out, encoding="utf-8")
    print(f"patched {path}")


def _strip_legacy_pytest_from_tool(tool: tomlkit.items.Table) -> None:
    """Remove ``[tool.pytest]`` from ``pyproject.toml`` (config lives in ``pytest.toml``)."""
    if "pytest" in tool:
        del tool["pytest"]


def load_setup_metadata(setup_cfg: Path) -> dict[str, object]:
    if not setup_cfg.is_file():
        return {}

    raw = setup_cfg.read_text(encoding="utf-8")
    section = _metadata_section_text(raw)
    if not section.strip():
        return {}

    result: dict[str, object] = {}
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg.read_string("[metadata]\n" + section)

    meta = cfg["metadata"]
    if "name" in meta:
        result["name"] = str(meta["name"]).strip()
    if "version" in meta:
        result["version"] = str(meta["version"]).strip()
    if "description" in meta:
        result["description"] = str(meta["description"]).strip()

    long_desc = meta.get("long_description", "")
    if long_desc:
        readme = _parse_long_description_readme(str(long_desc))
        if readme:
            result["readme"] = readme

    # Same INI pattern as classifiers: one value per continuation line (ConfigParser merges lines).
    kw = meta.get("keywords", "")
    if kw and str(kw).strip():
        result["keywords"] = [
            line.strip() for line in str(kw).splitlines() if line.strip()
        ]

    # ConfigParser merges setuptools-style indented continuation lines into one value.
    cl = meta.get("classifiers", "")
    if cl and str(cl).strip():
        result["classifiers"] = [
            line.strip() for line in str(cl).splitlines() if line.strip()
        ]

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pyproject", type=Path)
    args = parser.parse_args()

    path = args.pyproject
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    parsed = tomlkit.parse(text) if text.strip() else tomlkit.document()

    py_ver = python_version()
    setup_path = Path(
        os.environ.get("SETUP_CFG_PATH", str(path.parent / "setup.cfg"))
    ).resolve()

    metadata = load_setup_metadata(setup_path)

    if "project" not in parsed:
        parsed["project"] = tomlkit.table()
    project = parsed["project"]

    # Preserve dependencies added by ``uv add`` (e.g. bundler).
    existing_deps = project.get("dependencies")

    # Build ``[project]`` in insertion order; assign ``requires-python`` last so it stays last.
    project_table = tomlkit.table()
    for key in ("name", "version", "description", "readme", "keywords", "classifiers"):
        if key in metadata:
            project_table[key] = metadata[key]
    if existing_deps is not None:
        project_table["dependencies"] = existing_deps
    elif "dependencies" in project:
        project_table["dependencies"] = project["dependencies"]
    for k in project.keys():
        if k in project_table or k == "requires-python":
            continue
        project_table[k] = project[k]
    project_table["requires-python"] = requires_python(py_ver)

    # New document: ``[project]`` first, then other top-level keys as in the parsed file, then
    # ``[tool]`` last (tomlkit serializes tables in insertion order).
    doc = tomlkit.document()
    doc["project"] = project_table
    for k in parsed:
        if k in ("project", "tool"):
            continue
        doc[k] = parsed[k]

    if "tool" in parsed:
        tool = parsed["tool"]
        # We intentionally let `uv add` manage sources to avoid key-normalization drift.
        if "uv" in tool and "sources" in tool["uv"]:
            del tool["uv"]["sources"]
        _strip_legacy_pytest_from_tool(tool)
        doc["tool"] = tool

    _write_pytest_toml(path.parent)

    out = tomlkit.dumps(doc)
    if not out.endswith("\n"):
        out += "\n"
    path.write_text(out, encoding="utf-8")
    print(f"patched {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
