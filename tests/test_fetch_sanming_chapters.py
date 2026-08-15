import pytest
from scripts.fetch_sanming_chapters import parse_chapter_list, bootstrap_snapshot, ChapterEntry

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