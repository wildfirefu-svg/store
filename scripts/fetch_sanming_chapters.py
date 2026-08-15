"""Sanming Tonghui 383-chapter catalog parser + 80/303 bootstrap snapshot.

Stage 2 of the completion plan: parse the canonical chapter list (exactly 383
contiguous chapters 1..383), then bootstrap a snapshot record set by merging
the 80 historically-imported chapters (legacy raw text, no upstream response
body) with 303 fetched chapters (with archived response bodies).
"""
from __future__ import annotations
import io, json, os, re, tarfile, hashlib
from dataclasses import dataclass
from pathlib import Path

_LINE_RE = re.compile(r"^\s*(\d{1,3})\.\s*(.+?)\t(\S+)$")
EXPECTED_COUNT = 383

@dataclass(frozen=True)
class ChapterEntry:
    index: int; title: str; url: str

def parse_chapter_list(text: str) -> list[ChapterEntry]:
    entries, urls, indexes = [], set(), set()
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        m = _LINE_RE.match(line)
        if not m: raise ValueError(f"malformed line: {line!r}")
        idx, title, url = int(m.group(1)), m.group(2), m.group(3)
        if not title: raise ValueError(f"empty title at {idx}")
        if url in urls: raise ValueError(f"duplicate url at {idx}: {url}")
        if idx in indexes: raise ValueError(f"duplicate index: {idx}")
        urls.add(url); indexes.add(idx)
        entries.append(ChapterEntry(index=idx, title=title, url=url))
    if len(entries) != EXPECTED_COUNT or sorted(e.index for e in entries) != list(range(1, EXPECTED_COUNT + 1)):
        raise ValueError(f"expected {EXPECTED_COUNT} contiguous chapters 1..{EXPECTED_COUNT}, got {len(entries)}")
    return entries

def _legacy_index(name: str) -> int | None:
    m = re.match(r"raw_(\d+)_", name); return int(m.group(1)) if m else None

def bootstrap_snapshot(legacy_raw_dir: Path, chapter_list, fetched_records):
    records, ids = [], []
    legacy_by_idx = {}
    for p in Path(legacy_raw_dir).glob("raw_*.txt"):
        idx = _legacy_index(p.name)
        if idx is not None: legacy_by_idx[idx] = p
    for entry in [c for c in chapter_list if c.index <= 80]:
        p = legacy_by_idx.get(entry.index)
        if p is None: raise ValueError(f"legacy raw missing for index {entry.index}")
        data = p.read_bytes()
        records.append({"chapter_index": entry.index, "title": entry.title, "url": entry.url, "extracted_text_sha256": hashlib.sha256(data).hexdigest(), "response_body_sha256": None, "response_body_status": "historical_unavailable", "extractor_sha256": None, "normalized_page_title": None, "provenance_level": "historical_text_only", "encoding": "utf-8"})
        ids.append(entry.index)
    for rec in fetched_records:
        for k in ("response_body_status", "provenance_level", "encoding"):
            if k not in rec: raise ValueError(f"fetched record missing manifest field {k}")
        records.append(rec); ids.append(rec["chapter_index"])
    if sorted(ids) != list(range(1, 384)): raise ValueError("bootstrap must yield exactly 383 unique contiguous ids")
    return {"ids": ids, "records": records}

