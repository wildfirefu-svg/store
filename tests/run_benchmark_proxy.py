"""tests 内薄封装：把 run_benchmark.main 暴露为可 import 的入口（计划 Step 0）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.runners.run_benchmark import main  # noqa: F401
