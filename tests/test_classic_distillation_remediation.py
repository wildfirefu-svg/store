"""Tests for classic distillation remediation: conservation, staging atomicity, provenance."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from scripts.classic_artifacts import (
    CODE_FILE_NAMES,
    ConservationError,
    mcq_fp,
    rule_fp,
    sha256_file,
    validate_provenance,
    verify_conservation,
)
from scripts.remediate_classic_distillation import (
    SCRIPTS_DIR,
    _publish,
    remediate_book,
)

# Note: remediate_book builds a staging dir under base_path and publishes there.


def _make_rule(id: str, chapter: str, rule_text: str, original_text: str = "") -> dict:
    return {
        "id": id,
        "source_chapter": chapter,
        "rule": rule_text,
        "original_text": original_text,
    }


def _make_mcq(id: str, question: str, options: dict, answer: str, source_rule_id: str = "") -> dict:
    return {
        "id": id,
        "question": question,
        "options": options,
        "answer": answer,
        "source_rule_id": source_rule_id,
    }


def _setup_book(
    tmp_path: Path,
    rules: list[dict],
    mcqs: list[dict],
    raw_text: str = "原文内容",
    existing_q_rules: list[dict] | None = None,
    existing_q_mcqs: list[dict] | None = None,
) -> Path:
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text(
        json.dumps(rules, ensure_ascii=False), encoding="utf-8"
    )
    (book_dir / "all_mcq.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mcqs),
        encoding="utf-8",
    )
    (book_dir / "raw_001.txt").write_text(raw_text, encoding="utf-8")
    if existing_q_rules is not None:
        (book_dir / "quarantine_rules.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in existing_q_rules),
            encoding="utf-8",
        )
    if existing_q_mcqs is not None:
        (book_dir / "quarantine_mcq.jsonl").write_text(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in existing_q_mcqs),
            encoding="utf-8",
        )
    return book_dir


def _load_rules(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(l)
        for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


# ---------------------------------------------------------------------------
# verify_conservation unit tests
# ---------------------------------------------------------------------------


def test_verify_conservation_passes_when_multisets_match():
    verify_conservation(
        [_make_rule("r1", "ch1", "甲木")], [],
        [_make_rule("r1", "ch1", "甲木")], [], rule_fp,
    )


def test_verify_conservation_fails_when_item_dropped():
    with pytest.raises(ConservationError, match="lost"):
        verify_conservation(
            [_make_rule("r1", "ch1", "甲木"), _make_rule("r2", "ch1", "乙木")], [],
            [_make_rule("r1", "ch1", "甲木")], [], rule_fp,
        )


def test_verify_conservation_fails_when_item_gained():
    with pytest.raises(ConservationError, match="gained"):
        verify_conservation(
            [_make_rule("r1", "ch1", "甲木")], [],
            [_make_rule("r1", "ch1", "甲木")],
            [_make_rule("r2", "ch1", "乙木")], rule_fp,
        )


# ---------------------------------------------------------------------------
# P0-4: fingerprints cover full canonical content
# ---------------------------------------------------------------------------


def test_rule_fp_detects_original_text_tampering():
    a = _make_rule("r1", "ch1", "甲木", "甲木参天")
    b = _make_rule("r1", "ch1", "甲木", "乙木系甲")  # same rule, different original_text
    assert rule_fp(a) != rule_fp(b)


def test_rule_fp_detects_condition_tampering():
    a = _make_rule("r1", "ch1", "甲木")
    a["condition"] = "有根"
    b = _make_rule("r1", "ch1", "甲木")
    b["condition"] = "无根"
    assert rule_fp(a) != rule_fp(b)


def test_mcq_fp_detects_option_body_tampering():
    a = _make_mcq("m1", "问题", {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "A", "r1")
    b = _make_mcq("m1", "问题", {"A": "甲", "B": "乙", "C": "丙", "D": "戊"}, "A", "r1")
    assert mcq_fp(a) != mcq_fp(b)


def test_mcq_fp_invariant_to_label_rotation():
    # Rotating labels (answer rotation) must NOT change the fingerprint.
    a = _make_mcq("m1", "问题", {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "A", "r1")
    b = _make_mcq("m1", "问题", {"A": "丙", "B": "乙", "C": "甲", "D": "丁"}, "C", "r1")
    assert mcq_fp(a) == mcq_fp(b)


def test_mcq_fp_covers_explanation():
    a = _make_mcq("m1", "问题", {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "A", "r1")
    a["explanation"] = "解析一"
    b = _make_mcq("m1", "问题", {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "A", "r1")
    b["explanation"] = "解析二"
    assert mcq_fp(a) != mcq_fp(b)


# ---------------------------------------------------------------------------
# Remediation integration: conservation holds on final disk (P0-1)
# ---------------------------------------------------------------------------


def test_conservation_holds_after_remediation(tmp_path):
    rules = [
        _make_rule("old_001", "第一章", "甲木生春月", "甲木生春月"),
        _make_rule("old_002", "第一章", "乙木生夏月", "乙木生夏月"),
    ]
    mcqs = [
        _make_mcq("m1", "问题一", {"A": "春", "B": "夏", "C": "秋", "D": "冬"}, "A", "old_001"),
    ]
    _setup_book(tmp_path, rules, mcqs, raw_text="甲木生春月乙木生夏月")

    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    book_dir = tmp_path / "testbook"
    clean = _load_rules(book_dir / "all_rules.json")
    q = _load_jsonl(book_dir / "quarantine_rules.jsonl")
    verify_conservation(rules, [], clean, q, rule_fp, "rules")


def test_cross_chapter_merge_keeps_conservation_on_disk(tmp_path):
    """R7 merges cross-chapter duplicates; conservation must hold on FINAL disk.

    This is the scenario that previously "lost 4 rules" because the append step
    deduplicated by fingerprint. The staging approach must not lose anything.
    """
    rules = [
        _make_rule("old_001", "正月", "甲木参天", "甲木参天"),
        _make_rule("old_002", "二月", "甲木参天", "甲木参天"),
        _make_rule("old_003", "三月", "甲木参天", "甲木参天"),
        _make_rule("old_004", "正月", "乙木系甲", "乙木系甲"),
    ]
    # Existing quarantine already holds content identical to a merged rule.
    existing_q = [_make_rule("old_q_001", "四月", "甲木参天", "甲木参天")]
    _setup_book(tmp_path, rules, [], raw_text="甲木参天乙木系甲", existing_q_rules=existing_q)

    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    book_dir = tmp_path / "testbook"
    clean = _load_rules(book_dir / "all_rules.json")
    q = _load_jsonl(book_dir / "quarantine_rules.jsonl")
    verify_conservation(rules, existing_q, clean, q, rule_fp, "rules")

    # The merged duplicates must be present in quarantine (not silently dropped).
    merged = [r for r in q if r.get("quarantine_reason") == "cross_chapter_merged_into_canonical"]
    assert len(merged) == 2


def test_mcq_conservation_holds_on_disk(tmp_path):
    rules = [_make_rule("old_001", "第一章", "甲木生春月", "甲木生春月")]
    mcqs = [
        _make_mcq("m1", "问题一", {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "A", "old_001"),
        _make_mcq("m2", "问题二", {"A": "子", "B": "丑", "C": "寅", "D": "卯"}, "B", "old_001"),
    ]
    _setup_book(tmp_path, rules, mcqs, raw_text="甲木生春月")

    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    book_dir = tmp_path / "testbook"
    clean_mcqs = _load_jsonl(book_dir / "all_mcq.jsonl")
    q_mcqs = _load_jsonl(book_dir / "quarantine_mcq.jsonl")
    # Verify by content fingerprint (invariant to rotation/remap).
    fp = lambda m: mcq_fp(m)  # noqa: E731
    before = {}
    for m in mcqs:
        k = fp(m)
        before[k] = before.get(k, 0) + 1
    after = {}
    for m in clean_mcqs + q_mcqs:
        k = fp(m)
        after[k] = after.get(k, 0) + 1
    assert before == after


def test_quarantine_append_all_not_lossy(tmp_path):
    """Existing quarantine + new merges -> union preserved on disk (no lossy dedup)."""
    rules = [
        _make_rule("old_001", "正月", "甲木参天", "甲木参天"),
        _make_rule("old_002", "二月", "甲木参天", "甲木参天"),
    ]
    existing_q = [_make_rule("old_q_001", "三月", "甲木参天", "甲木参天")]
    _setup_book(tmp_path, rules, [], raw_text="甲木参天", existing_q_rules=existing_q)

    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    book_dir = tmp_path / "testbook"
    q = _load_jsonl(book_dir / "quarantine_rules.jsonl")
    # existing (1) + merged (1) must both be present -> 2 total quarantine records
    assert len(q) == 2
    verify_conservation(rules, existing_q, _load_rules(book_dir / "all_rules.json"), q, rule_fp, "rules")


# ---------------------------------------------------------------------------
# P0-3: publish rollback on mid-failure
# ---------------------------------------------------------------------------


def test_publish_rolls_back_on_failure(tmp_path, monkeypatch):
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    book_dir = _setup_book(tmp_path, rules, [], raw_text="甲木")
    original = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))

    # Simulate a staging dir with new content, then make the 2nd os.replace fail.
    staging = tmp_path / "staging"
    staging.mkdir()
    for name in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
                 "quarantine_mcq.jsonl", "remediation_meta.json", "provenance.json"):
        (staging / name).write_text("[]", encoding="utf-8")

    real_replace = _publish.__globals__["os"].replace
    call = {"n": 0}

    def flaky_replace(src, dst):
        call["n"] += 1
        if call["n"] == 2:
            raise OSError("simulated publish failure")
        return real_replace(src, dst)

    monkeypatch.setattr(_publish.__globals__["os"], "replace", flaky_replace)
    with pytest.raises(OSError):
        _publish(staging, book_dir, ["all_rules.json", "all_mcq.jsonl",
                                     "quarantine_rules.jsonl", "quarantine_mcq.jsonl",
                                     "remediation_meta.json", "provenance.json"])

    # all_rules.json must be rolled back to original.
    after = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))
    assert after == original
    # No backup dir left behind.
    assert not list(book_dir.glob(".publish_backup_*"))


# ---------------------------------------------------------------------------
# P0-2: provenance validation
# ---------------------------------------------------------------------------


def _make_minimal_provenance(book_dir: Path, anchor_commit: str = "abc123",
                              anchor_verified: bool = True) -> dict:
    """Build a provenance dict with all P0-3 required fields."""
    from scripts.classic_artifacts import sha256_file
    return {
        "generated_at": "2025-01-01",
        "anchor_commit": anchor_commit,
        "anchor_commit_verified": anchor_verified,
        "no_api": True,
        "input_baseline_commit": "303d375",
        "worktree_dirty": False,
        "code_fingerprint": "a" * 64,
        "upstream_provenance_status": "unavailable",
        "file_shas": {n: sha256_file(book_dir / n) for n in
                      ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
                       "quarantine_mcq.jsonl", "remediation_meta.json")},
        "code_shas": {n: sha256_file(SCRIPTS_DIR / n) for n in CODE_FILE_NAMES
                      if (SCRIPTS_DIR / n).exists()},
        "raw_text_shas": {"raw_001.txt": sha256_file(book_dir / "raw_001.txt")}
                      if (book_dir / "raw_001.txt").exists() else {},
        "input_baseline_blob_shas": {},
    }


def test_provenance_ok_when_all_shas_match(tmp_path):
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text("[]", encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text("{}", encoding="utf-8")
    (book_dir / "raw_001.txt").write_text("原文", encoding="utf-8")

    prov = _make_minimal_provenance(book_dir)
    (book_dir / "provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False), encoding="utf-8")

    ok, issues = validate_provenance(book_dir, SCRIPTS_DIR)
    assert ok, issues


def test_provenance_detects_file_sha_drift(tmp_path):
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text('[{"id":"x"}]', encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text("{}", encoding="utf-8")

    prov = _make_minimal_provenance(book_dir)
    prov["file_shas"]["all_rules.json"] = "0" * 64  # deliberately wrong
    (book_dir / "provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False), encoding="utf-8")

    ok, issues = validate_provenance(book_dir, SCRIPTS_DIR)
    assert not ok
    assert any("all_rules.json" in i and "mismatch" in i for i in issues)


def test_provenance_detects_missing_required_fields(tmp_path):
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "provenance.json").write_text('{"file_shas":{}}', encoding="utf-8")
    ok, issues = validate_provenance(book_dir, SCRIPTS_DIR)
    assert not ok
    assert any("missing required fields" in i for i in issues)


def test_provenance_missing_file(tmp_path):
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    ok, issues = validate_provenance(book_dir, SCRIPTS_DIR)
    assert not ok
    assert any("missing" in i for i in issues)


def test_provenance_rejects_unverified_anchor_commit(tmp_path):
    """P0-3: anchor_commit_verified=False must fail validation."""
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text("[]", encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text("{}", encoding="utf-8")

    prov = _make_minimal_provenance(book_dir, anchor_verified=False)
    (book_dir / "provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False), encoding="utf-8")

    ok, issues = validate_provenance(book_dir, SCRIPTS_DIR)
    assert not ok
    assert any("anchor_commit_verified" in i for i in issues)


def test_provenance_rejects_nonexistent_anchor_commit(tmp_path):
    """P0-3: anchor_commit that doesn't exist in git must fail when git_root given."""
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text("[]", encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text("{}", encoding="utf-8")

    prov = _make_minimal_provenance(book_dir, anchor_commit="deadbeef" * 5)
    (book_dir / "provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False), encoding="utf-8")

    # Without git_root: passes (no existence check).
    ok, _ = validate_provenance(book_dir, SCRIPTS_DIR)
    assert ok
    # With git_root: fails because anchor_commit doesn't exist.
    ok, issues = validate_provenance(book_dir, SCRIPTS_DIR, git_root=tmp_path)
    assert not ok
    assert any("does not exist" in i for i in issues)


def test_remediate_writes_valid_provenance(tmp_path):
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)
    # remediate_book was called without git_root, so provenance has no
    # input_baseline_blob_shas. validate_provenance must use the same
    # git_root=None to skip git-dependent checks (anchor_commit existence,
    # baseline blob coverage) -- otherwise it would falsely fail.
    ok, issues = validate_provenance(tmp_path / "testbook", SCRIPTS_DIR)
    assert ok, issues
    assert (tmp_path / "testbook" / "provenance.json").exists()


# ---------------------------------------------------------------------------
# P0-3: staging lives inside book dir (ACL inheritance)
# ---------------------------------------------------------------------------


def test_staging_created_inside_book_dir(tmp_path):
    """staging dir must be created inside the book dir, not in a system temp dir."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    book_dir = tmp_path / "testbook"
    # After remediation, no .staging_* dirs should remain (cleaned up in finally).
    staging_dirs = list(book_dir.glob(".staging_*"))
    assert not staging_dirs, f"staging dirs left behind: {staging_dirs}"


# ---------------------------------------------------------------------------
# P0-3: rollback deletes newly-created files (not just restores backed-up ones)
# ---------------------------------------------------------------------------


def test_publish_rolls_back_deletes_new_files(tmp_path, monkeypatch):
    """If a file didn't exist before publish and publish fails, it must be deleted."""
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    # Only all_rules.json exists before; others are new.
    (book_dir / "all_rules.json").write_text('[{"id":"old"}]', encoding="utf-8")

    staging = book_dir / ".staging_test"
    staging.mkdir()
    for name in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
                 "quarantine_mcq.jsonl", "remediation_meta.json", "provenance.json"):
        (staging / name).write_text("[]", encoding="utf-8")

    real_replace = _publish.__globals__["os"].replace
    call = {"n": 0}

    def flaky_replace(src, dst):
        call["n"] += 1
        if call["n"] == 2:
            raise OSError("simulated publish failure")
        return real_replace(src, dst)

    monkeypatch.setattr(_publish.__globals__["os"], "replace", flaky_replace)
    with pytest.raises(OSError):
        _publish(staging, book_dir, ["all_rules.json", "all_mcq.jsonl",
                                     "quarantine_rules.jsonl", "quarantine_mcq.jsonl",
                                     "remediation_meta.json", "provenance.json"])

    # all_rules.json must be rolled back to original.
    after = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))
    assert after == [{"id": "old"}]
    # all_mcq.jsonl was new (didn't exist before) -> must be DELETED, not left behind.
    assert not (book_dir / "all_mcq.jsonl").exists()
    # No backup dir left behind on failure.
    assert not list(book_dir.glob(".publish_backup_*"))


# ---------------------------------------------------------------------------
# P0-3: backup retained until external validation passes
# ---------------------------------------------------------------------------


def test_publish_returns_backup_dir_and_does_not_delete(tmp_path):
    """_publish on success returns backup_dir; caller must clean it up."""
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text('[{"id":"old"}]', encoding="utf-8")

    staging = book_dir / ".staging_test"
    staging.mkdir()
    names = ["all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
             "quarantine_mcq.jsonl", "remediation_meta.json", "provenance.json"]
    for name in names:
        (staging / name).write_text("[]", encoding="utf-8")

    backup_dir = _publish(staging, book_dir, names)
    assert backup_dir.exists()
    # all_rules.json was backed up.
    assert (backup_dir / "all_rules.json").exists()


