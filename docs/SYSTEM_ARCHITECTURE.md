# 八字命理智能体 — 系统架构与文件功能报告

> 版本: v2.2 | 日期: 2026-05-22 | 总代码: 36,217行 | 文件数: 109

本文档描述整个项目的文件结构、模块功能、依赖关系和调用链路，确保 Agent 能正确理解和使用每个文件。

---

## 一、目录总览

```
agent/
├── bazi_calculator.py          ← 核心引擎：排盘计算（1,916行，无依赖）
├── report_builder.py           ← 报告渲染引擎（610行，结构化JSON→Markdown）
├── report_to_pdf.py            ← PDF生成器（411行，无依赖）
├── api_server.py               ← FastAPI REST服务器（350行，10端点）
│
├── docs/                       ← 文档（Agent可读取参考）
│   ├── specs/                  ← 设计文档
│   │   └── 2026-05-21-phase1-backend-design.md
│   └── superpowers/plans/      ← 实施计划
│   ├── SYSTEM_ARCHITECTURE.md  ← 本文档
│   ├── USAGE_REPORT.md         ← 技术统计报告
│   └── USER_GUIDE.md           ← 客户使用指南
│
├── knowledge-base/             ← 知识库：数据 + 工具（11个Python + 10个JSON）
│   ├── [数据层——JSON]
│   │   ├── gejue.json             976条歌诀
│   │   ├── gejue_core.json        178条精选歌诀（Agent快速通道）
│   │   ├── shishen-combos.json    1,425条十神组合
│   │   ├── shensha.json           81条神煞
│   │   ├── nayin.json             60条纳音
│   │   ├── ziwei-patterns.json    60条紫微格局
│   │   ├── bingyao.json           34条病药配对
│   │   ├── xiangyi.json           22条干支象意
│   │   ├── yangzhai.json          8条阳宅调理
│   │   ├── wuyun-liuqi.json       10条五运六气
│   │   ├── hehun.json             合婚数据
│   │   └── solar_terms.json       3,624条节气数据
│   │
│   ├── [工具层——Python脚本]
│   │   ├── bazi_kb.py             350行  SQLite知识库（Phase 1 M1, 15表3,743条）
│   │   ├── bazi_kb.db                  SQLite数据库（~2MB, FTS5全文索引）
│   │   ├── zeri.py                503行  择日系统v2（八字个人化）
│   │   ├── liunian_calendar.py    671行  流年日历v2（12月运势）
│   │   ├── name_analysis.py       603行  取名引擎+名字评测
│   │   ├── name_wuxing_data.py    812行  字库（康熙笔画/81数理/五行）
│   │   ├── case_retrieval.py      650行  案例RAG检索（ChromaDB+简单匹配）
│   │   ├── hehun.py               290行  合婚分析CLI（四法合参）
│   │   ├── chuanren.py            303行  八字穿壬（大六壬+节气月将）
│   │   ├── search.py              269行  三层检索统一入口（SQLite层0）
│   │   ├── search_gejue.py        246行  Bigram歌诀检索
│   │   ├── search_vector.py       196行  ChromaDB向量检索
│   │   └── search_xiangyi.py      象意检索
│   │
│   └── [缓存文件]
│       ├── .gejue_tfidf.json      TF-IDF索引缓存
│       └── .query_classifier.json  查询分类器缓存
│
├── tests/                      ← 测试体系
│   ├── case_db.json           4,128条命例库（1.8MB）
│   ├── test_accuracy.py       排盘精度测试
│   ├── test_tools.py          174 工具测试 (zeri/liunian/name/case)
│   ├── test_bazi_kb.py        23 SQLite KB测试
│   ├── test_api.py            21 API端点测试
│   ├── test_consistency.py    格局一致性测试
│   ├── test_bingyao.py        病药自洽测试
│   ├── test_gejue_search.py   歌诀检索测试
│   ├── test_e2e_pipeline.py   端到端全流程测试
│   ├── validate_hallucination.py  幻觉率验证
│   ├── generate_suite.py      测试套件生成
│   ├── build_case_db.py       命例库构建
│   ├── expand_patterns.py     格局数据扩展
│   └── benchmark_charts/      20个金标案例的排盘JSON
│
├── quality/                    ← 模型质量评估
│   ├── model_quality_v2.py        507行  质量基准测试
│   ├── model_quality_report.json  评估报告
│   ├── model_quality_test.py
│   └── qualitative_comparison_report.md
│
├── tools/                      ← 辅助工具
│   ├── hour_inference.py      时辰推断（根据生平倒推）
│   ├── merge_cases.py         命例合并
│   └── scrape_celebrity_births.py  名人数据采集
│
├── data/                       ← 用户数据
│   ├── cases_real_db.json
│   ├── celebrity_cases.json
│   └── charts/                单个用户的排盘JSON
│
├── .claude/                    ← Claude Agent配置
│   ├── agents/
│   │   ├── bazi-multi-system-reader.md  ← Agent核心定义（~950行, Phase 1 M3拆分后）
│   │   └── templates/                   ← 6个报告模板（Phase 1 M3）
│   │       ├── mode1_ziping.md
│   │       ├── mode2_ditiansui.md
│   │       ├── mode3_ziwei.md
│   │       ├── mode4_mangpai.md
│   │       ├── mode5_sihechu.md
│   │       └── mode6_hehun.md
│   ├── agent-memory/
│   │   └── bazi-multi-system-reader/   ← Agent记忆存储
│   ├── skills/
│   │   ├── brainstorming/SKILL.md
│   │   ├── pdf-templates/SKILL.md
│   │   └── writing-plans/SKILL.md
│   └── settings.local.json
│
└── reports/                    ← 报告输出（由Agent自动管理）
    └── {姓名}_{日期}/           ← 个人子文件夹
        ├── 八字排盘_{日期}.json
        ├── {体系名}_报告.md
        └── {体系名}_报告.pdf
```

