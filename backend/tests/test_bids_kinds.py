"""
Kinds of data as BIDS defines them (AC-6): a file's kind is its datatype folder, after sub-*/ or
sub-*/ses-*/, so sidecars count with their scans. Files BIDS doesn't place in a datatype have no kind.

Verifies: AC-6.
"""
import pytest

from core.services.standards import kind_of
from core.services.standards.bids import BIDS


@pytest.mark.parametrize("path, kind", [
    ("/sub-01/anat/sub-01_T1w.nii.gz", "anat"),
    ("/sub-01/anat/sub-01_T1w.json", "anat"),
    ("/sub-01/ses-1/func/sub-01_ses-1_task-rest_bold.nii.gz", "func"),
    ("/sub-02/dwi/sub-02_dwi.bvec", "dwi"),
    ("/dataset_description.json", None),
    ("/participants.tsv", None),
    ("/sub-01/sub-01_scans.tsv", None),
    ("/sub-01/notes/readme.txt", None),
    ("/derivatives/fmriprep/sub-01/anat/x.nii.gz", None),
])
def test_a_files_kind_is_its_datatype_folder(path, kind):
    assert BIDS().kind_of(path) == kind


def test_kinds_are_looked_up_by_standard():
    assert kind_of("BIDS", "/sub-01/anat/a.nii") == "anat"
    assert kind_of("NOT-A-STANDARD", "/sub-01/anat/a.nii") is None
    assert "anat" in BIDS().kinds and "func" in BIDS().kinds
