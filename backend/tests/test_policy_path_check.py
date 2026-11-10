"""
Which policy paths can be saved: a file, a folder and everything in it, or everything; nothing the
matcher would read differently from how it looks.
"""

import os

# The endpoints build their database engine on import, from DATABASE_URL
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost:5432/unused")

import core.services.filetree  # noqa: E402,F401  (imported before the endpoints, as the app does, to avoid an import cycle)
from api.v0_1.endpoints.policies import is_literal_policy_path  # noqa: E402


def test_a_file_a_folder_and_everything_can_be_saved():
    assert is_literal_policy_path("bucket/study/scan.nii.gz")
    assert is_literal_policy_path("bucket/study/*")
    assert is_literal_policy_path("*")
    assert is_literal_policy_path("bucket/notes..txt")


def test_a_star_anywhere_else_is_refused():
    assert not is_literal_policy_path("bucket/study*")
    assert not is_literal_policy_path("bucket/*/secret.txt")
    assert not is_literal_policy_path("bucket/a*b.txt")
    assert not is_literal_policy_path("bucket/.*")


def test_dot_dot_is_refused():
    assert not is_literal_policy_path("bucket/../*")
    assert not is_literal_policy_path("bucket/shared/../secret.txt")