---

## 二、核心引擎

### 2.1 bazi_calculator.py — 排盘引擎

| 属性 | 值 |
|------|-----|
| 路径 | `bazi_calculator.py` |
| 规模 | 1,916行 |
| 依赖 | **无**（纯标准库） |
| 被调用 | 所有工具、所有测试、Agent |
| CLI | `--year --month --day --hour --gender --mode --output` |
| 输出 | JSON（four_pillars, day_master, shensha, da_yun, ziwei, wuyun_liuqi, birth_info等） |

**核心函数**：
| 函数 | 功能 |
|------|------|
| `calculate_four_pillars()` | 四柱+藏干+十神+纳音+空亡+胎元命宫身宫 |
| `calculate_dayun()` | 起运年龄+大运方向+10步大运 |
| `calculate_shensha()` | 每柱神煞（天乙贵人/文昌/桃花/驿马/华盖/羊刃/魁罡） |
| `calculate_ziwei()` | 紫微斗数（命宫/身宫/十二宫/十四主星/辅星/四化/大限） |
| `calculate_wuyun_liuqi()` | 五运六气 |
| `calculate_liunian()` | 未来3年流年 |
| `calculate_true_solar_time()` | 真太阳时校正 |
| `get_shishen()` | 十神判定 |
| `sexagenary_index/by_index()` | 六十甲子索引转换 |
| `get_year_pillar()` | 年柱（立春边界处理） |
| `get_month_pillar()` | 月柱（节气边界+五虎遁） |
| `get_day_pillar()` | 日柱（儒略日算法） |
| `get_hour_pillar()` | 时柱（五鼠遁+早/夜子时） |

**Agent 调用方式**：
```bash
python bazi_calculator.py --year 1993 --month 7 --day 15 --hour 14 --gender male --mode all -o chart.json
```

**下游消费方**：
- `zeri.py` — 导入 DIZHI, GAN_WUXING, LIUCHONG, LIUHE, TIANYI_GUIREN 等常量
- `liunian_calendar.py` — 导入 calculate_four_pillars, calculate_dayun, calculate_liunian 等
- `name_analysis.py` — 导入 GAN_WUXING, ZHI_WUXING
- `case_retrieval.py` — 导入 GAN_WUXING, ZHI_WUXING, sexagenary 函数
- `chuanren.py` — 导入 calculate_four_pillars
- `model_quality_v2.py` — 导入 calculate_four_pillars
- `test_accuracy.py` — 导入 calculate_four_pillars, calculate_dayun

### 2.2 report_to_pdf.py — PDF生成器

| 属性 | 值 |
|------|-----|
| 路径 | `report_to_pdf.py` |
| 规模 | 411行 |
| 依赖 | **无**（仅 fpdf2 库） |
| 被调用 | Agent（生成最终报告时） |
| CLI | `report.md -o report.pdf -t dark|modern|scroll|night` |

**4套模板**: dark(经典暗金), modern(清新现代), scroll(古风卷轴), night(暗夜模式)

**Agent 调用方式**：
```bash
python report_to_pdf.py "reports/{姓名}_{日期}/{体系}_报告.md" -o "reports/{姓名}_{日期}/{体系}_报告.pdf" -t dark
```

---

## 三、知识库——数据层（10个JSON文件）

