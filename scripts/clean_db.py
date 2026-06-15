#!/usr/bin/env python3
"""数据库清理工具 — 安全删除测试数据或全部命主。

用法示例：
    python scripts/clean_db.py --dry-run                # 预览全部命主，不删除
    python scripts/clean_db.py --test-only --dry-run    # 只预览测试数据
    python scripts/clean_db.py --test-only              # 删除测试数据
    python scripts/clean_db.py --all --yes              # 删除全部命主（含聊天/报告）

测试数据识别规则：命主名包含以下任一关键词
    测试  E2E  Test  Web验证  切换测试  TestMingzhu  updated  工具栏测试
"""
from __future__ import annotations

import argparse
import os
import sys

# 让脚本可以在项目根目录直接执行
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import data_store  # noqa: E402

TEST_KEYWORDS = (
    "测试", "E2E", "Test", "Web验证", "切换测试", "TestMingzhu",
    "updated", "工具栏测试",
)


def is_test_chart(name: str) -> bool:
    if not name:
        return True  # 空名字视为脏数据
    lowered = name.lower()
    for kw in TEST_KEYWORDS:
        if kw.lower() in lowered:
            return True
    return False


def confirm(prompt: str) -> bool:
    try:
        ans = input(prompt + " [y/N]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def main():
    parser = argparse.ArgumentParser(description="清理 BaZi 数据库中的命主数据")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="删除所有命主")
    group.add_argument("--test-only", action="store_true", help="只删除测试数据（基于名字关键词）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不真正删除")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过确认提示")
    args = parser.parse_args()

    charts = data_store.list_charts()
    print(f"数据库中共有 {len(charts)} 个命主")

    if args.all:
        targets = list(charts)
        scope_label = "全部"
    elif args.test_only:
        targets = [c for c in charts if is_test_chart(c.get("name") or "")]
        scope_label = "测试数据"
    else:
        # 默认 dry-run 全表预览
        for c in charts:
            mark = "[测试]" if is_test_chart(c.get("name") or "") else "      "
            print(f"  {mark}  {c['chart_id']}  {c.get('name','-')}")
        print("\n未指定 --all 或 --test-only，仅做预览。")
        return 0

    print(f"将清理 {scope_label} 共 {len(targets)} 条")
    for c in targets:
        print(f"  - {c['chart_id']}  {c.get('name','-')}")

    if args.dry_run:
        print("\n[--dry-run] 未真正删除任何数据")
        return 0

    if not args.yes and not confirm(f"确认删除上述 {len(targets)} 条命主？此操作不可恢复"):
        print("已取消")
        return 1

    deleted = 0
    failed = []
    for c in targets:
        try:
            data_store.delete_chart(c["chart_id"])
            deleted += 1
        except Exception as e:
            failed.append((c["chart_id"], str(e)))

    print(f"\n完成：删除 {deleted} 条，失败 {len(failed)} 条")
    for cid, err in failed:
        print(f"  ! {cid}: {err}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
