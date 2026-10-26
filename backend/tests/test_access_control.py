"""
Access control, tested from the outside: a user signs in, acts through the portal API, and
the test checks the HTTP answer and what the object store holds afterwards.

Requirements are in docs/requirements/access-control.md (AC-n). Tests marked with a ticket
are known to fail on the current code; each fix removes its marker. The markers are strict,
so a test that starts passing while still marked fails the run. To see the real failures:

    pytest tests/test_access_control.py --runxfail

Needs a running stack (local/: backend, Keycloak, MinIO, Postgres, MongoDB) and a storage
instance on it; tests skip when there isn't one. Settings are listed in portal_stack.py.
From backend/, after `set -a; . ../local/.env; set +a`:

    pytest tests/test_access_control.py -v

Each run creates its own bucket, and each test its own users with only the grants it names,
removed afterwards. Grants name single files, or folders as "folder/*".
"""
import pytest

from portal_stack import Portal, StackUnavailable, Tree, browsed, key_in_url, listed

INN_289 = pytest.mark.xfail(strict=True, reason="INN-289: a file name with a bracket breaks permission checks")
INN_291 = pytest.mark.xfail(strict=True, reason="INN-291: a grant written with a leading '/' grants nothing")
INN_292 = pytest.mark.xfail(strict=True, reason="INN-292: a grant covers paths that only start with the same text")
INN_293 = pytest.mark.xfail(strict=True, reason="INN-293: access to one file allows acting on the folders above it")
INN_294 = pytest.mark.xfail(strict=True, reason="INN-294: folder listings show files the user can't access")

# Every file in the test bucket. Tests that change files work in a folder of their own.
FILES = [
    "shared/notes.txt",
    "shared/notes.txt.secret",
    "data/report.csv",
    "data/report.csv.bak",
    "fold/a.txt",
    "folder-secret/x.txt",
    "study/scan-042.nii",
    "study/scan-043.nii",
    "study/patient-7/summary.csv",
    "study/patient-7/identifiers-MRN-0047731.csv",
    "other/unrelated.txt",
    "slash/notes.txt",
    "brackets/ok.txt",
    "brackets/a[b.bin",
    "del/one.nii",
    "del/two.nii",
    "del/sub/three.csv",
    "over/mine.csv",
    "over/theirs.csv",
    "over/sub/other.csv",
    "held/a.txt",
    "held/sub/b.txt",
    "own/del-me.txt",
    "own/keep.txt",
    "box/a.txt",
    "box/c.txt",
    "box/sub/b.txt",
]
# The browsing user never lists brackets/: on the current code that listing fails (INN-289).
BROWSABLE = [key for key in FILES if not key.startswith("brackets/") or key == "brackets/ok.txt"]


@pytest.fixture(scope="session")
def portal():
    try:
        portal = Portal()
    except StackUnavailable as reason:
        pytest.skip(str(reason))
    try:
        portal.put_files({key: f"{key}\n".encode() for key in FILES})
        yield portal
    finally:
        portal.remove_bucket()


@pytest.fixture(scope="session")
def tree(portal):
    """Folder and file ids, found by a user who may read every file it looks up."""
    browser = portal.create_user()
    for key in BROWSABLE:
        portal.grant(browser, portal.resource(key), "read")
    yield Tree(browser)
    portal.delete_user(browser)


@pytest.fixture
def make_user(portal):
    """make_user(("read", "shared/notes.txt"), ...): a new user holding exactly these grants,
    each on a path in the test bucket. Removed after the test."""
    made = []

    def make(*grants):
        user = portal.create_user()
        made.append(user)
        for action, key in grants:
            portal.grant(user, portal.resource(key), action)
        return user

    yield make
    for user in made:
        portal.delete_user(user)


# --------------------------------------------------------------------------- controls
# These pass before and after the fixes. If one fails, the setup is wrong and the other
# results mean nothing.

def test_a_user_can_read_a_file_they_hold(make_user, tree):
    user = make_user(("read", "study/patient-7/summary.csv"))
    assert user.download_url(tree.file("study/patient-7/summary.csv")).status_code == 200


def test_a_user_cannot_read_a_file_they_do_not_hold(make_user, tree):
    """AC-3."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    assert user.download_url(tree.file("other/unrelated.txt")).status_code == 403


def test_a_user_cannot_list_a_folder_they_hold_nothing_in(make_user, tree):
    """AC-1."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    assert user.list_folder(tree.folder("other/")).status_code == 403