所有JSON数据文件均可被 `search.py` / `search_gejue.py` / `search_vector.py` 检索，也可被 Agent 直接 `Read` 加载。

| 文件 | 条目 | 内容 | 检索方式 |
|------|------|------|---------|
| `gejue.json` | 976 | 歌诀（十神/格局/神煞/婚姻/财官等40+类别） | search.py / ChromaDB |
| `gejue_core.json` | 178 | 精选歌诀（Agent快速通道，减少检索噪音） | Agent直接Read |
| `shishen-combos.json` | 1,425 | 十神组合（身旺/身弱/男女/行业映射） | search.py |
| `shensha.json` | 81 | 神煞定义+含义 | search.py |
| `nayin.json` | 60 | 60甲子纳音+气质描述 | search.py |
| `ziwei-patterns.json` | 60 | 紫微格局+星曜组合 | search.py |
| `bingyao.json` | 34 | 病药配对 | search.py |
| `xiangyi.json` | 22 | 干支象意（职业/性格/健康映射） | search_xiangyi.py |
| `yangzhai.json` | 8 | 阳宅调理方案（九宫方位+五行补益） | Agent直接Read |
| `wuyun-liuqi.json` | 10 | 五运六气+脏腑对应 | Agent直接Read |
| `hehun.json` | — | 合婚数据 | Agent直接Read |
| `solar_terms.json` | 3,624 | 节气精确时间（151年全覆盖） | bazi_calculator.py内部使用 |

---

## 四、知识库——工具层（5个自助工具）

### 4.1 zeri.py — 择日系统v2

| 属性 | 值 |
|------|-----|
| CLI | `--year --month --purpose --chart --xishen --top --output` |
| 输入 | chart.json（八字排盘） 或 出生参数 |
| 输出 | JSON（排名日期列表，含评分/建除十二神/宜忌/分析） |
| 依赖 | bazi_calculator.py（常量+函数） |

**4层评分**：建除十二神(60) + 八字个人化互动(±5~40) + 喜用神匹配(±20) + 四离四绝(-50)

### 4.2 liunian_calendar.py — 流年日历v2

| 属性 | 值 |
|------|-----|
| CLI | `--chart --target-year --output --text` |
| 输入 | chart.json |
| 输出 | JSON（12月逐月分析：干支/十神/冲合/大运互动/4维评分/宜忌/神煞） |
| 依赖 | bazi_calculator.py（常量+calculate函数） |

**4维月度评分**：事业(1-5)/财运(1-5)/感情(1-5)/健康(1-5)

### 4.3 name_analysis.py — 取名引擎

| 属性 | 值 |
|------|-----|
| CLI | `--name <姓名> --chart --generate --surname --gender --top --output` |
| 输入 | chart.json + 姓名（评测模式）或 姓（生成模式） |
| 输出 | JSON（7维评分：五行匹配40/五格数理25/三才配置15/音韵10/字义10） |
| 依赖 | bazi_calculator.py + name_wuxing_data.py + zeri.infer_xishen |

**两个子模式**：
- `--name 张伟 --chart` → 评测已有名字
- `--generate --surname 王 --chart` → 推荐新名字

### 4.4 name_wuxing_data.py — 姓名学数据库

| 属性 | 值 |
|------|-----|
| 规模 | 812行 |
| 依赖 | **无**（纯数据） |
| 被调用 | name_analysis.py |

**数据表**：康熙笔画(~1,200字) + 百家姓(~100姓) + 81数理(81条) + 三才配置(125种) + 五行字库(5×~200字) + 生肖喜忌(12生肖) + 音韵词库

### 4.5 case_retrieval.py — 案例RAG检索

| 属性 | 值 |
|------|-----|
| CLI | `--build --chart --query --top --output --text` |
| 输入 | chart.json 或 文本查询 |
| 输出 | JSON（最相似案例：ID/姓名/类别/日主/标签/相似度/完整分析文本） |
| 依赖 | bazi_calculator.py（常量） |

**匹配算法**：日主五行同=+30, 月令同=+20, 最强五行同=+10, 五行分布距离≤3=+20/≤6=+10

**20个金标案例**：邓小平/钱学森/李嘉诚/冰心/陈毅/林彪/巴金/曹禺/张爱玲/杨绛/钱钟书/傅雷/林徽因/华罗庚/邓稼先/霍英东/徐向前/沈从文/屠呦呦/马云

### 4.6 chuanren.py — 八字穿壬

