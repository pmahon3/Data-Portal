"""
Rotating the portal's signing key: the file service looks keys up by ID in the portal's published
set, so a link signed with the previous key keeps working while the portal still publishes it.

Verifies: PX-1.
"""
import json

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import jwks_key_resolver
from app.config import Settings
from app.main import create_app
from tests.tokens import NS, sign

OLD, NEW = (rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))


def jwk(key, kid):
    return json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {"kid": kid, "alg": "RS256", "use": "sig"}


def client(tmp_path, monkeypatch, published):
    (tmp_path / "a.txt").write_bytes(b"data")
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": published})
    settings = Settings(root=tmp_path, namespace=NS, jwks_url="https://portal.invalid/jwks.json")
    return TestClient(create_app(settings, resolve_key=jwks_key_resolver(settings.jwks_url)))


def get(c, key, kid):
    token = jwt.encode(jwt.decode(sign(f"{NS}/a.txt", "read"), options={"verify_signature": False}), key,
                       algorithm="RS256", headers={"kid": kid})
    return c.get(f"/v1/files/{NS}/a.txt", params={"token": token})


def test_a_link_signed_with_the_previous_key_works_while_it_is_published(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch, [jwk(NEW, "new"), jwk(OLD, "old")])
    assert get(c, NEW, "new").status_code == 200
    assert get(c, OLD, "old").status_code == 200


def test_it_stops_working_once_the_previous_key_is_dropped(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch, [jwk(NEW, "new")])
    assert get(c, OLD, "old").status_code == 401
