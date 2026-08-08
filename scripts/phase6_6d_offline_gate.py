#!/usr/bin/env python3
"""Phase 6 6D offline gate - generate and freeze the temporal routed manifest.

Audits holdout datasets with the temporal routing primitives
(detect_temporal_rules / extract_target_years / classify_route_state),
collects every routed case, freezes a canonical manifest, and emits a
phase1 receipt (PASS when n_routed >= 20, BLOCKED otherwise).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from benchmark.formatters.bazi_time_context import (  # noqa: E402
    TemporalRouteState,
    classify_route_state,
    detect_temporal_rules,
    extract_target_years,
)

_DATASET_FILENAME = "baziqa_contest8_{year}_holdout_enriched.jsonl"
_BLOCK_THRESHOLD = 20
_DEFAULT_OUTPUT = "docs/phase6/6d/temporal_routed_cases.json"
_DEFAULT_DATASETS_DIR = "benchmark/datasets"
_RECEIPT_FILENAME = "phase1_receipt.json"


def compute_dataset_sha256(path: str) -> str:
    """Return SHA-256 hex digest of a dataset file's raw bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_birth_year(case: dict) -> int | None:
    birth_year = case.get("birth_year")
    if birth_year is None:
        birth_year = (case.get("person") or {}).get("birth", {}).get("year")
    return birth_year


def audit_dataset(year: str, path: str) -> list[dict]:
    """Audit one dataset year; return routed entries (route_state != NOT_ROUTED)."""
    ds_sha = compute_dataset_sha256(path)
    entries: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            case = json.loads(line)
            question = case.get("question", "")
            options = case.get("options", []) or []
            rules = detect_temporal_rules(question, options)
            target_years = extract_target_years(
                question, options, _resolve_birth_year(case)
            )
            state = classify_route_state(rules, target_years)
            if state == TemporalRouteState.NOT_ROUTED:
                continue
            entries.append(
                {
                    "year": year,
                    "dataset_sha256": ds_sha,
                    "case_id": case.get("case_id", ""),
                    "domain": case.get("domain", ""),
                    "route_state": state.value,
                    "matched_rules": sorted(rules),
                    "target_years": list(target_years),
                }
            )
    return entries


def _canonical_sha256(entries: list[dict]) -> str:
    return hashlib.sha256(
        json.dumps(
            entries, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def generate_routed_manifest(
    years: list[str], datasets_dir: str
) -> tuple[list[dict], dict, dict]:
    """Audit all datasets; return (entries, sha_by_year, receipt)."""
    all_entries: list[dict] = []
    sha_by_year: dict[str, str] = {}
    n_total = 0
    for y in sorted(years):
        path = os.path.join(datasets_dir, _DATASET_FILENAME.format(year=y))
        if not os.path.exists(path):
            raise SystemExit(f"dataset not found: {path}")
        sha_by_year[y] = compute_dataset_sha256(path)
        all_entries.extend(audit_dataset(y, path))
        with open(path, encoding="utf-8") as f:
            n_total += sum(1 for ln in f if ln.strip())
    n_routed = len(all_entries)
    status = "PASS" if n_routed >= _BLOCK_THRESHOLD else "BLOCKED"
    dataset_set_sha256 = hashlib.sha256(
        json.dumps(sha_by_year, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    receipt = {
        "status": status,
        "dataset_sha256_by_year": sha_by_year,
        "dataset_set_sha256": dataset_set_sha256,
        "temporal_routed_cases_sha256": _canonical_sha256(all_entries),
        "n_routed": n_routed,
        "n_total": n_total,
    }
    return all_entries, sha_by_year, receipt


def write_manifest(entries: list[dict], output_path: str) -> str:
    """Atomically write the manifest; return its canonical SHA-256."""
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    os.replace(tmp, output_path)
    return _canonical_sha256(entries)


def write_receipt(receipt: dict, output_path: str) -> None:
    """Atomically write the phase1 receipt."""
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    os.replace(tmp, output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 6 6D offline gate - temporal routed manifest"
    )
    parser.add_argument(
        "--datasets", default="2024,2025", help="comma-separated year list"
    )
    parser.add_argument(
        "--output", default=_DEFAULT_OUTPUT, help="manifest output path"
    )
    parser.add_argument(
        "--datasets-dir",
        default=_DEFAULT_DATASETS_DIR,
        help="datasets directory",
    )
    args = parser.parse_args()
    years = [y.strip() for y in args.datasets.split(",") if y.strip()]
    entries, _sha_by_year, receipt = generate_routed_manifest(
        years, args.datasets_dir
    )
    output_path = args.output
    receipt_path = os.path.join(
        os.path.dirname(output_path) or ".", _RECEIPT_FILENAME
    )
    if receipt["status"] == "PASS":
        write_manifest(entries, output_path)
        print(f"[6d] wrote manifest: {output_path}")
    else:
        print(
            f"[6d] BLOCKED (n_routed={receipt['n_routed']}<{_BLOCK_THRESHOLD}); "
            f"manifest not overwritten"
        )
    write_receipt(receipt, receipt_path)
    print(f"[6d] wrote receipt: {receipt_path}")
    per_year: dict[str, int] = {}
    rule_dist: dict[str, int] = {}
    for e in entries:
        per_year[e["year"]] = per_year.get(e["year"], 0) + 1
        for r in e["matched_rules"]:
            rule_dist[r] = rule_dist.get(r, 0) + 1
    print(
        f"[6d] status={receipt['status']} n_total={receipt['n_total']} "
        f"n_routed={receipt['n_routed']}"
    )
    print(f"[6d] per_year={dict(sorted(per_year.items()))}")
    print(f"[6d] rule_dist={dict(sorted(rule_dist.items()))}")


if __name__ == "__main__":
    main()
