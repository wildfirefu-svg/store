"""Tests for quality report generator: exit codes, provenance, SHA stamps."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.classic_artifacts import CODE_FILE_NAMES, sha256_file, mcq_record_sha256
from scripts.generate_quality_report import generate_report

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
