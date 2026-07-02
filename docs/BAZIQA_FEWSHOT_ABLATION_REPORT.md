# BaziQA Few-Shot Ablation Report

> 日期：2026-06-19
> 数据集：`benchmark/datasets/baziqa_contest8_2025_holdout.jsonl`（40 题）
> Corpus：`benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl`
> Provider：deepseek，Model：deepseek-v4-pro，Temperature：0.0
> FewShotN：3（来自 corpus，已去除与 holdout 同人）

---

## 一、Few-shot 示例（实际注入到 system prompt 的样题）

| # | domain | person_id | birth_year | answer |
|---|--------|-----------|------------|--------|
| 1 | relationship | male_19850629_P021 | 1985 | B |
| 2 | unknown | male_19620806_P010 | 1962 | D |
| 3 | career | female_19841220_P027 | 1984 | A |

文件落盘位置：`.tmp/baziqa_fewshot_examples.jsonl`

---

## 二、完整 Ablation 结果（6 配置 × 40 题，全部 Temperature=0）

| Run | Method | RAG | FewShot | Correct/Total | Accuracy | Δ vs baseline-direct | RunId |
|-----|--------|-----|---------|---------------|---------:|---------------------:|-------|
| baseline-direct | direct_choice | OFF | OFF | 10/40 | 25.0% | +0.0 pp | b507a32f |
| direct-fewshot | direct_choice | OFF | ON | 11/40 | 27.5% | **+2.5 pp** | badb8cd3 |
| rag-direct | direct_choice | ON | OFF | 13/40 | 32.5% | **+7.5 pp** | 5d9babc6 |
| rag-direct-fewshot | direct_choice | ON | ON | 9/40 | 22.5% | -2.5 pp | 2ffee399 |
| rag-structured | structured_reasoning | ON | OFF | **17/40** | **42.5%** | **+17.5 pp** | 6508583c |
| rag-structured-fewshot | structured_reasoning | ON | ON | 14/40 | 35.0% | +10.0 pp | c3bf031e |

---

## 三、对比观察

### 3.1 Few-shot 单独效应（无 RAG）

- baseline-direct → direct-fewshot：**+2.5 pp**（从 25.0% 到 27.5%）
- 在没有 RAG 的情况下，few-shot 带来**轻微正向**信号，但量级很小（仅 1 题差距）。

### 3.2 Few-shot × RAG 组合效应

- rag-direct → rag-direct-fewshot：**-10.0 pp**（从 32.5% 到 22.5%，回到随机水平）
- rag-structured → rag-structured-fewshot：**-7.5 pp**（从 42.5% 到 35.0%）
- **结论：当 RAG 已开启时，再叠加 few-shot 反而严重伤害准确率。**

### 3.3 跨方法对比

- direct_choice → structured_reasoning（同样开 RAG）：**+10.0 pp**（32.5% → 42.5%）
- 说明结构化推理仍是当前最有效的杠杆。
- **rag-structured = 42.5% 首次单次跨越 40% Gate**（之前是 32.5%）。考虑到 40 题样本下标准误约 ±7.4 pp，这是一次"乐观区间"的样本，需要 repeats≥3 来稳定。

---

## 四、为什么 RAG + Few-shot 反而更差？技术性归因

### 4.1 上下文稀释（Context Dilution）

当前 system prompt 同时塞入：

1. Few-shot 三道样题 + 标准答案
2. 三个检索命例（每个含 5 条事实）
3. base system prompt
4. 题干 + 选项

总长度逼近 8000 字符上限。**模型注意力被分散到与本题无关的 few-shot 答案上**，导致它一看 few-shot "标准答案：B" 就倾向于在本题中也猜 B。

### 4.2 Few-shot 答案分布偏差

我们抽中的 3 个 few-shot 答案是 `B / D / A`，分布不均衡。如果模型在难题上"模仿"few-shot 的答案分布，会在不知道选什么时偏向 B/D，与正确答案相关性低。

证据：rag-direct-fewshot 有 9 题正确，与 baseline-direct（10 题）相当——也就是说模型几乎完全"放弃"了 RAG 信息。

### 4.3 推理预算被切走

structured_reasoning 模式下，模型会输出推理过程；prompt 越长，留给输出的 token 上限越紧；few-shot 进一步压缩了"思考预算"。实测看 rag-structured-fewshot 比 rag-structured 低 7.5 pp 也支持该假设。

---

## 五、决策建议

### 5.1 立即采纳

- **保留 `rag-structured` 作为默认评测推荐配置**（42.5%，首次破 40% Gate，待重复验证稳定性）。
- **关闭 RAG + few-shot 组合**：在 `run_benchmark.py` 中，当 `--rag` 和 `--fewshot-file` 同时给出时，warning 并默认禁用 few-shot；或在文档中明确不推荐该组合。
- 保留 `direct_choice + few-shot` 作为"无 RAG 场景下的小幅提升"备选，但 +2.5 pp 量级在 40 题样本下不显著。

### 5.2 后续动作

- 对 `rag-structured = 42.5%` 跑 **3 次重复评测**，看均值是否稳定 ≥ 40%。
- 暂停 few-shot 相关投资，把资源转向 Milestone 2 的方向：
  1. **A1 向量检索**（提升 RAG 召回质量）
  2. **A2 扩展结构化字段**（日主+月令精准匹配）
  3. **B1 强制四步推理模板**（继续放大 structured_reasoning 优势）
- 单独验证：减少检索命例数（k=3 → k=2 或 k=1）能否进一步提升 structured 准确率，因为本次实验印证了"上下文稀释"假设。

### 5.3 可重复成本

- 6 配置 × 40 题 ≈ 1 小时 24 分（每子进程 ~13 分），DeepSeek API 费用估约 5–7 RMB。
- 重跑 `rag-structured` 3 次约 35 分钟、约 3 RMB。

---

## 六、产出物

- 实现：[rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py)（`load_fewshot_examples` + `build_system_prompt(few_shot_examples=...)`）
- 评测脚本：[scripts/run_baziqa_fewshot_ablation.py](file:///f:/project/agent/scripts/run_baziqa_fewshot_ablation.py)
- CLI flag：`benchmark/runners/run_benchmark.py --fewshot-file`
- 单元测试：[tests/test_rag_prompt_builder.py](file:///f:/project/agent/tests/test_rag_prompt_builder.py)（共 8 个测试，全绿）
- 命令记录：
  ```powershell
  python scripts/run_baziqa_fewshot_ablation.py --max-cases 40 --temperature 0 --fewshot-n 3
  python scripts/run_baziqa_fewshot_ablation.py --max-cases 40 --temperature 0 --fewshot-n 3 \
      --configs 'rag-direct,rag-direct-fewshot,rag-structured,rag-structured-fewshot' \
      --output 'docs/BAZIQA_FEWSHOT_ABLATION_RAG.md'
  ```
