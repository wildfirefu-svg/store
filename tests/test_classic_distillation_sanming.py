"""Stage 7/8 tests: batch entry (run_sanming_batch) + progress + cleanup fail-closed +
GenerationIndex + batch anchors. Ported from the approved proof module, adapted to
the real module layout (scripts.fill_missing_chapters / scripts.distill_lib /
scripts.classic_artifacts)."""
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess as _subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fill_missing_chapters import (
    _retry_pending_cleanup, _backup_fingerprint, _build_rule_id_map, _update_progress,
    run_sanming_batch, _segment_manifest_sha, _model_prompt_config_sha, _code_sha_now,
)
from scripts.distill_lib import _canonical_key, backfill_canonical_keys, canonical_dedup, EXPERIMENT_ID
from scripts.classic_artifacts import (
    GenerationIndex, finalize_batch, generation_index_sha256, verify_generation_index_entries,
    validate_generation_index_entry, FROZEN_ENTRY_FIELDS,
)
import scripts.remediate_classic_distillation as rc
import scripts.distill_lib as dl

# ==========================================================================
# snapshot 发布/物化 harness（阶段 4 复用）
# ==========================================================================
def _records_for(entries, status="archived", prov="full", text="T", body=b"B"):
    return [{"chapter_index": e.index, "title": e.title, "url": e.url,
             "response_body_sha256": hashlib.sha256(body).hexdigest(),
             "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
             "extractor_sha256": "x" * 64, "normalized_page_title": e.title,
             "response_body_status": status, "provenance_level": prov, "encoding": "utf-8",
             "extracted_text": text, "response_body": body, "ok": True} for e in entries]

def _materialized_snapshot(tmp_path, chapters=(81, 82)):
    from scripts.fetch_sanming_chapters import (ChapterEntry, build_and_publish_snapshot,
                                                read_active_snapshot, restore_responses, materialization_status)
    body = b"B"
    def text(c): return f"第{c}章正文。\n\n第二段。\n" * 40
    def factory(entries):
        return [{"chapter_index": e.index, "title": f"章{e.index}", "url": f"u{e.index}",
                 "response_body_sha256": hashlib.sha256(body).hexdigest(),
                 "extracted_text_sha256": hashlib.sha256(text(e.index).encode("utf-8")).hexdigest(),
                 "extractor_sha256": "x" * 64, "normalized_page_title": f"章{e.index}",
                 "response_body_status": "archived", "provenance_level": "full", "encoding": "utf-8",
                 "extracted_text": text(e.index), "response_body": body, "ok": True} for e in entries]
    formal = tmp_path / "formal"
    build_and_publish_snapshot([ChapterEntry(c, f"章{c}", f"u{c}") for c in chapters], formal, records_factory=factory, archive_root=tmp_path / "store")
    act = read_active_snapshot(formal); sha = act["snapshot_sha256"]
    restore_responses(formal, sha, archive_root=tmp_path / "store")
    assert materialization_status(formal, sha) == "materialized"
    return formal / "source_snapshots" / sha / "extracted", act, formal

def _setup_batch(tmp_path):
    snap, act, formal = _materialized_snapshot(tmp_path)
    out = tmp_path / "book"; out.mkdir()
    repo = tmp_path / "repo"; repo.mkdir()
    _subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    _subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    _subprocess.run(["git", "-C", str(repo), "add", "."], check=True); _subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    head = _subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    return snap, out, repo, head, formal, act

def _mk_batch_manifest(tmp_path, batch_id, snap_dir, head, parent, pre_run_sha, chs=(81,)):
    src_sha = {str(c): hashlib.sha256((snap_dir / f"raw_{c:03d}.txt").read_bytes()).hexdigest() for c in chs}
    m = {"schema_version": "1.0", "batch_id": batch_id, "selected_chapter_ids": list(chs), "source_sha_map": src_sha,
         "segment_manifest_sha": "0" * 64, "pre_run_output_sha": pre_run_sha, "model_prompt_config_sha": "0" * 64,
         "batch_hard_cap": 100, "parent_commit": parent, "parent_head_sha": head, "code_sha": "0" * 64, "rules_sha": "0" * 64,
         "source_snapshot_sha256": "0" * 64, "source_manifest_sha256": "0" * 64, "source_archive_pointer_sha256": "0" * 64,
         "experiment_id": EXPERIMENT_ID}
    p = tmp_path / f"{batch_id}.json"; p.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8"); return p, m

