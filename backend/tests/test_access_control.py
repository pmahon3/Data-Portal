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
import datetime
import time
import uuid
from urllib.parse import parse_qs, urlsplit, urlunsplit

import pytest
import requests

from portal_stack import Portal, StackUnavailable, Tree, browsed, key_in_url, listed, setting


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
    "bids/dataset_description.json",
    "bids/sub-01/anat/sub-01_T1w.nii.gz",
    "bids/sub-01/func/sub-01_task-rest_bold.nii.gz",
    "ren/results/a.txt",
    "mov/in/x.txt",
    "mov/out/keep.txt",
    "link/a.txt",
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
    """AC-5. Control: a file grant gives read on that file."""
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
    """AC-5. Control: a file grant gives delete on that file."""
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
    """AC-5. Checking each file must not break users whose grant covers the whole folder."""
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


def test_another_users_bundle_cant_be_checked_or_fetched(make_user, tree):
    """AC-3. A bundle ID isn't a permission: someone who holds none of the bundle's files gets
    the same answer as for a bundle that doesn't exist."""
    owner = make_user(("read", "study/scan-042.nii"), ("read", "study/scan-043.nii"))
    r = owner.download_bundle(file_ids=[tree.file("study/scan-042.nii"), tree.file("study/scan-043.nii")])
    assert r.status_code == 200, r.text
    bundle_id = r.json()["bundle_id"]
    assert owner.bundle_status(bundle_id).status_code != 404

    other = make_user()
    assert other.bundle_status(bundle_id).status_code == 404
    assert other.bundle_download(bundle_id).status_code == 404


def test_the_user_who_asked_for_a_bundle_can_fetch_it(make_user, tree):
    """AC-3. Control: the owner's own bundle still downloads once it's ready."""
    owner = make_user(("read", "study/scan-042.nii"), ("read", "study/scan-043.nii"))
    r = owner.download_bundle(file_ids=[tree.file("study/scan-042.nii"), tree.file("study/scan-043.nii")])
    assert r.status_code == 200, r.text
    bundle_id = r.json()["bundle_id"]
    for _ in range(60):
        r = owner.bundle_download(bundle_id)
        if r.status_code != 202:
            break
        time.sleep(1)
    assert r.status_code == 200, r.text
    assert r.json()["result_url"]


def ready_download(owner, bundle_id):
    for _ in range(60):
        r = owner.bundle_download(bundle_id)
        if r.status_code != 202:
            return r
        time.sleep(1)
    return r


def test_a_bundle_is_refused_once_access_to_a_file_in_it_is_revoked(make_user, tree, portal):
    """AC-3. A bundle is built from what its owner could read when they asked; if that access is
    revoked before they fetch it, the archive isn't handed over."""
    owner = make_user(("read", "study/scan-042.nii"), ("read", "study/scan-043.nii"))
    r = owner.download_bundle(file_ids=[tree.file("study/scan-042.nii"), tree.file("study/scan-043.nii")])
    assert r.status_code == 200, r.text
    bundle_id = r.json()["bundle_id"]
    assert ready_download(owner, bundle_id).status_code == 200
    portal.revoke(owner, portal.resource("study/scan-043.nii"), "read")
    assert owner.bundle_download(bundle_id).status_code == 403


# ------------------------------------------------- a grant covers exactly what it names

def test_a_new_instance_grants_its_creator_a_rule_the_portal_accepts(portal):
    """AC-5. The grant made for an instance's creator is written as a literal path, like any other."""
    name = f"acl-test-instance-{uuid.uuid4().hex[:8]}"
    created = portal.admin("POST", "/api/instances/", json={
        "flavour": "dummy", "instance_name": name, "instance_url": "http://dummy.invalid"}).json()
    try:
        grants = portal.admin("GET", "/api/policies/", params={"instance_name": name}).json()["details"]
        assert {(g["resource"], g["action"]) for g in grants} == {("*", "admin")}
    finally:
        portal.admin("DELETE", f"/api/instances/{created['instance']['uuid']}")


def test_a_file_grant_does_not_cover_longer_names(make_user, tree):
    """AC-5. Read on shared/notes.txt gives nothing on shared/notes.txt.secret."""
    user = make_user(("read", "shared/notes.txt"))
    assert user.download_url(tree.file("shared/notes.txt.secret")).status_code == 403


def test_a_file_grant_does_not_allow_creating_longer_names(make_user, tree):
    """AC-5. Write on data/report.csv.bak doesn't allow creating data/report.csv.bak.evil."""
    user = make_user(("write", "data/report.csv.bak"))
    assert user.upload_init(tree.folder("data/"), "report.csv.bak.evil").status_code == 403


