"""
Opening a multi-file download's files in batches: each batch is one request to the helper (one
process there), files are handed over in the order the stream reaches them, and any opened but not
sent are closed when the stream ends.

Verifies: PX-14.
"""
import os

import pytest
from fastapi import HTTPException

from app.broker import BatchOpener


class FakeAccess:
    def __init__(self, tmp_path, missing=()):
        self.tmp_path, self.missing, self.batches, self.fds = tmp_path, set(missing), [], []

    def open_read_many(self, token, resources, bundle):
        self.batches.append(list(resources))
        opened = []
        for r in resources:
            if r in self.missing:
                opened.append(HTTPException(status_code=404))
                continue
            (self.tmp_path / r).write_bytes(r.encode())
            fd = os.open(self.tmp_path / r, os.O_RDONLY)
            self.fds.append(fd)
            opened.append(fd)
        return opened


def is_open(fd):
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False


def test_files_are_opened_in_batches_as_the_stream_reaches_them(tmp_path):
    access = FakeAccess(tmp_path)
    paths = [f"f{i}" for i in range(10)]
    with BatchOpener(access, "tok", "ns/g", paths, batch=4) as opener:
        assert [opener.open(p).read() for p in paths] == [p.encode() for p in paths]
    assert access.batches == [paths[0:4], paths[4:8], paths[8:10]]


def test_a_resume_starts_its_batch_where_it_starts(tmp_path):
    access = FakeAccess(tmp_path)
    paths = [f"f{i}" for i in range(10)]
    with BatchOpener(access, "tok", "ns/g", paths, batch=4) as opener:
        opener.open("f6").close()
    assert access.batches == [paths[6:10]]


def test_files_opened_but_not_sent_are_closed(tmp_path):
    access = FakeAccess(tmp_path)
    paths = [f"f{i}" for i in range(10)]
    with BatchOpener(access, "tok", "ns/g", paths, batch=4) as opener:
        opener.open("f0").close()
    assert access.fds and not any(is_open(fd) for fd in access.fds)


def test_a_file_that_failed_to_open_fails_when_reached(tmp_path):
    access = FakeAccess(tmp_path, missing={"f1"})
    paths = ["f0", "f1", "f2"]
    with BatchOpener(access, "tok", "ns/g", paths, batch=4) as opener:
        assert opener.open("f0").read() == b"f0"
        with pytest.raises(HTTPException) as failed:
            opener.open("f1")
        assert failed.value.status_code == 404
        assert opener.open("f2").read() == b"f2"
