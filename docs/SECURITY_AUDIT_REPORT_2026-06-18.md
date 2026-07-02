# 玄机子（XuanJiZi）八字命理分析系统 — 安全与代码审查报告

- **审查日期**：2026-06-18
- **审查范围**：`f:\project\agent` 全项目（后端 FastAPI、前端 ES6、SQLite、Docker、测试）
- **审查方法**：静态代码分析、安全模式扫描、配置与依赖审计
- **总体风险等级**：**中-高**  
  存在可直接利用的存储型 XSS 与路径遍历风险，建议优先修复。

---

## 1. 执行摘要

项目功能完整、模块化程度较高，后端测试覆盖较广。但在**前端安全、认证传输、日志安全和输入校验**方面存在明显短板。最严重的问题可直接导致：

1. 用户会话被劫持（存储型 XSS）。
2. 服务器任意文件被覆盖（路径遍历）。
3. API Key 被泄露到日志、浏览器历史或 Referer。

建议优先修复严重与高危问题，再逐步完善中低危项。

---

## 2. 关键发现矩阵

| 严重度 | 数量 | 主要类别 |
|--------|------|----------|
| **Critical** | 2 | 存储型 XSS、路径遍历 |
| **High** | 4 | CORS 通配、API Key query 传输、日志泄露、硬编码密码 |
| **Medium** | 5 | 前端 innerHTML、提示词注入、CSRF、输入验证、构建产物 |
| **Low** | 若干 | 代码风格、测试缺口、部署加固 |

---

## 3. 严重问题（Critical）

### 3.1 存储型 XSS：AI / 聊天记录直接作为 HTML 渲染

- **文件**：`static/js/ui.js`
- **风险代码**：

```javascript
const safeText = role === 'user' ? _escHtml(text) : text;
d.innerHTML = '<div class="sender">...</div><div class="bubble">' + safeText + '</div>';
```

- **风险分析**：
  - 当 `role !== 'user'`（即系统消息或 AI 消息）时，文本**不做转义**直接写入 `innerHTML`。
  - AI 输出可能包含 `<script>`、`<img onerror=...>`、`<a href="javascript:...">` 等恶意代码。
  - 由于聊天历史会持久化到 SQLite，攻击者可写入包含恶意脚本的 `agent` 角色消息，向所有查看该命盘的用户植入脚本。
- **攻击路径**：
  1. 攻击者调用 `POST /api/charts/{chart_id}/history`，写入 `role='agent'`、`text='<img src=x onerror=fetch(...)'`。
  2. 用户打开该命盘，前端加载历史消息后执行脚本。
  3. 脚本以用户身份调用后端，窃取其他命盘数据或执行操作。
- **修复建议**：
  - 所有渲染到聊天气泡的文本统一使用 `_escHtml(text)`。
  - 报告内容使用安全的 Markdown 渲染（先转义 HTML 再解析标记）。
  - 后端也应对写入历史记录的角色和文本做校验与清洗。

### 3.2 路径遍历：合婚工具用用户输入拼接临时文件路径

- **文件**：`api_server.py`
- **风险代码**：

```python
t1 = os.path.join(tempfile.gettempdir(), f'hehun_c1_{req.chart_id1}.json')
t2 = os.path.join(tempfile.gettempdir(), f'hehun_c2_{req.chart_id2}.json')
json.dump(c1, open(t1, 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(c2, open(t2, 'w', encoding='utf-8'), ensure_ascii=False)
```

- **风险分析**：
  - `chart_id1` / `chart_id2` 来自请求体，未校验格式。
  - 若传入 `../../static/evil` 等路径，会覆盖项目目录或系统目录下的任意文件。
  - 配合 `subprocess` 调用外部脚本，可能进一步导致命令执行。
- **修复建议**：
  - 使用 `tempfile.NamedTemporaryFile()` 生成随机临时文件名。
  - 或严格限制 `chart_id` 为 `[a-zA-Z0-9]` 的固定长度字符串。
  - 禁止将用户可控输入直接拼接到文件路径。

---

## 4. 高危问题（High）

### 4.1 CORS 默认允许任意来源

