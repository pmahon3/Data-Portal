"""
Property-based and stateful tests (TESTING-STRATEGY.md, layers 2 and 4).

Properties hold for generated inputs, not chosen examples:
- whatever key is asked for, the file service never opens anything outside its root;
- byte ranges agree with a reference model written from RFC 9110 §14;
- changing any signed claim without re-signing makes the token fail;
- a sequence of uploads, downloads, ranged downloads, metadata reads and deletes always agrees
  with an in-memory model of the files.
"""
import base64
import json
import os
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, rule

from app.auth import check_token
from app.config import Settings
from app.files import BadPath, Root, parse_range, split_key
from app.main import create_app

NS = "inn-posix"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def sign(path, op, **overrides):
    now = int(time.time())
    claims = {"iss": "inn-portal", "aud": NS, "jti": uuid.uuid4().hex, "iat": now, "exp": now + 300,
              "op": op, "path": path} | overrides
    return jwt.encode(claims, KEY, algorithm="RS256")


# --- Paths never leave the root ---

# Names built from the characters that cause trouble: dots, slashes, backslashes, percent signs,
# NUL, and Unicode look-alikes, plus the names of things planted in the tree.
TRICKY = st.sampled_from([".", "..", "/", "\\", "%", "2e", "2f", "\x00", "．", "∕", "~", " ",
                          "study", "scan.nii.gz", "link", "outer", "in"])
KEYS = st.lists(TRICKY, min_size=1, max_size=8).map("".join)


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    base = tmp_path_factory.mktemp("tree")
    root, outside = base / "root", base / "outside"
    (root / "study").mkdir(parents=True)
    outside.mkdir()
    (root / "study" / "scan.nii.gz").write_bytes(b"inside")
    (outside / "scan.nii.gz").write_bytes(b"OUTSIDE")
    (root / "study" / "link").symlink_to(outside / "scan.nii.gz")
    (root / "outer").symlink_to(outside)
    (root / "in").symlink_to(root / "study")
    inside = {(p.stat().st_dev, p.stat().st_ino) for p in root.rglob("*") if p.is_file() and not p.is_symlink()}
    return root, inside


