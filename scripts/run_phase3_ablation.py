"""Phase 3 multi-permutation ablation orchestrator.

Drives the A1/A3/A4 on-agg + off-3 experiment matrix defined in
``docs/superpowers/specs/2026-07-02-phase3-anti-position-bias-design.md``.

This script is an ORCHESTRATOR: it generates runner commands, pre-permuted
dataset files (using the shared cyclic-shift permutation plan), budget
estimates, and a dry-run plan.  It does NOT call the model itself --- that
happens via ``benchmark/runners/run_benchmark.py`` subprocess invocations
produced from the generated command list.

**Critical**: on-3 mode does NOT pass ``--shuffle-options`` / ``--shuffle-seed``
to the runner.  Instead, the orchestrator writes per-permutation dataset files
where options are already placed in the correct fixed-cyclic-shift order.
This ensures every arm / mode / stage shares the exact same permutation plan
(design §4).

Modes:
  --dry-run        Emit the command plan + permutation plan + budget without
                   invoking any subprocess.
  --emit-commands  Print one runner command per line (for shell scripting).
  --plan-perms     Write the shared permutation plan JSONL to --perms-out.

Budget hard caps (per design §12):
  link8=174, dev20=432, MingLi20=72, formal40=288, formal20=144.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmark.phase3 import (
    build_permutation_plan,
    permute_case_by_plan,
)

STAGES = {
    "link8": {"cases": 8, "hard_call_cap": 174, "retry_budget": 30, "primary": 144},
    "dev20": {"cases": 20, "hard_call_cap": 432, "retry_budget": 72, "primary": 360},
    "MingLi20": {"cases": 20, "hard_call_cap": 72, "retry_budget": 12, "primary": 60},
    "formal40": {"cases": 40, "hard_call_cap": 288, "retry_budget": 48, "primary": 240},
    "formal20": {"cases": 20, "hard_call_cap": 144, "retry_budget": 24, "primary": 120},
}

ARMS = ["A1", "A3", "A4"]


def _arm_config(arm: str, fewshot_file: str) -> dict[str, Any]:
    """Return prompt/fewshot config for an arm."""
    if arm == "A1":
        return {"prompt": "base", "fewshot": False, "apb": False}
    if arm == "A3":
        return {"prompt": "base+APB", "fewshot": False, "apb": True}
    if arm == "A4":
        return {"prompt": "base+APB", "fewshot": True, "apb": True, "fewshot_file": fewshot_file}
    raise ValueError(f"unknown arm: {arm}")


def write_permuted_datasets(
    source_dataset: str,
    output_dir: str,
    stage: str,
    n_perms: int = 3,
) -> dict[int, str]:
    """Write per-permutation JSONL files using cyclic-shift.

    Returns a dict mapping ``perm_idx -> dataset_path`` so that on-3
    commands can point to the correctly permuted file.  Every arm and
    stage reuses the same files (shared permutation plan).
    """
    max_cases = STAGES[stage]["cases"]
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read all cases
    cases: list[dict[str, Any]] = []
    with Path(source_dataset).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    cases = cases[:max_cases]

    perm_files: dict[int, str] = {}
    for shift in range(n_perms):
        out_path = out_dir / f"{stage}_perm_s{shift}.jsonl"
        with out_path.open("w", encoding="utf-8") as fh:
            for case in cases:
                permuted = permute_case_by_plan(case, shift=shift)
                fh.write(json.dumps(permuted, ensure_ascii=False) + "\n")
        perm_files[shift] = str(out_path)

    return perm_files


def build_command_list(
    stage: str,
    dataset: str,
    corpus: str,
    model: str,
    fewshot_file: str,
    output_dir: str,
    n_perms: int = 3,
    method: str = "structured_reasoning",
    force_no_fewshot: bool = False,
    arms: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Build the full (arm, mode, permutation) command list for a stage.

    For dev20/link8: 3 arms x 2 modes (off-3, on-3) x 3 perms.
    For formal: only frozen candidate + its off-control (handled by caller
    passing a single arm).
    """
    # Write pre-permuted dataset files (shared across all arms)
    perm_files = write_permuted_datasets(dataset, output_dir, stage, n_perms=n_perms)

    commands: list[dict[str, Any]] = []
    for arm in (arms or ARMS):
        ac = _arm_config(arm, fewshot_file)
        if force_no_fewshot:
            ac = {**ac, "fewshot": False}
        for mode in ("off-3", "on-3"):
            for perm_idx in range(n_perms):
                cmd = _build_single_command(
                    arm=arm,
                    ac=ac,
                    mode=mode,
                    perm_idx=perm_idx,
                    dataset=str(perm_files[perm_idx]) if mode == "on-3" else dataset,
                    corpus=corpus,
                    model=model,
                    output_dir=output_dir,
                    stage=stage,
                    method=method,
                )
                commands.append(cmd)
    return commands


