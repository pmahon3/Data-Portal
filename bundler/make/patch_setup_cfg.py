#!/usr/bin/env python3
"""Minimally patch generated ini-style ``setup.cfg``.

Usage:
```bash
    SERVER_PYTHON_VERSION=3.12 python3 make/patch_setup_cfg.py \
        bundler_app_server_w/setup.cfg
```

Sample input:
```toml
[metadata]
name = openapi_server
version = 0.1.0
description = API contract for the Bundler service.
long_description = file: README.md
keywords = OpenAPI Bundler Service
python_requires = >= 3.7.*
classifiers = 
	Operating System :: OS Independent
	Programming Language :: Python :: 3
	Programming Language :: Python :: 3.7
```
Sample output after patch:
```toml
[metadata]
...
python_requires = >= 3.12.*
classifiers = 
	Operating System :: OS Independent
	Programming Language :: Python :: 3
	Programming Language :: Python :: 3.12
```
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


def python_version() -> str:
    value = os.environ.get("SERVER_PYTHON_VERSION", "3.12").strip()
    if not re.fullmatch(r"\d+\.\d+", value):
        raise ValueError("SERVER_PYTHON_VERSION must look like '3.12'")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("setup_cfg", type=Path)
    args = parser.parse_args()

    path = args.setup_cfg
    version = python_version()
    text = path.read_text(encoding="utf-8")

    text = re.sub(
        r"(?m)^python_requires\s*=.*$",
        f"python_requires = >= {version}.*",
        text,
        count=1,
    )

    # Replace only the versioned classifier, keep all other content unchanged.
    if re.search(r"Programming Language :: Python :: \d+\.\d+", text):
        text = re.sub(
            r"Programming Language :: Python :: \d+\.\d+",
            f"Programming Language :: Python :: {version}",
            text,
            count=1,
        )

    path.write_text(text, encoding="utf-8")
    print(f"patched {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

