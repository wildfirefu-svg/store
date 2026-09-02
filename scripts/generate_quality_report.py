"""
generate_quality_report.py
Generate a SHA-stamped quality report for classic-text distillation artifacts.

Fail-closed: returns non-zero exit code if ANY book has failed blocking gates
or missing provenance. The report is written atomically and includes the
validator code SHA and input artifact SHAs for reproducibility.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "knowledge_base" / "classic_texts"

BOOKS = {
    "ditiansui": "滴天髓",
    "zipingzhenquan": "子平真诠",
    "qiongtongbaojian": "穷通宝鉴",
    "sanmingtonghui": "三命通会",
}

sys.path.insert(0, str(ROOT))
val_mod = importlib.import_module("scripts.validate_classic_distillation")
from scripts.classic_artifacts import validate_provenance  # noqa: E402

SCRIPTS_DIR = ROOT / "scripts"


def _find_git_root(start: Path | None = None) -> Path | None:
    """Walk up from start (default: module ROOT) to find the git repository
    root (P0-4). Recognizes both normal checkouts (.git directory) and
    linked worktrees (.git file pointing at the real gitdir)."""
    p = start if start is not None else ROOT
    while p != p.parent:
        if (p / ".git").is_dir() or (p / ".git").is_file():
            return p
        p = p.parent
    return None


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(content, encoding="utf-8")
    try:
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def generate_report(
    base_path: Path | None = None,
    books: dict[str, str] | None = None,
) -> tuple[dict, int]:
    """Generate quality report. Returns (report_dict, exit_code).

    exit_code is 0 only if ALL books pass all gates AND have provenance.
    """
    base = base_path or BASE
    book_map = books or BOOKS
    git_root = _find_git_root()

    val_results = []
    for dir_key, name in book_map.items():
        r = val_mod.validate_book(dir_key, name, base_path=base)
        val_results.append(r)

    validator_path = ROOT / "scripts" / "validate_classic_distillation.py"
    validator_sha = _sha256_file(validator_path) if validator_path.exists() else "missing"

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "validator": "scripts/validate_classic_distillation.py",
        "validator_code_sha256": validator_sha,
        "validator_ran_live": True,
        "books": {},
        "known_limitations": [],
    }

    remediation_pass = True
    end_to_end_pass = True

    for dir_key, name in book_map.items():
        p = base / dir_key
        entry = {"name": name, "dir": dir_key}

        rules_f = p / "all_rules.json"
        mcq_f = p / "all_mcq.jsonl"
        q_rules_f = p / "quarantine_rules.jsonl"
        q_mcq_f = p / "quarantine_mcq.jsonl"
        provenance_f = p / "provenance.json"

        if rules_f.exists():
            rules = json.loads(rules_f.read_text(encoding="utf-8"))
            entry["rules"] = {"count": len(rules), "sha256": _sha256_file(rules_f)}
            cats = Counter(r.get("category", "?") for r in rules)
            entry["rules"]["categories"] = dict(cats.most_common())
        if mcq_f.exists():
            mcqs = [json.loads(l) for l in mcq_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["mcq"] = {"count": len(mcqs), "sha256": _sha256_file(mcq_f)}
            ans = Counter(m.get("answer", "?") for m in mcqs)
            entry["mcq"]["answer_dist"] = dict(ans)
            valid = sum(v for k, v in ans.items() if k in "ABCD")
            entry["mcq"]["answer_pct"] = {k: round(v / max(1, valid), 4) for k, v in ans.items() if k in "ABCD"}
        if q_rules_f.exists():
            qr = [l for l in q_rules_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["quarantine_rules"] = {"count": len(qr), "sha256": _sha256_file(q_rules_f)}
        else:
            entry["quarantine_rules"] = {"count": 0}
        if q_mcq_f.exists():
            qm = [l for l in q_mcq_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["quarantine_mcq"] = {"count": len(qm), "sha256": _sha256_file(q_mcq_f)}
        else:
            entry["quarantine_mcq"] = {"count": 0}

        provenance_ok = False
        end_to_end_provenance = False
        prov_issues: list[str] = []
        if provenance_f.exists():
            # P0-4: pass git_root so anchor_commit existence and baseline blob
            # checks actually run.
            prov_ok, prov_issues = validate_provenance(p, SCRIPTS_DIR, git_root=git_root)
            if prov_ok:
                prov_data = json.loads(provenance_f.read_text(encoding="utf-8"))
                entry["provenance"] = prov_data
                provenance_ok = True
                upstream_status = prov_data.get("upstream_provenance_status", "unavailable")
                # P0-4: only 'recovered' (full upstream schema validated) gives
                # end_to_end_provenance=True. 'partial' and 'unavailable' both
                # mean end-to-end is not proven.
                end_to_end_provenance = (upstream_status == "recovered")
                if not end_to_end_provenance:
                    end_to_end_pass = False
                    report["known_limitations"].append(
                        f"end-to-end provenance incomplete for {name} ({dir_key}): "
                        f"upstream_provenance_status={upstream_status}"
                    )
                # Round-7 Medium: a formal quality gate must NOT treat a partial
                # API generation chain (no archived run_manifest) as a verified
                # chain. Only verification_level=='full' counts. This degrades
                # provenance_ok and forces the remediation gate to fail.
                api_gen = (prov_data.get("api_generation") or {})
                api_vlevel = api_gen.get("verification_level")
                # Round-7/P0: whenever an api_generation chain exists, require
                # verification_level to be EXACTLY 'full' for the formal quality
                # gate. A missing value (None) must also degrade -- the old
                # `is not None` guard let an omitted verification_level bypass it.
                if api_gen and api_vlevel != "full":
                    provenance_ok = False
                    entry["provenance_partial"] = True
                    entry["provenance_issues"] = entry.get("provenance_issues", []) + [
                        f"api_generation.verification_level={api_vlevel!r} is not 'full' "
                        f"(no archived run_manifest); treated as unverified"]
                    remediation_pass = False
                    end_to_end_pass = False
                    report["known_limitations"].append(
                        f"api_generation chain for {name} ({dir_key}) is only "
                        f"{api_vlevel!r}, not 'full' -- not a verified generation chain"
                    )
            else:
                entry["provenance"] = json.loads(provenance_f.read_text(encoding="utf-8"))
                entry["provenance_issues"] = prov_issues
                entry["provenance_invalid"] = True
                remediation_pass = False
                end_to_end_pass = False
        else:
            entry["provenance"] = None
            entry["provenance_missing"] = True
            remediation_pass = False
            end_to_end_pass = False

        for v in val_results:
            if v.get("dir") == dir_key:
                entry["gates"] = {k: g.get("pass") for k, g in v.get("gates", {}).items()}
                entry["all_gates_pass"] = v.get("passed", False)
                entry["gate_details"] = v.get("gates", {})
                if not v.get("passed", False):
                    remediation_pass = False
                    end_to_end_pass = False
                break

        entry["provenance_ok"] = provenance_ok
        entry["end_to_end_provenance"] = end_to_end_provenance
        report["books"][dir_key] = entry

    # P0-4: split remediation_pass (gates + provenance valid) from
    # end_to_end_pass (remediation + upstream recovered). overall_pass is
    # kept for backward compatibility but is now end_to_end_pass.
    report["remediation_pass"] = remediation_pass
    report["end_to_end_pass"] = end_to_end_pass
    report["overall_pass"] = end_to_end_pass
    exit_code = 0 if end_to_end_pass else 1
    return report, exit_code


def main() -> int:
    print("Re-running validator for fresh gate results...")
    report, exit_code = generate_report()

    out = BASE / "QUALITY_REPORT.json"
    _atomic_write(out, json.dumps(report, ensure_ascii=False, indent=2))

    print(f"Quality report written to {out}")
    print(f"\n=== Summary ===")
    total_rules = 0
    total_mcq = 0
    total_q_rules = 0
    total_q_mcq = 0
    for dir_key, e in report["books"].items():
        r = e.get("rules", {}).get("count", 0)
        m = e.get("mcq", {}).get("count", 0)
        qr = e.get("quarantine_rules", {}).get("count", 0)
        qm = e.get("quarantine_mcq", {}).get("count", 0)
        passed = "PASS" if e.get("all_gates_pass") else "FAIL"
        prov = "OK" if e.get("provenance_ok") else "MISSING"
        e2e = "OK" if e.get("end_to_end_provenance") else "GAP"
        total_rules += r
        total_mcq += m
        total_q_rules += qr
        total_q_mcq += qm
        print(f"  {e['name']:<8} gates={passed:<4} prov={prov:<7} e2e={e2e:<3} rules={r:<5} mcq={m:<5} q_rules={qr:<3} q_mcq={qm:<3}")
    print(f"  {'TOTAL':<8} {'':<24} rules={total_rules:<5} mcq={total_mcq:<5} q_rules={total_q_rules:<3} q_mcq={total_q_mcq:<3}")
    print(f"\nKnown limitations: {len(report['known_limitations'])}")
    for lim in report["known_limitations"]:
        print(f"  - {lim}")
    print(f"Remediation: {'PASS' if report.get('remediation_pass') else 'FAIL'}")
    print(f"End-to-end:  {'PASS' if report.get('end_to_end_pass') else 'FAIL'}")
    print(f"OVERALL:     {'PASS' if exit_code == 0 else 'FAIL'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
