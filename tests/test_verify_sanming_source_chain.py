"""Tests for the sanming source-chain verifier (design §4.2 / §10-③).

Covers: AST same-source extraction of _FOOTER/_extract_content, the five
BLOCKED reasons, the verifier disk==HEAD identity gate, the C1/C2/C3 checks
including a deterministic 303/303 full replay, failures tuple ordering, and
the failures-vs-BLOCKED two-state separation.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from scripts.verify_sanming_source_chain import (
    BLOCKED_REASONS,
    CHAPTERS_END,
    CHAPTERS_EXPECTED,
    CHAPTERS_START,
    CHAPTER_LIST_BLOB_OID,
    EXTRACTOR_BLOB_OID,
    PARSER_BLOB_OID,
    BlockedError,
    _extract_from_extractor,
    _load_parse_chapter_list,
    check_verifier_identity,
    run_c_checks,
    verify_source_chain,
)

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts" / "verify_sanming_source_chain.py"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def _git_show(oid: str) -> bytes:
    return _git(ROOT, "show", oid)


def _tmp_git(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    return repo


# ---------------------------------------------------------------------------
# AST 同源（§4.2 实现冻结）
# ---------------------------------------------------------------------------

def test_extract_from_extractor_same_source():
    src = _git_show(EXTRACTOR_BLOB_OID)
    footer, func, footer_bytes, func_bytes = _extract_from_extractor(src)
    text = src.decode("utf-8")
    tree = ast.parse(text)
    footer_src = func_src = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_FOOTER" for t in node.targets):
            footer_src = ast.get_source_segment(text, node)
        elif isinstance(node, ast.FunctionDef) and node.name == "_extract_content":
            func_src = ast.get_source_segment(text, node)
    assert footer_src is not None and func_src is not None
    assert footer_bytes == footer_src.encode("utf-8")
    assert func_bytes == func_src.encode("utf-8")
    assert footer.pattern
    assert callable(func)


def test_extract_content_behavior():
    _, func, *_ = _extract_from_extractor(_git_show(EXTRACTOR_BLOB_OID))
    title = "卷五·水火既济"
    content = "三命通会内容章节测试" * 60
    html = f'<div class="content"><p>{title}</p><p>{content}</p></div>'
    out = func(html, 81, title)
    assert out == content


def test_parse_chapter_list_loaded_from_parser_blob():
    parser = _load_parse_chapter_list(_git_show(PARSER_BLOB_OID))
    text = _git_show(CHAPTER_LIST_BLOB_OID).decode("utf-8")
    entries = parser(text)
    assert len(entries) == 383
    assert entries[0].index == 1
    assert entries[80].title  # 第 81 章（C1 起点）
    assert entries[80].index == 81


# ---------------------------------------------------------------------------
# 五值 BLOCKED
# ---------------------------------------------------------------------------

def test_blocked_reasons_enum():
    assert BLOCKED_REASONS == (
        "archive_missing",
        "archive_sha_mismatch",
        "archive_size_mismatch",
        "verifier_identity_mismatch",
        "archive_root_missing",
    )


# ---------------------------------------------------------------------------
# 合成场景：真实 extractor/chapter_list，合成 manifest/tar（确定性可重放）
# ---------------------------------------------------------------------------

def _build_tar(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:", format=tarfile.GNU_FORMAT) as tf:
        for name in sorted(members):
            data = members[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture(scope="module")
def extractor_parts():
    return _extract_from_extractor(_git_show(EXTRACTOR_BLOB_OID))


@pytest.fixture(scope="module")
def titles():
    parser = _load_parse_chapter_list(_git_show(PARSER_BLOB_OID))
    text = _git_show(CHAPTER_LIST_BLOB_OID).decode("utf-8")
    return {e.index: e.title for e in parser(text)}


def _scenario(tmp_path, titles, extract_func):
    records, tar_map, extracted_map = [], {}, {}
    for n in range(CHAPTERS_START, CHAPTERS_END + 1):
        title = titles[n]
        html = f'<div class="content"><p>{title}</p><p>{"三命通会内容章节测试" * 60}</p></div>'
        html_bytes = html.encode("utf-8")
        text = extract_func(html, n, title)
        extracted_map[n] = text.encode("utf-8")
        tar_map[f"responses/raw_{n:03d}.html"] = html_bytes
        records.append(
            {
                "chapter_index": n,
                "title": title,
                "url": f"https://www.44414.cn/{n}.html",
                "response_body_sha256": hashlib.sha256(html_bytes).hexdigest(),
                "response_body_status": "archived",
                "provenance_level": "full",
                "encoding": "utf-8",
                "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "extractor_sha256": "afa691ef3568c94cc34a04da60e75c492f1faba6cfd8c2e8c16827ac33f6ab1d",
                "normalized_page_title": title,
            }
        )
    manifest = {"snapshot_sha256": "0" * 64, "response_archive_pointer_sha256": "0" * 64, "chapters": records}
    archive_root = tmp_path / "archive"
    archive_root.mkdir()

    def rebuild():
        tar_bytes = _build_tar(tar_map)
        archive_sha = hashlib.sha256(tar_bytes).hexdigest()
        uri = f"{archive_sha}.tar"
        (archive_root / uri).write_bytes(tar_bytes)
        pointer = {
            "snapshot_sha256": "0" * 64,
            "archive_format": "tar",
            "archive_sha256": archive_sha,
            "archive_size": len(tar_bytes),
            "archive_uri": uri,
            "response_count": 303,
        }
        return pointer, manifest

    return {
        "records": records,
        "tar_map": tar_map,
        "extracted_map": extracted_map,
        "archive_root": archive_root,
        "rebuild": rebuild,
    }


def _run(scenario, **overrides):
    pointer, manifest = scenario["rebuild"]()
    kw = dict(
        pointer=pointer,
        manifest=manifest,
        chapter_list_text=_git_show(CHAPTER_LIST_BLOB_OID).decode("utf-8"),
        extractor_source=_git_show(EXTRACTOR_BLOB_OID),
        parser_source=_git_show(PARSER_BLOB_OID),
        extracted_provider=lambda n: scenario["extracted_map"][n],
        check_identity=False,
    )
    kw.update(overrides)
    return verify_source_chain(ROOT, scenario["archive_root"], **kw)


# ---------------------------------------------------------------------------
# 303/303 全量重放与 C1/C2/C3 负向
# ---------------------------------------------------------------------------

def test_full_303_replay_ok(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    out, code = _run(scenario)
    assert code == 0
    assert out["status"] == "OK"
    assert out["chapters_expected"] == CHAPTERS_EXPECTED == 303
    assert out["c1_pass"] == out["c2_pass"] == out["c3_pass"] == 303
    assert out["failures"] == []


def test_c1_sha_mismatch(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    scenario["records"][0]["response_body_sha256"] = "0" * 64
    out, code = _run(scenario)
    assert code == 1
    assert out["c1_pass"] == 302
    f = out["failures"][0]
    assert f["chapter"] == CHAPTERS_START and f["check"] == "C1" and f["code"] == "C1_SHA_MISMATCH"


def test_member_missing_is_failure_not_blocked(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    scenario["tar_map"].pop(f"responses/raw_{CHAPTERS_START:03d}.html")
    out, code = _run(scenario)
    assert code == 1
    assert out["status"] == "OK"  # 源检查失败 ≠ BLOCKED（两态分离）
    assert any(f["code"] == "ARCHIVE_MEMBER_MISSING" and f["check"] == "C1" for f in out["failures"])


def test_c2_heading_not_found(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    html = b"<html><body><p>no title here</p></body></html>"
    scenario["tar_map"]["responses/raw_081.html"] = html
    scenario["records"][0]["response_body_sha256"] = hashlib.sha256(html).hexdigest()
    out, code = _run(scenario)
    assert code == 1
    f = next(x for x in out["failures"] if x["check"] == "C2")
    assert f["chapter"] == 81 and f["code"] == "C2_HEADING_NOT_FOUND"


def test_c2_no_body(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    html = f"<html><body><p>{titles[81]}</p></body></html>".encode("utf-8")
    scenario["tar_map"]["responses/raw_081.html"] = html
    scenario["records"][0]["response_body_sha256"] = hashlib.sha256(html).hexdigest()
    out, code = _run(scenario)
    assert code == 1
    f = next(x for x in out["failures"] if x["check"] == "C2")
    assert f["chapter"] == 81 and f["code"] == "C2_NO_BODY"


def test_c2_extraction_error_mapping(titles, extractor_parts):
    html = b"x"
    records = [{"chapter_index": 81, "response_body_sha256": hashlib.sha256(html).hexdigest(),
                "extracted_text_sha256": "0" * 64}]
    tar = {f"responses/raw_{CHAPTERS_START:03d}.html": html}
    def bad_func(html, idx, title):
        raise ValueError("boom")
    c1, c2, c3, failures = run_c_checks(records, titles, tar, extractor_parts[0], bad_func, lambda n: b"")
    assert (c1, c2, c3) == (1, 0, 0)
    assert failures[0]["code"] == "C2_EXTRACTION_ERROR"


def test_c2_sha_mismatch(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    scenario["records"][0]["extracted_text_sha256"] = "0" * 64
    out, code = _run(scenario)
    assert code == 1
    assert out["c2_pass"] == 302
    assert any(f["code"] == "C2_SHA_MISMATCH" and f["chapter"] == 81 for f in out["failures"])


def test_c3_sha_mismatch(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    scenario["extracted_map"][81] = b"committed txt drifted"
    out, code = _run(scenario)
    assert code == 1
    assert out["c3_pass"] == 302
    assert any(f["code"] == "C3_SHA_MISMATCH" and f["chapter"] == 81 for f in out["failures"])


def test_failures_sorted_by_tuple(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    scenario["records"][9]["response_body_sha256"] = "0" * 64  # ch90 C1
    scenario["records"][1]["extracted_text_sha256"] = "0" * 64  # ch82 C2
    scenario["extracted_map"][83] = b"x"  # ch83 C3
    out, code = _run(scenario)
    assert code == 1
    keys = [(f["chapter"], f["check"], f["code"], f["detail"]) for f in out["failures"]]
    assert keys == sorted(keys)
    assert keys[0] == (82, "C2", "C2_SHA_MISMATCH", keys[0][3])
    assert keys[1][0] == 83
    assert keys[2][0] == 90


# ---------------------------------------------------------------------------
# verifier disk==HEAD 身份门（§12 执行链）
# ---------------------------------------------------------------------------

def test_verifier_identity_ok(tmp_path):
    repo = _tmp_git(tmp_path)
    scripts = repo / "scripts"
    scripts.mkdir()
    stub = scripts / "verify_sanming_source_chain.py"
    stub.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "verifier"], check=True)
    check_verifier_identity(repo, stub)  # 不抛异常


def test_verifier_identity_handles_unicode_and_space_git_root(tmp_path):
    parent = tmp_path / "中文 与 space"
    parent.mkdir()
    repo = _tmp_git(parent)
    scripts = repo / "scripts"
    scripts.mkdir()
    stub = scripts / "verify_sanming_source_chain.py"
    stub.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "verifier"], check=True)
    check_verifier_identity(repo, stub)  # 参数数组保持中文和空格路径完整


def test_verifier_identity_mismatch_blocked(tmp_path):
    repo = _tmp_git(tmp_path)
    scripts = repo / "scripts"
    scripts.mkdir()
    stub = scripts / "verify_sanming_source_chain.py"
    stub.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "verifier"], check=True)
    stub.write_text("x = 2\n", encoding="utf-8")  # 工作区 != HEAD
    with pytest.raises(BlockedError) as e:
        check_verifier_identity(repo, stub)
    assert e.value.reason == "verifier_identity_mismatch"


# ---------------------------------------------------------------------------
# BLOCKED 行为（archive-root / archive / sha / size）
# ---------------------------------------------------------------------------

def test_archive_root_missing_blocked(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    pointer, manifest = scenario["rebuild"]()
    out, code = verify_source_chain(
        ROOT,
        tmp_path / "does-not-exist",
        pointer=pointer,
        manifest=manifest,
        chapter_list_text=_git_show(CHAPTER_LIST_BLOB_OID).decode("utf-8"),
        extractor_source=_git_show(EXTRACTOR_BLOB_OID),
        parser_source=_git_show(PARSER_BLOB_OID),
        check_identity=False,
    )
    assert code == 3
    assert out == {"schema_version": "1.0", "status": "BLOCKED", "reason": "archive_root_missing"}


def test_archive_missing_blocked(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    pointer, manifest = scenario["rebuild"]()
    pointer = dict(pointer, archive_uri="not-present.tar")
    out, code = _run(scenario, pointer=pointer)
    assert code == 3
    assert out["reason"] == "archive_missing"


def test_archive_sha_mismatch_blocked(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    pointer, manifest = scenario["rebuild"]()
    pointer = dict(pointer, archive_sha256="0" * 64)
    out, code = _run(scenario, pointer=pointer)
    assert code == 3
    assert out["reason"] == "archive_sha_mismatch"


def test_archive_size_mismatch_blocked(tmp_path, titles, extractor_parts):
    scenario = _scenario(tmp_path, titles, extractor_parts[1])
    pointer, manifest = scenario["rebuild"]()
    pointer = dict(pointer, archive_size=pointer["archive_size"] + 1)
    out, code = _run(scenario, pointer=pointer)
    assert code == 3
    assert out["reason"] == "archive_size_mismatch"


# ---------------------------------------------------------------------------
# CLI 接线：BLOCKED 输出 schema + exit 3（temp repo 无已提交 verifier → 身份门拦截）
# ---------------------------------------------------------------------------

def test_cli_blocked_output_schema(tmp_path):
    repo = _tmp_git(tmp_path)
    p = subprocess.run(
        [sys.executable, str(VERIFIER), "--git-root", str(repo), "--archive-root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 3
    out = json.loads(p.stdout)
    assert out["schema_version"] == "1.0"
    assert out["status"] == "BLOCKED"
    assert out["reason"] == "verifier_identity_mismatch"
