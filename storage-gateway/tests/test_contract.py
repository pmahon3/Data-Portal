"""
The file service's side of the link contract (contract/link-contract.json). The backend's
POSIX connector tests check the same file, so the two sides can't drift apart silently.

Verifies: PX-1.
"""
import json
import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import ALGORITHMS, OPERATION_BY_METHOD, REQUIRED_CLAIMS
from app.config import Settings
from app.files import BadPath, split_key
from app.main import create_app

CONTRACT = json.loads((Path(__file__).resolve().parents[1] / "contract" / "link-contract.json").read_text())
NS = CONTRACT["namespace"]
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def sign(path, op):
    now = int(time.time())
    return jwt.encode({"iss": CONTRACT["issuer"], "aud": NS, "jti": uuid.uuid4().hex, "iat": now, "exp": now + 60,
                       "op": op, "path": path}, KEY, algorithm=CONTRACT["algorithm"])


def test_operations_algorithm_and_claims_match():
    assert OPERATION_BY_METHOD == CONTRACT["operation_by_method"]
    assert ALGORITHMS == [CONTRACT["algorithm"]]
    assert sorted(REQUIRED_CLAIMS) == sorted(CONTRACT["required_claims"])


@pytest.fixture
def client(tmp_path):
    for item in CONTRACT["resources"]:
        key = item["resource"].split("/", 1)[1]
        (tmp_path / key).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / key).write_text(key)
    settings = Settings(root=tmp_path, namespace=NS, jwks_url="unused", issuer=CONTRACT["issuer"])
    return TestClient(create_app(settings, resolve_key=lambda t: KEY.public_key()))


@pytest.mark.parametrize("item", CONTRACT["resources"], ids=lambda i: i["resource"])
def test_each_encoded_url_reaches_its_resource(client, item):
    r = client.get(item["url_path"], params={"token": sign(item["resource"], "read")})
    assert r.status_code == 200
    assert r.text == item["resource"].split("/", 1)[1]
    head = client.head(item["url_path"], headers={"Authorization": f"Bearer {sign(item['resource'], 'stat')}"})
    assert set(CONTRACT["metadata_headers"]) <= {h.title() if h != "etag" else "ETag" for h in head.headers}


@pytest.mark.parametrize("resource", CONTRACT["refused_resources"])
def test_refused_resources(resource):
    with pytest.raises(BadPath):
        split_key(NS, resource)


def test_bundle_links_follow_the_contract(tmp_path):
    """PX-13."""
    import hashlib

    bundle = CONTRACT["bundle"]
    listing = json.dumps({"folder_name": "", "paths": []})
    path = bundle["path"].format(namespace=NS, grant="g7")
    now = int(time.time())
    token = jwt.encode({"iss": CONTRACT["issuer"], "aud": NS, "jti": "j", "iat": now, "exp": now + 60,
                        "op": bundle["operation"], "path": path, CONTRACT["grant_claim"]: "g7",
                        bundle["list_claim"]: hashlib.sha256(listing.encode()).hexdigest()},
                       KEY, algorithm=CONTRACT["algorithm"])
    asked = []
    app = create_app(Settings(root=tmp_path, namespace=NS, jwks_url="unused"), resolve_key=lambda t: KEY.public_key(),
                     fetch_list=lambda grant, tok: asked.append((grant, tok)) or listing)
    r = TestClient(app).get(bundle["url"].format(namespace=NS, grant="g7"), params={"token": token})
    assert r.status_code == 200 and asked == [("g7", token)]
