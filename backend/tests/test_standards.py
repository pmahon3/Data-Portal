"""
Datasets checked against the standard they declare, when an upload completes (strategy 5.1 step 3).
A stand-in validator plugs into the seam; MongoDB and the file tree are replaced in memory.

Verifies: STD-1.
"""
import asyncio

import pytest

from core.services import standards


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def replace_one(self, query, doc, upsert=False):
        self.docs[query["_id"]] = dict(doc)

    def find(self, query):
        return [d for d in self.docs.values() if all(d.get(k) == v for k, v in query.items())]


class FakeTree:
    def __init__(self, keys):
        self.keys = set(keys)

    async def complete_keys(self, bucket, keys):
        return self.keys & set(keys)

    async def complete_keys_under(self, bucket, prefix):
        return sorted(k for k in self.keys if k.startswith(prefix))


class NoCaps:
    """Stand-in standard: declared by DECLARE; a file name with capitals fails."""
    standard = "nocaps"
    marker = "DECLARE"

    def check(self, paths):
        return [standards.Finding(p, "capitals") for p in paths if p != "/DECLARE" and p != p.lower()]


@pytest.fixture
def store(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(standards, "_collection", lambda: collection)
    monkeypatch.setattr(standards, "VALIDATORS", [NoCaps()])
    return collection


def check(keys, uploaded):
    return asyncio.run(standards.check_upload(FakeTree(keys), "b", uploaded))


def test_a_failing_dataset_is_quarantined_and_the_failures_named(store):
    keys = ["study/DECLARE", "study/sub-01/ok.nii", "study/sub-01/Bad.nii"]
    (result,) = check(keys, ["study/sub-01/Bad.nii"])
    assert result["root"] == "study/" and result["quarantined"]
    assert result["findings"] == [{"path": "/sub-01/Bad.nii", "problem": "capitals"}]
    assert [r["standard"] for r in standards.quarantined("b", "study/")] == ["nocaps"]


def test_the_whole_dataset_is_checked_not_only_this_upload(store):
    (result,) = check(["study/DECLARE", "study/Old.nii", "study/new.nii"], ["study/new.nii"])
    assert result["problems"] == 1 and result["findings"][0]["path"] == "/Old.nii"


def test_an_upload_outside_a_declared_folder_isnt_checked(store):
    assert check(["study/DECLARE", "other/Bad.nii"], ["other/Bad.nii"]) == []
    assert store.docs == {}


def test_the_nearest_declaring_folder_is_the_dataset(store):
    keys = ["study/DECLARE", "study/derived/DECLARE", "study/derived/out.nii"]
    (result,) = check(keys, ["study/derived/out.nii"])
    assert result["root"] == "study/derived/"


def test_fixing_the_files_takes_the_dataset_out_of_quarantine(store):
    check(["study/DECLARE", "study/Bad.nii"], ["study/Bad.nii"])
    (result,) = check(["study/DECLARE", "study/good.nii"], ["study/good.nii"])
    assert not result["quarantined"] and standards.quarantined("b", "study/") == []


def test_a_dataset_at_the_bucket_root_is_declared_there(store):
    (result,) = check(["DECLARE", "Bad.nii"], ["Bad.nii"])
    assert result["root"] == "" and result["findings"][0]["path"] == "/Bad.nii"


def test_long_reports_are_cut_and_counted(store, monkeypatch):
    monkeypatch.setattr(standards, "REPORTED", 2)
    (result,) = check(["study/DECLARE"] + [f"study/F{i}.nii" for i in range(5)], ["study/F0.nii"])
    assert result["problems"] == 5 and len(result["findings"]) == 2


def test_with_no_standard_plugged_in_nothing_is_checked(store, monkeypatch):
    monkeypatch.setattr(standards, "VALIDATORS", [])
    assert check(["study/DECLARE", "study/Bad.nii"], ["study/Bad.nii"]) == []
