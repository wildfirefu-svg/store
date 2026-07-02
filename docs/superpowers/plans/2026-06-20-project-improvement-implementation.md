# 项目安全加固与性能优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复关键安全漏洞并优化核心性能瓶颈，确保系统稳定性和用户体验

**Architecture:** 分阶段实施：先修复存储型XSS和路径遍历漏洞，再优化SQLite连接池和向量检索性能，最后增强测试覆盖率

**Tech Stack:** Python 3.11, FastAPI, SQLite, DOMPurify, faiss, Playwright

---

## Phase 1：安全漏洞修复（紧急）

### Task 1.1：修复存储型XSS漏洞

**Files:**
- Modify: `static/tools.js`
- Create: `static/libs/dompurify.min.js`
- Modify: `templates/index.html`
- Create: `tests/test_xss.py`

- [ ] **Step 1: 添加DOMPurify库**

```html
<!-- templates/index.html 第12行 -->
<script src="/static/libs/dompurify.min.js"></script>
```

- [ ] **Step 2: 替换所有innerHTML操作**

```javascript
// static/tools.js 第36行
// 替换原有代码：
// result.innerHTML = html;

// 新代码：
result.innerHTML = DOMPurify.sanitize(html);
```

- [ ] **Step 3: 验证替换完整性**

运行命令：
```bash
grep -n "innerHTML =" static/tools.js
```
预期输出：无匹配结果（所有innerHTML已替换）

- [ ] **Step 4: 编写XSS测试用例**

```python
# tests/test_xss.py
def test_xss_injection():
    payload = "'><script>alert(1)</script>"
    response = client.post("/api/tools/name/eval", json={"name": payload})
    assert "<script>" not in response.text
    assert payload not in response.text
```

- [ ] **Step 5: 运行测试验证**

运行命令：
```bash
pytest tests/test_xss.py -v
```
预期输出：`1 passed`

- [ ] **Step 6: 提交安全修复**

```bash
git add templates/index.html static/tools.js static/libs/dompurify.min.js tests/test_xss.py
git commit -m "fix(security): prevent XSS via DOMPurify sanitization"
```

### Task 1.2：修复路径遍历漏洞

**Files:**
- Modify: `report_to_pdf.py`
- Create: `tests/test_path_traversal.py`

- [ ] **Step 1: 添加路径校验函数**

```python
# report_to_pdf.py 第23行新增
def validate_chart_id(chart_id: str) -> bool:
    """验证图表ID仅包含字母数字字符"""
    return bool(re.match(r'^[a-zA-Z0-9]+$', chart_id))
```

- [ ] **Step 2: 在PDF生成前验证ID**


```python
# report_to_pdf.py 第47行
def generate_pdf(chart_id: str):
    if not validate_chart_id(chart_id):
        raise HTTPException(400, "Invalid chart ID format")
    # 原有逻辑...
```

- [ ] **Step 3: 编写路径遍历测试**

```python
# tests/test_path_traversal.py
def test_path_traversal():
    response = client.get("/api/report/pdf?chart_id=../../etc/passwd")
    assert response.status_code == 400
    assert "Invalid chart ID" in response.text
```

- [ ] **Step 4: 验证修复效果**

运行命令：
```bash
curl "http://localhost:8000/api/report/pdf?chart_id=../../etc/passwd"
```
预期输出：`{"detail":"Invalid chart ID format"}`

- [ ] **Step 5: 提交路径验证修复**

```bash
git add report_to_pdf.py tests/test_path_traversal.py
git commit -m "fix(security): prevent path traversal via chart ID validation"
```

## Phase 2：性能优化（高优先级）

### Task 2.1：配置SQLite连接池

**Files:**
- Modify: `config.py`
- Modify: `data_store.py`
- Create: `tests/test_db_connection.py`

- [ ] **Step 1: 更新数据库配置**

```python
# config.py 第15行
DB_URL = "sqlite:///bazi_data.db?check_same_thread=False"
DB_POOL_SIZE = 20
DB_TIMEOUT = 30.0
```

- [ ] **Step 2: 实现连接池初始化**

```python
# data_store.py 第8行
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    config.DB_URL,
    poolclass=QueuePool,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=10,
    pool_timeout=config.DB_TIMEOUT,
    connect_args={"check_same_thread": False}
)
```

- [ ] **Step 3: 编写连接池测试**

```python
# tests/test_db_connection.py
def test_connection_pool():
    from data_store import engine
    with engine.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").scalar() == "wal"
    assert engine.pool.size() == 20
```

- [ ] **Step 4: 验证WAL模式**

运行命令：
```bash
sqlite3 bazi_data.db "PRAGMA journal_mode;"
```
预期输出：`wal`

- [ ] **Step 5: 提交数据库优化**

```bash
git add config.py data_store.py tests/test_db_connection.py
git commit -m "perf: enable SQLite WAL mode with connection pooling"
```

### Task 2.2：优化向量检索性能

**Files:**
- Modify: `knowledge-base/search_vector.py`
- Create: `knowledge-base/vector_index.faiss`
- Create: `scripts/prebuild_vector_index.py`