def _fill_real_shas(mp, m, snap, formal, act):
    chs = m["selected_chapter_ids"]
    from scripts.distill_lib import PromptLimits, segment_chapter
    segs = {c: segment_chapter((snap / f"raw_{c:03d}.txt").read_text(encoding="utf-8"), book="sanmingtonghui", chapter=str(c), limits=PromptLimits()) for c in chs}
    m["segment_manifest_sha"] = _segment_manifest_sha(segs)
    m["model_prompt_config_sha"] = _model_prompt_config_sha()
    m["code_sha"] = _code_sha_now(ROOT / "scripts", ROOT)
    m["source_snapshot_sha256"] = act["snapshot_sha256"]
    m["source_manifest_sha256"] = act["source_manifest_sha256"]
    from scripts.fetch_sanming_chapters import _file_sha256
    snap_dir = formal / "source_snapshots" / act["snapshot_sha256"]
    m["source_archive_pointer_sha256"] = _file_sha256(snap_dir / "RESPONSE_ARCHIVE_POINTER.json")
    mp.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

def _dispatch_fake(prompt, timeout=300):
    if "提取结构化命理规则" in prompt: return '[{"rule":"甲木日主喜水","condition":"甲木生于寅月","subject":"甲木","original_text":"甲木喜水"}]'
    if "生成一道四选一选择题" in prompt: return '{"question":"甲木喜什么？","options":{"A":"喜水滋润","B":"火","C":"土","D":"金"},"answer":"A","explanation":"甲木喜水"}'
    return "[]"

def _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, fake_call, generation_index_path=None, genesis_anchor="0" * 40):
    # fill_missing_chapters 用 `import distill_lib as dl`（非包导入）会创建独立模块对象，
    # 与 scripts.distill_lib 不是同一对象——两个都 patch 才能让 _call 补丁生效。
    import sys as _sys
    monkeypatch.setattr(dl, "_call", fake_call)
    _dm = _sys.modules.get("distill_lib")
    if _dm is not None:
        monkeypatch.setattr(_dm, "_call", fake_call)
    return run_sanming_batch(mp, snapshot_dir=snap, out_dir=out, formal_dir=formal, snapshot_sha=act["snapshot_sha256"],
                             proj_ledger_path=tmp_path / "proj.json", run_ledger_path=tmp_path / "run.json", run_id="R1",
                             project_total_cap=1000, scripts_dir=ROOT / "scripts", root=ROOT, git_root=repo,
                             genesis_anchor=genesis_anchor, generation_index_path=generation_index_path)