# ---------------------------------------------------------------------------
# P0-6: real subprocess verification after publish
# ---------------------------------------------------------------------------


def test_subprocess_verification_passes_after_remediate(tmp_path):
    """After remediate_book, a fresh subprocess can read + git-hash + verify."""
    rules = [
        _make_rule("old_001", "第一章", "甲木", "甲木"),
        _make_rule("old_002", "第一章", "乙木", "乙木"),
    ]
    mcqs = [
        _make_mcq("m1", "问题一", {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "A", "old_001"),
    ]
    _setup_book(tmp_path, rules, mcqs, raw_text="甲木乙木")

    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    # Independent subprocess: read all 6 files + git hash-object.
    import subprocess as sp
    code = (
        "import json, sys, subprocess\n"
        "from pathlib import Path\n"
        "book_dir = Path(sys.argv[1])\n"
        "git_root = Path(sys.argv[2])\n"
        "names = ['all_rules.json','all_mcq.jsonl','quarantine_rules.jsonl',\n"
        "         'quarantine_mcq.jsonl','remediation_meta.json','provenance.json']\n"
        "for n in names:\n"
        "    f = book_dir / n\n"
        "    data = f.read_bytes()\n"
        "    if n.endswith('.json'):\n"
        "        json.loads(data)\n"
        "    elif n.endswith('.jsonl'):\n"
        "        for line in data.decode('utf-8').splitlines():\n"
        "            if line.strip(): json.loads(line)\n"
        "    r = subprocess.run(['git','hash-object',str(f)],\n"
        "                       capture_output=True,text=True,cwd=str(git_root))\n"
        "    assert r.returncode == 0, f'hash-object failed {n}: {r.stderr}'\n"
        "print('OK')\n"
    )
    r = sp.run([sys.executable, "-c", code, str(tmp_path / "testbook"),
                str(Path(__file__).resolve().parent.parent)],
               capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"subprocess failed: {r.stderr}\nstdout: {r.stdout}"
    assert "OK" in r.stdout


def test_no_staging_or_backup_dirs_left_after_successful_remediate(tmp_path):
    """After successful remediate_book, no .staging_* or .publish_backup_* dirs remain."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    book_dir = tmp_path / "testbook"
    assert not list(book_dir.glob(".staging_*"))
    assert not list(book_dir.glob(".publish_backup_*"))


# ---------------------------------------------------------------------------
# P0-3: provenance includes new fields
# ---------------------------------------------------------------------------


def test_remediate_provenance_includes_new_fields(tmp_path):
    """Provenance written by remediate_book must include P0-3 fields."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    prov = json.loads(
        (tmp_path / "testbook" / "provenance.json").read_text(encoding="utf-8")
    )
    assert prov["no_api"] is True
    assert prov["anchor_commit_verified"] is True
    # "testbook" is not in INPUT_BASELINE_BY_BOOK, so it falls back to
    # INPUT_BASELINE_REF (the zpzq baseline). Import the constant so the
    # test stays correct when baselines are updated.
    from scripts.remediate_classic_distillation import INPUT_BASELINE_REF
    assert prov["input_baseline_commit"] == INPUT_BASELINE_REF
    assert "worktree_dirty" in prov
    assert isinstance(prov["worktree_dirty"], bool)
    assert "code_fingerprint" in prov
    assert len(prov["code_fingerprint"]) == 64
    assert "upstream_provenance_status" in prov
    assert prov["upstream_provenance_status"] in ("recovered", "unavailable")


def test_provenance_preserves_upstream_provenance(tmp_path):
    """P0-3: remediation must not drop upstream distillation provenance."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    book_dir = tmp_path / "testbook"
    # Simulate prior distillation-stage provenance with upstream fields.
    # P0-4: provide full schema so status='recovered' (not 'partial').
    upstream = {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "thinking": "disabled",
        "thinking_mode": "disabled",
        "temperature": 0.0,
        "source_url": "https://example.com/dts.txt",
        "source_version": "v1",
        "distill_script": "scripts/distill_lib.py",
        "upstream_artifact_shas": {
            "all_rules.json": "a" * 64,
            "all_mcq.jsonl": "b" * 64,
        },
    }
    (book_dir / "provenance.json").write_text(
        json.dumps(upstream, ensure_ascii=False), encoding="utf-8")

    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    prov = json.loads((book_dir / "provenance.json").read_text(encoding="utf-8"))
    assert "upstream_provenance" in prov
    assert prov["upstream_provenance"]["provider"] == "deepseek"
    assert prov["upstream_provenance"]["model"] == "deepseek-v4-flash"
    assert prov["upstream_provenance"]["source_url"] == "https://example.com/dts.txt"


def test_provenance_anchor_commit_not_required_to_equal_head(tmp_path):
    """P0-2: anchor_commit must NOT be required to equal current HEAD.

    After committing the artifacts, HEAD advances. Provenance recorded at
    generation time must still validate. This test simulates that scenario
    by using a real commit that is NOT HEAD.
    """
    import subprocess as sp
    # Create a git repo in tmp_path, make a commit, then advance HEAD.
    sp.run(["git", "init"], capture_output=True, cwd=str(tmp_path))
    sp.run(["git", "config", "user.email", "t@t.com"], capture_output=True, cwd=str(tmp_path))
    sp.run(["git", "config", "user.name", "t"], capture_output=True, cwd=str(tmp_path))
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    sp.run(["git", "add", "a.txt"], capture_output=True, cwd=str(tmp_path))
    sp.run(["git", "commit", "-m", "first"], capture_output=True, cwd=str(tmp_path))
    old_commit = sp.run(["git", "rev-parse", "HEAD"], capture_output=True,
                        text=True, encoding="utf-8", cwd=str(tmp_path)).stdout.strip()
    # Advance HEAD.
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    sp.run(["git", "add", "b.txt"], capture_output=True, cwd=str(tmp_path))
    sp.run(["git", "commit", "-m", "second"], capture_output=True, cwd=str(tmp_path))
    new_head = sp.run(["git", "rev-parse", "HEAD"], capture_output=True,
                      text=True, encoding="utf-8", cwd=str(tmp_path)).stdout.strip()
    assert old_commit != new_head

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text("[]", encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text("{}", encoding="utf-8")

    # anchor_commit = old_commit (NOT current HEAD), but it exists.
    prov = _make_minimal_provenance(book_dir, anchor_commit=old_commit)
    # input_baseline_commit must also exist in this repo.
    prov["input_baseline_commit"] = old_commit
    (book_dir / "provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False), encoding="utf-8")

    # Must pass: anchor_commit exists, even though != HEAD.
    ok, issues = validate_provenance(book_dir, SCRIPTS_DIR, git_root=tmp_path)
    assert ok, f"expected pass (anchor exists, != HEAD): {issues}"


# ---------------------------------------------------------------------------
# P0-4: post-publish exception triggers rollback
# ---------------------------------------------------------------------------


def test_post_publish_snapshot_write_failure_triggers_rollback(tmp_path, monkeypatch):
    """If baseline snapshot write fails after publish, artifacts must roll back."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    book_dir = tmp_path / "testbook"
    original_rules = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))

    # Make _write_baseline_snapshot raise after publish.
    import scripts.remediate_classic_distillation as rcd
    def boom(*a, **kw):
        raise OSError("simulated snapshot write failure")
    monkeypatch.setattr(rcd, "_write_baseline_snapshot", boom)

    with pytest.raises(OSError, match="simulated snapshot write failure"):
        remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    # Artifacts must be rolled back to original state.
    after = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))
    assert after == original_rules


def test_post_publish_subprocess_spawn_failure_triggers_rollback(tmp_path, monkeypatch):
    """If subprocess.run fails to spawn, artifacts must roll back."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    book_dir = tmp_path / "testbook"
    original_rules = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))

    # Make _verify_published_via_subprocess raise (not return False, but raise).
    import scripts.remediate_classic_distillation as rcd
    def boom(*a, **kw):
        raise RuntimeError("subprocess spawn failed")
    monkeypatch.setattr(rcd, "_verify_published_via_subprocess", boom)

    with pytest.raises(RuntimeError, match="subprocess spawn failed"):
        remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    after = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))
    assert after == original_rules


def test_post_publish_subprocess_output_unparseable_triggers_rollback(tmp_path, monkeypatch):
    """If subprocess output can't be parsed, artifacts must roll back."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    book_dir = tmp_path / "testbook"
    original_rules = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))

    import scripts.remediate_classic_distillation as rcd
    # Return garbage that will fail JSON parse inside _verify_published_via_subprocess.
    # Actually the function catches parse errors and returns (False, issues), which
    # raises ConservationError. Test that path too.
    def fake_subprocess(*a, **kw):
        return False, ["simulated unparseable output"]
    monkeypatch.setattr(rcd, "_verify_published_via_subprocess", fake_subprocess)

    with pytest.raises(ConservationError, match="simulated unparseable output"):
        remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    after = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))
    assert after == original_rules


# ---------------------------------------------------------------------------
# P0-2: MCQ semantic consistency gate (replaces token-based proof)
# ---------------------------------------------------------------------------


def test_mcq_prefilter_passes_with_overlap():
    """_mcq_prefilter returns True when question shares text with rule."""
    from scripts.distill_lib import _mcq_prefilter
    rule = {"subject": "甲木", "condition": "春月", "rule": "甲木生春月", "original_text": "甲木参天"}
    mcq = {"question": "甲木生春月时如何取用？", "explanation": "甲木在春月"}
    assert _mcq_prefilter(mcq, rule) is True


def test_mcq_prefilter_fails_without_overlap():
    """_mcq_prefilter returns False when question is unrelated to rule."""
    from scripts.distill_lib import _mcq_prefilter
    rule = {"subject": "甲木", "condition": "春月", "rule": "甲木生春月", "original_text": "甲木参天"}
    mcq = {"question": "丙火在冬月的特点？", "explanation": "丙火寒冷"}
    assert _mcq_prefilter(mcq, rule) is False


def test_mcq_prefilter_passes_when_rule_empty():
    """If rule has no checkable content, consistency passes (can't check)."""
    from scripts.distill_lib import _mcq_prefilter
    rule = {"subject": "", "condition": "", "rule": "", "original_text": ""}
    mcq = {"question": "任意问题", "explanation": "任意解析"}
    assert _mcq_prefilter(mcq, rule) is True


def test_link_mcq_to_rules_accepts_verified_consistent():
    """MCQ with _consistency_verified=True and semantic overlap is linked."""
    from scripts.distill_lib import link_mcq_to_rules
    rules = [{"id": "r1", "rule": "甲木参天", "subject": "甲木"}]
    # P0-1: MCQ must have valid options+answer for strict consistency check.
    mcqs = [
        {"source_rule_id": "r1", "_consistency_verified": True,
         "question": "甲木参天说明什么？", "explanation": "甲木",
         "options": {"A": "甲木参天", "B": "乙木", "C": "丙火", "D": "丁火"},
         "answer": "A"},
    ]
    linked, unlinked = link_mcq_to_rules(mcqs, rules)
    assert len(linked) == 1
    assert len(unlinked) == 0


def test_link_mcq_to_rules_quarantines_legacy_unaudited():
    """MCQ without _consistency_verified is quarantined as legacy_unaudited."""
    from scripts.distill_lib import link_mcq_to_rules
    rules = [{"id": "r1", "rule": "甲木参天", "subject": "甲木"}]
    mcqs = [{"source_rule_id": "r1", "question": "甲木参天", "explanation": "甲木"}]
    linked, unlinked = link_mcq_to_rules(mcqs, rules)
    assert len(linked) == 0
    assert len(unlinked) == 1
    assert "legacy_unaudited" in unlinked[0]["quarantine_reason"]


def test_link_mcq_to_rules_quarantines_semantic_mismatch():
    """MCQ with _consistency_verified=True but no overlap is quarantined."""
    from scripts.distill_lib import link_mcq_to_rules
    rules = [{"id": "r1", "rule": "甲木参天", "subject": "甲木"}]
    mcqs = [
        {"source_rule_id": "r1", "_consistency_verified": True,
         "question": "丙火在冬月的特点？", "explanation": "丙火寒冷"},
    ]
    linked, unlinked = link_mcq_to_rules(mcqs, rules)
    assert len(linked) == 0
    assert len(unlinked) == 1
    assert "semantic_consistency_failed" in unlinked[0]["quarantine_reason"]


def test_link_mcq_to_rules_quarantines_invalid_source_rule_id():
    """MCQ with unknown source_rule_id is quarantined."""
    from scripts.distill_lib import link_mcq_to_rules
    rules = [{"id": "r1", "rule": "甲木", "subject": "甲木"}]
    mcqs = [
        {"source_rule_id": "r_nonexistent", "_consistency_verified": True,
         "question": "问题", "explanation": "解析"},
    ]
    linked, unlinked = link_mcq_to_rules(mcqs, rules)
    assert len(linked) == 0
    assert len(unlinked) == 1
    assert "invalid_or_missing_source_rule_id" in unlinked[0]["quarantine_reason"]


# ---------------------------------------------------------------------------
# P0-2: remediation quarantines all old MCQs as legacy_unaudited
# ---------------------------------------------------------------------------


def test_remediate_quarantines_all_old_mcqs_as_legacy(tmp_path):
    """All existing MCQs must be quarantined as legacy_unaudited (not clean)."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    mcqs = [
        _make_mcq("m1", "问题一", {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "A", "old_001"),
        _make_mcq("m2", "问题二", {"A": "子", "B": "丑", "C": "寅", "D": "卯"}, "B", "old_001"),
    ]
    _setup_book(tmp_path, rules, mcqs, raw_text="甲木")

    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    book_dir = tmp_path / "testbook"
    clean_mcqs = _load_jsonl(book_dir / "all_mcq.jsonl")
    q_mcqs = _load_jsonl(book_dir / "quarantine_mcq.jsonl")
    assert len(clean_mcqs) == 0
    assert len(q_mcqs) == 2
    for m in q_mcqs:
        assert "legacy_unaudited" in m.get("quarantine_reason", "")


# ---------------------------------------------------------------------------
# P0-3: upstream_provenance_status field
# ---------------------------------------------------------------------------


def test_remediate_provenance_has_upstream_status_unavailable(tmp_path):
    """When no upstream provenance exists, status must be 'unavailable'."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    prov = json.loads(
        (tmp_path / "testbook" / "provenance.json").read_text(encoding="utf-8")
    )
    assert prov["upstream_provenance_status"] == "unavailable"


def test_remediate_provenance_has_upstream_status_recovered(tmp_path):
    """When full upstream provenance exists, status must be 'recovered'.

    P0-4: 'recovered' now requires upstream_artifact_commit AND git_root
    for byte-level verification. Without git_root (test environment),
    status is 'partial' even with full schema.
    """
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    book_dir = tmp_path / "testbook"
    # P0-4: 'recovered' requires full upstream schema INCLUDING artifact_commit.
    upstream = {
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
    (book_dir / "provenance.json").write_text(
        json.dumps(upstream, ensure_ascii=False), encoding="utf-8")

    remediate_book("testbook", "测试书", "tb", base_path=tmp_path)

    prov = json.loads((book_dir / "provenance.json").read_text(encoding="utf-8"))
    # P0-4: without git_root, status is 'partial' (cannot verify bytes)
    assert prov["upstream_provenance_status"] == "partial"
    # But the upstream_provenance data is preserved
    assert prov["upstream_provenance"]["upstream_artifact_commit"] == "abc123"


# ---------------------------------------------------------------------------
# P0-3: rollback failure does not swallow exception
# ---------------------------------------------------------------------------


def test_rollback_failure_reports_both_errors(tmp_path, monkeypatch):
    """If rollback also fails, the error must report both failures."""
    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")

    import scripts.remediate_classic_distillation as rcd

    def boom_snapshot(*a, **kw):
        raise OSError("snapshot write failed")

    def boom_rollback(*a, **kw):
        raise RuntimeError("rollback also failed")

    monkeypatch.setattr(rcd, "_write_baseline_snapshot", boom_snapshot)
    monkeypatch.setattr(rcd, "_rollback_from_backup", boom_rollback)

    with pytest.raises(ConservationError, match="ROLLBACK ALSO FAILED"):
        remediate_book("testbook", "测试书", "tb", base_path=tmp_path)


# ---------------------------------------------------------------------------
# P0-3: input_baseline_blob_shas recorded in provenance
# ---------------------------------------------------------------------------


def test_remediate_provenance_includes_input_baseline_blob_shas(tmp_path):
    """Provenance must include input_baseline_blob_shas when git_root is given."""
    import subprocess as sp
    sp.run(["git", "init"], capture_output=True, cwd=str(tmp_path))
    sp.run(["git", "config", "user.email", "t@t.com"], capture_output=True, cwd=str(tmp_path))
    sp.run(["git", "config", "user.name", "t"], capture_output=True, cwd=str(tmp_path))

    rules = [_make_rule("old_001", "第一章", "甲木", "甲木")]
    _setup_book(tmp_path, rules, [], raw_text="甲木")
    book_dir = tmp_path / "testbook"
    raw_file = book_dir / "raw_001.txt"
    sp.run(["git", "add", str(raw_file)], capture_output=True, cwd=str(tmp_path))
    sp.run(["git", "commit", "-m", "baseline"], capture_output=True, cwd=str(tmp_path))
    baseline_commit = sp.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        encoding="utf-8", cwd=str(tmp_path)
    ).stdout.strip()

    import scripts.remediate_classic_distillation as rcd
    # NOTE: remediate_book's input_baseline_commit default is bound at function
    # definition time, so mutating rcd.INPUT_BASELINE_REF has no effect on the
    # default. Pass the baseline commit explicitly instead.
    remediate_book(
        "testbook", "测试书", "tb",
        base_path=tmp_path, git_root=tmp_path,
        input_baseline_commit=baseline_commit,
    )

    prov = json.loads((book_dir / "provenance.json").read_text(encoding="utf-8"))
    assert "input_baseline_blob_shas" in prov
    assert "raw_001.txt" in prov["input_baseline_blob_shas"]
    blob = prov["input_baseline_blob_shas"]["raw_001.txt"]
    assert len(blob) == 40


