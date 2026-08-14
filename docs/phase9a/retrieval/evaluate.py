"""Phase 9A frozen retrieval metrics and bundle construction."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"

W_RELEVANT = 1.0
W_PARTIAL = 0.5
GATES = {
    "judgeable_item_rate": 0.90,
    "macro_weighted_recall": 0.90,
    "macro_bundle_noise": 0.20,
    "binary_item_coverage": 0.90,
}


def compute_metrics(
    judgment: list[dict], items: list[str], bundles: dict[str, list[dict]]
) -> dict:
    """Compute frozen silver metrics over the complete item denominator."""
    item_set = set(items)
    judgment_items = {row["item_id"] for row in judgment}
    bundle_items = set(bundles)
    outside = (judgment_items | bundle_items) - item_set
    if outside:
        sys.exit(f"FAIL: judgment/bundle items outside frozen set {sorted(outside)}")

    lookup = {
        (row["item_id"], row["canonical_key"]): row["label"] for row in judgment
    }
    per_item: dict[str, dict] = {}
    for item_id in items:
        pairs = [row for row in judgment if row["item_id"] == item_id]
        gold_mass = sum(
            W_RELEVANT
            if row["label"] == "relevant"
            else W_PARTIAL
            if row["label"] == "partially_relevant"
            else 0.0
            for row in pairs
        )
        if pairs and all(row["label"] == "uncertain" for row in pairs):
            per_item[item_id] = {
                "status": "UNJUDGEABLE",
                "gold_mass": 0.0,
                "binary_coverage": 0.0,
            }
            continue
        if gold_mass == 0:
            per_item[item_id] = {
                "status": "no_gold_mass",
                "gold_mass": 0.0,
                "binary_coverage": 0.0,
            }
            continue

        retrieved = bundles.get(item_id, [])
        retrieved_weight = sum(
            W_RELEVANT
            if lookup.get((item_id, hit["canonical_key"])) == "relevant"
            else W_PARTIAL
            if lookup.get((item_id, hit["canonical_key"])) == "partially_relevant"
            else 0.0
            for hit in retrieved
        )
        judged_labels = [
            lookup[(item_id, hit["canonical_key"])]
            for hit in retrieved
            if lookup.get((item_id, hit["canonical_key"]))
            in {"relevant", "partially_relevant", "irrelevant"}
        ]
        noise = (
            sum(label == "irrelevant" for label in judged_labels)
            / len(judged_labels)
            if judged_labels
            else 0.0
        )
        per_item[item_id] = {
            "status": "judged",
            "gold_mass": gold_mass,
            "weighted_recall": retrieved_weight / gold_mass,
            "bundle_noise": noise,
            "binary_coverage": 1.0 if retrieved_weight > 0 else 0.0,
        }

    unjudgeable = {
        item_id
        for item_id, values in per_item.items()
        if values["status"] == "UNJUDGEABLE"
    }
    no_gold = {
        item_id
        for item_id, values in per_item.items()
        if values["status"] == "no_gold_mass"
    }
    judged = {
        item_id: values
        for item_id, values in per_item.items()
        if values["status"] == "judged"
    }
    n_items = len(items)
    recalls = [values["weighted_recall"] for values in judged.values()]
    noises = [values["bundle_noise"] for values in judged.values()]
    return {
        "n_items": n_items,
        "judgeable_item_rate": (n_items - len(unjudgeable | no_gold)) / n_items,
        "macro_weighted_recall": sum(recalls) / len(recalls) if recalls else 0.0,
        "macro_bundle_noise": sum(noises) / len(noises) if noises else 0.0,
        "binary_item_coverage": sum(
            values["binary_coverage"] for values in per_item.values()
        )
        / n_items,
        "unjudgeable_items": sorted(unjudgeable),
        "no_gold_mass_items": sorted(no_gold),
        "macro_denominator": len(judged),
        "per_item": per_item,
    }


def decide(metrics: dict) -> str:
    passed = (
        metrics["judgeable_item_rate"] >= GATES["judgeable_item_rate"]
        and metrics["macro_weighted_recall"] >= GATES["macro_weighted_recall"]
        and metrics["macro_bundle_noise"] <= GATES["macro_bundle_noise"]
        and metrics["binary_item_coverage"] >= GATES["binary_item_coverage"]
    )
    return "SILVER_RETRIEVAL_READY" if passed else "SILVER_RETRIEVAL_NOT_READY"


def build_bundle(
    item_map: list[dict],
    config: dict,
    strategies: tuple[str, ...] = ("s1", "s2", "s3", "s4", "s5"),
    strategy_outputs_path: Path | None = None,
) -> list[dict]:
    """Build bundles from frozen strategy output under a per-question budget."""
    import retriever as rt
    import strategy_store as store

    output_path = strategy_outputs_path or P9 / "strategy_outputs.jsonl"
    frozen = store.load_frozen_strategy_hits(output_path)
    max_chars = config["N_chars_per_doc"]
    max_docs = config["M_docs_per_item"]
    question_budget = config["K_chars_per_question"]

    by_case: dict[str, list[dict]] = {}
    for item in item_map:
        by_case.setdefault(item["case_id"], []).append(item)

    rows: list[dict] = []
    for case_id, case_items in sorted(by_case.items()):
        remaining = question_budget
        for item in case_items:
            pooled: list[dict] = []
            seen: set[str] = set()
            for query in item["queries"]:
                for strategy, hits in frozen.get(query["query_id"], {}).items():
                    if strategy not in strategies:
                        continue
                    for hit in hits:
                        key = hit["canonical_key"]
                        if key not in seen:
                            seen.add(key)
                            pooled.append(hit)
            pooled.sort(
                key=lambda hit: rt.sort_key(
                    hit["score"],
                    hit["source_priority"],
                    hit["category"],
                    hit["canonical_key"],
                )
            )
            docs: list[dict] = []
            for hit in pooled[:max_docs]:
                text = (rt.doc_text(hit["canonical_key"]).get("text") or "")[:max_chars]
                if len(text) > remaining:
                    break
                docs.append(
                    {
                        "canonical_key": hit["canonical_key"],
                        "source": hit["canonical_key"].split(":", 1)[0],
                        "text": text,
                        "score": hit["score"],
                        "category": hit["category"],
                        "quarantined": False,
                    }
                )
                remaining -= len(text)
            rows.append(
                {"question_case_id": case_id, "item_id": item["item_id"], "docs": docs}
            )
    return rows


def build_bundles_for_eval(rows: list[dict]) -> dict[str, list[dict]]:
    bundles: dict[str, list[dict]] = {}
    for row in rows:
        bundles.setdefault(row["item_id"], []).extend(row["docs"])
    return bundles