def build_canonical_tar(responses: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:", format=tarfile.GNU_FORMAT) as tf:
        for name in sorted(responses, key=lambda n: int(re.search(r"raw_(\d+)\.html", n).group(1))):
            data = responses[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(data); info.mtime = 0; info.uid = 0; info.gid = 0; info.uname = ""; info.gname = ""; info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()

class ManifestClosedLoopError(RuntimeError): pass

def snapshot_canonical_sha(records) -> str:
    canon = json.dumps([{"i": r["chapter_index"], "t": r["title"], "u": r["url"], "e": r["extracted_text_sha256"], "r": r["response_body_sha256"], "x": r["extractor_sha256"], "p": r["normalized_page_title"], "enc": r.get("encoding"), "rbs": r.get("response_body_status"), "pl": r.get("provenance_level")} for r in records], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()

def _file_sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def _safe_member_name(name: str) -> str:
    if "\\" in name or name.startswith("/"): raise ManifestClosedLoopError(f"unsafe tar member: {name!r}")
    parts = name.split("/")
    if len(parts) != 2 or parts[0] != "responses" or not parts[1] or ".." in parts: raise ManifestClosedLoopError(f"tar member outside responses/: {name!r}")
    return parts[1]

def build_and_publish_snapshot(entries, formal_dir, records_factory, archive_root):
    import shutil
    staging = formal_dir / ".staging"
    if staging.exists(): shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    records = records_factory(entries)
    (staging / "extracted").mkdir()
    responses = {}
    for rec in records:
        t = rec["extracted_text"]; b = rec.get("response_body")
        tex = t.encode("utf-8")
        if hashlib.sha256(tex).hexdigest() != rec.get("extracted_text_sha256"): raise ManifestClosedLoopError(f"extracted_text_sha256 mismatch (actual bytes) for chapter {rec['chapter_index']}")
        if b is not None and hashlib.sha256(b).hexdigest() != rec.get("response_body_sha256"): raise ManifestClosedLoopError(f"response_body_sha256 mismatch (actual bytes) for chapter {rec['chapter_index']}")
        out = staging / "extracted" / f"raw_{rec['chapter_index']:03d}.txt"; out.write_bytes(tex)
        if hashlib.sha256(out.read_bytes()).hexdigest() != rec.get("extracted_text_sha256"): raise ManifestClosedLoopError(f"extracted file bytes drift after write for chapter {rec['chapter_index']}")
        if b is not None: responses[f"responses/raw_{rec['chapter_index']:03d}.html"] = b
    archive_bytes = build_canonical_tar(responses) if responses else b""
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_path = archive_root / f"{archive_sha}.tar"; archive_path.write_bytes(archive_bytes)
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != archive_sha: raise ManifestClosedLoopError("archive readback mismatch")
    snap_sha = snapshot_canonical_sha(records)
    pointer = {"snapshot_sha256": snap_sha, "archive_format": "tar", "archive_sha256": archive_sha, "archive_size": len(archive_bytes), "archive_uri": f"{archive_root}/{archive_sha}.tar", "response_count": len(responses)}
    ptr_file = staging / "RESPONSE_ARCHIVE_POINTER.json"; ptr_file.write_text(json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
    pointer_sha = _file_sha256(ptr_file)
    manifest = {"snapshot_sha256": snap_sha, "response_archive_pointer_sha256": pointer_sha, "chapters": [{k: r[k] for k in ("chapter_index", "title", "url", "response_body_sha256", "response_body_status", "provenance_level", "encoding", "extracted_text_sha256", "extractor_sha256", "normalized_page_title")} for r in records]}
    man_file = staging / "source_manifest.json"; man_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if json.loads(man_file.read_text(encoding="utf-8")) != manifest: raise ManifestClosedLoopError("manifest readback mismatch")
    snapshots = formal_dir / "source_snapshots"; snapshots.mkdir(parents=True, exist_ok=True)
    target = snapshots / snap_sha
    if target.exists():
        existing = json.loads((target / "source_manifest.json").read_text(encoding="utf-8"))
        if existing != manifest: shutil.rmtree(staging, ignore_errors=True); raise ManifestClosedLoopError("snapshot exists with drifted manifest")
        if _file_sha256(target / "RESPONSE_ARCHIVE_POINTER.json") != pointer_sha: shutil.rmtree(staging, ignore_errors=True); raise ManifestClosedLoopError("snapshot exists with drifted pointer file bytes")
        shutil.rmtree(staging, ignore_errors=True)
    else: os.replace(str(staging), str(target))
    manifest_sha = _file_sha256(target / "source_manifest.json")
    pointer_file = formal_dir / "active_source_snapshot.json"
    tmp_p = pointer_file.with_suffix(".tmp")
    tmp_p.write_text(json.dumps({"snapshot_sha256": snap_sha, "source_manifest_sha256": manifest_sha}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp_p), str(pointer_file))
    return True

def read_active_snapshot(formal_dir):
    p = formal_dir / "active_source_snapshot.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

def restore_responses(formal_dir, snap_sha, archive_root):
    import shutil
    snap_dir = formal_dir / "source_snapshots" / snap_sha
    # P0-6/P0-1：先验证 active pointer 闭环（放在幂等 return 之前，已物化也不能绕过）：
    # active.snapshot_sha256 -> manifest 文件字节 SHA -> archive pointer 文件字节 SHA -> archive bytes SHA/size
    act = read_active_snapshot(formal_dir)
    if not act or act.get("snapshot_sha256") != snap_sha: raise ManifestClosedLoopError("active pointer snapshot_sha256 mismatch")
    if _file_sha256(snap_dir / "source_manifest.json") != act.get("source_manifest_sha256"): raise ManifestClosedLoopError("active pointer source_manifest_sha256 != manifest file bytes SHA")
    man_file = snap_dir / "source_manifest.json"; man = json.loads(man_file.read_text(encoding="utf-8"))
    ptr_file = snap_dir / "RESPONSE_ARCHIVE_POINTER.json"
    if _file_sha256(ptr_file) != man.get("response_archive_pointer_sha256"): raise ManifestClosedLoopError("pointer file bytes SHA mismatch with manifest")
    ptr = json.loads(ptr_file.read_text(encoding="utf-8"))
    if ptr["snapshot_sha256"] != snap_sha: raise ManifestClosedLoopError("pointer snapshot mismatch")
    data = Path(ptr["archive_uri"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != ptr["archive_sha256"]: raise ManifestClosedLoopError("archive sha mismatch")
    if len(data) != ptr["archive_size"]: raise ManifestClosedLoopError("archive size mismatch")
    # 幂等：已存在且与 manifest 一致则跳过；不一致则拒绝，避免 Windows 重复 os.replace 失败
    responses_dir = snap_dir / "responses"
    if responses_dir.exists():
        if materialization_status(formal_dir, snap_sha) == "materialized": return
        raise ManifestClosedLoopError("responses/ exists but not consistent with manifest (refuse)")
    by_idx = {c["chapter_index"]: c for c in man["chapters"]}
    expected = {"responses/raw_%03d.html" % c["chapter_index"] for c in man["chapters"] if c.get("response_body_status") == "archived"}
    tmp_dir = snap_dir / "responses.tmp"
    if tmp_dir.exists(): shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
            members = tf.getmembers()
            actual = set(m.name for m in members)
            if actual != expected: raise ManifestClosedLoopError(f"archive member set mismatch: got {actual - expected} extra / {expected - actual} missing")
            if len(members) != ptr["response_count"]: raise ManifestClosedLoopError(f"archive member count {len(members)} != {ptr['response_count']}")
            for m in members:
                if not m.isfile(): raise ManifestClosedLoopError(f"archive member not a file: {m.name}")
                base = _safe_member_name(m.name)
                if not re.fullmatch(r"raw_\d{3}\.html", base): raise ManifestClosedLoopError(f"member name not raw_<3digits>.html: {base!r}")
                idx = int(base[4:7]); ch = by_idx.get(idx)
                if ch is None or ch.get("response_body_status") != "archived": raise ManifestClosedLoopError(f"member {m.name} not an archived chapter")
                content = tf.extractfile(m).read()
                if hashlib.sha256(content).hexdigest() != ch.get("response_body_sha256"): raise ManifestClosedLoopError(f"member {m.name} sha mismatch")
                (tmp_dir / base).write_bytes(content)
        os.replace(str(tmp_dir), str(snap_dir / "responses"))
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True); raise

def materialization_status(formal_dir, snap_sha):
    snap_dir = formal_dir / "source_snapshots" / snap_sha
    if not (snap_dir / "source_manifest.json").exists(): return "unmaterialized"
    man = json.loads((snap_dir / "source_manifest.json").read_text(encoding="utf-8"))
    for ch in man["chapters"]:
        if ch.get("response_body_status") == "archived":
            p = snap_dir / "responses" / f"raw_{ch['chapter_index']:03d}.html"
            if not p.exists(): return "unmaterialized"
            if hashlib.sha256(p.read_bytes()).hexdigest() != ch.get("response_body_sha256"): return "unmaterialized"
    return "materialized"