# Phase 7 错误归因分析设计（零 API）

**日期：** 2026-08-11
**状态：** v1.1（按 v2 产物回写同步：证据字段拆分、非循环 sanity check、Bonferroni 说明、实际特征集合；与 `docs/phase7/error-analysis/` v2 产物一致）
**输入：** Phase 7 r2 归档 `docs/phase7/phase7-mingli-v4flash-nt-20260811-r2/`（merged_details 160 行，107 错 / 53 对；SHA 按 git-canonical-lf 冻结，commit `0ce25f6`）
**产出：** `docs/phase7/error-analysis/`（统计数据 + 逐题分类 + 汇总报告）

---

## 1. 目标与非目标

**目标：** 对 107 道错题做可归因、可量化、可复核的错误分析，产出候选改进项及其覆盖题数。

**非目标（冻结）：**
- 不修改任何 prompt / 规则 / RAG / 代码（分析结论只进报告）；
- 不调用任何 LLM API；
- 不把 fetch 字节直取加固、torch 段错误等工程 backlog 混入本分析；
- 不启动任何新实验。

## 2. 数据与口径

- 错题集：merged_details 中 `correct=false` 的 107 行；对照组：`correct=true` 的 53 行。
- 题目元数据（year/category/question/options/birth_info）来自归档 `mingli_160.jsonl`，按题目 `case_id`（`mingli_ftb_*`）join；命盘分组用 `chart_case_id`。
- 模型推理原文取 detail 行 `raw_answer`；预测/期望取 `predicted_answer`/`expected_answer`。
- 全部统计脚本一次性落盘原始中间结果（JSON/JSONL），报告只引用落盘数字，不口头转述。

## 3. 分析任务（对应用户指令 1–4）

### A. 婚姻类深潜（38/44 错）
- 题型聚类：按 question 文本关键词归类（结婚应期/配偶特征/婚姻状况判断/离婚再婚等），统计各类错误率；
- 选项结构：正确/错误预测选项 letter 分布与混淆对（实际完成口径；选项文本长度差与迷惑项模式未单独立项，被 letter 分布分析取代）；
- 命盘信息缺口：错题的注入 astro 宫星覆盖（palace_stars 计数中位分割）与对照组比较；v1.1 增补盘面引用率（chinese_date / 宫星精确子串匹配，规则与逐题结果落盘于 quantitative_stats.json `chart_quote_rates`）。

### B. 7 个全错命盘（case_6/17/20/24/27/30/31）
- 盘级 vs 题级：同盘题目的 raw_answer 是否呈现共同的命盘读取/注入异常（如 astro 块字段缺失、盘信息被误读），还是各题独立的知识性错误；
- 逐盘给出判定：盘级解析/注入问题 / 共享知识盲区 / 疑似随机聚集。

### C. 错误类型分类（107 题全覆盖）
冻结分类法（每题恰好一个主类，允许附注）：

| 类别 | 定义 |
|---|---|
| `knowledge` | 命理知识/规则错误（用神、格局、应期推断等学理层面错误） |
| `chart_reading` | 命盘读取错误（把注入的盘信息读错/读漏，如宫位星曜、五行统计看错） |
| `relation_inference` | 关系推断错误（盘面对，但地支关系/十神关系推演错） |
| `question_misread` | 题意误解（答非所问，如问应期答成性质） |
| `option_confusion` | 选项混淆（推理方向对但选错 letter，或二选一选错） |
| `answer_format` | 答案格式问题（输出无法解析或解析到错误 letter；预期极少，因 parsed=160） |

分类由子代理分批阅读 raw_answer 完成，每题产出 `{case_id, chart_case_id, category, year, error_type, confidence, analyst_note, evidence_quote}`：`analyst_note` 为标注者概括，`evidence_quote` 为 raw_answer 的**逐字精确子串**（20–80 字，落盘后程序化子串校验 107/107）；chart_case_id/category/year 一律从 normalized dataset 机械重导（首轮 14 行手工误标教训）。主分类器拿不准的标 `confidence=low` 供汇总时复核。

### D. 特征富集量化（对照正确组）
对以下特征做错题组 vs 对照组的富集检验（Fisher 精确检验，α=0.05）：category、year、题长分位、注入 astro 宫星覆盖（中位分割）。v1.1 冻结两点：
- **多重比较说明**：实际检验 18 项，报告须给简单 Bonferroni 对照（婚姻类 0.0008×18≈0.0144，仍 <0.05）。
- **禁止循环检验**：`allwrong_chart_member` 之类"先按结果选盘再检验成员富集"的特征不得进入 Fisher。盘级异质性的非循环替代：同率零假设（p=107/160）+ Poisson-binomial 精确尾部（落盘 `allwrong_chart_sanity_check`：期望 4.30、观察 7、P(X≥7)=0.1292，不构成显著证据）。
输出每个特征的列联表与 p 值，明确"相关 ≠ 因果"。

## 4. 候选改进项（只列举，不实施）

每条候选改进必须给出：针对的错误类型、覆盖题数（按本分析的错题归因计数）、命盘级隔离下的验证路径。**不在本阶段修改 prompt。**

## 5. 密封与泛化诚实声明（冻结）

- 完整 160 题结果已看过 → 任何后续基于本题集的分割只能称"**确认集**"，不得宣称严格 held-out。
- 后续任何 prompt/规则实验的开发/验证分割必须按 `chart_case_id` 做**命盘级隔离**（同盘 4–6 题不得拆到两侧）。
- 若需证明泛化，必须新增独立密封题集。

## 6. 产出物清单

```text
docs/phase7/error-analysis/
├── quantitative_stats.py        # EA-1 统计脚本（零依赖复算入口，证据的一部分）
├── quantitative_stats.json      # EA-1 全部定量结果（含列联表与 p 值）
├── error_classification.jsonl   # 107 题逐题分类（case_id/error_type/confidence/evidence）
├── marriage_deepdive.md         # 任务 A
├── allwrong_charts.md           # 任务 B
└── report.md                    # 汇总：错误类型分布、富集结论、候选改进项（含覆盖题数）
```
