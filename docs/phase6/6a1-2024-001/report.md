# 6A1 严格投票报告（6a1-2024-001，2024）

- T = 1.0（冻结链：{"mode": "dev", "rate_r1": 0.2, "action_r1": "probe_r2", "rate_r2": 0.7, "action_r2": "freeze", "sample_temperature": 1.0}）
- Δ1（vote5−single@T，同源）= -3.33pp（每 repeat：[-7.5, 2.5, -5.0]）
- Δ2（vote5−single@0，锚定）= -10.0pp（每 repeat：[-17.5, -5.0, -7.5]）
- 准确率 vote5/single@T/anchor：[0.25, 0.375, 0.35] / [0.325, 0.35, 0.4] / [0.425, 0.425, 0.425]
- unresolved 率：0.25（>20% 为显著发现，不否决）
- 四格 vote5×single@T：{"both": 28, "vote5_only": 11, "single_t_only": 15, "neither": 66}
- 四格 vote5×anchor：{"both": 32, "vote5_only": 7, "anchor_only": 19, "neither": 62}
- 成本代理（prompt_chars_proxy）：vote5/single@T/anchor 总字符 = {'vote5': 153945, 'single_t': 30789, 'anchor': 30789}；比值 5.0 / 5.0；trimmed mean 251.3
- 准确率 trimmed mean（附列，不入 gate）：{'vote5': 0.325, 'single_t': 0.3583, 'anchor': 0.425}
- by_domain（设计 §2.1）：{"annual_fortune": {"vote5": 0.6667, "single_t": 1.0, "anchor": 1.0, "delta1_pp": -33.33, "delta2_pp": -33.33, "n": 3}, "career": {"vote5": 0.3333, "single_t": 0.4167, "anchor": 0.5, "delta1_pp": -8.33, "delta2_pp": -16.67, "n": 12}, "family": {"vote5": 0.6667, "single_t": 0.6667, "anchor": 0.5, "delta1_pp": 0.0, "delta2_pp": 16.67, "n": 6}, "health": {"vote5": 0.3333, "single_t": 0.5, "anchor": 1.0, "delta1_pp": -16.67, "delta2_pp": -66.67, "n": 6}, "relationship": {"vote5": 0.3333, "single_t": 0.2619, "anchor": 0.3571, "delta1_pp": 7.14, "delta2_pp": -2.38, "n": 42}, "study": {"vote5": 0.0, "single_t": 0.1667, "anchor": 0.0, "delta1_pp": -16.67, "delta2_pp": 0.0, "n": 6}, "unknown": {"vote5": 0.3095, "single_t": 0.3571, "anchor": 0.4286, "delta1_pp": -4.76, "delta2_pp": -11.9, "n": 42}, "wealth": {"vote5": 0.0, "single_t": 0.3333, "anchor": 0.0, "delta1_pp": -33.33, "delta2_pp": 0.0, "n": 3}}
- call_failed：0（污染标注：否）
- 判定：**ROLLBACK**

如实声明：API 未返回 token usage（成本为 prompt 字符 × 调用数代理）；采样不可由 seed 复现；40 题样本，2 题即 5pp，禁止过度表述。逐题明细见 case_details.jsonl。