# ---------------------------------------------------------------------------
# P0-1: _mcq_strict_consistency polarity contradiction detection
# ---------------------------------------------------------------------------


def test_strict_consistency_detects_polarity_contradiction():
    """Strict check must fail when rule says 喜 but MCQ says 忌."""
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "甲木", "condition": "", "rule": "甲木喜水滋养", "original_text": "甲木喜水"}
    mcq = {"question": "甲木为何忌水？", "explanation": "甲木遇水必凶。"}
    assert _mcq_strict_consistency(mcq, rule) is False


def test_strict_consistency_passes_aligned_polarity():
    """Strict check passes when rule and MCQ have same polarity."""
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "甲木", "condition": "", "rule": "甲木喜水滋养", "original_text": "甲木喜水"}
    # P0-1: answer option must exist and be polarity-consistent with rule.
    mcq = {
        "question": "甲木为何喜水？",
        "explanation": "甲木得水则生。",
        "options": {"A": "甲木喜水滋养", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
        "answer": "A",
    }
    assert _mcq_strict_consistency(mcq, rule) is True


def test_strict_consistency_detects_subject_mismatch():
    """Strict check must fail when rule subject not in MCQ question."""
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "甲木", "condition": "", "rule": "甲木参天", "original_text": "甲木"}
    mcq = {"question": "丙火在冬月的特点？", "explanation": "丙火寒冷"}
    assert _mcq_strict_consistency(mcq, rule) is False


def test_strict_consistency_fails_on_empty_content():
    """Strict check returns False (conservative) when content is empty."""
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "", "condition": "", "rule": "", "original_text": ""}
    mcq = {"question": "", "explanation": ""}
    assert _mcq_strict_consistency(mcq, rule) is False


# ---------------------------------------------------------------------------
# P0-2: BudgetLedger
# ---------------------------------------------------------------------------


def test_budget_ledger_tracks_calls():
    """BudgetLedger tracks calls and reports exhaustion."""
    from scripts.distill_lib import BudgetLedger
    ledger = BudgetLedger(global_hard_cap=3)
    assert ledger.can_call() is True
    ledger.record_call()
    ledger.record_call()
    ledger.record_call()
    assert ledger.can_call() is False
    assert ledger.exhausted is True
    s = ledger.summary()
    assert s["calls_made"] == 3
    assert s["remaining"] == 0


# ---------------------------------------------------------------------------
# P0-3: validate_provenance requires baseline blob keys match raw_text_shas
# ---------------------------------------------------------------------------


def test_validate_provenance_baseline_keys_must_match_raw(tmp_path):
    """input_baseline_blob_shas.keys() must equal raw_text_shas.keys()."""
    from scripts.classic_artifacts import validate_provenance
    p = tmp_path / "testbook"
    p.mkdir()
    (p / "raw_001.txt").write_text("甲木", encoding="utf-8")
    (p / "raw_002.txt").write_text("丙火", encoding="utf-8")
    from scripts.classic_artifacts import sha256_file
    raw_shas = {
        "raw_001.txt": sha256_file(p / "raw_001.txt"),
        "raw_002.txt": sha256_file(p / "raw_002.txt"),
    }
    prov = {
        "generated_at": "2025-01-01",
        "anchor_commit": "abc123",
        "anchor_commit_verified": True,
        "no_api": True,
        "input_baseline_commit": "303d375",
        "worktree_dirty": False,
        "code_fingerprint": "a" * 64,
        "upstream_provenance_status": "unavailable",
        "file_shas": {},
        "code_shas": {},
        "raw_text_shas": raw_shas,
        "input_baseline_blob_shas": {"raw_001.txt": "someblob"},  # missing raw_002.txt
    }
    (p / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
    # P0-3: baseline blob keys check only runs when git_root is provided.
    # Pass git_root=tmp_path so the keys-must-match check is enforced
    # (git hash-object works without a real repo; it just computes the SHA).
    ok, issues = validate_provenance(p, tmp_path / "scripts", git_root=tmp_path)
    assert ok is False
    assert any("missing entries" in i for i in issues)


# ---------------------------------------------------------------------------
# P0-3: upstream_provenance_status='recovered' requires upstream schema
# ---------------------------------------------------------------------------


def test_validate_provenance_recovered_requires_upstream_schema(tmp_path):
    """recovered status without upstream_provenance must fail."""
    from scripts.classic_artifacts import validate_provenance
    p = tmp_path / "testbook"
    p.mkdir()
    prov = {
        "generated_at": "2025-01-01",
        "anchor_commit": "abc123",
        "anchor_commit_verified": True,
        "no_api": True,
        "input_baseline_commit": "303d375",
        "worktree_dirty": False,
        "code_fingerprint": "a" * 64,
        "upstream_provenance_status": "recovered",
        "file_shas": {},
        "code_shas": {},
        "raw_text_shas": {},
        "input_baseline_blob_shas": {},
    }
    (p / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
    ok, issues = validate_provenance(p, tmp_path / "scripts")
    assert ok is False
    assert any("upstream_provenance" in i and "missing" in i for i in issues)


# ---------------------------------------------------------------------------
# P0-5: _rollback_from_backup raises on file deletion failure
# ---------------------------------------------------------------------------


def test_rollback_from_backup_raises_on_unlink_failure(tmp_path, monkeypatch):
    """_rollback_from_backup must raise when file deletion fails."""
    import os
    import scripts.remediate_classic_distillation as rcd
    p = tmp_path / "book"
    p.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    # Create a file that exists in target but not in backup (new file from publish)
    target_file = p / "new_file.json"
    target_file.write_text("{}", encoding="utf-8")

    # Make os.unlink fail for this specific file
    original_unlink = os.unlink
    def boom_unlink(path, *args, **kwargs):
        if str(target_file) in str(path):
            raise OSError("permission denied")
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(os, "unlink", boom_unlink)

    with pytest.raises(rcd.ConservationError, match="delete new file"):
        rcd._rollback_from_backup(p, backup, ["new_file.json"])


def test_rollback_from_backup_verifies_restored_sha(tmp_path):
    """_rollback_from_backup must verify restored file SHA matches backup."""
    import scripts.remediate_classic_distillation as rcd
    p = tmp_path / "book"
    p.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    # Create backup with original content
    (backup / "all_rules.json").write_text('{"original": true}', encoding="utf-8")
    # Create target with different content (published but needs rollback)
    (p / "all_rules.json").write_text('{"new": false}', encoding="utf-8")

    rcd._rollback_from_backup(p, backup, ["all_rules.json"])
    # File should be restored to backup content
    restored = (p / "all_rules.json").read_text(encoding="utf-8")
    assert restored == '{"original": true}'


# ---------------------------------------------------------------------------
# P0-1 regression: question contradicts rule but answer is correct
# ---------------------------------------------------------------------------


def test_strict_consistency_question_contradicts_rule_with_correct_answer():
    """P0-1: question text contradicts rule polarity -> must fail even if
    the answer option is correct.

    This is the audit's test case 1: rule says '甲木喜水，忌金' but the
    question asks '甲木为何忌水？'. Even though answer=A='甲木喜水' is
    correct, the question itself contradicts the rule's '喜水' binding.
    """
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "甲木", "condition": "", "rule": "甲木喜水，忌金", "original_text": ""}
    mcq = {
        "question": "甲木为何忌水？",
        "explanation": "甲木遇水不利",
        "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
        "answer": "A",
    }
    assert _mcq_strict_consistency(mcq, rule) is False


def test_strict_consistency_answer_points_to_wrong_option():
    """P0-1: correct explanation but answer points to wrong option -> must fail.

    This is the audit's test case 2: rule says '甲木喜水', answer=A='甲木忌水'
    which contradicts the rule polarity.
    """
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "甲木", "condition": "", "rule": "甲木喜水", "original_text": ""}
    mcq = {
        "question": "甲木为何喜水？",
        "explanation": "甲木遇水有利",
        "options": {"A": "甲木忌水", "B": "甲木喜水", "C": "甲木喜金", "D": "甲木忌金"},
        "answer": "A",
    }
    assert _mcq_strict_consistency(mcq, rule) is False


def test_strict_consistency_subject_missing_fails():
    """P0-1: subject missing -> must fail (semantic_unaudited, not auto-pass).

    This is the audit's test case 3: subject is empty, must not auto-pass.
    """
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "", "condition": "", "rule": "甲木喜水", "original_text": ""}
    mcq = {
        "question": "甲木为何喜水？",
        "explanation": "甲木遇水有利",
        "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
        "answer": "A",
    }
    assert _mcq_strict_consistency(mcq, rule) is False


def test_strict_consistency_answer_unrelated_to_rule_fails():
    """P0-1: answer option unrelated to rule -> must fail.

    This is the audit's new test case: rule says '甲木喜水', answer=A='甲木性刚'
    which shares the subject but not the rule's semantic content (喜水).
    Without check 5, this passes just because it doesn't contradict.
    """
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "甲木", "condition": "", "rule": "甲木喜水", "original_text": ""}
    mcq = {
        "question": "关于甲木喜水，哪项正确？",
        "explanation": "甲木喜水",
        "options": {"A": "甲木性刚", "B": "甲木喜水"},
        "answer": "A",
    }
    assert _mcq_strict_consistency(mcq, rule) is False


def test_strict_consistency_explanation_does_not_support_answer_fails():
    """P0-1: explanation doesn't support answer -> must fail (check 6).

    The explanation talks about a different topic than the answer option.
    Without check 6, this passes because the answer is supported by the rule.
    """
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "甲木", "condition": "", "rule": "甲木喜水", "original_text": ""}
    mcq = {
        "question": "甲木为何喜水？",
        "explanation": "乙木系甲得令",
        "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
        "answer": "A",
    }
    assert _mcq_strict_consistency(mcq, rule) is False


def test_strict_consistency_correct_mcq_passes_all_checks():
    """P0-1: a correct MCQ must still pass all 6 checks."""
    from scripts.distill_lib import _mcq_strict_consistency
    rule = {"subject": "甲木", "condition": "", "rule": "甲木喜水", "original_text": ""}
    mcq = {
        "question": "甲木为何喜水？",
        "explanation": "甲木遇水有利滋养",
        "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
        "answer": "A",
    }
    assert _mcq_strict_consistency(mcq, rule) is True


# ---------------------------------------------------------------------------
# P0-2 CLI integration: regen_book/fill_book fail-closed + exit codes
# ---------------------------------------------------------------------------


def test_budget_ledger_persistence_across_restart(tmp_path):
    """BudgetLedger state persists across process restarts (P0-2).

    P0-2: a corrupt or cap-mismatched ledger is rejected (fail-closed),
    not silently reset. Cap mismatch means the ledger was created for a
    different run with a different budget.
    """
    from scripts.distill_lib import BudgetLedger, LedgerCorruptionError
    ledger_path = tmp_path / "ledger.json"
    b = ("run1", "a" * 64, "b" * 64)  # frozen (run_id, code_sha, rules_sha)
    # First "process": make 3 calls
    l1 = BudgetLedger.load_or_create(ledger_path, global_hard_cap=10,
                                     run_id=b[0], code_sha=b[1], rules_sha=b[2])
    l1.record_call()
    l1.record_call()
    l1.record_call()
    # Second "process": reload from disk with SAME identity + cap
    l2 = BudgetLedger.load_or_create(ledger_path, global_hard_cap=10,
                                     run_id=b[0], code_sha=b[1], rules_sha=b[2])
    assert l2.calls_made == 3
    assert l2.can_call() is True
    # P0-2: cap mismatch is now rejected (fail-closed), not silently reset.
    # A mismatch means the ledger was created for a different run.
    with pytest.raises(LedgerCorruptionError, match="cap mismatch"):
        BudgetLedger.load_or_create(ledger_path, global_hard_cap=2,
                                    run_id=b[0], code_sha=b[1], rules_sha=b[2])
    # P0-1: resume with a different identity (cross-run drift) is rejected.
    with pytest.raises(LedgerCorruptionError, match="mismatch"):
        BudgetLedger.load_or_create(ledger_path, global_hard_cap=10,
                                    run_id="run2", code_sha=b[1], rules_sha=b[2])


def test_budget_ledger_corrupt_rejected(tmp_path):
    """P0-2: corrupt ledger raises LedgerCorruptionError, does not reset."""
    from scripts.distill_lib import BudgetLedger, LedgerCorruptionError
    ledger_path = tmp_path / "ledger.json"
    b = ("run1", "a" * 64, "b" * 64)
    # Corrupt JSON
    ledger_path.write_text("NOT JSON", encoding="utf-8")
    with pytest.raises((LedgerCorruptionError, json.JSONDecodeError)):
        BudgetLedger.load_or_create(ledger_path, global_hard_cap=10,
                                    run_id=b[0], code_sha=b[1], rules_sha=b[2])
    # Missing fields
    ledger_path.write_text(json.dumps({"calls_made": 5}), encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="missing required field"):
        BudgetLedger.load_or_create(ledger_path, global_hard_cap=10,
                                    run_id=b[0], code_sha=b[1], rules_sha=b[2])
    # Negative values
    ledger_path.write_text(json.dumps({
        "calls_made": -1, "accepted": 0, "skipped": 0, "global_hard_cap": 10,
    }), encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="negative"):
        BudgetLedger.load_or_create(ledger_path, global_hard_cap=10,
                                    run_id=b[0], code_sha=b[1], rules_sha=b[2])
    # P0-1: persisted ledger missing binding fields is rejected (no lenient
    # upgrade to a fresh identity).
    ledger_path.write_text(json.dumps({
        "calls_made": 0, "accepted": 0, "skipped": 0, "global_hard_cap": 10,
    }), encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="missing binding field"):
        BudgetLedger.load_or_create(ledger_path, global_hard_cap=10,
                                    run_id=b[0], code_sha=b[1], rules_sha=b[2])
    # P0-1: creating a persisted ledger without a frozen identity is refused.
    with pytest.raises(LedgerCorruptionError, match="must be provided"):
        BudgetLedger.load_or_create(ledger_path, global_hard_cap=10)


