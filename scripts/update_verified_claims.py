#!/usr/bin/env python3
"""Merge individual verification results into .better-harness/verified-claims.json.

This file is consumed by core-change-watch evidence-pack so locally verifiable
runtime/CI-configuration/test claims can be distinguished from external status.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = PROJECT_ROOT / ".better-harness"
OUTPUT_FILE = RESULT_DIR / "verified-claims.json"

CLAIM_FILES = {
    "focused smoke tests passed": RESULT_DIR / "verify-smoke.result.json",
    "CI workflow configuration": RESULT_DIR / "verify-ci.result.json",
    "runtime behavior": RESULT_DIR / "verify-runtime.result.json",
}


def load_result(path: Path) -> dict:
    if not path.exists():
        return {"status": "missing", "error": f"result file not found: {path}"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> int:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    claims = []
    for claim_name, path in CLAIM_FILES.items():
        raw = load_result(path)
        status = raw.get("status", "unverified")
        claims.append({
            "claim": claim_name,
            "status": status,
            "command": raw.get("command", ""),
            "exitCode": raw.get("exitCode", None),
            "details": {
                "resultFile": str(path.relative_to(PROJECT_ROOT)),
                "finishedAt": raw.get("finishedAt", ""),
                "error": raw.get("error") or raw.get("stderr", "")[:500],
            },
        })

    verified_count = sum(1 for c in claims if c["status"] == "verified")
    all_verified = verified_count == len(claims)

    output = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "allVerified": all_verified,
        "verifiedCount": verified_count,
        "totalCount": len(claims),
        "claims": claims,
    }

    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"allVerified": all_verified, "verifiedCount": verified_count, "totalCount": len(claims)}))
    return 0 if all_verified else 1


if __name__ == "__main__":
    sys.exit(main())
