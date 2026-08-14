"""Phase 9A-R1 原子对账：manifest_v5 expected SHA == 磁盘 actual SHA（逐项）；FAIL 即 exit 1。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
import phase9a_manifest as pm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(P9R1 / "manifest_v5.json"))
    parser.add_argument("--r1-dir", default=str(P9R1))
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    r1_dir = Path(args.r1_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "sealed":
        sys.exit("FAIL: manifest not sealed")
    base = manifest_path.parent.parent.parent.parent
    all_ok = True
    for name, entry in sorted(manifest["entries"].items()):
        p = base / entry["path"]
        if not p.exists():
            print(f"  FAIL  {name}: missing")
            all_ok = False
            continue
        actual = pm.STRATEGY_FN[entry["strategy"]](p)
        ok = actual == entry["sha256"]
        all_ok = all_ok and ok
        print(f"  {'ok' if ok else 'FAIL'}  {name}  ({entry['strategy']})")
    # upstream manifest_v4 校验（必需）
    upstream = manifest["entries"].get("upstream_manifest_v4")
    if upstream is None:
        print("  FAIL  upstream_manifest_v4 missing")
        all_ok = False
    else:
        upstream_path = base / upstream["path"]
        upstream_data = json.loads(upstream_path.read_text(encoding="utf-8"))
        upstream_ok = upstream_data["stage"] == "sealed" and pm.STRATEGY_FN[upstream["strategy"]](upstream_path) == upstream["sha256"]
        all_ok = all_ok and upstream_ok
        print(f"  {'ok' if upstream_ok else 'FAIL'}  upstream manifest_v4 (stage=sealed, SHA match)")
    # treatment fingerprint 双 SHA 校验（路径从 manifest 条目解析）
    tf_entry = manifest["entries"]["upstream_treatment_fingerprint"]
    tf_path = base / tf_entry["path"]
    tf = json.loads(tf_path.read_text(encoding="utf-8"))
    tf_file_sha = hashlib.sha256(json.dumps(tf, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b"\n").hexdigest()
    tf_ok = tf_file_sha == tf_entry["sha256"]
    all_ok = all_ok and tf_ok
    print(f"  {'ok' if tf_ok else 'FAIL'}  treatment fingerprint unchanged")
    # calibration fingerprint（组件集合精确相等 + 顺序冻结 + 总摘要重算）
    cf = json.loads((r1_dir / "calibration_fingerprint.json").read_text(encoding="utf-8"))
    expected_names = ["silver_judge_v3_py", "silver_relevance_judgment_v3", "silver_judgment_summary_v3", "qc_sample_list_v2", "attribution_json"]
    cf_names = [c["logical_name"] for c in cf["components"]]
    cf_ok = cf_names == expected_names
    for c in cf["components"]:
        if manifest["entries"].get(c["logical_name"], {}).get("sha256") != c["sha256"]:
            cf_ok = False
    digest = hashlib.sha256()
    for c in cf["components"]:
        digest.update(c["sha256"].encode() + b"\0")
    if digest.hexdigest() != cf["sha256"]:
        cf_ok = False
    all_ok = all_ok and cf_ok
    print(f"  {'ok' if cf_ok else 'FAIL'}  calibration fingerprint (components + aggregate SHA)")
    # verdict 与 effective_disagreement 一致
    qr = json.loads((r1_dir / "qc_result_v2.json").read_text(encoding="utf-8"))
    verdict_ok = (qr["verdict"] == "SILVER_LABEL_CALIBRATED" and qr["effective_disagreement"] <= 6) or \
                 (qr["verdict"] == "SILVER_LABEL_NOT_CALIBRATED" and qr["effective_disagreement"] > 6)
    all_ok = all_ok and verdict_ok
    print(f"  {'ok' if verdict_ok else 'FAIL'}  verdict matches effective_disagreement")
    # RECEIPT 校验（artifact 集合精确相等 + SHA/size/strategy/verdict + 绑定 sealed manifest SHA）
    receipt = json.loads((r1_dir / "RECEIPT_r1.json").read_text(encoding="utf-8"))
    receipt_ok = True
    if set(receipt["artifacts"]) != {"qc_result_v2.json", "calibration_fingerprint.json", "CLOSURE.md"}:
        receipt_ok = False
    if receipt["verdict"] != qr["verdict"]:
        receipt_ok = False
    if receipt["manifest_sha256"] != pm.STRATEGY_FN["json_canonical"](manifest_path):
        receipt_ok = False
    for name, meta in receipt["artifacts"].items():
        raw = (r1_dir / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != meta["sha256"] or len(raw) != meta["size"] or meta["strategy"] != "raw_bytes":
            receipt_ok = False
    all_ok = all_ok and receipt_ok
    print(f"  {'ok' if receipt_ok else 'FAIL'}  RECEIPT (artifacts + sealed manifest binding)")
    # closure 与 qc_result 一致（严格行解析，非子串 in）
    closure = (r1_dir / "CLOSURE.md").read_text(encoding="utf-8")
    fields = {}
    for line in closure.splitlines():
        if ": " in line and not line.startswith("#"):
            k, v = line.split(": ", 1)
            fields[k.strip()] = v.strip()
    closure_ok = (
        fields.get("verdict") == qr["verdict"]
        and fields.get("effective_disagreement") == f"{qr['effective_disagreement']}/61"
        and fields.get("disagreement_count") == str(qr["disagreement_count"])
        and fields.get("uncertain_count") == str(qr["uncertain_count"])
    )
    all_ok = all_ok and closure_ok
    print(f"  {'ok' if closure_ok else 'FAIL'}  closure matches qc_result")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
