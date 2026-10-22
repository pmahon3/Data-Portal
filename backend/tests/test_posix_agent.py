"""
POSIX storage agent and storage link signing.

The file service on the POSIX machine is mocked with httpx.MockTransport; tokens are checked
against the signer's published public key, as the file service will do.
"""
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from core.services.storage_links import LinkSigner
from core.storage_agents import AVAILABLE_FLAVOURS, PosixStorageAgent, agent_factory

NAMESPACE = "inn-posix"
URL = "https://posix.example.org"


@pytest.fixture(scope="module")
def signer():
    return LinkSigner(rsa.generate_private_key(public_exponent=65537, key_size=2048))


def decode(signer, token):
    """Verify a token the way the file service will: with the published key, for this namespace."""
    key = jwt.PyJWK(signer.jwks()["keys"][0]).key
    return jwt.decode(token, key, algorithms=["RS256"], audience=NAMESPACE, issuer="inn-portal")


def make_agent(signer, handler):
    agent = PosixStorageAgent(URL, NAMESPACE)
    agent._signer = signer
    agent._client = httpx.Client(transport=httpx.MockTransport(handler))
    return agent


def test_posix_is_a_registered_flavour():
    assert AVAILABLE_FLAVOURS["posix"] is PosixStorageAgent
    agent = agent_factory({"flavour": "posix", "agent": {"instance_url": URL + "/", "namespace": NAMESPACE}})
    assert agent.instance_url == URL
    assert agent.config() == {"instance_url": URL, "namespace": NAMESPACE}
    assert agent.fetch_all_buckets() == [NAMESPACE]


@pytest.mark.parametrize("namespace", ["", "  ", "a/b"])
def test_namespace_must_be_a_single_name(namespace):
    with pytest.raises(ValueError):
        PosixStorageAgent(URL, namespace)


@pytest.mark.parametrize("method,operation", [("read", "read"), ("write", "write")])
def test_access_link_names_path_and_operation(signer, method, operation):
    agent = make_agent(signer, lambda request: httpx.Response(500))
    urls, paths = agent.generate_access_link(f"{NAMESPACE}/study 1/scan.nii.gz", method, 900)

    assert paths == [f"{NAMESPACE}/study 1/scan.nii.gz"]
    parsed = urlparse(urls[0])
    assert f"{parsed.scheme}://{parsed.netloc}" == URL
    assert parsed.path == f"/v1/files/{NAMESPACE}/study%201/scan.nii.gz"
    claims = decode(signer, parse_qs(parsed.query)["token"][0])
    assert claims["op"] == operation
    assert claims["path"] == f"{NAMESPACE}/study 1/scan.nii.gz"
    assert claims["exp"] - claims["iat"] == 900
    assert claims["jti"]


def test_each_link_has_its_own_id(signer):
    agent = make_agent(signer, lambda request: httpx.Response(500))
    tokens = [
        parse_qs(urlparse(agent.generate_access_link(f"{NAMESPACE}/a.txt", "read", 60)[0][0]).query)["token"][0]
        for _ in range(2)
    ]
    assert decode(signer, tokens[0])["jti"] != decode(signer, tokens[1])["jti"]


@pytest.mark.parametrize("resource", [
    "other-namespace/a.txt",
    NAMESPACE,
    f"{NAMESPACE}/",
    f"{NAMESPACE}/../etc/passwd",
    f"{NAMESPACE}/a/./b",
    f"{NAMESPACE}/a//b",
    f"{NAMESPACE}//etc/passwd",
])
def test_resources_outside_the_namespace_are_refused(signer, resource):
    agent = make_agent(signer, lambda request: httpx.Response(500))
    with pytest.raises(ValueError):
        agent.generate_access_link(resource, "read", 60)


def test_unknown_method_is_refused(signer):
    agent = make_agent(signer, lambda request: httpx.Response(500))
    with pytest.raises(ValueError):
        agent.generate_access_link(f"{NAMESPACE}/a.txt", "delete", 60)


def test_metadata_has_the_keys_callers_read(signer):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["claims"] = decode(signer, request.headers["Authorization"].removeprefix("Bearer "))
        return httpx.Response(200, headers={
            "Content-Length": "42",
            "ETag": '"abc"',
            "Last-Modified": "Wed, 21 Oct 2026 07:28:00 GMT",
            "Content-Type": "application/octet-stream",
        })

    head = make_agent(signer, handler).get_object_metadata(f"{NAMESPACE}/a.txt")

    assert seen["method"] == "HEAD"
    assert seen["claims"]["op"] == "stat"
    assert head == {
        "ContentLength": 42,
        "ETag": '"abc"',
        "LastModified": datetime(2026, 10, 21, 7, 28, tzinfo=UTC),
        "ContentType": "application/octet-stream",
    }


def test_metadata_for_a_missing_file(signer):
    with pytest.raises(FileNotFoundError):
        make_agent(signer, lambda request: httpx.Response(404)).get_object_metadata(f"{NAMESPACE}/a.txt")