# ==========================================================================
# Stage 7: progress reconcile 逐记录映射 + 守恒
# ==========================================================================
def test_progress_reconcile_duplicate_old_id_per_record(tmp_path):
    staging = tmp_path / "staging"; staging.mkdir()
    base = {"subject": "甲木", "condition": "生于寅月", "rule": "甲木日主喜水", "original_text": "甲木喜水",
            "source_book": "sanmingtonghui", "source_chapter": "81", "category": "classic"}
    old_progress = {"done": [], "all_rules": [
        dict(base, id="smth_0001"),
        dict(base, condition="生于卯月", id="smth_0001"),
        dict(base, condition="生于辰月", id="smth_0002"),
    ], "all_mcqs": []}
    (staging / "progress.json").write_text(json.dumps(old_progress, ensure_ascii=False), encoding="utf-8")
    new_rules = [dict(base, id="smth_000_000"), dict(base, condition="生于卯月", id="smth_000_001")]
    (staging / "all_rules.json").write_text(json.dumps(new_rules, ensure_ascii=False), encoding="utf-8")
    (staging / "all_mcq.jsonl").write_text("", encoding="utf-8")
    _update_progress(staging, run_id="R1", batch_id="B1", genesis_anchor="a" * 40)
    act = [a for a in json.loads((staging / "remediation_meta.json").read_text(encoding="utf-8"))["actions"] if a["type"] == "progress_reconcile"][0]
    mapped, conflicts, unmappable = act["mapped"], act["conflicts"], act["unmappable"]
    assert len(mapped) + len(conflicts) + len(unmappable) == 3
    assert [r["old_id"] for r in mapped + conflicts + unmappable].count("smth_0001") == 2
    assert sorted(r["new_id"] for r in mapped) == ["smth_000_000", "smth_000_001"]
    assert len(unmappable) == 1 and unmappable[0]["reason"] == "no_new_rule" and unmappable[0]["old_id"] == "smth_0002"
    for rec in mapped + conflicts + unmappable:
        assert isinstance(rec.get("old_record_sha256"), str) and len(rec["old_record_sha256"]) == 64

def test_progress_reconcile_one_to_many_conflict(tmp_path):
    staging = tmp_path / "staging"; staging.mkdir()
    base = {"subject": "甲木", "condition": "生于寅月", "rule": "甲木日主喜水", "original_text": "甲木喜水",
            "source_book": "sanmingtonghui", "source_chapter": "81", "category": "classic"}
    old_progress = {"done": [], "all_rules": [dict(base, id="smth_0001")], "all_mcqs": []}
    (staging / "progress.json").write_text(json.dumps(old_progress, ensure_ascii=False), encoding="utf-8")
    new_rules = [dict(base, id="smth_000_000"), dict(base, id="smth_000_001")]
    (staging / "all_rules.json").write_text(json.dumps(new_rules, ensure_ascii=False), encoding="utf-8")
    (staging / "all_mcq.jsonl").write_text("", encoding="utf-8")
    _update_progress(staging, run_id="R1", batch_id="B1", genesis_anchor="a" * 40)
    act = [a for a in json.loads((staging / "remediation_meta.json").read_text(encoding="utf-8"))["actions"] if a["type"] == "progress_reconcile"][0]
    assert len(act["mapped"]) + len(act["conflicts"]) + len(act["unmappable"]) == 1
    assert len(act["conflicts"]) == 1 and act["conflicts"][0]["new_ids"] == ["smth_000_000", "smth_000_001"]

def test_progress_reconcile_real_front80_conservation(tmp_path):
    src = ROOT / "knowledge_base/classic_texts/sanmingtonghui"
    staging = tmp_path / "staging"; staging.mkdir()
    shutil.copy2(src / "progress.json", staging / "progress.json")
    shutil.copy2(src / "all_rules.json", staging / "all_rules.json")
    shutil.copy2(src / "all_mcq.jsonl", staging / "all_mcq.jsonl")
    old_rules = json.loads((staging / "progress.json").read_text(encoding="utf-8"))["all_rules"]
    _update_progress(staging, run_id="R1", batch_id="B1", genesis_anchor="a" * 40)
    act = [a for a in json.loads((staging / "remediation_meta.json").read_text(encoding="utf-8"))["actions"] if a["type"] == "progress_reconcile"][0]
    mapped, conflicts, unmappable = act["mapped"], act["conflicts"], act["unmappable"]
    assert len(old_rules) == 1727
    assert len(mapped) + len(conflicts) + len(unmappable) == len(old_rules)
    for rec in mapped + conflicts + unmappable:
        assert isinstance(rec.get("old_record_sha256"), str) and len(rec["old_record_sha256"]) == 64
    for rec in mapped: assert rec.get("new_id")
    for rec in conflicts: assert rec.get("new_ids")
    for rec in unmappable: assert rec.get("reason")
    for sha in ("mapped_sha256", "conflicts_sha256", "unmappable_sha256"):
        v = act[sha]
        assert v is None or (isinstance(v, str) and len(v) == 64)

