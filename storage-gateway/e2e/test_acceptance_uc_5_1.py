"""
Use case 5.1, storing PII, walked end to end on a POSIX instance: one test per step of the use case's
main flow and postconditions (strategy, section 5.1). Steps not built yet are known-failing, each
naming what it waits on; the markers are strict, so a step that starts working fails until its marker
comes off.

Accepts: UC-5.1.
"""
import subprocess
import time

import pytest
import requests

from portal import BACKEND, GATEWAY_CONTAINER, NAMESPACE, TIMEOUT, data_read, download_url, root_id, unique_name, upload

CONTENT = b"identifiable scan, for the acceptance walk"


@pytest.fixture(scope="module")
def stored(admin, instance):
    started = time.time()
    file_id, key = upload(admin, instance, unique_name(".nii"), CONTENT)
    return {"id": file_id, "key": key, "since": started}


def test_step_1_the_researcher_signs_in(admin):
    assert admin["Authorization"].startswith("Bearer ")


@pytest.mark.xfail(strict=True, reason="TLS terminates in the file service on a real machine "
                   "(DS-tls-in-service, SA-12); the local stack runs plain HTTP")
def test_step_2_data_is_uploaded_over_an_encrypted_channel(admin, instance):
    r = requests.post(f"{BACKEND}/api/tree/files/upload/init", headers=admin, timeout=TIMEOUT, json={
        "instance_name": instance, "bucket": NAMESPACE, "folder_id": root_id(admin, instance), "filename": unique_name()})
    assert r.json().get("url", "").startswith("https://")


@pytest.mark.xfail(strict=True, reason="format, metadata and consent validation on upload isn't built "
                   "(strategy 5.1 step 3; STD-1 for BIDS)")
def test_step_3_format_metadata_and_consent_are_validated(admin, instance):
    r = requests.post(f"{BACKEND}/api/tree/files/upload/init", headers=admin, timeout=TIMEOUT, json={
        "instance_name": instance, "bucket": NAMESPACE, "folder_id": root_id(admin, instance), "filename": unique_name(),
        "consent": None})
    assert r.status_code in (400, 422)  # an upload without consent metadata is held, not accepted


def test_step_4_data_is_stored_with_access_control(stored, u1, instance):
    assert data_read(stored["key"]) == CONTENT
    assert download_url(u1, instance, stored["id"]).status_code in (403, 404)


@pytest.mark.xfail(strict=True, reason="notifications are built on their own branch, feat/notifications "
                   "(NT-1), not yet merged into this stack's base")
def test_step_5_the_researcher_is_told_the_data_is_stored(admin, stored):
    r = requests.get(f"{BACKEND}/api/notifications/", headers=admin, timeout=TIMEOUT)
    assert r.status_code == 200 and any(str(stored["id"]) in str(n) for n in r.json())


def test_postcondition_only_authorized_users_can_read_it(stored, admin, instance):
    url = download_url(admin, instance, stored["id"]).json()["url"]
    assert requests.get(url, timeout=TIMEOUT).content == CONTENT


def test_postcondition_the_upload_is_recorded_with_the_person(stored):
    logs = subprocess.run(["docker", "logs", "--since", f"{stored['since']:.3f}", GATEWAY_CONTAINER],
                          capture_output=True, text=True, timeout=30)
    placed = [line for line in (logs.stdout + logs.stderr).splitlines()
              if "placed link=" in line and stored["key"] in line]
    assert placed and "user=" in placed[0]
