"""Production: fetch sanmingtonghui chapters 81-383 from 44414.cn, build the
383-chapter snapshot, publish + materialize. Caches fetched pages to disk so a
crash does not re-fetch. Web scraping is an independently-approved entry point."""
from __future__ import annotations
import hashlib, json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(r"G:\project\agent")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_sanming_chapters import (
    ChapterEntry, parse_chapter_list,
    build_and_publish_snapshot, read_active_snapshot, restore_responses,
)

BOOK = ROOT / "knowledge_base" / "classic_texts" / "sanmingtonghui"
CACHE = ROOT / ".tmp" / "sanming_fetch_cache"
CACHE.mkdir(parents=True, exist_ok=True)
FORMAL = BOOK / "formal"
ARCHIVE = BOOK / ".snapshot_archive"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_EXTRACTOR_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_FOOTER = re.compile(r"Powered by|Copyright|All rights Reserved|大唐创业起居注|药性歌括四百味|在线国学网首页|投诉建议|收藏网站")


def _extract_content(html: str, idx: int, title: str) -> str:
    # attempt 1: <div class="content"> with <p> paragraphs (cleaner structure)
    m = re.search(r'<div[^>]*class="content"[^>]*>(.*?)</div>', html, flags=re.S)
    if m:
        paras = [re.sub(r"<[^>]+>", "", p).replace("&nbsp;", " ").strip()
                 for p in re.findall(r"<p[^>]*>(.*?)</p>", m.group(1), flags=re.S)]
        paras = [p for p in paras if len(p) > 8]
        if paras and sum(len(p) for p in paras) > 200:
            return "\n\n".join(paras)
    # attempt 2: body text after the chapter-title heading, cut at footer markers
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", body).replace("&nbsp;", " ")
    lines = [l.strip() for l in text.splitlines()]
    mark = None
    for i, l in enumerate(lines):
        if l == title:
            mark = i
    if mark is None:
        for i, l in enumerate(lines):
            if title in l and len(l) <= len(title) + 12:
                mark = i
    if mark is None:
        raise ValueError(f"chapter {idx}: heading not found")
    out = []
    for l in lines[mark + 1:]:
        if _FOOTER.search(l):
            break
        if len(l) > 8:
            out.append(l)
    if not out:
        raise ValueError(f"chapter {idx}: no body text after heading")
    return "\n\n".join(out)


def _fetch(url: str, idx: int, title: str, retries: int = 3) -> tuple[bytes, str]:
    cache_f = CACHE / f"ch_{idx:03d}.html"
    if cache_f.exists():
        html = cache_f.read_bytes().decode("utf-8", errors="replace")
        return html.encode("utf-8"), _extract_content(html, idx, title)
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            raw = urllib.request.urlopen(req, timeout=30).read()
            html = raw.decode("utf-8", errors="replace")
            text = _extract_content(html, idx, title)
            cache_f.write_bytes(html.encode("utf-8"))
            return raw, text
        except Exception as e:
            last = e
            time.sleep(2 * attempt)
    raise RuntimeError(f"chapter {idx} fetch failed after {retries}: {last!r}")


def main():
    text = (BOOK / "chapter_list.txt").read_text(encoding="utf-8")
    entries = parse_chapter_list(text)  # exactly 383

    legacy_by_idx = {}
    for p in BOOK.glob("raw_*.txt"):
        m = re.match(r"raw_(\d+)_", p.name)
        if m:
            legacy_by_idx[int(m.group(1))] = p

    records = []
    for e in entries:
        if e.index <= 80:
            p = legacy_by_idx.get(e.index)
            if p is None:
                raise ValueError(f"legacy raw missing for index {e.index}")
            data = p.read_bytes()
            records.append({"chapter_index": e.index, "title": e.title, "url": e.url,
                            "extracted_text_sha256": hashlib.sha256(data).hexdigest(),
                            "response_body_sha256": None, "response_body_status": "historical_unavailable",
                            "extractor_sha256": None, "normalized_page_title": None,
                            "provenance_level": "historical_text_only", "encoding": "utf-8",
                            "extracted_text": data.decode("utf-8", errors="replace"), "response_body": None})
        else:
            raw, txt = _fetch(e.url, e.index, e.title)
            records.append({"chapter_index": e.index, "title": e.title, "url": e.url,
                            "extracted_text_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                            "response_body_sha256": hashlib.sha256(raw).hexdigest(),
                            "response_body_status": "archived", "extractor_sha256": _EXTRACTOR_SHA,
                            "normalized_page_title": e.title, "provenance_level": "full", "encoding": "utf-8",
                            "extracted_text": txt, "response_body": raw})
            print(f"  fetched {e.index} {e.title[:18]} ({len(txt)} chars)", flush=True)

    assert len(records) == 383 and sorted(r["chapter_index"] for r in records) == list(range(1, 384))
    assert sum(1 for r in records if r["response_body_status"] == "archived") == 303
    build_and_publish_snapshot([ChapterEntry(e.index, e.title, e.url) for e in entries],
                               FORMAL, lambda es: records, ARCHIVE)
    act = read_active_snapshot(FORMAL)
    restore_responses(FORMAL, act["snapshot_sha256"], ARCHIVE)
    print("SNAPSHOT_PUBLISHED", act["snapshot_sha256"])
    print("chapters:", len(records), "fetched(archived):", sum(1 for r in records if r["response_body_status"] == "archived"))


if __name__ == "__main__":
    main()
