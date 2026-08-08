"""Phase 6A0 enrichment 薄封装：固定 as_of_date、输出 .tmp/phase6/datasets/、SHA-256 manifest。

不修改 benchmark/datasets/ 原始文件；2023 默认排除（密封），--include-2023 仅生成
输入侧 chart_input，不等于打开评测。enrich_row 对已有 chart_input 的行幂等跳过；
计算器异常（TypeError/ValueError/KeyError）时该行无 chart_input，由覆盖率门禁 fail-closed。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from bazi_calculator import compute_chart
from benchmark.formatters.chart_context import (
    APPROVED_BAZI_FIELDS,
    approved_field_presence,
)
from scripts.enrich_baziqa_chart_input import enrich_row, load_jsonl, write_jsonl

DEFAULT_YEARS = (2021, 2022, 2024, 2025)
SEALED_YEAR = 2023
DATASET_TEMPLATE = "benchmark/datasets/baziqa_contest8_{year}_holdout.jsonl"
OUTPUT_TEMPLATE = "baziqa_contest8_{year}_holdout_enriched.jsonl"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_denylisted(obj):
    """递归删除 denylist 键（kong_wang / liu_nian），用于跨版本一致性比较。"""
    if isinstance(obj, dict):
        return {
            k: strip_denylisted(v)
            for k, v in obj.items()
            if k not in ("kong_wang", "liu_nian")
        }
    if isinstance(obj, list):
        return [strip_denylisted(v) for v in obj]
    return obj


def enrich_year(year: int, as_of_date: str, out_dir: Path, root: Path = PROJECT_ROOT) -> dict:
    src = root / DATASET_TEMPLATE.format(year=year)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / OUTPUT_TEMPLATE.format(year=year)
    rows = [enrich_row(r, compute_chart) for r in load_jsonl(src)]
    write_jsonl(dst, rows)
    total = len(rows)
    if total == 0:
        raise SystemExit(f"空数据集：{src}")
    coverage: dict[str, int] = {}
    for row in rows:
        chart = row.get("chart_input") or {}
        for field, ok in approved_field_presence(chart).items():
            coverage[field] = coverage.get(field, 0) + int(ok)
    missing = {k: total - v for k, v in coverage.items() if v != total}
    if missing:
        raise SystemExit(f"批准字段覆盖率未达 100%: {missing}（{year}）")
    return {
        "year": year,
        "source_path": str(src.relative_to(root)),
        "source_sha256": sha256_file(src),
        "output_path": str(dst.relative_to(root)),
        "output_sha256": sha256_file(dst),
        "row_count": total,
        "approved_fields": list(APPROVED_BAZI_FIELDS),
        "approved_coverage": {k: f"{v}/{total}" for k, v in sorted(coverage.items())},
        "as_of_date": as_of_date,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 enrichment 薄封装")
    parser.add_argument("--years", type=int, nargs="*", default=list(DEFAULT_YEARS))
    parser.add_argument("--include-2023", action="store_true")
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--out-dir", type=Path, default=Path(".tmp/phase6/datasets"))
    parser.add_argument("--manifest", type=Path, default=Path(".tmp/phase6/enrich_manifest.json"))
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT,
                        help="数据集根目录（测试注入 tmp 根；生产默认项目根）")
    args = parser.parse_args(argv)
    # 相对 out-dir 锚定到 root（默认 .tmp/phase6/datasets 在项目根下）；
    # 否则 dst.relative_to(root) 在绝对 root 上抛 ValueError（真实运行暴露）
    out_dir = args.out_dir if args.out_dir.is_absolute() else args.root / args.out_dir

    years = sorted(set(args.years))
    if args.include_2023:
        years = sorted(set(years) | {SEALED_YEAR})
    elif SEALED_YEAR in years:
        raise SystemExit(
            "2023 为密封集：需显式 --include-2023（仅生成输入侧 chart_input，不等于打开评测）"
        )

    entries = [enrich_year(y, args.as_of_date, out_dir, root=args.root) for y in years]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": args.as_of_date,
        "includes_sealed_2023": args.include_2023,
        "identity_strategy": "passthrough_pseudo_anonymized_dataset",
        "note": "chart_input 中 kong_wang/liu_nian 为计算器固有输出，渲染层 denylist 永不读取",
        "entries": entries,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"years": [e["year"] for e in entries], "manifest": str(args.manifest)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
