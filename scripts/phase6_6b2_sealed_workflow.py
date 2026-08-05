#!/usr/bin/env python3
"""Phase 6 6B2 sealed workflow - enrichment + 2023 RUNNING/FINALIZED state machine + stage gating.

Task 15 implementation per v18 plan.
"""
from __future__ import annotations

import datetime
import hashlib
import inspect
import json
import os
from pathlib import Path


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_func(fn):
    return hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()


def _now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# 2023 原始数据集预登记 SHA-256（已核验）
BLESSED_2023_RAW_SHA256 = "8933783ef7da9084adeb0a9940d12277de6a1c3def41374f836bec48c4afcd3d"

RECEIPT_REQUIRED_FIELDS = (
    "verdict", "stage", "run_id", "user_run_id", "archive_dir",
    "audit_index_sha256", "provider", "model",
    "code_fingerprint", "dataset_sha256",
)


def enrich_year(year, input_path, output_path):
    """Enrich a holdout year dataset with chart input. Fail-closed on coverage."""
    from scripts.enrich_holdout_chart_input import enrich_row, load_jsonl, write_jsonl
    rows = [enrich_row(r) for r in load_jsonl(input_path)]
    write_jsonl(output_path, rows)
    has_zw = sum(1 for r in rows if r.get("chart_input", {}).get("ziwei"))
    if has_zw < len(rows):
        raise SystemExit(f"enrichment 覆盖率不足: {has_zw}/{len(rows)}")
    return {
        "year": year,
        "input_sha256": _sha256_file(input_path),
        "output_sha256": _sha256_file(output_path),
        "code_sha256": _sha256_func(enrich_row),
        "rows": len(rows),
        "ziwei_coverage": has_zw,
    }


def check_stage_gate(stage, gate_root="docs/phase6/6b2", provider=None, model=None,
                     current_code_fingerprint=None, expected_user_run_id=None):
    """Stage gate admission. v16 field-level validation. Returns validated receipt or SystemExit.

    expected_user_run_id: if provided, every receipt's user_run_id MUST equal this value.
    For final_2023, dev and reuse receipts MUST also share the same user_run_id.
    """
    r = Path(gate_root)

    def _validate_receipt(name, expect_stage, expect_verdicts):
        path = r / name
        if not path.exists():
            raise SystemExit(f"{expect_stage} receipt 缺失: {path}")
        rec = json.loads(path.read_text(encoding="utf-8"))
        missing = [k for k in RECEIPT_REQUIRED_FIELDS if k not in rec]
        if missing:
            raise SystemExit(f"{expect_stage} receipt 缺字段 {missing}")
        if rec["stage"] != expect_stage:
            raise SystemExit(f"receipt stage 不符: {rec['stage']} != {expect_stage}")
        if rec["verdict"] not in expect_verdicts:
            raise SystemExit(f"{expect_stage} 未通过 ({rec.get('verdict')})")
        # P0-1: verify user_run_id matches expected if provided
        if expected_user_run_id is not None:
            rid = rec.get("user_run_id")
            if rid != expected_user_run_id:
                raise SystemExit(
                    f"{expect_stage} receipt user_run_id 不一致: "
                    f"receipt={rid!r}, expected={expected_user_run_id!r}")
        archive_dir = Path(rec["archive_dir"])
        audit_path = archive_dir / "audit_index.json"
        if not archive_dir.exists() or not audit_path.exists():
            raise SystemExit(f"{expect_stage} 归档或 audit_index.json 缺失")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if _sha256_file(str(audit_path)) != rec["audit_index_sha256"]:
            raise SystemExit(f"{expect_stage} audit SHA 与 receipt 不一致")
        if audit.get("code_fingerprint") != rec["code_fingerprint"]:
            raise SystemExit(f"{expect_stage} receipt 与 audit 代码指纹交叉不一致")
        if audit.get("run_id") != rec["run_id"]:
            raise SystemExit(f"{expect_stage} audit.run_id != receipt.run_id")
        if audit.get("user_run_id") != rec.get("user_run_id"):
            raise SystemExit(f"{expect_stage} audit.user_run_id != receipt.user_run_id")
        if audit.get("stage") != rec["stage"]:
            raise SystemExit(f"{expect_stage} audit.stage != receipt.stage")
        if audit.get("provider") != rec.get("provider"):
            raise SystemExit(f"{expect_stage} audit.provider != receipt.provider")
        if audit.get("model") != rec.get("model"):
            raise SystemExit(f"{expect_stage} audit.model != receipt.model")
        if audit.get("gate_verdict") != rec.get("verdict"):
            raise SystemExit(f"{expect_stage} audit.gate_verdict != receipt.verdict")
        if provider and rec["provider"] != provider:
            raise SystemExit(f"{expect_stage} provider 不一致: {rec['provider']} != {provider}")
        if model and rec["model"] != model:
            raise SystemExit(f"{expect_stage} model 不一致: {rec['model']} != {model}")
        if current_code_fingerprint and rec["code_fingerprint"] != current_code_fingerprint:
            raise SystemExit(f"{expect_stage} receipt 代码指纹与当前代码不一致")
        return rec

    if stage == "reuse":
        return _validate_receipt("dev_gate.json", "dev", ("PROMOTE_CANDIDATE",))
    elif stage == "final_2023":
        dev_rec = _validate_receipt("dev_gate.json", "dev", ("PROMOTE_CANDIDATE",))
        reuse_rec = _validate_receipt("reuse_gate.json", "reuse", ("PASS",))
        # P0-1: cross-stage chain integrity — dev and reuse MUST share user_run_id
        dev_urid = dev_rec.get("user_run_id")
        reuse_urid = reuse_rec.get("user_run_id")
        if dev_urid != reuse_urid:
            raise SystemExit(
                f"final_2023 跨阶段 user_run_id 不一致: "
                f"dev={dev_urid!r}, reuse={reuse_urid!r} (混合链拒绝)")
        return {"dev": dev_rec, "reuse": reuse_rec}
    else:
        raise SystemExit(f"unknown stage: {stage}")


