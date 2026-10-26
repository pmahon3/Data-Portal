"""
A running portal, driven only through its public interfaces, for black-box tests.

Tests and their setup reach the portal through:
  - the portal API: as the portal admin for setup (instances, sync, policies), and as
    ordinary users for every action under test;
  - Keycloak's admin API, to create and remove throwaway users;
  - the object store behind the test instance, to create the test files and to see what
    happened to them.
Nothing here imports backend code or reads the portal's databases, so the same tests run
unchanged against any version of the backend.

Settings come from the environment. The defaults fit the local docker stack (local/), so
sourcing local/.env is enough there:
  BACKEND_BASE_URL                        http://localhost:8000
  KEYCLOAK_DOMAIN                         http://localhost:8080
  KEYCLOAK_REALM                          ams-portal
  KEYCLOAK_UI_CLIENT_ID                   ams-portal-ui
  KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD Keycloak master-realm admin (creates test users)
  PORTAL_ADMIN_USER, PORTAL_ADMIN_PASSWORD portal admin in the realm (admin / admin123)
  TEST_INSTANCE                           storage instance to test on (qa-instance)
  TEST_S3_URL                             object store behind it (http://localhost:9000)
  MINIO_ROOT_USER, MINIO_ROOT_PASSWORD    object store credentials
"""
import os
import time
import uuid
from urllib.parse import unquote, urlsplit

import boto3
import requests

TIMEOUT = 30


