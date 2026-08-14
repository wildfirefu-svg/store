"""Run the one-shot Phase 9A silver retrieval evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
sys.path.insert(0, str(P9))
sys.path.insert(0, str(REPO / "docs" / "phase8" / "marriage-capability"))

import evaluate as evaluation
import phase9a_manifest as manifest
import qc_gate


def _write_tmp(root: Path, name: str, payload: object) -> Path:
    tmp = root / f".{name}.tmp"
    if name.endswith(".jsonl"):
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            for row in payload:
                handle.write(
                    json.dumps(
                        row,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
    else:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return tmp


def _atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def _publish(root: Path, artifacts: dict[str, Path], verdict: str) -> None:
    """Publish artifacts, then atomically publish the completion receipt last."""
    try:
        for name in artifacts:
            if (root / name).exists():
                sys.exit(f"FAIL: {name} already exists - one-shot violated")
        if (root / "RECEIPT.json").exists():
            sys.exit("FAIL: RECEIPT.json already exists - one-shot violated")

        for name, tmp in artifacts.items():
            if name.endswith(".jsonl"):
                for line in tmp.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        json.loads(line)
            else:
                json.loads(tmp.read_text(encoding="utf-8"))

        receipt_artifacts: dict[str, dict] = {}
        for name, tmp in artifacts.items():
            raw = tmp.read_bytes()
            receipt_artifacts[name] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "strategy": "raw_bytes",
                "size": len(raw),
            }
        receipt = {
            "schema_version": "1.0",
            "verdict": verdict,
            "artifacts": receipt_artifacts,
            "published_at": "sealed",
        }
        for name, tmp in artifacts.items():
            os.replace(tmp, root / name)
        _atomic_json(root / "RECEIPT.json", receipt)
    except BaseException:
        for tmp in artifacts.values():
            tmp.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(P9))
    args = parser.parse_args()
    root = Path(args.root)

    manifest.verify_frozen(
        root / "manifest.json",
        [
            "evaluate_py",
            "qc_gate_py_v2",
            "retriever_py",
            "run_eval_py_v3",
            "strategy_store_py",
            "silver_relevance_judgment",
            "item_query_map",
            "truncation_config",
            "ranking_config",
            "qc_config",
            "qc_sample_list",
            "qc_human_review",
            "strategy_outputs",
        ],
    )
    qc_config = json.loads((root / "qc_config.json").read_text(encoding="utf-8"))
    truncation_config = json.loads(
        (root / "truncation_config.json").read_text(encoding="utf-8")
    )
    state = qc_gate.qc_state(
        root / "qc_human_review.jsonl", root / "qc_sample_list.json"
    )
    if state != "REVIEWED":
        sys.exit(f"HUMAN_QC_REQUIRED: state={state}")

    reviews = qc_gate.load_human_review(root / "qc_human_review.jsonl")
    qc_gate.validate_review_coverage(
        json.loads((root / "qc_sample_list.json").read_text(encoding="utf-8"))[
            "sample_list"
        ],
        reviews,
    )
    qc_result = qc_gate.check_disagreement(
        reviews,
        root / "silver_relevance_judgment.jsonl",
        qc_config["max_disagreement_rate"],
    )

    item_map = json.loads((root / "item_query_map.json").read_text(encoding="utf-8"))[
        "items"
    ]
    items = [item["item_id"] for item in item_map]
    if len(items) != 112:
        sys.exit(f"FAIL: frozen item count {len(items)} != 112")
    judgment = [
        json.loads(line)
        for line in (root / "silver_relevance_judgment.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    if qc_result["verdict"] == "SILVER_RETRIEVAL_NOT_READY":
        payload = {
            "schema_version": "1.0",
            "verdict": "SILVER_RETRIEVAL_NOT_READY",
            "metrics": "not_computed",
            "qc_state": "QC_FAIL",
            "qc_result": qc_result,
            "note": "QC disagreement exceeded the frozen gate; metrics were not computed.",
        }
        _publish(
            root,
            {
                "qc_result.json": _write_tmp(root, "qc_result.json", qc_result),
                "retrieval_eval.json": _write_tmp(
                    root, "retrieval_eval.json", payload
                ),
            },
            payload["verdict"],
        )
        print(
            "QC_FAIL chain published: SILVER_RETRIEVAL_NOT_READY "
            "(metrics=not_computed)"
        )
        return

    per_strategy: dict[str, dict] = {}
    strategy_outputs_path = root / "strategy_outputs.jsonl"
    for name in ("s1", "s2", "s3", "s4", "s5"):
        rows = evaluation.build_bundle(
            item_map,
            truncation_config,
            strategies=(name,),
            strategy_outputs_path=strategy_outputs_path,
        )
        per_strategy[name] = evaluation.compute_metrics(
            judgment, items, evaluation.build_bundles_for_eval(rows)
        )

    rows = evaluation.build_bundle(
        item_map,
        truncation_config,
        strategies=("s1", "s2", "s3", "s4", "s5"),
        strategy_outputs_path=strategy_outputs_path,
    )
    metrics = evaluation.compute_metrics(
        judgment, items, evaluation.build_bundles_for_eval(rows)
    )
    payload = {
        "schema_version": "1.0",
        "verdict": evaluation.decide(metrics),
        "metrics": metrics,
        "gates": evaluation.GATES,
        "qc_state": "REVIEWED",
        "qc_result": qc_result,
        "note": "Silver result is limited to engineering reproducibility, not semantic correctness.",
    }
    _publish(
        root,
        {
            "qc_result.json": _write_tmp(root, "qc_result.json", qc_result),
            "retrieval_bundle_dev.jsonl": _write_tmp(
                root, "retrieval_bundle_dev.jsonl", rows
            ),
            "per_strategy_eval.json": _write_tmp(
                root,
                "per_strategy_eval.json",
                {
                    "schema_version": "1.0",
                    "per_strategy": per_strategy,
                    "gates": evaluation.GATES,
                },
            ),
            "retrieval_eval.json": _write_tmp(root, "retrieval_eval.json", payload),
        },
        payload["verdict"],
    )
    print(
        f"one-shot eval published: verdict={payload['verdict']}, "
        f"macro_recall={metrics['macro_weighted_recall']:.3f}, "
        f"noise={metrics['macro_bundle_noise']:.3f}"
    )


if __name__ == "__main__":
    main()
