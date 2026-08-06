#!/usr/bin/env python3
"""Phase 6 6B1 smoke gate — single-slice precondition check (v9 protocol).

协议：
  - 只执行 schedule[0]（某一原子切片，13 题）
  - 该 13 题计入 720 预算（由上层 orchestrator 管理账本）
  - 独立运行时使用独立账本检查
  - hard cap = 14 (13 + 1 retry)
  - parser rate 阈值: 0.95
  - 五状态恢复机制

用法:
  # 独立 smoke（不连接 orchestrator 账本）
  python scripts/phase6_6b1_smoke.py --output-dir benchmark/outputs/phase6_6b1 \
    --provider deepseek --model deepseek-chat

  # 在 orchestrator 内部调用时，orchestrator 直接执行 schedule[0]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

# ---- constants ----

REASONED_PROFILE = "baziqa_xjz_reasoned"
CHART_SCHEMA = "legacy_v0"
FROZEN_DATE = "2026-07-17"
ENV_CLEANUP = ["BAZI_RAG", "BAZI_RAG_CORPUS", "BAZI_FEWSHOT_FILE", "BAZI_APB_BLOCK"]
HARD_CAP_MAP = {13: 14, 14: 16}

SMOKE_SLICE_SIZE = 13
SMOKE_HARD_CAP = 14                        # size + 1 retry (frozen)
PARSER_RATE_THRESHOLD = 0.95

# ---- helpers ----

def load_jsonl(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def atomic_write_json(path: str, data) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_smoke_slice(schedule_path: str) -> dict | None:
    """Load schedule[0] from orchestrator-generated schedule.json."""
    if not os.path.exists(schedule_path):
        print(json.dumps({
            "status": "SCHEDULE_NOT_FOUND",
            "reason": f"schedule.json 不存在于 {schedule_path}，先运行 orchestrator --dry-run",
        }, ensure_ascii=False))
        return None
    with open(schedule_path, "r", encoding="utf-8") as f:
        schedule = json.load(f)
    slices = schedule.get("slices", [])
    if not slices:
        print(json.dumps({
            "status": "SCHEDULE_EMPTY", "reason": "schedule.json 中无切片",
        }, ensure_ascii=False))
        return None
    return slices[0]


def _five_state_resolve(sl: dict) -> str:
    """Determine smoke resume state.

    Returns one of: "fresh", "completed", "resume", "blocked_manifest", "blocked_other"
    """
    detail_path = sl["detail_path"]
    manifest_path = sl.get("manifest_path",
                           os.path.splitext(detail_path)[0] + ".manifest.json")
    events_path = sl.get("events_path",
                         os.path.splitext(detail_path)[0] + ".events.jsonl")

    detail_exists = os.path.exists(detail_path)
    manifest_exists = os.path.exists(manifest_path)
    events_exists = os.path.exists(events_path)

    if not detail_exists and not manifest_exists and not events_exists:
        return "fresh"

    if detail_exists and manifest_exists:
        # Check if all SMOKE_SLICE_SIZE cases have terminal states
        rows = load_jsonl(detail_path)
        terminal_count = sum(
            1 for r in rows
            if r.get("terminal_state") in ("parsed", "invalid",
                                           "unresolved", "call_failed")
        )
        if terminal_count >= SMOKE_SLICE_SIZE:
            return "completed"
        return "resume"

    if manifest_exists and not detail_exists:
        return "resume"

    # Manifest mismatch or other blocked state
    if detail_exists and not manifest_exists:
        return "blocked_other"

    return "blocked_other"


def smoke_gate(sl: dict, provider: str, model: str) -> dict:
    """Run single-slice smoke with 5-state resume.

    Returns {status, parser_rate, calls_attempted, ...}.
    """
    state = _five_state_resolve(sl)
    print(f"[smoke] state={state} slice={sl['slice_id']}")

    if state == "completed":
        # Full re-verification (same checks as fresh path)
        # Require events file for call auditing
        events_path = sl.get("events_path", "")
        if not events_path or not os.path.exists(events_path):
            return _smoke_result(sl, "BLOCKED_SMOKE", 0, 0)

        rows = load_jsonl(sl["detail_path"])
        if len(rows) < sl["size"]:
            return _smoke_result(sl, "INCOMPLETE", 0, 0)

        # attempt-key integrity
        detail_keys = [tuple(r.get("attempt_key", [])) for r in rows]
        completed_keys = set(detail_keys)
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        expected_keys = set()
        for case_id in sl["case_ids"]:
            ek = (dataset_id, REASONED_PROFILE, sl["arm"], "main",
                  provider, model, str(case_id), sl["repeat"], 0, "p0")
            expected_keys.add(ek)

        if len(detail_keys) != len(expected_keys):
            return _smoke_result(sl, "INCOMPLETE", 0, 0)
        if len(completed_keys) != len(detail_keys):
            return _smoke_result(sl, "DUPLICATE_KEY", 0, 0)
        if completed_keys != expected_keys:
            return _smoke_result(sl, "KEY_MISMATCH", 0, 0)

        # manifest verification (full, all RESUME_MANIFEST_FIELDS)
        manifest_path = sl.get("manifest_path",
                               os.path.splitext(sl["detail_path"])[0] + ".manifest.json")
        if os.path.exists(manifest_path):
            # Import full manifest verifier from orchestrator
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
            from scripts.phase6_6b1_orchestrator import verify_slice_manifest
            ok, diff = verify_slice_manifest(sl, provider, model)
            if not ok:
                return _smoke_result(sl, "MANIFEST_MISMATCH", 0, 0)
        else:
            return _smoke_result(sl, "MANIFEST_MISMATCH", 0, 0)

        # parser rate
        parsed_count = sum(1 for r in rows if r.get("terminal_state") == "parsed")
        parser_rate = parsed_count / len(rows) if rows else 0

        # Validate events: parseable + count within [scheduled, hard_cap]
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from scripts.phase6_6b1_orchestrator import _validate_events
        ev_ok, calls_attempted, ev_reason = _validate_events(
            sl.get("events_path", ""), sl["size"],
            HARD_CAP_MAP.get(sl["size"], sl.get("hard_cap", SMOKE_HARD_CAP)))
        if not ev_ok:
            return _smoke_result(sl, "BLOCKED_SMOKE", parser_rate, calls_attempted)

        if parser_rate < PARSER_RATE_THRESHOLD:
            return _smoke_result(sl, "PARSER_RATE_TOO_LOW", parser_rate, calls_attempted)

        return _smoke_result(sl, "OK", parser_rate, calls_attempted)

    if state == "blocked_other":
        print(json.dumps({
            "status": "BLOCKED_SMOKE", "slice_id": sl["slice_id"],
            "reason": "产物状态异常：detail/manifest/events 不一致",
        }, ensure_ascii=False))
        return _smoke_result(sl, "BLOCKED_SMOKE", 0, 0)

    # Write case_ids file
    slice_dir = Path(sl["output_dir"])
    os.makedirs(str(slice_dir), exist_ok=True)
    case_ids_path = str(slice_dir / f"case_ids_{sl['slice_id']}.json")
    atomic_write_json(case_ids_path, sl["case_ids"])

    cmd = [
        sys.executable, "-u",
        os.path.join("benchmark", "runners", "run_benchmark.py"),
        "--dataset", sl["dataset"],
        "--profile", REASONED_PROFILE,
        "--chart-schema-version", CHART_SCHEMA,
        "--arm", sl["arm"],
        "--ziwei-arm", sl["ziwei_arm"],
        "--attempt-stage", "main",
        "--repeat-idx", str(sl["repeat"]),
        "--case-details-jsonl", sl["detail_path"],
        "--case-ids-file", case_ids_path,
        "--provider", provider,
        "--model", model,
        "--method", "direct_choice",
        "--model-runner",
        "--n-samples", "1",
        "--temperature", "0",
        "--scheduled-calls", str(sl["size"]),
        "--hard-cap", str(HARD_CAP_MAP.get(sl["size"], sl["hard_cap"])),
        "--output-dir", sl["output_dir"],
        "--as-of-date", FROZEN_DATE,
    ]

    if state in ("resume",):
        cmd.append("--resume")
        print(f"      [resume] continuing from existing artifacts")

    print(f"      cmd: {' '.join(cmd)}")
    clean_env = dict(os.environ)
    for var in ENV_CLEANUP:
        clean_env.pop(var, None)
    result = subprocess.run(cmd, capture_output=False, text=True, env=clean_env)

    if result.returncode not in (0,):
        print(f"[smoke] runner exited with {result.returncode}")
        return _smoke_result(sl, "RUNNER_FAILED", 0, 0)

    # Check results — detail completeness
    rows = load_jsonl(sl["detail_path"])
    if len(rows) < sl["size"]:
        print(f"[smoke] incomplete: {len(rows)}/{sl['size']} rows")
        return _smoke_result(sl, "INCOMPLETE", 0, 0)

    parsed_count = sum(1 for r in rows if r.get("terminal_state") == "parsed")
    parser_rate = parsed_count / len(rows) if rows else 0

    # P0-1: validate events (not just count) - reject corrupt/empty/under-count events
    # fresh/resume must use same strict validation as completed branch
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from scripts.phase6_6b1_orchestrator import _validate_events
    ev_ok, calls_attempted, ev_reason = _validate_events(
        sl.get("events_path", ""), sl["size"],
        HARD_CAP_MAP.get(sl["size"], sl.get("hard_cap", SMOKE_HARD_CAP)))

    # ---- attempt-key integrity check ----
    # Use row["attempt_key"] directly (runner writes it as a list)
    actual_keys: set = set()
    key_counts: dict = {}
    for row in rows:
        ak = tuple(row.get("attempt_key", []))
        if not ak:
            continue
        actual_keys.add(ak)
        key_counts[ak] = key_counts.get(ak, 0) + 1

    dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
    expected_keys: set = set()
    for case_id in sl["case_ids"]:
        ek = (dataset_id, REASONED_PROFILE, sl["arm"], "main",
              provider, model, str(case_id), sl["repeat"], 0, "p0")
        expected_keys.add(ek)

    duplicates = {k: v for k, v in key_counts.items() if v > 1}
    missing_keys = expected_keys - actual_keys
    extra_keys = actual_keys - expected_keys
    key_ok = (len(actual_keys) == len(expected_keys)
              and len(duplicates) == 0
              and len(missing_keys) == 0
              and len(extra_keys) == 0)

    # ---- manifest matching (P0-1: full verification, not just 3 fields) ----
    # Reuse verify_slice_manifest from orchestrator for full-field parity
    # with the completed branch (dataset_sha, code_sha, prompt, date, budget, etc.)
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from scripts.phase6_6b1_orchestrator import verify_slice_manifest
    manifest_ok = True
    if os.path.exists(sl.get("manifest_path", "")):
        ok, diff = verify_slice_manifest(sl, provider, model)
        if not ok:
            manifest_ok = False
            print(f"[smoke] manifest mismatch (full verify): {json.dumps(diff, ensure_ascii=False)}")
    else:
        manifest_ok = False
        print(f"[smoke] manifest missing: {sl.get('manifest_path')}")

    if not key_ok:
        print(json.dumps({
            "smoke_integrity": {
                "expected": len(expected_keys), "actual": len(actual_keys),
                "duplicates": len(duplicates),
                "missing": len(missing_keys),
                "extra": len(extra_keys),
                "missing_sample": list(missing_keys)[:3],
                "extra_sample": list(extra_keys)[:3],
            },
        }, ensure_ascii=False))
        status = "KEY_INTEGRITY_FAILED"
    elif not manifest_ok:
        status = "MANIFEST_MISMATCH"
    elif not ev_ok:
        # P0-1: reject corrupt/missing/under-count events (was: empty events -> OK)
        print(json.dumps({
            "events_validation": {"reason": ev_reason, "calls_found": calls_attempted},
        }, ensure_ascii=False))
        status = "BLOCKED_SMOKE"
    elif parser_rate < PARSER_RATE_THRESHOLD:
        status = "PARSER_RATE_TOO_LOW"
    else:
        status = "OK"

    return _smoke_result(sl, status, parser_rate, calls_attempted)


def _count_call_attempts(events_path: str) -> int:
    if not events_path or not os.path.exists(events_path):
        return 0
    count = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("kind") == "call_attempt":
                    count += 1
            except json.JSONDecodeError:
                pass
    return count


def _smoke_result(sl: dict, status: str, parser_rate: float,
                  calls_attempted: int) -> dict:
    return {
        "slice_id": sl["slice_id"],
        "status": status,
        "parser_rate": round(parser_rate, 4),
        "calls_attempted": calls_attempted,
        "hard_cap": SMOKE_HARD_CAP,
        "size": sl["size"],
        "arm": sl["arm"],
        "year": sl["year"],
        "repeat": sl["repeat"],
        "pass": status == "OK",
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 6 6B1 smoke gate")
    parser.add_argument("--output-dir", default="benchmark/outputs/phase6_6b1",
                        help="产物输出根目录（包含 schedule.json）")
    parser.add_argument("--provider", default="deepseek", help="模型 provider")
    parser.add_argument("--model", default="deepseek-chat", help="模型名")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅检查 schedule 和产物状态，不调 API")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    schedule_path = str(output_dir / "schedule.json")

    sl = load_smoke_slice(schedule_path)
    if sl is None:
        return 2

    # Verify smoke slice has correct size
    if sl["size"] not in (SMOKE_SLICE_SIZE,):
        print(json.dumps({
            "status": "SMOKE_SLICE_SIZE_MISMATCH",
            "expected": SMOKE_SLICE_SIZE,
            "actual": sl["size"],
        }, ensure_ascii=False))
        return 2

    if args.dry_run:
        state = _five_state_resolve(sl)
        print(json.dumps({
            "status": "DRY_RUN", "smoke_slice": sl["slice_id"],
            "size": sl["size"], "arm": sl["arm"], "year": sl["year"],
            "resume_state": state,
            "detail_path": sl["detail_path"],
        }, indent=2, ensure_ascii=False))
        return 0

    result = smoke_gate(sl, args.provider, args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
