"""
Adversarial catalogue: forged and altered tokens, and paths built to escape the root.

Token attacks go through the real key lookup (jwks_key_resolver), with the portal's published key
set served from a stub, so header tricks (kid, jwk, jku) are tested the way they would arrive.
Every case must be refused; none may read the secret outside the root.
See TESTING-STRATEGY.md, layer 5.
"""
import base64
import hashlib
import hmac
import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import jwks_key_resolver
from app.config import Settings
from app.main import create_app

NS = "inn-posix"
FILE = f"{NS}/study/scan.nii.gz"
PORTAL_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ATTACKER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "storage-links-1"


def jwk_of(key, kid=KID):
    return json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {"kid": kid, "alg": "RS256", "use": "sig"}


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def claims(path=FILE, op="read", **overrides):
    now = int(time.time())
    base = {"iss": "inn-portal", "aud": NS, "jti": uuid.uuid4().hex, "iat": now, "exp": now + 60, "op": op, "path": path}
    return base | overrides


def raw_token(header: dict, payload: dict, signature: bytes = b"") -> str:
    return ".".join([b64(json.dumps(header).encode()), b64(json.dumps(payload).encode()), b64(signature)])


@pytest.fixture
def root(tmp_path):
    (tmp_path / "study").mkdir()
    (tmp_path / "study" / "scan.nii.gz").write_bytes(b"governed data")
    return tmp_path


@pytest.fixture
def client(root, monkeypatch):
    # Serve the portal's key set from a stub instead of the network.
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [jwk_of(PORTAL_KEY)]})
    settings = Settings(root=root, namespace=NS, jwks_url="https://portal.invalid/jwks.json")
    return TestClient(create_app(settings, resolve_key=jwks_key_resolver(settings.jwks_url)))


def fetch(client, token, path=FILE):
    return client.get(f"/v1/files/{path}", params={"token": token})


def test_a_genuine_token_works(client):
    token = jwt.encode(claims(), PORTAL_KEY, algorithm="RS256", headers={"kid": KID})
    assert fetch(client, token).status_code == 200


@pytest.mark.parametrize("alg", ["none", "None", "NONE", "nOnE"])
def test_unsigned_tokens_are_refused(client, alg):
    assert fetch(client, raw_token({"alg": alg, "typ": "JWT", "kid": KID}, claims())).status_code == 401


def test_algorithm_confusion_hs256_with_the_public_key_is_refused(client):
    public_pem = PORTAL_KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header, payload = {"alg": "HS256", "typ": "JWT", "kid": KID}, claims()
    signing_input = f"{b64(json.dumps(header).encode())}.{b64(json.dumps(payload).encode())}".encode()
    signature = hmac.new(public_pem, signing_input, hashlib.sha256).digest()
    assert fetch(client, raw_token(header, payload, signature)).status_code == 401


def test_an_embedded_jwk_is_not_trusted(client):
    token = jwt.encode(claims(), ATTACKER_KEY, algorithm="RS256",
                       headers={"kid": KID, "jwk": jwk_of(ATTACKER_KEY)})
    assert fetch(client, token).status_code == 401


def test_a_jku_pointing_elsewhere_is_ignored(client):
    token = jwt.encode(claims(), ATTACKER_KEY, algorithm="RS256",
                       headers={"kid": KID, "jku": "https://attacker.invalid/jwks.json"})
    assert fetch(client, token).status_code == 401


@pytest.mark.parametrize("kid", ["unknown", "../../../../dev/null", "' OR '1'='1", ""])
def test_unknown_or_crafted_kids_are_refused(client, kid):
    token = jwt.encode(claims(), PORTAL_KEY, algorithm="RS256", headers={"kid": kid})
    assert fetch(client, token).status_code == 401


def test_a_token_signed_by_another_key_with_the_right_kid_is_refused(client):
    token = jwt.encode(claims(), ATTACKER_KEY, algorithm="RS256", headers={"kid": KID})
    assert fetch(client, token).status_code == 401


def test_a_token_that_isnt_valid_yet_is_refused(client):
    token = jwt.encode(claims(nbf=int(time.time()) + 3600), PORTAL_KEY, algorithm="RS256", headers={"kid": KID})
    assert fetch(client, token).status_code == 401


def test_claims_altered_after_signing_are_refused(client):
    genuine = jwt.encode(claims(path=f"{NS}/study/other.nii.gz"), PORTAL_KEY, algorithm="RS256", headers={"kid": KID})
    header, _, signature = genuine.split(".")
    altered = ".".join([header, b64(json.dumps(claims()).encode()), signature])
    assert fetch(client, altered).status_code == 401


@pytest.mark.parametrize("garbage", ["", "a.b.c", "....", "x" * 5000, "eyJhbGciOiJSUzI1NiJ9.e30."])
def test_malformed_tokens_are_refused_not_crashed(client, garbage):
    assert fetch(client, garbage).status_code == 401


@pytest.mark.parametrize("path", [
    f"{NS}/%2e%2e/secret.txt",          # percent-encoded traversal (decoded by the router)
    f"{NS}/study/%2e%2e/%2e%2e/secret.txt",
    f"{NS}/..%2fsecret.txt",            # encoded slash
])
def test_encoded_traversal_is_refused(client, root, path):
    (root.parent / "secret.txt").write_bytes(b"SECRET")
    decoded = path.replace("%2e", ".").replace("%2f", "/")
    token = jwt.encode(claims(path=decoded), PORTAL_KEY, algorithm="RS256", headers={"kid": KID})
    r = client.get(f"/v1/files/{path}", params={"token": token})
    assert r.status_code in (400, 403, 404)
    assert b"SECRET" not in r.content


@pytest.mark.parametrize("name", ["%252e%252e", "..\\secret.txt", "．．", "scan.nii.gz​"])
def test_lookalike_names_are_just_names(client, root, name):
    # Double encoding, backslashes, full-width dots and zero-width characters are ordinary file names
    # on POSIX: they must not reach anything outside the root, and here they don't exist.
    path = f"{NS}/study/{name}"
    token = jwt.encode(claims(path=path), PORTAL_KEY, algorithm="RS256", headers={"kid": KID})
    r = client.get(f"/v1/files/{path}", params={"token": token})
    assert r.status_code in (403, 404)