@settings(max_examples=2000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(key=KEYS)
def test_no_key_opens_anything_outside_the_root(tree, key):
    root, inside = tree
    try:
        fd, st_ = Root(root).open_file(split_key(NS, f"{NS}/{key}"))
    except (BadPath, FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return
    os.close(fd)
    assert (st_.st_dev, st_.st_ino) in inside


# --- Byte ranges agree with RFC 9110 §14 ---

def reference_range(header, size):
    """
    Independent model of RFC 9110 §14: 'whole', 'unsatisfiable', or (start, end) inclusive.
    Unknown units must be ignored; malformed, invalid or multiple ranges may be ignored (we do);
    only a well-formed range that doesn't overlap the file is unsatisfiable.
    """
    import re

    if not header:
        return "whole"
    m = re.fullmatch(r"\s*bytes\s*=\s*(\d*)-(\d*)\s*", header, flags=re.IGNORECASE)
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return "whole"
    first, last = m.group(1), m.group(2)
    if first == "":
        if int(last) == 0 or size == 0:
            return "unsatisfiable"
        return (max(0, size - int(last)), size - 1)
    if last != "" and int(last) < int(first):
        return "whole"
    if int(first) >= size:
        return "unsatisfiable"
    return (int(first), size - 1 if last == "" else min(int(last), size - 1))


NUMBER = st.one_of(st.integers(0, 3000).map(str), st.just(""), st.sampled_from(["-1", "1e3", " 5", "x"]))
HEADERS = st.one_of(
    st.none(),
    st.builds(lambda a, b: f"bytes={a}-{b}", NUMBER, NUMBER),
    st.builds(lambda a, b, c, d: f"bytes={a}-{b},{c}-{d}", NUMBER, NUMBER, NUMBER, NUMBER),
    st.sampled_from(["bytes=", "items=0-1", "bytes 0-1", "BYTES=0-1", "bytes=--1"]),
    st.text(max_size=20),
)


@settings(max_examples=3000)
@given(header=HEADERS, size=st.integers(0, 2500))
def test_byte_ranges_match_the_rfc_model(header, size):
    expected = reference_range(header, size)
    try:
        got = parse_range(header, size)
    except ValueError:
        got = "unsatisfiable"
    assert (got if got is not None else "whole") == expected


# --- Tampering with a signed token always breaks it ---

def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@settings(max_examples=300)
@given(claim=st.sampled_from(["iss", "aud", "jti", "iat", "exp", "op", "path"]), value=st.text(min_size=1, max_size=30))
def test_changing_any_claim_without_resigning_fails(claim, value):
    path = f"{NS}/study/scan.nii.gz"
    token = sign(path, "read")
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    assume(str(claims[claim]) != value)
    claims[claim] = value
    forged = ".".join([header, b64(json.dumps(claims).encode()), signature])
    with pytest.raises(HTTPException) as refused:
        check_token(forged, lambda t: KEY.public_key(), namespace=NS, issuer="inn-portal", path=path, method="GET")
    assert refused.value.status_code in (401, 403)


# --- A random sequence of operations agrees with a model ---

NAMES = st.sampled_from(["a.bin", "b.csv", "deep/c.nii.gz", "deep/er/d.txt"])
CONTENT = st.binary(max_size=3000)


class FileServiceMachine(RuleBasedStateMachine):
    """The file service against a dict of path -> bytes."""

    names = Bundle("names")

    def __init__(self):
        super().__init__()
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        settings_ = Settings(root=__import__("pathlib").Path(self.tmp.name), namespace=NS, jwks_url="unused",
                             chunk_size=257)
        self.client = TestClient(create_app(settings_, resolve_key=lambda t: KEY.public_key()))
        self.model: dict[str, bytes] = {}

    def teardown(self):
        self.tmp.cleanup()

    def url(self, name):
        return f"/v1/files/{NS}/{name}"

    @rule(target=names, name=NAMES, content=CONTENT)
    def upload(self, name, content):
        path = f"{NS}/{name}"
        r = self.client.put(self.url(name), params={"token": sign(path, "write")}, content=content)
        assert r.status_code == (200 if name in self.model else 201)
        self.model[name] = content
        return name

    @rule(name=names)
    def download(self, name):
        r = self.client.get(self.url(name), params={"token": sign(f"{NS}/{name}", "read")})
        if name in self.model:
            assert r.status_code == 200 and r.content == self.model[name]
        else:
            assert r.status_code == 404

    @rule(name=names, start=st.integers(0, 3500))
    def resume(self, name, start):
        r = self.client.get(self.url(name), params={"token": sign(f"{NS}/{name}", "read")},
                            headers={"Range": f"bytes={start}-"})
        if name not in self.model:
            assert r.status_code == 404
        elif start < len(self.model[name]):
            assert r.status_code == 206 and r.content == self.model[name][start:]
        else:
            assert r.status_code == 416

    @rule(name=names)
    def metadata(self, name):
        r = self.client.head(self.url(name), headers={"Authorization": f"Bearer {sign(f'{NS}/{name}', 'stat')}"})
        if name in self.model:
            assert r.status_code == 200 and int(r.headers["content-length"]) == len(self.model[name])
        else:
            assert r.status_code == 404

    @rule(name=names)
    def delete(self, name):
        r = self.client.delete(self.url(name), headers={"Authorization": f"Bearer {sign(f'{NS}/{name}', 'delete')}"})
        assert r.status_code == (204 if name in self.model else 404)
        self.model.pop(name, None)

    @invariant()
    def no_temporary_files_left_behind(self):
        leftovers = [n for _, _, files in os.walk(self.tmp.name) for n in files if n.startswith(".upload-")]
        assert not leftovers


FileServiceMachine.TestCase.settings = settings(max_examples=60, stateful_step_count=30, deadline=None)
test_file_service_agrees_with_a_model = FileServiceMachine.TestCase