def test_a_dot_in_a_grant_is_just_a_dot(make_user, tree):
    """AC-5. Write on data/report.csv.bak doesn't allow writing data/reportXcsv.bak."""
    user = make_user(("write", "data/report.csv.bak"))
    assert user.upload_init(tree.folder("data/"), "reportXcsv.bak").status_code == 403


def test_a_folder_grant_does_not_cover_folders_sharing_its_name(make_user, tree):
    """AC-5. Read on fold/* gives nothing in folder-secret/."""
    user = make_user(("read", "fold/*"))
    assert user.download_url(tree.file("fold/a.txt")).status_code == 200
    assert user.download_url(tree.file("folder-secret/x.txt")).status_code == 403


def test_a_folder_holding_a_file_named_with_a_bracket_can_be_browsed(make_user, tree):
    """AC-1. The page's file tree for brackets/ answers normally and shows only the user's
    file, although the folder also holds brackets/a[b.bin."""
    user = make_user(("read", "brackets/ok.txt"))
    r = user.browse("read", tree.folder("brackets/"))
    assert r.status_code == 200, r.text
    assert browsed(r) == (set(), {"brackets/ok.txt"})


def test_a_grant_on_a_file_named_with_a_bracket_gives_access_to_it(make_user, tree):
    """AC-5. Read on brackets/a[b.bin can be granted, and shows and reads that file."""
    user = make_user(("read", "brackets/a[b.bin"))
    r = user.browse("read", tree.folder("brackets/"))
    assert r.status_code == 200, r.text
    assert browsed(r) == (set(), {"brackets/a[b.bin"})
    file_id = int(next(n["id"] for n in r.json()["assets"]).removeprefix("file-"))
    assert user.download_url(file_id).status_code == 200


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


@pytest.mark.parametrize("parent", ["", "data/"])
def test_a_file_grant_does_not_allow_creating_folders_above_it(make_user, tree, parent):
    """AC-2. Write on data/report.csv.bak doesn't allow creating folders in data/ or at the
    bucket root."""
    user = make_user(("write", "data/report.csv.bak"))
    assert user.create_folder(tree.folder(parent), "made-by-test").status_code == 403


# ------------------------------------------------ listings show only the user's path

def test_a_folder_listing_shows_only_files_the_user_may_read(make_user, tree):
    """AC-1. Listing study/patient-7/ shows summary.csv, not the file beside it."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    r = user.list_folder(tree.folder("study/patient-7/"))
    assert r.status_code == 200, r.text
    assert listed(r) == (set(), {"study/patient-7/summary.csv"})


def test_listings_above_a_file_show_only_the_path_to_it(make_user, tree):
    """AC-1. study/ shows only patient-7/, and the bucket root only study/."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    r = user.list_folder(tree.folder("study/"))
    assert r.status_code == 200, r.text
    assert listed(r) == ({"/study/patient-7/"}, set())
    r = user.list_folder(tree.folder(""))
    assert r.status_code == 200, r.text
    assert listed(r) == ({"/study/"}, set())


@pytest.mark.parametrize("action", ["write", "delete"])
def test_a_listing_for_an_action_shows_what_the_user_may_do_it_to(make_user, tree, action):
    """AC-1. With only write (or delete) on summary.csv, listing study/patient-7/ for that action
    shows that file and not the one beside it, and study/ shows only patient-7/; the listing for
    read refuses."""
    user = make_user((action, "study/patient-7/summary.csv"))
    folder = tree.folder("study/patient-7/")
    r = user.list_folder(folder, access=action)
    assert r.status_code == 200, r.text
    assert listed(r) == (set(), {"study/patient-7/summary.csv"})
    r = user.list_folder(tree.folder("study/"), access=action)
    assert r.status_code == 200, r.text
    assert listed(r) == ({"/study/patient-7/"}, set())
    assert user.list_folder(folder).status_code == 403


# --------------------------------------------------------------------------- end dates

def utc_day(offset: int) -> str:
    return (datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=offset)).isoformat()


def test_a_policy_with_an_end_date_gives_access_until_then(portal, make_user, tree):
    """AC-8. A policy ending tomorrow gives access today, and the person sees when it ends."""
    user = make_user()
    portal.grant(user, portal.resource("study/scan-042.nii"), "read", ends=utc_day(1))
    assert user.download_url(tree.file("study/scan-042.nii")).status_code == 200
    assert [p.get("ends") for p in user.my_policies()] == [utc_day(1)]


