"""Task 4.1 dry-run harness.

Drives scripts.run_baziqa_retrieval_ablation.main with a stubbed
subprocess.run so we can verify the end-to-end report / rollback /
backfill plumbing on disk without spending any API budget.

Output:
  .tmp/dryrun_ablation/<config_id>_run<N>.jsonl  (8 fake rows each)
  .tmp/dryrun_ablation/rollback_stage1_dryrun.jsonl
  .tmp/dryrun_ablation/report.md
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_baziqa_retrieval_ablation as mod


# Each ablation config gets its own "true" accuracy on a fake 8-row holdout,
# emulating roughly what the real flash run might look like so we can sanity
# check report column widths and ordering.
_CONFIG_TRUE_ACC = {
    "bm25": 0.250,
    "structured": 0.375,
    "semantic": 0.500,
    "tfidf_vector": 0.500,
    "embedding_vector": 0.625,
}

_FAKE_ROWS = 8


def _fake_case_details(config_id: str, repeat: int):
    """Produce 8 fake case_details rows with `correct` flipped to match the
    config's target accuracy (plus a tiny per-repeat jitter)."""
    rng = random.Random(hash((config_id, repeat)) & 0xFFFFFFFF)
    base_acc = _CONFIG_TRUE_ACC.get(config_id, 0.4)
    jitter = (rng.random() - 0.5) * 0.10  # ±5 percentage points
    target_correct = max(0, min(_FAKE_ROWS, round((base_acc + jitter) * _FAKE_ROWS)))

    rows = []
    for i in range(_FAKE_ROWS):
        rows.append({
            "case_id": f"dryrun-{i+1}",
            "domain": "wealth",
            "question": "示例问题?",
            "expected_answer": "B",
            "predicted_answer": "B" if i < target_correct else "A",
            "raw_answer": "答案：B" if i < target_correct else "答案：A",
            "correct": i < target_correct,
            "evidence_coverage": 0.0,
            "safety_score": 0.0,
            "parser_source": "letter",
            "parser_valid": True,
            "rag_k": 2,
            "rag_trace": [{"rank": 1, "person_id": "fake-p", "facts": ["fake -> B"]}],
            "retrieved_answer_leak": False,
        })
    return rows


def fake_subprocess_run(cmd, check=True, env=None):
    cmd_list = list(cmd)
    details_path = None
    config_id = None
    for i, tok in enumerate(cmd_list):
        if tok == "--case-details-jsonl":
            details_path = cmd_list[i + 1]
        if tok == "--config-id":
            config_id = cmd_list[i + 1]
    assert details_path and config_id, ("missing --case-details-jsonl/--config-id in cmd", cmd_list)
    rng_key = (config_id, details_path)
    # Infer repeat from filename `<id>_run<N>.jsonl`.
    name = Path(details_path).name
    try:
        repeat = int(name.rsplit("_run", 1)[1].split(".")[0])
    except Exception:
        repeat = 1

    rows = _fake_case_details(config_id, repeat)
    Path(details_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(details_path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    class _R:
        returncode = 0
    return _R()


def main():
    out = PROJECT_ROOT / ".tmp" / "dryrun_ablation"
    out.mkdir(parents=True, exist_ok=True)
    rollback = out / "rollback_stage1_dryrun.jsonl"
    report = out / "report.md"
    # Wipe any prior rollback so the dry-run starts clean.
    if rollback.exists():
        rollback.unlink()

    argv = [
        "--run",
        "--configs", "bm25,structured,semantic,tfidf_vector,embedding_vector",
        "--model", "deepseek-v4-flash",
        "--repeats", "3",
        "--output-dir", str(out),
        "--rollback-jsonl", str(rollback),
        "--report", str(report),
    ]

    with patch.object(mod.subprocess, "run", fake_subprocess_run):
        rc = mod.main(argv)
    print(f"main() returned {rc}")
    print(f"report:   {report}")
    print(f"rollback: {rollback}")


if __name__ == "__main__":
    main()
