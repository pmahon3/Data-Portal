"""
How access decisions scale (AC-11): the targets in docs/requirements/access-control.md, for a user
holding many policies, many of them with conditions (what the tree picker makes when a folder is
ticked and things inside it are unticked).

  - one check under 1 ms;
  - a 10,000-entry folder listing decided under 200 ms;
  - a 100,000-file folder (a delete or a download) decided under 1 s.

Each test times the best of three runs, so a busy machine doesn't fail it.

Verifies: AC-11
"""
import time

from core.services.policies.rules import Checker, Rule

SUBJECTS = 500
PATHS = [f"study/sub-{i % SUBJECTS:03d}/anat/f{i}.nii" for i in range(100_000)]


def best_of_three(work):
    times = []
    for _ in range(3):
        start = time.perf_counter()
        work()
        times.append(time.perf_counter() - start)
    return min(times)


def picker_user():
    """2,000 plain policies elsewhere, and 200 folder policies inside the study, one per subject, each
    leaving out five things and limited to one ending: the other 300 subjects are denied, so each of
    their files is checked against every policy that could cover it."""
    rules = [Rule(f"other/p{i}/*", "read") for i in range(2_000)]
    rules += [Rule(f"study/sub-{s:03d}/*", "read", excluded=tuple(f"study/sub-{s:03d}/x{j}/*" for j in range(5)),
                   endings=(".nii", ".nii.gz")) for s in range(200)]
    return Checker(rules)


def one_folder_user():
    """Twenty conditioned policies on the same folder, none of which covers its files (the worst case)."""
    return Checker([Rule("study/*", "read", excluded=tuple(f"study/x{j}/*" for j in range(20)), endings=(f".e{i}",))
                    for i in range(20)])


def test_a_100000_file_folder_is_decided_in_under_a_second():
    checker = picker_user()
    assert best_of_three(lambda: checker.split(PATHS, "read")) < 1.0


def test_many_policies_on_one_folder_still_decide_100000_files_in_under_a_second():
    checker = one_folder_user()
    assert best_of_three(lambda: checker.split(PATHS, "read")) < 1.0


def test_a_10000_entry_listing_is_decided_in_under_200_ms():
    checker = picker_user()
    entries = PATHS[:9_500] + [f"study/sub-{s:03d}/" for s in range(SUBJECTS)]
    assert best_of_three(lambda: [checker.allows(e, "read") or checker.shows_folder(e, "read")
                                  for e in entries]) < 0.2


def test_one_check_takes_under_a_millisecond():
    checker = picker_user()
    sample = PATHS[:1_000]
    assert best_of_three(lambda: [checker.allows(p, "read") for p in sample]) / len(sample) < 0.001