def test_a_policy_cannot_end_on_a_date_already_past(portal, make_user):
    """AC-8. It would allow nothing, so the portal refuses it."""
    user = make_user()
    assert portal.try_grant(user, portal.resource("study/scan-042.nii"), "read", ends=utc_day(-1)) is None


# --------------------------------------------------------------------------- exclusions

def test_a_folder_policy_leaves_out_what_it_excludes(portal, make_user, tree):
    """AC-10. Read on study/ leaving out patient-7/: the scans are readable and listed; patient-7/
    and its files aren't."""
    user = make_user()
    portal.grant(user, portal.resource("study/*"), "read", excluded=[portal.resource("study/patient-7/*")])
    assert user.download_url(tree.file("study/scan-042.nii")).status_code == 200
    assert user.download_url(tree.file("study/patient-7/summary.csv")).status_code == 403
    r = user.list_folder(tree.folder("study/"))
    assert r.status_code == 200, r.text
    assert listed(r) == (set(), {"study/scan-042.nii", "study/scan-043.nii"})
    assert [p.get("excluded") for p in user.my_policies()] == [[portal.resource("study/patient-7/*")]]


def test_only_paths_inside_a_folder_policy_can_be_left_out(portal, make_user):
    """AC-10. Leaving out something outside the policy's folder is refused."""
    user = make_user()
    assert portal.try_grant(user, portal.resource("study/*"), "read", excluded=[portal.resource("other/*")]) is None


# --------------------------------------------------------------------------- file types

def test_a_folder_policy_limited_to_file_endings_covers_only_those_files(portal, make_user, tree):
    """AC-6. Read on study/ for .nii files: the scans are readable and listed; the CSVs in patient-7/
    aren't, though the folder can still be browsed."""
    user = make_user()
    portal.grant(user, portal.resource("study/*"), "read", endings=[".NII"])
    assert user.download_url(tree.file("study/scan-042.nii")).status_code == 200
    assert user.download_url(tree.file("study/patient-7/summary.csv")).status_code == 403
    r = user.list_folder(tree.folder("study/patient-7/"))
    assert r.status_code == 200, r.text
    assert listed(r) == (set(), set())
    assert [p.get("endings") for p in user.my_policies()] == [[".nii"]]


def test_only_a_folder_policy_can_be_limited_to_file_endings(portal, make_user):
    """AC-6."""
    user = make_user()
    assert portal.try_grant(user, portal.resource("study/scan-042.nii"), "read", endings=[".nii"]) is None


def test_a_folder_policy_limited_to_kinds_of_data_covers_only_those_kinds(portal, make_user, tree):
    """AC-6. Read on a BIDS dataset for anatomical scans: the T1w is readable, the functional run isn't."""
    user = make_user()
    portal.grant(user, portal.resource("bids/*"), "read", kinds=["anat"])
    assert user.download_url(tree.file("bids/sub-01/anat/sub-01_T1w.nii.gz")).status_code == 200
    assert user.download_url(tree.file("bids/sub-01/func/sub-01_task-rest_bold.nii.gz")).status_code == 403
    assert [p.get("kinds") for p in user.my_policies()] == [["anat"]]


def test_kinds_of_data_need_a_dataset_that_declares_a_standard(portal, make_user):
    """AC-6. study/ isn't a BIDS dataset, so it has no kinds of data."""
    user = make_user()
    assert portal.try_grant(user, portal.resource("study/*"), "read", kinds=["anat"]) is None


# ------------------------------------------------------- access is by name; links run out

def move_in_storage(portal, old, new):
    """Rename or move a file the way it happens outside the portal: in the object store itself."""
    portal.s3.copy_object(Bucket=portal.bucket, CopySource={"Bucket": portal.bucket, "Key": old}, Key=new)
    portal.s3.delete_object(Bucket=portal.bucket, Key=old)
    synced(portal)


def synced(portal):
    """Have the portal pick up what changed in the object store, as put_files does."""
    portal.admin("POST", f"/api/instances/{portal.instance_uuid}/sync", timeout=300).raise_for_status()


def fetch_link(url):
    """
    Fetch a presigned link from the test runner. The link names the storage instance's own address
    (e.g. minio:9000), which only the stack's containers resolve, so the request goes to the store's
    local address with the signed Host header kept, and the signature still holds.
    """
    signed = urlsplit(url)
    local = urlsplit(setting("TEST_S3_URL", "http://localhost:9000"))
    return requests.get(urlunsplit(signed._replace(netloc=local.netloc)), headers={"Host": signed.netloc},
                        timeout=10)