| 属性 | 值 |
|------|-----|
| CLI | `--chart --year --month --day --hour --qyear --qmonth --qday --qhour --output` |
| 输入 | chart.json + 查询时间 |
| 输出 | JSON（大六壬天地盘+四课+三传+八字交互分析） |
| 依赖 | bazi_calculator.py（calculate_four_pillars） |

---

## 五、知识库——检索层（3个检索后端）

### 5.1 search.py — 三层统一检索

| 属性 | 值 |
|------|-----|
| CLI | `"查询词" -v -c <类别> --top N` |
| 路由 | ①关键词分类器 → ②Bigram歌诀检索 → ③ChromaDB向量检索（三层fallback） |
| 依赖 | 所有JSON数据文件 + ChromaDB（可选） |

### 5.2 search_gejue.py — Bigram检索

| 属性 | 值 |
|------|-----|
| 算法 | 查询分类(P0/P1/P2关键词权重) → Bigram Jaccard相似度 → tag bonus + category bonus |
| 精度 | 78%（类别级） |

### 5.3 search_vector.py — ChromaDB向量检索

| 属性 | 值 |
|------|-----|
| 模型 | paraphrase-multilingual-MiniLM-L12-v2（384维） |
| 索引 | 1,536条文档 |
| 用途 | 语义探索（ChromaDB不可用时降级） |

---

## 六、质量与测试体系

### 6.1 测试文件

| 文件 | 功能 | 用例数 | 通过率 |
|------|------|--------|--------|
| `test_accuracy.py` | 排盘精度 | 1,113 | 100% |
| `test_consistency.py` | 格局一致性（5规则交叉） | 75 | 97.3% |
| `test_bingyao.py` | 病药自洽 | 32 | 100% |
| `test_gejue_search.py` | 歌诀检索精度 | 50 | 78% |
| `validate_hallucination.py` | 幻觉率检测 | — | <1% |
| `test_e2e_pipeline.py` | 端到端全流程 | 1 | ✅ |

### 6.2 测试数据

| 文件 | 内容 |
|------|------|
| `case_db.json` | 4,128条命例（系统覆盖3,162+边缘686+真实215+特殊41+随机300） |
| `test_charts.json` | 100条精确测试用例 |
| `test_suite.json` | 1,013条覆盖测试用例 |
| `benchmark_charts/` | 20个金标案例的calculator输出JSON |

### 6.3 质量评估

| 文件 | 功能 |
|------|------|
| `model_quality_v2.py` | 自动化质量基准测试（507行） |
| `model_quality_report_v2.json` | 质量评估报告 |

---

## 七、Agent 配置层

| 文件 | 功能 |
|------|------|
| `.claude/agents/bazi-multi-system-reader.md` | **Agent定义文件**（1,361行）——分析引擎+报告模板+工具调用规则 |
| `.claude/agent-memory/bazi-multi-system-reader/` | 记忆存储（用户偏好、已知问题、修正记录） |
| `.claude/skills/pdf-templates/SKILL.md` | PDF模板选择指南（4套模板说明） |
| `.claude/skills/brainstorming/SKILL.md` | 头脑风暴流程 |
| `.claude/skills/writing-plans/SKILL.md` | 实施计划编写 |
| `.claude/settings.local.json` | 项目本地设置 |

---

## 八、完整调用链路

### 8.1 标准分析流程（Agent自动执行）

```
用户输入出生信息
    │
    ▼
[Step 1] bazi_calculator.py --mode all -o chart.json
    │  输出: JSON（四柱/大运/神煞/紫微/五运六气/birth_info）
    │
    ▼
[Step 2] case_retrieval.py --chart chart.json --top 3
    │  输出: 3个最相似案例（日主/月令/格局匹配）
    │
    ▼
[Step 3] Agent 执行 U1-U4 通用引擎 → 旺衰量化+用神选取+岁运叠加+十神解码
    │
    ▼
[Step 4] Agent 执行选定 Mode（1-6）的分析引擎 + 交叉验证
    │
    ▼
[Step 5] Agent 按报告模板生成 Markdown
    │
    ▼
[Step 6] report_to_pdf.py {report}.md -o {report}.pdf -t dark
    │
    ▼
[Output] reports/{姓名}_{日期}/ 目录下的 .md + .pdf
```

### 8.2 自助工具调用链