# ==========================================================================
# Stage 7: backfill 守恒
# ==========================================================================
def test_backfill_front80_keeps_ids(tmp_path):
    src = ROOT / "knowledge_base/classic_texts/sanmingtonghui"
    book = tmp_path / "book"; book.mkdir()
    shutil.copy2(src / "all_rules.json", book / "all_rules.json")
    before = json.loads((book / "all_rules.json").read_text(encoding="utf-8"))
    backfill_canonical_keys(book)
    after = json.loads((book / "all_rules.json").read_text(encoding="utf-8"))
    assert len(after) == len(before)
    allowed_added = {"canonical_key", "source_book", "source_chapter", "category"}
    for b, a in zip(before, after):
        extra = set(a) - set(b)
        assert extra <= allowed_added, f"unexpected added fields: {extra}"
        assert {k: b[k] for k in b} == {k: a[k] for k in b}
        assert isinstance(a.get("canonical_key"), str) and len(a["canonical_key"]) == 64
    assert [b.get("id") for b in before] == [a.get("id") for a in after]

def test_canonical_dedup_fails_closed_on_missing_field():
    with pytest.raises(ValueError, match="canonical field"):
        canonical_dedup([{"rule": "r", "condition": "c", "subject": "s"}])

# ==========================================================================
# Stage 7: cleanup fail-closed（显式状态）
# ==========================================================================
def test_retry_pending_cleanup_rejects_path_escape(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    victim = tmp_path / "victim"; victim.mkdir(); (victim / "f").write_text("x", encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(victim)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=victim, frozen_fingerprint=_backup_fingerprint(victim))
    assert st == "blocked" and victim.exists() and cp.exists()

def test_retry_pending_cleanup_rejects_wrong_batch(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_1_1"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "OTHER", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=_backup_fingerprint(target))
    assert st == "blocked" and target.exists() and cp.exists()

def test_retry_pending_cleanup_deletes_matching_frozen(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_123_456"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    fp = _backup_fingerprint(target)
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=fp)
    assert st == "cleaned" and not target.exists() and not cp.exists()

def test_retry_pending_cleanup_noop_without_pending(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=None, frozen_fingerprint=None)
    assert st == "noop"

def test_retry_pending_cleanup_rejects_unparseable_pending(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_123_456"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text("{not valid json", encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=_backup_fingerprint(target))
    assert st == "blocked" and target.exists() and cp.exists()

def test_retry_pending_cleanup_rejects_frozen_fingerprint_mismatch(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_111_222"; target.mkdir(); (target / "all_rules.json").write_text('["B2-rules"]', encoding="utf-8")
    frozen_fp = _backup_fingerprint(out / ".publish_backup_111_222")
    (target / "all_rules.json").write_text('["B2-rules-CHANGED"]', encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=frozen_fp)
    assert st == "blocked" and target.exists() and cp.exists()

def test_retry_pending_cleanup_rmtree_failure_blocked(tmp_path, monkeypatch):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_123_456"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    fp = _backup_fingerprint(target)
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    def failing_rmtree(path, *a, **k): raise PermissionError("simulated rmtree failure")
    monkeypatch.setattr(shutil, "rmtree", failing_rmtree)
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=fp)
    monkeypatch.setattr(shutil, "rmtree", shutil.rmtree)
    assert st == "blocked" and target.exists() and cp.exists()

def test_retry_pending_cleanup_ignores_tampered_pending_path(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    own = out / ".publish_backup_111_222"; own.mkdir(); (own / "all_rules.json").write_text('["B1-rules"]', encoding="utf-8")
    other = out / ".publish_backup_333_444"; other.mkdir(); (other / "all_rules.json").write_text('["B2-rules"]', encoding="utf-8")
    own_fp = _backup_fingerprint(own)
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(other),
                              "backup_fingerprint": _backup_fingerprint(other)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=own, frozen_fingerprint=own_fp)
    assert st == "cleaned" and other.exists()
    assert not own.exists() and not cp.exists()

# ==========================================================================
# Stage 7: fake_flow 全生命周期（cleanup 失败 -> pending -> finalize 认证 -> cleanup 重试 / blocked）
# ==========================================================================
def test_fake_flow_end_to_end_published(tmp_path, monkeypatch):
    snap, out, repo, head, formal, act = _setup_batch(tmp_path)
    pre_run_sha = hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest()
    mp, m = _mk_batch_manifest(tmp_path, "B1", snap_dir=snap, head=head, parent=head, pre_run_sha=pre_run_sha)
    _fill_real_shas(mp, m, snap, formal, act)
    monkeypatch.setattr(dl, "_call", _dispatch_fake)
    real_rmtree = shutil.rmtree
    def failing_rmtree(path, *a, **k):
        if isinstance(path, (str, Path)) and re.fullmatch(r"\.publish_backup_\d+_\d+", Path(path).name):
            raise PermissionError("simulated cleanup failure")
        return real_rmtree(path, *a, **k)
    monkeypatch.setattr(shutil, "rmtree", failing_rmtree)
    res1 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, _dispatch_fake, genesis_anchor=head)
    monkeypatch.setattr(shutil, "rmtree", real_rmtree)
    assert res1["status"] == "published"
    cp_path = out / ".batch" / "B1" / "cleanup_pending.json"
    assert cp_path.exists()
    rec = json.loads((out / ".batch" / "B1" / "completed_receipt.json").read_text(encoding="utf-8"))
    backup_dir = Path(rec["backup_dir"])
    assert backup_dir.exists() and backup_dir.name.startswith(".publish_backup_")
    assert isinstance(rec["backup_fingerprint"], dict) and len(rec["backup_fingerprint"]["member_set_sha256"]) == 64
    assert _backup_fingerprint(backup_dir) == rec["backup_fingerprint"]
    # 未 finalize -> published_pending_finalize，不清理
    calls = {"n": 0}
    def fake(*a, **k): calls["n"] += 1; raise AssertionError("must not re-call")
    monkeypatch.setattr(dl, "_call", fake)
    res2 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, fake, genesis_anchor=head)
    assert res2["status"] == "published_pending_finalize" and calls["n"] == 0
    assert backup_dir.exists() and cp_path.exists()
    # finalize -> completed_idempotent + cleanup 重试成功
    receipt = out / ".batch" / "B1" / "completed_receipt.json"
    gi = tmp_path / "gi.json"
    finalize_batch(batch_id="B1", completed_receipt_path=receipt, index_path=gi, genesis_anchor=head)
    assert GenerationIndex(gi, genesis_anchor=head).verify() is True
    res3 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, fake, generation_index_path=gi, genesis_anchor=head)
    assert res3["status"] == "completed_idempotent" and calls["n"] == 0
    assert not backup_dir.exists() and not cp_path.exists()

def test_fake_flow_cleanup_blocked_after_finalize(tmp_path, monkeypatch):
    snap, out, repo, head, formal, act = _setup_batch(tmp_path)
    pre_run_sha = hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest()
    mp, m = _mk_batch_manifest(tmp_path, "B1", snap_dir=snap, head=head, parent=head, pre_run_sha=pre_run_sha)
    _fill_real_shas(mp, m, snap, formal, act)
    monkeypatch.setattr(dl, "_call", _dispatch_fake)
    real_rmtree = shutil.rmtree
    def failing_rmtree(path, *a, **k):
        if isinstance(path, (str, Path)) and re.fullmatch(r"\.publish_backup_\d+_\d+", Path(path).name):
            raise PermissionError("simulated cleanup failure")
        return real_rmtree(path, *a, **k)
    monkeypatch.setattr(shutil, "rmtree", failing_rmtree)
    res1 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, _dispatch_fake, genesis_anchor=head)
    monkeypatch.setattr(shutil, "rmtree", real_rmtree)
    assert res1["status"] == "published"
    cp_path = out / ".batch" / "B1" / "cleanup_pending.json"
    assert cp_path.exists()
    rec = json.loads((out / ".batch" / "B1" / "completed_receipt.json").read_text(encoding="utf-8"))
    backup_dir = Path(rec["backup_dir"])
    assert backup_dir.exists() and _backup_fingerprint(backup_dir) == rec["backup_fingerprint"]
    receipt = out / ".batch" / "B1" / "completed_receipt.json"
    gi = tmp_path / "gi.json"
    finalize_batch(batch_id="B1", completed_receipt_path=receipt, index_path=gi, genesis_anchor=head)
    (backup_dir / "tamper.txt").write_text("tampered", encoding="utf-8")
    assert _backup_fingerprint(backup_dir) != rec["backup_fingerprint"]
    calls = {"n": 0}
    def fake(*a, **k): calls["n"] += 1; raise AssertionError("must not re-call")
    monkeypatch.setattr(dl, "_call", fake)
    res2 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, fake, generation_index_path=gi, genesis_anchor=head)
    assert calls["n"] == 0
    assert res2["status"] == "completed_cleanup_blocked"
    assert backup_dir.exists() and cp_path.exists()

