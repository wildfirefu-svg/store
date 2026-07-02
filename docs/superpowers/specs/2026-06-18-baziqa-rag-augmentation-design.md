# BaziQA 命例库增强：RAG + Few-shot + 校验器扩容（设计）

## 1. 背景与目标

### 1.1 现状基线

- 数据集：BaziQA contest8，2021–2025 共 200 题，归一化到 [benchmark/datasets/baziqa_contest8_2021_2025.jsonl](file:///f:/project/agent/benchmark/datasets/baziqa_contest8_2021_2025.jsonl)。
- 已切分：
  - holdout：[benchmark/datasets/baziqa_contest8_2025_holdout.jsonl](file:///f:/project/agent/benchmark/datasets/baziqa_contest8_2025_holdout.jsonl)，40 题。
  - corpus：[benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl](file:///f:/project/agent/benchmark/datasets/baziqa_contest8_2021_2024_corpus.jsonl)，160 题。
- 基线评测：DeepSeek-V4-Pro / direct_choice 在 holdout 上 **accuracy = 25% (10/40)**，run_id=`cf614db6`，证据/安全均 100%。

### 1.2 目标

不动远端模型权重，通过命例 RAG + few-shot 模板 + 报告校验器扩容，把命理报告的事实基础与表达精度同时拉高，并用 holdout 量化提升幅度。

成功标准（必须全部满足）：

1. **量化指标**：在 BaziQA 2025 holdout 上，`direct_choice` 与 `structured_reasoning` 两种 method 的准确率均 ≥ baseline + 8%（即 ≥ 33%）。
2. **质量指标**：[scripts/verify_ui_report_quality.ps1](file:///f:/project/agent/scripts/verify_ui_report_quality.ps1) 全绿，`bad_patterns=[]`，新增 `case_evidence_present=True` 信号。
3. **零回归**：[tests/test_e2e.py](file:///f:/project/agent/tests/test_e2e.py) 与 core non-e2e 全部通过；现有 [tests/test_bazi_report_validator.py](file:///f:/project/agent/tests/test_bazi_report_validator.py) 全绿。
4. **数据隔离**：2025 holdout 在所有非评测路径下不可访问；corpus 仅用于 RAG/Few-shot/规则挖掘。

非目标：

- 不做 LoRA / SFT / RLHF / 模型权重微调。
- 不替换远端 API 调用。
- 不引入 GPU 依赖。

## 2. 总体架构

```
+------------------+        +-----------------------+
| BaZi chart input | -----> | feature_extractor     |  (日主, 月令, 旺衰, 十神, 大运, 性别, 出生年代)
+------------------+        +----------+------------+
                                       |
                                       v
                            +----------+------------+
                            | case_index            |  ChromaDB collection
                            | (corpus 160 题派生)   |
                            +----------+------------+
                                       |
                                       v
+------------------+        +----------+------------+        +---------------+
| user question    | -----> | rag_prompt_builder    | -----> | LLM provider  |
+------------------+        +----------+------------+        +-------+-------+
                                       |                              |
                                       v                              v
                            +----------+------------+        +-------+-------+
                            | bazi_report_validator |<-------+ raw report     |
                            | (规则 + 命例反推规律) |        +---------------+
                            +----------+------------+
                                       |
                                       v
                            +----------+------------+
                            | finalized report      |
                            +----------------------+
```

### 2.1 模块清单

| 模块 | 路径 | 职责 |
|------|------|------|
| `bazi_features.py` | [bazi_features.py](file:///f:/project/agent/bazi_features.py)（新建） | 把 chart 转成结构化特征向量与文本描述 |
| `case_index.py` | [case_index.py](file:///f:/project/agent/case_index.py)（新建） | 构建/加载 corpus 命例索引；提供 `top_k_cases(features, k)` |
| `rag_prompt_builder.py` | [rag_prompt_builder.py](file:///f:/project/agent/rag_prompt_builder.py)（新建） | 把召回命例与 few-shot 模板拼到 system prompt |
| `bazi_report_validator.py` | [bazi_report_validator.py](file:///f:/project/agent/bazi_report_validator.py)（扩容） | 在原规则基础上，加载 corpus 反推规律 |
| `api_server.py` | [api_server.py](file:///f:/project/agent/api_server.py)（小改） | `/api/chat/stream` 在调用 LLM 前调用 `rag_prompt_builder` |
| `run_benchmark.py` | [benchmark/runners/run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py)（小改） | 增加 `--rag` flag，开关 RAG 注入 |
| 评测脚本 | [scripts/verify_baziqa_rag_lift.ps1](file:///f:/project/agent/scripts/verify_baziqa_rag_lift.ps1)（新建） | 一键跑 baseline vs RAG 对比，写入 [docs/BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md) |

### 2.2 数据流要点

1. **chart 特征化**：`bazi_features.extract` 输出
   - `text_blob`：人类可读 + embedding 用文本（约 200 字）
   - `structured`：日主五行/月支主气/格局标签/性别/出生年代区间/年柱地支
   - 用作向量检索的 query 与精排的 filter。

2. **case_index 召回**：
   - 文档单元：corpus 中的"命主级"样本，每个 case 包含 `chart_text + answered_facts`（把所有 5 题 A/B/C/D 的"答案揭示出的真实事件"拼成事实段落）。
   - 检索：先用结构化 filter（日主、性别、出生年代±10）粗筛，再用向量相似度精排，取 top_k=3。

3. **prompt 注入**：在 system prompt 中插入：
   ```
   <类似命例>
   ## 案例 1（仅供参考，非当前命主）
   命盘特征：...
   史实结果：1985 年伤官见官 → 失去工作；2003 年伤官伤尽 → 创业成功
   </类似命例>
   ```
   并明确"案例仅作类比，最终判断需结合当前命盘"。

4. **few-shot 模板**：在 [prompt_engine.py](file:///f:/project/agent/prompt_engine.py) 的 srp_v1 模板下新增 7 个领域的 few-shot 段（事业/婚姻/财运/六亲/健康/学业/流年），样本来源 corpus，按"日主+性别"分桶热替换。

5. **校验器扩容**：从 corpus 答案反推群体规律（如"丁火生巳月，伤官见官者，事业初期多坎坷"），命中规律但报告输出与之相悖时，输出 `## 系统校验提示`。规律以 YAML 文件 [knowledge-base/baziqa_rules.yaml](file:///f:/project/agent/knowledge-base/baziqa_rules.yaml) 维护，便于人工审阅。

## 3. 关键决策与权衡

| 决策点 | 选项 | 决定 | 理由 |
|--------|------|------|------|
| 索引后端 | ChromaDB / FAISS / 纯 SQLite | **ChromaDB**（项目已有痕迹） | 已有依赖；本地、零配置；适合 < 10k 文档 |
| Embedding 模型 | OpenAI / DeepSeek / 本地 bge-small-zh | **本地 bge-small-zh**（fallback 到 DeepSeek embedding） | 0 网络成本；中文质量足够；离线可用 |
| 召回单元粒度 | 按"题" / 按"命主" | **按"命主"** | 命例的事实链是按命主成立的；一个命主一个文档，避免同人不同题分裂 |
| top_k | 1 / 3 / 5 | **3** | 平衡 prompt 长度与多样性 |
| 是否开关化 | 默认开 / 默认关 / flag | **flag**：`--rag` / `BAZI_RAG=1` | 对比基线；灰度回滚 |
| holdout 隔离 | 软隔离（命名约定） / 硬隔离（运行时断言） | **硬隔离**：`case_index` 加载时若发现 holdout 文件路径直接 raise | 避免误污染评测 |

## 4. 验收协议

### 4.1 自动化测试

- [tests/test_bazi_features.py](file:///f:/project/agent/tests/test_bazi_features.py)：特征提取确定性。
- [tests/test_case_index.py](file:///f:/project/agent/tests/test_case_index.py)：召回结果稳定、holdout 文件被拒绝。
- [tests/test_rag_prompt_builder.py](file:///f:/project/agent/tests/test_rag_prompt_builder.py)：prompt 拼接结构 + 长度上限。
- [tests/test_bazi_report_validator.py](file:///f:/project/agent/tests/test_bazi_report_validator.py)：扩容规则覆盖。
- [tests/test_api.py](file:///f:/project/agent/tests/test_api.py)：`/api/chat/stream` 在 RAG flag 开启时仍能完成；rag context 不进入用户消息。
- [tests/test_e2e.py](file:///f:/project/agent/tests/test_e2e.py)：UI 完整链路不变。

### 4.2 量化评测

- 命令：[scripts/verify_baziqa_rag_lift.ps1](file:///f:/project/agent/scripts/verify_baziqa_rag_lift.ps1)
- 步骤：
  1. baseline = 当前 25%（已落库 run_id=`cf614db6`）。
  2. RAG 模式：跑 holdout 40 题 × 2 method（direct_choice + structured_reasoning）。
  3. 输出 [docs/BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md)：baseline_acc / rag_acc / delta / 各题命中变化。
- 通过：两种 method 的 rag_acc 均 ≥ 33%。

### 4.3 人工抽检

- 在 UI 上至少跑 3 个真实命主，肉眼检查报告是否引用了类似命例、表述更具体、无"巳午未会火局"类断言错误。

## 5. 风险与回退

| 风险 | 缓解 |
|------|------|
| 召回噪声把模型带偏 | top_k=3 + 结构化预过滤 + prompt 写明"仅作类比" |
| holdout 误进检索 | `case_index` 启动断言；CI 测试覆盖 |
| 规则反推过拟合 corpus | 规则要求"命主数 ≥ 3 且占比 ≥ 0.6"才入库；规律以 YAML 维护，人工可审 |
| Embedding 模型下载失败 | 回退到 DeepSeek embedding API；再失败回退到关键词 BM25 召回 |
| RAG 提升不达 8% | 设置 flag，可一键关闭；保留作为 prompt 调试工具 |

## 6. 范围与时间

- 范围内：上述 5 个模块、3 个测试文件、1 个评测脚本、1 个对比报告。
- 范围外（不做）：模型微调、UI 大改、知识库重建、流式协议修改。
- 预计步数：5 个 task，逐个 TDD。

## 7. 对外接口（契约）

```python
# bazi_features.py
def extract(chart: dict) -> dict:
    """返回 {"text_blob": str, "structured": dict}."""

# case_index.py
class CaseIndex:
    def __init__(self, corpus_path: Path, embed_fn): ...
    def top_k_cases(self, features: dict, k: int = 3) -> list[dict]: ...

# rag_prompt_builder.py
def build_system_prompt(
    base_system: str,
    chart: dict,
    case_index: CaseIndex,
    enable_rag: bool = True,
) -> str: ...
```

## 8. 自审清单

- [x] 基线已量化（25%），不再凭主观判断改进效果。
- [x] holdout/corpus 已物理切分，硬隔离设计入断言。
- [x] 不动模型权重；零 GPU 依赖。
- [x] 所有改动都有 flag，可回滚。
- [x] 评测协议覆盖自动化 + 量化 + 人工抽检。
- [x] 模块边界清晰，方便单元测试。
