# BaziQA 准确度提升思路与行动计划

> 基线：2025 holdout structured RAG = 32.5%（当前最高可达配置）
> 目标：结构化 RAG 单次 ≥ 40%，LOVO mean ≥ 40%，LOVO min ≥ 30%
> 更新日期：2026-06-18

---

## 一、问题诊断：当前系统的瓶颈在哪里

### 1.1 从数据反推

现有 688 条命例（2021–2025），RAG 检索上限取决于两件事：

1. **检索召回率**：对某一题，top-k 里是否存在"能直接帮助判断的命例"。
2. **模型吸收利用率**：命例已经召回，但模型是否真的会参考它来推理。

当前观察到的信号：

- baseline-direct 约 22.5%，rag-structured 32.5%，提升 10 pp → 说明检索 **有** 信号，但不强烈。
- 2022 LOVO 达到 40.0%，而 2023 仅 22.5% → 说明"命例覆盖是否与 holdout 题目匹配"对结果影响极大。
- 4 选 1 的随机基线是 25%，32.5% 其实只比随机高 7.5 pp → 说明系统对八字的实质性推理能力仍然很弱。

### 1.2 从代码反推

当前检索评分（`case_index.CaseIndex.top_k_cases`）的构成是：

- decade 匹配 → 基础分
- query_domain 匹配 → +0.8
- 地支关键词重叠 → min(overlap × 0.1, 0.4)
- text_blob 关键词重叠 → 额外分

这意味着**当前检索本质是"结构化字段的加权布尔检索 + 简单关键词重叠"**，缺少：

1. 日主/十神的实质性相似度（例如"丁火生于巳月"应优先匹配"丁火生于巳月"，而不是"任意命中带丁火"）。
2. 问题意图的语义相似度（文本关键词区分不了"是否会离婚"和"是否会再婚"）。
3. 更丰富的结构化特征（五行缺补、大运流年、格局标签等）。
4. 检索结果的**质量过滤**（当前只要命中关键词就提升，没有区分"该命例是否确实给出了判断依据"）。

另一方面，当前 RAG prompt 的构建方式（`rag_prompt_builder.build_system_prompt`）把命例作为"参考文本"附加给 system prompt，但：

- 没有显式要求模型"先看命例再作答"。
- 没有对命例与问题的**匹配理由**做解析呈现。
- k 的取值是固定的，可能引入噪声命例。

---

## 二、提升思路总览（分 6 个方向）

| 方向 | 手段 | 预期提升 | 复杂度 |
|------|------|----------|--------|
| A. 检索增强 | 语义向量检索 + 更强的结构化匹配 | +5–10 pp | 中 |
| B. 推理方式 | 结构化 Reasoning + Self-consistency | +5–12 pp | 中 |
| C. 提示优化 | Chain-of-thought / Few-shot 模板 / Self-refine | +3–8 pp | 低 |
| D. 规则库扩容 | 用 corpus 反推 YAML 规律，校验 + rerank | +3–7 pp | 中 |
| E. 语料增强 | 扩充 BaziQA 以外的公开命例库 | +5–15 pp | 高 |
| F. 评测工程 | 更大的 holdout、按领域拆分 Gate | 不直接提升准确率，但让 Gate 可信 | 低 |

### 2.1 方向 A：检索增强（最高优先级）

**A1. 加入向量检索**

- 在 `CaseIndex.__init__` 中对每个命例的 `text_blob` 用本地模型（`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`）或 DeepSeek Embedding API 生成 embedding。
- 对查询，同样生成 embedding，用 cosine 相似度作为一路分数，与当前结构化分数做加权融合（例如 `final = 0.4 * sim + 0.6 * structured_score`）。
- 预期效果：解决"问题意图语义相似度"的缺口，尤其对感情/健康这类关键词多样的领域。
- 实施位置：`case_index.py`，加 `embedding_cache` 字段（持久化到 `.tmp/` 避免重复构建）。

**A2. 强化结构化匹配**

- 把 `bazi_features.extract` 中的结构化字段从 `{gender, birth_decade, day_master_gan, branches, query_domain}` 扩展到：
  - `day_master_gan`（已有）
  - `month_zhi`（已有）
  - `day_gan_zhi`（日主 + 日支组合）
  - `five_elements_balance`（五行缺/盛，例如"缺金多火"）
  - `ten_god_summary`（十神在四柱中的分布标签）
  - `useful_god` / `avoid_god`（喜神/忌神，若有标注）
- 在 `top_k_cases` 中对"日主+月令完全一致"的命例给 **强 boost**（例如 +1.5），对"日主相同但月令不同"给中 boost（+0.8），对"五行缺补一致"给弱 boost（+0.3）。
- 预期效果：把当前"泛命中"改成"精准命中"，让命例的可借鉴性更高。
- 实施位置：`bazi_features.py` + `case_index.py`。