# ==========================================================================
# Stage 8: GenerationIndex 40/64 契约 + batch anchor + final anchor
# ==========================================================================
def _mk_entry(batch_id="B1", sha=None, prev=None, genesis="0" * 40):
    return {"batch_id": batch_id, "completed_receipt_sha256": sha or "a" * 64,
            "genesis_commit": genesis, "previous_index_sha256": prev}

def test_generation_index_entry_schema_required():
    for bad in ({"batch_id": "B1"}, None, "x", {"batch_id": "B1", "completed_receipt_sha256": "a" * 64}):
        with pytest.raises(ValueError):
            validate_generation_index_entry(bad)

def test_generation_index_real_40hex_genesis_passes(tmp_path):
    genesis = "a" * 40
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor=genesis)
    idx.append({"batch_id": "B1", "completed_receipt_sha256": "b" * 64})
    assert idx.verify() is True
    e0 = idx._load()[0]
    assert e0["genesis_commit"] == genesis and e0["previous_index_sha256"] is None

def test_generation_index_chain_verified(tmp_path):
    genesis = "b" * 40
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor=genesis)
    idx.append({"batch_id": "B1", "completed_receipt_sha256": "a" * 64})
    idx.append({"batch_id": "B2", "completed_receipt_sha256": "c" * 64})
    assert idx.verify() is True
    entries = idx._load()
    assert entries[1]["previous_index_sha256"] == generation_index_sha256(entries[:1])
    stripped = [dict(entries[0])]; stripped[0].pop("completed_receipt_sha256")
    assert verify_generation_index_entries(stripped, genesis, None) is False

