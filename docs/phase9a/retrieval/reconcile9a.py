"""Phase 9A 原子对账：manifest expected SHA == 磁盘 actual SHA（逐项）；FAIL 即 exit 1。
--manifest 可选参数：指向镜像 manifest（篡改负向测试用）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
import phase9a_manifest as pm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(P9 / "manifest_v4.json"))
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "sealed":
        sys.exit("FAIL: manifest not sealed")
    # 仓库根推导：manifest 位于 <root>/docs/phase9a/retrieval/manifest_v2.json；镜像模式同样适用
    base = manifest_path.parent.parent.parent.parent
    all_ok = True
    for name, entry in sorted(manifest["entries"].items()):
        p = base / entry["path"]  # 保留仓库相对目录结构（P0：无扁平化碰撞）
        if not p.exists():
            print(f"  FAIL  {name}: missing")
            all_ok = False
            continue
        actual = pm.STRATEGY_FN[entry["strategy"]](p)
        ok = actual == entry["sha256"]
        all_ok = all_ok and ok
        print(f"  {'ok' if ok else 'FAIL'}  {name}  ({entry['strategy']})")
    ev_path = base / "docs/phase9a/retrieval/retrieval_eval.json"  # P0：终态一律从 base 解析（镜像自包含）
    ev = json.loads(ev_path.read_text(encoding="utf-8"))
    if ev["qc_state"] == "QC_FAIL":
        terminal_ok = ev["verdict"] == "SILVER_RETRIEVAL_NOT_READY" and ev["metrics"] == "not_computed"
        denom_ok = True  # QC_FAIL 不计算检索指标
    else:
        terminal_ok = ev["verdict"] in {"SILVER_RETRIEVAL_READY", "SILVER_RETRIEVAL_NOT_READY"} and ev["qc_state"] == "REVIEWED"
        denom_ok = ev["metrics"]["n_items"] == 112
    # RECEIPT 证据链（P0 修订 + 中优）：receipt 存在、artifacts 集合与终态分支精确匹配、
    # 每 artifact 的 sha256/size/strategy 与磁盘一致（从 base 解析）
    import hashlib
    retrieval_dir = base / "docs/phase9a/retrieval"
    receipt_path = retrieval_dir / "RECEIPT.json"
    receipt_ok = receipt_path.exists()
    if receipt_ok:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        expected_artifacts = {"qc_result.json", "retrieval_eval.json"} if ev["qc_state"] == "QC_FAIL" \
            else {"qc_result.json", "retrieval_bundle_dev.jsonl", "per_strategy_eval.json", "retrieval_eval.json"}
        if set(receipt.get("artifacts", {})) != expected_artifacts:
            receipt_ok = False  # 精确 artifact 集合校验（中优）
        for aname, meta in receipt.get("artifacts", {}).items():
            ap = retrieval_dir / aname
            if not ap.exists():
                receipt_ok = False
                break
            raw = ap.read_bytes()
            if hashlib.sha256(raw).hexdigest() != meta.get("sha256") or len(raw) != meta.get("size") or meta.get("strategy") != "raw_bytes":
                receipt_ok = False  # sha256 + size + strategy 全量校验（中优）
                break
        if receipt.get("verdict") != ev["verdict"]:
            receipt_ok = False
    fp_ok = (retrieval_dir / "treatment_fingerprint.json").exists()
    # 迁移链校验（P0/P1 修订）：逐代核对 SHA + stage + entries 数；强制当前 manifest 含 closure 条目
    migration_ok = True
    migration = manifest.get("migration")
    if migration:
        # 1. immediate predecessor SHA + strategy
        pred_path = retrieval_dir / migration["supersedes"]
        if not pred_path.exists():
            migration_ok = False
        else:
            strategy = migration.get("supersedes_sha256_strategy", "json_canonical")
            actual_pred_sha = pm.STRATEGY_FN[strategy](pred_path)
            migration_ok = actual_pred_sha == migration["supersedes_sha256"]
        # 2. 逐代核对 chain 节点的 entries/stage（P0：防虚假链元数据）
        for node in migration.get("chain", []):
            node_path = retrieval_dir / node["version"]
            if not node_path.exists():
                migration_ok = False
                break
            node_data = json.loads(node_path.read_text(encoding="utf-8"))
            if len(node_data["entries"]) != node["entries"] or node_data["stage"] != node["stage"]:
                migration_ok = False
                break
        # 3. 强制当前 manifest 含 closure 条目（P0：防 closure 缺失）
        if "closure" not in manifest["entries"] and "closure_v2" not in manifest["entries"]:
            migration_ok = False
    all_ok = all_ok and terminal_ok and denom_ok and receipt_ok and fp_ok and migration_ok
    print(f"  {'ok' if terminal_ok else 'FAIL'}  terminal verdict ({ev['verdict']}, qc={ev['qc_state']})")
    print(f"  {'ok' if denom_ok else 'FAIL'}  fixed-112 denominator")
    print(f"  {'ok' if receipt_ok else 'FAIL'}  RECEIPT evidence chain")
    print(f"  {'ok' if fp_ok else 'FAIL'}  treatment fingerprint")
    print(f"  {'ok' if migration_ok else 'FAIL'}  migration chain (SHA + stage + entries + closure)")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
