# 八字分析网站质量提升 + Windows 客户端设计

> **Status:** Design approved, pending implementation plan.
> **Date:** 2026-06-02
> **Goal:** Fix core calculation bugs, improve AI analysis quality from 0.56 to 0.7+, polish UX, add E2E tests, and produce a standalone Windows .exe.

---

## P0: 计算引擎 Bug 修复

### Bug 1: 十神正/偏反转

**位置:** `bazi_calculator.py` — `get_shishen()` 函数

**问题:** `same_yy` 逻辑与经典定义相反：
- 经典规则: 克我/我克/生我 三类中，阴阳相反 → 正（正官/正印/正财），阴阳相同 → 偏（七杀/偏印/偏财）
- 当前代码: `same_yy → 正`, `!same_yy → 偏`，完全颠倒

**影响:** 正官↔七杀、正印↔偏印、正财↔偏财全部反转。比肩/劫财、食神/伤官不受影响。

**修复方案:** 翻转 `get_shishen()` 中 克我/我克/生我 三类关系的 `same_yy` 判断。
```python
# 修复前: same_yy → '正'
# 修复后: same_yy → '偏'  (异性相反=正)
```

**验证:** 选克林顿案例（丙戌 丙申 乙丑 庚辰），乙木见庚金为七杀（同性），修复前后对比确认。

### Bug 2: 紫微星曜索引混用

**问题:** `calculate_ziwei()` 中 `stars.get(DIZHI.index(pzhi), [])` 使用 0=子 索引，但 `ziwei_position()` 使用 0=寅 索引，offset 差 2 位。

**修复方案:** 将 palace lookup 统一为 0=寅 索引，与 `ziwei_position()` 保持一致。

**验证:** 选已知案例手工计算紫微盘，与修复后输出对比。

### Bug 3: 身宫函数重复定义

**问题:** `get_shengong()` 被定义了两次，后者覆盖前者。

**修复方案:** 保留正确的实现，删除重复定义。

### Bug 4: 节气交界处理

**问题:** 节气边界使用简化月/日阈值。

**修复方案:** 使用 `solar_terms.json` 精确时刻判断。

### Bug 5: 紫微农历日近似

**问题:** `lunar_day = day if day <= 30 else 30`，直接用公历日代替农历日。

**修复方案:** 调用 `lunar_calendar.py` 的 `solar_to_lunar()` 获取准确的农历日期。

### 验证策略

- **快速验证**: 选 10 个基准案例（覆盖所有 bug），手工对比修复前后差异
- **全量回归**: 跑全部 52 个 benchmark charts + 1,113 个 accuracy 测试用例
- **验收标准**: accuracy 保持 100%，consistency ≥ 97%

---

## P1: AI 分析质量提升

### 当前状态

| 维度 | 评分 | 问题 |
|------|------|------|
| 综合 | 0.56 | 17.5% 正面命中率 |
| 事业 | 0.74 | 较强 |
| 健康 | 0.47 | 弱 |
| 家庭 | 0.24 | 极弱 |
| 财运 | 0.36 | 弱 |

### 提升策略

**策略 1: 提示词注入领域知识**

将知识库中的核心歌诀（gejue_core.json, 178 条精选歌诀）注入系统提示词或作为 few-shot 示例。选取与健康/家庭主题最相关的 30 条歌诀作为上下文，引导模型给出更精准的判断。

**策略 2: 结构化判断模板强制约束**

修改 API 调用的 system prompt，要求 AI 对每个分析维度输出：
```json
{
  "dimension": "health",
  "conclusion": "...",
  "basis": ["干支X", "五行Y"],
  "confidence": "high|medium|low"
}
```
结构化输出减少模型自由发挥导致的错误。

**策略 3: 基准案例 Few-Shot**

从 52 个 benchmark charts 中选出最优质的 5-8 个案例（事业/财运/健康/家庭维度覆盖），将其分析结论作为 few-shot 示例注入系统提示词。

**策略 4: 双系统交叉验证增强**

对每次分析，并行调用两次 API（temperature=0.1 和 temperature=0.3），对比核心结论一致性。分歧 > 30% 时标记低置信度，不输出争议结论。

### 验收标准

- 综合质量评分从 0.56 → 0.70+
- 健康维度从 0.47 → 0.60+
- 家庭维度从 0.24 → 0.50+
- 正面命中率从 17.5% → 30%+

---

## P2: 用户体验打磨

### 界面改进

