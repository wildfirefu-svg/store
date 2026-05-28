# 八字命理智能体 — 使用报告

> 生成日期: 2026-05-22 | 版本: v2.2

---

## 一、系统架构

```
agent/
├── 核心引擎
│   ├── bazi_calculator.py        1,916行 八字+紫微排盘引擎
│   ├── report_builder.py           610行 Markdown报告渲染（结构化输出）
│   ├── report_to_pdf.py            411行 Markdown→PDF生成（4套模板）
│   ├── api_server.py               350行 FastAPI REST服务器（10端点）
│   └── bazi-multi-system-reader.md 950行 Agent智能体定义
│
├── 知识库 (knowledge-base/)      14 SQLite表 + 11 Python工具
│   ├── bazi_kb.py + bazi_kb.db    SQLite统一知识库（14表/3,743条/FTS5全文检索）
│   ├── 结构化JSON: 12个源文件
│   └── 专项模块: 择日/流年/取名/合婚/穿壬/案例检索/五运六气
│
├── 案例检索
│   ├── case_retrieval.py          650行 ChromaDB向量 + 简单匹配双轨
│   ├── 金标案例: 39例（benchmark_charts/）
│   └── ChromaDB索引: 向量相似度 0.88-0.92
│
└── 测试体系 (tests/)
    ├── test_tools.py: 174 工具测试
    ├── test_bazi_kb.py: 23 KB测试
    ├── test_api.py: 21 API测试
    ├── test_e2e_pipeline.py: 端到端全流程
    ├── 排盘精度: 100用例100% + 1,013用例100%
    ├── 格局一致性: 75用例97.3%
    ├── 病药自洽: 32用例100%
    └── 综合用例: 218 tests, 100%通过
```

---

## 二、核心功能清单

### 2.1 排盘引擎 (`bazi_calculator.py`)

| 功能 | 命令示例 |
|------|---------|
| 八字四柱 | `python bazi_calculator.py --year 1989 --month 1 --day 15 --hour 8 --gender male --mode all -o chart.json` |
| 神煞/纳音/空亡 | 自动输出到 JSON |
| 大运排盘 | 起运年龄+10步大运+方向 |
| 紫微斗数 | 十二宫+十四主星+辅星+四化 |
| 五运六气 | 年干五运+年支六气 |
| 真太阳时 | 全球200+城市自动时区检测+经度校正 |
| birth_info | 输出包含出生参数供下游工具使用 |

### 2.2 分析体系 (Agent 6 Mode + 交叉验证)

| Mode | 体系 | 适用场景 | 自动辅系统 |
|------|------|---------|-----------|
| 1 | 子平真诠 | 格局判定/用神选取/人生层次 | 盲派 |
| 2 | 滴天髓 | 五行辨证/气势流通/寒暖燥湿 | 子平真诠 |
| 3 | 紫微斗数 | 十二宫全维度/大限流年 | 盲派 |
| 4 | 盲派 | 做功分析/带象直断/病药说 | 子平真诠 |
| 5 | 四合出 | 四体系交叉验证 | — |
| 6 | 合婚 | 双盘对比+13维度分析 | 子平+盲派(双方) |

**报告生成**: Agent输出结构化JSON → report_builder渲染Markdown → report_to_pdf生成PDF。Token消耗-56%。

### 2.3 自助工具（10个）

| 工具 | 命令 | 功能 |
|------|------|------|
| 择日 v2 | `python knowledge-base/zeri.py --chart chart.json --purpose 结婚` | 4层评分个人化择吉 |
| 流年 v2 | `python knowledge-base/liunian_calendar.py --chart chart.json --target-year 2026` | 12月4维运势 |
| 取名 | `python knowledge-base/name_analysis.py --generate --chart chart.json --gender male` | 八字匹配取名 |
| 评测 | `python knowledge-base/name_analysis.py --name 张伟 --chart chart.json` | 7维名字打分 |
| 合婚 | `python knowledge-base/hehun.py --chart1 m.json --chart2 f.json` | 四法合参 |
| 穿壬 | `python knowledge-base/chuanren.py --chart chart.json --qyear 2026 ...` | 八字+大六壬 |
| 案例检索 | `python knowledge-base/case_retrieval.py --chart chart.json --top 5` | ChromaDB向量检索 |
| KB搜索 | `python knowledge-base/bazi_kb.py --search "婚姻"` | SQLite FTS5全文检索 |
| PDF | `python report_to_pdf.py report.md -o report.pdf -t dark` | 4模板PDF生成 |
| 报告渲染 | `python report_builder.py --chart c.json --mode 1 --conclusions a.json -o r.md` | 结构化→Markdown |