```
用户问"帮我选个结婚日子"
    │
    ▼
Agent 检测到择日意图 → 自助工具 #1
    │
    ▼
zeri.py --year 2026 --month 6 --purpose 结婚 --chart chart.json
    │  内部: infer_xishen_from_chart() → score_day_personal() → find_good_dates()
    │  输出: 排名日期列表
    │
    ▼
Agent 解析JSON → 用自然语言呈现Top 5

---

用户问"帮我取个名字"
    │
    ▼
Agent 检测到取名意图 → 自助工具 #3
    │
    ▼
name_analysis.py --generate --surname 张 --chart chart.json --gender male
    │  内部: infer_xishen() → generate_names() → evaluate_name() 逐名打分
    │  输出: 排名名字列表
    │
    ▼
Agent 解析JSON → 呈现Top 5 + 评分理由
```

### 8.3 依赖图（纵向）

```
┌──────────────────────────────────────────────────┐
│                    Agent 层                        │
│         bazi-multi-system-reader.md                │
│         (调用所有下层工具)                          │
└────────┬──────────┬──────────┬──────────┬─────────┘
         │          │          │          │
    ┌────▼───┐ ┌───▼────┐ ┌──▼────┐ ┌──▼──────┐
    │ report │ │  zeri  │ │liunian│ │  name   │
    │_to_pdf │ │  .py   │ │  .py  │ │_analysis│
    │  .py   │ └───┬────┘ └───┬───┘ │  .py    │
    └────────┘     │          │     └──┬──────┘
                   │          │        │
              ┌────▼──────────▼────────▼─────┐
              │      bazi_calculator.py       │
              │      (核心引擎，无依赖)         │
              └───────────────────────────────┘
                         │
              ┌──────────▼───────────┐
              │   knowledge-base/    │
              │   JSON 数据层 (10文件) │
              └──────────────────────┘
```

---

## 九、文件完整性检查清单

Agent 在分析前应确认以下文件存在且可用：

| # | 文件 | 必须 | 检查方式 |
|---|------|------|---------|
| 1 | `bazi_calculator.py` | ✅ | 运行成功=可用 |
| 2 | `report_to_pdf.py` | ✅ | 生成PDF成功=可用 |
| 3 | `knowledge-base/zeri.py` | — | 用户问择日时需要 |
| 4 | `knowledge-base/liunian_calendar.py` | — | 用户问流年时需要 |
| 5 | `knowledge-base/name_analysis.py` | — | 用户问取名时需要 |
| 6 | `knowledge-base/name_wuxing_data.py` | ✅ | 被name_analysis导入 |
| 7 | `knowledge-base/case_retrieval.py` | ✅ | 每次分析前运行（ChromaDB+简单匹配） |
| 8 | `knowledge-base/chuanren.py` | — | 用户问穿壬时需要 |
| 9 | `knowledge-base/hehun.py` | — | 用户问合婚时需要 |
| 10 | `knowledge-base/gejue_core.json` | ✅ | Agent快速通道歌诀 |
| 11 | `tests/benchmark_charts/` | ✅ | 案例检索数据源（39个JSON） |
| 12 | `knowledge-base/bazi_kb.py` + `.db` | ✅ | SQLite知识库（14表/3,743条, FTS5） |
| 13 | `api_server.py` | ✅ | FastAPI服务器（10端点, Swagger） |
| 14 | `report_builder.py` | ✅ | 报告渲染引擎（6 Mode, -56% token） |
| 15 | `.claude/agents/templates/` | ✅ | 6个报告模板文件 |

---

## 十、Phase 1 新增模块（v2.2）

### 10.1 bazi_kb.py — SQLite 知识库

| 属性 | 值 |
|------|-----|
| CLI | `--build --stats --search "<关键词>"` |
| 表数 | 15（gejue, shensha, nayin, shishen_combos, ziwei_patterns, bingyao, xiangyi, yangzhai, wuyun_liuqi + FTS5索引） |
| 条目 | 3,743 |
| 查询 | `BaziKnowledgeBase().search_gejue("婚姻")` 等9个API |
| 依赖 | 12个源JSON文件（构建时读取） |

### 10.2 api_server.py — FastAPI REST 服务器

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
| `/api/kb/search?q=` | GET | 知识库搜索 |
| `/api/kb/stats` | GET | 知识库统计 |
| `/docs` | GET | Swagger UI |

启动：`python api_server.py` → `http://localhost:8000/docs`

### 10.3 Agent 模板分离

Agent 核心从 1,361 行压缩至 ~950 行，6 个报告模板移至 `.claude/agents/templates/`。Agent 分析时按 Mode 读取对应模板文件。

### 10.4 ChromaDB 案例向量索引

39 个金标案例通过 ChromaDB + paraphrase-multilingual-MiniLM-L12-v2 嵌入模型实现向量检索。相似度 0.88-0.92。CaseRetriever 类支持 auto/chroma/simple 三种模式，网络不可用时自动降级。

---

*文档结束*