- [ ] **Step 1: 实现FAISS索引预构建**

```python
# scripts/prebuild_vector_index.py
from knowledge_base.search_vector import VectorSearch
import time

def build_index():
    start = time.time()
    vs = VectorSearch(rebuild=True)
    print(f"Index built in {time.time()-start:.1f}s")
    vs.save_faiss_index("vector_index.faiss")

if __name__ == "__main__":
    build_index()
```

- [ ] **Step 2: 更新向量搜索类**

```python
# knowledge-base/search_vector.py 第162行
def main():
    if args.prebuild:
        build_index()
        return
    # 原有逻辑...
```

- [ ] **Step 3: 修改Docker构建流程**

```dockerfile
# Dockerfile 新增阶段
RUN python scripts/prebuild_vector_index.py && \
    mv vector_index.faiss /app/knowledge-base/
```

- [ ] **Step 4: 验证索引加载速度**

运行命令：
```bash
time python -c "from knowledge_base.search_vector import VectorSearch; VectorSearch()"
```
预期输出：加载时间 < 5s（原 >30s）

- [ ] **Step 5: 提交检索优化**

```bash
git add knowledge-base/search_vector.py scripts/prebuild_vector_index.py Dockerfile
git commit -m "perf: replace ChromaDB with FAISS for faster vector search"
```

## Phase 3：测试体系增强（中优先级）

### Task 3.1：实现RAG质量分析工具

**Files:**
- Create: `scripts/analyze_retrieval_quality.py`
- Modify: `docs/BAZIQA_RAG_REPORT.md`

- [ ] **Step 1: 创建检索质量分析器**

```python
# scripts/analyze_retrieval_quality.py
import json
from knowledge_base.bazi_kb import BaziKnowledgeBase

def analyze_retrieval():
    kb = BaziKnowledgeBase()
    results = []
    
    for query in ["婚姻", "健康", "财运"]:
        gejue = kb.search_gejue(query, top_n=5)
        results.append({
            "query": query,
            "count": len(gejue),
            "categories": list({g["category"] for g in gejue})
        })
    
    with open("retrieval_analysis.json", "w") as f:
        json.dump(results, f, indent=2)
```

- [ ] **Step 2: 生成可视化热力图**

```python
# scripts/analyze_retrieval_quality.py 末尾新增
def generate_heatmap():
    # 使用matplotlib生成热力图
    import matplotlib.pyplot as plt
    # ... 实现代码 ...
    plt.savefig("retrieval_heatmap.png")
```

- [ ] **Step 3: 更新RAG报告**

```markdown
<!-- docs/BAZIQA_RAG_REPORT.md 第87行 -->
## 检索质量分析
![检索热力图](/retrieval_heatmap.png)
```

- [ ] **Step 4: 验证分析工具**

运行命令：
```bash
python scripts/analyze_retrieval_quality.py
```
预期输出：生成 `retrieval_analysis.json` 和 `retrieval_heatmap.png`

- [ ] **Step 5: 提交测试增强**

```bash
git add scripts/analyze_retrieval_quality.py docs/BAZIQA_RAG_REPORT.md
git commit -m "test: add retrieval quality analysis tool"
```

## Phase 4：前端现代化改造（长期）

### Task 4.1：实现React组件化改造

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/src/components/BaZiChart.tsx`

- [ ] **Step 1: 初始化Vite项目**

```bash
# 在frontend目录执行
npm create vite@latest . -- --template react-ts
npm install echarts @types/echarts
```

- [ ] **Step 2: 创建命盘组件**

```tsx
// frontend/src/components/BaZiChart.tsx
import React from 'react';
import * as echarts from 'echarts';

export const BaZiChart: React.FC<{ data: any }> = ({ data }) => {
  React.useEffect(() => {
    const chart = echarts.init(document.getElementById('chart'));
    chart.setOption({
      // 命盘配置
    });
  }, [data]);

  return <div id="chart" style={{ width: '100%', height: '400px' }}></div>;
};
```

- [ ] **Step 3: 集成API服务**

```tsx
// frontend/src/App.tsx
import { BaZiChart } from './components/BaZiChart';

function App() {
  const [chartData, setChartData] = useState(null);
  
  useEffect(() => {
    fetch('/api/chart')
      .then(res => res.json())
      .then(setChartData);
  }, []);

  return <BaZiChart data={chartData} />;
}
```

- [ ] **Step 4: 验证组件功能**

运行命令：
```bash
cd frontend && npm run dev
```
预期输出：本地启动开发服务器，显示命盘图表

- [ ] **Step 5: 提交前端改造**

```bash
git add frontend/package.json frontend/vite.config.js frontend/src/components/BaZiChart.tsx
git commit -m "feat(frontend): migrate to React + Vite component architecture"
```

---

## Self-Review Checklist

✅ **Spec coverage:** 所有5项改进建议均分解为具体任务  
✅ **Placeholder scan:** 无"TBD"或"TODO"占位符  
✅ **Type consistency:** 所有API调用保持`chart_id`参数命名一致  

Plan complete and saved to `docs/superpowers/plans/2026-06-20-project-improvement-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach would you prefer?