def setting(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or default


class StackUnavailable(Exception):
    """The stack isn't running or isn't configured; tests skip rather than fail."""


class Portal:
    """One test run's view of the stack: a fresh bucket on the test instance."""

    def __init__(self):
        self.backend = setting("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
        self.keycloak = setting("KEYCLOAK_DOMAIN", "http://localhost:8080").rstrip("/")
        self.realm = setting("KEYCLOAK_REALM", "ams-portal")
        self.client_id = setting("KEYCLOAK_UI_CLIENT_ID", "ams-portal-ui")
        self.kc_admin = (setting("KEYCLOAK_ADMIN", "admin"), setting("KEYCLOAK_ADMIN_PASSWORD", "admin123"))
        self.portal_admin = (setting("PORTAL_ADMIN_USER", "admin"), setting("PORTAL_ADMIN_PASSWORD", "admin123"))
        self.instance = setting("TEST_INSTANCE", "qa-instance")
        self.bucket = f"acl-test-{uuid.uuid4().hex[:8]}"
        self._tokens: dict[str, tuple[float, str]] = {}

        try:
            requests.get(f"{self.backend}/api/health", timeout=5).raise_for_status()
            self.admin_headers()
        except requests.RequestException as error:
            raise StackUnavailable(f"portal or Keycloak not reachable: {error}") from error

        instances = self.admin("GET", "/api/instances/").json()["instances"]
        match = [i for i in instances if i["name"] == self.instance]
        if not match:
            raise StackUnavailable(f"no storage instance named '{self.instance}' (set TEST_INSTANCE)")
        self.instance_uuid = match[0]["uuid"]

        if not setting("MINIO_ROOT_USER"):
            raise StackUnavailable("object store credentials not set (source local/.env)")
        self.s3 = boto3.client(
            "s3",
            endpoint_url=setting("TEST_S3_URL", "http://localhost:9000"),
            aws_access_key_id=setting("MINIO_ROOT_USER"),
            aws_secret_access_key=setting("MINIO_ROOT_PASSWORD"),
            region_name="us-east-1",
        )

    # ------------------------------------------------------------------ tokens

    def _token(self, realm: str, client_id: str, username: str, password: str) -> str:
        cached = self._tokens.get(f"{realm}/{username}")
        if cached and time.monotonic() - cached[0] < 60:
            return cached[1]
        r = requests.post(
            f"{self.keycloak}/realms/{realm}/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": client_id,
                  "username": username, "password": password},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        token = r.json()["access_token"]
        self._tokens[f"{realm}/{username}"] = (time.monotonic(), token)
        return token

    def admin_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token(self.realm, self.client_id, *self.portal_admin)}"}

    def _kc_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token('master', 'admin-cli', *self.kc_admin)}"}

    def admin(self, method: str, path: str, **kwargs) -> requests.Response:
        """A portal API call as the portal admin. Setup only; it must succeed."""
        kwargs.setdefault("timeout", TIMEOUT)
        r = requests.request(method, f"{self.backend}{path}", headers=self.admin_headers(), **kwargs)
        r.raise_for_status()
        return r

    # ------------------------------------------------------------------- files

    def resource(self, key: str) -> str:
        """The policy resource for a key in the test bucket."""
        return f"{self.bucket}/{key}"

    def put_files(self, files: dict[str, bytes]) -> None:
        """Create the test bucket with these files and let the portal discover them."""
        self.s3.create_bucket(Bucket=self.bucket)
        for key, body in files.items():
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=body)
        self.admin("POST", f"/api/instances/{self.instance_uuid}/sync", timeout=300)

    def stored(self, prefix: str = "") -> dict[str, bytes]:
        """What the object store holds under a prefix, read directly."""
        found = {}
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                found[obj["Key"]] = self.s3.get_object(Bucket=self.bucket, Key=obj["Key"])["Body"].read()
        return found

    def remove_bucket(self) -> None:
        """Remove the test bucket from the object store. The portal's file tree may keep rows
        for it, since a sync only adds and updates; nobody holds a grant on them."""
        for key in self.stored():
            self.s3.delete_object(Bucket=self.bucket, Key=key)
        self.s3.delete_bucket(Bucket=self.bucket)

    # ------------------------------------------------------------------- users

    def create_user(self) -> "User":
        """A new Keycloak user with the realm's ordinary user role and no grants."""
        username = f"acl-test-{uuid.uuid4().hex[:10]}"
        password = uuid.uuid4().hex
        base = f"{self.keycloak}/admin/realms/{self.realm}"
        r = requests.post(f"{base}/users", headers=self._kc_headers(), timeout=TIMEOUT, json={
            "username": username, "enabled": True, "emailVerified": True,
            "email": f"{username}@example.test", "firstName": "Access", "lastName": "Test",
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        })
        r.raise_for_status()
        user_id = r.headers["Location"].rsplit("/", 1)[1]
        role = requests.get(f"{base}/roles/user", headers=self._kc_headers(), timeout=TIMEOUT)
        if role.status_code == 200:
            requests.post(f"{base}/users/{user_id}/role-mappings/realm", headers=self._kc_headers(),
                          timeout=TIMEOUT, json=[role.json()]).raise_for_status()
        return User(self, username, password, user_id)

    def delete_user(self, user: "User") -> None:
        for resource, action in list(user.grants):
            self.revoke(user, resource, action)
        requests.delete(f"{self.keycloak}/admin/realms/{self.realm}/users/{user.uuid}",
                        headers=self._kc_headers(), timeout=TIMEOUT)

    # ---------------------------------------------------------------- policies

    def grant(self, user: "User", resource: str, action: str) -> str:
        """Add a policy through the policy API, as an administrator would. Returns the
        resource as the portal stored it."""
        r = requests.post(f"{self.backend}/api/policies/", headers=self.admin_headers(), timeout=TIMEOUT, json={
            "username": user.username, "instance_name": self.instance,
            "resource": resource, "action": action})
        assert r.status_code in (200, 201), f"the portal refused a grant of {action} on {resource!r}: {r.status_code} {r.text}"
        stored = r.json()["details"][0]["resource"]
        user.grants.append((stored, action))
        return stored

    def revoke(self, user: "User", resource: str, action: str) -> None:
        requests.delete(f"{self.backend}/api/policies/", headers=self.admin_headers(), timeout=TIMEOUT, json={
            "user_uuid": user.uuid, "instance_uuid": self.instance_uuid,
            "resource": resource, "action": action})
        user.grants.remove((resource, action))