**A3. 检索 k 与命例上下文长度优化**

- 当前默认 `k` 值没有按题调整。做 ablation：k=3 / 5 / 8，看哪个最好。
- 对命例文本进行**摘要截断**：只保留与 query_domain 相关的问答片段，不是整份命主的所有事实。
- 实施位置：`rag_prompt_builder.py` 增加 `_trim_case_by_domain(case, query_domain)`。

### 2.2 方向 B：推理方式（第二优先级）

**B1. 结构化推理模板升级**

当前 `structured_reasoning` 的 prompt 让模型自行推理，但没有强制的推理结构。改成显式步骤：

```
请按以下步骤推理，最后给出选项：

1. 解析题干：命主性别/出生年份/日主/月令/问题领域 = ________。
2. 八字关键信息：五行分布 = ____，格局判断 = ____，喜忌神 = ____。
3. 类似命例（仅供参考，不直接等同于本题）：
   [检索到的命例逐条列出，含与本题的相似度评分]
4. 逐条分析选项 A/B/C/D，写出判断依据与置信度（0-1）。
5. 综合后选择：________（只写字母）。
```

- 预期效果：让模型"慢思考"，避免在四选一里直接拍脑袋。
- 实施位置：`benchmark/runners/run_benchmark.py` 的 `_resolve_system_prompt` / `build_system_prompt`。

**B2. Self-consistency（自一致性）**

- 对同一题，用不同"推理路径模板"生成 3 个 reasoning 结果，再做"多数投票"选出最终选项。
- 成本是 3 倍 API 调用，但对 40 题/年的评测量仍在可控范围。
- 实施位置：新增 `scripts/self_consistency_eval.py`。

**B3. 让模型显式做"命例证据引用"**

- 在推理步骤里强制模型回答："你参考了哪一条检索命例？它的哪句话支持你的选择？"
- 如果模型写不出具体引用，就降权——这也能间接让检索质量问题暴露出来。

### 2.3 方向 C：提示优化（低成本但有效）

**C1. Few-shot 模板**

- 从 corpus 中选 2–3 个"经典题+标准答案"作为 few-shot，放在 system prompt 开头，教模型期望的输出格式与推理风格。
- few-shot 示例必须与 holdout 严格去重（已由 `split_baziqa_by_year` 保证年份不交）。
- 实施位置：`rag_prompt_builder.py`，新增 `_build_few_shot_block`。

**C2. Chain-of-thought 中文化**

- 当前结构化推理是自由文本，改成"先写理由→再选答案"的强制两段式——让模型必须写理由，而不是直接给字母。
- 在评测脚本 `run_benchmark.py` 中抽取最后一个字母作为答案，忽略前面所有推理文本。

**C3. Self-refine 两段式**

- 第一轮让模型给一个"初判 + 证据"。
- 第二轮把初判和题目再喂给模型，让它"自我批评并修正"。
- 对结构化题可能带来 +3–5 pp 的提升（经验数值，需实测验证）。

### 2.4 方向 D：规则库扩容

**D1. corpus 反推 YAML 规律**

- 已经有 `bazi_report_validator.load_yaml_rules` 的骨架；现在需要扩充 `knowledge-base/baziqa_rules.yaml`。
- 方法：对 688 条 corpus 做"结构化特征 → 事件标签"的简单统计，例如：
  - "丁火生于巳月 + 感情题 = 70% 选 B"（伪数据，仅示意）
- 把高 `support` 且高 `confidence` 的模式录入 YAML。
- 让规则库同时服务两个角色：
  1. **生成时**：作为 system prompt 中的"已知规律"段。
  2. **评测时 rerank**：模型给 4 个选项各打一个理由，再用规则库筛选最不矛盾的选项。

**D2. 2023 弱年份专项**

- 单独跑 2023 holdout 的每题检索结果，人工审阅：是命例不相关？还是模型判断错误？
- 针对 2023 的问题风格，新增适配的提示模板或规则。

### 2.5 方向 E：语料增强

- 当前 corpus 仅 BaziQA contest8，规模 688 条，对 RAG 而言偏小。
- 可选扩充：
  1. 公开八字命例书（如《穷通宝鉴》《滴天髓》中的案例）。
  2. 其他可公开获得的八字 contest 数据集。
  3. 用模型从 corpus 做 paraphrase 生成增广命例（但必须标注"合成"，避免数据泄露）。
- 风险：版权与许可；需在项目 README 中标注来源。
- 预期：若把 corpus 从 688 扩到 3000+，检索覆盖度应有显著提升。

