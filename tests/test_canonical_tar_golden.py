import hashlib, tarfile, io
from scripts.fetch_sanming_chapters import build_canonical_tar

FIXTURE = {"responses/raw_081.html": b"<html>B1</html>", "responses/raw_082.html": b"<html>B2</html>", "responses/raw_083.html": b"<html>B3</html>"}
GOLDEN_ARCHIVE_SIZE = 10240
GOLDEN_SHA256 = "1bca7aeb1ce38ef0b5069180b5aba1d214914eaf49840925a595c86470c49009"

def test_canonical_tar_golden_sha_and_size():
    data = build_canonical_tar(FIXTURE)
    assert len(data) == GOLDEN_ARCHIVE_SIZE
    assert hashlib.sha256(data).hexdigest() == GOLDEN_SHA256
def test_canonical_tar_layout():
    data = build_canonical_tar(FIXTURE)
    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
    names = tf.getnames(); assert names == sorted(names)
    for m in tf.getmembers():
        assert not m.isdir() and m.mtime == 0 and m.uid == 0 and m.gid == 0 and m.uname == "" and m.gname == "" and m.mode == 0o644