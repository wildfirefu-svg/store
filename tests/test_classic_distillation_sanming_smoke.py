import sys as _sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_ROOT / "scripts"))

"""完整协议 fake-runner E2E：snapshot -> restore -> 崩溃(attempt1 无 terminal) -> 恢复(published) -> finalize_batch -> git commit -> verify_batch_anchors -> verify_final_anchor。末行断言：receipt["genesis_commit"]==genesis、idx.genesis==genesis、rec["final_commit"]==final_commit。"""
import json, subprocess, hashlib
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parent.parent

def _git_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def _dispatch_fake(prompt, timeout=300):
    if "提取结构化命理规则" in prompt: return '[{"rule":"甲木日主喜水","condition":"甲木生于寅月","subject":"甲木","original_text":"甲木喜水"}]'
    if "生成一道四选一选择题" in prompt: return '{"question":"甲木喜什么？","options":{"A":"喜水滋润","B":"火","C":"土","D":"金"},"answer":"A","explanation":"甲木喜水"}'
    return "[]"

def _mk_snapshot(tmp_path, text="第一段。\n\n第二段。\n" * 40):
    from scripts.fetch_sanming_chapters import ChapterEntry, build_and_publish_snapshot, read_active_snapshot, materialization_status, restore_responses
    body = b"B"
    def factory(entries):
        return [{"chapter_index": e.index, "title": e.title, "url": e.url, "response_body_sha256": hashlib.sha256(body).hexdigest(), "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "extractor_sha256": "x"*64, "normalized_page_title": e.title, "response_body_status": "archived", "provenance_level": "full", "encoding": "utf-8", "extracted_text": text, "response_body": body, "ok": True} for e in entries]
    formal = tmp_path / "formal"
    build_and_publish_snapshot([ChapterEntry(81, "卷六·论命", "u1")], formal, records_factory=factory, archive_root=tmp_path / "store")
    act = read_active_snapshot(formal); sha = act["snapshot_sha256"]
    restore_responses(formal, sha, archive_root=tmp_path / "store")
    assert materialization_status(formal, sha) == "materialized"
    return formal / "source_snapshots" / sha / "extracted", act, formal

def _mk_manifest(tmp_path, batch_id, snapshot_dir, out_dir, repo, head, seg_sha, cfg_sha, code_sha, pre_run_sha, parent, snap_shas):
    from scripts.distill_lib import EXPERIMENT_ID
    m = {"schema_version": "1.0", "batch_id": batch_id, "selected_chapter_ids": [81], "source_sha_map": {"81": hashlib.sha256((snapshot_dir / "raw_081.txt").read_bytes()).hexdigest()}, "segment_manifest_sha": seg_sha, "pre_run_output_sha": pre_run_sha, "model_prompt_config_sha": cfg_sha, "batch_hard_cap": 100, "parent_commit": parent, "parent_head_sha": head, "code_sha": code_sha, "rules_sha": "0"*64, "source_snapshot_sha256": snap_shas["snapshot"], "source_manifest_sha256": snap_shas["manifest"], "source_archive_pointer_sha256": snap_shas["pointer"], "experiment_id": EXPERIMENT_ID}
    p = tmp_path / f"{batch_id}.json"; p.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8"); return p

def _run_batch(tmp_path, monkeypatch, mp, snap_dir, out, repo, formal, act, fake_call, genesis_anchor="0"*40, generation_index_path=None):
    import scripts.distill_lib as dl
    from scripts.fill_missing_chapters import run_sanming_batch
    monkeypatch.setattr(dl, "_call", fake_call)
    _dm = _sys.modules.get("distill_lib")
    if _dm is not None:
        monkeypatch.setattr(_dm, "_call", fake_call)
    return run_sanming_batch(mp, snapshot_dir=snap_dir, out_dir=out, formal_dir=formal, snapshot_sha=act["snapshot_sha256"], proj_ledger_path=tmp_path / "project.json", run_ledger_path=tmp_path / "run.json", run_id="R1", project_total_cap=1000, scripts_dir=Path("scripts"), root=ROOT, git_root=repo, genesis_anchor=genesis_anchor, generation_index_path=generation_index_path)

def _git(repo, *args): return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()

def test_e2e_full_protocol_crash_then_resume(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    from scripts.fetch_sanming_chapters import _file_sha256
    from scripts.fill_missing_chapters import _segment_manifest_sha, _model_prompt_config_sha, _code_sha_now
    from scripts.classic_artifacts import GenerationIndex, generation_index_sha256, finalize_batch, batch_anchor_receipt, verify_batch_anchors, repository_identity
    from scripts.verify_final_anchor import build_final_anchor_receipt, verify_final_anchor
    snap_dir, act, formal = _mk_snapshot(tmp_path)
    out = tmp_path / "book"; out.mkdir()
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/example/sanming.git"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    genesis = _git(repo, "rev-parse", "HEAD")
    segs = {81: dl.segment_chapter((snap_dir / "raw_081.txt").read_text(encoding="utf-8"), book="sanmingtonghui", chapter="81", limits=dl.PromptLimits())}
    code_sha = _code_sha_now(Path("scripts"), ROOT)
    pre_run_sha = hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest()
    snap_dir_path = formal / "source_snapshots" / act["snapshot_sha256"]
    snap_shas = {"snapshot": act["snapshot_sha256"], "manifest": act["source_manifest_sha256"], "pointer": _file_sha256(snap_dir_path / "RESPONSE_ARCHIVE_POINTER.json")}
    mp = _mk_manifest(tmp_path, "B1", snap_dir, out, repo, genesis, seg_sha=_segment_manifest_sha(segs), cfg_sha=_model_prompt_config_sha(), code_sha=code_sha, pre_run_sha=pre_run_sha, parent=genesis, snap_shas=snap_shas)
    # 运行 1：KeyboardInterrupt 崩溃
    def kbi(*a, **k): raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt): _run_batch(tmp_path, monkeypatch, mp, snap_dir, out, repo, formal, act, kbi, genesis_anchor=genesis)
    from scripts.distill_lib import attempt_base_id, next_attempt_no, attempt_id_for
    proj1 = dl.ProjectLedger.load_or_create(tmp_path / "project.json", experiment_id=dl.EXPERIMENT_ID, total_cap=1000)
    run1 = dl.BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=100, run_id="R1", code_sha=code_sha, rules_sha="0"*64)
    base = attempt_base_id(run_id="R1", batch_id="B1", chapter_id=80, segment_id=0, operation="rules", rule_id=None)
    att1 = attempt_id_for(run_id="R1", batch_id="B1", chapter_id=80, segment_id=0, operation="rules", rule_id=None, attempt_no=1)
    assert proj1.calls_made == 1 and run1.calls_made == 1
    assert run1.attempts[att1]["status"] == "attempted"
    assert next_attempt_no(run1, base_id=base) == 2
    # 运行 2：恢复，从 attempt2 起成功
    res2 = _run_batch(tmp_path, monkeypatch, mp, snap_dir, out, repo, formal, act, _dispatch_fake, genesis_anchor=genesis)
    assert res2["status"] == "published"
    run2 = dl.BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=100, run_id="R1", code_sha=code_sha, rules_sha="0"*64)
    proj2 = dl.ProjectLedger.load_or_create(tmp_path / "project.json", experiment_id=dl.EXPERIMENT_ID, total_cap=1000)
    assert proj2.calls_made == run2.calls_made
    att2 = attempt_id_for(run_id="R1", batch_id="B1", chapter_id=80, segment_id=0, operation="rules", rule_id=None, attempt_no=2)
    assert run2.attempts[att2]["status"] == "success"
    # finalize + anchor + final-anchor
    gi = tmp_path / "gi.json"
    idx = GenerationIndex(gi, genesis_anchor=genesis)
    receipt = out / ".batch" / "B1" / "completed_receipt.json"
    fin = finalize_batch(batch_id="B1", completed_receipt_path=receipt, index_path=gi, genesis_anchor=genesis)
    (repo / "out").mkdir(exist_ok=True)
    (repo / "out" / "all_rules.json").write_bytes((out / "all_rules.json").read_bytes())
    (repo / "out" / "completed_receipt.json").write_bytes(receipt.read_bytes())
    (repo / "gi.json").write_bytes(gi.read_bytes())
    (repo / "out" / "source_manifest.json").write_bytes((snap_dir_path / "source_manifest.json").read_bytes())
    anchor = batch_anchor_receipt(batch_id="B1", parent_commit=genesis, head_sha=fin["head_sha"], index_rel="gi.json", anchor_rel="out/batch_anchor.json", completed_receipt_rel="out/completed_receipt.json", completed_receipt_sha256=fin["completed_receipt_sha256"], source_snapshot_sha256=act["snapshot_sha256"], source_snapshot_rel="out/source_manifest.json")
    (repo / "out" / "batch_anchor.json").write_text(json.dumps(anchor, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "batch Cn"], check=True)
    cn = _git(repo, "rev-parse", "HEAD")
    assert verify_batch_anchors([anchor], git_root=repo, genesis_commit=genesis, final_commit=cn) is True
    assert idx.verify() is True
    full_head = generation_index_sha256(idx._load())
    assert idx.verify(expected_head=full_head) is True
    audit = repo / "audit.txt"; audit.write_bytes(b"audit")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "final"], check=True)
    final_commit = _git(repo, "rev-parse", "HEAD")
    repo_identity = repository_identity(repo)
    from scripts.classic_artifacts import EXPERIMENT_ID
    rec = build_final_anchor_receipt(final_commit=final_commit, generation_index_head_sha256=full_head, final_audit_receipt_sha256=hashlib.sha256(b"audit").hexdigest(), approver="lead", approved_at="2026-08-13T00:00:00Z", batch_count=1, last_batch_anchor_sha256=_git_sha256(anchor), experiment_id=EXPERIMENT_ID, repository_identity=repo_identity)
    rec_path = tmp_path / "rec.json"; rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    anchors_path = tmp_path / "anchors.json"; anchors_path.write_text(json.dumps([anchor], ensure_ascii=False), encoding="utf-8")
    verify_final_anchor(rec_path, index_rel="gi.json", audit_rel="audit.txt", genesis_anchor=genesis, git_root=repo, anchors_path=anchors_path)
    # P0-3：三条独立断言
    assert json.loads(receipt.read_text(encoding="utf-8"))["genesis_commit"] == genesis
    assert idx.genesis == genesis
    assert rec["final_commit"] == final_commit

