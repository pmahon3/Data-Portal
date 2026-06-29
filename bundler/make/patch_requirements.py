#!/usr/bin/env python3
"""Normalize generated ``requirements.txt`` by removing version constraints.

Usage:
    python3 make/patch_requirements.py bundler_app_server/requirements.txt

Sample input:
    fastapi==0.109.2
    pydantic>=2
    uvicorn[standard]>=0.30.0
    uvicorn[standard]>=0.30.0; python_version < "3.13" # dev note
    requests>=2.20 # keep comment
    pkg @ https://example.com/wheel.whl#sha256=abc

Sample output after patch:
    fastapi
    pydantic
    uvicorn[standard]
    uvicorn[standard]; python_version < "3.13" # dev note
    requests # keep comment
    pkg @ https://example.com/wheel.whl#sha256=abc
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

CONSTRAINT_RE = re.compile(r"\s*(==|~=|!=|<=|>=|<|>)\s*[^;\s]+")
# Split a requirement line into three optional parts:
# - req:     requirement expression body (always present, may be empty)
# - marker:  environment marker starting with ';' (e.g. `; python_version < "3.13"`)
# - comment: trailing inline comment that must start with whitespace + '#'
#
# Important: comment is `\s+#...`, not just `#...`, so URL fragments like
# `pkg @ https://.../wheel.whl#sha256=...` stay in `req` and are not mistaken for comments.
LINE_PARTS_RE = re.compile(
    r"^(?P<req>.*?)(?P<marker>\s*;[^#]*)?(?P<comment>\s+#.*)?$"
)


def strip_constraints(line: str) -> str:
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return raw

    # Parse line into requirement / marker / inline comment in one regex pass.
    # Comments only match when preceded by whitespace, so URL fragments like
    # `...#sha256=...` stay part of the requirement body.
    m = LINE_PARTS_RE.match(raw)
    if not m:
        return raw
    req_part = (m.group("req") or "").rstrip()
    marker = m.group("marker") or ""
    comment = m.group("comment") or ""

    req_part = CONSTRAINT_RE.sub("", req_part, count=1).rstrip()
    return f"{req_part}{marker}{comment}".rstrip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("requirements_txt", type=Path)
    args = parser.parse_args()

    path = args.requirements_txt
    lines = path.read_text(encoding="utf-8").splitlines()
    out_lines = [strip_constraints(line) for line in lines]
    path.with_stem(path.stem + "-unpinned").write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")
    print(f"patched {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

