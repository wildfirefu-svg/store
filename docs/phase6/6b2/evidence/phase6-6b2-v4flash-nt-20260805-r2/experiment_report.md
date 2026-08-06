# 6B2 双管线报告
- Model protocol：DeepSeek-V4-Flash non-thinking
- Provider：deepseek
- Requested model：deepseek-v4-flash
- Thinking mode：disabled
- Run ID：phase6-6b2-v4flash-nt-20260805-r2
- Primary comparison：concurrent b1a_prime vs dual
- gate：**ROLLBACK**（dev）
- judge 触发率：0.5583（参照 0.579）
- parser rate：0.9742；call_failed：0
- 预算：scheduled 960 / attempted 837 / cap 1060
- B1-c advisory（非决策）：count 240，冻结 SHA 10e6b82f92fabd02b7e621b714d330a812f16e6b7aac7ad98adf4a0dd494eafa；gate_inclusion=False；historical deepseek-chat advisory only; excluded from all gates

如实声明：40 题/年度，2 题即 5pp；请求不携带 seed；B1-c 为 6B1 时段旧 run。