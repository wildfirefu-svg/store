"""Structural guards for .qoder workflow assets (design 2026-08-07 v2)."""
import json

from tests.harness_asset_helpers import PROJECT_ROOT, parse_frontmatter

RULES = ["core-boundary.md", "scripts-safety.md", "benchmark-conventions.md"]


def test_rules_exist_with_type_and_consistency_clause():
    for name in RULES:
        path = PROJECT_ROOT / ".qoder" / "rules" / name
        assert path.is_file(), f"missing rule: {name}"
        fm = parse_frontmatter(path)
        assert fm.get("type") in {"always_apply", "specific_files"}, name
        body = path.read_text(encoding="utf-8")
        assert "不引入新豁免" in body, f"{name} 缺少一致性声明"


def test_core_boundary_selects_entry_not_mandatory_all():
    body = (PROJECT_ROOT / ".qoder" / "rules" / "core-boundary.md").read_text(
        encoding="utf-8"
    )
    assert "按要验证的声明选择对应验证入口" in body
    assert "必跑" not in body, "Rules 优先级高于 AGENTS.md，不得新增全局必跑约束"


def test_quality_gate_skill_structure():
    fm = parse_frontmatter(
        PROJECT_ROOT / ".qoder" / "skills" / "quality-gate" / "SKILL.md"
    )
    for key in ("name", "description", "trigger", "output", "validation"):
        assert fm.get(key), key
    mirror = PROJECT_ROOT / ".reasonix" / "skills" / "quality-gate.md"
    source = PROJECT_ROOT / ".qoder" / "skills" / "quality-gate" / "SKILL.md"
    assert mirror.read_bytes() == source.read_bytes(), "mirror drift"


def test_hook_settings_shape():
    settings = json.loads(
        (PROJECT_ROOT / ".qoder" / "settings.json").read_text(encoding="utf-8")
    )
    hooks = settings["hooks"]
    pre = hooks["PreToolUse"]
    post = hooks["PostToolUse"]
    assert pre[0]["matcher"] == "Write|Edit|Bash"
    assert post[0]["matcher"] == "Write|Edit"
    for entry in pre + post:
        for hook in entry["hooks"]:
            assert hook["type"] == "command"
            assert hook["command"].endswith(".py")


def test_agents_frontmatter_and_tool_scope():
    expected = {
        "bench-runner.md": {"Read", "Bash"},
        "core-guard.md": {"Read", "Grep", "Glob"},
        "rag-debugger.md": {"Read", "Bash", "Grep"},
    }
    for name, tools in expected.items():
        fm = parse_frontmatter(PROJECT_ROOT / ".qoder" / "agents" / name)
        assert fm.get("name") == name[:-3]
        assert fm.get("description"), name
        got = {t.strip() for t in fm["tools"].split(",")}
        assert got == tools, f"{name}: {got}"
        if name == "core-guard.md":
            assert "Write" not in got and "Edit" not in got


def test_forbidden_patterns_single_source_of_truth():
    """Hook 脚本清单必须与 core-boundary 规则一致（AGENTS.md §4 复述）。"""
    script = (PROJECT_ROOT / ".qoder" / "hooks" / "guard_data_artifacts.py").read_text(
        encoding="utf-8"
    )
    rule = (PROJECT_ROOT / ".qoder" / "rules" / "core-boundary.md").read_text(
        encoding="utf-8"
    )
    for pattern in (
        "knowledge-base/*.json",
        "tests/case_db.json",
        "data/*.json",
        "benchmark/datasets/*.jsonl",
    ):
        assert pattern in script, f"hook 缺模式: {pattern}"
        assert pattern in rule, f"规则缺模式: {pattern}"


def test_agents_md_memory_operation_line():
    body = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "总是用 UpdateMemory 沉淀经验" in body
