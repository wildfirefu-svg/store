#!/usr/bin/env python3
"""Run project verification scripts and produce a verified core-change-watch evidence pack.

Usage:
    python scripts/run_verified_evidence_pack.py [out-dir]

Defaults to .qoder/better-harness/<timestamp>-verified.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_cli(env: dict[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    explicit = environment.get("BETTER_HARNESS_CLI")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"BETTER_HARNESS_CLI does not point to a file: {path}"
            )
        return path

    qoder_home = Path(
        environment.get("QODER_HOME", str(Path.home() / ".qoder-cn"))
    )
    path = (
        qoder_home
        / "plugins"
        / "cache"
        / "qoder-bundler"
        / "better-harness"
        / "scripts"
        / "better-harness.mjs"
    )
    if path.is_file():
        return path
    raise FileNotFoundError(
        "Better Harness CLI not found; set BETTER_HARNESS_CLI to "
        "better-harness.mjs"
    )


def find_node() -> str:
    return "node"


def run_script(name: str) -> int:
    return run_script_with_args(name, [])


def run_script_with_args(name: str, args: list[str]) -> int:
    script = PROJECT_ROOT / "scripts" / name
    print(f"\n>>> Running {script.relative_to(PROJECT_ROOT)}")
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=PROJECT_ROOT,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode


def main() -> int:
    try:
        cli = resolve_cli()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out_dir = sys.argv[1] if len(sys.argv) > 1 else None
    if out_dir is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        out_dir = str(PROJECT_ROOT / ".qoder" / "better-harness" / f"{timestamp}-verified")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1) Run verification scripts
    failures = 0
    for script_name in ["verify_smoke.py", "verify_ci.py", "verify_runtime.py"]:
        rc = run_script(script_name)
        if rc != 0:
            failures += 1

    # 2) Merge results into verified-claims.json
    rc = run_script("update_verified_claims.py")
    if rc != 0:
        failures += 1

    # 3) Generate core-change-watch evidence pack
    print(f"\n>>> Running core-change-watch evidence-pack -> {out_dir}")
    proc = subprocess.run(
        [
            find_node(),
            str(cli),
            "core-change-watch",
            "evidence-pack",
            "--cwd",
            str(PROJECT_ROOT),
            "--json",
            "--output",
            str(out_path / "project-evidence.json"),
        ],
        cwd=PROJECT_ROOT,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        print("core-change-watch evidence-pack failed", file=sys.stderr)
        return proc.returncode

    # 4) Post-process with verified claims
    rc = run_script_with_args("apply_verified_claims.py", [str(out_path / "project-evidence.json")])
    if rc != 0:
        failures += 1

    print(f"\nVerified evidence pack written to: {out_dir}")
    print(f"To post-process an existing evidence pack, run: python scripts/apply_verified_claims.py")
    print(f"Verification failures: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