def test_delete_signs_a_delete_token_and_tolerates_missing_files(signer):
    calls = []

    def handler(request):
        claims = decode(signer, request.headers["Authorization"].removeprefix("Bearer "))
        calls.append((request.method, claims["op"], claims["path"]))
        return httpx.Response(404 if claims["path"].endswith("gone.txt") else 204)

    make_agent(signer, handler).delete_objects([f"{NAMESPACE}/a.txt", f"{NAMESPACE}/gone.txt"])

    assert calls == [
        ("DELETE", "delete", f"{NAMESPACE}/a.txt"),
        ("DELETE", "delete", f"{NAMESPACE}/gone.txt"),
    ]


@pytest.mark.parametrize("code,error", [(401, PermissionError), (403, PermissionError), (500, RuntimeError)])
def test_file_service_refusals_become_errors(signer, code, error):
    with pytest.raises(error):
        make_agent(signer, lambda request: httpx.Response(code)).delete_object(f"{NAMESPACE}/a.txt")


def test_connect_requires_a_signing_key(monkeypatch):
    from core.services.storage_links import signer as signer_module

    monkeypatch.delenv(signer_module.KEY_FILE_ENV, raising=False)
    signer_module.get_link_signer.cache_clear()
    with pytest.raises(RuntimeError):
        PosixStorageAgent(URL, NAMESPACE).connect()
    signer_module.get_link_signer.cache_clear()


def test_signer_loads_its_key_from_a_pem_file(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization

    from core.services.storage_links import signer as signer_module

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "links.pem"
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    monkeypatch.setenv(signer_module.KEY_FILE_ENV, str(path))
    signer_module.get_link_signer.cache_clear()
    try:
        loaded = signer_module.get_link_signer()
        token = loaded.sign(NAMESPACE, f"{NAMESPACE}/a.txt", "read", 60)
        assert decode(loaded, token)["path"] == f"{NAMESPACE}/a.txt"
    finally:
        signer_module.get_link_signer.cache_clear()


@pytest.mark.parametrize("operation,ttl", [("list", 60), ("read", 0)])
def test_signer_refuses_bad_requests(signer, operation, ttl):
    with pytest.raises(ValueError):
        signer.sign(NAMESPACE, f"{NAMESPACE}/a.txt", operation, ttl)


def test_public_key_endpoint(signer, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.v0_1.endpoints import storage_links

    app = FastAPI()
    app.include_router(storage_links.router)
    client = TestClient(app)

    monkeypatch.setattr(storage_links, "get_link_signer", lambda: signer)
    response = client.get("/storage-links/jwks.json")
    assert response.status_code == 200
    assert response.json() == signer.jwks()

    def unconfigured():
        raise RuntimeError("not configured")

    monkeypatch.setattr(storage_links, "get_link_signer", unconfigured)
    assert client.get("/storage-links/jwks.json").status_code == 503


def bundle_request(monkeypatch, signer, file_ids):
    """Call the bundle endpoint for a POSIX instance with its database and services faked out."""
    import asyncio
    from types import SimpleNamespace

    from api.v0_1.common.models import BundleCreateRequest
    from api.v0_1.endpoints import s3_endpoints

    agent = make_agent(signer, lambda request: httpx.Response(500))
    files = {i: SimpleNamespace(id=i, bucket=NAMESPACE, key=f"f{i}.nii.gz") for i in file_ids}

    class FakeFileService:
        def __init__(self, session):
            pass

        async def get_files(self, ids):
            return [files[i] for i in ids]

    async def bundler_must_not_be_called(*args, **kwargs):
        raise AssertionError("POSIX files were sent to the bundler")

    monkeypatch.setattr(s3_endpoints, "FileService", FakeFileService)
    monkeypatch.setattr(s3_endpoints, "get_instance_agent", lambda manager, name: ("instance-uuid", agent))
    monkeypatch.setattr(s3_endpoints.bundler_client, "post", bundler_must_not_be_called)
    policy_manager = SimpleNamespace(checker=lambda user, instance: SimpleNamespace(allows=lambda resource, action: True))
    user_manager = SimpleNamespace(get_user_uuid=lambda name: "user-uuid")

    return asyncio.run(s3_endpoints.create_asset_bundle(
        BundleCreateRequest(instance_name="posix", file_ids=list(file_ids)),
        user={"preferred_username": "u1"},
        session=None,
        user_manager=user_manager,
        policy_manager=policy_manager,
        instance_manager=None,
    ))


def test_posix_files_are_never_sent_to_the_bundler(signer, monkeypatch):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refused:
        bundle_request(monkeypatch, signer, [1, 2])
    assert refused.value.status_code == 501


def test_a_single_posix_file_still_downloads_directly(signer, monkeypatch):
    response = bundle_request(monkeypatch, signer, [1])
    assert response.bundle_id == "single-file"
    assert urlparse(response.single_file_url).path == f"/v1/files/{NAMESPACE}/f1.nii.gz"
