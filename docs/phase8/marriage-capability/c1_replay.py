"""C1 一致性转换器：回放评估器（Phase 8，6A 单版本开发冻结 / 6B 单次回放）。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md v1.3.1（§P8-3）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md v3.2（Task 6A/6B）

纯评估逻辑：逐题 old_letter/new_letter/expected/change_result 四态；分母对账；
0018/0034/0073 判定；PASS/TERMINATED 终态裁决。只用合成 fixture 开发冻结。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P8_DIR = REPO / "docs" / "phase8" / "marriage-capability"

TARGET_CASES = ["mingli_ftb_0018", "mingli_ftb_0034", "mingli_ftb_0073"]
CHANGE_RESULTS = ["improved", "harmed", "unchanged", "changed_wrong_to_wrong"]


def _load_detector():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "c1_detector", P8_DIR / "c1_detector.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["c1_detector"] = mod
    spec.loader.exec_module(mod)
    return mod


def _check_frozen_and_no_overwrite(out_path: Path) -> None:
    """6B.1 运行前校验：双冻结 SHA == manifest；eval 已存在即拒绝覆盖。"""
    import hashlib

    manifest_path = P8_DIR / "phase8_freeze_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {e["path"]: e for e in manifest["entries"]}
    for name in ("c1_detector.py", "c1_replay.py"):
        rel = f"docs/phase8/marriage-capability/{name}"
        current = hashlib.sha256(
            (P8_DIR / name).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        frozen = entries[rel]["sha256"]
        if current != frozen:
            sys.exit(f"6B.1 拒绝运行：{name} SHA 漂移 {current} != {frozen}")
    if out_path.exists():
        sys.exit("6B.1 拒绝运行：c1_detector_eval.json 已存在（单次回放机械门）")


def evaluate_row(row: dict, detector=None) -> dict:
    """逐题评估：old/new/expected/change_result。"""
    detector = detector or _load_detector()
    old_letter = row["predicted_answer"]
    expected = row["expected_answer"]
    raw = row.get("raw_answer") or ""
    options = row.get("options") or []

    det = detector.detect(raw, options)
    new_letter = None
    if det["conflict"] and det["candidate_letter"]:
        candidate = det["candidate_letter"]
        if candidate != old_letter:
            new_letter = candidate
        else:
            new_letter = old_letter  # 触发且候选==old → unchanged

    if new_letter is None:
        change_result = "unchanged"
    elif new_letter == expected and old_letter != expected:
        change_result = "improved"
    elif new_letter != expected and old_letter == expected:
        change_result = "harmed"
    elif new_letter != expected and old_letter != expected:
        change_result = "changed_wrong_to_wrong"
    else:
        change_result = "unchanged"

    return {
        "case_id": row["case_id"],
        "old_letter": old_letter,
        "new_letter": new_letter,
        "expected": expected,
        "change_result": change_result,
    }


def compute_verdict(rows: list[dict]) -> dict:
    """终态裁决：0018/0034/0073 全 improved 且 harmed=0 → C1_PASS，否则 C1_TERMINATED。"""
    detector = _load_detector()
    results = [evaluate_row(r, detector) for r in rows]
    counts = {k: 0 for k in CHANGE_RESULTS}
    for r in results:
        counts[r["change_result"]] += 1
    targets = [r for r in results if r["case_id"] in TARGET_CASES]
    targets_improved = [r["case_id"] for r in targets if r["change_result"] == "improved"]
    verdict = (
        "C1_PASS"
        if len(targets_improved) == len(TARGET_CASES) and counts["harmed"] == 0
        else "C1_TERMINATED"
    )
    return {
        "verdict": verdict,
        "counts": counts,
        "harmed": counts["harmed"],
        "targets_improved": targets_improved,
        "results": results,
    }


def run_replay(details_path: Path, out_path: Path, cases160_path: Path | None = None) -> dict:
    """单次回放（6B）：只执行已冻结 evaluator，产出 c1_detector_eval.json。

    merged_details.jsonl 无 options 字段，需从 mingli_160.jsonl 按 case_id 补充。
    """
    rows = [
        json.loads(l) for l in details_path.open(encoding="utf-8") if l.strip()
    ]
    if cases160_path is not None:
        norm = {
            r["case_id"]: r
            for r in (json.loads(l) for l in cases160_path.open(encoding="utf-8") if l.strip())
        }
        for row in rows:
            if "options" not in row or row["options"] is None:
                row["options"] = (norm.get(row["case_id"]) or {}).get("options")
    verdict = compute_verdict(rows)
    verdict["replay_count"] = 1
    verdict["total"] = len(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return verdict


def main() -> None:
    out_path = P8_DIR / "c1_detector_eval.json"
    _check_frozen_and_no_overwrite(out_path)
    run_replay(
        REPO / "docs" / "phase7" / "phase7-mingli-v4flash-nt-20260811-r2" / "merged_details.jsonl",
        out_path,
        REPO / "docs" / "phase7" / "phase7-mingli-v4flash-nt-20260811-r2" / "mingli_160.jsonl",
    )
    print(f"c1 replay written to {out_path}")


if __name__ == "__main__":
    main()
