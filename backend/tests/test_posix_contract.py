"""
The backend's side of the POSIX link contract (storage-gateway/contract/link-contract.json).
The file service's tests check the same file.
"""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from core.services.storage_links import LinkSigner
from core.services.storage_links import signer as signer_module
from core.storage_agents import PosixStorageAgent

CONTRACT_FILE = Path(__file__).resolve().parents[2] / "storage-gateway" / "contract" / "link-contract.json"
if not CONTRACT_FILE.exists():
    pytest.skip("link contract not available (run from the repository root)", allow_module_level=True)
CONTRACT = json.loads(CONTRACT_FILE.read_text())
NS = CONTRACT["namespace"]
SIGNER = LinkSigner(rsa.generate_private_key(public_exponent=65537, key_size=2048))


def agent(handler=lambda request: httpx.Response(204)):
    a = PosixStorageAgent("https://posix.example.org", NS)
    a._signer = SIGNER
    a._client = httpx.Client(transport=httpx.MockTransport(handler))
    return a


def decode(token):
    key = jwt.PyJWK(SIGNER.jwks()["keys"][0]).key
    return jwt.decode(token, key, algorithms=[CONTRACT["algorithm"]], audience=NS, issuer=CONTRACT["issuer"])


def test_issuer_and_algorithm_match():
    assert signer_module.ISSUER == CONTRACT["issuer"]
    assert signer_module.ALGORITHM == CONTRACT["algorithm"]


@pytest.mark.parametrize("item", CONTRACT["resources"], ids=lambda i: i["resource"])
@pytest.mark.parametrize("access,operation", CONTRACT["link_operation_by_access"].items())
def test_links_encode_paths_and_claims_as_agreed(item, access, operation):
    urls, _ = agent().generate_access_link(item["resource"], access, 60)
    parsed = urlparse(urls[0])
    assert parsed.path == item["url_path"]
    claims = decode(parse_qs(parsed.query)["token"][0])
    assert set(CONTRACT["required_claims"]) <= set(claims)
    assert claims["op"] == operation and claims["path"] == item["resource"]


@pytest.mark.parametrize("method", ["HEAD", "DELETE"])
def test_service_calls_use_the_agreed_operation_and_header(method):
    seen = {}

    def handler(request):
        seen["path"] = request.url.raw_path.decode()
        seen["claims"] = decode(request.headers["Authorization"].removeprefix("Bearer "))
        return httpx.Response(200, headers={"Content-Length": "1", "ETag": '"e"',
                                            "Last-Modified": "Wed, 21 Oct 2026 07:28:00 GMT", "Content-Type": "text/plain"})

    item = CONTRACT["resources"][0]
    a = agent(handler)
    head = a.get_object_metadata(item["resource"]) if method == "HEAD" else a.delete_object(item["resource"])
    assert seen["path"] == item["url_path"]
    assert seen["claims"]["op"] == CONTRACT["operation_by_method"][method]
    if method == "HEAD":
        assert set(head) == set(CONTRACT["metadata_headers"].values())


@pytest.mark.parametrize("resource", CONTRACT["refused_resources"])
def test_refused_resources(resource):
    with pytest.raises(ValueError):
        agent().generate_access_link(resource, "read", 60)


@pytest.mark.parametrize("subject", [None, "3f0c1b9e-user"])
def test_links_carry_the_user_as_subject_when_given(subject):
    item = CONTRACT["resources"][0]
    urls, _ = agent().generate_access_link(item["resource"], "read", 60, subject=subject)
    claims = decode(parse_qs(urlparse(urls[0]).query)["token"][0])
    assert claims.get(CONTRACT["subject_claim"]) == subject


@pytest.mark.parametrize("grant", [None, "approval-7"])
def test_links_carry_the_approval_when_given(grant):
    item = CONTRACT["resources"][0]
    urls, _ = agent().generate_access_link(item["resource"], "read", 60, subject="u", grant=grant)
    claims = decode(parse_qs(urlparse(urls[0]).query)["token"][0])
    assert claims.get(CONTRACT["grant_claim"]) == grant
