#!/usr/bin/env python3
"""Map changed files (git diff --name-only) to the minimal pytest file list.

Usage:
    python scripts/affected_tests.py                # diff vs HEAD (tracked + untracked)
    python scripts/affected_tests.py --base main    # diff vs another ref
    python scripts/affected_tests.py path/a.py ...  # explicit file list
    python scripts/affected_tests.py --run          # also run the selected tests

Output (stdout): one pytest file per line, or the marker `FULL_SUITE`.
Exit code 0 when a mapping is produced; 1 only on internal error.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Explicit module -> tests mapping (extends .reasonix/skills/test-suite.md).
EXPLICIT_MODULE_TESTS = {
    "bazi_calculator": [
        "tests/test_bazi_calculator_pillars.py",
        "tests/test_bazi_calculator_dayun.py",
        "tests/test_bazi_calculator_derived.py",
        "tests/test_bazi_calculator_location_matching.py",
        "tests/test_bazi_calculator_shensha.py",
        "tests/test_bazi_calculator_ziwei.py",
    ],
    "api_server": ["tests/test_api.py", "tests/test_clients_api.py"],
    "config": ["tests/test_claude_api.py"],
    "hybrid_retrieval": ["tests/test_hybrid_rrf.py"],
    "case_reranker": ["tests/test_reranker_stub.py"],
}

# Directory-level mapping (from .reasonix/skills/test-suite.md).
EXPLICIT_DIR_TESTS = {
    "knowledge-base/": [
        "tests/test_bazi_kb.py",
        "tests/test_gejue_search.py",
        "tests/test_bingyao.py",
    ],
    "static/": ["tests/test_e2e.py"],
    "tests/": ["FULL_SUITE"],
}

# Changes to these files invalidate any partial selection.
FULL_SUITE_TRIGGERS = {
    "pytest.ini",
    "requirements.txt",
    "requirements-dev.txt",
}

# Minimal fallback subset when a change has no specific test mapping.
FALLBACK_SMOKE = [
    "tests/test_bazi_calculator_pillars.py",
    "tests/test_frontend_assets.py",
]


def pytest_command(tests: list[str]) -> list[str]:
    basetemp = PROJECT_ROOT / ".tmp" / f"pytest-affected-{os.getpid()}"
    return [
        sys.executable,
        "-m",
        "pytest",
        *tests,
        "-q",
        "--tb=short",
        "--basetemp",
        str(basetemp),
        "-p",
        "no:cacheprovider",
    ]


def git_changed_files(base: str) -> list[str]:
    tracked = subprocess.run(
        ["git", "diff", "--name-only", base, "--"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.splitlines()
    return [line.strip() for line in tracked + untracked if line.strip()]


def existing_tests(candidates: list[str]) -> list[str]:
    return [t for t in candidates if (PROJECT_ROOT / t).exists()]


def reverse_index_for_script(script_name: str) -> list[str]:
    """Find tests that reference scripts/<script_name>.py."""
    hits = []
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.exists():
        return hits
    needle = f"scripts/{script_name}.py"
    needle_alt = f"scripts\\{script_name}.py"
    for path in sorted(tests_dir.glob("test_*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if needle in text or needle_alt in text:
            hits.append(f"tests/{path.name}")
    return hits


def map_file(path: str) -> list[str]:
    """Return pytest files for one changed path, or ["FULL_SUITE"]/"fallback"."""
    posix = path.replace("\\", "/")

    if posix in FULL_SUITE_TRIGGERS or posix.startswith("tests/"):
        return ["FULL_SUITE"]

    for directory, tests in EXPLICIT_DIR_TESTS.items():
        if posix.startswith(directory):
            return tests

    if posix.endswith(".py"):
        stem = Path(posix).stem
        if posix.startswith("scripts/"):
            hits = reverse_index_for_script(stem)
            if hits:
                return hits
            return ["FALLBACK"]
        if stem in EXPLICIT_MODULE_TESTS:
            return existing_tests(EXPLICIT_MODULE_TESTS[stem]) or ["FALLBACK"]
        convention = f"tests/test_{stem}.py"
        if (PROJECT_ROOT / convention).exists():
            return [convention]
        return ["FALLBACK"]

    # Docs/config/etc. changes do not require tests.
    return []


def resolve(files: list[str]) -> tuple[list[str], bool]:
    """Return (pytest_files, full_suite)."""
    selected: list[str] = []
    full_suite = False
    for path in files:
        for target in map_file(path):
            if target == "FULL_SUITE":
                full_suite = True
            elif target == "FALLBACK":
                selected.extend(FALLBACK_SMOKE)
            else:
                selected.append(target)
    if full_suite:
        return [], True
    seen: list[str] = []
    for test in selected:
        if test not in seen:
            seen.append(test)
    return seen, False


def main() -> int:
    argv = list(sys.argv[1:])
    base = "HEAD"
    if "--base" in argv:
        index = argv.index("--base")
        base = argv[index + 1]
        argv = argv[:index] + argv[index + 2:]
    flags = {a for a in argv if a.startswith("-")}
    args = [a for a in argv if not a.startswith("-")]

    if args:
        changed = args
    else:
        changed = git_changed_files(base)

    tests, full_suite = resolve(changed)

    if full_suite:
        print("FULL_SUITE")
    elif tests:
        for test in tests:
            print(test)
    else:
        print("# no test mapping needed for changed files")

    if "--run" in flags and not full_suite and tests:
        proc = subprocess.run(pytest_command(tests), cwd=PROJECT_ROOT)
        return proc.returncode
    if "--run" in flags and full_suite:
        proc = subprocess.run(pytest_command(["tests/"]), cwd=PROJECT_ROOT)
        return proc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