def test_e2e_always_down_never_publishes(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    from scripts.fetch_sanming_chapters import _file_sha256
    from scripts.fill_missing_chapters import _segment_manifest_sha, _model_prompt_config_sha, _code_sha_now
    snap_dir, act, formal = _mk_snapshot(tmp_path)
    out = tmp_path / "book"; out.mkdir()
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    head0 = _git(repo, "rev-parse", "HEAD")
    segs = {81: dl.segment_chapter((snap_dir / "raw_081.txt").read_text(encoding="utf-8"), book="sanmingtonghui", chapter="81", limits=dl.PromptLimits())}
    pre_run_sha = hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest()
    snap_dir_path = formal / "source_snapshots" / act["snapshot_sha256"]
    snap_shas = {"snapshot": act["snapshot_sha256"], "manifest": act["source_manifest_sha256"], "pointer": _file_sha256(snap_dir_path / "RESPONSE_ARCHIVE_POINTER.json")}
    mp = _mk_manifest(tmp_path, "B2", snap_dir, out, repo, head0, seg_sha=_segment_manifest_sha(segs), cfg_sha=_model_prompt_config_sha(), code_sha=_code_sha_now(Path("scripts"), ROOT), pre_run_sha=pre_run_sha, parent=head0, snap_shas=snap_shas)
    def boom(*a, **k): raise RuntimeError("network down")
    res = _run_batch(tmp_path, monkeypatch, mp, snap_dir, out, repo, formal, act, boom, genesis_anchor=head0)
    assert res["status"] == "resume"
    assert not (out / "all_rules.json").exists()
    assert not (out / ".batch_staging" / "B2").exists()
