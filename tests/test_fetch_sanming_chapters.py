import hashlib, json
from pathlib import Path
import pytest
from scripts.fetch_sanming_chapters import (
    parse_chapter_list, bootstrap_snapshot, ChapterEntry,
    ManifestClosedLoopError, build_canonical_tar, build_and_publish_snapshot,
    read_active_snapshot, materialization_status, restore_responses,
)

def test_parse_requires_383_contiguous():
    text = "\n".join(f"{i}. 章{i}\thttps://x/{i}.html" for i in range(1, 383))
    with pytest.raises(ValueError, match="383"): parse_chapter_list(text)
    full = text + "\n383. 章383\thttps://x/383.html\n"
    es = parse_chapter_list(full)
    assert len(es) == 383 and [e.index for e in es] == list(range(1, 384))
def test_parse_rejects_duplicate_url_and_index():
    dup = "1. a\thttps://x/1\n1. b\thttps://x/2\n2. c\thttps://x/1\n"
    with pytest.raises(ValueError, match="(duplicate url|duplicate index)"): parse_chapter_list(dup)
def test_bootstrap_merges_80_plus_303_to_383(tmp_path):
    legacy = tmp_path / "legacy"; legacy.mkdir()
    for i in range(1, 81): (legacy / f"raw_{i:03d}_章{i}.txt").write_text(f"T{i}", encoding="utf-8")
    fetched = [{"chapter_index": i, "title": f"章{i}", "url": f"u{i}", "extracted_text_sha256": "e"*64, "response_body_sha256": "r"*64, "extractor_sha256": "x"*64, "normalized_page_title": f"章{i}", "response_body_status": "archived", "provenance_level": "full", "encoding": "utf-8"} for i in range(81, 384)]
    chapter_list = [ChapterEntry(index=i, title=f"章{i}", url=f"u{i}") for i in range(1, 384)]
    snap = bootstrap_snapshot(legacy, chapter_list, fetched)
    assert sorted(snap["ids"]) == list(range(1, 384)) and len(snap["records"]) == 383
    for r in snap["records"]:
        for k in ("encoding", "response_body_status", "provenance_level", "extracted_text_sha256"): assert k in r