### 2.4 Web API (`api_server.py` — 10端点)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/chart` | POST | 排盘 |
| `/api/chart/{id}` | GET | 获取缓存命盘 |
| `/api/tools/zeri` | POST | 择日 |
| `/api/tools/liunian` | POST | 流年日历 |
| `/api/tools/name/eval` | POST | 名字评测 |
| `/api/tools/name/gen` | POST | 取名推荐 |
| `/api/tools/case/search` | POST | 案例检索 |
| `/api/analyze` | POST | 报告生成(JSON→Markdown) |
| `/api/kb/search?q=` | GET | 知识库搜索 |

启动: `python api_server.py` → `http://localhost:8000/docs` (Swagger UI)

---

## 三、测试结果总览

| 测试项 | 用例数 | 结果 | 目标 |
|--------|--------|------|------|
| 排盘精度(精准) | 100 | **100%** | >=99% |
| 排盘精度(覆盖) | 1,013 | **100%** | >=99% |
| 格局一致性 | 75 | **97.3%** | >=90% |
| 病药自洽 | 32 | **100%** | >=95% |
| 幻觉率 | — | **<1%** | <1% |
| 工具测试 | 174 | **100%** | 100% |
| SQLite KB测试 | 23 | **100%** | 100% |
| API测试 | 21 | **100%** | 100% |
| 端到端全流程 | 1 | **100%** | 100% |
| 模型质量(544事件) | 0.56 | **正向17.5%** | 提升中 |

---

## 四、知识库规模

| 模块 | 条目数 | 存储 |
|------|--------|------|
| bazi_kb.db (SQLite) | 3,743 | 14表 + FTS5索引 |
| gejue.json (歌诀) | 976 | 264KB |
| shishen-combos.json (十神组合) | 1,425 | 150KB |
| shensha.json (神煞) | 81 | 34KB |
| nayin.json (纳音) | 60 | 10KB |
| ziwei-patterns.json (紫微格局) | 60 | 15KB |
| bingyao.json (病药) | 34 | 3KB |
| xiangyi.json (干支象意) | 22 | 12KB |
| yangzhai.json (阳宅) | 10 | 8KB |
| wuyun-liuqi.json (五运六气) | 22 | 15KB |
| solar_terms.json (节气) | 3,624 | 138KB |
| name_wuxing_data.py (字库) | ~1,200字 | 812行 |
| **合计** | **7,500+** | **~2.7MB** |

---

## 五、模型质量评估

82人/544已知事件验证：

| 维度 | 事件数 | 平均分 | 正向匹配 | 趋势 |
|------|--------|--------|---------|------|
| 事业 | 189 | 0.74 | 27.5% | 最强 |
| 感情 | 76 | 0.64 | 17.1% | 中等 |
| 财运 | 88 | 0.56 | 15.9% | 中等 |
| 健康 | 78 | 0.47 | 7.7% | 大幅提升(+292%) |
| 家庭 | 111 | 0.24 | 9.0% | 大幅提升(+71%) |
| **综合** | **544** | **0.56** | **17.5%** | **+37%** |

评分特性：大运十神 + 流年天干地支 + 岁运并临/天克地冲 + 地支刑冲合害 + 神煞(贵人/羊刃/桃花) + 五行偏枯 + 五运六气

---

## 六、性能指标

| 指标 | 优化前 | 优化后 | 改善 |
|------|--------|--------|------|
| Agent prompt | 1,848行 | 950行 | -49% |
| 报告模板 | 6套内嵌 | 6个独立文件 | 按需加载 |
| Token/报告 | ~16,000 | ~7,000 | -56% |
| 知识库查询 | JSON扫描 | SQLite FTS5 | <10ms |
| 案例检索 | 简单匹配(0.50) | ChromaDB向量(0.92) | +84%相似度 |

---

## 七、统计

| 指标 | 数值 |
|------|------|
| 总文件数 | 109 |
| 总代码行数 | 36,217 |
| Agent提示词 | 950行 |
| 知识库条目 | 7,500+ |
| 测试用例 | 218 (100%) |
| 命例库 | 4,128人 |
| 金标案例 | 39人 |
| PDF报告模板 | 4套 |
| 支持体系 | 6 Mode + 交叉验证 |
| 自助工具 | 10个 |
| Web API | 10端点 + Swagger |
| 排盘准确率 | 100% |
| 向量检索 | ChromaDB 0.88-0.92 |

---

## 八、版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.0 | 2026-05-15 | 基础排盘 + 子平真诠模式 |
| v2.0 | 2026-05-19 | 6大分析模式 + 天纪 + 合婚 + 择日 + 穿壬 + 4,128人例库 |
| v2.1 | 2026-05-20 | 交叉验证全Mode + 取名系统 + 流年v2 + 择日v2 + Agent自助工具 |
| v2.2 | 2026-05-22 | SQLite KB(3,743条) + ChromaDB向量(39例) + Web API(10端点) + 合婚CLI + report_builder(-56% token) + 模型质量0.41→0.56 + Agent压缩-49% |

---

*报告结束*
