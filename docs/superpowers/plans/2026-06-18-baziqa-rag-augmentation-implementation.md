# BaziQA 命例库增强：RAG + Few-shot + 校验器扩容（实施计划）

依据：[2026-06-18-baziqa-rag-augmentation-design.md](file:///f:/project/agent/docs/superpowers/specs/2026-06-18-baziqa-rag-augmentation-design.md)
基线：BaziQA 2025 holdout direct_choice = 25% (10/40)，run_id=`cf614db6`
目标：两种 method 的 rag_acc 均 ≥ 33%。

## 全局原则

- 严格 TDD：先写测试 → 看失败 → 实现 → 看通过。
- 每个 Task 完成后跑相关 focused 测试 + `python -m pytest -q -m "not e2e"` 至少一次。
- 不引入 GPU 依赖；本地 embedding 优先 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（与项目现有依赖兼容性更好），失败回退到 DeepSeek embedding API。
- 任何改动都加 flag：`BAZI_RAG=1` 或 `--rag`，默认关。
- 不能让 holdout 文件路径混进检索路径，[case_index.py](file:///f:/project/agent/case_index.py) 启动时硬断言。

## 文件总览

| 类型 | 路径 |
|------|------|
| 新建模块 | [bazi_features.py](file:///f:/project/agent/bazi_features.py) |
| 新建模块 | [case_index.py](file:///f:/project/agent/case_index.py) |
| 新建模块 | [rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py) |
| 扩容模块 | [bazi_report_validator.py](file:///f:/project/agent/bazi_report_validator.py) |
| 数据文件 | [knowledge-base/baziqa_rules.yaml](file:///f:/project/agent/knowledge-base/baziqa_rules.yaml) |
| 服务集成 | [api_server.py](file:///f:/project/agent/api_server.py) |
| 评测集成 | [benchmark/runners/run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py) |
| 评测脚本 | [scripts/verify_baziqa_rag_lift.ps1](file:///f:/project/agent/scripts/verify_baziqa_rag_lift.ps1) |
| 验收报告 | [docs/BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md) |

测试文件：

| 测试 | 路径 |
|------|------|
| 单元 | [tests/test_bazi_features.py](file:///f:/project/agent/tests/test_bazi_features.py) |
| 单元 | [tests/test_case_index.py](file:///f:/project/agent/tests/test_case_index.py) |
| 单元 | [tests/test_rag_prompt_builder.py](file:///f:/project/agent/tests/test_rag_prompt_builder.py) |
| 扩容 | [tests/test_bazi_report_validator.py](file:///f:/project/agent/tests/test_bazi_report_validator.py)（追加 case） |
| 集成 | [tests/test_api.py](file:///f:/project/agent/tests/test_api.py)（追加 RAG flag case） |

## Task 1：bazi_features 特征提取

1. 写 [tests/test_bazi_features.py](file:///f:/project/agent/tests/test_bazi_features.py)
   - `test_extract_returns_text_blob_and_structured_keys`
   - `test_text_blob_contains_day_master_and_month_branch`
   - `test_structured_birth_decade_bucketed`
   - `test_handles_missing_fields_gracefully`
2. 实现 [bazi_features.py](file:///f:/project/agent/bazi_features.py)：
   - `extract(chart) -> {"text_blob": str, "structured": dict}`
   - `text_blob` 长度 ≤ 600 字。
3. 跑 `python -m pytest tests/test_bazi_features.py -q` 全绿。

## Task 2：case_index 命例库

1. 写 [tests/test_case_index.py](file:///f:/project/agent/tests/test_case_index.py)
   - `test_rejects_holdout_corpus_path`：传入 holdout 路径必须 raise `ValueError`。
   - `test_top_k_returns_at_most_k_unique_cases`
   - `test_filter_by_day_master_when_set`
   - `test_falls_back_to_keyword_when_embed_fn_raises`
2. 实现 [case_index.py](file:///f:/project/agent/case_index.py)：
   - `class CaseIndex` 接受 `corpus_path` 与可选 `embed_fn`。
   - `__init__` 时 raise 如果路径 basename 包含 `holdout`。
   - 内置 BM25 fallback（用 `rank_bm25` 或简洁 TF-IDF 自实现，不要引入新依赖；自实现即可）。
   - 命例文档单元 = "命主级"，把同一命主的所有题答案揭示拼成 `answered_facts`。
3. 跑 `python -m pytest tests/test_case_index.py -q` 全绿。

## Task 3：rag_prompt_builder

1. 写 [tests/test_rag_prompt_builder.py](file:///f:/project/agent/tests/test_rag_prompt_builder.py)
   - `test_disabled_returns_base_prompt_unchanged`
   - `test_enabled_injects_top_k_cases_block`
   - `test_total_length_capped_to_8000_chars`
   - `test_injected_cases_marked_as_reference_only`
2. 实现 [rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py)：
   - `build_system_prompt(base_system, chart, case_index, enable_rag)`。
   - 当 `enable_rag=False` 时返回 `base_system` 原值。
3. 跑 `python -m pytest tests/test_rag_prompt_builder.py -q` 全绿。

## Task 4：报告校验器扩容（规则反推）

1. 在 [tests/test_bazi_report_validator.py](file:///f:/project/agent/tests/test_bazi_report_validator.py) 追加：
   - `test_loads_extra_rules_from_yaml`：YAML 中规律命中时，违反者被标记。
   - `test_yaml_rule_requires_min_support_3`：少于 3 例支持的规律不入校验。
2. 新增 [knowledge-base/baziqa_rules.yaml](file:///f:/project/agent/knowledge-base/baziqa_rules.yaml)，含 ≥ 5 条经过 corpus 反推的规律（每条记录 `support`、`confidence`、`pattern`、`expected_event`、`source_persons`）。
3. 扩容 [bazi_report_validator.py](file:///f:/project/agent/bazi_report_validator.py) 在 `validate_report_claims` 后追加 `_validate_against_yaml_rules`。
4. 跑 `python -m pytest tests/test_bazi_report_validator.py -q` 全绿。

## Task 5：服务层 + 评测层接入

1. 在 [tests/test_api.py](file:///f:/project/agent/tests/test_api.py) 追加：
   - `test_chat_stream_uses_rag_when_enabled`：`os.environ["BAZI_RAG"] = "1"` 时，fake `_stream_claude` 收到的 system prompt 含 "类似命例" 字段。
   - `test_chat_stream_disabled_when_flag_off`：默认不含。
2. 修改 [api_server.py](file:///f:/project/agent/api_server.py)：
   - 模块级懒加载 `CaseIndex` 单例（指向 corpus 路径）。
   - `/api/chat/stream` 在 `_stream_claude` 调用前调用 `rag_prompt_builder.build_system_prompt`。
3. 修改 [benchmark/runners/run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py)：
   - 增加 `--rag` flag；启用时把 system prompt 替换为 `build_system_prompt(...)`。
4. 跑 `python -m pytest tests/test_api.py -q` 与 `python -m pytest -q -m "not e2e"` 全绿。

## Task 6：评测脚本 + 报告

1. 新增 [scripts/verify_baziqa_rag_lift.ps1](file:///f:/project/agent/scripts/verify_baziqa_rag_lift.ps1)：
   - 入参 `-Holdout`（默认 [benchmark/datasets/baziqa_contest8_2025_holdout.jsonl](file:///f:/project/agent/benchmark/datasets/baziqa_contest8_2025_holdout.jsonl)）。
   - 顺序执行：`direct_choice` 无 RAG → `direct_choice` 启用 RAG → `structured_reasoning` 启用 RAG。
   - 解析 stdout 提取 accuracy；用 [docs/BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md) 模板写入对比表。
2. 跑脚本一次，生成 [docs/BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md)。
3. 校验：两种 method 的 rag_acc 均 ≥ 33%（baseline 25% + 8%）。
4. 把结果链接补到 [docs/BAZIQA_ACCEPTANCE_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCEPTANCE_REPORT.md) 的 "Latest Result" 段。

## 最终验证矩阵

```powershell
python -m pytest tests/test_bazi_features.py tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_report_validator.py -q
python -m pytest -q -m "not e2e"
python -m pytest tests/test_e2e.py -q --tb=short
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_rag_lift.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify_ui_report_quality.ps1
```

## 回退策略

- 如果 Task 1–5 完成但 Task 6 提升不达 8%：保留 RAG 代码与 flag，但默认 `BAZI_RAG=0`，把 [docs/BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md) 标 `BLOCKED` 并附调优 TODO；不允许把"开了反而更差"作为合格结果。
- 任何 Task 中的回归（focused / e2e 失败）必须在原地修复后才可继续下一 Task。

## 注意事项

- 性能：embedding 首次构建期 ≤ 30s；常驻进程内不重复构建。
- 隐私：corpus 已在仓内标注 BaziQA 来源；不收集真实用户命主进入索引。
- 兼容性：所有改动都需保留"BAZI_RAG 默认关"的行为，避免影响现有 [tests/test_api.py](file:///f:/project/agent/tests/test_api.py)。
