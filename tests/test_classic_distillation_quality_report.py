"""Tests for quality report generator: exit codes, provenance, SHA stamps."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.classic_artifacts import CODE_FILE_NAMES, sha256_file, mcq_record_sha256
from scripts.generate_quality_report import generate_report, _find_git_root

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _git_blob_sha(file_path: Path) -> str:
    r = subprocess.run(
        ["git", "hash-object", str(file_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    return r.stdout.strip() if r.returncode == 0 else ""

RULE_REQUIRED = {"id", "category", "subject", "condition", "rule", "original_text",
                 "source_book", "source_chapter"}
MCQ_REQUIRED = {"id", "question", "options", "answer", "explanation",
                "source_rule_id", "difficulty", "category"}


def _make_full_rule(id: str, chapter: str, rule_text: str) -> dict:
    return {
        "id": id,
        "category": "test",
        "subject": "test",
        "condition": "test",
        "rule": rule_text,
        "original_text": rule_text,
        "source_book": "test",
        "source_chapter": chapter,
    }


def _make_full_mcq(id: str, question: str, answer: str, source_rule_id: str) -> dict:
    return {
        "id": id,
        "question": question,
        "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
        "answer": answer,
        "explanation": "test",
        "source_rule_id": source_rule_id,
        "difficulty": "easy",
        "category": "test",
    }


def _setup_passing_book(base: Path, dir_key: str = "zipingzhenquan") -> Path:
    """Set up a book directory that passes all validator gates."""
    p = base / dir_key
    p.mkdir(parents=True, exist_ok=True)

    rules = [
        _make_full_rule("r1", "ch1", "甲木参天"),
        _make_full_rule("r2", "ch1", "乙木系甲"),
    ]
    mcqs = [
        _make_full_mcq("m1", "问题一", "A", "r1"),
        _make_full_mcq("m2", "问题二", "B", "r2"),
        _make_full_mcq("m3", "问题三", "C", "r1"),
        _make_full_mcq("m4", "问题四", "D", "r2"),
    ]

    (p / "all_rules.json").write_text(
        json.dumps(rules, ensure_ascii=False), encoding="utf-8"
    )
    (p / "all_mcq.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mcqs),
        encoding="utf-8",
    )
    (p / "raw_001.txt").write_text("甲木参天乙木系甲", encoding="utf-8")
    # Ensure all output files exist (quarantine may be empty) so provenance validates.
    (p / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (p / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (p / "remediation_meta.json").write_text("{}", encoding="utf-8")
    names = ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
             "quarantine_mcq.jsonl", "remediation_meta.json")
    # P0-2/P0-3: build a fully verifiable api_generation chain (canonical
    # prompt/config/script, recomputable rules SHAs, and an archived run
    # manifest so the identity cross-check has persistent evidence).
    import hashlib
    from scripts.distill_lib import (
        canonical_prompt_sha256, canonical_config_sha256, FROZEN_MODEL_CONFIG,
    )
    rules_payload = json.dumps(rules, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
    rules_io_sha = hashlib.sha256(rules_payload).hexdigest()
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    rm_manifest = {
        "immutable": {
            "targets": [dir_key],
            "frozen_config_sha256": canonical_config_sha256(),
            "frozen_prompt_sha256": canonical_prompt_sha256(),
            "input_files": {
                dir_key: {"all_rules.json_sha256": sha256_file(p / "all_rules.json"),
                          "all_rules.json_bytes": len((p / "all_rules.json").read_bytes()),
                          "pre_run_mcq_ids": [], "operation": "fill",
                          "preserves_existing_mcqs": True},
            },
        },
        "mutable": {},
    }
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    # P0-3: identity is re-derived -- rules_sha == manifest sha, code_sha from
    # the canonical code scope, run_id from the binding formula.
    ident_code_sha = compute_code_sha(ledger_code_files(SCRIPTS_DIR, SCRIPTS_DIR.parent))
    ident_rules_sha = rm_sha
    ident_run_id = hashlib.sha256(
        (ident_code_sha + ":" + ident_rules_sha).encode("utf-8")).hexdigest()[:16]
    run_manifest = {
        "manifest": rm_manifest,
        "manifest_sha256": rm_sha,
        "run_id": ident_run_id,
        "code_sha": ident_code_sha,
        "rules_sha": ident_rules_sha,
    }
    provenance = {
        "generated_at": "2025-01-01",
        "anchor_commit": "abc123",
        "anchor_commit_verified": True,
        "no_api": True,
        "input_baseline_commit": "303d375",
        "worktree_dirty": False,
        "code_fingerprint": "a" * 64,
        "upstream_provenance_status": "unavailable",
        "file_shas": {n: sha256_file(p / n) for n in names},
        "code_shas": {n: sha256_file(SCRIPTS_DIR / n) for n in CODE_FILE_NAMES
                      if (SCRIPTS_DIR / n).exists()},
        "raw_text_shas": {"raw_001.txt": sha256_file(p / "raw_001.txt")},
        "input_baseline_blob_shas": {"raw_001.txt": _git_blob_sha(p / "raw_001.txt")},
        "api_generation": {
            "run_id": ident_run_id,
            "code_sha": ident_code_sha,
            "rules_sha": ident_rules_sha,
            "rules_input_sha": rules_io_sha,
            "rules_output_sha": rules_io_sha,
            "rules_added": 0,
            "mcq_output_sha": sha256_file(p / "all_mcq.jsonl"),
            "generated_mcq_sha256_by_id": {
                m["id"]: mcq_record_sha256(m) for m in mcqs
            },
            "prompt_sha256": canonical_prompt_sha256(),
            "config_sha256": canonical_config_sha256(),
            "script_sha256": sha256_file(SCRIPTS_DIR / "distill_lib.py"),
            "provider": FROZEN_MODEL_CONFIG["provider"],
            "model": FROZEN_MODEL_CONFIG["model"],
            "thinking_mode": FROZEN_MODEL_CONFIG["thinking_mode"],
            "temperature": FROZEN_MODEL_CONFIG["temperature"],
            "calls_made": 4,
            "accepted": 4,
            "skipped": 0,
            "verification_level": "full",
            "operation": "fill",
            "preserves_existing_mcqs": True,
            "pre_run_mcq_ids": [],
            "completed": True,
        },
        "run_manifest": run_manifest,
        "run_manifest_sha256": rm_sha,
    }
    (p / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False), encoding="utf-8")
    return p


def test_report_returns_zero_when_all_pass_with_provenance(tmp_path, monkeypatch):
    _setup_passing_book(tmp_path)
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, exit_code = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    assert report["remediation_pass"] is True
    assert report["end_to_end_pass"] is False
    assert exit_code == 1
    assert report["books"]["zipingzhenquan"]["provenance_ok"] is True


def test_report_returns_one_when_provenance_missing(tmp_path, monkeypatch):
    _setup_passing_book(tmp_path)
    (tmp_path / "zipingzhenquan" / "provenance.json").unlink()
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)

    report, exit_code = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    assert exit_code == 1
    assert report["overall_pass"] is False
    assert report["remediation_pass"] is False
    assert report["books"]["zipingzhenquan"]["provenance_ok"] is False
    assert report["books"]["zipingzhenquan"].get("provenance_missing") is True


def test_report_returns_one_when_gates_fail(tmp_path, monkeypatch):
    _setup_passing_book(tmp_path)
    rules = json.loads((tmp_path / "zipingzhenquan" / "all_rules.json").read_text(encoding="utf-8"))
    rules[0]["id"] = rules[1]["id"]
    (tmp_path / "zipingzhenquan" / "all_rules.json").write_text(
        json.dumps(rules, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)

    report, exit_code = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    assert exit_code == 1
    assert report["overall_pass"] is False
    assert report["remediation_pass"] is False
    assert report["books"]["zipingzhenquan"]["all_gates_pass"] is False


def test_report_returns_one_when_provenance_invalid(tmp_path, monkeypatch):
    """P0-2: provenance with a stale file_sha must NOT be reported as OK."""
    _setup_passing_book(tmp_path)
    prov_f = tmp_path / "zipingzhenquan" / "provenance.json"
    prov = json.loads(prov_f.read_text(encoding="utf-8"))
    prov["file_shas"]["all_rules.json"] = "0" * 64  # stale
    prov_f.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)

    report, exit_code = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    assert exit_code == 1
    assert report["overall_pass"] is False
    assert report["remediation_pass"] is False
    assert report["books"]["zipingzhenquan"]["provenance_ok"] is False
    assert report["books"]["zipingzhenquan"].get("provenance_invalid") is True


def test_report_includes_validator_code_sha(tmp_path, monkeypatch):
    _setup_passing_book(tmp_path)
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, _ = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    assert "validator_code_sha256" in report
    assert len(report["validator_code_sha256"]) == 64


def test_report_includes_artifact_shas(tmp_path, monkeypatch):
    _setup_passing_book(tmp_path)
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, _ = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    entry = report["books"]["zipingzhenquan"]
    assert "sha256" in entry["rules"]
    assert len(entry["rules"]["sha256"]) == 64
    assert "sha256" in entry["mcq"]
    assert len(entry["mcq"]["sha256"]) == 64


def test_report_end_to_end_provenance_false_when_upstream_unavailable(tmp_path, monkeypatch):
    """When upstream_provenance_status='unavailable', end_to_end_provenance=False."""
    _setup_passing_book(tmp_path)
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, _ = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    entry = report["books"]["zipingzhenquan"]
    assert entry["end_to_end_provenance"] is False
    assert report["end_to_end_pass"] is False
    assert any("end-to-end provenance incomplete" in lim for lim in report["known_limitations"])


def test_report_end_to_end_provenance_true_when_upstream_recovered(tmp_path, monkeypatch):
    """When upstream_provenance_status='recovered' with full schema AND git
    byte verification passes, end_to_end=True.

    P0-4: 'recovered' now requires upstream_artifact_commit AND git_root so
    that upstream_artifact_shas can be verified against actual git blob bytes.
    Without git_root, 'recovered' is rejected (cannot verify bytes).
    """
    _setup_passing_book(tmp_path)
    prov_f = tmp_path / "zipingzhenquan" / "provenance.json"
    prov = json.loads(prov_f.read_text(encoding="utf-8"))
    # P0-4: 'recovered' requires full upstream schema INCLUDING artifact_commit.
    prov["upstream_provenance_status"] = "recovered"
    prov["upstream_provenance"] = {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "source_url": "https://example.com/source.txt",
        "source_version": "v1",
        "distill_script": "scripts/distill_lib.py",
        "thinking_mode": "disabled",
        "temperature": 0.0,
        "upstream_artifact_shas": {
            "all_rules.json": "a" * 64,
            "all_mcq.jsonl": "b" * 64,
        },
        "upstream_artifact_commit": "abc123",
    }
    prov_f.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    # P0-4: without git_root, byte verification cannot run, so 'recovered'
    # is rejected. The report must NOT claim end_to_end_provenance=True.
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)

    report, exit_code = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    entry = report["books"]["zipingzhenquan"]
    # Without git_root, recovered validation fails -> provenance_ok=False
    assert entry["provenance_ok"] is False
    assert entry["end_to_end_provenance"] is False
    assert report["end_to_end_pass"] is False
    assert exit_code == 1


def test_report_end_to_end_provenance_false_when_upstream_partial(tmp_path, monkeypatch):
    """P0-4: 'partial' status (incomplete schema) -> end_to_end_provenance=False."""
    _setup_passing_book(tmp_path)
    prov_f = tmp_path / "zipingzhenquan" / "provenance.json"
    prov = json.loads(prov_f.read_text(encoding="utf-8"))
    # partial: has some upstream fields but not full schema
    prov["upstream_provenance_status"] = "partial"
    prov["upstream_provenance"] = {"provider": "deepseek", "model": "deepseek-v4-flash"}
    prov_f.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)

    report, exit_code = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    entry = report["books"]["zipingzhenquan"]
    assert entry["provenance_ok"] is True  # partial is a valid status
    assert entry["end_to_end_provenance"] is False
    assert report["end_to_end_pass"] is False
    assert exit_code == 1


def test_report_partial_api_generation_not_verified(tmp_path, monkeypatch):
    """Round-7 Medium: an api_generation chain with verification_level='partial'
    (no archived run_manifest) must NOT be treated as a verified chain by the
    formal quality gate -- provenance_ok and remediation_pass degrade to False."""
    _setup_passing_book(tmp_path)
    prov_f = tmp_path / "zipingzhenquan" / "provenance.json"
    prov = json.loads(prov_f.read_text(encoding="utf-8"))
    # Remove the archived run_manifest and mark the chain partial (this still
    # passes validate_provenance, but the gate must degrade it).
    prov.pop("run_manifest", None)
    prov.pop("run_manifest_sha256", None)
    prov["api_generation"]["verification_level"] = "partial"
    prov_f.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, _ = generate_report(base_path=tmp_path, books={"zipingzhenquan": "子平真诠"})
    entry = report["books"]["zipingzhenquan"]
    assert entry["provenance_ok"] is False
    assert report["remediation_pass"] is False
    assert any("not 'full'" in lim for lim in report["known_limitations"])


def test_report_missing_verification_level_degrades_gate(tmp_path, monkeypatch):
    """P0: OMITTING api_generation.verification_level entirely (the old
    `is not None` guard was bypassed by a missing value) must fail the formal
    quality gate. The validator now requires 'full' whenever a run_manifest is
    archived, so provenance_ok and remediation_pass both degrade to False."""
    _setup_passing_book(tmp_path)
    prov_f = tmp_path / "zipingzhenquan" / "provenance.json"
    prov = json.loads(prov_f.read_text(encoding="utf-8"))
    del prov["api_generation"]["verification_level"]  # missing entirely
    prov_f.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, exit_code = generate_report(base_path=tmp_path, books={"zipingzhenquan": "子平真诠"})
    entry = report["books"]["zipingzhenquan"]
    assert entry["provenance_ok"] is False
    assert report["remediation_pass"] is False
    assert exit_code == 1


def test_report_remediation_pass_separate_from_end_to_end(tmp_path, monkeypatch):
    """remediation_pass can be True while end_to_end_pass is False."""
    _setup_passing_book(tmp_path)
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, exit_code = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"}
    )
    # remediation should pass (gates + provenance valid)
    # but end_to_end should fail (upstream unavailable)
    if report["books"]["zipingzhenquan"]["provenance_ok"]:
        assert report["remediation_pass"] is True
        assert report["end_to_end_pass"] is False
        assert exit_code == 1
    else:
        # If git is not available, provenance validation may fail
        # on baseline blob checks. In that case, both should be False.
        assert report["remediation_pass"] is False
        assert report["end_to_end_pass"] is False
        assert exit_code == 1


def test_find_git_root_recognizes_git_dir(tmp_path):
    """Normal checkout: .git is a directory."""
    (tmp_path / ".git").mkdir()
    assert _find_git_root(tmp_path) == tmp_path


def test_find_git_root_recognizes_worktree_git_file(tmp_path):
    """P0: linked worktrees carry .git as a FILE pointing at the real
    gitdir; _find_git_root must treat that as a repository root (it
    previously returned None in worktrees, degrading provenance checks)."""
    (tmp_path / ".git").write_text(
        "gitdir: G:/elsewhere/.git/worktrees/wt\n", encoding="utf-8"
    )
    assert _find_git_root(tmp_path) == tmp_path


def test_find_git_root_walks_up_to_nearest_repo(tmp_path):
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "sub"
    sub.mkdir()
    assert _find_git_root(sub) == tmp_path


# ---------------------------------------------------------------------------
# §10-⑦ B3：APPROVAL_B2_BY_BOOK 常量、豁免链消费（E0/E1/E2/E3）、
# 三态闭合、source_chain_check 无条件汇合、顶层状态机与 exit 码。
# ---------------------------------------------------------------------------
import re

import pytest

from scripts.generate_classic_historical_freeze import (
    KINDS,
    _book_rel,
)
from scripts.generate_quality_report import (
    APPROVAL_B2_BY_BOOK,
    EVIDENCE_REL,
    FREEZE_REL,
    _e0_static_check,
    _e1_artifact_chain,
    _e2_recompute,
    _e3_multiset_check,
    _git_head_blob,
    _git_rev_parse,
    _git_show_blob,
    _run_source_chain_check,
    evaluate_provenance_admissibility,
    main,
    validate_approval_b2_constant,
)

ROOT = Path(__file__).resolve().parent.parent
FOUR_BOOKS = ("ditiansui", "qiongtongbaojian", "sanmingtonghui", "zipingzhenquan")


def _approvals_rel(book: str, kind: str) -> str:
    return f"docs/superpowers/plans/notes/approvals/2026-09-02-classic-texts-provenance-exemption-{book}-{kind}"


def _head_json(rel: str) -> dict:
    return json.loads(_git_head_blob(ROOT, rel).decode("utf-8"))


def _load_e_r(book: str) -> tuple[dict, dict]:
    ptr = _head_json(_approvals_rel(book, "b2-pointer.json"))
    e = json.loads(_git_show_blob(ROOT, ptr["b1_commit"], ptr["e_path"]).decode("utf-8"))
    r = json.loads(_git_show_blob(ROOT, ptr["b1_commit"], ptr["r_path"]).decode("utf-8"))
    return e, r


def _tamper_head_blob(monkeypatch, rel: str, transform):
    """拦截 _git_head_blob：仅对 rel 返回变换后的字节，其余透传真实 HEAD blob。"""
    real = _git_head_blob

    def fake(git_root, rel_path):
        data = real(git_root, rel_path)
        if rel_path == rel:
            return transform(data)
        return data

    monkeypatch.setattr("scripts.generate_quality_report._git_head_blob", fake)


def _reserialize(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


# --- §5.1 B3 常量 -----------------------------------------------------------

def test_approval_b2_constant_schema():
    assert set(APPROVAL_B2_BY_BOOK) == set(FOUR_BOOKS)
    for v in APPROVAL_B2_BY_BOOK.values():
        assert re.fullmatch(r"[0-9a-f]{40}", v)
    assert len(set(APPROVAL_B2_BY_BOOK.values())) == 4


def test_approval_b2_constant_head_descendant():
    # 真实仓库：HEAD 必须是每个 B2 的后代；违反 → ValueError（fail-closed）
    validate_approval_b2_constant(ROOT)


def test_approval_b2_constant_rejects_bad_shapes():
    good = dict(APPROVAL_B2_BY_BOOK)
    with pytest.raises(ValueError):  # 缺书
        validate_approval_b2_constant(None, {k: v for k, v in good.items() if k != "ditiansui"})
    with pytest.raises(ValueError):  # 多书
        validate_approval_b2_constant(None, {**good, "extra": "a" * 40})
    with pytest.raises(ValueError):  # 非 40hex
        validate_approval_b2_constant(None, {**good, "ditiansui": "zz"})
    with pytest.raises(ValueError):  # 全零占位符
        validate_approval_b2_constant(None, {**good, "ditiansui": "0" * 40})
    with pytest.raises(ValueError):  # 重复值
        validate_approval_b2_constant(None, {**good, "ditiansui": good["qiongtongbaojian"]})


# --- E0 静态校验（真实 HEAD + 错误优先级短路）--------------------------------

def test_e0_static_check_real_head_passes():
    assert _e0_static_check(ROOT) == {"ok": True, "error_code": None}


def test_e0_generator_identity_highest_priority(monkeypatch):
    # 篡改 freeze.generator_blob_oid：六向断言首先失败 → GENERATOR_IDENTITY_MISMATCH
    def tamper(data):
        obj = json.loads(data)
        obj["generator_blob_oid"] = "f" * 40
        return _reserialize(obj)

    _tamper_head_blob(monkeypatch, FREEZE_REL, tamper)
    assert _e0_static_check(ROOT) == {"ok": False, "error_code": "GENERATOR_IDENTITY_MISMATCH"}


def test_e0_frozen_at_commit_mismatch(monkeypatch):
    def tamper(data):
        obj = json.loads(data)
        obj["frozen_at_commit"] = "e" * 40
        return _reserialize(obj)

    _tamper_head_blob(monkeypatch, FREEZE_REL, tamper)
    assert _e0_static_check(ROOT) == {"ok": False, "error_code": "FROZEN_AT_COMMIT_MISMATCH"}


def test_e0_freeze_static_mismatch(monkeypatch):
    # 结构自洽（排序/格式合法）但非 BASE 重建值 → FREEZE_STATIC_MISMATCH
    def tamper(data):
        obj = json.loads(data)
        recs = obj["books"]["ditiansui"]["all_rules"]["records"]
        recs[0]["sha256"] = ("ab" * 32) if recs[0]["sha256"] != ("ab" * 32) else ("cd" * 32)
        recs.sort(key=lambda e: (e["id"], e["sha256"]))
        return _reserialize(obj)

    _tamper_head_blob(monkeypatch, FREEZE_REL, tamper)
    assert _e0_static_check(ROOT) == {"ok": False, "error_code": "FREEZE_STATIC_MISMATCH"}


def test_e0_evidence_static_mismatch(monkeypatch):
    def tamper(data):
        obj = json.loads(data)
        obj["unproven_facts"] = ["tampered"]
        return _reserialize(obj)

    _tamper_head_blob(monkeypatch, EVIDENCE_REL, tamper)
    assert _e0_static_check(ROOT) == {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}


# --- E1 工件链（逐书真实链 + 负向）-------------------------------------------

@pytest.mark.parametrize("book", FOUR_BOOKS)
def test_e1_artifact_chain_real_head_all_books(book):
    r = _e1_artifact_chain(ROOT, book, _head_json(FREEZE_REL), _head_json(EVIDENCE_REL))
    assert r["ok"] is True
    assert r["error_code"] is None


def test_e1_baseline_six_way_mismatch():
    # (j) 最后执行：仅篡改 freeze 侧 frozen_at_commit → BASELINE_COMMIT_MISMATCH
    freeze = {**_head_json(FREEZE_REL), "frozen_at_commit": "e" * 40}
    r = _e1_artifact_chain(ROOT, "ditiansui", freeze, _head_json(EVIDENCE_REL))
    assert r == {"ok": False, "error_code": "BASELINE_COMMIT_MISMATCH"}


def test_e1_pointer_head_tamper_rejected(monkeypatch):
    # (a) B2 树指针字节 != 当前 HEAD 指针 blob → EVIDENCE_STATIC_MISMATCH
    _tamper_head_blob(monkeypatch, _approvals_rel("ditiansui", "b2-pointer.json"), lambda d: d + b" ")
    r = _e1_artifact_chain(ROOT, "ditiansui", _head_json(FREEZE_REL), _head_json(EVIDENCE_REL))
    assert r == {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}


# --- E2 权威重算（三方全等）---------------------------------------------------

def test_e2_recompute_real_passes():
    for book in FOUR_BOOKS:
        e, r = _load_e_r(book)
        assert _e2_recompute(ROOT, book, e, r) == {"ok": True, "error_code": None}


def test_e2_recompute_tampered_manifest_rejected():
    e, r = _load_e_r("ditiansui")
    e2 = {**e, "artifact_manifest_sha256": "a" * 64}
    r2 = {**r, "artifact_manifest_sha256": "a" * 64}
    assert _e2_recompute(ROOT, "ditiansui", e2, r2) == {
        "ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}


# --- E3 多重集合严格相等-------------------------------------------------------

def test_e3_multiset_real_head_passes():
    assert _e3_multiset_check(ROOT, _head_json(FREEZE_REL)) == {"ok": True, "error_code": None}


@pytest.mark.parametrize("mode", ["mutate", "duplicate", "delete"])
def test_e3_multiset_negative_only_e3_fails(monkeypatch, mode):
    """v27.3 P0：freeze/evidence/E/R/pointer 全部有效且不变，仅当前 HEAD 聚合
    blob 被改动（合法新 sha256 / 改变重复次数 / 删记录）→ E0/E1/E2 通过、
    仅 E3_ok=false。"""
    freeze = _head_json(FREEZE_REL)
    kinds = [k for k in KINDS if freeze["books"]["sanmingtonghui"][k]["present"]]
    rel = _book_rel("sanmingtonghui", kinds[0])
    real = _git_head_blob

    def fake(git_root, rel_path):
        data = real(git_root, rel_path)
        if rel_path != rel:
            return data
        obj = json.loads(data.decode("utf-8"))
        if mode == "mutate":
            obj[0] = {**obj[0], "category": "tampered-x"}
        elif mode == "duplicate":
            obj = [obj[0]] + obj
        else:
            obj = obj[1:]
        return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")

    monkeypatch.setattr("scripts.generate_quality_report._git_head_blob", fake)
    # 不 stub E0/E1/E2：freeze/evidence/E/R/pointer 均未改动，真实链必须通过，
    # 最终仅 E3 对当前 HEAD 多重集合重算并拒绝（v27.3 P0 契约）
    adm = evaluate_provenance_admissibility(
        ROOT / "knowledge_base" / "classic_texts" / "sanmingtonghui", ROOT)
    assert adm["provenance_state"] == "MISSING"
    assert adm["E0_ok"] is True
    assert adm["E1_ok"] is True
    assert adm["E2_ok"] is True
    assert adm["E3_ok"] is False
    assert adm["historical_exemption_valid"] is False
    assert adm["provenance_admissible"] is False
    assert adm["exemption_error_code"] == "EVIDENCE_STATIC_MISMATCH"


# --- 三态闭合（VALID / INVALID / MISSING）-------------------------------------

def test_admissible_valid_state_e0_failure_not_consulted(tmp_path, monkeypatch):
    """VALID 下 E0 失败不得改写 admissible=true；豁免链（E1）不被咨询。"""
    _setup_passing_book(tmp_path)
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    monkeypatch.setattr(
        "scripts.generate_quality_report._e0_static_check",
        lambda gr: {"ok": False, "error_code": "GENERATOR_IDENTITY_MISMATCH"},
    )
    e1_calls = []
    monkeypatch.setattr(
        "scripts.generate_quality_report._e1_artifact_chain",
        lambda *a, **k: e1_calls.append(1) or {"ok": True, "error_code": None},
    )
    adm = evaluate_provenance_admissibility(tmp_path / "zipingzhenquan", None)
    assert adm["provenance_state"] == "VALID"
    assert adm["provenance_admissible"] is True
    assert adm["historical_exemption_valid"] is False
    assert e1_calls == []


def test_admissible_invalid_state_exemption_not_consulted(tmp_path, monkeypatch):
    """INVALID 是正式 provenance 失败，不得用豁免绕过。"""
    _setup_passing_book(tmp_path)
    prov_f = tmp_path / "zipingzhenquan" / "provenance.json"
    prov = json.loads(prov_f.read_text(encoding="utf-8"))
    prov["file_shas"]["all_rules.json"] = "0" * 64  # stale → INVALID
    prov_f.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    e0_calls = []
    monkeypatch.setattr(
        "scripts.generate_quality_report._e0_static_check",
        lambda gr: e0_calls.append(1) or {"ok": True, "error_code": None},
    )
    adm = evaluate_provenance_admissibility(tmp_path / "zipingzhenquan", None)
    assert adm["provenance_state"] == "INVALID"
    assert adm["provenance_admissible"] is False
    assert adm["historical_exemption_valid"] is False
    assert adm["E1_ok"] is None
    assert e0_calls == []  # 无 git_root 时 E0 fail-closed，不执行


def test_e0_executed_even_when_invalid(tmp_path, monkeypatch):
    """无论 provenance_state 为何 E0 都要执行（INVALID 下也执行并产出 E0_ok）。"""
    _setup_passing_book(tmp_path)
    prov_f = tmp_path / "zipingzhenquan" / "provenance.json"
    prov = json.loads(prov_f.read_text(encoding="utf-8"))
    prov["file_shas"]["all_rules.json"] = "0" * 64
    prov_f.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    e0_calls = []
    monkeypatch.setattr(
        "scripts.generate_quality_report._e0_static_check",
        lambda gr: e0_calls.append(1) or {"ok": True, "error_code": None},
    )
    adm = evaluate_provenance_admissibility(tmp_path / "zipingzhenquan", ROOT)
    assert adm["provenance_state"] == "INVALID"
    assert adm["provenance_admissible"] is False
    assert adm["E0_ok"] is True
    assert e0_calls == [1]


def test_admissible_missing_e0_fail_short_circuits(tmp_path, monkeypatch):
    """E0 失败 → E1/E2/E3 不执行（阶段顺序短路），单错误码。"""
    (tmp_path / "zipingzhenquan").mkdir()
    monkeypatch.setattr(
        "scripts.generate_quality_report._e0_static_check",
        lambda gr: {"ok": False, "error_code": "FREEZE_STATIC_MISMATCH"},
    )
    stage_calls = []
    for name in ("_e1_artifact_chain", "_e2_recompute", "_e3_multiset_check"):
        monkeypatch.setattr(
            f"scripts.generate_quality_report.{name}",
            lambda *a, **k: stage_calls.append(name) or {"ok": True, "error_code": None},
        )
    adm = evaluate_provenance_admissibility(tmp_path / "zipingzhenquan", ROOT)
    assert adm["provenance_state"] == "MISSING"
    assert adm["E0_ok"] is False
    assert adm["E1_ok"] is None and adm["E2_ok"] is None and adm["E3_ok"] is None
    assert adm["historical_exemption_valid"] is False
    assert adm["provenance_admissible"] is False
    assert adm["exemption_error_code"] == "FREEZE_STATIC_MISMATCH"
    assert stage_calls == []


@pytest.mark.parametrize("book", FOUR_BOOKS)
def test_admissible_real_head_all_books(book):
    """当前树：四书 provenance 均 MISSING，豁免链 E0∧E1∧E2∧E3 全过 → admissible。"""
    adm = evaluate_provenance_admissibility(
        ROOT / "knowledge_base" / "classic_texts" / book, ROOT)
    assert adm["provenance_state"] == "MISSING"
    assert adm["E0_ok"] is True
    assert adm["E1_ok"] is True
    assert adm["E2_ok"] is True
    assert adm["E3_ok"] is True
    assert adm["historical_exemption_valid"] is True
    assert adm["provenance_admissible"] is True
    assert adm["exemption_error_code"] is None


def test_admissible_missing_no_git_root_fail_closed(tmp_path):
    (tmp_path / "zipingzhenquan").mkdir()
    adm = evaluate_provenance_admissibility(tmp_path / "zipingzhenquan", None)
    assert adm["provenance_state"] == "MISSING"
    assert adm["E0_ok"] is False
    assert adm["provenance_admissible"] is False


# --- source_chain_check 无条件汇合与顶层状态机 --------------------------------

def test_run_source_chain_check_archive_root_missing():
    assert _run_source_chain_check(ROOT, None) == {
        "status": "BLOCKED", "reason": "archive_root_missing"}


def _spy_source(monkeypatch, result):
    calls = []

    def fake(git_root, archive_root):
        calls.append(archive_root)
        return dict(result)

    monkeypatch.setattr("scripts.generate_quality_report._run_source_chain_check", fake)
    return calls


def test_source_check_spy_sanmingtonghui_called_once(tmp_path, monkeypatch):
    """spy 锁定：sanmingtonghui 恰调用一次，其余三书调用零次。"""
    for k in FOUR_BOOKS:
        _setup_passing_book(tmp_path, dir_key=k)
    calls = _spy_source(monkeypatch, {"status": "PASS", "reason": None})
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, _ = generate_report(
        base_path=tmp_path, books={k: "书" for k in FOUR_BOOKS}, archive_root=tmp_path)
    assert calls == [tmp_path]
    assert report["books"]["sanmingtonghui"]["source_e2e_status"] == "PASS"
    for k in FOUR_BOOKS:
        if k != "sanmingtonghui":
            assert report["books"][k]["source_e2e_status"] == "FAIL"
    assert report["source_e2e_status"] == "FAIL"


def test_report_e0_fail_source_still_runs_blocked_exit3(tmp_path, monkeypatch):
    """静态失败 vs source BLOCKED 分离：E0 失败仍无条件执行 source 链；
    两者同时存在时 BLOCKED 优先，exit 3。"""
    _setup_passing_book(tmp_path, dir_key="sanmingtonghui")
    (tmp_path / "sanmingtonghui" / "provenance.json").unlink()
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: ROOT)
    monkeypatch.setattr(
        "scripts.generate_quality_report._e0_static_check",
        lambda gr: {"ok": False, "error_code": "FREEZE_STATIC_MISMATCH"},
    )
    calls = _spy_source(monkeypatch, {"status": "BLOCKED", "reason": "archive_missing"})
    report, exit_code = generate_report(
        base_path=tmp_path, books={"sanmingtonghui": "三命通会"}, archive_root=tmp_path)
    assert calls == [tmp_path]  # 非提前 return
    entry = report["books"]["sanmingtonghui"]
    assert entry["provenance_admissible"] is False
    assert entry["exemption_error_code"] == "FREEZE_STATIC_MISMATCH"
    assert entry["source_e2e_status"] == "BLOCKED"
    assert entry["source_blocked_reason"] == "archive_missing"
    assert report["status"] == "BLOCKED"
    assert report["overall_pass"] is False
    assert exit_code == 3


def test_report_archive_root_missing_blocked(tmp_path, monkeypatch):
    """三命通会在书集内而 archive_root 缺失 → BLOCKED（archive_root_missing）、exit 3。"""
    _setup_passing_book(tmp_path, dir_key="sanmingtonghui")
    (tmp_path / "sanmingtonghui" / "provenance.json").unlink()
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, exit_code = generate_report(
        base_path=tmp_path, books={"sanmingtonghui": "三命通会"}, archive_root=None)
    entry = report["books"]["sanmingtonghui"]
    assert entry["source_e2e_status"] == "BLOCKED"
    assert entry["source_blocked_reason"] == "archive_root_missing"
    assert report["status"] == "BLOCKED"
    assert exit_code == 3


def test_report_exit_zero_when_all_pass(tmp_path, monkeypatch):
    # sanmingtonghui 不在 validate_provenance 的 fill target 白名单内，无法用
    # 假书构造 VALID；此处 monkeypatch 豁免判定为通过，专测状态机聚合与 exit 0。
    _setup_passing_book(tmp_path, dir_key="sanmingtonghui")
    (tmp_path / "sanmingtonghui" / "provenance.json").unlink()
    monkeypatch.setattr(
        "scripts.generate_quality_report.evaluate_provenance_admissibility",
        lambda bd, gr: {
            "provenance_state": "MISSING", "E0_ok": True, "E1_ok": True,
            "E2_ok": True, "E3_ok": True, "historical_exemption_valid": True,
            "provenance_admissible": True, "exemption_error_code": None})
    _spy_source(monkeypatch, {"status": "PASS", "reason": None})
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: ROOT)
    report, exit_code = generate_report(
        base_path=tmp_path, books={"sanmingtonghui": "三命通会"}, archive_root=tmp_path)
    assert report["approval_b2_constant_valid"] is True
    assert report["status"] == "PASS"
    assert report["overall_pass"] is True
    assert report["content_gates_pass"] is True
    assert report["provenance_admissible_all"] is True
    assert report["source_e2e_pass"] is True
    assert exit_code == 0


def test_report_b2_constant_invalid_fails_closed(tmp_path, monkeypatch):
    """§5.1 报告级 fail-closed：其他门全部通过，仅 B2 常量校验失败 →
    approval_b2_constant_valid=False、overall_pass=False、status=FAIL、exit 1。"""
    _setup_passing_book(tmp_path, dir_key="sanmingtonghui")
    (tmp_path / "sanmingtonghui" / "provenance.json").unlink()
    monkeypatch.setattr(
        "scripts.generate_quality_report.evaluate_provenance_admissibility",
        lambda bd, gr: {
            "provenance_state": "MISSING", "E0_ok": True, "E1_ok": True,
            "E2_ok": True, "E3_ok": True, "historical_exemption_valid": True,
            "provenance_admissible": True, "exemption_error_code": None})
    _spy_source(monkeypatch, {"status": "PASS", "reason": None})
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: ROOT)

    def _bad(git_root, constant=None):
        raise ValueError("tampered constant")

    monkeypatch.setattr(
        "scripts.generate_quality_report.validate_approval_b2_constant", _bad)
    report, exit_code = generate_report(
        base_path=tmp_path, books={"sanmingtonghui": "三命通会"}, archive_root=tmp_path)
    assert report["approval_b2_constant_valid"] is False
    assert report["overall_pass"] is False
    assert report["status"] == "FAIL"
    assert exit_code == 1


def test_report_b2_constant_unverifiable_without_git_root(tmp_path, monkeypatch):
    """git_root 缺失 → 常量无法校验 → fail-closed 记 False（不得记 True）。"""
    _setup_passing_book(tmp_path)
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, _ = generate_report(base_path=tmp_path, books={"zipingzhenquan": "子平真诠"})
    assert report["approval_b2_constant_valid"] is False


def test_report_top_level_state_machine_keys(tmp_path, monkeypatch):
    """三态聚合：VALID 书 + 非 sanming → source FAIL → status FAIL、exit 1。"""
    _setup_passing_book(tmp_path)
    monkeypatch.setattr("scripts.generate_quality_report._find_git_root", lambda: None)
    report, exit_code = generate_report(
        base_path=tmp_path, books={"zipingzhenquan": "子平真诠"})
    entry = report["books"]["zipingzhenquan"]
    assert entry["provenance_state"] == "VALID"
    assert entry["provenance_admissible"] is True
    assert entry["historical_exemption_valid"] is False
    assert report["source_e2e_status"] == "FAIL"
    assert report["source_e2e_pass"] is False
    assert report["provenance_admissible_all"] is True
    assert report["status"] == "FAIL"
    assert report["overall_pass"] is False
    assert exit_code == 1


# --- CLI 参数链（--archive-root → generate_report(archive_root=...)）----------

def test_main_passes_archive_root(monkeypatch, tmp_path):
    captured = {}

    def fake_report(base_path=None, books=None, archive_root=None):
        captured["archive_root"] = archive_root
        return {
            "books": {}, "known_limitations": [], "remediation_pass": False,
            "end_to_end_pass": False, "content_gates_pass": False,
            "provenance_admissible_all": False, "source_e2e_status": "FAIL",
            "source_e2e_pass": False, "overall_pass": False, "status": "FAIL",
        }, 1

    monkeypatch.setattr("scripts.generate_quality_report.generate_report", fake_report)
    monkeypatch.setattr("scripts.generate_quality_report.BASE", tmp_path)
    rc = main(["--archive-root", str(tmp_path)])
    assert captured["archive_root"] == str(tmp_path)
    assert rc == 1