def acquire_2023_run_lock(lock_path, run_id, code_fingerprint, schedule_hash,
                          budget_hard_cap=None):
    """Atomically acquire 2023 RUNNING lock with blessed raw SHA. O_EXCL for new runs."""
    lp = Path(lock_path)
    if lp.exists():
        st = json.loads(lp.read_text(encoding="utf-8"))
        if st.get("status") == "FINALIZED":
            raise SystemExit("2023 已 FINALIZED, 禁止重跑（密封终验）")
        if st.get("status") == "RUNNING":
            if (st.get("run_id") == run_id
                    and st.get("raw_sha256") == BLESSED_2023_RAW_SHA256
                    and st.get("code_fingerprint") == code_fingerprint):
                return "RESUME"
            raise SystemExit("2023 RUNNING 但指纹不匹配, 禁止恢复")
    lp.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(
        status="RUNNING", run_id=run_id,
        raw_sha256=BLESSED_2023_RAW_SHA256,
        code_fingerprint=code_fingerprint, schedule_hash=schedule_hash,
        started_at=_now_iso(),
    )
    if budget_hard_cap is not None:
        payload["budget_hard_cap"] = budget_hard_cap
    try:
        fd = os.open(str(lp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("2023 锁已被其他进程持有 (fail-closed)")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False))
    return "NEW"


def verify_2023_raw_data(raw_path, pre_blessed_sha):
    """Verify raw data matches blessed SHA after acquiring lock."""
    actual = _sha256_file(raw_path)
    if actual != pre_blessed_sha:
        raise SystemExit(f"2023 原始数据 SHA 不匹配: {actual} != {pre_blessed_sha} (BLOCKED)")


