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