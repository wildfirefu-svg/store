"""qc_gate.py：分层抽样 + QC 状态机（HUMAN_QC_REQUIRED / fail-closed / 分歧判定）。"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"


def generate_sample_list(seed: int, ratio: float, judgment_path: Path, out_path: Path) -> dict:
    """按 item 分层抽样（冻结算法）：总样本 = int(pool_size × ratio)；
    每 item 按比例 floor 分配，余数由 rng 从剩余 pool 补足，保证总样本数精确。"""
    if not 0 < ratio <= 1:
        sys.exit(f"FAIL: sample_ratio out of range: {ratio!r}")
    rows = [json.loads(l) for l in judgment_path.open(encoding="utf-8") if l.strip()]
    rng = random.Random(seed)
    by_item: dict[str, list] = {}
    for r in rows:
        by_item.setdefault(r["item_id"], []).append(r)
    total = max(1, int(len(rows) * ratio))
    sample, remaining = [], list(rows)
    for item_id, group in sorted(by_item.items()):
        k = min(len(group), int(len(group) * ratio))  # floor 分配
        chosen = rng.sample(group, k)
        sample.extend(chosen)
        for c in chosen:
            remaining.remove(c)
    if len(sample) < total:  # 余数：从剩余 pool 补足到精确总样本数
        sample.extend(rng.sample(remaining, min(len(remaining), total - len(sample))))
    payload = {"schema_version": "1.0", "seed": seed, "sample_ratio": ratio,
               "pool_size": len(rows), "sample_size": len(sample),
               "sample_list": [{"item_id": s["item_id"], "canonical_key": s["canonical_key"]} for s in sample]}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return payload


LABEL_ENUM = {"relevant", "partially_relevant", "irrelevant", "uncertain"}


def load_human_review(review_path: Path) -> list[dict]:
    """人类复核记录：字段 item_id/canonical_key/human_label/note；校验一一对应。"""
    if not review_path.exists():
        return []
    return [json.loads(l) for l in review_path.open(encoding="utf-8") if l.strip()]


def validate_human_review_schema(reviews: list[dict]) -> None:
    """字段/枚举/非空校验：human_label 必填且属于冻结枚举；note 非空；缺失即 fail-closed（P0 防空标签绕过）。"""
    for r in reviews:
        if not isinstance(r.get("human_label"), str) or r["human_label"] not in LABEL_ENUM:
            sys.exit(f"FAIL: missing or invalid human_label in {r.get('item_id')} {r.get('canonical_key')}: {r.get('human_label')!r}")
        if not isinstance(r.get("note"), str) or not r["note"].strip():
            sys.exit(f"FAIL: empty note in {r.get('item_id')} {r.get('canonical_key')}")


def validate_review_coverage(sample_list: list[dict], reviews: list[dict]) -> None:
    """复核记录与样本一一对应：无缺失、无重复、无额外 pair。失败即 fail-closed。"""
    expected = {(s["item_id"], s["canonical_key"]) for s in sample_list}
    actual = {(r["item_id"], r["canonical_key"]) for r in reviews}
    missing = expected - actual
    extra = actual - expected
    dup = len(reviews) != len(actual)
    if missing or extra or dup:
        sys.exit(f"HUMAN_QC_REQUIRED: coverage mismatch missing={len(missing)} extra={len(extra)} dup={dup}")


def check_disagreement(reviews: list[dict], judgment_path: Path, max_rate: float) -> dict:
    """分歧率 = 人类标签与 silver 标签不一致占比；**纯函数不写盘**（P0 修订：
    qc_result 由 run_eval 与分支产物放入同一发布批次，避免绕过 one-shot 发布事务）。"""
    validate_human_review_schema(reviews)
    silver = {(r["item_id"], r["canonical_key"]): r["label"]
              for r in (json.loads(l) for l in judgment_path.open(encoding="utf-8") if l.strip())}
    n_diff = sum(1 for r in reviews if r["human_label"] != silver[(r["item_id"], r["canonical_key"])])
    rate = n_diff / len(reviews) if reviews else 1.0
    return {"schema_version": "1.0", "disagreement_rate": rate, "n_reviewed": len(reviews), "n_diff": n_diff,
            "max_disagreement_rate": max_rate,
            "verdict": "PASS" if rate <= max_rate else "SILVER_RETRIEVAL_NOT_READY"}


def qc_state(review_path: Path, sample_path: Path) -> str:
    """QC 状态机：无完整复核 → HUMAN_QC_REQUIRED；完整复核后由 evaluate 消费分歧判定。"""
    sample = json.loads(sample_path.read_text(encoding="utf-8"))["sample_list"]
    reviews = load_human_review(review_path)
    if len(reviews) < len(sample):
        return "HUMAN_QC_REQUIRED"
    validate_review_coverage(sample, reviews)
    validate_human_review_schema(reviews)
    return "REVIEWED"


def main() -> None:
    sys.path.insert(0, str(P9))
    sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))
    import phase9a_manifest as pm
    pm.verify_frozen(P9 / "manifest.json", ["qc_config", "silver_relevance_judgment", "qc_gate_py"])
    cfg = json.loads((P9 / "qc_config.json").read_text(encoding="utf-8"))
    generate_sample_list(cfg["seed"], cfg["sample_ratio"], P9 / "silver_relevance_judgment.jsonl", P9 / "qc_sample_list.json")
    print("qc sample list generated")


if __name__ == "__main__":
    main()
