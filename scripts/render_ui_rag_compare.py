"""Render docs/UI_RAG_COMPARE.md from .tmp/ui-rag-compare/{baseline,rag}/ui-report-quality.json + report.txt."""

from __future__ import annotations

import json
from pathlib import Path


BASE = Path(".tmp/ui-rag-compare")
OUT = Path("docs/UI_RAG_COMPARE.md")


def _load(tag: str):
    info = BASE / tag / "ui-report-quality.json"
    text = BASE / tag / "ui-report-quality-report.txt"
    data = json.loads(info.read_text(encoding="utf-8")) if info.exists() else {}
    body = text.read_text(encoding="utf-8") if text.exists() else ""
    return data, body


def _signal(d, key, default="?"):
    return (d.get("signals") or {}).get(key, default)


def main():
    base, base_body = _load("baseline")
    rag, rag_body = _load("rag")

    pipe = chr(124)
    rows = [
        ("report_chars", "字符数", "越长 ≈ 内容越丰富"),
        ("table_count", "表格数", "越多 ≈ 结构更细"),
        ("has_disclaimer", "免责声明", "True 才合规"),
        ("has_validation_note", "系统校验提示", "命中可疑断言时为 True"),
        ("has_connection_error", "连接错误", "必须为 False"),
        ("bad_patterns", "可疑断言", "应为 []"),
    ]

    lines = ["# UI RAG 对比：同一命主下报告分析水平差异", ""]
    lines.append(
        "命主：1990-05-12 08:30 北京 女命（与 [scripts/run_ui_report_quality.py]"
        "(file:///f:/project/agent/scripts/run_ui_report_quality.py) 默认一致）。"
    )
    lines.append("")
    lines.append(f"{pipe} 指标 {pipe} 含义 {pipe} BAZI_RAG=0 (baseline) {pipe} BAZI_RAG=1 (RAG) {pipe}")
    lines.append(f"{pipe} ---- {pipe} ---- {pipe} ----------------- {pipe} -------------- {pipe}")
    for key, label, hint in rows:
        b = _signal(base, key)
        r = _signal(rag, key)
        lines.append(f"{pipe} {label} {pipe} {hint} {pipe} {b} {pipe} {r} {pipe}")

    lines.append("")
    lines.append("## Errors 摘要")
    lines.append("")
    lines.append("- baseline: " + ", ".join(base.get("errors") or []) or "- baseline: 无")
    lines.append("- rag: " + ", ".join(rag.get("errors") or []) or "- rag: 无")

    lines.append("")
    lines.append("## 报告片段（前 800 字）")
    lines.append("")
    lines.append("### baseline")
    lines.append("")
    lines.append("```")
    lines.append((base_body or "")[:800].rstrip())
    lines.append("```")
    lines.append("")
    lines.append("### rag")
    lines.append("")
    lines.append("```")
    lines.append((rag_body or "")[:800].rstrip())
    lines.append("```")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("Written", OUT)


if __name__ == "__main__":
    main()
