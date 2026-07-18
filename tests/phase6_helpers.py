"""Phase 6 共享测试设施。

当前为最小集（`make_case`）；RunnerEnv / RunnerSpy / fake_config 等
在 Task 6 Step 0 按计划增补（注意：完整定义中的
`from scripts.run_phase6_6a0_ablation import AblationConfig` 在 Task 9 前不可导入，
增补时需改为 fake_config 内延迟导入——执行偏离已在 Task 2 提交信息登记）。
"""
from __future__ import annotations


def make_case(case_id: str = "c1", answer: str = "B", person_id: str = "p1") -> dict:
    """最小合法 BaziQA case；chart_input 按需注入。"""
    return {
        "case_id": case_id, "answer": answer, "domain": "wealth",
        "question": "命主财运如何？", "options": ["A 普通", "B 富裕", "C 破财", "D 平稳"],
        "source_year": "2024",
        "person": {
            "person_id": person_id, "name": f"命主{person_id}", "gender": "male",
            "birth": {"year": 1990, "month": 1, "day": 2, "hour": 3, "minute": 0, "place": "北京"},
        },
    }
