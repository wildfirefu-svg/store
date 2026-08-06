#!/usr/bin/env python3
"""Post-process a core-change-watch evidence pack with verified-claims.json.

Usage:
    python scripts/apply_verified_claims.py [path/to/project-evidence.json]

If no path is given, updates .qoder/better-harness/<latest-run>/project-evidence.json.
The file is rewritten in-place; the static-evidence-boundary reviewMatrix item and
unverifiedClaims list are updated to reflect claims marked verified in
.better-harness/verified-claims.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERIFIED_CLAIMS_FILE = PROJECT_ROOT / ".better-harness" / "verified-claims.json"


def find_latest_evidence_file() -> Path | None:
    base = PROJECT_ROOT / ".qoder" / "better-harness"
    if not base.exists():
        return None
    candidates = []
    for run_dir in base.iterdir():
        if run_dir.is_dir():
            candidate = run_dir / "project-evidence.json"
            if candidate.exists():
                candidates.append((candidate.stat().st_mtime, candidate))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def load_verified_claims() -> dict:
    if not VERIFIED_CLAIMS_FILE.exists():
        return {}
    try:
        return json.loads(VERIFIED_CLAIMS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    if len(sys.argv) > 1:
        evidence_path = Path(sys.argv[1]).resolve()
    else:
        evidence_path = find_latest_evidence_file()

    if evidence_path is None or not evidence_path.exists():
        print(f"Evidence file not found: {evidence_path}", file=sys.stderr)
        return 1

    verified = load_verified_claims()
    claim_map = {c["claim"]: c for c in verified.get("claims", [])}

    raw_bytes = evidence_path.read_bytes()
    if raw_bytes[:2] == b"\xff\xfe":
        evidence_text = raw_bytes.decode("utf-16-le", errors="replace")
    elif raw_bytes[:2] == b"\xfe\xff":
        evidence_text = raw_bytes.decode("utf-16-be", errors="replace")
    else:
        evidence_text = raw_bytes.decode("utf-8-sig", errors="replace")
    evidence_text = evidence_text.lstrip("\ufeff")
    evidence = json.loads(evidence_text, strict=False)

    # Update evidenceSources.unverifiedClaims
    unverified_claims = []
    verified_claims = [
        {
            "claim": claim_name,
            "status": "verified",
            "command": item.get("command", ""),
            "resultFile": item.get("details", {}).get("resultFile", ""),
            "verifiedAt": verified.get("generatedAt", ""),
        }
        for claim_name, item in claim_map.items()
        if item.get("status") == "verified"
    ]
    for item in evidence.get("evidenceSources", {}).get("unverifiedClaims", []):
        claim_name = item.get("claim")
        verified_item = claim_map.get(claim_name)
        if verified_item and verified_item.get("status") == "verified":
            continue
        else:
            unverified_claims.append(item)

    evidence["evidenceSources"]["unverifiedClaims"] = unverified_claims
    if verified_claims:
        evidence["evidenceSources"]["verifiedClaims"] = verified_claims

    # Update reviewMatrix static-evidence-boundary
    for row in evidence.get("reviewMatrix", []):
        if row.get("id") == "static-evidence-boundary":
            boundary_evidence = row.get("evidence", {})
            original_unverified = boundary_evidence.get("unverified", [])
            new_unverified = [c for c in original_unverified if c not in claim_map or claim_map.get(c, {}).get("status") != "verified"]
            new_verified = [item["claim"] for item in verified_claims]
            boundary_evidence["unverified"] = new_unverified
            boundary_evidence["verified"] = new_verified
            boundary_evidence["boundary"] = "static-local-git-and-file-analysis-plus-project-verification"
            boundary_evidence["verificationResultFile"] = str(VERIFIED_CLAIMS_FILE.relative_to(PROJECT_ROOT))
            row["note"] = "Local runtime, CI workflow configuration, and test claims are verified by project scripts when .better-harness/verified-claims.json is present; remote CI status remains separate."
            break

    evidence["verifiedClaimsAppliedAt"] = datetime.now(timezone.utc).isoformat()

    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "evidenceFile": str(evidence_path.relative_to(PROJECT_ROOT)),
        "remainingUnverified": [c.get("claim") for c in unverified_claims],
        "verified": [c.get("claim") for c in verified_claims],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
