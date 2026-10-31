"""
BIDS datasets checked by name and layout when an upload completes (strategy 5.1 step 3), through
the validation seam. MongoDB and the file tree are replaced in memory.

Verifies: STD-1.
"""
import asyncio

import pytest

from core.services import standards
from core.services.standards.bids import BIDS
from tests.test_standards import FakeCollection, FakeTree


@pytest.fixture
def store(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(standards, "_collection", lambda: collection)
    return collection


def check(keys):
    return asyncio.run(standards.check_upload(FakeTree(keys), "b", keys))


SESSION = ["scan/dataset_description.json", "scan/participants.tsv", "scan/README",
           "scan/sub-01/anat/sub-01_T1w.nii.gz", "scan/sub-01/anat/sub-01_T1w.json",
           "scan/sub-01/func/sub-01_task-rest_bold.nii.gz"]


def test_bids_is_plugged_in_by_default():
    assert any(isinstance(v, BIDS) for v in standards.VALIDATORS)


def test_a_valid_bids_session_passes(store):
    (result,) = check(SESSION)
    assert (result["standard"], result["root"], result["quarantined"]) == ("BIDS", "scan/", False)


def test_a_misnamed_scan_is_held_and_named(store):
    (result,) = check(SESSION + ["scan/sub-01/anat/T1.nii", "scan/notes.txt"])
    assert result["quarantined"]
    assert sorted(f["path"] for f in result["findings"]) == ["/notes.txt", "/sub-01/anat/T1.nii"]


def test_derivatives_code_and_source_data_are_allowed(store):
    (result,) = check(SESSION + ["scan/derivatives/fmriprep/out.nii.gz", "scan/code/run.py",
                                 "scan/sourcedata/raw.dcm"])
    assert not result["quarantined"]


def test_hidden_files_are_left_out(store):
    (result,) = check(SESSION + ["scan/.DS_Store", "scan/.bidsignore", "scan/.git/config"])
    assert not result["quarantined"]


def test_a_folder_without_dataset_description_isnt_bids(store):
    assert check(["other/T1.nii"]) == []
