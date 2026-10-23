"""The streaming ZIP core: valid archives, exact sizes, any byte range, resume without re-reading."""
import io
import shutil
import struct
import subprocess
import zipfile

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.zipstream import Entry, FileChanged, ZipStream

FILES = {
    "study/scan.nii.gz": bytes(range(256)) * 40,
    "study/über ñ.csv": b"a,b\n1,2\n",
    "empty.txt": b"",
    "deep/er/notes #1.txt": b"x" * 3001,
}


@pytest.fixture
def tree(tmp_path):
    for name, data in FILES.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(data)
    return tmp_path


def entries(root, opened=None, crcs=None):
    result = []
    for i, name in enumerate(FILES):
        path = root / name

        def opener(path=path, name=name):
            if opened is not None:
                opened.append(name)
            return open(path, "rb")

        st_ = path.stat()
        result.append(Entry(name, st_.st_size, st_.st_mtime, opener, crcs[i] if crcs else None))
    return result


def whole(stream):
    return b"".join(stream.iter_bytes())


def test_a_valid_archive_with_every_file(tree):
    stream = ZipStream(entries(tree), chunk_size=500)
    data = whole(stream)
    assert len(data) == stream.size
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None
        assert z.namelist() == list(FILES)
        for name, content in FILES.items():
            assert z.read(name) == content
            assert z.getinfo(name).compress_type == zipfile.ZIP_STORED


@pytest.mark.skipif(shutil.which("unzip") is None, reason="unzip not installed")
def test_unzip_accepts_it(tree, tmp_path_factory):
    out = tmp_path_factory.mktemp("zip") / "a.zip"
    out.write_bytes(whole(ZipStream(entries(tree))))
    result = subprocess.run(["unzip", "-t", str(out)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_same_files_give_the_same_bytes(tree):
    assert whole(ZipStream(entries(tree))) == whole(ZipStream(entries(tree)))


def test_an_empty_archive_is_valid():
    with zipfile.ZipFile(io.BytesIO(whole(ZipStream([])))) as z:
        assert z.namelist() == []


@settings(max_examples=300, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_any_range_matches_the_whole_archive(tree, data):
    reference = whole(ZipStream(entries(tree)))
    known_crcs = data.draw(st.booleans())
    crcs = ZipStream(entries(tree)) if known_crcs else None
    if crcs:
        whole(crcs)
    stream = ZipStream(entries(tree, crcs=crcs.checksums() if crcs else None), chunk_size=data.draw(st.integers(1, 700)))
    start = data.draw(st.integers(0, stream.size - 1))
    end = data.draw(st.integers(start, stream.size - 1))
    assert b"".join(stream.iter_bytes(start, end)) == reference[start:end + 1]


def test_resuming_with_saved_checksums_doesnt_reread_earlier_files(tree):
    first = ZipStream(entries(tree))
    reference = whole(first)
    saved = first.checksums()
    assert all(c is not None for c in saved)

    opened = []
    resumed = ZipStream(entries(tree, opened=opened, crcs=saved))
    start = reference.index(FILES["deep/er/notes #1.txt"]) + 100  # partway through the last file
    assert b"".join(resumed.iter_bytes(start)) == reference[start:]
    assert opened == ["deep/er/notes #1.txt"]


def test_resuming_without_checksums_still_gives_the_right_bytes(tree):
    reference = whole(ZipStream(entries(tree)))
    stream = ZipStream(entries(tree))
    start = stream.size // 2
    assert b"".join(stream.iter_bytes(start)) == reference[start:]


@pytest.mark.parametrize("change", [b"shorter", bytes(range(256)) * 41])
def test_a_file_that_changes_size_while_streaming_is_caught(tree, change):
    stream = ZipStream(entries(tree))
    (tree / "study" / "scan.nii.gz").write_bytes(change)
    with pytest.raises(FileChanged):
        whole(stream)


def test_ranges_outside_the_archive_are_refused(tree):
    stream = ZipStream(entries(tree))
    for start, end in ((-1, 5), (5, 4), (0, stream.size)):
        with pytest.raises(ValueError):
            list(stream.iter_bytes(start, end))


class Zeros(io.RawIOBase):
    """A file of zeros of any size, without using disk."""

    def __init__(self, size):
        self.size, self.pos = size, 0

    def readable(self):
        return True

    def seek(self, offset, whence=0):
        self.pos = offset
        return offset

    def read(self, n=-1):
        n = self.size - self.pos if n < 0 else min(n, self.size - self.pos)
        self.pos += n
        return bytes(n)


def test_zip64_records_hold_files_over_4gb():
    big = 5 * 1024**3
    stream = ZipStream([Entry("big.nii", big, 1.7e9, lambda: Zeros(big), crc32=0x1234ABCD),
                        Entry("after.txt", 3, 1.7e9, lambda: io.BytesIO(b"abc"), crc32=None)])
    tail = b"".join(stream.iter_bytes(stream.size - 400))  # central directory and end records only
    # ZIP64 end of central directory: entry count, directory size and offset
    z64 = tail[tail.rindex(struct.pack("<I", 0x06064B50)):]
    count, _, cd_size, cd_offset = struct.unpack("<QQQQ", z64[24:56])
    assert count == 2
    assert cd_offset > 2**32 and cd_offset + cd_size + 98 == stream.size
    # The big file's central record carries its true size in the ZIP64 extra field
    central = tail[tail.index(b"big.nii") + len(b"big.nii"):]
    header_id, length, uncompressed, compressed, offset = struct.unpack("<HHQQQ", central[:28])
    assert (header_id, length, uncompressed, compressed, offset) == (1, 24, big, big, 0)