def test_a_user_cannot_upload_into_a_folder_they_hold_nothing_in(make_user, tree):
    """AC-3."""
    user = make_user(("write", "data/report.csv.bak"))
    assert user.upload_init(tree.folder("other/"), "new.txt").status_code == 403


def test_a_user_cannot_delete_a_file_they_do_not_hold(make_user, tree, portal):
    """AC-2."""
    user = make_user(("delete", "study/scan-042.nii"))
    assert user.delete_file(tree.file("study/scan-043.nii")).status_code == 403
    assert "study/scan-043.nii" in portal.stored("study/")


def test_a_user_can_delete_a_file_they_hold(make_user, tree, portal):
    user = make_user(("delete", "own/del-me.txt"))
    assert user.delete_file(tree.file("own/del-me.txt")).status_code == 200
    assert set(portal.stored("own/")) == {"own/keep.txt"}


def test_uploading_a_file_never_replaces_an_existing_one(make_user, tree, portal):
    """AC-2. data/report.csv exists and isn't the user's: refused as forbidden (403) or as a
    name conflict (409), and its content is unchanged."""
    user = make_user(("write", "data/report.csv.bak"))
    before = portal.stored("data/report.csv")
    assert user.upload_init(tree.folder("data/"), "report.csv").status_code in (403, 409)
    assert portal.stored("data/report.csv") == before


def test_a_folder_grant_allows_uploading_into_and_deleting_the_folder(make_user, tree, portal):
    """Checking each file must not break users whose grant covers the whole folder."""
    user = make_user(("write", "held/*"), ("delete", "held/*"))
    r = user.folder_upload_init(tree.folder("held/"), ["a.txt", "sub/new.txt"], on_conflict="replace")
    assert r.status_code == 200, r.text
    r = user.delete_folder(tree.folder("held/"))
    assert r.status_code == 200, r.text
    assert portal.stored("held/") == {}


def test_a_folder_download_holds_only_files_the_user_may_read(make_user, tree, portal):
    """AC-4. With one readable file in the selected folder, the portal answers with a direct
    link to that file alone."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    r = user.download_bundle(folder_ids=[tree.folder("study/patient-7/")])
    assert r.status_code == 200, r.text
    assert key_in_url(r.json()["single_file_url"], portal.bucket) == "study/patient-7/summary.csv"


def test_a_download_refuses_a_selected_file_the_user_may_not_read(make_user, tree):
    """AC-3."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    r = user.download_bundle(file_ids=[tree.file("study/patient-7/summary.csv"),
                                       tree.file("study/patient-7/identifiers-MRN-0047731.csv")])
    assert r.status_code == 403


# ------------------------------------------------- a grant covers exactly what it names

@INN_292
def test_a_file_grant_does_not_cover_longer_names(make_user, tree):
    """AC-5. Read on shared/notes.txt gives nothing on shared/notes.txt.secret."""
    user = make_user(("read", "shared/notes.txt"))
    assert user.download_url(tree.file("shared/notes.txt.secret")).status_code == 403


@INN_292
def test_a_file_grant_does_not_allow_creating_longer_names(make_user, tree):
    """AC-5. Write on data/report.csv.bak doesn't allow creating data/report.csv.bak.evil."""
    user = make_user(("write", "data/report.csv.bak"))
    assert user.upload_init(tree.folder("data/"), "report.csv.bak.evil").status_code == 403


@INN_292
def test_a_dot_in_a_grant_is_just_a_dot(make_user, tree):
    """AC-5. Write on data/report.csv.bak doesn't allow writing data/reportXcsv.bak."""
    user = make_user(("write", "data/report.csv.bak"))
    assert user.upload_init(tree.folder("data/"), "reportXcsv.bak").status_code == 403


@INN_292
def test_a_folder_grant_does_not_cover_folders_sharing_its_name(make_user, tree):
    """AC-5. Read on fold/* gives nothing in folder-secret/."""
    user = make_user(("read", "fold/*"))
    assert user.download_url(tree.file("fold/a.txt")).status_code == 200
    assert user.download_url(tree.file("folder-secret/x.txt")).status_code == 403


