"""Phase 9A-R1 终态发布：单一 finalize 脚本完成终态计算 + fingerprint + closure + 发布 + seal + RECEIPT。
RECEIPT 在 seal manifest 后发布（绑定 sealed manifest SHA），不加入 manifest（避免循环）。
受控 resume：manifest 已 sealed 但 RECEIPT 未发布时，校验产物后补发 RECEIPT。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
STAGING = P9R1 / ".staging_r1"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
import phase9a_manifest as pm  # 仅顶层导入 manifest helper；qc_gate 延迟导入（先验证后导入）


def _count_disagreement(reviews, silver):
    n_uncertain = sum(1 for r in reviews if r["human_label"] == "uncertain")
    n_diff = sum(1 for r in reviews
                 if r["human_label"] != "uncertain" and r["human_label"] != silver[(r["item_id"], r["canonical_key"])])
    return n_diff, n_uncertain


def _atomic_json(path, payload):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def _publish_receipt(m5, verdict):
    """RECEIPT 绑定 sealed manifest SHA，最后原子发布（不加入 manifest）。"""
    manifest_sha = pm.STRATEGY_FN["json_canonical"](m5)
    receipt_artifacts = {}
    for name in ("qc_result_v2.json", "calibration_fingerprint.json", "CLOSURE.md"):
        raw = (P9R1 / name).read_bytes()
        receipt_artifacts[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "strategy": "raw_bytes", "size": len(raw)}
    receipt = {"schema_version": "1.0", "verdict": verdict, "artifacts": receipt_artifacts,
               "manifest_sha256": manifest_sha, "note": "Phase 9A-R1 finalize receipt"}
    STAGING.mkdir(parents=True, exist_ok=True)
    _atomic_json(STAGING / "RECEIPT_r1.json", receipt)
    os.replace(STAGING / "RECEIPT_r1.json", P9R1 / "RECEIPT_r1.json")


def main() -> None:
    m5 = P9R1 / "manifest_v5.json"
    manifest = json.loads(m5.read_text(encoding="utf-8")) if m5.exists() else None
    # 先验证 upstream + qc_gate 冻结 SHA，然后才延迟导入 qc_gate（防漂移代码执行）
    entry = manifest["entries"]["upstream_manifest_v4"]
    actual_upstream = pm.STRATEGY_FN[entry["strategy"]](P9 / "manifest_v4.json")
    if actual_upstream != entry["sha256"]:
        sys.exit("FAIL: upstream_manifest_v4 SHA drift")
    # verify_frozen 是精确 stage 相等，先读 stage 再按实际 stage 验证（否则 sealed 分支永远不可达）
    stage = manifest.get("stage")
    if stage not in {"code_frozen", "sealed"}:
        sys.exit(f"FAIL: unexpected manifest_v5 stage {stage}")
    pm.verify_frozen(m5, ["phase9a_manifest_py"], required_stage=stage)
    pm.verify_frozen(P9 / "manifest_v4.json", ["qc_gate_py", "qc_gate_py_v2", "retriever_py"], required_stage="sealed")
    import qc_gate as qc  # 延迟导入（验证后）
    # stage == sealed：受控 resume，manifest 已 sealed 但 RECEIPT 未发布 → 校验产物后补发 RECEIPT
    if stage == "sealed":
        if (P9R1 / "RECEIPT_r1.json").exists():
            sys.exit("FAIL: RECEIPT_r1.json already exists - one-shot violated")
        entry_map = {"qc_result_v2.json": "qc_result_v2", "calibration_fingerprint.json": "calibration_fingerprint", "CLOSURE.md": "closure"}
        for name, entry_name in entry_map.items():
            entry = manifest["entries"][entry_name]
            actual = pm.STRATEGY_FN[entry["strategy"]](P9R1 / name)
            if actual != entry["sha256"]:
                sys.exit(f"FAIL: {name} SHA mismatch with manifest - manual intervention required")
        verdict = json.loads((P9R1 / "qc_result_v2.json").read_text(encoding="utf-8"))["verdict"]
        _publish_receipt(m5, verdict)
        print(f"finalize_r1: RECEIPT补发完成（manifest 已 sealed，verdict={verdict}）")
        return
    # 正常流程：stage == code_frozen
    # 正常分支先拒绝异常 RECEIPT（不得覆盖）
    if (P9R1 / "RECEIPT_r1.json").exists():
        sys.exit("FAIL: RECEIPT_r1.json already exists but manifest not sealed - one-shot violated")
    pm.verify_frozen(m5, ["silver_relevance_judgment_v3", "qc_sample_list_v2", "qc_human_review_v2", "finalize_r1_py", "reconcile_r1_py"], required_stage="code_frozen")
    state = qc.qc_state(P9R1 / "qc_human_review_v2.jsonl", P9R1 / "qc_sample_list_v2.json")
    if state != "REVIEWED":
        sys.exit(f"HUMAN_QC_REQUIRED: state={state}")
    reviews = qc.load_human_review(P9R1 / "qc_human_review_v2.jsonl")
    qc.validate_review_coverage(json.loads((P9R1 / "qc_sample_list_v2.json").read_text(encoding="utf-8"))["sample_list"], reviews)
    qc.validate_human_review_schema(reviews)
    silver = {(r["item_id"], r["canonical_key"]): r["label"]
              for r in (json.loads(l) for l in (P9R1 / "silver_relevance_judgment_v3.jsonl").open(encoding="utf-8") if l.strip())}
    n_diff, n_uncertain = _count_disagreement(reviews, silver)
    effective = n_diff + n_uncertain
    verdict = "SILVER_LABEL_CALIBRATED" if effective <= 6 else "SILVER_LABEL_NOT_CALIBRATED"
    qc_result = {"schema_version": "1.0", "verdict": verdict, "disagreement_count": n_diff,
                 "uncertain_count": n_uncertain, "effective_disagreement": effective, "max_allowed": 6,
                 "n_reviewed": len(reviews), "note": "effective_disagreement = disagreement + uncertain；≤6 才 CALIBRATED"}
    # 生成三项数据产物到 staging
    staging = STAGING
    staging.mkdir(parents=True, exist_ok=True)
    _atomic_json(staging / "qc_result_v2.json", qc_result)
    manifest = json.loads(m5.read_text(encoding="utf-8"))
    components, digest = [], hashlib.sha256()
    for name in ("silver_judge_v3_py", "silver_relevance_judgment_v3", "silver_judgment_summary_v3", "qc_sample_list_v2", "attribution_json"):
        entry = manifest["entries"][name]
        components.append({"logical_name": name, "path": entry["path"], "strategy": entry["strategy"], "sha256": entry["sha256"]})
        digest.update(entry["sha256"].encode() + b"\0")
    fp = {"schema_version": "1.0", "components": components, "sha256": digest.hexdigest(),
          "note": "Phase 9A-R1 calibration fingerprint；treatment fingerprint 不变（retriever 未改）"}
    _atomic_json(staging / "calibration_fingerprint.json", fp)
    closure = (
        f"# Phase 9A-R1 Closure：silver relevance 标签校准（{verdict}）\n\n"
        f"verdict: {verdict}\n"
        f"effective_disagreement: {effective}/61\n"
        f"disagreement_count: {n_diff}\n"
        f"uncertain_count: {n_uncertain}\n"
        f"max_allowed: 6\n"
        f"sample_size: 61\n"
        f"item_coverage: 37\n"
        f"seed: 20260814\n\n"
        f"校准规则变更点：cat_ok 可选（query 无 category 时不降级）。\n"
        f"后续衔接：R2（候选覆盖）。\n"
    )
    (staging / "CLOSURE.md").write_text(closure, encoding="utf-8", newline="\n")
    # 发布三项数据产物（逐项存在则字节一致校验，防覆盖）
    for name in ("qc_result_v2.json", "calibration_fingerprint.json", "CLOSURE.md"):
        target = P9R1 / name
        if target.exists():
            if target.read_bytes() != (staging / name).read_bytes():
                sys.exit(f"FAIL: existing {name} byte mismatch - manual intervention required")
            continue
        os.replace(staging / name, target)
    # 冻结数据产物 + seal manifest
    pm.freeze(m5, {
        "qc_result_v2": (P9R1 / "qc_result_v2.json", "json_canonical"),
        "calibration_fingerprint": (P9R1 / "calibration_fingerprint.json", "json_canonical"),
        "closure": (P9R1 / "CLOSURE.md", "git_canonical_lf"),
    })
    pm.set_stage(m5, "sealed")
    # RECEIPT 绑定 sealed manifest SHA，最后原子发布（不加入 manifest）
    _publish_receipt(m5, verdict)
    print(f"finalize_r1: verdict={verdict}, effective_disagreement={effective}/61, manifest_v5 sealed, RECEIPT published")


if __name__ == "__main__":
    main()