def _tmp_git(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    _subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    _subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    _subprocess.run(["git", "-C", str(repo), "add", "."], check=True); _subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    return repo

def _git(repo, *args): return _subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()

def _build_chain(tmp_path):
    from scripts.classic_artifacts import batch_anchor_receipt
    repo = _tmp_git(tmp_path)
    genesis = _git(repo, "rev-parse", "HEAD")
    idx_path = repo / "gi.json"
    idx = GenerationIndex(idx_path, genesis_anchor=genesis)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": hashlib.sha256(b"receipt-1").hexdigest()})
    head = generation_index_sha256(idx._load())
    (repo / "out").mkdir()
    (repo / "out" / "completed_receipt.json").write_bytes(b"receipt-1")
    (repo / "out" / "source_manifest.json").write_text(json.dumps({"snapshot_sha256": "s"*64}), encoding="utf-8")
    rel = lambda p: str(Path(p).resolve().relative_to(Path(repo).resolve())).replace("\\", "/")
    anchor = batch_anchor_receipt(batch_id="b1", parent_commit=genesis, head_sha=head, index_rel=rel(idx_path),
                                  anchor_rel="out/batch_anchor.json", completed_receipt_rel="out/completed_receipt.json",
                                  completed_receipt_sha256=hashlib.sha256(b"receipt-1").hexdigest(),
                                  source_snapshot_sha256="s"*64, source_snapshot_rel="out/source_manifest.json")
    (repo / "out" / "batch_anchor.json").write_text(json.dumps(anchor, ensure_ascii=False), encoding="utf-8")
    _subprocess.run(["git", "-C", str(repo), "add", "."], check=True); _subprocess.run(["git", "-C", str(repo), "commit", "-qm", "batch Cn"], check=True)
    return repo, genesis, _git(repo, "rev-parse", "HEAD"), idx_path, anchor, head

def test_verify_batch_anchors_git_history_located(tmp_path):
    from scripts.classic_artifacts import verify_batch_anchors
    repo, genesis, cn, idx_path, anchor, head = _build_chain(tmp_path)
    assert verify_batch_anchors([anchor], git_root=repo, genesis_commit=genesis, final_commit=cn) is True
    bad = dict(anchor); bad["parent_commit"] = "0" * 40
    assert verify_batch_anchors([bad], git_root=repo, genesis_commit=genesis, final_commit=cn) is False
    assert verify_batch_anchors([], git_root=repo, genesis_commit=genesis, final_commit=cn) is False

def test_final_anchor_full_chain_verify(tmp_path):
    from scripts.classic_artifacts import repository_identity, _git_sha256
    from scripts.verify_final_anchor import build_final_anchor_receipt, verify_final_anchor
    repo, genesis, cn, idx_path, anchor, head = _build_chain(tmp_path)
    _subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/example/sanming.git"], check=True)
    (repo / "audit.txt").write_bytes(b"audit")
    _subprocess.run(["git", "-C", str(repo), "add", "."], check=True); _subprocess.run(["git", "-C", str(repo), "commit", "-qm", "final"], check=True)
    final_commit = _git(repo, "rev-parse", "HEAD")
    rec = build_final_anchor_receipt(final_commit=final_commit, generation_index_head_sha256=head,
                                     final_audit_receipt_sha256=hashlib.sha256(b"audit").hexdigest(),
                                     approver="lead", approved_at="2026-08-13T00:00:00Z", batch_count=1,
                                     last_batch_anchor_sha256=_git_sha256(anchor), experiment_id=EXPERIMENT_ID,
                                     repository_identity=repository_identity(repo))
    rec_path = tmp_path / "rec.json"; rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    anchors_path = tmp_path / "anchors.json"; anchors_path.write_text(json.dumps([anchor], ensure_ascii=False), encoding="utf-8")
    verify_final_anchor(rec_path, index_rel="gi.json", audit_rel="audit.txt", genesis_anchor=genesis, git_root=repo, anchors_path=anchors_path)
    bad = dict(rec); bad["experiment_id"] = "other"
    bp = tmp_path / "bad.json"; bp.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="experiment_id"):
        verify_final_anchor(bp, index_rel="gi.json", audit_rel="audit.txt", genesis_anchor=genesis, git_root=repo, anchors_path=anchors_path)



def test_clean_subprocess_package_import():
    """P0-1：fill_missing_chapters 必须是干净的包导入——干净子进程 `python -c
    "import scripts.fill_missing_chapters"` 不得依赖 sys.path 手改，也不能因
    双模块（distill_lib vs scripts.distill_lib）而 ModuleNotFoundError。"""
    import subprocess, sys
    r = subprocess.run(
        [sys.executable, "-c", "import scripts.fill_missing_chapters; print('ok', scripts.fill_missing_chapters.run_sanming_batch.__name__)"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60)
    assert r.returncode == 0, f"clean import failed: {r.stderr.strip()}"
    assert "ok" in r.stdout