def test_renaming_a_folder_leaves_its_policy_on_the_old_name(make_user, tree, portal):
    """AC-5. Renaming results/ to results-2025/ leaves a policy on results/* behind, and a new file
    at the old path is covered by it again."""
    user = make_user(("read", "ren/results/*"))
    finder = make_user(("read", "ren/*"))
    assert user.download_url(tree.file("ren/results/a.txt")).status_code == 200

    move_in_storage(portal, "ren/results/a.txt", "ren/results-2025/a.txt")
    renamed = Tree(finder).file("ren/results-2025/a.txt")
    assert user.download_url(renamed).status_code == 403
    assert portal.resource("ren/results/*") in {p["resource"] for p in user.my_policies()}

    portal.s3.put_object(Bucket=portal.bucket, Key="ren/results/a.txt", Body=b"new\n")
    synced(portal)
    again = Tree(finder).file("ren/results/a.txt")
    assert user.download_url(again).status_code == 200


def test_moving_a_file_puts_it_under_the_policies_of_its_new_path(make_user, portal):
    """AC-5. A moved file leaves the reach of policies on its old path and comes under those on its new one."""
    before = make_user(("read", "mov/in/*"))
    after = make_user(("read", "mov/out/*"))
    finder = make_user(("read", "mov/*"))

    move_in_storage(portal, "mov/in/x.txt", "mov/out/x.txt")
    moved = Tree(finder).file("mov/out/x.txt")
    assert before.download_url(moved).status_code == 403
    assert after.download_url(moved).status_code == 200


def test_a_download_link_lasts_at_most_15_minutes(make_user, tree):
    """AC-3. A link handed out for one file expires within 15 minutes."""
    user = make_user(("read", "link/a.txt"))
    url = user.download_url(tree.file("link/a.txt")).json()["url"]
    expires = parse_qs(urlsplit(url).query)["X-Amz-Expires"]
    assert 0 < int(expires[0]) <= 15 * 60


def test_a_link_handed_out_keeps_working_after_its_policy_is_removed(make_user, tree, portal):
    """AC-3. Removing a policy stops new links at once; a link given before still works until it expires."""
    user = make_user(("read", "link/a.txt"))
    url = user.download_url(tree.file("link/a.txt")).json()["url"]
    portal.revoke(user, portal.resource("link/a.txt"), "read")

    assert user.download_url(tree.file("link/a.txt")).status_code == 403
    fetched = fetch_link(url)
    assert fetched.status_code == 200
    assert fetched.content == b"link/a.txt\n"


# ---------------------------------- two backend processes: policies are read from the store
# Production runs two backend processes. A policy saved through one must be listed, refused as a
# duplicate and removable through the other. Access decisions already read the store each request;
# the policy pages and the duplicate check read the store too, and a change reloads the
# enforcer's copy first.

def test_a_policy_saved_through_another_backend_is_listed(make_user, portal):
    """AC-8. The policies table, the user's own list, and so end-date reminders, read what's stored."""
    user = make_user()
    portal.store_policy_as_another_backend(user, portal.resource("shared/notes.txt"), "read")
    try:
        listed_for_admin = portal.admin("GET", "/api/policies/", params={"username": user.username}).json()
        assert portal.resource("shared/notes.txt") in {p["resource"] for p in listed_for_admin["details"]}
        assert portal.resource("shared/notes.txt") in {p["resource"] for p in user.my_policies()}
    finally:
        portal.unstore_policy(user, portal.resource("shared/notes.txt"), "read")


def test_a_policy_saved_through_another_backend_is_refused_as_a_duplicate(make_user, portal):
    """AC-5. One policy per person, instance, path and action."""
    user = make_user()
    portal.store_policy_as_another_backend(user, portal.resource("shared/notes.txt"), "read")
    try:
        assert portal.try_grant(user, portal.resource("shared/notes.txt"), "read") is None
    finally:
        portal.unstore_policy(user, portal.resource("shared/notes.txt"), "read")


def test_a_policy_saved_through_another_backend_can_be_removed(make_user, portal):
    """AC-3. Removing a policy works whichever process saved it, and access ends."""
    user = make_user()
    portal.store_policy_as_another_backend(user, portal.resource("shared/notes.txt"), "read")
    try:
        r = portal.admin("DELETE", "/api/policies/", json={
            "user_uuid": user.uuid,
            "instance_uuid": portal.instance_uuid,
            "resource": portal.resource("shared/notes.txt"),
            "action": "read",
        })
        assert r.status_code == 200, r.text
        assert portal.resource("shared/notes.txt") not in {p["resource"] for p in user.my_policies()}
    finally:
        portal.unstore_policy(user, portal.resource("shared/notes.txt"), "read")


