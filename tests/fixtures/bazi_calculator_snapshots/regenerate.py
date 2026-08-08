"""手动再生成全部快照基线。变更引擎后运行，并人工 review diff 再提交（spec §5）。"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))                     # tests/fixtures/bazi_calculator_snapshots/
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))       # 仓库根（三层上溯）
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))            # tests/

import lunar_calendar

lunar_calendar._IZTRO_PYTHON = None  # 固定内置后端（spec §5）

try:
    from bazi_snapshot_helper import (
        SNAPSHOT_CASES,
        SNAPSHOT_DIR,
        compute_e2e,
        compute_shensha,
        compute_ziwei,
        save_snapshot,
    )
except ImportError as e:
    raise SystemExit(f"导入 bazi_snapshot_helper 失败：请从仓库根目录运行本脚本（{e}）")


def main():
    for case in SNAPSHOT_CASES:
        save_snapshot(SNAPSHOT_DIR / f"e2e_{case['name']}.json", compute_e2e(case))
    for case in SNAPSHOT_CASES[:3]:
        save_snapshot(SNAPSHOT_DIR / f"shensha_{case['name']}.json", compute_shensha(case))
    save_snapshot(SNAPSHOT_DIR / f"ziwei_{SNAPSHOT_CASES[0]['name']}.json", compute_ziwei(SNAPSHOT_CASES[0]))
    print(f"regenerated 9 snapshots in {SNAPSHOT_DIR}")


if __name__ == '__main__':
    main()