1. **报告区实时滚动**: 对 SSE 流式输出，自动滚动到最新内容（当前需手动下拉）
2. **加载状态指示器**: AI 思考时显示脉动动画，替代当前简单的文本提示
3. **八字排盘可视化**: 用表格/卡片展示四柱八字，替代纯 JSON 渲染
4. **五行数量颜色统一**: 确保五行计数数字颜色与对应五行颜色一致（已有部分实现）
5. **PDF 下载按钮优化**: 移入报告工具栏，始终可见

### 响应速度

1. **图表 JSON 缓存**: 前端缓存 chart JSON，切换命主时不需要重新请求
2. **知识库预加载**: 服务启动时预热知识库，首次检索零延迟
3. **SQLite WAL 模式**: 已启用，验证读写性能

### 移动端

- 当前已有 mobile nav 四按钮切换面板
- 需要修复: 横屏模式下的布局溢出问题
- 输入框在小屏幕上的可用性差（当前 min-width: 0 已修复部分）

### PDF 报告

- 当前 4 个模板（dark/modern/scroll/night）功能可用
- 字体 fallback 已实现（Linux Noto CJK）
- 改进: 增加封面页、目录、页码

---

## P3: 工程健壮性

### E2E 测试（Playwright）

1. **完整排盘流程**: 输入出生信息 → 排盘 → 验证四柱和报告生成
2. **多命主管理**: 添加/切换/删除命主 → 验证数据隔离
3. **聊天对话**: 发送消息 → 验证 SSE 流式响应 → 验证聊天持久化
4. **工具调用**: 择日/取名/流年/合婚各工具 → 验证结果展示
5. **数据持久化**: 创建数据 → 模拟重启 → 验证数据恢复

### 单元测试

1. `data_store.py` — 新模块，零测试覆盖。需要覆盖 CRUD + 级联删除
2. `claude_api.py` — API key 加载、provider 检测、payload 构建

### Docker 部署

- 当前 Dockerfile 存在但 Playwright + 完整 CJK 字体未集成
- 需要: `docker compose up` 一键启动，自动健康检查
- 添加 `.env.example` 文件说明环境变量配置

---

## P4: Windows .exe 客户端

### 方案: PyInstaller + pywebview

**产物**: 单个 `玄机子.exe` 文件，约 80-120MB

**打包配置** (`app.spec`):
- 入口: `desktop_app.py`
- 隐藏导入: `uvicorn`, `fastapi`, `pydantic`, `fpdf2`, `sqlite3`
- 数据文件: `templates/`, `static/`, `knowledge-base/`, `.claude/`
- 排除: `tests/`, `docs/`, `reports/`

**打包命令**:
```bash
pyinstaller --onedir --windowed --name 玄机子 \
    --add-data "templates;templates" \
    --add-data "static;static" \
    --add-data "knowledge-base;knowledge-base" \
    --hidden-import uvicorn.loops.auto \
    desktop_app.py
```

**注意事项**:
1. `pywebview` 依赖 Edge WebView2 Runtime（Win10/11 系统自带，Win7 需安装）
2. `.deepseek_key` / `.anthropic_key` 文件放在 .exe 同目录下
3. `bazi_data.db` 数据库文件在 .exe 同目录下自动创建
4. 首次启动需要几秒解压依赖

---

## 实施顺序

```
P0 (计算Bug修复) ──→ P1 (AI质量) ──→ P2 (UX) ──→ P3 (工程) ──→ P4 (客户端)
    ↓                    ↓                ↓             ↓              ↓
  2-3天               3-4天           2-3天         2-3天          1-2天
```

**总计**: 约 10-15 个工作日

**依赖关系**: P0 必须在 P1 之前（AI 分析质量依赖正确的基础数据）。P2/P3 可并行。P4 在所有功能稳定后进行。

---

## 风险与注意事项

1. **P0 Bug 修复风险**: 十神反转修复后，所有使用十神的下游分析（旺衰、格局、大运喜忌）都会变化，需要全面回归测试
2. **紫微修复风险**: 星曜索引修正后 UI 中的紫微盘面显示可能变化，前端渲染需同步验证
3. **PyInstaller 打包风险**: FastAPI + asyncio + uvicorn 打包可能有隐式依赖遗漏，需要在一台干净的 Windows 机器上测试
4. **模型质量提升不确定性**: AI 分析质量是迭代过程，0.56 → 0.70 是目标而非保证
