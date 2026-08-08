#!/usr/bin/env python3
"""PreToolUse hook: block writes to tracked data artifacts.

Blocks direct file tools (Write/Edit) and explicit Bash commands that
write, move, or delete forbidden paths. Dynamically assembled paths are
NOT covered -- see spec 2026-08-07-agent-workflow-enhancement-design.md
section 4.3 for the honest protection boundary.

Protocol (Qoder Hooks, docs.qoder.com/extensions/hooks):
  block  -> reason on stderr + exit 2
  allow  -> exit 0
The exit-0 + stdout deny-JSON protocol is deliberately not used.

Reads one JSON event from stdin: {"tool_name": ..., "tool_input": {...}}
Stdlib only; never echoes prompts, env values, or suspected secrets.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 与 AGENTS.md §4 同步（单一事实源；同步检查见
# tests/test_qoder_workflow_assets.py::test_forbidden_patterns_single_source_of_truth）
FORBIDDEN_PATTERNS = (
    "knowledge-base/*.json",
    "tests/case_db.json",
    "data/*.json",
    "benchmark/datasets/*.jsonl",
)

_WRITE_HINTS = re.compile(
    # >>?(?!&\d): 排除 2>&1 这类 fd 合并（非文件写入）；>&file 仍命中。
    r"(>>?(?!&\d)|mv\b|move\b|cp\b|copy\b|tee\b|rm\b|del\b|erase\b|remove-item\b"
    r"|set-content\b|out-file\b|git\s+rm\b|git\s+restore\b|git\s+checkout\s+--)",
    re.IGNORECASE,
)


def _normalize(path_str: str, cwd: str) -> str:
    """Resolve a tool file_path against the event cwd to a posix path.

    Relative paths are anchored at the event cwd (not the project root) so
    traversal like ../knowledge-base/x.json from a subdirectory resolves to
    its real target before matching. Backslashes are normalized for
    cross-platform consistency.
    """
    p = Path(path_str.replace("\\", "/"))
    if not p.is_absolute():
        p = (Path(cwd) if cwd else PROJECT_ROOT) / p
    resolved = p.resolve(strict=False)
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _glob_to_regex(pat: str) -> re.Pattern:
    """Translate a glob pattern to a regex; `*` spans path separators
    (recursive-hit semantics). Version-agnostic (3.8+): avoids
    PurePosixPath.full_match which requires Python 3.13."""
    out = []
    for ch in pat:
        if ch == "*":
            out.append(".*")
        elif ch in ".^$+{}[]()|\\":
            out.append("\\" + ch)
        elif ch == "?":
            out.append(".")
        else:
            out.append(ch)
    return re.compile("^" + "".join(out) + "$")


_FORBIDDEN_REGEXES = tuple(_glob_to_regex(p) for p in FORBIDDEN_PATTERNS)


def _forbidden(posix_path: str) -> bool:
    return any(rx.match(posix_path) for rx in _FORBIDDEN_REGEXES)


def _pattern_prefix(pat: str) -> str:
    """Leading literal segment prefix of a pattern (up to first wildcard)."""
    fixed = []
    for seg in pat.split("/"):
        if "*" in seg:
            break
        fixed.append(seg)
    return "/".join(fixed)


def _bash_hits(command: str) -> bool:
    """写意图 + 禁改前缀子串双命中才拦截；宁可保守过度拒绝，不做精细解析。"""
    if not _WRITE_HINTS.search(command):
        return False
    normalized = command.replace("\\", "/")
    return any(_pattern_prefix(pat) in normalized for pat in FORBIDDEN_PATTERNS)


def _deny(reason: str) -> int:
    print(reason, file=sys.stderr)
    return 2


def main() -> int:
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass
    try:
        event = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return 0  # fail-open: guard must not block the session on bad input
    if not isinstance(event, dict):
        return 0
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    cwd = str(event.get("cwd") or "")
    if tool in ("Write", "Edit"):
        path = _normalize(str(tool_input.get("file_path") or ""), cwd)
        if _forbidden(path):
            return _deny(
                f"denied: {path} is a tracked data artifact (AGENTS.md §4 禁改清单)"
            )
    elif tool == "Bash":
        command = str(tool_input.get("command") or "")
        if _bash_hits(command):
            return _deny(
                "denied: explicit Bash write/move/delete targets a forbidden "
                "data artifact path (AGENTS.md §4 禁改清单)"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