def _build_single_command(
    arm: str,
    ac: dict[str, Any],
    mode: str,
    perm_idx: int,
    dataset: str,
    corpus: str,
    model: str,
    output_dir: str,
    stage: str,
    method: str = "structured_reasoning",
) -> dict[str, Any]:
    """Build a single run_benchmark.py invocation as a command list + metadata.

    on-3 runs use pre-permuted datasets --- NO ``--shuffle-options`` or
    ``--shuffle-seed``.  The cyclic-shift permutation is already encoded
    in the input file.
    """
    details = Path(output_dir) / f"{stage}_{arm}_{mode}_p{perm_idx}.jsonl"
    cmd = [
        sys.executable, "benchmark/runners/run_benchmark.py",
        "--dataset", dataset,
        "--model-runner",
        "--provider", "deepseek",
        "--model", model,
        "--max-cases", str(STAGES[stage]["cases"]),
        "--method", method,
        "--rag",
        "--rag-k", "2",
        "--rag-corpus", corpus,
        "--retrieval-mode", "option_grounded",
        "--option-evidence-k", "2",
        "--case-details-jsonl", str(details),
        "--config-id", f"{stage}_{arm}_{mode}_p{perm_idx}",
    ]
    # NO --shuffle-options / --shuffle-seed: permutation is in the data file
    if ac.get("apb"):
        cmd.append("--apb-block")
    if ac.get("fewshot") and ac.get("fewshot_file"):
        cmd.extend(["--fewshot-file", ac["fewshot_file"]])
    if method == "two_stage_reasoning":
        stage1_cache = Path(output_dir) / f"{stage}_{arm}_phase4_stage1_cache.json"
        cmd.extend(["--phase4-stage1-cache", str(stage1_cache)])
    return {
        "arm": arm,
        "mode": mode,
        "perm_idx": perm_idx,
        "command": cmd,
        "details_path": str(details),
        "config": ac,
    }


def estimate_budget(stage: str, method: str = "structured_reasoning") -> dict[str, int]:
    cfg = STAGES[stage]
    if method == "two_stage_reasoning":
        return {
            "planned_primary_calls": cfg["primary"] + cfg["cases"],
            "retry_budget": int((cfg["primary"] + cfg["cases"]) * 0.2),
            "hard_call_cap": int((cfg["primary"] + cfg["cases"]) * 1.2),
        }
    return {
        "planned_primary_calls": cfg["primary"],
        "retry_budget": cfg["retry_budget"],
        "hard_call_cap": cfg["hard_call_cap"],
    }


def emit_permutation_plan(cases_path: str, out_path: str) -> None:
    """Write the shared permutation plan for all cases in cases_path.

    Uses option body text (strip label prefix) as identity rather than
    requiring an ``id`` field.
    """
    import json as _json

    from benchmark.phase3 import _strip_option_prefix

    rows = []
    with Path(cases_path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            case = _json.loads(line)
            options = case.get("options") or []
            if len(options) != 4:
                continue
            # Use stripped option body as identity
            option_ids = [_strip_option_prefix(o) for o in options]
            plan = build_permutation_plan(option_ids)
            rows.append({"case_id": case.get("case_id"), "option_ids": option_ids, "permutations": plan})
    with Path(out_path).open("w", encoding="utf-8") as f:
        f.writelines(_json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3 multi-permutation ablation orchestrator.")
    parser.add_argument("--stage", default="dev20", choices=list(STAGES.keys()))
    parser.add_argument("--dataset", default="benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl")
    parser.add_argument("--corpus", default="benchmark/datasets/baziqa_contest8_2021_2024_corpus_enriched.jsonl")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--fewshot-file", default="benchmark/fewshot/anti_position_bias_v1.jsonl")
    parser.add_argument("--output-dir", default=".tmp/phase3_ablation")
    parser.add_argument("--n-perms", type=int, default=3)
    parser.add_argument("--method", default="structured_reasoning",
                        help="Reasoning method passed to run_benchmark.py (Phase 4: two_stage_reasoning)")
    parser.add_argument("--arms", default=",".join(ARMS),
                        help="Comma-separated arms to run (default: all). Phase 4 uses --arms A4")
    parser.add_argument("--no-fewshot", action="store_true",
                        help="Disable fewshot injection (Phase 4 constraint: no fewshot)")
    parser.add_argument("--dry-run", action="store_true", help="Emit plan without invoking subprocess")
    parser.add_argument("--emit-commands", action="store_true", help="Print one command per line")
    parser.add_argument("--execute", action="store_true", help="Execute commands via subprocess (no shell)")
    parser.add_argument("--plan-perms", action="store_true", help="Write permutation plan to --perms-out")
    parser.add_argument("--perms-out", default=".tmp/phase3_ablation/permutation_plan.jsonl")
    args = parser.parse_args(argv)

    if args.execute and args.dry_run:
        print("ERROR: --execute and --dry-run are mutually exclusive.", file=sys.stderr)
        return 1
    if args.execute and args.emit_commands:
        print("ERROR: --execute and --emit-commands are mutually exclusive.", file=sys.stderr)
        return 1

    if args.plan_perms:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)
        emit_permutation_plan(args.dataset, args.perms_out)
        print(f"permutation plan written to {args.perms_out}")
        return 0

    selected_arms = [a.strip() for a in args.arms.split(",") if a.strip()] or None
    commands = build_command_list(
        stage=args.stage,
        dataset=args.dataset,
        corpus=args.corpus,
        model=args.model,
        fewshot_file=args.fewshot_file,
        output_dir=args.output_dir,
        n_perms=args.n_perms,
        method=args.method,
        force_no_fewshot=args.no_fewshot,
        arms=selected_arms,
    )
    budget = estimate_budget(args.stage, method=args.method)

    if args.emit_commands:
        for c in commands:
            print(shlex.join(c["command"]))
        return 0

    if args.execute:
        from datetime import datetime
        n_total = len(commands)
        print(f"=== Phase 3 {args.stage} EXECUTE ({n_total} commands) ===")
        success = 0
        failures: list[dict[str, Any]] = []
        t_start = datetime.now()
        for i, c in enumerate(commands):
            label = f"[{i+1}/{n_total}] {c['arm']} {c['mode']} p{c['perm_idx']}"
            print(f"{label} ... ", end="", flush=True)
            t0 = datetime.now()
            try:
                # c["command"] is a list; pass directly to subprocess (no shell)
                result = subprocess.run(
                    c["command"],
                    capture_output=True,
                    text=True,
                    cwd=str(_PROJECT_ROOT),
                    timeout=3600,  # 60 min per command
                )
                elapsed = (datetime.now() - t0).total_seconds()
                if result.returncode == 0:
                    print(f"OK ({elapsed:.0f}s)")
                    success += 1
                else:
                    print(f"FAIL (rc={result.returncode}, {elapsed:.0f}s)")
                    failures.append({
                        "label": label,
                        "rc": result.returncode,
                        "stderr": result.stderr[-500:] if result.stderr else "",
                        "details_path": c["details_path"],
                    })
            except subprocess.TimeoutExpired:
                print("TIMEOUT (>600s)")
                failures.append({"label": label, "rc": -1, "stderr": "timeout", "details_path": c["details_path"]})
            except Exception as exc:
                print(f"ERROR: {exc}")
                failures.append({"label": label, "rc": -1, "stderr": str(exc), "details_path": c["details_path"]})

        total_elapsed = (datetime.now() - t_start).total_seconds()
        print(f"\n=== {args.stage} DONE: {success}/{n_total} OK in {total_elapsed:.0f}s ===")
        if failures:
            print(f"FAILURES ({len(failures)}):")
            for f in failures:
                print(f"  {f['label']}: rc={f['rc']}")
                if f["stderr"]:
                    print(f"    {f['stderr'][:200]}")
            return 2
        return 0
    print(f"dataset: {args.dataset}")
    print(f"corpus: {args.corpus}")
    print(f"model: {args.model}")
    print(f"arms: {selected_arms or ARMS}")
    print("modes: off-3, on-3")
    print(f"perms per case: {args.n_perms}")
    print(f"total commands: {len(commands)}")
    print(f"budget: {budget}")
    print()
    for c in commands:
        print(f"  [{c['arm']} {c['mode']} p{c['perm_idx']}] -> {c['details_path']}")

    if not args.dry_run:
        print("\nERROR: pass --dry-run to confirm plan; online execution requires Task 16 gate.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
