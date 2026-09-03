"""Sanming Tonghui source-chain verifier (design §4.2 / §10-③).

Implements ``source_chain_check``: reads pointer/manifest/chapter-list/
extractor/parser from Git blobs (frozen identities below), self-pins the
external archive at ``--archive-root``, and replays C1/C2/C3 over chapters
81-383. The extractor's ``_FOOTER`` and ``_extract_content`` are AST-extracted
from the frozen blob (no hand copies); ``parse_chapter_list`` is loaded from
its frozen parser blob. BLOCKED reasons and failure codes follow the frozen
enums; exit 0 = all pass, 1 = failures, 3 = BLOCKED.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# §4.1 精确身份（全长）
BASE_COMMIT = "c5cff699fdb547bd9270acbebe1f485380848751"
POINTER_BLOB_OID = "b423b726afe4890618b5f0796162ba6d4120b7da"
MANIFEST_BLOB_OID = "662fbe6013c11b3bc58a3393ef1168ea82b05eca"
CHAPTER_LIST_BLOB_OID = "70c5029c29c3443ea2b149a749e7ba6aef904779"
PARSER_BLOB_OID = "1842a8d5c732b19a233baa72fd7fec496217722d"
EXTRACTOR_COMMIT = "f64a25ddd8ef43aef9ad75e189e72a4f9d373938"
EXTRACTOR_REL = "scripts/fetch_sanming_full.py"
EXTRACTOR_BLOB_OID = "4bbd6e1a2717d932f0f33bb9bbce4f7ed24db463"
SNAP = "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/b4e9be580dbecd3e233d3adbe163299f06c6ca5174309dc83e8f14433796aaa2"
VERIFIER_REL = "scripts/verify_sanming_source_chain.py"
SCHEMA_VERSION = "1.0"
CHAPTERS_START = 81
CHAPTERS_END = 383
CHAPTERS_EXPECTED = 303

# §4.2 统一枚举
BLOCKED_REASONS = (
    "archive_missing",
    "archive_sha_mismatch",
    "archive_size_mismatch",
    "verifier_identity_mismatch",
    "archive_root_missing",
)

FAILURE_CODES = (
    "ARCHIVE_MEMBER_MISSING",
    "C1_SHA_MISMATCH",
    "C2_HEADING_NOT_FOUND",
    "C2_NO_BODY",
    "C2_EXTRACTION_ERROR",
    "C2_SHA_MISMATCH",
    "C3_SHA_MISMATCH",
)


class BlockedError(Exception):
    """BLOCKED（§4.2 五值枚举），携带 reason。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _run_git(git_root: Path, args, check: bool = True):
    p = subprocess.run(["git", "-C", str(git_root), *args], capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.decode('utf-8', 'replace').strip()}")
    return p


def _git_show_bytes(git_root: Path, oid: str) -> bytes:
    return _run_git(git_root, ["show", oid]).stdout


def _git_rev_parse(git_root: Path, rev: str) -> str | None:
    p = _run_git(git_root, ["rev-parse", rev], check=False)
    return p.stdout.decode().strip() if p.returncode == 0 else None


def _git_hash_object(git_root: Path, path: Path) -> str:
    return _run_git(git_root, ["hash-object", str(path)]).stdout.decode().strip()


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def check_verifier_identity(git_root: Path, verifier_path: Path) -> None:
    """执行前身份门（§12）：``git hash-object`` 工作区 == ``HEAD`` blob OID。

    HEAD 无此文件或两者不等 → BLOCKED ``verifier_identity_mismatch``。
    """
    head_oid = _git_rev_parse(git_root, f"HEAD:{VERIFIER_REL}")
    worktree_oid = _git_hash_object(git_root, verifier_path)
    if head_oid is None or head_oid != worktree_oid:
        raise BlockedError("verifier_identity_mismatch")


def _load_parse_chapter_list(parser_source: bytes):
    """从冻结 parser blob 源码加载 ``parse_chapter_list``（§4.2，禁止手工副本）。"""
    ns: dict = {}
    exec(compile(parser_source.decode("utf-8"), "<parser:fetch_sanming_chapters>", "exec"), ns)
    return ns["parse_chapter_list"]


def _extract_from_extractor(source: bytes):
    """AST 提取 extractor blob 的 ``_FOOTER`` 与 ``_extract_content`` 并执行（§4.2 实现冻结）。

    Returns ``(footer, extract_content, footer_src_bytes, extract_src_bytes)``；
    提取片段字节 == blob 内源码段（同源测试断言）。
    """
    text = source.decode("utf-8")
    tree = ast.parse(text)
    footer_src = extract_src = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_FOOTER" for t in node.targets):
            footer_src = ast.get_source_segment(text, node)
        elif isinstance(node, ast.FunctionDef) and node.name == "_extract_content":
            extract_src = ast.get_source_segment(text, node)
    if footer_src is None or extract_src is None:
        raise ValueError("extractor blob missing _FOOTER/_extract_content")
    ns = {"re": re}
    exec(compile(footer_src, "<extractor:_FOOTER>", "exec"), ns)
    exec(compile(extract_src, "<extractor:_extract_content>", "exec"), ns)
    return ns["_FOOTER"], ns["_extract_content"], footer_src.encode("utf-8"), extract_src.encode("utf-8")


def _read_tar_members(archive_root: Path, pointer: dict) -> dict[str, bytes]:
    """自钉并读取外部归档（§4.2）；缺失/损坏 → BLOCKED。返回 {成员名: 字节}。"""
    if not archive_root.is_dir():
        raise BlockedError("archive_root_missing")
    tar_path = archive_root / pointer["archive_uri"]
    if not tar_path.is_file():
        raise BlockedError("archive_missing")
    data = tar_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != pointer["archive_sha256"]:
        raise BlockedError("archive_sha_mismatch")
    if len(data) != pointer["archive_size"]:
        raise BlockedError("archive_size_mismatch")
    members: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
        for m in tf.getmembers():
            if m.isfile():
                members[m.name] = tf.extractfile(m).read()
    return members


