"""
R1: POSIX follows the same access rules as object storage (TESTING-STRATEGY.md, layer 5).

The same files and the same grants are set up on an S3 instance (MinIO) and a POSIX instance, and
one user tries the same things on both: download (and fetch the bytes), upload inside and outside a
granted folder, delete, and list a folder. Every outcome must be identical, and as expected.
The S3 side uses its own MinIO bucket and a MinIO user that can see only that bucket, so nothing
the main stack uses is touched. Setup: see conftest.py.
"""
import json
import subprocess
import uuid
from urllib.parse import urlparse

import pytest
import requests

from portal import BACKEND, GATEWAY, NAMESPACE, TIMEOUT, delete_file, download_url, login, root_id

RUN = uuid.uuid4().hex[:6]
BUCKET = f"parity-{RUN}"
FOLDER = f"parity-{RUN}"
FILES = {"a.txt": b"A" * 10, "b.txt": b"B" * 10, "sub/c.txt": b"C" * 10, "d.txt": b"D" * 10}


def mc(*args, stdin=None):
    script = ('mc alias set loc http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && '
              + " ".join(args))
    return subprocess.run(["docker", "exec", "-i", "ams-portal-minio-1", "sh", "-c", script],
                          input=stdin, capture_output=True, text=True)


def via_host(url):
    """MinIO links are signed for minio:9000 (inside Docker); send them to localhost with that Host."""
    parsed = urlparse(url)
    if parsed.netloc == "minio:9000":
        return parsed._replace(netloc="localhost:9000").geturl(), {"Host": "minio:9000"}
    return url, {}


def grant(admin, instance, username, action, resource):
    r = requests.post(f"{BACKEND}/api/policies/", headers=admin, timeout=TIMEOUT, json={
        "username": username, "instance_name": instance, "resource": resource, "action": action})
    assert r.status_code in (200, 201), r.text


@pytest.fixture(scope="module")
def s3_instance(admin):
    if mc("true").returncode != 0:
        pytest.skip("MinIO container not available")
    secret = uuid.uuid4().hex
    policy = {"Version": "2012-10-17", "Statement": [
        # No s3:ListAllMyBuckets, so listing buckets shows only this one and the bucket-name check passes.
        {"Effect": "Allow", "Action": ["s3:*"], "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"]},
    ]}
    def cleanup():
        mc(f"mc rb --force loc/{BUCKET}; mc admin user remove loc {BUCKET}; mc admin policy remove loc {BUCKET}")

    assert mc(f"mc mb loc/{BUCKET}").returncode == 0
    assert mc(f"cat > /tmp/{BUCKET}.json && mc admin policy create loc {BUCKET} /tmp/{BUCKET}.json",
              stdin=json.dumps(policy)).returncode == 0
    assert mc(f"mc admin user add loc {BUCKET} {secret}").returncode == 0
    assert mc(f"mc admin policy attach loc {BUCKET} --user {BUCKET}").returncode == 0
    name = f"s3-parity-{RUN}"
    r = requests.post(f"{BACKEND}/api/instances/", headers=admin, timeout=TIMEOUT, json={
        "flavour": "s3", "instance_name": name, "instance_url": "http://minio:9000",
        "aws_access_key_id": BUCKET, "aws_secret_access_key": secret, "region_name": "us-east-1",
        "project_names": []})
    if r.status_code != 201:
        cleanup()
    assert r.status_code == 201, r.text
    instance_uuid = r.json()["instance"]["uuid"]
    grant(admin, name, "qa-authz-admin", "*", "*")
    yield name
    requests.delete(f"{BACKEND}/api/instances/{instance_uuid}", headers=admin, timeout=TIMEOUT)
    cleanup()


