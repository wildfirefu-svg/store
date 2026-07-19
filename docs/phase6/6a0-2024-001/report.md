# 6A0 上下文消融报告（6a0-2024-001，2024）

- Δ_dev = -5.0pp（每 repeat：[-5.0, -5.0, -5.0]）
- 判定：**ROLLBACK**（≥+2 ADOPT；0≤Δ<+2 ADOPT_FOUNDATION；<0 ROLLBACK）
- call_failed：0（40 题；污染标注：否）
- 成本代理（prompt 字符数，非 token）：{"ctx_approved": {"prompt_chars_total": 78293, "prompt_chars_mean": 1957}, "ctx_legacy": {"prompt_chars_total": 10263, "prompt_chars_mean": 257}}

如实声明：API 未返回 token usage，成本对比为字符数代理；采样不可由 seed 复现。