def _records_for(entries, status="archived", prov="full", text="T", body=b"B"):
    return [{"chapter_index": e.index, "title": e.title, "url": e.url, "response_body_sha256": hashlib.sha256(body).hexdigest(), "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "extractor_sha256": "x"*64, "normalized_page_title": e.title, "response_body_status": status, "provenance_level": prov, "encoding": "utf-8", "extracted_text": text, "response_body": body, "ok": True} for e in entries]

def _publish_one(tmp_path, entries=None, text="T", body=b"B"):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = entries or [ChapterEntry(81, "卷六·论命", "u1")]
    def factory(entries): return _records_for(entries, text=text, body=body)
    formal = tmp_path / "formal"; store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=factory, archive_root=store)
    return formal, store, read_active_snapshot(formal)["snapshot_sha256"]

def test_publish_writes_exact_bytes_and_verifies(tmp_path):
    text = "第一段。\n第二段。\n"; formal, store, sha = _publish_one(tmp_path, text=text)
    f = formal / "source_snapshots" / sha / "extracted" / "raw_081.txt"
    assert f.read_bytes() == text.encode("utf-8")
def test_publish_recomputes_hashes_from_actual_bytes(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    e = ChapterEntry(81, "卷六·论命", "u1")
    def bad(entries, **kw): recs = _records_for(entries, text="T", body=b"B"); recs[0]["extracted_text_sha256"] = "0"*64; return recs
    with pytest.raises(ManifestClosedLoopError, match="extracted"): build_and_publish_snapshot([e], tmp_path / "f", records_factory=bad, archive_root=tmp_path / "s")
def test_publish_leaves_unmaterialized_then_restore_materializes(tmp_path):
    formal, store, sha = _publish_one(tmp_path)
    assert materialization_status(formal, sha) == "unmaterialized"
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
def test_pointer_and_manifest_sha_are_file_bytes(tmp_path):
    formal, store, sha = _publish_one(tmp_path)
    man = json.loads((formal / "source_snapshots" / sha / "source_manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((formal / "source_snapshots" / sha / "RESPONSE_ARCHIVE_POINTER.json").read_bytes()).hexdigest() == man["response_archive_pointer_sha256"]
    act = json.loads((formal / "active_source_snapshot.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((formal / "source_snapshots" / sha / "source_manifest.json").read_bytes()).hexdigest() == act["source_manifest_sha256"]
def test_idempotent_reuse_verifies_all_identity_fields(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1")]
    formal = tmp_path / "formal"; store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=lambda e: _records_for(e), archive_root=store)
    sha1 = read_active_snapshot(formal)["snapshot_sha256"]
    ptr_file = formal / "source_snapshots" / sha1 / "RESPONSE_ARCHIVE_POINTER.json"
    ptr_file.write_text('{"snapshot_sha256": "0"*64}', encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError, match="pointer"): build_and_publish_snapshot(entries, formal, records_factory=lambda e: _records_for(e), archive_root=store)
def test_restore_requires_exact_member_set(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1"), ChapterEntry(82, "卷六·论人", "u2")]
    formal = tmp_path / "formal"; store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=lambda e: _records_for(e), archive_root=store)
    sha = read_active_snapshot(formal)["snapshot_sha256"]
    snap_dir = formal / "source_snapshots" / sha
    # P0-1：构造真正多余成员（raw_083.html 不在 manifest），并同步更新 pointer/manifest 及 active pointer 的 SHA，
    # 确保上游身份门（active pointer -> manifest SHA -> archive pointer SHA）全部通过，member set 校验失败
    data = build_canonical_tar({"responses/raw_081.html": b"B", "responses/raw_082.html": b"B", "responses/raw_083.html": b"B"})
    tampered_uri = str(store / f"tampered_{hashlib.sha256(data).hexdigest()[:8]}.tar")
    Path(tampered_uri).write_bytes(data)
    ptr = json.loads((snap_dir / "RESPONSE_ARCHIVE_POINTER.json").read_text(encoding="utf-8"))
    ptr["archive_sha256"] = hashlib.sha256(data).hexdigest(); ptr["archive_size"] = len(data); ptr["response_count"] = 3; ptr["archive_uri"] = tampered_uri
    (snap_dir / "RESPONSE_ARCHIVE_POINTER.json").write_text(json.dumps(ptr, ensure_ascii=False, indent=2), encoding="utf-8")
    man = json.loads((snap_dir / "source_manifest.json").read_text(encoding="utf-8"))
    man["response_archive_pointer_sha256"] = hashlib.sha256((snap_dir / "RESPONSE_ARCHIVE_POINTER.json").read_bytes()).hexdigest()
    (snap_dir / "source_manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    # P0-6：同步更新 active pointer 的 manifest SHA，使上游身份门通过
    (formal / "active_source_snapshot.json").write_text(json.dumps({"snapshot_sha256": sha, "source_manifest_sha256": hashlib.sha256((snap_dir / "source_manifest.json").read_bytes()).hexdigest()}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError, match="member set"): restore_responses(formal, sha, archive_root=store)
def test_restore_idempotent_skip_when_consistent(tmp_path):
    # 中优：restore 幂等——已一致则跳过，重复调用不失败
    formal, store, sha = _publish_one(tmp_path)
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
def test_restore_rejects_active_pointer_drift(tmp_path):
    # P0-6：active pointer 的 manifest SHA 漂移 -> 拒绝（上游身份门）
    formal, store, sha = _publish_one(tmp_path)
    act = json.loads((formal / "active_source_snapshot.json").read_text(encoding="utf-8"))
    act["source_manifest_sha256"] = "0" * 64
    (formal / "active_source_snapshot.json").write_text(json.dumps(act, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError, match="active pointer"): restore_responses(formal, sha, archive_root=store)
def test_restore_rejects_active_pointer_drift_after_materialized(tmp_path):
    # P0-1：已物化后篡改 active pointer，再次 restore 也必须拒绝（闭环校验在幂等 return 之前）
    formal, store, sha = _publish_one(tmp_path)
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
    act = json.loads((formal / "active_source_snapshot.json").read_text(encoding="utf-8"))
    act["source_manifest_sha256"] = "0" * 64
    (formal / "active_source_snapshot.json").write_text(json.dumps(act, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError, match="active pointer"): restore_responses(formal, sha, archive_root=store)
def test_restore_atomic_no_partial_on_failure(tmp_path, monkeypatch):
    formal, store, sha = _publish_one(tmp_path)
    snap_dir = formal / "source_snapshots" / sha
    def _boom(*a, **k): raise OSError("disk full")
    monkeypatch.setattr("scripts.fetch_sanming_chapters.os.replace", _boom)
    with pytest.raises(OSError): restore_responses(formal, sha, archive_root=store)
    assert not (snap_dir / "responses").exists() and not (snap_dir / "responses.tmp").exists()
def test_restore_rejects_unsafe_member(tmp_path):
    from scripts.fetch_sanming_chapters import _safe_member_name
    for bad in ("../evil", "responses/../evil", "/abs", "responses\\raw.html", "other/x"):
        with pytest.raises(ManifestClosedLoopError): _safe_member_name(bad)
    assert _safe_member_name("responses/raw_081.html") == "raw_081.html"