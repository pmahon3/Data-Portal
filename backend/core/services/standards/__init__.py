"""
Datasets checked against the standard they declare (STD-1). A folder declares a standard by holding
that standard's marker file at its root (BIDS: ``dataset_description.json``), so files placed on a
machine directly declare it the same way as an upload. When an upload completes, every declared
dataset it touched is checked as a whole; a failure puts the dataset in quarantine, a later pass
takes it out, and the researcher is told what failed in the upload's response.

What quarantine holds back is an open question (N-QUARANTINE), so here it's only recorded. Which
standards the portal checks is another (E-STD): each plugs in a ``Validator`` (``VALIDATORS``).
Checks read names and layout from the file tree, never file contents. A standard also names the kinds
of data it defines (BIDS: datatypes such as ``anat``), and a file's kind from its path, so a policy can
be limited to kinds (AC-6).
"""
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
        """Every file in the dataset, relative to its root with a leading "/"; returns what fails."""

    def kind_of(self, path: str) -> str | None:
        """The kind of a file, from its path relative to the dataset's root with a leading "/"."""


class Tree(Protocol):
    async def complete_keys(self, bucket: str, keys: list[str]) -> set[str]: ...
    async def complete_keys_under(self, bucket: str, prefix: str) -> list[str]: ...


VALIDATORS: list[Validator] = []


def _plug_in() -> None:
    """The standards named in DATA_STANDARDS (comma-separated; "" for none)."""
    available = {"bids": "core.services.standards.bids:BIDS"}
    for name in filter(None, (s.strip().lower() for s in os.getenv("DATA_STANDARDS", "bids").split(","))):
        if name not in available:
            logger.warning("DATA_STANDARDS names %r, which isn't available", name)
            continue
        module, cls = available[name].split(":")
        VALIDATORS.append(getattr(__import__(module, fromlist=[cls]), cls)())


def standard(name: str) -> Validator | None:
    """The plugged-in standard with that name (e.g. "BIDS")."""
    return next((v for v in VALIDATORS if v.standard == name), None)


def kind_of(name: str, path: str) -> str | None:
    """A file's kind as standard `name` defines it; None if it defines none or isn't plugged in."""
    found = standard(name)
    return found.kind_of(path) if found else None


def ancestors(key: str) -> list[str]:
    """Folder prefixes of an object key, nearest first: "a/b/c.nii" gives "a/b/", "a/", ""."""
    parts = key.split("/")[:-1]
    return ["/".join(parts[:i]) + "/" if i else "" for i in range(len(parts), -1, -1)]


async def declared_roots(tree: Tree, bucket: str, keys: list[str], marker: str) -> set[str]:
    """The nearest folder declaring the standard above each key (none if no folder does)."""
    candidates = {a for k in keys for a in ancestors(k)}
    markers = await tree.complete_keys(bucket, [c + marker for c in candidates])
    roots = set()
    for k in keys:
        nearest = next((a for a in ancestors(k) if a + marker in markers), None)
        if nearest is not None:
            roots.add(nearest)
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
    """The latest result for one dataset and standard, replacing the one before."""
    result = {"_id": f"{bucket}:{root}:{standard}", "bucket": bucket, "root": root, "standard": standard,
              "quarantined": bool(findings), "problems": len(findings),
              "findings": [{"path": f.path, "problem": f.problem} for f in findings[:REPORTED]],
              "checked_at": datetime.utcnow()}
    _collection().replace_one({"_id": result["_id"]}, result, upsert=True)
    if findings:
        logger.info("dataset %s/%s quarantined: %s %s problem(s)", bucket, root, standard, len(findings))
    return result


def quarantined(bucket: str, root: str) -> list[dict]:
    """The standards a dataset currently fails."""
    return list(_collection().find({"bucket": bucket, "root": root, "quarantined": True}))


_plug_in()