def ensure_folder(headers, instance, bucket, relative):
    r = requests.post(f"{BACKEND}/api/tree/folders/ensure-path", headers=headers, timeout=TIMEOUT, json={
        "instance_name": instance, "bucket": bucket, "parent_id": root_id_for(headers, instance, bucket),
        "relative_path": relative})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def root_id_for(headers, instance, bucket):
    r = requests.get(f"{BACKEND}/api/tree/root", headers=headers, timeout=TIMEOUT,
                     params={"instance_name": instance, "bucket": bucket})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def upload_to(headers, instance, bucket, folder_id, filename, content):
    """Upload through the portal; returns (status of init, file id or None)."""
    init = requests.post(f"{BACKEND}/api/tree/files/upload/init", headers=headers, timeout=TIMEOUT, json={
        "instance_name": instance, "bucket": bucket, "folder_id": folder_id, "filename": filename,
        "content_type": "application/octet-stream"})
    if init.status_code != 200:
        return init.status_code, None
    url, host = via_host(init.json()["url"])
    put = requests.put(url, data=content, headers=host, timeout=TIMEOUT)
    assert put.status_code in (200, 201), put.text
    done = requests.post(f"{BACKEND}/api/tree/files/upload/complete", headers=headers, timeout=TIMEOUT,
                         json={"instance_name": instance, "file_id": init.json()["file_id"]})
    assert done.status_code == 200, done.text
    return 200, init.json()["file_id"]


def outcomes(admin, u1, instance, bucket):
    """Set up the files and grants on one instance, then record everything the user can and can't do."""
    folders = {"": ensure_folder(admin, instance, bucket, FOLDER),
               "sub": ensure_folder(admin, instance, bucket, f"{FOLDER}/sub"),
               "up": ensure_folder(admin, instance, bucket, f"{FOLDER}/up")}
    ids = {}
    for name, content in FILES.items():
        folder, _, filename = name.rpartition("/")
        status, ids[name] = upload_to(admin, instance, bucket, folders[folder], filename, content)
        assert status == 200
    base = f"{bucket}/{FOLDER}"
    for action, resource in (("read", f"{base}/a.txt"), ("read", f"{base}/sub/*"),
                             ("delete", f"{base}/d.txt"), ("write", f"{base}/up/*")):
        grant(admin, instance, "qa-authz-u1", action, resource)

    result = {}
    for name in FILES:
        r = download_url(u1, instance, ids[name])
        result[f"download {name}"] = r.status_code
        if r.status_code == 200:
            url, host = via_host(r.json()["url"])
            result[f"bytes {name}"] = requests.get(url, headers=host, timeout=TIMEOUT).content == FILES[name]
    result["upload into up/"], new_id = upload_to(u1, instance, bucket, folders["up"], "new.txt", b"new")
    result["upload outside up/"], _ = upload_to(u1, instance, bucket, folders[""], "new.txt", b"new")
    listing = requests.get(f"{BACKEND}/api/tree/{folders['']}", headers=u1, timeout=TIMEOUT,
                           params={"instance_name": instance, "bucket": bucket})
    result["list folder"] = (listing.status_code, sorted(f["name"] for f in listing.json().get("files", []))
                             if listing.status_code == 200 else None)
    result["delete a.txt"] = delete_file(u1, instance, ids["a.txt"]).status_code
    result["delete d.txt"] = delete_file(u1, instance, ids["d.txt"]).status_code

    for name, file_id in [*ids.items(), ("up/new.txt", new_id)]:
        if file_id and name != "d.txt":
            delete_file(admin, instance, file_id)
    return result


EXPECTED = {
    "download a.txt": 200, "bytes a.txt": True,
    "download b.txt": 403,
    "download sub/c.txt": 200, "bytes sub/c.txt": True,
    "download d.txt": 403,
    "upload into up/": 200,
    "upload outside up/": 403,
    "delete a.txt": 403,
    "delete d.txt": 200,
}


def test_posix_follows_the_same_rules_as_object_storage(admin, instance, s3_instance):
    u1 = login("qa-authz-u1")
    on_s3 = outcomes(admin, u1, s3_instance, BUCKET)
    on_posix = outcomes(admin, u1, instance, NAMESPACE)
    differences = {k: (on_s3.get(k), on_posix.get(k)) for k in set(on_s3) | set(on_posix) if on_s3.get(k) != on_posix.get(k)}
    assert differences == {}, f"S3 vs POSIX differ: {differences}"
    # The listing is compared for parity only: this branch is based on !166, where a folder listing
    # still shows names the user can't open (INN-294, fixed in !164). With !164 in the base, the user
    # sees only a.txt and d.txt; add ("list folder": (200, ["a.txt", "d.txt"])) to EXPECTED then.
    assert {k: v for k, v in on_posix.items() if k != "list folder"} == EXPECTED
