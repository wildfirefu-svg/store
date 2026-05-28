# Phase 1: 后端地基 — 详细设计

> 日期: 2026-05-21 | 目标: 建立可API化的后端基础设施

---

## M1: 知识库 SQLite 化

### 1.1 现状

12个独立 JSON 文件，每个有不同 schema。Agent 需要多次 Read 调用加载。search.py/search_gejue.py 各自解析 JSON。

### 1.2 设计

新建 `knowledge-base/bazi_kb.py`，包含：

```python
class BaziKnowledgeBase:
    """统一知识库访问层。底层 SQLite，上层 Python API。"""
    
    def __init__(self, db_path="knowledge-base/bazi_kb.db"):
        """打开或创建数据库"""
    
    def build(self):
        """从12个JSON文件构建SQLite数据库"""
    
    # === 查询API ===
    def search_gejue(self, query, category=None, top_n=5) -> list[dict]
    def search_shensha(self, name) -> dict | None
    def search_nayin(self, gan, zhi) -> dict | None
    def search_shishen_combo(self, combo_name, dm_strength=None) -> list[dict]
    def search_ziwei_pattern(self, pattern_name) -> dict | None
    def search_bingyao(self, disease) -> list[dict]
    def search_xiangyi(self, gan_or_zhi) -> list[dict]
    def search_yangzhai(self, problem) -> dict | None
    def fulltext_search(self, text, top_n=10) -> list[dict]
    
    # === 统计API ===
    def stats(self) -> dict
```

**SQLite Schema 设计（6张表）**：

```sql
-- 歌诀表（最大：976条）
CREATE TABLE gejue (
    id TEXT PRIMARY KEY,
    category TEXT,        -- '十神赋文'/'婚姻断诀' 等
    tags TEXT,             -- JSON array
    text TEXT,             -- 歌诀原文
    baihua TEXT,           -- 白话解释
    source TEXT,           -- 经典出处
    keywords TEXT          -- 提取的关键词，用于FTS
);
CREATE VIRTUAL TABLE gejue_fts USING fts5(id, text, baihua, keywords);

-- 神煞表（81条）
CREATE TABLE shensha (
    id TEXT PRIMARY KEY,
    name TEXT,
    category TEXT,         -- '吉神'/'凶煞'
    meaning TEXT,
    position_rule TEXT,
    source TEXT
);

-- 纳音表（60条）
CREATE TABLE nayin (
    id TEXT PRIMARY KEY,
    ganzhi TEXT,
    nayin_name TEXT,
    wuxing TEXT,
    temperament TEXT,      -- 气质描述
    likes TEXT,
    dislikes TEXT
);

-- 十神组合表（1,425条）
CREATE TABLE shishen_combos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combo_name TEXT,       -- '官印相生'/'食神生财' 等
    dm_strength TEXT,      -- '身旺'/'身弱'/'通用'
    gender TEXT,           -- '男'/'女'/'通用'
    industry TEXT,         -- 行业映射
    meaning TEXT,
    advice TEXT
);

-- 紫微格局表（60条）
CREATE TABLE ziwei_patterns (
    id TEXT PRIMARY KEY,
    pattern_name TEXT,
    star_combo TEXT,
    palace_requirement TEXT,
    interpretation TEXT
);

-- 病药/阳宅/五运六气 等小表...
```

### 1.3 构建流程

```
bazi_kb.py --build   # 一次性构建，生成 .db 文件（~2MB）
```

构建后 JSON 文件保留作为备份，SQLite 成为主数据源。

### 1.4 FTS5 全文检索

利用 SQLite FTS5 扩展，对歌诀的 text + baihua + keywords 字段建立全文索引。支持中文分词（使用内置分词器，配合 keyword 字段弥补分词不足）。

---

## M2: 案例向量检索升级

### 2.1 现状

`case_retrieval.py` 使用简单特征匹配（日主五行同=+30，月令同=+20）。不需要网络，但匹配粗糙。

### 2.2 设计

保留简单匹配作为 fallback，新增 ChromaDB 向量检索层：

```python
class CaseRetriever:
    def __init__(self, chroma_persist_dir=".chromadb_case_index"):
        self.simple_matcher = SimpleMatcher()  # 现有逻辑
        self.chroma_available = False
        if self._check_chroma():
            self.collection = self._get_or_create_collection()
            self.chroma_available = True
    
    def retrieve(self, query_features, top_n=5, mode='auto') -> list[dict]:
        """
        mode='auto': 尝试ChromaDB，失败降级simple
        mode='chroma': 仅ChromaDB
        mode='simple': 仅简单匹配
        """
```

**嵌入模型**：尝试加载 `paraphrase-multilingual-MiniLM-L12-v2`（384维）。如果本地已缓存则直接使用，否则降级为 simple match。

**文档构建**：每个金标案例的嵌入文本 = 
```
日主: {gan}({wuxing}) | 月令: {month_zhi} | 最强五行: {strongest} | 
格局: {key_tags} | 生平: {life_facts} | 分析: {pattern_note}
```