- **文件**：`api_server.py`、`config.py`
- **风险代码**：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGIN_LIST if CORS_ORIGIN_LIST else ["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
```

- **风险分析**：
  - 当 `BAZI_CORS_ORIGINS` 为空或配置为 `*` 时，任何网站都能调用该 API。
  - 如果同时启用了 API Key 查询参数认证，恶意网页可通过 XHR 直接调用后端。
- **修复建议**：
  - 生产环境默认拒绝 `*`，必须显式配置可信来源。
  - 空配置时不应退化为全开放，建议抛出配置错误或仅允许本地来源。

### 4.2 API Key 通过 URL 参数传递

- **文件**：`api_server.py`、`config.py`
- **风险代码**：

```python
if ALLOW_QUERY_API_KEY and request.query_params.get("api_key") == _BAZI_API_KEY:
    return await call_next(request)
```

```python
ALLOW_QUERY_API_KEY = os.environ.get(
    "BAZI_ALLOW_QUERY_API_KEY",
    "1" if ENV != "production" else "0",
) in ("1", "true", "True", "yes", "YES")
```

- **风险分析**：
  - URL 参数会留在浏览器历史、服务器日志、反向代理日志和 Referer 中。
  - 非生产环境默认开启，极易被误用于生产。
- **修复建议**：
  - 移除 query 参数认证方式。
  - 或至少强制生产环境关闭，并在启动时检查报错。

### 4.3 日志记录 AI API Key 前缀

- **文件**：`claude_api.py`
- **风险代码**：

```python
prefix = key[:7] + "***"
logger.info("AI configured: provider=%s model=%s key_prefix=%s key_len=%d", ...)
```

- **风险分析**：
  - 日志中出现 key 前缀，一旦日志泄露，攻击者可缩小爆破范围。
- **修复建议**：
  - 只记录 provider、model、是否已配置。
  - 不记录 key 的任何片段。

### 4.4 设计文档中硬编码默认密码

- **文件**：`improvement_part_engineering.md`
- **风险内容**：

```text
- GF_SECURITY_ADMIN_PASSWORD=xuanjizi2024
```

- **风险分析**：
  - 若该配置被复制到生产环境（如 Grafana/监控面板），攻击者可直接使用默认密码登录。
- **修复建议**：
  - 改为占位符 `<CHANGE_ME>` 或环境变量。
  - 在文档中明确警告必须修改。

---

## 5. 中危问题（Medium）

### 5.1 前端多处 `innerHTML` 与转义不完整

- **文件**：`static/app.js`、`static/js/ui.js`、`static/js/render-bazi.js` 等
- **风险分析**：
  - `render-bazi.js` 直接把后端返回的八字数据拼成 HTML 插入，未做转义。
  - 如果后端数据被污染（如 `location`、`name` 字段含 HTML），可触发 XSS。
- **修复建议**：
  - 所有动态 HTML 生成统一使用 `textContent` 或完整 HTML 转义。
  - 建立前端统一渲染工具函数，避免直接拼接 HTML。

### 5.2 提示词注入防护薄弱

- **文件**：`api_server.py`
- **风险代码**：

```python
def _sanitize_memory_text(value, limit=500):
    text = str(value or '')[:limit]
    blocked = ['忽略以上', '忽略前面', '系统提示', '开发者指令', '必须遵守', '必须执行', '不要遵守', 'override', 'system prompt']
    for phrase in blocked:
        text = text.replace(phrase, '[已过滤]')
```

- **风险分析**：
  - 简单字符串替换极易绕过（加空格、拼音、特殊字符、英文变体）。
  - 用户输入与系统提示直接拼接，角色隔离不足。
- **修复建议**：
  - 采用更严格的输入校验。
  - 系统提示与用户输入的角色隔离。
  - 对历史摘要进行结构化输出，而非直接拼接。

### 5.3 缺少 CSRF 保护

- **文件**：`api_server.py`
- **风险分析**：
  - 对 `POST /api/charts/save`、`POST /api/clients` 等状态变更接口，仅依赖 API Key 或 CORS。
  - 如果 CORS 配置宽松，恶意网站可能发起跨站请求。
- **修复建议**：
  - 对浏览器端调用使用 CSRF Token 或 SameSite Cookie。
  - 非浏览器客户端使用 Header 认证。

### 5.4 输入验证不统一

- **文件**：多个 API 端点
- **风险分析**：
  - `chart_id`、`client_id`、`purpose` 等参数没有统一的格式校验。
  - 部分字符串字段没有长度限制。
- **修复建议**：
  - 为所有路径参数和查询参数添加 Pydantic 校验器或正则约束。
  - 统一输入校验中间件。

### 5.5 构建产物与二进制依赖在仓库中

- **发现**：`dist/`（246 个文件）、`build/`（10 个文件）包含编译产物和 DLL/PYD。
- **风险分析**：
  - 仓库臃肿，可能包含有漏洞或不可追溯的二进制文件。
  - 二进制文件难以审计。
- **修复建议**：
  - 将 `dist/`、`build/` 加入 `.gitignore`。
  - 由 CI/CD 构建生成，并记录构建来源。

---

## 6. 代码质量评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 模块化 | 良 | 后端按功能拆分清晰，前端使用 ES 模块 |
| 错误处理 | 中 | 基本覆盖，但部分 `except Exception` 静默吞掉错误 |
| 可测试性 | 良 | 测试文件多，但缺少前端与端到端安全测试 |
| 文档 | 中 | 代码注释足够，但安全部署与威胁建模文档不足 |
| 配置管理 | 中 | 环境变量覆盖较好，但部分默认值不够安全 |

---

## 7. 测试与部署评估

### 7.1 测试

- `tests/` 包含 45+ 个测试文件，覆盖 API、数据库、基准测试。
- 缺少前端 XSS 测试和认证绕过测试。
- 建议补充：
  - 输入验证测试。
  - 路径遍历测试。
  - 存储型 XSS 测试。
  - CORS 与 API Key 传输安全测试。

### 7.2 Docker 部署

- 多阶段构建、健康检查、日志轮转配置良好。
- 容器以 root 运行，建议增加非 root 用户。
- 默认监听 `0.0.0.0`，适合容器化部署，但本地开发时需注意暴露风险。

### 7.3 依赖

- `requirements.txt` 管理依赖，建议定期扫描已知漏洞（如使用 `pip-audit`）。
- 建议使用锁定文件（`requirements.lock`）固定版本。

---

## 8. 优先修复清单

| 优先级 | 问题 | 建议行动 |
|--------|------|----------|
| P0 | 存储型 XSS | 统一前端 HTML 转义，消除 `ui.js` 中按角色跳过转义的逻辑 |
| P0 | 路径遍历 | 合婚工具改用 `tempfile.NamedTemporaryFile` |
| P1 | CORS 通配 | 生产环境禁用 `*`，默认仅允许显式配置的来源 |
| P1 | API Key query 传输 | 移除或强制生产环境关闭 |
| P1 | 日志泄露 | 停止记录任何 API Key 片段 |
| P2 | 提示词注入 | 强化输入过滤与角色隔离 |
| P2 | CSRF 防护 | 为浏览器端状态变更接口增加 CSRF Token |
| P2 | 输入验证 | 统一 Pydantic 校验器与正则约束 |
| P3 | 构建产物 | 将 `dist/`、`build/` 加入 `.gitignore` |
| P3 | 测试补充 | 增加前端安全与认证绕过测试 |

---

## 9. 结论

玄机子项目功能完整、架构合理，但在面向用户的安全上存在明显短板。建议优先处理：

1. **存储型 XSS**
2. **路径遍历**
3. **CORS 与 API Key 传输策略**

随后逐步完善输入验证、CSRF 防护、提示词注入防御，并建立常态化的安全测试与代码审计流程。

---

## 10. 附录：审查文件清单

- `api_server.py`
- `config.py`
- `claude_api.py`
- `bazi_calculator.py`
- `auto_analyzer.py`
- `data_store.py`
- `static/js/ui.js`
- `static/js/render-bazi.js`
- `static/app.js`
- `templates/index.html`
- `Dockerfile`
- `docker-compose.yml`
- `requirements.txt`
- `pytest.ini`
- `tests/` 目录
- `knowledge-base/` 目录
- `improvement_part_engineering.md`
