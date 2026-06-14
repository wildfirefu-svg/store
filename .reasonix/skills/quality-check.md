---
name: quality-check
description: 运行模型质量检查和代码审计，验证八字计算准确性
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

Verify that the same input produces the same output across runs.

## Hallucination Validation

```bash
python tests/validate_hallucination.py
```

Checks that AI-generated outputs don't contain fabricated data (fake dates, non-existent shensha, wrong element assignments).

## Pattern Expansion

```bash
python tests/expand_patterns.py
```

Verifies that pattern matching covers edge cases.

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
