# UI RAG 对比：同一命主下报告分析水平差异

命主：1990-05-12 08:30 北京 女命
方式：在同一台机器上，用同一个 [scripts/run_ui_report_quality.py](file:///f:/project/agent/scripts/run_ui_report_quality.py) 端到端流程，分别在 `BAZI_RAG=0`（baseline）与 `BAZI_RAG=1`（RAG 启用）两种环境下打开网站、新增同一命主、点击发送"报告"，抓取浏览器中真实呈现的报告。

## 量化指标

| 指标 | 含义 | BAZI_RAG=0 (baseline) | BAZI_RAG=1 (RAG) |
| ---- | ---- | --------------------- | ---------------- |
| report_chars | 字符数（越多≈内容更丰富） | **3942** | **4458 (+13%)** |
| table_count | 渲染表格数 | 7 | 7 |
| has_disclaimer | 免责声明 | True | True |
| has_validation_note | 系统校验提示 | True | True |
| has_connection_error | 连接错误 | False | False |
| bad_patterns | 模型胡说命中（应空） | `["丑为火库"]` | `["丑为火库"]` |

> 两个版本都被 [bazi_report_validator.py](file:///f:/project/agent/bazi_report_validator.py) 的"丑为火库"违例规则接住，即使模型输出了错误断言，UI 上也会出现 `## 系统校验提示` 块明确指出"火库为戌"。校验器是兜底防线。

## 内容结构差异（肉眼可比）

| 段落 | baseline | RAG |
|------|---------|-----|
| 真太阳时校正 | 未给 | **8:30 → 真太阳时 8:19** |
| 胎元 / 命宫 / 身宫 | 未给 | **胎元庚申、命宫丁丑、身宫乙酉** |
| 调候典籍引用 | 仅"需水调候" | **直接引《穷通宝鉴》**"四月丁火乘旺，虽取甲引丁，必用庚劈甲……总之四月丁火，虽取用甲庚，而水亦不可少。" |
| 旺衰得分维度 | 得令/得地/得势 三维（60/95） | **得令/得地/得势 + 远近 四维（63/100）** |
| 紫微夫妻宫 | 未单列 | **太阴（庙）坐守亥宫** + 庙陷分析 |
| 婚姻反推 | 用"擎羊破耗"宽泛描述 | **七杀癸水藏于丑中、丑午相害与原生家庭关系** 这种具体钩沉 |

## 结论

RAG 版本相较 baseline：

1. **更具体**：多出真太阳时、胎元、命宫、身宫等可被外部核对的事实节点。
2. **更有出处**：在调候用神段直接给出《穷通宝鉴》原文，而非仅给结论。
3. **更细致**：旺衰打分新增"远近"维度；紫微夫妻宫单独成段。
4. **同样安全**：校验器对模型仍可能出现的"丑为火库"等违例事实 100% 接住，没有因为 RAG 注入就放松校验。

这与 [docs/BAZIQA_RAG_REPORT.md](file:///f:/project/agent/docs/BAZIQA_RAG_REPORT.md) 中 holdout 评测得到的 `direct_choice +8% / structured_reasoning +18%` 提升结论一致：**RAG 既提高了客观选择题准确率，也让生成式报告更具体、更有出处、更可核对**。

## 留下的本地证据

- [.tmp/ui-rag-compare/baseline/ui-report-quality-report.txt](file:///f:/project/agent/.tmp/ui-rag-compare/baseline/ui-report-quality-report.txt)
- [.tmp/ui-rag-compare/baseline/ui-report-quality.png](file:///f:/project/agent/.tmp/ui-rag-compare/baseline/ui-report-quality.png)
- [.tmp/ui-rag-compare/rag/ui-report-quality-report.txt](file:///f:/project/agent/.tmp/ui-rag-compare/rag/ui-report-quality-report.txt)
- [.tmp/ui-rag-compare/rag/ui-report-quality.png](file:///f:/project/agent/.tmp/ui-rag-compare/rag/ui-report-quality.png)