def run_c_checks(records, titles, tar, footer, extract_func, extracted_provider):
    """C1/C2/C3 over chapters 81-383（§4.2）。返回 ``(c1, c2, c3, failures)``。"""
    by_index = {r["chapter_index"]: r for r in records}
    failures = []
    c1 = c2 = c3 = 0
    for n in range(CHAPTERS_START, CHAPTERS_END + 1):
        rec = by_index.get(n)
        if rec is None:
            failures.append(
                {"chapter": n, "check": "C1", "code": "ARCHIVE_MEMBER_MISSING",
                 "detail": f"no manifest record for chapter {n}"}
            )
            continue
        html = tar.get(f"responses/raw_{n:03d}.html")
        if html is None:
            failures.append(
                {"chapter": n, "check": "C1", "code": "ARCHIVE_MEMBER_MISSING",
                 "detail": f"responses/raw_{n:03d}.html not in archive"}
            )
            continue
        if hashlib.sha256(html).hexdigest() != rec.get("response_body_sha256"):
            failures.append(
                {"chapter": n, "check": "C1", "code": "C1_SHA_MISMATCH",
                 "detail": f"response body sha mismatch for chapter {n}"}
            )
        else:
            c1 += 1
        title = titles.get(n, "")
        text = None
        try:
            text = extract_func(html.decode("utf-8", errors="replace"), n, title)
        except ValueError as exc:
            msg = str(exc)
            if "heading not found" in msg:
                code = "C2_HEADING_NOT_FOUND"
            elif "no body text" in msg:
                code = "C2_NO_BODY"
            else:
                code = "C2_EXTRACTION_ERROR"
            failures.append({"chapter": n, "check": "C2", "code": code, "detail": msg})
            continue
        text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if text_sha != rec.get("extracted_text_sha256"):
            failures.append(
                {"chapter": n, "check": "C2", "code": "C2_SHA_MISMATCH",
                 "detail": f"extracted text sha mismatch for chapter {n}"}
            )
        else:
            c2 += 1
        committed = extracted_provider(n)
        if hashlib.sha256(committed).hexdigest() != text_sha:
            failures.append(
                {"chapter": n, "check": "C3", "code": "C3_SHA_MISMATCH",
                 "detail": f"committed extracted txt sha mismatch for chapter {n}"}
            )
        else:
            c3 += 1
    failures.sort(key=lambda f: (f["chapter"], f["check"], f["code"], f["detail"]))
    return c1, c2, c3, failures


def verify_source_chain(
    git_root: Path,
    archive_root: Path,
    *,
    verifier_path: Path | None = None,
    check_identity: bool = True,
    pointer: dict | None = None,
    manifest: dict | None = None,
    chapter_list_text: str | None = None,
    extractor_source: bytes | None = None,
    parser_source: bytes | None = None,
    extracted_provider=None,
    base_commit: str | None = None,
):
    """``source_chain_check`` 执行体。返回 ``(output_dict, exit_code)``。

    参数均可注入（测试用）；缺省从冻结 Git blob 读取。
    """
    base_commit = base_commit or BASE_COMMIT
    try:
        if check_identity:
            if verifier_path is None:
                raise ValueError("verifier_path required when check_identity=True")
            check_verifier_identity(git_root, verifier_path)
        if pointer is None:
            pointer = json.loads(_git_show_bytes(git_root, POINTER_BLOB_OID))
        if manifest is None:
            manifest = json.loads(_git_show_bytes(git_root, MANIFEST_BLOB_OID))
        if chapter_list_text is None:
            chapter_list_text = _git_show_bytes(git_root, CHAPTER_LIST_BLOB_OID).decode("utf-8")
        if extractor_source is None:
            extractor_source = _git_show_bytes(git_root, EXTRACTOR_BLOB_OID)
        if parser_source is None:
            parser_source = _git_show_bytes(git_root, PARSER_BLOB_OID)

        tar = _read_tar_members(archive_root, pointer)
        parse_chapter_list = _load_parse_chapter_list(parser_source)
        titles = {e.index: e.title for e in parse_chapter_list(chapter_list_text)}
        footer, extract_func, _, _ = _extract_from_extractor(extractor_source)
        if extracted_provider is None:

            def extracted_provider(n):
                return _git_show_bytes(git_root, f"{base_commit}:{SNAP}/extracted/raw_{n:03d}.txt")

        c1, c2, c3, failures = run_c_checks(
            manifest["chapters"], titles, tar, footer, extract_func, extracted_provider
        )
        output = {
            "schema_version": SCHEMA_VERSION,
            "status": "OK",
            "chapters_expected": CHAPTERS_EXPECTED,
            "c1_pass": c1,
            "c2_pass": c2,
            "c3_pass": c3,
            "failures": failures,
        }
        return output, (1 if failures else 0)
    except BlockedError as e:
        return {"schema_version": SCHEMA_VERSION, "status": "BLOCKED", "reason": e.reason}, 3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verify_sanming_source_chain")
    ap.add_argument("--base", default=BASE_COMMIT, help="data base commit（冻结默认，报告链禁止非冻结 base）")
    ap.add_argument("--archive-root", required=True)
    ap.add_argument("--git-root", default=str(ROOT))
    a = ap.parse_args(argv)
    git_root = Path(a.git_root)
    out, code = verify_source_chain(
        git_root,
        Path(a.archive_root),
        verifier_path=Path(__file__),
        check_identity=True,
        base_commit=a.base,
    )
    sys.stdout.write(_canonical(out))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
