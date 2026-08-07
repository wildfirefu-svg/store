---
name: quality-check
description: 运行模型质量检查和代码审计，验证八字计算准确性
trigger: 用户要求验证八字计算准确性、回归基线、幻觉检测或知识库缺口审计时使用；代码改动后需要领域级质量确认也适用
output: 质量报告摘要：总体结论（pass/fail/warn）、各组件准确率、回归项与针对警告的修复建议
validation: model_quality_test 与一致性检查命令退出码为 0 且无 FAIL 指标；失败时输出具体失败项而非笼统报错
---
# Quality Check Skill — 玄机子

Run model quality assessments and code audit tools for the BaZi project.

## Model Quality (八字计算准确性)

```bash
python quality/model_quality_test.py
```

Check output for:
- Accuracy scores per component (排盘/神煞/紫微/大运)
- Regression from previous baseline
- Any FAIL indicators

## Consistency Check

```bash
python tests/test_consistency.py
```

Verify cross-school rule consistency across the frozen 子平、滴天髓、盲派 fixtures. This command does not test repeated model-run determinism.

## Hallucination Validation

```bash
python tests/validate_hallucination.py path/to/report.md path/to/chart.json --strict
```

Replace both paths with the actual generated report and its source chart. Checks that AI-generated outputs don't contain fabricated data (fake dates, non-existent shensha, wrong element assignments).

`tests/expand_patterns.py` mutates the tracked pattern fixture and is a maintenance script, not a quality-check command. Do not run it during validation.

## Code Audit (quick)

```bash
python tools/audit_gaps.py
```

Checks for gaps in the knowledge base vs calculation engine.

## Report

Summarize:
- Overall score (pass/fail/warn)
- Any regressions
- Recommended fixes for warnings
