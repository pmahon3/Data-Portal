"""
Retake the screenshots in docs/images/ from the local stack (local/), with made-up example data.

    set -a; . local/.env; set +a
    uv run --with playwright==1.61.0 --with boto3 --with requests python docs/images/capture.py
    (first time: uv run --with playwright==1.61.0 playwright install chromium)

It puts an example study (bucket "study", file names only, no real data) on the test instance,
uploads one folder through the portal so the admin has a notification, then signs in to the UI
as the portal admin and captures each page. Settings as in backend/tests/portal_stack.py, plus
FRONTEND_URL (http://localhost:3000). Run it after a UI change and commit the images it rewrites.
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend" / "tests"))
from portal_stack import Portal, setting  # noqa: E402

FRONTEND = setting("FRONTEND_URL", "http://localhost:3000").rstrip("/")
BUCKET = "study"
FILES = [
    "sub-01/anat/sub-01_T1w.nii.gz",
    "sub-01/func/sub-01_task-rest_bold.nii.gz",
    "sub-02/anat/sub-02_T1w.nii.gz",
    "protocol.pdf",
]
UPLOADED = ["sub-03/anat/sub-03_T1w.nii.gz", "sub-03/anat/sub-03_T1w.json"]


def seed(portal: Portal) -> None:
    """The example study, plus one folder uploaded through the portal (which notifies the admin)."""
    portal.bucket = BUCKET
    if BUCKET not in [b["Name"] for b in portal.s3.list_buckets()["Buckets"]]:
        portal.s3.create_bucket(Bucket=BUCKET)
    for key in FILES:
        portal.s3.put_object(Bucket=BUCKET, Key=key, Body=b"example")
    portal.admin("POST", f"/api/instances/{portal.instance_uuid}/sync", timeout=300)

    # Upload once: a rerun would add a notification each time.
    if portal.s3.list_objects_v2(Bucket=BUCKET, Prefix=UPLOADED[0]).get("KeyCount"):
        return
    root = portal.admin("GET", "/api/tree/root", params={"instance_name": portal.instance, "bucket": BUCKET}).json()
    init = requests.post(f"{portal.backend}/api/tree/folders/upload/init", headers=portal.admin_headers(), json={
        "instance_name": portal.instance, "bucket": BUCKET, "parent_id": root["id"], "on_conflict": "replace",
        "files": [{"relative_path": p, "content_type": "application/octet-stream", "size": 7} for p in UPLOADED],
    }, timeout=30)
    init.raise_for_status()
    for plan in init.json()["files"]:
        # The URL names the object store as the backend sees it (minio:9000 in local/); the
        # signature covers that host, so send it there through the published port.
        url = urlsplit(plan["url"])
        local = urlsplit(setting("TEST_S3_URL", "http://localhost:9000"))
        requests.put(url._replace(netloc=local.netloc).geturl(), data=b"example",
                     headers={"Host": url.netloc}, timeout=30).raise_for_status()
    portal.admin("POST", "/api/tree/folders/upload/complete", json={
        "instance_name": portal.instance, "file_ids": [f["file_id"] for f in init.json()["files"]]})


def row(page, text):
    return page.locator(".tree-node-label", has=page.locator(".tree-node-text", has_text=text)).first


def expand(page, text):
    row(page, text).locator(".tree-row-chevron").click()
    page.wait_for_timeout(500)


def capture(portal: Portal) -> None:
    user, password = portal.portal_admin
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page.goto(FRONTEND)
        page.locator(".navbar-button").click()
        page.fill("#username", user)
        page.fill("#password", password)
        page.click("#kc-login")
        page.wait_for_url(f"{FRONTEND}/app**")

        # Notifications: the bell and its list.
        page.get_by_role("button", name=re.compile(r"^notifications")).click()
        page.wait_for_timeout(500)
        page.screenshot(path=HERE / "notifications.png", clip={"x": 680, "y": 0, "width": 600, "height": 360})
        page.keyboard.press("Escape")

        # The navbar is fixed and would cover the top of anything captured lower down.
        hide_navbar = "nav.navbar { position: static !important; }"

        # Policies: choosing the resource from the file tree, with the preview.
        page.goto(f"{FRONTEND}/app/policy-management")
        page.add_style_tag(content=hide_navbar)
        page.get_by_placeholder("alice").fill("alice")
        page.get_by_role("combobox").first.select_option(portal.instance)
        page.get_by_role("button", name="Choose from the tree").click()
        expand(page, BUCKET)
        row(page, "sub-01").click()
        row(page, "protocol.pdf").click()
        page.locator(".pm-card").first.screenshot(path=HERE / "policy-from-tree.png")

        # Assets: an instance's Download tab.
        page.goto(f"{FRONTEND}/app/asset-management")
        page.add_style_tag(content=hide_navbar)
        card = page.locator(".ec-card", has_text=portal.instance)
        card.locator(".ec-header").click()
        expand(page, BUCKET)
        expand(page, "sub-01")
        card.screenshot(path=HERE / "asset-download.png")

        # Assets: selecting a folder under a filter selects only the files it shows (AC-4).
        search = card.get_by_placeholder("Filter paths, e.g. *.csv")
        search.fill("*T1w.nii.gz")
        search.press("Enter")
        page.wait_for_timeout(1500)
        if not row(page, "sub-01").is_visible():  # the search keeps folders open that were open
            expand(page, BUCKET)
        row(page, "sub-01").click()
        if not row(page, "sub-01_T1w.nii.gz").is_visible():
            expand(page, "anat")
        card.screenshot(path=HERE / "asset-filtered-selection.png")

        # Storage connections (secret fields are masked by the page).
        page.goto(f"{FRONTEND}/app/storage-management")
        page.add_style_tag(content=hide_navbar)
        page.wait_for_timeout(1500)
        page.locator(".admin-content, main").first.screenshot(path=HERE / "storage-management.png")
        browser.close()


if __name__ == "__main__":
    portal = Portal()
    seed(portal)
    capture(portal)
    print("wrote", ", ".join(sorted(p.name for p in HERE.glob("*.png"))))
