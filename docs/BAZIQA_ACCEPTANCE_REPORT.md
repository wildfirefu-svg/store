# BaziQA Acceptance Report

## Test Commands

Core deterministic suite:

```powershell
python -m pytest -q -m "not e2e"
```

Browser E2E suite:

```powershell
python -m pytest tests/test_e2e.py -q -s --tb=short
```

BaziQA focused suite:

```powershell
python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py tests/test_baziqa_real_import_contract.py tests/test_baziqa_smoke_script_contract.py -q
```

Real BaziQA import:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_real_import.ps1 -SourceDir F:\project\BaziQA\data
```

Real model smoke:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_direct.jsonl -MaxCases 2 -Method direct_choice
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_structured.jsonl -MaxCases 2 -Method structured_reasoning
powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_smoke.ps1 -Dataset .tmp\baziqa_smoke_multiturn.jsonl -MaxCases 2 -Method multi_turn
```

Dashboard verification:

```text
http://127.0.0.1:8000/benchmark
```

## Latest Result

- BaziQA focused suite: PASS, `31 passed, 1 skipped`, date=2026-06-17.
- Core deterministic suite: PASS, `257 passed, 1 skipped, 6 deselected, 1 warning`, date=2026-06-17.
- Browser E2E suite: PASS, `6 passed`, date=2026-06-17.
- Smoke fixture guard: PASS, `scripts/verify_baziqa_smoke.ps1` generated `.tmp\baziqa_smoke_test.jsonl` with 2 rows before aborting without API key.
- Smoke key loading: PASS, `scripts/verify_baziqa_smoke.ps1` accepts `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` and local `.deepseek_key` / `.anthropic_key` files; key-file-only smoke produced run_id=`8adb8352`.
- Real BaziQA import: PASS, source=`F:\project\BaziQA\data`, output=`benchmark/datasets/baziqa_contest8_2021_2025.jsonl`, rows=688, years=`2021, 2022, 2023, 2024, 2025`, date=2026-06-17.
- Real model smoke: PASS, provider=deepseek, methods=`direct_choice, structured_reasoning, multi_turn`, max_cases=2, run_ids=`bd4af201, 78a0c16c, a45bf9ca`, date=2026-06-17.
- Dashboard verification: PASS, url=`http://127.0.0.1:8000/benchmark`, run_id=`a45bf9ca`, screenshot=`reports/baziqa_dashboard_acceptance.png`, browser console errors=0, date=2026-06-17.
- Report helper scripts: PASS, `scripts/test_all_reports_e2e.py` returned `PASS=7, WARN=0, FAIL=0`; `scripts/test_all_reports_edge.py` returned `OK=25, FAIL=0`.
- UI report quality smoke: PASS, command=`powershell -ExecutionPolicy Bypass -File scripts/verify_ui_report_quality.ps1`, result=`report_chars=4075, table_count=5, has_disclaimer=True, has_validation_note=False, has_connection_error=False, bad_patterns=[]`, date=2026-06-18.
- BaziQA 2025 holdout baseline: PASS, command=`python benchmark/runners/run_benchmark.py --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl --model-runner --provider deepseek --model deepseek-v4-pro --max-cases 40 --method direct_choice`, result=`run_id=cf614db6, accuracy=25% (10/40), evidence=100%, safety=100%`, date=2026-06-18. 用作后续 RAG / Few-shot / 校验器扩容改进的对比基线。
- BaziQA RAG lift evaluation: BLOCKED (real API, deterministic), command=`temperature=0; baseline-direct + rag-direct + rag-structured on 2025 holdout`, result=`baseline-direct=22.5% (9/40, run e7702f6d); rag-direct=27.5% (11/40, run b6678bbc, +5.0pp); rag-structured=32.5% (13/40, run 5be0a212, +10.0pp)`, report=[BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md), reason=`direct 未达到 baseline+8pp，structured 未达到 40% gate`, date=2026-06-18。
- BaziQA repeated evaluation: BLOCKED (real API, repeats=1), command=`python scripts/run_baziqa_repeated_eval.py --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl --provider deepseek --model deepseek-v4-pro --max-cases 40 --repeats 1 --temperature 0`, result=`baseline-direct=32.5% (run 63e55767); rag-direct=30.0% (run 1f6f816c); rag-structured=32.5% (run 016ee6de)`, report=[BAZIQA_REPEATED_EVAL_REPORT.md](file:///f:/project/agent/docs/BAZIQA_REPEATED_EVAL_REPORT.md), date=2026-06-18。
- BaziQA LOVO evaluation: BLOCKED (real API), command=`powershell -ExecutionPolicy Bypass -File scripts/verify_baziqa_lovo.ps1 -MaxCases 40`, result=`2021=35.0%, 2022=40.0%, 2023=22.5%, 2024=35.0%, 2025=27.5%, mean=32.0%, min=22.5%`, report=[BAZIQA_LOVO_REPORT.md](file:///f:/project/agent/docs/BAZIQA_LOVO_REPORT.md), reason=`mean < 40% 且 min < 30%`, date=2026-06-18。
- BaziQA accuracy evaluation hardening: PASS (implementation/non-network), commands=`python -m pytest tests/test_claude_api.py tests/test_benchmark_runner.py tests/test_accuracy_stats.py tests/test_baziqa_split_by_year.py tests/test_bazi_features.py tests/test_case_index.py tests/test_rag_prompt_builder.py -q`, result=`37 passed`; deterministic temperature 入参、`AccuracyExact` 输出、`benchmark.reports.accuracy_stats`、`benchmark/runners/split_baziqa_by_year.py`、领域感知检索、`scripts/run_baziqa_repeated_eval.py`、`scripts/verify_baziqa_lovo.ps1` 等已落地。
- BaziQA few-shot ablation: PARTIAL (real API, deterministic), command=`python scripts/run_baziqa_fewshot_ablation.py --max-cases 40 --temperature 0 --fewshot-n 3`, result=`baseline-direct=25.0% (b507a32f); direct-fewshot=27.5% (badb8cd3, +2.5pp); rag-direct=32.5% (5d9babc6); rag-direct-fewshot=22.5% (2ffee399, -10pp vs rag-direct); rag-structured=42.5% (6508583c, +17.5pp 首次过 40% gate); rag-structured-fewshot=35.0% (c3bf031e, -7.5pp vs rag-structured)`, report=[BAZIQA_FEWSHOT_ABLATION_REPORT.md](file:///f:/project/agent/docs/BAZIQA_FEWSHOT_ABLATION_REPORT.md), date=2026-06-19。结论：few-shot 单独使用在 direct mode 下 +2.5pp，但与 RAG 叠加会导致严重的 context dilution，准确率下降；rag-structured 单跑 42.5% 后续已证明不稳定。
- BaziQA rag-structured stability: BLOCKED (real API, deterministic), command=`python scripts/run_baziqa_repeated_eval.py --max-cases 40 --repeats 3 --temperature 0 --configs rag-structured --output docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md`, result=`run 267d34d4=27.5% (11/40); run d373b30c=35.0% (14/40); run 620c0311=27.5% (11/40); mean=30.0%; min=27.5%; max=35.0%; stdev=4.3pp`, report=[BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_STRUCTURED_STABILITY_REPORT.md), reason=`mean < 40% 且 min < 35%，42.5% 乐观单跑未复现`, date=2026-06-19。
- BaziQA RAG deterministic tie-break: PASS (implementation/non-network), files=[case_index.py](file:///f:/project/agent/case_index.py), [test_case_index.py](file:///f:/project/agent/tests/test_case_index.py), result=`CaseIndex.top_k_cases` now sorts tied scores by `person_id/birth_year/name`; command=`python -m pytest tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_features.py tests/test_benchmark_runner.py -q`, result=`28 passed`, date=2026-06-19。
- BaziQA per-case trace export: PASS (implementation/non-network), files=[run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py), [test_benchmark_runner.py](file:///f:/project/agent/tests/test_benchmark_runner.py), result=`--case-details-jsonl` exports full per-case raw_answer/predicted_answer/correct/rag_trace JSONL and now writes incrementally per completed case; command=`python -m pytest tests/test_benchmark_runner.py tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_features.py -q`, result=`30 passed`, date=2026-06-19。
- BaziQA trace diagnosis: PASS (real API diagnostic), files=[BAZIQA_TRACE_DIAGNOSIS_REPORT.md](file:///f:/project/agent/docs/BAZIQA_TRACE_DIAGNOSIS_REPORT.md), [analyze_baziqa_trace_runs.py](file:///f:/project/agent/scripts/analyze_baziqa_trace_runs.py), result=`rag-structured 10 cases × 3 runs: accuracy=50.0%/60.0%/40.0%; prediction unstable=7/10; correctness flips=4/10; RAG top-k unstable=0/10`, conclusion=`variance is primarily model/API output instability under identical RAG context, not retrieval ordering instability`, date=2026-06-19。
- BaziQA strict choice parser + confidence prompt contract: PASS (implementation/non-network), files=[benchmark/scorers/choice_accuracy.py](file:///f:/project/agent/benchmark/scorers/choice_accuracy.py), [benchmark/formatters/baziqa_prompt.py](file:///f:/project/agent/benchmark/formatters/baziqa_prompt.py), [tests/test_benchmark_choice_accuracy.py](file:///f:/project/agent/tests/test_benchmark_choice_accuracy.py), result=`extract_choice_with_meta` supports final_answer > confidence > legacy fallback; structured prompt requires confidence lines and `最终答案：X`; command=`python -m pytest tests/test_benchmark_choice_accuracy.py tests/test_baziqa_prompt_formatter.py -q`, result=`9 passed`, date=2026-06-20。
- BaziQA configurable RAG k + parser metadata: PASS (implementation/non-network), files=[benchmark/runners/run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py), [tests/test_benchmark_runner.py](file:///f:/project/agent/tests/test_benchmark_runner.py), result=`--rag-k` CLI argument; per-case detail includes `parser_source`, `parser_valid`, `rag_k`; command=`python -m pytest tests/test_benchmark_runner.py -q`, result=`13 passed`, date=2026-06-20。
- BaziQA k-ablation script: PASS (implementation/non-network), files=[scripts/run_baziqa_k_ablation.py](file:///f:/project/agent/scripts/run_baziqa_k_ablation.py), [tests/test_baziqa_k_ablation.py](file:///f:/project/agent/tests/test_baziqa_k_ablation.py), result=orchestrates k=1/2/3 with repeats and produces Markdown report; command=`python -m pytest tests/test_baziqa_k_ablation.py -q`, result=`1 passed`, date=2026-06-20。
- BaziQA error attribution script: PASS (implementation/non-network), files=[scripts/analyze_baziqa_error_attribution.py](file:///f:/project/agent/scripts/analyze_baziqa_error_attribution.py), [tests/test_baziqa_error_attribution.py](file:///f:/project/agent/tests/test_baziqa_error_attribution.py), result=domain-level accuracy and error-type counts; command=`python -m pytest tests/test_baziqa_error_attribution.py -q`, result=`1 passed`, date=2026-06-20。
- BaziQA report quality gate: PASS (implementation/non-network), files=[scripts/verify_report_quality_gate.py](file:///f:/project/agent/scripts/verify_report_quality_gate.py), [tests/test_verify_report_quality_gate.py](file:///f:/project/agent/tests/test_verify_report_quality_gate.py), result=fails if any `error` severity validator issue exists; command=`python -m pytest tests/test_verify_report_quality_gate.py -q`, result=`2 passed`, date=2026-06-20。
- BaziQA P1 retrieval quality upgrade: PASS (implementation/non-network), files=[case_index.py](file:///f:/project/agent/case_index.py), [bazi_features.py](file:///f:/project/agent/bazi_features.py), [rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py), [benchmark/runners/run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py), result=`rag_k` default changed to 2; query question/options enter retrieval as `query_text`; CaseIndex boosts same domain, intent keyword overlap, gender, decade, branch text overlap; RAG prompt/trace include match reasons and score; command=`python -m pytest tests/test_case_index.py tests/test_rag_prompt_builder.py tests/test_bazi_features.py tests/test_benchmark_runner.py -q`, result=`36 passed`, date=2026-06-20。
- BaziQA P2 semantic retrieval upgrade: PASS (implementation + real API validation), files=[case_index.py](file:///f:/project/agent/case_index.py), [tests/test_case_index.py](file:///f:/project/agent/tests/test_case_index.py), [tests/test_rag_prompt_builder.py](file:///f:/project/agent/tests/test_rag_prompt_builder.py), [run_ecdec259.md](file:///f:/project/agent/docs/p2_real_api_output/run_ecdec259.md), [run_d33408bd.md](file:///f:/project/agent/docs/p2_refined_real_api_output/run_d33408bd.md), result=local semantic phrase overlap added to retrieval ranking; broad semantic noise filtered; full 40-case pre-refine real API result `9/40=22.5%`; refined 10-case smoke result `5/10=50.0%`; command=`python -m pytest -q -m "not e2e"`, result=`316 passed, 1 skipped, 7 deselected`, date=2026-06-20。

## Final Status

- BaziQA focused tests: PASS, command=`python -m pytest tests/test_baziqa_importer.py tests/test_baziqa_prompt_formatter.py tests/test_benchmark_choice_accuracy.py tests/test_benchmark_runner.py tests/test_benchmark_report.py tests/test_benchmark_regression_gate.py tests/test_baziqa_real_import_contract.py tests/test_baziqa_smoke_script_contract.py tests/test_baziqa_k_ablation.py tests/test_baziqa_error_attribution.py tests/test_verify_report_quality_gate.py -q`, result=`34 passed, 1 skipped`.
- Core deterministic suite: PASS, command=`python -m pytest -q -m "not e2e"`, result=`257 passed, 1 skipped, 6 deselected, 1 warning`.
- Browser E2E: PASS, command=`python -m pytest tests/test_e2e.py -q -s --tb=short`, result=`6 passed`.
- Real BaziQA import: PASS, result=`Imported rows: 688; Distinct years sampled: 2021, 2022, 2023, 2024, 2025; output=benchmark/datasets/baziqa_contest8_2021_2025.jsonl`.
- Real model smoke: PASS, result=`bd4af201 direct_choice accuracy=1.0; 78a0c16c structured_reasoning accuracy=0.5; a45bf9ca multi_turn accuracy=1.0`.
- Dashboard verification: PASS, result=`Benchmark Runs`, `Choice Accuracy`, `Evidence Coverage`, `Safety`, and markdown report panel rendered; console errors=0.
- Worktree cleanliness: PASS for project-relevant changes; `.codegraph` generated local state was restored, and remaining changes are intentional source/doc/test acceptance updates.

## Remaining Risks

- BaziQA original repository is cloned locally at `F:\project\BaziQA`; repeatability depends on that local upstream checkout remaining available.
- Real-model smoke depends on network and valid DeepSeek/Anthropic credentials.
- The dashboard screenshot is stored under ignored `reports/` as local evidence and is not intended for commit.
- `.codegraph` generated local state should not be committed; any future local drift should be restored before commit.
- `pytest` 中 `StarletteDeprecationWarning`（`starlette.testclient` 依赖 `httpx` 而非 `httpx2`）已在 [pytest.ini](file:///f:/project/agent/pytest.ini) 通过 `filterwarnings: ignore::starlette.exceptions.StarletteDeprecationWarning` 屏蔽，验证后 `258 passed, 1 skipped, 6 deselected` 输出不再出现 warning summary；TODO 在 fastapi/starlette/httpx 升级窗口统一迁移到 `httpx2`。
- 生成性 BaziQA 产物 `benchmark/datasets/baziqa_contest8_*.jsonl` 与 `tests/fixtures/baziqa/contest8_sample.jsonl` 已加入 `.gitignore`，保留为本地证据，不入仓。

## Current Stable Status / 当前稳定状态

- 解析器：`extract_choice_with_meta` 已落地，支持 `最终答案：X` > 置信度表 > 旧模式 > invalid。
- Prompt：structured reasoning prompt 已强制要求置信度表 + `最终答案：X`。
- RAG k：`run_benchmark.py` 支持 `--rag-k`，默认已按 P0 k-ablation 初步结果调整为 2，并在 trace 中记录 `rag_k`。
- 诊断脚本：k-ablation、error-attribution、report-quality-gate 均已实现并通过测试。
- 当前验收线仍不达标：`rag-structured` 3 次重复均值 30.0%，min 27.5%，max-min=7.5pp；需进一步降低模型/API 输出波动。

## BaziQA Accuracy And Judgment Improvement

- Bazi accuracy and judgment专项：**BLOCKED**.
- Refined P2 full 40-case run (run b99ddab3): **8/40 = 20.0%**, below 27.5% threshold and previous 30% baseline.
- Chart_input coverage: 100% (160/160). ✅
- Weak domains: unknown (14.3%), relationship (14.3%), health (0.0%).
- Decision: semantic overlap disabled; chart-structure scoring requires investigation (degraded vs baseline).
- Report: [BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md](file:///f:/project/agent/docs/BAZIQA_ACCURACY_JUDGMENT_IMPROVEMENT_REPORT.md)
- Domain action plan: [BAZIQA_DOMAIN_ACTION_PLAN.md](file:///f:/project/agent/docs/BAZIQA_DOMAIN_ACTION_PLAN.md)

## Next Steps / 下一步计划

- 当前核心矛盾已从“RAG 检索排序不稳定”转移到“模型/API 输出不稳定”。
- 后续重点：
  1. 在真实 holdout 上跑 `--rag-k` ablation，根据结果调整默认 k；
  2. 用新 parser 重复跑 `rag-structured` 3 次，验证 min/max 差距是否 ≤ 5pp；
  3. 若波动仍大，继续收紧 prompt / 增加解析后校验 / 使用确定性更高的模型；
  4. 进入 Milestone 2，做向量检索 + 日主/月令/五行结构化加权；
  5. 用 error-attribution 脚本识别低分领域，针对性补强 corpus。
- 详细路线图与执行命令见 [BAZIQA_PROJECT_ROADMAP.md](file:///f:/project/agent/docs/BAZIQA_PROJECT_ROADMAP.md)。