def test_regen_book_fail_closed_on_budget_exhaustion(tmp_path, monkeypatch):
    """regen_book returns error=fail_closed when budget is exhausted (P0-2).

    No MCQ files should be written.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    rules = [
        {"id": "tb_000_000", "source_chapter": "ch1", "subject": "甲木",
         "rule": "甲木喜水", "original_text": "甲木", "category": "天干"},
        {"id": "tb_000_001", "source_chapter": "ch1", "subject": "乙木",
         "rule": "乙木喜火", "original_text": "乙木", "category": "天干"},
    ]
    (book_dir / "all_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text(
        json.dumps({"needs_mcq_regen": True}), encoding="utf-8")

    # Mock _call to simulate API returning valid MCQs
    call_count = {"n": 0}
    def mock_call(prompt, timeout=120):
        call_count["n"] += 1
        return json.dumps({
            "question": "甲木为何喜水？",
            "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A",
            "explanation": "甲木遇水有利",
            "difficulty": "基础",
            "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)

    # Override BASE to tmp_path
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})

    ledger_path = tmp_path / ".regen_ledger.json"
    b = ("r1", "a" * 64, "b" * 64)
    # Pre-exhaust the ledger: set cap=0 so no calls can be made
    result = rm.regen_book("testbook", global_budget=0, ledger_path=ledger_path,
                           run_id=b[0], code_sha=b[1], rules_sha=b[2])
    assert result.get("error") == "fail_closed"
    # No MCQ file should be written (all_mcq.jsonl stays empty)
    mcq_content = (book_dir / "all_mcq.jsonl").read_text(encoding="utf-8")
    assert mcq_content == ""


def test_regen_book_fail_closed_on_incomplete_mcqs(tmp_path, monkeypatch):
    """regen_book returns error=fail_closed when MCQs are incomplete (P0-2).

    If len(linked) < len(rules), no files should be written.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    rules = [
        {"id": "tb_000_000", "source_chapter": "ch1", "subject": "甲木",
         "rule": "甲木喜水", "original_text": "甲木", "category": "天干"},
        {"id": "tb_000_001", "source_chapter": "ch1", "subject": "乙木",
         "rule": "乙木喜火", "original_text": "乙木", "category": "天干"},
    ]
    (book_dir / "all_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text(
        json.dumps({"needs_mcq_regen": True}), encoding="utf-8")

    # Mock _call to return MCQ that FAILS strict consistency (wrong polarity)
    # This means linked will be empty -> len(linked) < len(rules) -> incomplete
    def mock_call(prompt, timeout=120):
        return json.dumps({
            "question": "甲木为何忌水？",
            "options": {"A": "甲木忌水", "B": "甲木喜水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A",
            "explanation": "甲木遇水不利",
            "difficulty": "基础",
            "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})

    ledger_path = tmp_path / ".regen_ledger.json"
    b = ("r1", "a" * 64, "b" * 64)
    result = rm.regen_book("testbook", global_budget=100, ledger_path=ledger_path,
                           run_id=b[0], code_sha=b[1], rules_sha=b[2])
    assert result.get("error") == "fail_closed"
    # No MCQ file should be written
    mcq_content = (book_dir / "all_mcq.jsonl").read_text(encoding="utf-8")
    assert mcq_content == ""


def test_regen_book_main_returns_nonzero_on_fail_closed(tmp_path, monkeypatch):
    """regen_mcq.main() returns exit code 1 when any book fails (P0-2)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    rules = [{"id": "tb_000_000", "source_chapter": "ch1", "subject": "甲木",
              "rule": "甲木喜水", "original_text": "甲木", "category": "天干"}]
    (book_dir / "all_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text(
        json.dumps({"needs_mcq_regen": True}), encoding="utf-8")

    monkeypatch.setattr(dl, "_call", lambda *a, **k: "")
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})
    # P0-14: keep the shared allowlist consistent with the patched BOOKS.
    monkeypatch.setitem(dl.VALID_TARGETS_BY_OPERATION, "regen", ("testbook",))
    monkeypatch.setattr("sys.argv", ["regen_mcq.py", "testbook"])

    exit_code = rm.main()
    assert exit_code == 1


def test_fill_book_fail_closed_no_raw_files_written(tmp_path, monkeypatch):
    """fill_book does not write raw_*.txt when incomplete (P0-2).

    The audit found fill_book wrote raw files before the integrity check.
    Now raw writes are deferred until chapter is confirmed complete.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.fill_missing_chapters as fmc
    import distill_lib as dl

    book_dir = tmp_path / "zipingzhenquan"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text("[]", encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "progress.json").write_text(
        json.dumps({"done": [], "total_rules": 0, "total_mcqs": 0}),
        encoding="utf-8")
    (book_dir / "raw_full.txt").write_text("第一章 甲木\n甲木参天\n第二章 乙木\n乙木系甲", encoding="utf-8")
    (book_dir / "chapter_list.txt").write_text("1. 第一章 甲木\n2. 第二章 乙木", encoding="utf-8")

    # Mock distill_chapter to return rules (so len(rules) > 0), but _call
    # to return empty for MCQ generation (so len(linked) < len(rules)).
    mock_rules = [
        {"id": "zpzq_000_000", "source_chapter": "第一章 甲木", "subject": "甲木",
         "rule": "甲木参天", "original_text": "甲木", "category": "天干"},
    ]
    monkeypatch.setattr(dl, "distill_chapter", lambda *a, **k: mock_rules)
    monkeypatch.setattr(dl, "_call", lambda *a, **k: "")
    monkeypatch.setattr(fmc, "BASE", tmp_path)

    ledger_path = tmp_path / ".fill_ledger.json"
    b = ("r1", "a" * 64, "b" * 64)
    result = fmc.fill_book("zipingzhenquan", global_budget=100, ledger_path=ledger_path,
                           run_id=b[0], code_sha=b[1], rules_sha=b[2])
    assert result.get("error") == "fail_closed"
    # No raw_*.txt files should have been written (deferred writes)
    raw_files = list(book_dir.glob("raw_*.txt"))
    new_raws = [f for f in raw_files if f.name != "raw_full.txt"]
    assert len(new_raws) == 0, f"Unexpected raw files written: {new_raws}"


# ---------------------------------------------------------------------------
# P0-1: ledger run-identity binding (missing fields + cross-run drift)
# ---------------------------------------------------------------------------


def test_ledger_rejects_missing_binding_on_fresh_persist(tmp_path):
    """P0-1: creating a persisted ledger without a frozen identity is refused."""
    from scripts.distill_lib import BudgetLedger, LedgerCorruptionError
    p = tmp_path / "ledger.json"
    with pytest.raises(LedgerCorruptionError, match="must be provided"):
        BudgetLedger.load_or_create(p, global_hard_cap=10)


def test_ledger_rejects_resume_with_missing_persisted_binding(tmp_path):
    """P0-1: an old ledger missing binding fields is rejected (no lenient upgrade)."""
    from scripts.distill_lib import BudgetLedger, LedgerCorruptionError
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"calls_made": 0, "accepted": 0, "skipped": 0,
                             "global_hard_cap": 10}), encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="missing binding field"):
        BudgetLedger.load_or_create(p, global_hard_cap=10,
                                    run_id="r", code_sha="a" * 64, rules_sha="b" * 64)


def test_ledger_rejects_cross_run_drift(tmp_path):
    """P0-1: resume with a different run_id is rejected (fail-closed)."""
    from scripts.distill_lib import BudgetLedger, LedgerCorruptionError
    p = tmp_path / "ledger.json"
    b = ("runA", "a" * 64, "b" * 64)
    BudgetLedger.load_or_create(p, 10, run_id=b[0], code_sha=b[1], rules_sha=b[2]).save()
    with pytest.raises(LedgerCorruptionError, match="mismatch"):
        BudgetLedger.load_or_create(p, 10, run_id="runB", code_sha=b[1], rules_sha=b[2])


# ---------------------------------------------------------------------------
# P0-2: regen publish is a multi-file transaction (2nd replace failure -> rollback)
# ---------------------------------------------------------------------------