def record_enriched_sha_to_lock(lock_path, enriched_path):
    """Record enriched dataset SHA to RUNNING lock after enrichment. RESUME validates consistency."""
    lp = Path(lock_path)
    st = json.loads(lp.read_text(encoding="utf-8"))
    if st.get("status") != "RUNNING":
        raise SystemExit(f"record_enriched 拒绝: 锁非 RUNNING (当前 {st.get('status')})")
    new_sha = _sha256_file(enriched_path)
    existing_sha = st.get("enriched_sha256")
    if existing_sha is not None:
        if new_sha != existing_sha:
            raise SystemExit(f"record_enriched 拒绝: enriched SHA 不一致 (现有 {existing_sha} != 新 {new_sha})")
        return
    st["enriched_sha256"] = new_sha
    tmp = lp.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(lp))


def update_lock_schedule_hash(lock_path, schedule_hash):
    """Update schedule_hash in RUNNING lock after schedule is built. Must be called before running slices."""
    lp = Path(lock_path)
    st = json.loads(lp.read_text(encoding="utf-8"))
    if st.get("status") != "RUNNING":
        raise SystemExit(f"update_sched_hash 拒绝: 锁非 RUNNING (当前 {st.get('status')})")
    existing = st.get("schedule_hash")
    if existing and existing != "pending" and existing != schedule_hash:
        raise SystemExit(f"update_sched_hash 拒绝: schedule_hash 不一致 (现有 {existing} != 新 {schedule_hash})")
    st["schedule_hash"] = schedule_hash
    tmp = lp.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(lp))


def finalize_2023_run_lock(lock_path, archive_path, gate_verdict,
                           schedule_complete, integrity_passed):
    """Transactionally switch RUNNING -> FINALIZED after all validations pass.
    Failures keep lock in RUNNING state.
    """
    if not schedule_complete:
        raise SystemExit("finalize 拒绝: schedule 未完整 (保持 RUNNING)")
    if not integrity_passed:
        raise SystemExit("finalize 拒绝: integrity gate 未通过 (保持 RUNNING)")
    archive_path = Path(archive_path)
    audit_path = archive_path / "audit_index.json"
    if not audit_path.exists():
        raise SystemExit("finalize 拒绝: archive/audit_index.json 不存在 (保持 RUNNING)")
    audit_sha = _sha256_file(str(audit_path))
    lp = Path(lock_path)
    st = json.loads(lp.read_text(encoding="utf-8"))
    if st.get("status") != "RUNNING":
        raise SystemExit(f"finalize 拒绝: 锁非 RUNNING (当前 {st.get('status')})")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("run_id") != st.get("run_id"):
        raise SystemExit(f"finalize 拒绝: audit run_id={audit.get('run_id')} != 锁 {st.get('run_id')}")
    if audit.get("stage") != "final_2023":
        raise SystemExit(f"finalize 拒绝: audit stage={audit.get('stage')} != final_2023")
    if audit.get("gate_verdict") != gate_verdict:
        raise SystemExit(f"finalize 拒绝: audit gate_verdict={audit.get('gate_verdict')} != {gate_verdict}")
    if audit.get("code_fingerprint") != st.get("code_fingerprint"):
        raise SystemExit("finalize 拒绝: audit code_fingerprint 与锁不一致")
    if audit.get("sched_hash") != st.get("schedule_hash"):
        raise SystemExit("finalize 拒绝: audit sched_hash 与锁不一致")
    raw_hashes = audit.get("dataset_hashes", {}).get("raw")
    if raw_hashes != st.get("raw_sha256"):
        raise SystemExit("finalize 拒绝: audit raw_dataset_hashes 与锁不一致")
    enriched_hash = audit.get("dataset_hashes", {}).get("enriched")
    if enriched_hash != st.get("enriched_sha256"):
        raise SystemExit("finalize 拒绝: audit enriched_sha256 与锁不一致")
    if audit.get("budget_hard_cap") != st.get("budget_hard_cap"):
        raise SystemExit("finalize 拒绝: audit budget_hard_cap 与锁不一致")
    if audit.get("integrity_result") != "PASS":
        raise SystemExit("finalize 拒绝: audit integrity_result 非 PASS")
    st.update({
        "status": "FINALIZED", "finalized_at": _now_iso(),
        "archive_id": archive_path.name, "audit_index_sha256": audit_sha,
        "gate_verdict": gate_verdict,
    })
    tmp = lp.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(lp))
