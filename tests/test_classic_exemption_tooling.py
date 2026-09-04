"""§10-⑤ C-exemption-tooling：v2.0 豁免链工具测试。

覆盖：v2 E 生成（正式 CLI）、v2 E/R 精确字段集与逐项镜像、
§5-E2 权威重算三方全等、ls-tree -z 中文/空格路径解析负向。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.classic_artifacts import (
    BASE_COMMIT,
    exemption_request_sha256,
    load_exemption_request,
    recompute_artifact_manifest_sha256,
    recompute_validator_code_sha256,
    verify_approval_receipt,
    verify_exemption_request,
)

ROOT = Path(__file__).resolve().parent.parent
MAKE_E = ROOT / "scripts" / "make_historical_exemption.py"
FREEZE_PATH = ROOT / "docs/superpowers/specs/2026-09-02-classic-texts-historical-record-freeze.json"
EVIDENCE_PATH = ROOT / "docs/superpowers/specs/2026-09-02-classic-texts-historical-generation-evidence.json"


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _tmp_git(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "seed"], check=True)
    return repo


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _v2_request(**overrides):
    e = {
        "schema_version": "2.0",
        "book": "ditiansui",
        "artifact_manifest_sha256": "a" * 64,
        "baseline_commit": BASE_COMMIT,
        "validator_code_sha256": "b" * 64,
        "historical_record_freeze_sha256": "c" * 64,
        "historical_generation_evidence_sha256": "d" * 64,
        "exempted_checks": ["missing_formal_model_run_manifest"],
        "non_exempt_checks": ["artifact_integrity", "quality_gates", "future_generation_provenance"],
        "author": "implementing-agent",
        "date": "2026-09-04",
        "parent_commit": "e" * 40,
    }
    e.update(overrides)
    return e


def _v2_receipt(e, **overrides):
    r = {
        "schema_version": "2.0",
        "exemption_request_sha256": exemption_request_sha256(e),
        "baseline_commit": e["baseline_commit"],
        "artifact_manifest_sha256": e["artifact_manifest_sha256"],
        "validator_code_sha256": e["validator_code_sha256"],
        "historical_record_freeze_sha256": e["historical_record_freeze_sha256"],
        "historical_generation_evidence_sha256": e["historical_generation_evidence_sha256"],
        "parent_commit": e["parent_commit"],
        "approver": "owner",
        "approved_at": "2026-09-04T00:00:00+08:00",
    }
    r.update(overrides)
    return r


def _drop(obj, key):
    return {k: v for k, v in obj.items() if k != key}


# ---------------------------------------------------------------------------
# v2 E 精确字段集（12 项）
# ---------------------------------------------------------------------------

def test_v2_request_ok():
    assert verify_exemption_request(_v2_request()) is True


def test_v2_request_extra_field_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request({**_v2_request(), "extra": 1})


def test_v2_request_missing_field_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request(_drop(_v2_request(), "parent_commit"))


def test_v2_request_wrong_version_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(schema_version="3.0"))


def test_v2_request_bad_baseline_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(baseline_commit="0" * 40))


def test_v2_request_bad_book_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(book="hacker"))


@pytest.mark.parametrize("checks", [
    [],
    ["missing_upstream_response_body"],
    ["missing_formal_model_run_manifest", "extra_check"],
])
def test_v2_request_bad_exempted_checks_rejected(checks):
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(exempted_checks=checks))


@pytest.mark.parametrize("checks", [
    [],
    ["artifact_integrity"],
    ["artifact_integrity", "quality_gates", "future_generation_provenance", "extra"],
])
def test_v2_request_bad_non_exempt_checks_rejected(checks):
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(non_exempt_checks=checks))


@pytest.mark.parametrize("field", [
    "artifact_manifest_sha256",
    "validator_code_sha256",
    "historical_record_freeze_sha256",
    "historical_generation_evidence_sha256",
])
def test_v2_request_bad_sha_format_rejected(field):
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(**{field: "z" * 63}))


def test_v2_request_bad_parent_commit_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(parent_commit="1234"))


def test_v2_request_receipt_field_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request({**_v2_request(), "approval_receipt_sha256": "0" * 64})


def test_v2_request_approval_commit_field_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request({**_v2_request(), "approval_commit": "0" * 40})


def test_v2_request_empty_author_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(author=""))


def test_v2_request_empty_date_rejected():
    with pytest.raises(ValueError):
        verify_exemption_request(_v2_request(date=""))


# ---------------------------------------------------------------------------
# v2 R 精确字段集（10 项）与逐项镜像
# ---------------------------------------------------------------------------

def test_v2_receipt_ok():
    e = _v2_request()
    assert verify_approval_receipt(_v2_receipt(e), e) is True


def test_v2_receipt_extra_field_rejected():
    e = _v2_request()
    with pytest.raises(ValueError):
        verify_approval_receipt({**_v2_receipt(e), "extra": 1}, e)


def test_v2_receipt_missing_field_rejected():
    e = _v2_request()
    with pytest.raises(ValueError):
        verify_approval_receipt(_drop(_v2_receipt(e), "validator_code_sha256"), e)


def test_v2_receipt_wrong_version_rejected():
    e = _v2_request()
    with pytest.raises(ValueError):
        verify_approval_receipt(_v2_receipt(e, schema_version="1.0"), e)


def test_v2_receipt_request_sha_mismatch_rejected():
    e = _v2_request()
    with pytest.raises(ValueError):
        verify_approval_receipt(_v2_receipt(e, exemption_request_sha256="0" * 64), e)


@pytest.mark.parametrize("field", [
    "baseline_commit",
    "artifact_manifest_sha256",
    "validator_code_sha256",
    "historical_record_freeze_sha256",
    "historical_generation_evidence_sha256",
    "parent_commit",
])
def test_v2_receipt_mirror_mismatch_rejected(field):
    e = _v2_request()
    bad = "0" * 40 if field in ("baseline_commit", "parent_commit") else "0" * 64
    with pytest.raises(ValueError):
        verify_approval_receipt(_v2_receipt(e, **{field: bad}), e)


def test_v2_receipt_empty_approver_rejected():
    e = _v2_request()
    with pytest.raises(ValueError):
        verify_approval_receipt(_v2_receipt(e, approver=""), e)


def test_v2_receipt_empty_approved_at_rejected():
    e = _v2_request()
    with pytest.raises(ValueError):
        verify_approval_receipt(_v2_receipt(e, approved_at=""), e)


def test_v2_request_rejects_receipt_fields():
    # 两版禁含回执/批准字段：v2 E 携带 approver 被精确字段集拒绝
    with pytest.raises(ValueError):
        verify_exemption_request({**_v2_request(), "approver": "x"})


# ---------------------------------------------------------------------------
# v1 分派回归：无 schema_version 的 v1 路径保持不变
# ---------------------------------------------------------------------------

def _v1_request():
    return {
        "book": "ditiansui",
        "baseline_commit": "a" * 40,
        "artifact_manifest_sha256": "b" * 64,
        "validator_code_sha256": "c" * 64,
        "exempted_checks": ["missing_upstream_response_body"],
        "non_exempt_checks": ["artifact_integrity"],
        "author": "r",
        "date": "2026-08-13",
    }


def test_v1_request_without_schema_version_still_passes():
    assert verify_exemption_request(_v1_request()) is True


def test_v1_receipt_without_schema_version_still_passes():
    e = _v1_request()
    r = {
        "exemption_request_sha256": exemption_request_sha256(e),
        "baseline_commit": "a" * 40,
        "artifact_manifest_sha256": "b" * 64,
        "approver": "lead",
        "approved_at": "2026-08-13T00:00:00Z",
    }
    assert verify_approval_receipt(r, e) is True


# ---------------------------------------------------------------------------
# §5-E2 权威重算：validator_code_sha256 与 artifact_manifest_sha256
# ---------------------------------------------------------------------------

def test_recompute_validator_code_sha256_matches_git_blob(tmp_path):
    repo = _tmp_git(tmp_path)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "validate_classic_distillation.py").write_text("# validator v", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "v"], check=True)
    head = _git(repo, "rev-parse", "HEAD")
    assert recompute_validator_code_sha256(repo, head) == _sha_bytes(b"# validator v")


def test_recompute_validator_code_sha256_tracks_blob_not_worktree(tmp_path):
    repo = _tmp_git(tmp_path)
    (repo / "scripts").mkdir()
    validator = repo / "scripts" / "validate_classic_distillation.py"
    validator.write_text("# committed", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "v"], check=True)
    head = _git(repo, "rev-parse", "HEAD")
    validator.write_text("# tampered worktree", encoding="utf-8")  # 工作区漂移不影响 Git 对象重算
    assert recompute_validator_code_sha256(repo, head) == _sha_bytes(b"# committed")


def _make_book_repo(tmp_path, *, with_weird_names=True):
    repo = _tmp_git(tmp_path)
    book = repo / "knowledge_base" / "classic_texts" / "ditiansui"
    book.mkdir(parents=True)
    (book / "all_rules.json").write_text("{}", encoding="utf-8")
    if with_weird_names:
        (book / "raw 全文.txt").write_text("中文内容", encoding="utf-8")
        (book / "note book.txt").write_text("space name", encoding="utf-8")
    (book / "sub").mkdir()
    (book / "sub" / "inner.json").write_text("[]", encoding="utf-8")  # 嵌套：非直接子项，必须排除
    (book / "README.md").write_text("md", encoding="utf-8")  # 后缀过滤：必须排除
    (repo / "scripts").mkdir()
    (repo / "scripts" / "validate_classic_distillation.py").write_text("# v", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "book"], check=True)
    return repo, _git(repo, "rev-parse", "HEAD")


def test_recompute_artifact_manifest_chinese_and_space_names(tmp_path):
    # ls-tree -z NUL 解析：中文/空格路径的键为精确 basename；按行/空格切分会得到错误键
    repo, head = _make_book_repo(tmp_path)
    expected_shas = {
        "all_rules.json": _sha_bytes(b"{}"),
        "raw 全文.txt": _sha_bytes("中文内容".encode("utf-8")),
        "note book.txt": _sha_bytes(b"space name"),
    }
    expected_manifest = {
        "sha256_by_path": expected_shas,
        "git_ref": head,
        "git_verified": True,
    }
    expected = _sha_bytes(_canonical(expected_manifest).encode("utf-8"))
    assert recompute_artifact_manifest_sha256(repo, head, "ditiansui") == expected


def test_recompute_artifact_manifest_direct_children_only(tmp_path):
    # 非递归：sub/inner.json 排除；后缀过滤：README.md 排除
    repo, head = _make_book_repo(tmp_path, with_weird_names=False)
    expected_shas = {"all_rules.json": _sha_bytes(b"{}")}
    expected_manifest = {"sha256_by_path": expected_shas, "git_ref": head, "git_verified": True}
    expected = _sha_bytes(_canonical(expected_manifest).encode("utf-8"))
    assert recompute_artifact_manifest_sha256(repo, head, "ditiansui") == expected


def test_recompute_artifact_manifest_rejects_unknown_book(tmp_path):
    repo, head = _make_book_repo(tmp_path, with_weird_names=False)
    with pytest.raises(ValueError):
        recompute_artifact_manifest_sha256(repo, head, "hacker")


def test_recompute_artifact_manifest_rejects_bad_base(tmp_path):
    repo, _ = _make_book_repo(tmp_path, with_weird_names=False)
    with pytest.raises(ValueError):
        recompute_artifact_manifest_sha256(repo, "0" * 40, "ditiansui")


# ---------------------------------------------------------------------------
# E2 三方全等（E == R == 重算值）
# ---------------------------------------------------------------------------

def test_three_way_equality_in_tmp_repo(tmp_path):
    repo, head = _make_book_repo(tmp_path, with_weird_names=True)
    manifest_sha = recompute_artifact_manifest_sha256(repo, head, "ditiansui")
    val_sha = recompute_validator_code_sha256(repo, head)
    e = _v2_request(artifact_manifest_sha256=manifest_sha, validator_code_sha256=val_sha)
    r = _v2_receipt(e)
    assert verify_exemption_request(e) is True
    assert verify_approval_receipt(r, e) is True
    assert e["artifact_manifest_sha256"] == r["artifact_manifest_sha256"] == manifest_sha
    assert e["validator_code_sha256"] == r["validator_code_sha256"] == val_sha


def test_three_way_inequality_detected(tmp_path):
    # 篡改 E 的 manifest SHA 且 R 同步镜像（自洽）→ 仍与权威重算值不等 → E2 判豁免失效
    repo, head = _make_book_repo(tmp_path, with_weird_names=False)
    manifest_sha = recompute_artifact_manifest_sha256(repo, head, "ditiansui")
    forged = _sha_bytes((manifest_sha + "x").encode("utf-8"))
    assert forged != manifest_sha
    e = _v2_request(artifact_manifest_sha256=forged)
    r = _v2_receipt(e)
    assert e["artifact_manifest_sha256"] == r["artifact_manifest_sha256"] != manifest_sha


# ---------------------------------------------------------------------------
# v2 E 生成（正式 CLI）
# ---------------------------------------------------------------------------

def _run_make_e(*args):
    return subprocess.run(
        [sys.executable, str(MAKE_E), *args], capture_output=True, text=True, cwd=ROOT
    )


def test_v2_cli_generation_real_repo(tmp_path):
    out = tmp_path / "e2.json"
    p = _run_make_e(
        "--schema-version", "2.0",
        "--book", "ditiansui",
        "--baseline", BASE_COMMIT,
        "--out", str(out),
        "--git-root", str(ROOT),
        "--freeze", str(FREEZE_PATH),
        "--evidence", str(EVIDENCE_PATH),
        "--author", "implementing-agent",
        "--date", "2026-09-04",
    )
    assert p.returncode == 0, p.stderr
    e = load_exemption_request(out)
    assert verify_exemption_request(e) is True
    assert set(e) == set(_v2_request())
    # E2 三方全等（真实仓库、真实冻结基点）
    assert e["artifact_manifest_sha256"] == recompute_artifact_manifest_sha256(ROOT, BASE_COMMIT, "ditiansui")
    assert e["validator_code_sha256"] == recompute_validator_code_sha256(ROOT, BASE_COMMIT)
    assert e["historical_record_freeze_sha256"] == _sha_bytes(FREEZE_PATH.read_bytes())
    assert e["historical_generation_evidence_sha256"] == _sha_bytes(EVIDENCE_PATH.read_bytes())
    assert e["parent_commit"] == _git(ROOT, "rev-parse", "HEAD")
    # R 镜像通过 v2 复核
    r = _v2_receipt(e)
    assert verify_approval_receipt(r, e) is True
    # 执行器永不写回执
    assert not (tmp_path / "r.json").exists()


def test_v2_cli_missing_freeze_rejected(tmp_path):
    out = tmp_path / "e2.json"
    p = _run_make_e(
        "--schema-version", "2.0",
        "--book", "ditiansui",
        "--baseline", BASE_COMMIT,
        "--out", str(out),
        "--git-root", str(ROOT),
        "--evidence", str(EVIDENCE_PATH),
    )
    assert p.returncode != 0
    assert not out.exists()


def test_v2_cli_bad_baseline_rejected(tmp_path):
    out = tmp_path / "e2.json"
    p = _run_make_e(
        "--schema-version", "2.0",
        "--book", "ditiansui",
        "--baseline", "0" * 40,
        "--out", str(out),
        "--git-root", str(ROOT),
        "--freeze", str(FREEZE_PATH),
        "--evidence", str(EVIDENCE_PATH),
    )
    assert p.returncode != 0
    assert not out.exists()


def test_v2_cli_unknown_book_rejected(tmp_path):
    out = tmp_path / "e2.json"
    p = _run_make_e(
        "--schema-version", "2.0",
        "--book", "hacker",
        "--baseline", BASE_COMMIT,
        "--out", str(out),
        "--git-root", str(ROOT),
        "--freeze", str(FREEZE_PATH),
        "--evidence", str(EVIDENCE_PATH),
    )
    assert p.returncode != 0
    assert not out.exists()


def test_v1_cli_path_unchanged(tmp_path):
    # v1 路径不变：不带 --schema-version 仍生成 v1 E（含 reason，缺 v2 字段）
    repo = _tmp_git(tmp_path)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "validate_classic_distillation.py").write_text("# v", encoding="utf-8")
    book = repo / "knowledge_base" / "classic_texts" / "ditiansui"
    book.mkdir(parents=True)
    (book / "all_rules.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "b0"], check=True)
    b0 = _git(repo, "rev-parse", "HEAD")
    out = tmp_path / "e1.json"
    p = _run_make_e("--book", "ditiansui", "--baseline", b0, "--out", str(out), "--git-root", str(repo))
    assert p.returncode == 0, p.stderr
    e = load_exemption_request(out)
    assert e["schema_version"] == "1.0"
    assert "reason" in e
    assert "parent_commit" not in e