### 2.6 方向 F：评测工程（让 Gate 更可信）

**F1. holdout 规模提升**

- 40 题/年 × 5 年 = 200 题总评测量；标准误约 7 pp，导致 Gate 判断会"偶尔通过、偶尔不通过"。
- 建议把每年 holdout 扩充到 80–100 题（BaziQA contest8 本身有更多题可用，仅需调整抽样）。

**F2. 按领域拆 Gate**

- 报告中加 domain-level 准确率段：事业 / 财运 / 感情 / 健康 / 家庭 / 流年 / 学业 / 性格。
- 每个领域的最小准确率 ≥ 25%（高于随机），否则标记 WARN。
- 这让"健康领域特弱"这种问题更早暴露，而不是被总准确率掩盖。

**F3. 把重复评测作为默认**

- 默认 `run_baziqa_repeated_eval.py --repeats 3` 而不是 1。
- 报告强制要求均值 + 95% Wilson 置信区间。

---

## 三、近期行动方案（分 Milestone）

### Milestone 1：一周内可见收益（低代码量、高信号）

1. **F2 / F3**：让 `run_benchmark.py` 输出 domain-level accuracy，并把 `run_baziqa_repeated_eval.py` 的默认 `--repeats` 提为 3。
2. **C1**：新增 few-shot 模板（3–5 个经典题示例），做一次 ablation：`with few-shot` vs `without few-shot`。
3. **B1 简化版**：把结构化推理改成"强制四步模板"，跑一次 2025 holdout，观察是否提升。

预期结果：把结构化 RAG 从 32.5% 推到 **35%–37%** 附近。

### Milestone 2：两到三周内的关键改造（中等代码量）

1. **A1**：引入本地 embedding（`sentence-transformers`）做向量检索。
2. **A2**：在 `bazi_features.extract` 扩展结构化字段（五行平衡、十神、格局标签）。
3. **A3**：检索 k ablation + 按领域修剪命例上下文。
4. **D1**：扩充 `baziqa_rules.yaml` 到 ≥ 20 条高置信规律。

预期结果：结构化 RAG 推到 **38%–42%**，有机会首次通过 40% Gate。

### Milestone 3：中期投入（1–2 月）

1. **B2 / B3**：Self-consistency 与证据引用强制。
2. **D2**：对 2023 弱年份做专项修复。
3. **E**：扩充 corpus 到 2000+ 条（需版权审查）。

预期结果：LOVO mean 到 **40%+**，LOVO min 到 **30%+**。

---

## 四、决策建议

1. **不要仅靠 "更大的 k" 或 "更长的 prompt"**：当前检索质量是瓶颈，而不是 prompt 长度。
2. **把 "2023 为什么差" 作为首个根因分析**：把最薄弱的年份拉起来，对 LOVO min 提升立即可见。
3. **保留 `temperature=0` 作为评测默认**：否则无法比较不同版本。
4. **先跑 Milestone 1 的 few-shot ablation**：如果 few-shot 能把 32.5% 推到 37%，说明模型"知道怎么做只是被 prompt 隐藏了"，此时应优先做 prompt/推理工程；如果 few-shot 几乎无提升，说明瓶颈确实在检索/语料。
5. **把 gate 决策建立在 repeats≥3 的均值上**，并报置信区间——避免"我昨天跑了 41% 就以为过了"的情况。

---

## 五、验证脚本（已有 + 待补充）

已有自动化脚本：

- [scripts/verify_baziqa_rag_lift.ps1](file:///f:/project/agent/scripts/verify_baziqa_rag_lift.ps1)：RAG Lift 评测。
- [scripts/run_baziqa_repeated_eval.py](file:///f:/project/agent/scripts/run_baziqa_repeated_eval.py)：重复评测。
- [scripts/verify_baziqa_lovo.ps1](file:///f:/project/agent/scripts/verify_baziqa_lovo.ps1)：LOVO 评测。
- [benchmark/runners/split_baziqa_by_year.py](file:///f:/project/agent/benchmark/runners/split_baziqa_by_year.py)：按年拆分 corpus/holdout。

待补充（Milestone 1–2）：

- `scripts/domain_breakdown_eval.py`：按领域输出准确率与置信区间。
- `scripts/ablation_k_eval.py`：对 top-k 做 3/5/8 ablation。
- `scripts/self_consistency_eval.py`：Self-consistency 多数投票。
- `scripts/analyze_2023_weak_year.py`：输出 2023 每题的检索命例与模型推理，供人工审阅。

所有新脚本应遵循与现有脚本一致的惯例：
- 默认 `temperature=0`；
- 输出 `AccuracyExact: correct/total=value` 便于统一解析；
- 生成 markdown 报告到 `docs/`。
