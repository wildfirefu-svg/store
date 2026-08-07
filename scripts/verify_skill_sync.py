#!/usr/bin/env python3
"""Check that .reasonix/skills/ mirrors stay byte-identical to .qoder/skills/.

.qoder/skills/ is the single authoritative skill surface (see AGENTS.md §10);
.reasonix/skills/ is a mirror copy for other providers. This script detects
drift between the two trees.

Usage:
    python scripts/verify_skill_sync.py

Exit code 0 when consistent, 2 on drift or missing mirrors.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTHORITATIVE_DIR = PROJECT_ROOT / ".qoder" / "skills"
MIRROR_DIR = PROJECT_ROOT / ".reasonix" / "skills"


def main() -> int:
    if not AUTHORITATIVE_DIR.is_dir():
        print(f"error: authoritative surface missing: {AUTHORITATIVE_DIR}")
        return 2

    problems: list[str] = []
    checked = 0
    for skill_md in sorted(AUTHORITATIVE_DIR.glob("*/SKILL.md")):
        name = skill_md.parent.name
        mirror = MIRROR_DIR / f"{name}.md"
        checked += 1
        if not mirror.is_file():
            problems.append(f"missing mirror: {mirror.relative_to(PROJECT_ROOT)}")
            continue
        if skill_md.read_bytes() != mirror.read_bytes():
            problems.append(f"content drift: {name}")

    if problems:
        print("skill sync check FAILED:")
        for item in problems:
            print(f"  - {item}")
        print("Resync from the authoritative surface .qoder/skills/ "
              "to .reasonix/skills/ (one file per skill, <name>.md).")
        return 2

    print(f"skill sync check OK: {checked} skill(s) identical on both surfaces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
