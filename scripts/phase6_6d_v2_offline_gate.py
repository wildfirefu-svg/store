#!/usr/bin/env python3
"""Phase 6 6D-v2 offline gate - authoritative phase1 receipt generator.

Regenerates the temporal routed manifest via the v1 offline gate audit and
writes the AUTHORITATIVE ``phase1_receipt.json`` for 6D-v2 (overwrites the
intermediate receipt produced by the v1 gate). The receipt keeps every field
validated by ``_validate_phase1_receipt`` (status / n_routed /
temporal_routed_cases_sha256 / dataset_sha256_by_year / dataset_set_sha256,
with n_routed == manifest entries) and appends v2 check fields:

- ``on_limited_no_relations``: the on_limited injection path emits no
  地支关系/天干关系 text for any routed case (6D 方案 A limited injection)
- ``arm_fail_closed_ok``: ``b1a_time_on_limited`` maps to ``ziwei_arm``
  ``none`` in the fail-closed ``_REASONED_ARM_MAP``
- ``off_reuse_precheck_ok``: the 6D v1 off-data reuse precheck
  (``_verify_off_reuse``) passes against the real v1 archive/runs workspace

``status`` is PASS only when ``n_routed`` >= threshold AND all v2 checks
pass; the manifest is (re)written only on PASS.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.phase6_6d_offline_gate import (
    _BLOCK_THRESHOLD,
    generate_routed_manifest,
    write_manifest,
    write_receipt,
)
from scripts.phase6_6d_v2_orchestrator import V1_ARCHIVE_DIR, V1_RUNS_DIR

_DEFAULT_OUTPUT = "docs/phase6/6d-v2/temporal_routed_cases.json"
_DEFAULT_DATASETS_DIR = "benchmark/datasets"
_RECEIPT_FILENAME = "phase1_receipt.json"
_DATASET_FILENAME = "baziqa_contest8_{year}_holdout_enriched.jsonl"


def _load_cases_by_id(year: str, datasets_dir: str) -> dict:
    path = os.path.join(datasets_dir, _DATASET_FILENAME.format(year=year))
    cases = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                case = json.loads(line)
                cases[case.get("case_id", "")] = case
    return cases


def check_on_limited_no_relations(entries: list, datasets_dir: str) -> bool:
    """Render every routed case through the real on_limited injection path
    and require that no 地支关系/天干关系 text is emitted."""
    from benchmark.formatters.chart_context import render_reasoned_context

    cache: dict = {}
    for e in entries:
        year = e["year"]
        if year not in cache:
            cache[year] = _load_cases_by_id(year, datasets_dir)
        case = cache[year].get(e["case_id"])
        if case is None:
            return False
        text = render_reasoned_context(
            case, "legacy_v0", "none", "on_limited",
            route_state=e["route_state"],
            frozen_target_years=tuple(e["target_years"]))
        if "地支关系" in text or "天干关系" in text:
            return False
    return True


def check_arm_fail_closed() -> bool:
    """b1a_time_on_limited must map to ziwei_arm "none" (fail-closed)."""
    from benchmark.runners.run_benchmark import _REASONED_ARM_MAP

    return _REASONED_ARM_MAP.get("b1a_time_on_limited") == "none"


def check_off_reuse_precheck(receipt: dict, v1_archive_dir: str,
                             v1_runs_dir: str) -> bool:
    """6D v1 off data reuse precheck against the real v1 archive/runs."""
    from scripts.phase6_6d_v2_orchestrator import (
        FROZEN_METHOD,
        FROZEN_MODEL,
        FROZEN_PROFILE,
        FROZEN_PROVIDER,
        FROZEN_TEMPERATURE,
        FROZEN_THINKING_MODE,
        _verify_off_reuse,
    )

    v2_frozen = {
        "dataset_sha256_by_year": receipt["dataset_sha256_by_year"],
        "temporal_routed_cases_sha256":
            receipt["temporal_routed_cases_sha256"],
        "dataset_set_sha256": receipt["dataset_set_sha256"],
        "provider": FROZEN_PROVIDER,
        "model": FROZEN_MODEL,
        "thinking_mode": FROZEN_THINKING_MODE,
        "temperature": FROZEN_TEMPERATURE,
        "profile": FROZEN_PROFILE,
        "method": FROZEN_METHOD,
    }
    try:
        off = _verify_off_reuse(v1_archive_dir, v1_runs_dir, v2_frozen)
    except SystemExit:
        return False
    return len(off) == 93


def run_v2_checks(entries: list, receipt: dict, datasets_dir: str,
                  v1_archive_dir: str, v1_runs_dir: str) -> dict:
    """Run all v2 checks; any internal error fails that check (fail-closed)."""
    checks = {}
    for name, fn in (
        ("on_limited_no_relations",
         lambda: check_on_limited_no_relations(entries, datasets_dir)),
        ("arm_fail_closed_ok", check_arm_fail_closed),
        ("off_reuse_precheck_ok",
         lambda: check_off_reuse_precheck(receipt, v1_archive_dir,
                                          v1_runs_dir)),
    ):
        try:
            checks[name] = bool(fn())
        except Exception:
            checks[name] = False
    return checks


def build_receipt(years: list, datasets_dir: str, v1_archive_dir: str,
                  v1_runs_dir: str) -> tuple[list, dict]:
    """Audit datasets and build the authoritative v2 phase1 receipt."""
    entries, _sha_by_year, receipt = generate_routed_manifest(
        years, datasets_dir)
    checks = run_v2_checks(entries, receipt, datasets_dir,
                           v1_archive_dir, v1_runs_dir)
    receipt.update(checks)
    receipt["gate"] = "6d-v2"
    ok = receipt["n_routed"] >= _BLOCK_THRESHOLD and all(checks.values())
    receipt["status"] = "PASS" if ok else "BLOCKED"
    return entries, receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 6 6D-v2 offline gate - authoritative phase1 receipt"
    )
    parser.add_argument("--datasets", default="2024,2025",
                        help="comma-separated year list")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT,
                        help="manifest output path")
    parser.add_argument("--datasets-dir", default=_DEFAULT_DATASETS_DIR,
                        help="datasets directory")
    parser.add_argument("--v1-archive-dir", default=V1_ARCHIVE_DIR,
                        help="6D v1 archive dir (contains dev_gate.json)")
    parser.add_argument("--v1-runs-dir", default=V1_RUNS_DIR,
                        help="6D v1 runs workspace (contains run_context.json)")
    args = parser.parse_args(argv)
    years = [y.strip() for y in args.datasets.split(",") if y.strip()]
    entries, receipt = build_receipt(
        years, args.datasets_dir, args.v1_archive_dir, args.v1_runs_dir)
    receipt_path = os.path.join(
        os.path.dirname(args.output) or ".", _RECEIPT_FILENAME)
    if receipt["status"] == "PASS":
        write_manifest(entries, args.output)
        print(f"[6d-v2] wrote manifest: {args.output}")
    else:
        print(f"[6d-v2] BLOCKED (n_routed={receipt['n_routed']} "
              f"< {_BLOCK_THRESHOLD} or v2 check failed); "
              f"manifest not overwritten")
    write_receipt(receipt, receipt_path)
    print(f"[6d-v2] wrote receipt: {receipt_path}")
    print(f"[6d-v2] status={receipt['status']} "
          f"n_routed={receipt['n_routed']} "
          f"on_limited_no_relations={receipt['on_limited_no_relations']} "
          f"arm_fail_closed_ok={receipt['arm_fail_closed_ok']} "
          f"off_reuse_precheck_ok={receipt['off_reuse_precheck_ok']}")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