### 2.3 金标案例扩展到 50+

从 case_db 中再筛选 11+ 个有明确生平的真实人物，加到现有 39 例中（如：周恩来、蒋介石、孙中山、鲁迅等），搜索生平经历。

---

## M3: Agent/Prompt 分离

### 3.1 现状

Agent prompt 1,361 行，包含：核心规则 + 6套报告模板 + 工具调用规则 + 质量检查 + 幻觉防控。

### 3.2 设计

拆分为三层：

```
.claude/agents/
├── bazi-multi-system-reader.md    # 核心层 (~350行)：身份+流程+调用规则
└── templates/
    ├── mode1_ziping.md             # 子平真诠报告模板 (~80行)
    ├── mode2_ditiansui.md          # 滴天髓报告模板 (~80行)
    ├── mode3_ziwei.md              # 紫微斗数报告模板 (~80行)
    ├── mode4_mangpai.md            # 盲派报告模板 (~80行)
    ├── mode5_sihechu.md            # 四合出报告模板 (~80行)
    └── mode6_hehun.md              # 合婚报告模板 (~100行)
```

**核心层内容**（agent_core 替代当前 agent prompt 的大部分内容）：
- 身份定义 + 核心职责
- 输入处理 + 时辰范围
- Pre-Analysis: 跑 calculator + 5步快速验证（压缩版）
- Chart Presentation 格式
- 通用引擎 U1-U4（压缩版）
- 误判陷阱 T1-T13（压缩表格）
- 补充分析层 L1-L5（压缩版）
- 模式选择指南 + 交叉验证规则
- 输出校验清单（20项精简版）
- 评分标准 + 溯源规则 + 幻觉防控
- 自助工具调用规则（5个工具）
- Save 流程

**Agent 工作流**（加载模板的方式）：
1. 用户选择 Mode → Agent Read 对应模板文件
2. Agent 按模板生成报告
3. 交叉验证自动附加

### 3.3 分离后文件大小

| 文件 | 行数 |
|------|------|
| agent_core.md | ~400 |
| mode1_ziping.md | ~80 |
| mode2_ditiansui.md | ~80 |
| mode3_ziwei.md | ~80 |
| mode4_mangpai.md | ~80 |
| mode5_sihechu.md | ~80 |
| mode6_hehun.md | ~100 |
| **合计** | ~900（但 Agent 仅需加载 core + 1个 mode = ~480行） |

对比当前 1,361 行全部加载，节省 ~65% 上下文。

---

## M4: 统一 API 层

### 4.1 设计

新建 `api_server.py`，使用 FastAPI：

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="BaZi Analysis API", version="1.0")

# === 请求/响应模型 ===
class BirthInfo(BaseModel):
    year: int
    month: int
    day: int
    hour: int = 0
    minute: int = 0
    gender: str = "male"  # male | female
    location: str = "Beijing"

class ChartResponse(BaseModel):
    chart_id: str
    four_pillars: dict
    day_master: dict
    da_yun: list
    shensha: list
    ziwei: dict
    # ...

# === 端点 ===
POST /api/chart              # 排盘 → 返回完整命盘
GET  /api/chart/{id}         # 获取已缓存的命盘
POST /api/analyze            # 分析命盘（指定mode）→ 返回Markdown报告
POST /api/analyze/pdf        # 生成PDF
POST /api/tools/zeri         # 择日
POST /api/tools/liunian      # 流年日历
POST /api/tools/name/eval    # 名字评测
POST /api/tools/name/gen     # 取名推荐
POST /api/tools/case/search  # 案例检索
GET  /api/kb/search?q=       # 知识库检索
GET  /api/health             # 健康检查
GET  /docs                   # Swagger UI (自动)
```

### 4.2 关键技术选择

- **FastAPI**: 异步支持 + 自动 Swagger + Pydantic 验证
- **uvicorn**: ASGI server
- **缓存**: 内存 LRU（命盘缓存 128 条）

### 4.3 不做的

- ❌ 用户认证
- ❌ 数据库持久化（仅内存缓存 + SQLite 知识库）
- ❌ 前端界面
- ❌ Docker 部署（Phase 2）

---

## 实施顺序

```
Day 1-2: M1 (SQLite知识库) → 可验证查询速度
Day 3:   M2 (案例向量检索) → 可验证匹配质量
Day 4:   M3 (Agent/Prompt分离) → 可验证Agent行为不变
Day 5-6: M4 (API层) → 可验证端点响应
Day 7:   集成测试 + 文档更新
```

## 验收标准

1. `bazi_kb.py --build` 生成 .db 文件，所有查询 < 10ms
2. `case_retrieval.py` 向量模式可用，至少 3 例匹配 > 0.7 相似度
3. Agent 加载 core + mode1 能生成完整子平真诠报告（与当前质量一致）
4. `api_server.py` 所有端点返回正确 JSON，Swagger 可访问
5. `tests/test_tools.py` 174/174 仍全部通过

---

*设计结束*