def test_a_policy_on_a_path_with_a_bracket_is_listed_and_removed(make_user, portal):
    """AC-5. Paths are literal: a policy on brackets/a[b.bin is listed like any other, and removing
    it works."""
    user = make_user(("read", "brackets/a[b.bin"))
    listed_for_admin = portal.admin("GET", "/api/policies/", params={"username": user.username})
    assert listed_for_admin.status_code == 200, listed_for_admin.text
    assert portal.resource("brackets/a[b.bin") in {p["resource"] for p in listed_for_admin.json()["details"]}

    r = requests.delete(f"{portal.backend}/api/policies/", headers=portal.admin_headers(), timeout=30, json={
        "user_uuid": user.uuid,
        "instance_uuid": portal.instance_uuid,
        "resource": portal.resource("brackets/a[b.bin"),
        "action": "read",
    })
    assert r.status_code == 200, r.text
    assert user.my_policies() == []


# --------------------------------------------- check access: the answer and the reason

def check(caller_headers, portal, user, key, action):
    return requests.get(f"{portal.backend}/api/policies/check", headers=caller_headers, timeout=30, params={
        "username": user.username,
        "instance_name": portal.instance,
        "resource": portal.resource(key),
        "action": action,
    })


def test_check_access_names_the_policy_that_allows_it(make_user, portal):
    """AC-3. Allowed, because of the folder policy that covers the file."""
    user = make_user(("read", "study/*"))
    answer = check(portal.admin_headers(), portal, user, "study/scan-042.nii", "read").json()
    assert answer["allowed"] is True
    assert [(p["resource"], p["action"]) for p in answer["because"]] == [(portal.resource("study/*"), "read")]


def test_check_access_refuses_with_no_reason(make_user, portal):
    """AC-3. Refused: none of the person's policies allows it, and nothing else is listed."""
    user = make_user(("read", "study/*"))
    answer = check(portal.admin_headers(), portal, user, "other/unrelated.txt", "read").json()
    assert answer == {"allowed": False, "shown": None, "because": []}


def test_check_access_says_a_folder_is_shown_without_being_allowed(make_user, portal):
    """AC-1. A folder on the way to a file the person holds is shown in their tree, not allowed."""
    user = make_user(("read", "study/patient-7/summary.csv"))
    answer = check(portal.admin_headers(), portal, user, "study/", "read").json()
    assert (answer["allowed"], answer["shown"]) == (False, True)


def test_check_access_is_refused_to_an_ordinary_user(make_user, portal):
    """AC-3. Only administrators and project managers may check someone's access."""
    user = make_user(("read", "study/*"))
    asker = make_user()
    assert check(asker._headers, portal, user, "study/scan-042.nii", "read").status_code == 403


def test_a_manager_may_check_only_people_in_their_projects(make_user, portal):
    """AC-3. A project manager checks people in a project they manage, on its instances, and no one else."""
    member = make_user(("read", "study/*"))
    outsider = make_user(("read", "study/*"))
    manager = make_user()
    project = f"acl-test-{uuid.uuid4().hex[:8]}"
    portal.admin("POST", "/api/projects", json={"name": project}).raise_for_status()
    try:
        portal.admin("POST", f"/api/projects/{project}/storage-instances", json={"instance_name": portal.instance})
        portal.admin("POST", f"/api/projects/{project}/users", json={"username": member.username})
        portal.admin("POST", f"/api/projects/{project}/managers", json={"username": manager.username})
        assert check(manager._headers, portal, member, "study/scan-042.nii", "read").status_code == 200
        assert check(manager._headers, portal, outsider, "study/scan-042.nii", "read").status_code == 403
    finally:
        portal.admin("DELETE", f"/api/projects/{project}")


# ------------------------------------------- administration scope: what a manager may see

def test_a_manager_lists_only_people_in_their_projects(make_user, portal):
    """AC-3. A project manager sees the people in the projects they manage, not everyone's names."""
    member = make_user()
    outsider = make_user()
    manager = make_user()
    project = f"acl-test-{uuid.uuid4().hex[:8]}"
    portal.admin("POST", "/api/projects", json={"name": project})
    try:
        portal.admin("POST", f"/api/projects/{project}/users", json={"username": member.username})
        portal.admin("POST", f"/api/projects/{project}/managers", json={"username": manager.username})
        listed = requests.get(f"{portal.backend}/api/users/", headers=manager._headers, timeout=30)
        assert listed.status_code == 200, listed.text
        names = {u["username"] for u in listed.json()}
        assert member.username in names
        assert outsider.username not in names
        everyone = {u["username"] for u in portal.admin("GET", "/api/users/").json()}
        assert {member.username, outsider.username} <= everyone
    finally:
        portal.admin("DELETE", f"/api/projects/{project}")
