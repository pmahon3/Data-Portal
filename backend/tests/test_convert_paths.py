# backend/tests/test_convert_paths.py
"""
Converting stored policy paths to literal paths (INN-297)

The one-off conversion rewrites the regular expressions the policy form suggested, keeps paths that
were already literal, and leaves anything else for a person.
"""

import pytest

from core.services.policies.convert_paths import literal


@pytest.mark.parametrize("stored, converted", [
    (".*", "*"),
    ("bucket/folder/.*", "bucket/folder/*"),
    ("bucket/folder/scan.nii.gz", "bucket/folder/scan.nii.gz"),
    ("bucket/brackets/a[b.bin", None),
    ("bucket/(a|b)/.*", None),
    ("bucket/folder/sub.*", None),
])
def test_stored_paths_are_rewritten_or_left_for_a_person(stored, converted):
    assert literal(stored) == converted
