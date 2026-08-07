#!/usr/bin/env python3
"""Validate the CI workflow configuration and record local harness evidence."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CI_FILE = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
RESULT_DIR = PROJECT_ROOT / ".better-harness"
RESULT_FILE = RESULT_DIR / "verify-ci.result.json"


def _rel(path: Path) -> str:
    """Project-relative display path; falls back to absolute outside the repo."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _job_block(text: str, job_name: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped == f"{job_name}:" and indent > 0:
            block = [line]
            for candidate in lines[index + 1:]:
                candidate_stripped = candidate.lstrip()
                candidate_indent = len(candidate) - len(candidate_stripped)
                if candidate_stripped and candidate_indent <= indent:
                    break
                block.append(candidate)
            return "\n".join(block)
    return ""


def main() -> int:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    details: dict = {}
    status = "verified"
    exit_code = 0

    if not CI_FILE.exists():
        status = "failed"
        exit_code = 1
        details = {"error": f"CI workflow not found: {CI_FILE}"}
    else:
        text = CI_FILE.read_text(encoding="utf-8")
        test_block = _job_block(text, "test")
        details["file"] = _rel(CI_FILE)
        details["exists"] = True
        details["hasTestJob"] = bool(test_block)
        details["hasPythonSetup"] = "actions/setup-python" in test_block
        details["hasPytestStep"] = "pytest" in test_block

        # Try a best-effort YAML parse if PyYAML is available; do not fail if absent.
        try:
            import yaml

            workflow = yaml.safe_load(text)
            jobs = workflow.get("jobs", {})
            details["jobCount"] = len(jobs)
            details["jobNames"] = list(jobs.keys())
            test_job = jobs.get("test") if isinstance(jobs, dict) else None
            steps = test_job.get("steps", []) if isinstance(test_job, dict) else []
            details["hasTestJob"] = isinstance(test_job, dict)
            details["hasPythonSetup"] = any(
                isinstance(step, dict)
                and str(step.get("uses", "")).startswith("actions/setup-python@")
                for step in steps
            )
            details["hasPytestStep"] = any(
                isinstance(step, dict) and "pytest" in str(step.get("run", ""))
                for step in steps
            )
        except ImportError:
            details["yamlParse"] = "skipped (PyYAML not installed)"
        except Exception as e:
            status = "failed"
            exit_code = 1
            details["error"] = f"CI YAML parse error: {e}"

        if status == "verified" and not (
            details["hasTestJob"]
            and details["hasPythonSetup"]
            and details["hasPytestStep"]
        ):
            status = "failed"
            exit_code = 1
            details["error"] = (
                "CI workflow missing test job, Python setup, or pytest step"
            )

    finished_at = datetime.now(timezone.utc).isoformat()

    result = {
        "claim": "CI workflow configuration",
        "status": status,
        "command": f"python {Path(__file__).relative_to(PROJECT_ROOT)}",
        "exitCode": exit_code,
        "details": details,
        "startedAt": started_at,
        "finishedAt": finished_at,
    }

    RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"claim": result["claim"], "status": result["status"], "exitCode": result["exitCode"]}))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
