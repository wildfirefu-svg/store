"""Shared helpers for structural tests of .qoder agent assets."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_frontmatter(path: Path) -> dict:
    """Parse simple one-level `key: value` YAML frontmatter (no nesting)."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"missing frontmatter in {path}"
    end = text.index("---", 3)
    fields: dict = {}
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields
