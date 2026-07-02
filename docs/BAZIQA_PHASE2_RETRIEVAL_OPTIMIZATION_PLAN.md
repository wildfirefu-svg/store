# BaziQA Phase 2 检索优化方案

> **状态说明**：本文是 Phase 2 中途诊断与优化计划，其中部分问题已在 Phase 2.5 中修补。Phase 2 当前统一状态以 [PHASE2_STATUS_UNIFIED.md](file:///f:/project/agent/docs/PHASE2_STATUS_UNIFIED.md) 为准：Engineering Done / Evaluation NO-GO；Phase 2.5 Offline Candidate Improved / Reranker Runtime Blocked。

## 诊断结论

### 根因分析

1. **环境变量未设置导致 RAG 未启用**
   - `BAZI_RAG=1` 未设置 → `_get_bench_case_index()` 返回 `None`
   - `BAZI_RAG_VECTOR=1` 未设置 → 向量检索默认关闭
   - `BAZI_RAG_CORPUS` 未设置 → 语料库路径使用默认值

2. **检索结果高度同质化**（即使 RAG 启用时）
   - 所有查询召回相同的 2-3 个 cases
   - `score=None` 表明相似度计算未工作
   - `bazi_features.extract()` 可能对所有输入返回相似特征

3. **k-ablation 测试不完整**
   - 仅 run1 完成，run2/run3 为空
   - benchmark runner 在 CaseIndex 初始化时卡住（>10 分钟无输出）

## 优化方案

### 任务 1：修复环境变量配置

创建 `.env.baziqa_rag` 文件：
```
BAZI_RAG=1
BAZI_RAG_CORPUS=benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl
BAZI_RAG_VECTOR=1
BAZI_RAG_VECTOR_MODE=st
BAZI_RAG_VECTOR_MODEL=BAAI/bge-small-zh-v1.5
BAZI_RAG_STRUCTURED_WEIGHT=1.0
BAZI_RAG_SEMANTIC_WEIGHT=1.0
BAZI_RAG_VECTOR_WEIGHT=1.5
```

### 任务 2：修复 CaseIndex 初始化性能问题

问题：`CaseIndex.__init__` 中加载 sentence-transformers 模型耗时过长，且每次 benchmark 调用都重新初始化。

解决方案：
1. 使用全局单例缓存 `_BENCH_CASE_INDEX`（已在代码中但需确保正确工作）
2. 预加载模型到内存，避免重复初始化
3. 添加超时机制，如果模型加载超过 30 秒则使用 TF-IDF fallback

### 任务 3：验证特征提取区分度

运行诊断脚本：
```python
from bazi_features import extract

# 加载 5 个不同的 holdout cases
# 比较它们的特征向量差异
# 如果相似度 > 0.9，说明特征提取有问题
```

### 任务 4：修复 score=None 问题

在 `top_k_cases()` 中，`_score` 被计算但可能为 0 或负数。检查：
1. `adj = score + structured_score + chart_score + semantic_score + vector_score`
2. 如果所有分量都为 0，则 `_score=0` 但不会是 `None`
3. 问题可能在 `_resolve_rag_trace` 中 `item.get("_score")` 返回 None

### 任务 5：重新运行完整的 k-ablation

在修复上述问题后，运行：
```bash
# 设置环境变量
$env:BAZI_RAG="1"
$env:BAZI_RAG_VECTOR="1"
$env:BAZI_RAG_CORPUS="benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl"

# 运行 k-ablation
python scripts/run_baziqa_k_ablation.py \
  --dataset benchmark/datasets/baziqa_contest8_2025_holdout.jsonl \
  --provider deepseek --model deepseek-v4-pro \
  --method structured_reasoning --max-cases 40 --repeats 3
```

### 任务 6：如果检索仍无法提升，考虑替代方案

1. **Few-shot prompting**：不使用 RAG，直接在 prompt 中提供 3-5 个示例
2. **Self-consistency**：采样 5 次取多数投票
3. **Domain-specific rules**：为每个 domain 编写专门的判断规则
4. **Ensemble**：结合多个模型的输出

## 预期结果

- 修复环境变量后，retrieved_answer_leak 应该 > 0%
- 如果向量检索正常工作，准确率应从 27.5% 提升到 35%+
- 如果仍无法达到 35%，则确认瓶颈在 LLM 推理能力，需进入 Phase 3（reasoning stabilization）

## 下一步行动

请确认优先级：
1. 先修复环境变量和 CaseIndex 问题，重新运行 k-ablation
2. 或者直接跳过 Phase 2，进入 Phase 3（self-consistency / few-shot）
3. 或者先分析已有的 retrieval configs，尝试不同的配置组合