class User:
    """An ordinary portal user. Every method is one call to the portal's file API."""

    def __init__(self, portal: Portal, username: str, password: str, user_uuid: str):
        self.portal = portal
        self.username = username
        self.password = password
        self.uuid = user_uuid
        self.grants: list[tuple[str, str]] = []

    @property
    def _headers(self) -> dict:
        p = self.portal
        return {"Authorization": f"Bearer {p._token(p.realm, p.client_id, self.username, self.password)}"}

    @property
    def _where(self) -> dict:
        return {"instance_name": self.portal.instance, "bucket": self.portal.bucket}

    def _call(self, method: str, path: str, **kwargs) -> requests.Response:
        return requests.request(method, f"{self.portal.backend}/api/tree{path}",
                                headers=self._headers, timeout=TIMEOUT, **kwargs)

    def root(self) -> requests.Response:
        return self._call("GET", "/root", params=self._where)

    def list_folder(self, folder_id: int) -> requests.Response:
        return self._call("GET", f"/{folder_id}", params=self._where)

    def browse(self, access: str, folder_id: int) -> requests.Response:
        """A folder's children in the file tree the web page shows, for one action."""
        return self._call("GET", f"/dashboard/{self.portal.instance_uuid}/children",
                          params={"access": access, "parent_id": folder_id})

    def download_url(self, file_id: int) -> requests.Response:
        return self._call("GET", f"/files/{file_id}/download-url", params=self._where)

    def upload_init(self, folder_id: int, filename: str) -> requests.Response:
        return self._call("POST", "/files/upload/init",
                          json={**self._where, "folder_id": folder_id, "filename": filename})

    def folder_upload_init(self, parent_id: int, relative_paths: list[str], on_conflict: str) -> requests.Response:
        return self._call("POST", "/folders/upload/init", json={
            **self._where, "parent_id": parent_id, "on_conflict": on_conflict,
            "files": [{"relative_path": p, "size": 1} for p in relative_paths]})

    def create_folder(self, parent_id: int, name: str) -> requests.Response:
        return self._call("POST", "/folders", json={**self._where, "parent_id": parent_id, "name": name})

    def delete_file(self, file_id: int) -> requests.Response:
        return self._call("DELETE", f"/files/{file_id}", params=self._where)

    def delete_folder(self, folder_id: int) -> requests.Response:
        return self._call("DELETE", f"/folders/{folder_id}", params=self._where)

    def download_bundle(self, file_ids: list[int] = (), folder_ids: list[int] = ()) -> requests.Response:
        return self._call("POST", "/bundle/zip", json={
            "instance_name": self.portal.instance, "file_ids": list(file_ids),
            "folder_ids": list(folder_ids), "folder_name": ""})


class Tree:
    """Finds folder and file ids by browsing as a user who can read every file it's asked
    about, so tests never depend on the listing behaviour they test."""

    def __init__(self, browser: User):
        self.browser = browser
        self._folders: dict[str, int] = {}
        self._children: dict[int, dict] = {}

    def _list(self, folder_id: int) -> dict:
        if folder_id not in self._children:
            r = self.browser.list_folder(folder_id)
            r.raise_for_status()
            self._children[folder_id] = r.json()
        return self._children[folder_id]

    def folder(self, path: str) -> int:
        """The id of a folder, given as "" for the bucket root or "a/b/" below it."""
        if path not in self._folders:
            if path == "":
                r = self.browser.root()
                r.raise_for_status()
                self._folders[path] = r.json()["id"]
            else:
                parent = path.rstrip("/").rpartition("/")[0]
                parent = f"{parent}/" if parent else ""
                children = self._list(self.folder(parent))["folders"]
                self._folders[path] = next(f["id"] for f in children if f["full_path"] == f"/{path}")
        return self._folders[path]

    def file(self, key: str) -> int:
        folder = key.rpartition("/")[0]
        files = self._list(self.folder(f"{folder}/" if folder else ""))["files"]
        return next(f["id"] for f in files if f["key"] == key)


def listed(response: requests.Response) -> tuple[set[str], set[str]]:
    """The folder paths and file keys in a folder listing."""
    body = response.json()
    return {f["full_path"] for f in body["folders"]}, {f["key"] for f in body["files"]}


def browsed(response: requests.Response) -> tuple[set[str], set[str]]:
    """The folder paths and file keys in a page-tree response."""
    nodes = [n["li_attr"] for n in response.json()["assets"]]
    return ({n["full_path"] for n in nodes if n["type"] == "folder"},
            {n["key"] for n in nodes if n["type"] == "file"})


def key_in_url(url: str, bucket: str) -> str:
    """The object key a presigned URL points at."""
    path = unquote(urlsplit(url).path).lstrip("/")
    return path[len(bucket) + 1:] if path.startswith(f"{bucket}/") else path
