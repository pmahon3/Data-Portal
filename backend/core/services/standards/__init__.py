"""
Check datasets against the standard they declare (STD-1).

A folder declares a standard by holding that standard's marker file at its root (BIDS:
``dataset_description.json``), so files placed on a machine directly declare it the same way as an
upload. When an upload completes, every declared dataset it touched is checked as a whole; a failure
puts the dataset in quarantine, a later pass takes it out, and the response tells the researcher what
failed. Checks read names and layout from the file tree, never file contents.

What quarantine holds back is open (N-QUARANTINE), so here it's only recorded. Which standards are
checked is open too (E-STD): each plugs in a ``Validator``. A standard also names the kinds of data it
defines (BIDS: ``anat``, ``func``, ...) and a file's kind from its path, for policies (AC-6).
"""
from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from core.db.mongodb.mongo_client import get_mongo_database

logger = logging.getLogger(__name__)

REPORTED = 100  # findings listed per dataset in a response; the count covers the rest


@dataclass(frozen=True)
class Finding:
    path: str  # relative to the dataset's root, with a leading "/"
    problem: str


class Validator(Protocol):
    standard: str  # e.g. "BIDS"
    marker: str  # file at a dataset's root that declares the standard

    kinds: frozenset[str]  # the kinds of data it defines

    def check(self, paths: list[str]) -> list[Finding]:
        """Check every file in the dataset (relative to its root, with a leading "/"); return what fails."""

    def kind_of(self, path: str) -> str | None:
        """Return a file's kind, from its path relative to the dataset's root with a leading "/"."""


class Tree(Protocol):
    async def complete_keys(self, bucket: str, keys: list[str]) -> set[str]: ...
    async def complete_keys_under(self, bucket: str, prefix: str) -> list[str]: ...


VALIDATORS: list[Validator] = []


def _plug_in() -> None:
    """Plug in the standards named in ``DATA_STANDARDS`` (comma-separated; "" for none)."""
    available = {"bids": "core.services.standards.bids:BIDS"}
    for name in os.getenv("DATA_STANDARDS", "bids").split(","):
        name = name.strip().lower()
        if not name:
            continue
        if name not in available:
            logger.warning("DATA_STANDARDS names %r, which isn't available", name)
            continue
        # imported by name, so a standard's library loads only when it's plugged in
        module_name, class_name = available[name].split(":")
        module = importlib.import_module(module_name)
        VALIDATORS.append(getattr(module, class_name)())


def standard(name: str) -> Validator | None:
    """Return the plugged-in standard with that name (e.g. "BIDS"), or None."""
    for validator in VALIDATORS:
        if validator.standard == name:
            return validator
    return None


def kind_of(name: str, path: str) -> str | None:
    """Return a file's kind as standard ``name`` defines it; None if it has none or isn't plugged in."""
    found = standard(name)
    if found is None:
        return None
    return found.kind_of(path)


def ancestors(key: str) -> list[str]:
    """
    Return the folder prefixes of an object key, nearest first.

    Example: "a/b/c.nii" -> ["a/b/", "a/", ""]
    """
    parts = key.split("/")[:-1]
    prefixes = []
    for i in range(len(parts), 0, -1):
        prefixes.append("/".join(parts[:i]) + "/")
    prefixes.append("")
    return prefixes


async def declared_roots(tree: Tree, bucket: str, keys: list[str], marker: str) -> set[str]:
    """Return the nearest folder declaring the standard above each key (none if no folder does)."""
    candidates = {a for k in keys for a in ancestors(k)}
    markers = await tree.complete_keys(bucket, [c + marker for c in candidates])
    roots = set()
    for k in keys:
        for folder in ancestors(k):
            if folder + marker in markers:
                roots.add(folder)
                break
    return roots


async def check_upload(tree: Tree, bucket: str, keys: list[str]) -> list[dict]:
    """Check every declared dataset the uploaded keys belong to; record and return each result."""
    results = []
    for validator in VALIDATORS:
        for root in sorted(await declared_roots(tree, bucket, keys, validator.marker)):
            paths = ["/" + k[len(root):] for k in await tree.complete_keys_under(bucket, root)]
            findings = validator.check(paths)
            results.append(record(bucket, root, validator.standard, findings))
    return results


def _collection():
    return get_mongo_database()[os.getenv("MONGO_DATASET_CHECK_COLLECTION", "dataset-checks")]


def record(bucket: str, root: str, standard: str, findings: list[Finding]) -> dict:
    """Record the latest result for one dataset and standard, replacing the one before."""
    result = {
        "_id": f"{bucket}:{root}:{standard}",
        "bucket": bucket,
        "root": root,
        "standard": standard,
        "quarantined": bool(findings),
        "problems": len(findings),
        "findings": [{"path": f.path, "problem": f.problem} for f in findings[:REPORTED]],
        "checked_at": datetime.utcnow(),
    }
    _collection().replace_one({"_id": result["_id"]}, result, upsert=True)
    if findings:
        logger.info("dataset %s/%s quarantined: %s %s problem(s)", bucket, root, standard, len(findings))
    return result


def quarantined(bucket: str, root: str) -> list[dict]:
    """Return the standards a dataset currently fails."""
    return list(_collection().find({"bucket": bucket, "root": root, "quarantined": True}))


_plug_in()