def test_regen_publish_rolls_back_on_second_replace_failure(tmp_path, monkeypatch):
    """P0-2: a mid-publish os.replace failure fully rolls back regen's files."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    import scripts.remediate_classic_distillation as rc

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    rules = [{"id": "tb_000_000", "source_chapter": "ch1", "subject": "甲木",
              "rule": "甲木喜水", "original_text": "甲木", "category": "天干"}]
    (book_dir / "all_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text(
        json.dumps({"needs_mcq_regen": True}), encoding="utf-8")
    original_rules = (book_dir / "all_rules.json").read_bytes()
    original_mcq = (book_dir / "all_mcq.jsonl").read_bytes()

    def mock_call(prompt, timeout=120):
        return json.dumps({
            "question": "甲木为何喜水？",
            "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A", "explanation": "甲木喜水有利",
            "difficulty": "基础", "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})

    real_replace = rc.os.replace
    calls = {"n": 0}
    def flaky(src, dst):
        # Only count replaces that PUBLISH into book_dir (not ledger save,
        # which also uses os.replace underneath Path.replace).
        if str(Path(dst)).startswith(str(book_dir)):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("simulated 2nd publish failure")
        return real_replace(src, dst)
    monkeypatch.setattr(rc.os, "replace", flaky)

    ledger_path = tmp_path / ".regen_ledger.json"
    b = ("r1", "a" * 64, "b" * 64)
    with pytest.raises(OSError):
        rm.regen_book("testbook", global_budget=100, ledger_path=ledger_path,
                      run_id=b[0], code_sha=b[1], rules_sha=b[2])

    # Rollback: production files restored to original.
    assert (book_dir / "all_rules.json").read_bytes() == original_rules
    assert (book_dir / "all_mcq.jsonl").read_bytes() == original_mcq
    # No staging/backup left behind.
    assert not list(book_dir.glob(".regen_staging_*"))
    assert not list(book_dir.glob(".publish_backup_*"))


# ---------------------------------------------------------------------------
# P0-3: regen finalizes provenance + meta so provenance does not go stale
# ---------------------------------------------------------------------------


def test_regen_finalizes_provenance_and_meta(tmp_path, monkeypatch):
    """P0-3: after regen, provenance file_shas are refreshed, needs_mcq_regen=False,
    and the resulting provenance validates (not stale)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    from scripts.classic_artifacts import validate_provenance, sha256_file

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    rules = [{"id": "tb_000_000", "source_chapter": "ch1", "subject": "甲木",
              "rule": "甲木喜水", "original_text": "甲木", "category": "天干"}]
    (book_dir / "all_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text(
        json.dumps({"needs_mcq_regen": True}), encoding="utf-8")
    # Initial (stale) provenance with a bogus file_sha that regen must refresh.
    prov = {
        "generated_at": "2025-01-01", "anchor_commit": "abc123",
        "anchor_commit_verified": True, "no_api": True,
        "input_baseline_commit": "303d375", "worktree_dirty": False,
        "code_fingerprint": "a" * 64, "upstream_provenance_status": "unavailable",
        "file_shas": {"all_mcq.jsonl": "0" * 64}, "code_shas": {},
        "raw_text_shas": {}, "input_baseline_blob_shas": {},
    }
    (book_dir / "provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False), encoding="utf-8")

    def mock_call(prompt, timeout=120):
        return json.dumps({
            "question": "甲木为何喜水？",
            "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A", "explanation": "甲木喜水有利",
            "difficulty": "基础", "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})

    ledger_path = tmp_path / ".regen_ledger.json"
    b = rm._compute_run_bindings(["testbook"])[:3]
    rm.regen_book("testbook", global_budget=100, ledger_path=ledger_path,
                  run_id=b[0], code_sha=b[1], rules_sha=b[2])

    # Meta updated.
    meta = json.loads((book_dir / "remediation_meta.json").read_text(encoding="utf-8"))
    assert meta["needs_mcq_regen"] is False
    # New all_mcq written.
    new_mcqs = [json.loads(l) for l in
                (book_dir / "all_mcq.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(new_mcqs) == 1
    # Provenance is fresh and validates.
    prov2 = json.loads((book_dir / "provenance.json").read_text(encoding="utf-8"))
    assert prov2["file_shas"]["all_mcq.jsonl"] == sha256_file(book_dir / "all_mcq.jsonl")
    ok, issues = validate_provenance(book_dir, ROOT / "scripts")
    assert ok, issues


# ---------------------------------------------------------------------------
# P0-4: upstream provenance requires generation-chain fingerprints
# ---------------------------------------------------------------------------


def test_recovered_rejected_when_chain_fingerprints_missing(tmp_path):
    """P0-4: a 'recovered' upstream provenance WITHOUT distill_script_sha256 /
    prompt_sha256 / config_sha256 must NOT validate (generation chain unprovable)."""
    from scripts.classic_artifacts import validate_provenance

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book_dir / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book_dir / "raw_001.txt").write_text("原文", encoding="utf-8")

    prov = {
        "generated_at": "2025-01-01", "anchor_commit": "abc123",
        "anchor_commit_verified": True, "no_api": True,
        "input_baseline_commit": "303d375", "worktree_dirty": False,
        "code_fingerprint": "a" * 64, "upstream_provenance_status": "recovered",
        "file_shas": {}, "code_shas": {}, "raw_text_shas": {},
        "input_baseline_blob_shas": {},
        "upstream_provenance": {
            "provider": "deepseek", "model": "m", "source_url": "u",
            "source_version": "v", "distill_script": "scripts/distill_lib.py",
            "thinking_mode": "disabled", "temperature": 0.0,
            "upstream_artifact_shas": {"all_rules.json": "a" * 64, "all_mcq.jsonl": "b" * 64},
            "upstream_artifact_commit": "abc123",
            # NOTE: distill_script_sha256 / prompt_sha256 / config_sha256 absent.
        },
    }
    (book_dir / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")

    ok, issues = validate_provenance(book_dir, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "distill_script_sha256" in joined
    assert "prompt_sha256" in joined
    assert "config_sha256" in joined


# ---------------------------------------------------------------------------
# P0-1: post-publish validation failure must roll back (regen + fill)
# ---------------------------------------------------------------------------


def test_regen_rolls_back_when_post_publish_validation_fails(tmp_path, monkeypatch):
    """P0-1: regen rolls back published files when post-publish provenance
    validation fails (not just mid-replace failures)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    rules = [{"id": "tb_000_000", "source_chapter": "ch1", "subject": "甲木",
              "rule": "甲木喜水", "original_text": "甲木", "category": "天干"}]
    (book_dir / "all_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text(
        json.dumps({"needs_mcq_regen": True}), encoding="utf-8")
    original_rules = (book_dir / "all_rules.json").read_bytes()

    def mock_call(prompt, timeout=120):
        return json.dumps({
            "question": "甲木为何喜水？",
            "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A", "explanation": "甲木喜水有利",
            "difficulty": "基础", "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})
    # Force post-publish provenance validation to fail.
    monkeypatch.setattr(rm, "validate_provenance",
                        lambda *a, **k: (False, ["simulated validation failure"]))

    ledger_path = tmp_path / ".regen_ledger.json"
    b = ("r1", "a" * 64, "b" * 64)
    with pytest.raises(ConservationError):
        rm.regen_book("testbook", global_budget=100, ledger_path=ledger_path,
                      run_id=b[0], code_sha=b[1], rules_sha=b[2])

    # Rolled back: no new MCQ content, no provenance.json left, no staging/backup.
    assert (book_dir / "all_rules.json").read_bytes() == original_rules
    assert (book_dir / "all_mcq.jsonl").read_text(encoding="utf-8") == ""
    assert not (book_dir / "provenance.json").exists()
    assert not list(book_dir.glob(".regen_staging_*"))
    assert not list(book_dir.glob(".publish_backup_*"))


def test_fill_rolls_back_when_post_publish_validation_fails(tmp_path, monkeypatch):
    """P0-1: fill rolls back published files when post-publish provenance
    validation fails (not just mid-replace failures)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.fill_missing_chapters as fmc
    import distill_lib as dl

    book_dir = tmp_path / "zipingzhenquan"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text("[]", encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "progress.json").write_text(
        json.dumps({"done": [], "total_rules": 0, "total_mcqs": 0}), encoding="utf-8")
    (book_dir / "raw_full.txt").write_text("第一章 甲木\n甲木参天", encoding="utf-8")
    (book_dir / "chapter_list.txt").write_text("1. 第一章 甲木", encoding="utf-8")

    mock_rules = [{"id": "zpzq_000_000", "source_chapter": "第一章 甲木", "subject": "甲木",
                   "rule": "甲木参天", "original_text": "甲木", "category": "天干"}]
    monkeypatch.setattr(dl, "distill_chapter", lambda *a, **k: mock_rules)

    def mock_call(prompt, timeout=120):
        return json.dumps({
            "question": "甲木为何参天？",
            "options": {"A": "甲木参天", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A", "explanation": "甲木参天", "difficulty": "基础", "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)
    monkeypatch.setattr(fmc, "BASE", tmp_path)
    monkeypatch.setattr(fmc, "validate_provenance",
                        lambda *a, **k: (False, ["simulated validation failure"]))

    ledger_path = tmp_path / ".fill_ledger.json"
    b = ("r1", "a" * 64, "b" * 64)
    with pytest.raises(ConservationError):
        fmc.fill_book("zipingzhenquan", global_budget=100, ledger_path=ledger_path,
                      run_id=b[0], code_sha=b[1], rules_sha=b[2])

    # Rolled back: no rules/mcq/new-raw files, no staging/backup left.
    assert (book_dir / "all_rules.json").read_text(encoding="utf-8") == "[]"
    assert (book_dir / "all_mcq.jsonl").read_text(encoding="utf-8") == ""
    new_raws = [f for f in book_dir.glob("raw_*.txt") if f.name != "raw_full.txt"]
    assert len(new_raws) == 0, f"new raw files left behind: {new_raws}"
    assert not list(book_dir.glob(".fill_staging_*"))
    assert not list(book_dir.glob(".publish_backup_*"))


# ---------------------------------------------------------------------------
# P0-2: run bindings are sensitive to the full input manifest
# ---------------------------------------------------------------------------


def test_fill_run_bindings_sensitive_to_input_manifest(tmp_path, monkeypatch):
    """P0-2: changing any manifest-covered input changes the run_id."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.fill_missing_chapters as fmc
    monkeypatch.setattr(fmc, "BASE", tmp_path)

    book_dir = tmp_path / "zipingzhenquan"
    book_dir.mkdir()
    (book_dir / "raw_full.txt").write_text("甲木参天", encoding="utf-8")
    (book_dir / "chapter_list.txt").write_text("1. 第一章", encoding="utf-8")
    (book_dir / "progress.json").write_text("{}", encoding="utf-8")
    (book_dir / "all_rules.json").write_text("[]", encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")

    rid1 = fmc._compute_run_bindings(["zipingzhenquan"])
    # Changing a manifest-covered input (chapter_list.txt) must change run_id.
    (book_dir / "chapter_list.txt").write_text("1. 第一章\n2. 第二章", encoding="utf-8")
    rid2 = fmc._compute_run_bindings(["zipingzhenquan"])
    assert rid1[0] != rid2[0]
    assert rid1[2] != rid2[2]  # rules_sha must change too


def test_regen_run_bindings_sensitive_to_rules_input(tmp_path, monkeypatch):
    """P0-2: regen run_id changes when the rules input changes."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    monkeypatch.setattr(rm, "BASE", tmp_path)

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    (book_dir / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    rid1 = rm._compute_run_bindings(["testbook"])
    (book_dir / "all_rules.json").write_text('[{"id":"r1"},{"id":"r2"}]', encoding="utf-8")
    rid2 = rm._compute_run_bindings(["testbook"])
    assert rid1[0] != rid2[0]


# ---------------------------------------------------------------------------
# P0-4: forged generation-chain SHA / missing script are rejected
# ---------------------------------------------------------------------------


def _write_recovered_book(tmp_path: Path, upstream: dict) -> Path:
    """Write a book dir with a 'recovered' upstream provenance and return it."""
    from scripts.classic_artifacts import validate_provenance  # noqa: F401
    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book_dir / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book_dir / "raw_001.txt").write_text("原文", encoding="utf-8")
    prov = {
        "generated_at": "2025-01-01", "anchor_commit": "abc123",
        "anchor_commit_verified": True, "no_api": True,
        "input_baseline_commit": "303d375", "worktree_dirty": False,
        "code_fingerprint": "a" * 64, "upstream_provenance_status": "recovered",
        "file_shas": {}, "code_shas": {}, "raw_text_shas": {},
        "input_baseline_blob_shas": {},
        "upstream_provenance": upstream,
    }
    (book_dir / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    return book_dir


def test_recovered_rejected_when_prompt_or_config_sha_forged(tmp_path):
    """P0-4: prompt_sha256 / config_sha256 that do NOT match the frozen
    canonical values are rejected, so arbitrary 64-char strings cannot pass."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance

    script_sha = hashlib.sha256((ROOT / "scripts" / "distill_lib.py").read_bytes()).hexdigest()
    upstream = {
        "provider": "deepseek", "model": "deepseek-v4-flash", "source_url": "u",
        "source_version": "v", "distill_script": "distill_lib.py",
        "thinking_mode": "disabled", "temperature": 0.0,
        "upstream_artifact_shas": {"all_rules.json": "a" * 64, "all_mcq.jsonl": "b" * 64},
        "upstream_artifact_commit": "abc123",
        "distill_script_sha256": script_sha,
        "prompt_sha256": "f" * 64,   # forged, not canonical
        "config_sha256": "e" * 64,   # forged, not canonical
    }
    book_dir = _write_recovered_book(tmp_path, upstream)
    ok, issues = validate_provenance(book_dir, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "prompt_sha256 mismatch" in joined
    assert "config_sha256 mismatch" in joined


def test_recovered_rejected_when_distill_script_missing(tmp_path):
    """P0-4: a declared distill_script that does not exist in the allowed
    scripts dir is a hard failure (fail-closed), not silently accepted."""
    from scripts.classic_artifacts import validate_provenance

    upstream = {
        "provider": "deepseek", "model": "m", "source_url": "u", "source_version": "v",
        "distill_script": "no_such_script.py",
        "thinking_mode": "disabled", "temperature": 0.0,
        "upstream_artifact_shas": {"all_rules.json": "a" * 64, "all_mcq.jsonl": "b" * 64},
        "upstream_artifact_commit": "abc123",
        "distill_script_sha256": "c" * 64,
        "prompt_sha256": "d" * 64,
        "config_sha256": "e" * 64,
    }
    book_dir = _write_recovered_book(tmp_path, upstream)
    ok, issues = validate_provenance(book_dir, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "not found in allowed scripts dir" in joined


# ---------------------------------------------------------------------------
# P0-1: raw_sources derivation anchors are recomputable, not forgeable
# ---------------------------------------------------------------------------


def test_derivation_anchor_accepts_genuine_slice():
    """A genuine substring_strip anchor whose slice reproduces the target SHA."""
    import hashlib
    from scripts.classic_artifacts import _verify_derivation_anchor
    src = b"abcdefghij"
    slice_bytes = src[2:8]  # b"cdefgh" -- strip is identity
    target = hashlib.sha256(slice_bytes).hexdigest()
    anchor = {
        "derived_from": "raw_full.txt",
        "derived_from_blob_sha256": hashlib.sha256(src).hexdigest(),
        "extraction_strategy": "substring_strip",
        "source_start": 2,
        "source_end": 8,
    }
    assert _verify_derivation_anchor("raw_001.txt", anchor,
                                     hashlib.sha256(src).hexdigest(), src, target) is None


def test_derivation_anchor_rejects_forged_source_blob():
    """An anchor claiming derived_from=raw_full.txt but with a WRONG source blob
    is rejected (cannot pass by just naming the source)."""
    import hashlib
    from scripts.classic_artifacts import _verify_derivation_anchor
    src = b"abcdefghij"
    anchor = {
        "derived_from": "raw_full.txt",
        "derived_from_blob_sha256": "f" * 64,  # forged, != real source sha256
        "extraction_strategy": "substring_strip",
        "source_start": 2,
        "source_end": 8,
    }
    err = _verify_derivation_anchor("raw_001.txt", anchor,
                                    hashlib.sha256(src).hexdigest(), src,
                                    hashlib.sha256(b"cdefgh").hexdigest())
    assert err is not None
    assert "derived_from_blob_sha256 mismatch" in err


def test_derivation_anchor_rejects_wrong_slice():
    """Even with the correct source blob, a slice that does NOT reproduce the
    target SHA is rejected."""
    import hashlib
    from scripts.classic_artifacts import _verify_derivation_anchor
    src = b"abcdefghij"
    anchor = {
        "derived_from": "raw_full.txt",
        "derived_from_blob_sha256": hashlib.sha256(src).hexdigest(),
        "extraction_strategy": "substring_strip",
        "source_start": 0,
        "source_end": 3,  # wrong slice -> target sha won't match
    }
    err = _verify_derivation_anchor("raw_001.txt", anchor,
                                    hashlib.sha256(src).hexdigest(), src,
                                    hashlib.sha256(b"cdefgh").hexdigest())
    assert err is not None
    assert "re-extraction mismatch" in err


def test_derivation_anchor_rejects_unsupported_strategy():
    """An unsupported extraction_strategy cannot be accepted."""
    import hashlib
    from scripts.classic_artifacts import _verify_derivation_anchor
    src = b"abcdefghij"
    anchor = {
        "derived_from": "raw_full.txt",
        "derived_from_blob_sha256": hashlib.sha256(src).hexdigest(),
        "extraction_strategy": "magic",
    }
    err = _verify_derivation_anchor("raw_001.txt", anchor,
                                    hashlib.sha256(src).hexdigest(), src, "0" * 64)
    assert err is not None
    assert "unsupported extraction_strategy" in err


# ---------------------------------------------------------------------------
# P0-2: post-publish validation that RAISES (not just returns False) rolls back
# ---------------------------------------------------------------------------


def test_regen_rolls_back_when_post_publish_validation_raises(tmp_path, monkeypatch):
    """P0-2: if validate_provenance raises (I/O, permission, malformed field),
    regen still rolls back the published files."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl

    book_dir = tmp_path / "testbook"
    book_dir.mkdir()
    rules = [{"id": "tb_000_000", "source_chapter": "ch1", "subject": "甲木",
              "rule": "甲木喜水", "original_text": "甲木", "category": "天干"}]
    (book_dir / "all_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (book_dir / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book_dir / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book_dir / "remediation_meta.json").write_text(
        json.dumps({"needs_mcq_regen": True}), encoding="utf-8")
    original_rules = (book_dir / "all_rules.json").read_bytes()

    def mock_call(prompt, timeout=120):
        return json.dumps({
            "question": "甲木为何喜水？",
            "options": {"A": "甲木喜水", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A", "explanation": "甲木喜水有利",
            "difficulty": "基础", "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})
    # validate_provenance RAISES instead of returning False.
    def boom(*a, **k):
        raise RuntimeError("simulated validator crash")
    monkeypatch.setattr(rm, "validate_provenance", boom)

    ledger_path = tmp_path / ".regen_ledger.json"
    b = ("r1", "a" * 64, "b" * 64)
    with pytest.raises(RuntimeError):
        rm.regen_book("testbook", global_budget=100, ledger_path=ledger_path,
                      run_id=b[0], code_sha=b[1], rules_sha=b[2])

    assert (book_dir / "all_rules.json").read_bytes() == original_rules
    assert (book_dir / "all_mcq.jsonl").read_text(encoding="utf-8") == ""
    assert not (book_dir / "provenance.json").exists()
    assert not list(book_dir.glob(".regen_staging_*"))
    assert not list(book_dir.glob(".publish_backup_*"))


# ---------------------------------------------------------------------------
# P0-3: frozen model config + path-traversal rejection
# ---------------------------------------------------------------------------


def test_recovered_rejected_when_model_config_not_frozen(tmp_path):
    """P0-3: provenance declaring non-frozen provider/model is rejected even if
    its config_sha256 is internally self-consistent."""
    from scripts.classic_artifacts import validate_provenance

    upstream = {
        "provider": "deepseek", "model": "evil-model", "source_url": "u",
        "source_version": "v", "distill_script": "distill_lib.py",
        "thinking_mode": "disabled", "temperature": 0.0,
        "upstream_artifact_shas": {"all_rules.json": "a" * 64, "all_mcq.jsonl": "b" * 64},
        "upstream_artifact_commit": "abc123",
        "distill_script_sha256": "c" * 64,
        "prompt_sha256": "d" * 64,
        "config_sha256": "e" * 64,
    }
    book_dir = _write_recovered_book(tmp_path, upstream)
    ok, issues = validate_provenance(book_dir, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "model config not frozen" in joined


def test_recovered_rejected_when_distill_script_traversal(tmp_path):
    """P0-3: a distill_script with path traversal (../../evil/...) is rejected
    outright, not silently normalized to a basename."""
    from scripts.classic_artifacts import validate_provenance

    upstream = {
        "provider": "deepseek", "model": "deepseek-v4-flash", "source_url": "u",
        "source_version": "v", "distill_script": "../../evil/distill_lib.py",
        "thinking_mode": "disabled", "temperature": 0.0,
        "upstream_artifact_shas": {"all_rules.json": "a" * 64, "all_mcq.jsonl": "b" * 64},
        "upstream_artifact_commit": "abc123",
        "distill_script_sha256": "c" * 64,
        "prompt_sha256": "d" * 64,
        "config_sha256": "e" * 64,
    }
    book_dir = _write_recovered_book(tmp_path, upstream)
    ok, issues = validate_provenance(book_dir, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "path traversal" in joined


# ---------------------------------------------------------------------------
# P0-4: run identity respects target ORDER
# ---------------------------------------------------------------------------


def test_regen_run_bindings_sensitive_to_target_order(tmp_path, monkeypatch):
    """P0-4: reordering targets changes run_id (no sort_keys)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    monkeypatch.setattr(rm, "BASE", tmp_path)
    for k in ("bookA", "bookB"):
        d = tmp_path / k
        d.mkdir()
        (d / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    rid1 = rm._compute_run_bindings(["bookA", "bookB"])
    rid2 = rm._compute_run_bindings(["bookB", "bookA"])
    assert rid1[0] != rid2[0]


# ---------------------------------------------------------------------------
# P0-1: frozen run manifest survives the run modifying its own inputs
# ---------------------------------------------------------------------------


def test_frozen_run_manifest_survives_input_modification(tmp_path):
    """P0-1: after freezing, resume does NOT recompute identity from files the
    run modified -- the frozen manifest keeps the SAME run_id."""
    from scripts.distill_lib import freeze_run_manifest, LedgerCorruptionError
    mp = tmp_path / ".regen_run_manifest.json"
    code_files = [ROOT / "scripts" / "distill_lib.py"]
    manifest_before = {
        "frozen_config_sha256": "c" * 64,
        "targets": {"bookA": {"all_rules.json_sha256": "a" * 64}},
    }
    rid1 = freeze_run_manifest(mp, manifest_before, code_files)
    # Simulate a resume where the run's own outputs changed the inputs:
    manifest_after = {
        "frozen_config_sha256": "c" * 64,
        "targets": {"bookA": {"all_rules.json_sha256": "f" * 64}},  # changed by run
    }
    rid2 = freeze_run_manifest(mp, manifest_after, code_files)  # reloads frozen
    assert rid1 == rid2  # resume keeps the frozen identity
    # A genuinely fresh run (no frozen manifest) would get a DIFFERENT identity
    # from the post-run inputs.
    fresh = tmp_path / ".fresh.json"
    rid3 = freeze_run_manifest(fresh, manifest_after, code_files)
    assert rid3[0] != rid1[0]


def test_frozen_run_manifest_tamper_detected(tmp_path):
    """P0-1: a tampered frozen manifest (sha mismatch) is rejected."""
    from scripts.distill_lib import freeze_run_manifest, LedgerCorruptionError
    mp = tmp_path / ".regen_run_manifest.json"
    code_files = [ROOT / "scripts" / "distill_lib.py"]
    freeze_run_manifest(mp, {"targets": {}}, code_files)
    # Corrupt the stored sha
    import json as _json
    data = _json.loads(mp.read_text(encoding="utf-8"))
    data["manifest_sha256"] = "0" * 64
    mp.write_text(_json.dumps(data), encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="tampered"):
        freeze_run_manifest(mp, {"targets": {}}, code_files)


# ---------------------------------------------------------------------------
# P0-2: clean MCQs must be bound to an api_generation chain
# ---------------------------------------------------------------------------


def _minimal_prov_with_mcq(book_dir: Path, api_gen: dict | None) -> None:
    """Write a provenance with required fields; optionally with api_generation."""
    from scripts.classic_artifacts import sha256_file
    names = ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
             "quarantine_mcq.jsonl", "remediation_meta.json")
    prov = {
        "generated_at": "2025-01-01", "anchor_commit": "abc123",
        "anchor_commit_verified": True, "no_api": True,
        "input_baseline_commit": "303d375", "worktree_dirty": False,
        "code_fingerprint": "a" * 64, "upstream_provenance_status": "unavailable",
        "file_shas": {n: sha256_file(book_dir / n) for n in names},
        "code_shas": {}, "raw_text_shas": {}, "input_baseline_blob_shas": {},
    }
    if api_gen is not None:
        prov["api_generation"] = api_gen
    (book_dir / "provenance.json").write_text(
        json.dumps(prov, ensure_ascii=False), encoding="utf-8")


def test_clean_mcqs_require_api_generation(tmp_path):
    """P0-2: clean MCQs without an api_generation record fail validation."""
    from scripts.classic_artifacts import validate_provenance
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q"}\n', encoding="utf-8")
    _minimal_prov_with_mcq(book, api_gen=None)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    assert "no api_generation" in "; ".join(issues)


def test_api_generation_mcq_output_sha_mismatch_fails(tmp_path):
    """P0-2: api_generation whose mcq_output_sha does NOT match the current
    all_mcq.jsonl is rejected (old chain cannot vouch for new MCQs)."""
    from scripts.classic_artifacts import validate_provenance
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q"}\n', encoding="utf-8")
    api_gen = {
        "run_id": "r1", "code_sha": "a" * 64, "rules_sha": "b" * 64,
        "rules_input_sha": "c" * 64,
        "mcq_output_sha": "f" * 64,  # forged -- does not match actual file
        "prompt_sha256": "d" * 64, "config_sha256": "e" * 64, "script_sha256": "g" * 64,
        "provider": "deepseek", "model": "deepseek-v4-flash",
        "thinking_mode": "disabled", "temperature": 0.0,
        "calls_made": 1, "accepted": 1, "skipped": 0, "completed": True,
    }
    _minimal_prov_with_mcq(book, api_gen)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "mcq_output_sha mismatch" in joined


# ---------------------------------------------------------------------------
# P0-3: single authoritative frozen model config (used by _call AND the hash)
# ---------------------------------------------------------------------------


def test_call_sends_frozen_model_config(monkeypatch):
    """P0-3: _call() sends exactly FROZEN_MODEL_CONFIG; canonical_config_sha256
    hashes that same constant -- one authoritative copy."""
    import hashlib, json
    from scripts.distill_lib import _call, FROZEN_MODEL_CONFIG, canonical_config_sha256
    import claude_api
    captured = {}
    def fake_call(messages, **kwargs):
        captured.update(kwargs)
        return "[]", None
    monkeypatch.setattr(claude_api, "call_model_messages_sync_with_meta", fake_call)
    _call("test")
    assert captured["provider"] == FROZEN_MODEL_CONFIG["provider"]
    assert captured["model"] == FROZEN_MODEL_CONFIG["model"]
    assert captured["thinking_mode"] == FROZEN_MODEL_CONFIG["thinking_mode"]
    assert captured["temperature"] == FROZEN_MODEL_CONFIG["temperature"]
    canonical = json.dumps(FROZEN_MODEL_CONFIG, sort_keys=True,
                           ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert canonical_config_sha256() == hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# Medium: duplicate targets are rejected
# ---------------------------------------------------------------------------


def test_regen_main_rejects_duplicate_targets(tmp_path, monkeypatch):
    """Medium: a CLI invocation with duplicate targets must be rejected."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})
    # P0-14: keep the shared allowlist consistent with the patched BOOKS.
    monkeypatch.setitem(dl.VALID_TARGETS_BY_OPERATION, "regen", ("testbook",))
    monkeypatch.setattr("sys.argv", ["regen_mcq.py", "testbook", "testbook"])
    assert rm.main() == 2


# ---------------------------------------------------------------------------
# P0: invalid explicit targets fail closed (never expand into a full run)
# ---------------------------------------------------------------------------


def _spy_run_bindings(monkeypatch, module):
    """Spy on module._compute_run_bindings; returns the recorded call list."""
    calls = []
    real = module._compute_run_bindings
    def spy(*a, **k):
        calls.append(a)
        return real(*a, **k)
    monkeypatch.setattr(module, "_compute_run_bindings", spy)
    return calls


def test_regen_main_rejects_invalid_target_without_run_bindings(tmp_path, monkeypatch):
    """P0: `regen ghostbook` returns 2 and never computes run bindings."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})
    monkeypatch.setitem(dl.VALID_TARGETS_BY_OPERATION, "regen", ("testbook",))
    calls = _spy_run_bindings(monkeypatch, rm)
    monkeypatch.setattr("sys.argv", ["regen_mcq.py", "ghostbook"])
    assert rm.main() == 2
    assert calls == []


def test_fill_main_rejects_invalid_target_without_run_bindings(tmp_path, monkeypatch):
    """P0: `fill ghostbook` returns 2 and never computes run bindings."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.fill_missing_chapters as fmc
    import distill_lib as dl
    monkeypatch.setattr(fmc, "BASE", tmp_path)
    monkeypatch.setitem(dl.VALID_TARGETS_BY_OPERATION, "fill", ("zipingzhenquan",))
    calls = _spy_run_bindings(monkeypatch, fmc)
    monkeypatch.setattr("sys.argv", ["fill_missing_chapters.py", "ghostbook"])
    assert fmc.main() == 2
    assert calls == []


def test_regen_main_rejects_mixed_valid_invalid_targets(tmp_path, monkeypatch):
    """P0: mixed valid+invalid explicit targets reject the whole run
    (never run the legal subset)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})
    monkeypatch.setitem(dl.VALID_TARGETS_BY_OPERATION, "regen", ("testbook",))
    calls = _spy_run_bindings(monkeypatch, rm)
    monkeypatch.setattr("sys.argv", ["regen_mcq.py", "testbook", "ghostbook"])
    assert rm.main() == 2
    assert calls == []


def test_regen_main_no_args_defaults_to_all_allowed(tmp_path, monkeypatch):
    """P0: no explicit args still default to the full shared allowlist."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})
    monkeypatch.setitem(dl.VALID_TARGETS_BY_OPERATION, "regen", ("testbook",))
    monkeypatch.setattr(dl, "_call", lambda *a, **k: "")
    calls = []
    def spy(dir_key, *a, **k):
        calls.append(dir_key)
        return {"error": "simulated"}  # 模拟失败返回：跳过 prepared-receipt 消费路径，只验证 targets 展开
    monkeypatch.setattr(rm, "regen_book", spy)
    monkeypatch.setattr("sys.argv", ["regen_mcq.py"])
    rm.main()
    assert calls == ["testbook"]  # 无参数 → 默认全部（allowlist 仅 testbook）


def test_regen_main_fail_closed_on_allowlist_metadata_drift(tmp_path, monkeypatch):
    """P0: shared allowlist vs BOOKS drift → regen rejects outright
    (no filtering-and-continue), even with no explicit args."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"testbook": ("测试书", "tb")})
    # Drift: allowlist contains a target missing from BOOKS metadata.
    monkeypatch.setitem(dl.VALID_TARGETS_BY_OPERATION, "regen", ("ghostbook",))
    calls = _spy_run_bindings(monkeypatch, rm)
    monkeypatch.setattr("sys.argv", ["regen_mcq.py"])
    assert rm.main() == 2
    assert calls == []


def test_producers_use_single_shared_target_mapping():
    """P0-14: the producers' local book registries must exactly match the
    shared authoritative allowlist. A drift would let a producer accept a run
    the validator is guaranteed to reject."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    # regen's display registry must match the shared regen allowlist, so
    # main() and the validator share one authority (set equality; order is
    # decided by the shared mapping for default runs).
    assert set(rm.BOOKS) == set(dl.VALID_TARGETS_BY_OPERATION["regen"])
    # fill's shared allowlist is a subset of regen's (fill touches 2 of the 4).
    assert set(dl.VALID_TARGETS_BY_OPERATION["fill"]) <= \
        set(dl.VALID_TARGETS_BY_OPERATION["regen"])
    # The shared mapping itself is a closed legal pairing with VALID_MODES.
    assert set(dl.VALID_TARGETS_BY_OPERATION) == set(__import__(
        "scripts.classic_artifacts", fromlist=["VALID_MODES"]).VALID_MODES)


# ---------------------------------------------------------------------------
# P0-1: resume rejects different targets / changed code
# ---------------------------------------------------------------------------


def test_frozen_manifest_rejects_target_change(tmp_path):
    """P0-1: a stale manifest for a DIFFERENT target set must be rejected."""
    from scripts.distill_lib import freeze_run_manifest, LedgerCorruptionError
    mp = tmp_path / ".regen_run_manifest.json"
    code = [ROOT / "scripts" / "distill_lib.py"]
    freeze_run_manifest(mp, {"immutable": {"targets": ["A", "B"]}, "mutable": {}}, code)
    m2 = {"immutable": {"targets": ["A"]}, "mutable": {}}  # different targets
    with pytest.raises(LedgerCorruptionError, match="immutable intent mismatch"):
        freeze_run_manifest(mp, m2, code)


def test_frozen_manifest_rejects_code_drift(tmp_path):
    """P0-1: resume with changed code (different code SHA) must be rejected."""
    from scripts.distill_lib import freeze_run_manifest, LedgerCorruptionError
    mp = tmp_path / ".regen_run_manifest.json"
    code = [ROOT / "scripts" / "distill_lib.py"]
    freeze_run_manifest(mp, {"immutable": {"targets": ["A"]}, "mutable": {}}, code)
    # Simulate code change: same filename, different content.
    fake = tmp_path / "distill_lib.py"
    fake.write_text("CHANGED CODE", encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="code drift"):
        freeze_run_manifest(mp, {"immutable": {"targets": ["A"]}, "mutable": {}}, [fake])


# ---------------------------------------------------------------------------
# P0-2: resume must not re-run a completed book
# ---------------------------------------------------------------------------


def test_regen_resume_skips_completed_book(tmp_path, monkeypatch):
    """P0-2: after book A completed, an explicit-target resume runs only B."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.regen_mcq as rm
    import distill_lib as dl
    monkeypatch.setattr(rm, "BASE", tmp_path)
    monkeypatch.setattr(rm, "BOOKS", {"bookA": ("A书", "ba"), "bookB": ("B书", "bb")})
    # P0-14: keep the shared allowlist consistent with the patched BOOKS.
    monkeypatch.setitem(dl.VALID_TARGETS_BY_OPERATION, "regen", ("bookA", "bookB"))
    for k in ("bookA", "bookB"):
        d = tmp_path / k
        d.mkdir()
        (d / "all_rules.json").write_text(
            '[{"id":"r1","source_chapter":"ch1","subject":"甲木",'
            '"rule":"甲木喜水","original_text":"甲木","category":"天干"}]',
            encoding="utf-8")
        (d / "all_mcq.jsonl").write_text("", encoding="utf-8")
        (d / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
        (d / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
        (d / "remediation_meta.json").write_text('{"needs_mcq_regen":true}', encoding="utf-8")
    # Freeze the manifest and mark bookA completed (it finished before a crash).
    mp = tmp_path / ".regen_run_manifest.json"
    rm._compute_run_bindings(["bookA", "bookB"], mp)
    dl.append_book_receipt(
        mp, "bookA", "completed", book_dir=tmp_path / "bookA",
        output_names=("all_mcq.jsonl", "quarantine_mcq.jsonl", "remediation_meta.json"))
    monkeypatch.setattr(dl, "_call", lambda *a, **k: "")
    calls = []
    real_regen = rm.regen_book
    def spy(dir_key, *a, **k):
        calls.append(dir_key)
        return real_regen(dir_key, *a, **k)
    monkeypatch.setattr(rm, "regen_book", spy)
    monkeypatch.setattr("sys.argv", ["regen_mcq.py", "bookA", "bookB"])
    rm.main()
    assert "bookA" not in calls, f"completed book re-run: {calls}"
    assert "bookB" in calls


# ---------------------------------------------------------------------------
# P0-3: api_generation fields are verified, not just checked non-empty
# ---------------------------------------------------------------------------


def test_api_generation_forged_shas_rejected(tmp_path):
    """P0-3: keeping mcq_output_sha correct but forging prompt/config/script/
    rules SHAs must fail validation."""
    from scripts.classic_artifacts import validate_provenance, sha256_file
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = {
        "run_id": "r1", "code_sha": "a" * 64, "rules_sha": "b" * 64,
        "rules_input_sha": "c" * 64, "rules_output_sha": "d" * 64, "rules_added": 0,
        "mcq_output_sha": sha256_file(book / "all_mcq.jsonl"),  # correct
        "prompt_sha256": "f" * 64,   # forged
        "config_sha256": "e" * 64,   # forged
        "script_sha256": "g" * 64,   # forged
        "provider": "deepseek", "model": "deepseek-v4-flash",
        "thinking_mode": "disabled", "temperature": 0.0,
        "calls_made": 1, "accepted": 1, "skipped": 0, "completed": True,
    }
    _minimal_prov_with_mcq(book, api_gen)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    joined = "; ".join(issues)
    assert ok is False
    assert "prompt_sha256 mismatch" in joined
    assert "config_sha256 mismatch" in joined
    assert "script_sha256 mismatch" in joined
    assert "rules_output_sha mismatch" in joined


# ---------------------------------------------------------------------------
# P0-4: fill records the actual rule payload; zero-call runs create nothing
# ---------------------------------------------------------------------------


def test_fill_api_generation_records_actual_rule_payload(tmp_path, monkeypatch):
    """P0-4: fill's rules_input_sha hashes the rules ACTUALLY sent this run
    (new_rules_total), and rules_output_sha the final all_rules.json."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.fill_missing_chapters as fmc
    import distill_lib as dl
    book = tmp_path / "zipingzhenquan"
    book.mkdir()
    (book / "all_rules.json").write_text("[]", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book / "progress.json").write_text(
        json.dumps({"done": [], "total_rules": 0, "total_mcqs": 0}), encoding="utf-8")
    (book / "raw_full.txt").write_text("第一章 甲木\n甲木参天", encoding="utf-8")
    (book / "chapter_list.txt").write_text("1. 第一章 甲木", encoding="utf-8")
    mock_rules = [{"id": "zpzq_000_000", "source_chapter": "第一章 甲木", "subject": "甲木",
                   "rule": "甲木参天", "original_text": "甲木", "category": "天干"}]
    monkeypatch.setattr(dl, "distill_chapter", lambda *a, **k: mock_rules)

    def mock_call(prompt, timeout=120):
        return json.dumps({
            "question": "甲木为何参天？",
            "options": {"A": "甲木参天", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A", "explanation": "甲木参天", "difficulty": "基础", "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)
    monkeypatch.setattr(fmc, "BASE", tmp_path)
    manifest_path = tmp_path / ".fill_run_manifest.json"
    b = fmc._compute_run_bindings(["zipingzhenquan"], manifest_path)[:3]
    fmc.fill_book("zipingzhenquan", global_budget=100,
                  ledger_path=tmp_path / ".fill_ledger.json",
                  run_id=b[0], code_sha=b[1], rules_sha=b[2],
                  manifest_path=manifest_path)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    api = prov.get("api_generation")
    assert api is not None
    import hashlib
    rules_input_payload = json.dumps(
        mock_rules, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    rules_out = json.loads((book / "all_rules.json").read_text(encoding="utf-8"))
    rules_output_payload = json.dumps(
        rules_out, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert api["rules_input_sha"] == hashlib.sha256(rules_input_payload).hexdigest()
    assert api["rules_output_sha"] == hashlib.sha256(rules_output_payload).hexdigest()
    assert api["rules_added"] == 1


def test_fill_noop_does_not_create_api_generation(tmp_path, monkeypatch):
    """P0-4: when there is nothing to fill (zero API calls), fill skips and
    does NOT create an api_generation record for the existing MCQs."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.fill_missing_chapters as fmc
    monkeypatch.setattr(fmc, "BASE", tmp_path)
    book = tmp_path / "zipingzhenquan"
    book.mkdir()
    (book / "all_rules.json").write_text("[]", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"old"}\n', encoding="utf-8")
    (book / "progress.json").write_text(
        json.dumps({"done": ["第一章 甲木"], "total_rules": 0, "total_mcqs": 1}), encoding="utf-8")
    (book / "raw_full.txt").write_text("第一章 甲木\n甲木参天", encoding="utf-8")
    (book / "chapter_list.txt").write_text("1. 第一章 甲木", encoding="utf-8")
    b = ("r1", "a" * 64, "b" * 64)
    result = fmc.fill_book("zipingzhenquan", global_budget=100,
                           ledger_path=tmp_path / ".fill_ledger.json",
                           run_id=b[0], code_sha=b[1], rules_sha=b[2])
    assert result.get("skipped") is True
    assert not (book / "provenance.json").exists()


# ---------------------------------------------------------------------------
# Round-5 P0-1: resume rejects forged identity / forged completed receipt
# ---------------------------------------------------------------------------


def test_resume_rejects_forged_identity(tmp_path):
    """P0-1: tampering run_id/rules_sha (stored outside the manifest hash) after
    freeze is rejected on resume because the identity is re-derived."""
    import hashlib
    from scripts.distill_lib import freeze_run_manifest, LedgerCorruptionError
    mp = tmp_path / ".manifest.json"
    code = [ROOT / "scripts" / "distill_lib.py"]
    manifest = {"immutable": {"targets": ["bookA"]}, "mutable": {}}
    freeze_run_manifest(mp, manifest, code)
    data = json.loads(mp.read_text(encoding="utf-8"))
    data["run_id"] = "forgedrunid12345"
    data["rules_sha"] = "f" * 64
    mp.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="forged identity"):
        freeze_run_manifest(mp, manifest, code)


def test_resume_rejects_forged_completed_receipt(tmp_path):
    """P0-1: a forged 'completed' receipt (valid sha but empty output_shas, or a
    transplanted receipt) cannot silently skip a book on resume."""
    import hashlib
    from scripts.distill_lib import freeze_run_manifest, _receipt_sha, LedgerCorruptionError
    mp = tmp_path / ".manifest.json"
    code = [ROOT / "scripts" / "distill_lib.py"]
    manifest = {"immutable": {"targets": ["bookA"]}, "mutable": {}}
    freeze_run_manifest(mp, manifest, code)
    data = json.loads(mp.read_text(encoding="utf-8"))
    run_id = data["run_id"]
    msha = data["manifest_sha256"]
    # Forge a completed receipt with a valid sha but NO output_shas -- this is
    # the "skip a book for free" attack.
    rsha = _receipt_sha(msha, run_id, "bookA", "completed", {})
    data["book_receipts"] = [{"target": "bookA", "status": "completed",
                              "output_shas": {}, "prev_sha": msha, "sha": rsha}]
    mp.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="no output_shas"):
        freeze_run_manifest(mp, manifest, code)


# ---------------------------------------------------------------------------
# Round-5 P0-2: pending mutable input drift is rejected on resume
# ---------------------------------------------------------------------------


def test_resume_rejects_pending_mutable_drift(tmp_path):
    """P0-2: a pending book whose mutable input changed after freeze (before the
    run processed it) is rejected -- the change did not come from this run."""
    import hashlib
    from scripts.distill_lib import freeze_run_manifest, LedgerCorruptionError
    mp = tmp_path / ".manifest.json"
    code = [ROOT / "scripts" / "distill_lib.py"]
    book = tmp_path / "bookA"
    book.mkdir()
    (book / "progress.json").write_text('{"done":[]}', encoding="utf-8")
    frozen_sha = hashlib.sha256(b'{"done":[]}').hexdigest()
    manifest = {
        "immutable": {"targets": ["bookA"]},
        "mutable": {"bookA": {"progress.json_sha256": frozen_sha,
                              "progress.json_bytes": 11}},
    }
    freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)
    # Externally modify the pending book's mutable input.
    (book / "progress.json").write_text('{"done":["ch1"]}', encoding="utf-8")
    with pytest.raises(LedgerCorruptionError, match="mutable input drift"):
        freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)


# ---------------------------------------------------------------------------
# Round-5 P0-3: self-consistent archived identity tampering is detected
# ---------------------------------------------------------------------------


def test_validator_rejects_self_consistent_identity_tamper(tmp_path):
    """P0-3: tampering run_manifest AND api_generation identity to the SAME forged
    values is still detected because the validator re-derives from canonical
    sources (manifest sha + code scope + binding formula)."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance, sha256_file, mcq_record_sha256
    from scripts.distill_lib import (
        canonical_prompt_sha256, canonical_config_sha256, FROZEN_MODEL_CONFIG)
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q","id":"m1"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    rm_manifest = {"immutable": {"targets": ["testbook"]}, "mutable": {}}
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    # Forge a self-consistent identity that does NOT match the re-derived one.
    forged_code = "f" * 64
    forged_rules = "e" * 64
    forged_run = hashlib.sha256(
        (forged_code + ":" + forged_rules).encode()).hexdigest()[:16]
    rules_io = sha256_file(book / "all_rules.json")
    mcq_io = sha256_file(book / "all_mcq.jsonl")
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": forged_run, "code_sha": forged_code, "rules_sha": forged_rules}
    api_gen = {
        "run_id": forged_run, "code_sha": forged_code, "rules_sha": forged_rules,
        "rules_input_sha": rules_io, "rules_output_sha": rules_io, "rules_added": 0,
        "mcq_output_sha": mcq_io,
        "generated_mcq_sha256_by_id": {"m1": mcq_record_sha256({"question": "q", "id": "m1"})},
        "prompt_sha256": canonical_prompt_sha256(), "config_sha256": canonical_config_sha256(),
        "script_sha256": sha256_file(ROOT / "scripts" / "distill_lib.py"),
        "provider": FROZEN_MODEL_CONFIG["provider"], "model": FROZEN_MODEL_CONFIG["model"],
        "thinking_mode": FROZEN_MODEL_CONFIG["thinking_mode"],
        "temperature": FROZEN_MODEL_CONFIG["temperature"],
        "calls_made": 1, "accepted": 1, "skipped": 0, "completed": True,
    }
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "re-derived" in joined


# ---------------------------------------------------------------------------
# Round-5 P0-4: forged rules_input_sha / missing MCQ attribution rejected
# ---------------------------------------------------------------------------


def _valid_no_manifest_api_gen(book):
    """Build a self-consistent api_generation for the no-manifest validator path."""
    import hashlib
    from scripts.distill_lib import (
        canonical_prompt_sha256, canonical_config_sha256, FROZEN_MODEL_CONFIG,
        compute_code_sha, ledger_code_files)
    from scripts.classic_artifacts import sha256_file, mcq_record_sha256
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    ident_rules_sha = hashlib.sha256(
        json.dumps({"immutable": {"targets": ["testbook"]}, "mutable": {}},
                   ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    run_id = hashlib.sha256(
        (code_sha + ":" + ident_rules_sha).encode()).hexdigest()[:16]
    rules_io = sha256_file(book / "all_rules.json")
    _mcq_record = {"question": "q", "id": "m1"}
    return {
        "run_id": run_id, "code_sha": code_sha, "rules_sha": ident_rules_sha,
        "rules_input_sha": rules_io, "rules_output_sha": rules_io, "rules_added": 0,
        "mcq_output_sha": sha256_file(book / "all_mcq.jsonl"),
        "generated_mcq_sha256_by_id": {"m1": mcq_record_sha256(_mcq_record)},
        "prompt_sha256": canonical_prompt_sha256(),
        "config_sha256": canonical_config_sha256(),
        "script_sha256": sha256_file(ROOT / "scripts" / "distill_lib.py"),
        "provider": FROZEN_MODEL_CONFIG["provider"], "model": FROZEN_MODEL_CONFIG["model"],
        "thinking_mode": FROZEN_MODEL_CONFIG["thinking_mode"],
        "temperature": FROZEN_MODEL_CONFIG["temperature"],
        "calls_made": 1, "accepted": 1, "skipped": 0, "completed": True,
        "verification_level": "partial",  # no archived manifest -> partial only
    }


def test_validator_rejects_forged_rules_input_sha(tmp_path):
    """P0-4: when rules_added > 0, a rules_input_sha that does not match the
    persisted rules_input_snapshot is rejected (a bare 64-char string no longer
    suffices)."""
    from scripts.classic_artifacts import validate_provenance
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q","id":"m1"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["rules_added"] = 1
    api_gen["rules_input_sha"] = "f" * 64  # forged
    api_gen["rules_input_snapshot"] = [{"id": "r1", "rule": "x"}]  # real snapshot
    _minimal_prov_with_mcq(book, api_gen)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "rules_input_sha does not match rules_input_snapshot" in joined


def test_validator_rejects_missing_generated_mcq_ids(tmp_path):
    """P0-4: generated_mcq_ids referencing MCQs not present in all_mcq.jsonl is
    rejected -- proves which content this chain produced, not just the file."""
    from scripts.classic_artifacts import validate_provenance
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q","id":"m1"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    # m1 exists in the file but m999 does not -> reject.
    api_gen["generated_mcq_sha256_by_id"]["m999"] = "f" * 64
    api_gen["accepted"] = 2
    _minimal_prov_with_mcq(book, api_gen)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "not found in all_mcq.jsonl" in joined


def test_validator_rejects_reused_old_mcq_id(tmp_path):
    """P0-4: an MCQ whose record content does not match the canonical hash under
    a claimed generated id is rejected -- reusing an old id with different
    content cannot be passed off as this run's output."""
    from scripts.classic_artifacts import validate_provenance, mcq_record_sha256
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q","id":"m1"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    # Claim m1 was generated this run, but store the hash of DIFFERENT content.
    api_gen["generated_mcq_sha256_by_id"] = {
        "m1": mcq_record_sha256({"question": "DIFFERENT", "id": "m1"})}
    _minimal_prov_with_mcq(book, api_gen)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "content does not match" in joined


def test_validator_requires_full_when_manifest_archived(tmp_path):
    """Medium: api_generation that archives a run_manifest but does not mark
    verification_level='full' is rejected."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q","id":"m1"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["verification_level"] = "partial"  # but we'll archive a manifest below
    rm_manifest = {"immutable": {"targets": ["testbook"]}, "mutable": {}}
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "verification_level must be 'full'" in joined


def test_validator_rejects_missing_verification_level_no_manifest(tmp_path):
    """Medium: with no archived run_manifest, verification_level must be exactly
    'partial'. A MISSING verification_level (previously bypassed by the
    `is not None` guard) is rejected."""
    from scripts.classic_artifacts import validate_provenance
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"question":"q","id":"m1"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    del api_gen["verification_level"]  # missing entirely -> must be rejected
    _minimal_prov_with_mcq(book, api_gen)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "verification_level must be 'partial'" in joined


# ---------------------------------------------------------------------------
# Round-5 Medium: per-book call delta, not cross-book cumulative
# ---------------------------------------------------------------------------


def test_fill_records_per_book_call_delta(tmp_path, monkeypatch):
    """Medium: api_generation.calls_made is THIS book's call delta, not the
    cross-book cumulative ledger total."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import scripts.fill_missing_chapters as fmc
    import distill_lib as dl
    book = tmp_path / "zipingzhenquan"
    book.mkdir()
    (book / "all_rules.json").write_text("[]", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text("", encoding="utf-8")
    (book / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (book / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (book / "progress.json").write_text(
        json.dumps({"done": [], "total_rules": 0, "total_mcqs": 0}), encoding="utf-8")
    (book / "raw_full.txt").write_text("第一章 甲木\n甲木参天", encoding="utf-8")
    (book / "chapter_list.txt").write_text("1. 第一章 甲木", encoding="utf-8")
    mock_rules = [{"id": "zpzq_000_000", "source_chapter": "第一章 甲木", "subject": "甲木",
                   "rule": "甲木参天", "original_text": "甲木", "category": "天干"}]
    monkeypatch.setattr(dl, "distill_chapter", lambda *a, **k: mock_rules)

    def mock_call(prompt, timeout=120):
        return json.dumps({
            "question": "甲木为何参天？",
            "options": {"A": "甲木参天", "B": "甲木忌水", "C": "甲木喜金", "D": "甲木忌金"},
            "answer": "A", "explanation": "甲木参天", "difficulty": "基础", "category": "天干",
        })
    monkeypatch.setattr(dl, "_call", mock_call)
    monkeypatch.setattr(fmc, "BASE", tmp_path)
    manifest_path = tmp_path / ".fill_run_manifest.json"
    b = fmc._compute_run_bindings(["zipingzhenquan"], manifest_path)[:3]
    ledger_path = tmp_path / ".fill_ledger.json"
    # Pre-seed the shared ledger with 7 calls from a PRIOR book.
    seed = dl.BudgetLedger.load_or_create(
        ledger_path, 100, run_id=b[0], code_sha=b[1], rules_sha=b[2])
    for _ in range(7):
        seed.record_call()
    fmc.fill_book("zipingzhenquan", global_budget=100, ledger_path=ledger_path,
                  run_id=b[0], code_sha=b[1], rules_sha=b[2],
                  manifest_path=manifest_path)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    api = prov["api_generation"]
    # The delta is THIS book's calls (< 7); a cumulative value would be > 7.
    assert 1 <= api["calls_made"] < 7


# ---------------------------------------------------------------------------
# Round-6 P0-1: missing files must be rejected on resume / at receipt write
# ---------------------------------------------------------------------------


def test_resume_rejects_missing_pending_input(tmp_path):
    """P0-1: deleting a pending book's frozen mutable input must be rejected on
    resume (a missing file is not 'unchanged')."""
    import hashlib
    from scripts.distill_lib import freeze_run_manifest, LedgerCorruptionError
    mp = tmp_path / ".manifest.json"
    code = [ROOT / "scripts" / "distill_lib.py"]
    book = tmp_path / "bookA"
    book.mkdir()
    (book / "progress.json").write_text('{"done":[]}', encoding="utf-8")
    frozen_sha = hashlib.sha256(b'{"done":[]}').hexdigest()
    manifest = {
        "immutable": {"targets": ["bookA"]},
        "mutable": {"bookA": {"progress.json_sha256": frozen_sha,
                              "progress.json_bytes": 11}},
    }
    freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)
    # Delete the pending book's mutable input -- resume must reject it.
    (book / "progress.json").unlink()
    with pytest.raises(LedgerCorruptionError, match="mutable input missing"):
        freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)


def test_resume_rejects_missing_completed_output(tmp_path):
    """P0-1: deleting a completed book's receipt-bound output must be rejected."""
    from scripts.distill_lib import (
        freeze_run_manifest, append_book_receipt, LedgerCorruptionError)
    mp = tmp_path / ".manifest.json"
    code = [ROOT / "scripts" / "distill_lib.py"]
    book = tmp_path / "bookA"
    book.mkdir()
    (book / "all_mcq.jsonl").write_text('{"id":"m1"}\n', encoding="utf-8")
    (book / "remediation_meta.json").write_text("{}", encoding="utf-8")
    (book / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    manifest = {
        "immutable": {"targets": ["bookA"]},
        "mutable": {"bookA": {}},
    }
    freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)
    append_book_receipt(mp, "bookA", "completed", book_dir=book,
                        output_names=("all_mcq.jsonl", "quarantine_mcq.jsonl",
                                      "remediation_meta.json"))
    # Delete one receipt-bound output -- resume must reject it.
    (book / "all_mcq.jsonl").unlink()
    with pytest.raises(LedgerCorruptionError, match="output missing"):
        freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)


def test_append_receipt_requires_all_outputs_exist(tmp_path):
    """P0-1: append_book_receipt must refuse to write a completed/prepared
    receipt when any output_names file is missing (no silent skip)."""
    from scripts.distill_lib import (
        freeze_run_manifest, append_book_receipt, LedgerCorruptionError)
    mp = tmp_path / ".manifest.json"
    code = [ROOT / "scripts" / "distill_lib.py"]
    book = tmp_path / "bookA"
    book.mkdir()
    (book / "all_mcq.jsonl").write_text('{"id":"m1"}\n', encoding="utf-8")
    # remediation_meta.json is MISSING.
    manifest = {"immutable": {"targets": ["bookA"]}, "mutable": {"bookA": {}}}
    freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)
    with pytest.raises(LedgerCorruptionError, match="output missing"):
        append_book_receipt(mp, "bookA", "completed", book_dir=book,
                            output_names=("all_mcq.jsonl", "remediation_meta.json"))


# ---------------------------------------------------------------------------
# Round-6 P0-2: prepared/completed recoverable transaction
# ---------------------------------------------------------------------------


def _freeze_with_prepared(mp, book, old_bytes, new_bytes):
    """Freeze a manifest for bookA whose mutable out.json is old_bytes, then
    switch the file to new_bytes and append a PREPARED receipt bound to it."""
    import hashlib
    from scripts.distill_lib import freeze_run_manifest, append_book_receipt
    code = [ROOT / "scripts" / "distill_lib.py"]
    (book / "out.json").write_bytes(old_bytes)
    frozen_sha = hashlib.sha256(old_bytes).hexdigest()
    manifest = {
        "immutable": {"targets": ["bookA"]},
        "mutable": {"bookA": {"out.json_sha256": frozen_sha,
                              "out.json_bytes": len(old_bytes)}},
    }
    freeze_run_manifest(mp, manifest, code, mutable_root=book.parent)
    (book / "out.json").write_bytes(new_bytes)
    append_book_receipt(mp, "bookA", "prepared", book_dir=book,
                        output_names=("out.json",))


def _resume_prepared(mp, root):
    """Resume a prepared manifest with the correct immutable intent + code."""
    from scripts.distill_lib import freeze_run_manifest
    resume_manifest = {"immutable": {"targets": ["bookA"]}, "mutable": {}}
    code = [ROOT / "scripts" / "distill_lib.py"]
    return freeze_run_manifest(mp, resume_manifest, code, mutable_root=root)


def test_prepared_publish_done_resolves_to_completed(tmp_path):
    """P0-2: crash after publish but before the completed receipt -- current
    output equals the prepared expected SHA -> resume completes it."""
    import json
    mp = tmp_path / ".manifest.json"
    book = tmp_path / "bookA"
    book.mkdir()
    old = b'{"old":true}'
    new = b'{"new":true}'
    _freeze_with_prepared(mp, book, old, new)
    # current == new (prepared expected) -> completed
    rid, _, _, book_state = _resume_prepared(mp, tmp_path)
    assert book_state.get("bookA") == "completed"
    data = json.loads(mp.read_text(encoding="utf-8"))
    statuses = [r["status"] for r in data["book_receipts"]]
    assert "prepared" in statuses and "completed" in statuses


def test_prepared_publish_not_done_resolves_to_pending(tmp_path):
    """P0-2: crash before publish -- current output still equals old frozen
    mutable -> resume re-executes (pending), not blocked."""
    mp = tmp_path / ".manifest.json"
    book = tmp_path / "bookA"
    book.mkdir()
    old = b'{"old":true}'
    new = b'{"new":true}'
    _freeze_with_prepared(mp, book, old, new)
    # Revert output to old (publish never happened).
    (book / "out.json").write_bytes(old)
    rid, _, _, book_state = _resume_prepared(mp, tmp_path)
    assert book_state.get("bookA") != "completed"


def test_prepared_neither_old_nor_new_is_blocked(tmp_path):
    """P0-2: prepared receipt whose current output matches neither old nor
    expected is BLOCKED (cannot recover safely)."""
    from scripts.distill_lib import LedgerCorruptionError
    mp = tmp_path / ".manifest.json"
    book = tmp_path / "bookA"
    book.mkdir()
    _freeze_with_prepared(mp, book, b'{"old":true}', b'{"new":true}')
    (book / "out.json").write_bytes(b'{"corrupted":true}')
    with pytest.raises(LedgerCorruptionError, match="BLOCKED"):
        _resume_prepared(mp, tmp_path)


# ---------------------------------------------------------------------------
# Round-7 P0-1: a newer prepared receipt must not be blocked by an older one
# ---------------------------------------------------------------------------


def test_double_prepared_latest_resolves_not_blocked(tmp_path):
    """P0-1: after a prepared-before-publish retry writes a SECOND prepared, the
    old expected SHA must NOT be evaluated first and falsely BLOCK the valid
    newer publication -- only the latest prepared per target participates."""
    import hashlib
    from scripts.distill_lib import (
        freeze_run_manifest, append_book_receipt)
    mp = tmp_path / ".manifest.json"
    book = tmp_path / "bookA"
    book.mkdir()
    code = [ROOT / "scripts" / "distill_lib.py"]
    old = b'{"old":true}'
    new1 = b'{"new":1}'
    new2 = b'{"new":2}'
    (book / "out.json").write_bytes(old)
    frozen = hashlib.sha256(old).hexdigest()
    manifest = {
        "immutable": {"targets": ["bookA"]},
        "mutable": {"bookA": {"out.json_sha256": frozen,
                              "out.json_bytes": len(old)}},
    }
    freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)
    # prepared P1 (expected new1), then prepared P2 (expected new2).
    (book / "out.json").write_bytes(new1)
    append_book_receipt(mp, "bookA", "prepared", book_dir=book, output_names=("out.json",))
    (book / "out.json").write_bytes(new2)
    append_book_receipt(mp, "bookA", "prepared", book_dir=book, output_names=("out.json",))
    # Resume with current == new2 (the latest prepared publish). It must resolve
    # to completed, NOT be blocked by the older P1 expected SHA.
    resume_manifest = {"immutable": {"targets": ["bookA"]}, "mutable": {}}
    rid, _, _, book_state = freeze_run_manifest(
        mp, resume_manifest, code, mutable_root=tmp_path)
    assert book_state.get("bookA") == "completed"


# ---------------------------------------------------------------------------
# Round-7 P0-2: complete_prepared_receipt enforces the prepared SHA contract
# ---------------------------------------------------------------------------


def test_complete_prepared_succeeds_and_copies_prepared_shas(tmp_path):
    """P0-2: completing with current==prepared writes a completed receipt whose
    output_shas are EXACTLY the prepared SHAs (not re-hashed), referencing the
    prepared receipt."""
    import hashlib
    from scripts.distill_lib import (
        freeze_run_manifest, append_book_receipt, complete_prepared_receipt)
    mp = tmp_path / ".manifest.json"
    book = tmp_path / "bookA"
    book.mkdir()
    code = [ROOT / "scripts" / "distill_lib.py"]
    old = b'{"old":true}'
    new = b'{"new":true}'
    (book / "out.json").write_bytes(old)
    frozen = hashlib.sha256(old).hexdigest()
    manifest = {
        "immutable": {"targets": ["bookA"]},
        "mutable": {"bookA": {"out.json_sha256": frozen}},
    }
    freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)
    (book / "out.json").write_bytes(new)
    append_book_receipt(mp, "bookA", "prepared", book_dir=book, output_names=("out.json",))
    data_before = json.loads(mp.read_text(encoding="utf-8"))
    prep = data_before["book_receipts"][-1]
    prep_expected = prep["output_shas"]
    complete_prepared_receipt(mp, "bookA", book)
    data = json.loads(mp.read_text(encoding="utf-8"))
    comp = data["book_receipts"][-1]
    assert comp["status"] == "completed"
    assert comp["output_shas"] == prep_expected  # copied, not re-defined
    assert comp["prepared_sha"] == prep["sha"]


def test_complete_prepared_blocks_on_mutation(tmp_path):
    """P0-2: if a file is mutated after the prepared receipt (e.g. after publish
    validation), completion is BLOCKED -- the mutated content is not blessed."""
    import hashlib
    from scripts.distill_lib import (
        freeze_run_manifest, append_book_receipt, complete_prepared_receipt,
        LedgerCorruptionError)
    mp = tmp_path / ".manifest.json"
    book = tmp_path / "bookA"
    book.mkdir()
    code = [ROOT / "scripts" / "distill_lib.py"]
    (book / "out.json").write_bytes(b'{"old":true}')
    frozen = hashlib.sha256(b'{"old":true}').hexdigest()
    manifest = {
        "immutable": {"targets": ["bookA"]},
        "mutable": {"bookA": {"out.json_sha256": frozen}},
    }
    freeze_run_manifest(mp, manifest, code, mutable_root=tmp_path)
    (book / "out.json").write_bytes(b'{"new":true}')
    append_book_receipt(mp, "bookA", "prepared", book_dir=book, output_names=("out.json",))
    # Mutate after prepared.
    (book / "out.json").write_bytes(b'{"tampered":true}')
    with pytest.raises(LedgerCorruptionError, match="does not match prepared"):
        complete_prepared_receipt(mp, "bookA", book)


# ---------------------------------------------------------------------------
# Round-7 P0-3: duplicate/empty ids + old-identical-id reuse rejected
# ---------------------------------------------------------------------------


def test_validator_rejects_duplicate_mcq_ids(tmp_path):
    """P0-3: duplicate ids in the final all_mcq.jsonl are rejected (setdefault
    must not silently keep only the first)."""
    from scripts.classic_artifacts import validate_provenance
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text(
        '{"id":"m1","question":"a"}\n{"id":"m1","question":"b"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    _minimal_prov_with_mcq(book, api_gen)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "duplicate ids" in joined


def test_validator_rejects_empty_mcq_id(tmp_path):
    """P0-3: an empty/missing id in the final all_mcq.jsonl is rejected."""
    from scripts.classic_artifacts import validate_provenance
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"","question":"a"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    _minimal_prov_with_mcq(book, api_gen)
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "empty/missing id" in joined


def test_validator_rejects_old_identical_mcq_reuse(tmp_path):
    """P0-3/P0-8: for a run that preserves pre-existing MCQs, claiming a
    pre-existing id (even with IDENTICAL content) as generated this run is
    rejected because generated ids must be disjoint from the FROZEN pre-run id
    set in the archived run manifest."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / "zipingzhenquan"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    # m1 exists before the run with IDENTICAL content; claiming it as generated
    # must be rejected via the disjointness check against the FROZEN pre-run set.
    api_gen["preserves_existing_mcqs"] = True
    api_gen["pre_run_mcq_ids"] = ["m1"]
    api_gen["operation"] = "fill"
    api_gen["verification_level"] = "full"  # we archive a manifest below
    rm_manifest = {
        "immutable": {
            "targets": ["zipingzhenquan"],
            "input_files": {"zipingzhenquan": {
                "pre_run_mcq_ids": ["m1"], "operation": "fill",
                "preserves_existing_mcqs": True,
            }},
        },
        "mutable": {},
    }
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "overlaps frozen pre-run mcq ids" in joined


def test_validator_rejects_forged_blank_pre_run_ids(tmp_path):
    """P0: blanking api_generation.pre_run_mcq_ids in provenance (while the
    archived run manifest still freezes the true pre-run set) must NOT bypass
    the overlap check. An identical pre-existing MCQ cannot be passed off as
    newly generated just by deleting the pre-run list from provenance."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / "zipingzhenquan"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["preserves_existing_mcqs"] = False  # FORGED: flipped mode flag
    api_gen["pre_run_mcq_ids"] = []  # FORGED: blanked to hide that m1 pre-existed
    api_gen["operation"] = "fill"
    api_gen["verification_level"] = "full"  # we archive a manifest below
    rm_manifest = {
        "immutable": {
            "targets": ["zipingzhenquan"],
            "input_files": {"zipingzhenquan": {
                "pre_run_mcq_ids": ["m1"], "operation": "fill",
                "preserves_existing_mcqs": True,
            }},
        },
        "mutable": {},
    }
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    # Flipped mode flag != frozen operation mode -> forgery detected.
    assert "preserves_existing_mcqs does not equal" in joined
    # Blanked provenance list != frozen archived set -> forgery detected.
    assert "does not equal" in joined
    # Even ignoring the blanked list, m1 still overlaps the FROZEN set.
    assert "overlaps frozen pre-run mcq ids" in joined


@pytest.mark.parametrize("frozen_op, frozen_preserves, api_op, api_preserves, expect", [
    # Illegal but self-consistent pair: provenance matches the bad frozen values.
    ("fill", False, "fill", False, "does not match the legal mode"),
    ("regen", True, "regen", True, "does not match the legal mode"),
    # Missing frozen operation.
    (None, False, None, False, "must be one of"),
    # Missing frozen preserves_existing_mcqs.
    ("fill", None, "fill", None, "does not match the legal mode"),
])
def test_validator_rejects_illegal_frozen_mode_pair(
        tmp_path, frozen_op, frozen_preserves, api_op, api_preserves, expect):
    """P0: a frozen (operation, preserves_existing_mcqs) pair in the archived
    run manifest must itself be a legal closed mode (fill->True, regen->False).
    Illegal or missing frozen fields are rejected even when provenance matches
    them exactly; disjointness is driven by the frozen operation (fill), not
    by the boolean flag."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["verification_level"] = "full"
    if api_op is not None:
        api_gen["operation"] = api_op
    if api_preserves is not None:
        api_gen["preserves_existing_mcqs"] = api_preserves
    imm_entry = {"pre_run_mcq_ids": ["m1"]}
    if frozen_op is not None:
        imm_entry["operation"] = frozen_op
    if frozen_preserves is not None:
        imm_entry["preserves_existing_mcqs"] = frozen_preserves
    rm_manifest = {"immutable": {"targets": ["testbook"],
                                 "input_files": {"testbook": imm_entry}},
                   "mutable": {}}
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    assert expect in "; ".join(issues)


@pytest.mark.parametrize("targets, input_files_map, expect", [
    # Current book is not listed in targets (but is present in input_files).
    (["otherbook"],
     {"testbook": {"pre_run_mcq_ids": ["m1"], "operation": "fill",
                   "preserves_existing_mcqs": True}},
     "not an authorized target"),
    # targets contains duplicates.
    (["testbook", "testbook"],
     {"testbook": {"pre_run_mcq_ids": ["m1"], "operation": "fill",
                   "preserves_existing_mcqs": True}},
     "contains duplicates"),
    # targets and input_files key sets mismatch (extra un-authorized key).
    (["testbook"],
     {"testbook": {"pre_run_mcq_ids": ["m1"], "operation": "fill",
                   "preserves_existing_mcqs": True},
      "extra": {"operation": "fill", "preserves_existing_mcqs": True}},
     "must exactly match"),
])
def test_validator_rejects_unbound_frozen_target(
        tmp_path, targets, input_files_map, expect):
    """P0: before trusting any book-level frozen entry, the validator must prove
    the current book is an authorized target of the frozen run -- targets must
    be a unique list containing p.name, and input_files keys must exactly equal
    targets. A self-consistent archive that omits the book from targets (or
    lists an un-authorized set) must fail."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["preserves_existing_mcqs"] = True
    api_gen["pre_run_mcq_ids"] = ["m1"]
    api_gen["operation"] = "fill"
    api_gen["verification_level"] = "full"
    rm_manifest = {"immutable": {"targets": targets, "input_files": input_files_map},
                   "mutable": {}}
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    assert expect in "; ".join(issues)


@pytest.mark.parametrize("bad_targets", [
    [["testbook"]],                 # nested array element
    [{"book": "testbook"}],         # object element
    ["testbook", ""],               # empty string element
    ["testbook", 1],                # non-string element
])
def test_validator_rejects_malformed_frozen_targets(tmp_path, bad_targets):
    """P0: malformed target entries (nested arrays/objects, empty strings,
    non-string elements) must fail-closed with ok=False -- NOT crash with a
    TypeError from set(targets)."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["preserves_existing_mcqs"] = True
    api_gen["pre_run_mcq_ids"] = ["m1"]
    api_gen["operation"] = "fill"
    api_gen["verification_level"] = "full"
    rm_manifest = {
        "immutable": {"targets": bad_targets,
                      "input_files": {"testbook": {
                          "pre_run_mcq_ids": ["m1"], "operation": "fill",
                          "preserves_existing_mcqs": True}}},
        "mutable": {},
    }
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    assert "non-empty strings" in "; ".join(issues)


@pytest.mark.parametrize("ghost_entry, expect", [
    # Second target entry is an empty object ({} is a dict, so the missing
    # pre_run_mcq_ids list is what must fail).
    ({}, "must be a list"),
    # Second target entry missing pre_run_mcq_ids.
    ({"operation": "fill", "preserves_existing_mcqs": True}, "must be a list"),
    # Second target uses an illegal mode pair.
    ({"pre_run_mcq_ids": [], "operation": "fill",
      "preserves_existing_mcqs": False}, "does not match the legal mode"),
])
def test_validator_rejects_forged_other_target_entry(tmp_path, ghost_entry, expect):
    """P0: every frozen target participates in the run_id computation, so a
    forged empty/malformed entry on a NON-current target must fail-closed --
    not just the current book's entry."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["preserves_existing_mcqs"] = True
    api_gen["pre_run_mcq_ids"] = ["m1"]
    api_gen["operation"] = "fill"
    api_gen["verification_level"] = "full"
    rm_manifest = {
        "immutable": {"targets": ["testbook", "ghostbook"],
                      "input_files": {
                          "testbook": {"pre_run_mcq_ids": ["m1"], "operation": "fill",
                                       "preserves_existing_mcqs": True},
                          "ghostbook": ghost_entry}},
        "mutable": {},
    }
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    assert expect in "; ".join(issues)


def test_validator_rejects_mixed_fill_regen_manifest(tmp_path):
    """P0: a single canonical run comes from exactly ONE producer, so a manifest
    whose targets mix fill (preserves=True) and regen (preserves=False) is forged
    and must be rejected even when each individual entry is legal."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / "testbook"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["preserves_existing_mcqs"] = True
    api_gen["pre_run_mcq_ids"] = ["m1"]
    api_gen["operation"] = "fill"
    api_gen["verification_level"] = "full"
    rm_manifest = {
        "immutable": {"targets": ["testbook", "ghostbook"],
                      "input_files": {
                          "testbook": {"pre_run_mcq_ids": ["m1"], "operation": "fill",
                                       "preserves_existing_mcqs": True},
                          "ghostbook": {"pre_run_mcq_ids": [], "operation": "regen",
                                        "preserves_existing_mcqs": False}}},
        "mutable": {},
    }
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    assert "mix incompatible operations" in "; ".join(issues)


@pytest.mark.parametrize("field, forged", [
    ("frozen_prompt_sha256", "0" * 64),
    ("frozen_config_sha256", "f" * 64),
])
def test_validator_rejects_forged_frozen_prompt_config(tmp_path, field, forged):
    """P0: the manifest's own frozen prompt/config SHAs participate in the run
    identity and must equal the canonical values AND the api_generation fields.
    Forging them and re-hashing the manifest must fail."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / "zipingzhenquan"
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["preserves_existing_mcqs"] = True
    api_gen["pre_run_mcq_ids"] = ["m1"]
    api_gen["operation"] = "fill"
    api_gen["verification_level"] = "full"
    # Manifest freezes the canonical prompt/config EXCEPT the forged field.
    rm_manifest = {
        "immutable": {
            "targets": ["zipingzhenquan"],
            "frozen_config_sha256": "f" * 64 if field == "frozen_prompt_sha256"
            else __import__("scripts.distill_lib", fromlist=["canonical_config_sha256"])
            .canonical_config_sha256(),
            "frozen_prompt_sha256": "f" * 64 if field == "frozen_config_sha256"
            else __import__("scripts.distill_lib", fromlist=["canonical_prompt_sha256"])
            .canonical_prompt_sha256(),
            "input_files": {"zipingzhenquan": {
                "pre_run_mcq_ids": ["m1"], "operation": "fill",
                "preserves_existing_mcqs": True,
            }},
        },
        "mutable": {},
    }
    # Forge the target field regardless of which side the canonical was put on.
    rm_manifest["immutable"][field] = forged
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert f"{field} does not" in joined


@pytest.mark.parametrize("target, operation", [
    # Field-complete but unknown target (not in any producer's allowed set).
    ("ghostbook", "fill"),
    # A fill manifest adding a target that only regen supports.
    ("sanmingtonghui", "fill"),
    # A regen manifest adding an unknown target.
    ("ghostbook", "regen"),
])
def test_validator_rejects_unknown_or_operation_mismatched_target(
        tmp_path, target, operation):
    """P0: every frozen target must belong to the ALLOWED target set for the
    unified operation (shared VALID_TARGETS_BY_OPERATION). A field-complete but
    unknown target, or a target that belongs to another operation, must fail."""
    import hashlib
    from scripts.classic_artifacts import validate_provenance
    from scripts.distill_lib import compute_code_sha, ledger_code_files
    book = tmp_path / ("zipingzhenquan" if operation == "fill" else "sanmingtonghui")
    book.mkdir()
    for n in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
              "quarantine_mcq.jsonl", "remediation_meta.json"):
        (book / n).write_text("[]" if n.endswith(".json") else "", encoding="utf-8")
    (book / "all_mcq.jsonl").write_text('{"id":"m1","question":"q"}\n', encoding="utf-8")
    (book / "all_rules.json").write_text('[{"id":"r1"}]', encoding="utf-8")
    api_gen = _valid_no_manifest_api_gen(book)
    api_gen["preserves_existing_mcqs"] = (operation == "fill")
    api_gen["pre_run_mcq_ids"] = ["m1"]
    api_gen["operation"] = operation
    api_gen["verification_level"] = "full"
    preserves = (operation == "fill")
    current = book.name
    rm_manifest = {
        "immutable": {
            "targets": [current, target],
            "input_files": {
                current: {"pre_run_mcq_ids": ["m1"], "operation": operation,
                          "preserves_existing_mcqs": preserves},
                target: {"pre_run_mcq_ids": [], "operation": operation,
                         "preserves_existing_mcqs": preserves},
            },
        },
        "mutable": {},
    }
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    code_sha = compute_code_sha(ledger_code_files(ROOT / "scripts", ROOT))
    run_manifest = {"manifest": rm_manifest, "manifest_sha256": rm_sha,
                    "run_id": hashlib.sha256((code_sha + ":" + rm_sha).encode()).hexdigest()[:16],
                    "code_sha": code_sha, "rules_sha": rm_sha}
    api_gen["run_id"] = run_manifest["run_id"]
    api_gen["code_sha"] = code_sha
    api_gen["rules_sha"] = rm_sha
    _minimal_prov_with_mcq(book, api_gen)
    prov = json.loads((book / "provenance.json").read_text(encoding="utf-8"))
    prov["run_manifest"] = run_manifest
    (book / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_provenance(book, ROOT / "scripts", git_root=None)
    assert ok is False
    joined = "; ".join(issues)
    assert "not an allowed target" in joined