@INN_289
def test_a_folder_holding_a_file_named_with_a_bracket_can_be_browsed(make_user, tree):
    """AC-1. The page's file tree for brackets/ answers normally and shows only the user's
    file, although the folder also holds brackets/a[b.bin."""
    user = make_user(("read", "brackets/ok.txt"))
    r = user.browse("read", tree.folder("brackets/"))
    assert r.status_code == 200, r.text
    assert browsed(r) == (set(), {"brackets/ok.txt"})


@INN_289
def test_a_grant_on_a_file_named_with_a_bracket_gives_access_to_it(make_user, tree):
    """AC-5. Read on brackets/a[b.bin can be granted, and shows and reads that file."""
    user = make_user(("read", "brackets/a[b.bin"))
    r = user.browse("read", tree.folder("brackets/"))
    assert r.status_code == 200, r.text
    assert browsed(r) == (set(), {"brackets/a[b.bin"})
    file_id = int(next(n["id"] for n in r.json()["assets"]).removeprefix("file-"))
    assert user.download_url(file_id).status_code == 200


@INN_291
def test_a_grant_written_with_a_leading_slash_gives_access(make_user, tree, portal):
    """AC-5. A grant entered as "/bucket/slash/notes.txt", the form the policy screen
    suggested, gives read on that file."""
    user = make_user()
    portal.grant(user, "/" + portal.resource("slash/notes.txt"), "read")
    assert user.download_url(tree.file("slash/notes.txt")).status_code == 200


# --------------------------------------- one file never opens the folders above it

def test_a_file_grant_does_not_allow_deleting_the_folder_above(make_user, tree, portal):
    """AC-2. Delete on del/one.nii doesn't allow deleting del/, and nothing is deleted."""
    user = make_user(("delete", "del/one.nii"))
    before = portal.stored("del/")
    assert user.delete_folder(tree.folder("del/")).status_code == 403
    assert portal.stored("del/") == before


def test_a_file_grant_does_not_allow_replacing_other_files_by_folder_upload(make_user, tree, portal):
    """AC-2. Write on over/mine.csv doesn't allow a folder upload that replaces
    over/theirs.csv and over/sub/other.csv."""
    user = make_user(("write", "over/mine.csv"))
    before = portal.stored("over/")
    r = user.folder_upload_init(tree.folder("over/"), ["theirs.csv", "sub/other.csv"], on_conflict="replace")
    assert r.status_code == 403, r.text
    assert portal.stored("over/") == before


def test_deleting_a_folder_never_removes_a_file_the_user_could_not_delete(make_user, tree, portal):
    """AC-2. A grant entered on the bare folder path "box/" (no "*") may be refused, or may
    cover the files inside, but deleting the folder never removes a file the same user
    couldn't delete on its own."""
    user = make_user()
    folder_id, file_id = tree.folder("box/"), tree.file("box/a.txt")
    if portal.try_grant(user, portal.resource("box/"), "delete") is None:
        return
    file_deletable = user.delete_file(file_id).status_code == 200
    before = portal.stored("box/")
    r = user.delete_folder(folder_id)
    if not file_deletable:
        assert r.status_code == 403, r.text
        assert portal.stored("box/") == before


@INN_293
@pytest.mark.parametrize("parent", ["", "data/"])
def test_a_file_grant_does_not_allow_creating_folders_above_it(make_user, tree, parent):
    """AC-2. Write on data/report.csv.bak doesn't allow creating folders in data/ or at the
    bucket root."""
    user = make_user(("write", "data/report.csv.bak"))
    assert user.create_folder(tree.folder(parent), "made-by-test").status_code == 403


# ------------------------------------------------ listings show only the user's path

@INN_294
def test_a_folder_listing_shows_only_files_the_user_may_read(make_user, tree):
    """AC-1. Listing study/patient-7/ shows summary.csv, not the file beside it."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    r = user.list_folder(tree.folder("study/patient-7/"))
    assert r.status_code == 200, r.text
    assert listed(r) == (set(), {"study/patient-7/summary.csv"})


@INN_294
def test_listings_above_a_file_show_only_the_path_to_it(make_user, tree):
    """AC-1. study/ shows only patient-7/, and the bucket root only study/."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    r = user.list_folder(tree.folder("study/"))
    assert r.status_code == 200, r.text
    assert listed(r) == ({"/study/patient-7/"}, set())
    r = user.list_folder(tree.folder(""))
    assert r.status_code == 200, r.text
    assert listed(r) == ({"/study/"}, set())
