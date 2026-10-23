"""
The file service's side of the link contract (contract/link-contract.json). The backend's
POSIX connector tests check the same file, so the two sides can't drift apart silently.
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
