# 第五章 工程实践改进方案

> 本文档针对"玄机子"八字命理 AI 项目的工程实践层面，提出系统性的改进方案。每个小节包含当前问题分析、详细改进方案（含完整代码示例）、实施步骤和预期收益。

---

## 5.1 CI/CD 自动化

### 5.1.1 当前问题分析

当前项目已有的 `.github/workflows/ci.yml` 存在以下不足：

1. **流水线过于简单**：仅包含语法检查和基础测试，缺少代码质量检查（lint/type-check）环节。
2. **测试执行被忽略失败**：`pytest` 命令末尾使用 `|| true`，即使测试失败也不会阻断流水线，失去了 CI 的质量守门意义。
3. **缺少多版本 Python 测试矩阵**：仅测试 Python 3.11，无法验证兼容性。
4. **缺少自动化构建与发布**：PyInstaller 桌面版打包、Docker 镜像构建推送均未自动化。
5. **缺少缓存优化**：pip 缓存虽然配置了，但缺少 Docker 层缓存。
6. **缺少分支保护策略**：没有针对 `main` 分支的 status check 强制要求。
7. **缺少自动化版本号管理**：没有语义化版本标记和 changelog 生成。

### 5.1.2 详细改进方案

#### 方案一：完整 GitHub Actions 工作流

将单一 CI 工作流拆分为多个职责清晰的工作流文件：

**文件：`.github/workflows/ci.yml`（重构后的主 CI 流水线）**

```yaml
name: CI Pipeline

on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master]
  workflow_dispatch:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHON_VERSION: "3.11"
  PIP_DISABLE_PIP_VERSION_CHECK: 1

jobs:
  # ────────────────────────────────────────────
  # Job 1: 代码质量检查（Lint & Type Check）
  # ────────────────────────────────────────────
  lint:
    name: Code Quality
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install lint dependencies
        run: |
          pip install -r requirements-dev.txt
          pip install black isort ruff mypy

      - name: Check code formatting (Black)
        run: black --check --diff --line-length 100 .
        continue-on-error: true

      - name: Check import sorting (isort)
        run: isort --check-only --diff --profile black .
        continue-on-error: true

      - name: Lint with Ruff
        run: ruff check --output-format=github .
        continue-on-error: true

      - name: Type check with mypy
        run: |
          mypy --ignore-missing-imports \
               --no-strict-optional \
               --warn-unused-ignores \
               api_server.py config.py data_store.py bazi_calculator.py
        continue-on-error: true

  # ────────────────────────────────────────────
  # Job 2: 多版本 Python 测试矩阵
  # ────────────────────────────────────────────
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    needs: lint
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: |
          python -m pytest tests/test_api.py tests/test_bazi_kb.py \
            tests/test_data_store.py tests/test_rate_limit.py \
            -v --tb=short --timeout=120 \
            --junitxml=reports/junit-${{ matrix.python-version }}.xml

      - name: Run accuracy tests
        run: |
          python -m pytest tests/test_accuracy.py tests/test_consistency.py \
            tests/test_bingyao.py \
            -v --tb=short --timeout=300 \
            --junitxml=reports/junit-accuracy-${{ matrix.python-version }}.xml

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-reports-py${{ matrix.python-version }}
          path: reports/junit-*.xml
          retention-days: 30

  # ────────────────────────────────────────────
  # Job 3: Docker 镜像构建验证
  # ────────────────────────────────────────────
  docker:
    name: Docker Build
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push'
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build Docker image (verify)
        uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          load: true
          tags: xuanjizi:test
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Smoke test in container
        run: |
          docker run --rm -d --name xuanjizi-smoke -p 8000:8000 xuanjizi:test
          sleep 5
          curl -sf http://localhost:8000/api/health || exit 1
          docker stop xuanjizi-smoke
```

**文件：`.github/workflows/release.yml`（发布流水线）**

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'  # 仅当推送 v1.0.0 格式标签时触发

permissions:
  contents: write
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # ────────────────────────────────────────────
  # Job 1: PyInstaller 桌面版打包
  # ────────────────────────────────────────────
  build-desktop:
    name: Build Desktop (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 30
    strategy:
      matrix:
        os: [windows-latest, macos-latest]
        include:
          - os: windows-latest
            artifact: XuanJiZi-Windows.zip
          - os: macos-latest
            artifact: XuanJiZi-macOS.zip
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Build with PyInstaller
        run: pyinstaller app.spec --noconfirm

      - name: Package artifact
        shell: pwsh
        run: |
          $distDir = if ($env:RUNNER_OS -eq "Windows") { "dist\XuanJiZi" } else { "dist/XuanJiZi" }
          Compress-Archive -Path $distDir -DestinationPath ${{ matrix.artifact }}

      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact }}
          path: ${{ matrix.artifact }}
          retention-days: 7

  # ────────────────────────────────────────────
  # Job 2: Docker 镜像构建并推送
  # ────────────────────────────────────────────
  build-docker:
    name: Build & Push Docker Image
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4

      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ────────────────────────────────────────────
  # Job 3: 创建 GitHub Release
  # ────────────────────────────────────────────
  release:
    name: Create Release
    runs-on: ubuntu-latest
    needs: [build-desktop, build-docker]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # 获取全部历史以生成 changelog

      - name: Download all artifacts
        uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: Generate changelog
        id: changelog
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo "")
          if [ -n "$PREV_TAG" ]; then
            echo "CHANGES<<EOF" >> $GITHUB_OUTPUT
            git log --pretty=format:"- %s (%h)" ${PREV_TAG}..HEAD >> $GITHUB_OUTPUT
            echo "EOF" >> $GITHUB_OUTPUT
          else
            echo "CHANGES=Initial release" >> $GITHUB_OUTPUT
          fi

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          body: |
            ## 变更内容
            ${{ steps.changelog.outputs.CHANGES }}

            ## 下载
            - Windows 桌面版: XuanJiZi-Windows.zip
            - macOS 桌面版: XuanJiZi-macOS.zip
            - Docker 镜像: `docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.ref_name }}`
          files: artifacts/**/*.zip
          draft: false
          prerelease: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**文件：`.github/workflows/nightly.yml`（每日定时集成测试）**

```yaml
name: Nightly Integration Test

on:
  schedule:
    - cron: '0 2 * * *'  # 每天凌晨 2 点（UTC）
  workflow_dispatch:

jobs:
  integration:
    name: E2E Integration Test
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt

      - name: Start API server
        run: |
          python api_server.py &
          sleep 5
          curl -sf http://localhost:8000/api/health

      - name: Run E2E tests
        run: |
          python -m pytest tests/test_e2e.py -v --tb=long --timeout=300

      - name: Run full accuracy suite
        run: |
          python -m pytest tests/test_accuracy.py tests/test_consistency.py \
            tests/test_bingyao.py -v --tb=short --timeout=600

      - name: Stop server
        if: always()
        run: pkill -f "python api_server.py" || true

      - name: Notify on failure
        if: failure()
        run: |
          echo "::error::Nightly integration test failed! Check logs for details."
```

#### 方案二：代码质量配置文件

**文件：`pyproject.toml`（项目级工具配置）**

```toml
[project]
name = "xuanjizi"
version = "1.0.0"
description = "玄机子 - 八字命理 AI 分析系统"
requires-python = ">=3.10"

# ── Black 代码格式化 ──
[tool.black]
line-length = 100
target-version = ["py311"]
include = '\.pyi?$'
extend-exclude = '''
/(
    \.git
  | \.venv
  | build
  | dist
  | knowledge-base
)/
'''

# ── isort 导入排序 ──
[tool.isort]
profile = "black"
line_length = 100
skip_glob = ["build/*", "dist/*", "knowledge-base/*"]
known_third_party = ["fastapi", "uvicorn", "pydantic", "webview"]

# ── Ruff 代码检查 ──
[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["build", "dist", "knowledge-base"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "RUF",  # ruff-specific
]
ignore = [
    "E501",   # line too long (handled by black)
    "B008",   # do not perform function calls in argument defaults
    "N802",   # function name should be lowercase (allow Chinese naming)
    "RUF001", # ambiguous unicode characters (Chinese strings)
    "RUF003", # ambiguous unicode character (Chinese strings)
]

[tool.ruff.lint.per-file-ignores]
"tests/*.py" = ["N802", "B011"]
"tools/*.py" = ["N802"]

# ── mypy 类型检查 ──
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
no_strict_optional = true
warn_unused_ignores = true
exclude = [
    "build/",
    "dist/",
    "knowledge-base/",
    "tests/",
]

# ── pytest 配置 ──
[tool.pytest.ini_options]
testpaths = ["tests"]
timeout = 120
addopts = "-v --tb=short"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "e2e: end-to-end tests",
    "accuracy: accuracy validation tests",
]
```

#### 方案三：Pre-commit Hooks

**文件：`.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=1024']
      - id: check-merge-conflict
      - id: debug-statements

  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
        args: ['--line-length', '100']

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ['--profile', 'black', '--line-length', '100']

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.8
    hooks:
      - id: ruff
        args: ['--fix']
```

### 5.1.3 实施步骤

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| 第 1 周 | 创建 `pyproject.toml`，配置 Black/isort/ruff/mypy 规则 | 1 天 |
| 第 1 周 | 重构 `.github/workflows/ci.yml`，拆分为 lint + test + docker 三个 job | 1 天 |
| 第 1 周 | 移除 `|| true`，修复现有测试失败问题 | 2 天 |
| 第 2 周 | 创建 `release.yml`，配置 PyInstaller 自动打包和 Docker 推送 | 2 天 |
| 第 2 周 | 配置 `pre-commit` hooks，团队统一代码风格 | 1 天 |
| 第 3 周 | 创建 `nightly.yml`，配置每日集成测试 | 1 天 |
| 第 3 周 | 配置分支保护规则（main 分支要求 lint + test 通过才能合并） | 0.5 天 |

### 5.1.4 预期收益

- **代码质量提升**：通过自动化 lint 和类型检查，在合并前发现潜在问题，预计减少 40% 的代码缺陷。
- **发布效率提升**：从手动打包到自动发布，版本发布时间从 30 分钟缩短至 5 分钟。
- **兼容性保障**：多版本 Python 测试矩阵确保在 3.10/3.11/3.12 上均可运行。
- **回归风险降低**：每日夜间集成测试，及早发现因依赖更新导致的问题。

---

## 5.2 文档完善

### 5.2.1 当前问题分析

1. **Swagger 文档过于简单**：当前 `api_server.py` 中的端点仅有简短中文描述，缺少请求/响应示例、错误码说明、参数约束详情。
2. **缺少用户使用指南**：虽有 `docs/USER_GUIDE.md`，但缺少从安装到使用的完整流程、常见问题解答。
3. **开发者文档不足**：`docs/SYSTEM_ARCHITECTURE.md` 存在但缺少模块交互图、数据流图、贡献指南。
4. **API 文档与实现不同步**：手动维护的文档容易与实际接口不一致。
5. **缺少错误码文档**：客户端无法预知各类错误码的含义和处理方式。

### 5.2.2 详细改进方案

#### 方案一：Swagger/OpenAPI 文档增强

在 `api_server.py` 中为每个端点添加详细的 `summary`、`description`、`response_model`、`examples`：

```python
# api_server.py 中的改进示例

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
import json

app = FastAPI(
    title="玄机子 · 八字命理分析 API",
    description="""
## 概述

玄机子是一个基于传统命理学理论的八字命理 AI 分析系统，提供以下核心能力：

- **排盘引擎**：精确计算四柱八字、大运、五行统计
- **AI 深度分析**：接入 Claude/DeepSeek 大模型进行命理分析
- **知识库检索**：内置经典歌诀、神煞、纳音等命理知识
- **辅助工具**：择日、流年日历、取名评测、合婚分析

## 认证

如服务端配置了 API Key，需在请求头中携带：
```
Authorization: Bearer YOUR_API_KEY
```

## 错误码说明

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误（如缺少 chart_id） |
| 401 | 未认证或 API Key 无效 |
| 404 | 资源不存在（chart_id 无效） |
| 409 | 资源状态冲突（PDF 尚未生成完成） |
| 413 | 请求体超过大小限制 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |
    """,
    version="1.0.0",
    contact={
        "name": "玄机子项目",
        "url": "https://github.com/example/xuanjizi",
    },
    license_info={
        "name": "MIT",
    },
    openapi_tags=[
        {"name": "排盘", "description": "八字排盘相关接口"},
        {"name": "分析", "description": "AI 分析与报告生成"},
        {"name": "工具", "description": "择日、流年、取名等辅助工具"},
        {"name": "知识库", "description": "命理知识库检索"},
        {"name": "存储", "description": "命盘数据持久化管理"},
        {"name": "系统", "description": "健康检查、指标监控"},
    ],
)
```

为每个端点添加详细示例：

```python
class BirthInfo(BaseModel):
    """出生信息"""
    year: int = Field(
        ...,
        ge=1900, le=2100,
        description="出生年份",
        examples=[1993],
    )
    month: int = Field(
        ...,
        ge=1, le=12,
        description="出生月份（公历）",
        examples=[7],
    )
    day: int = Field(
        ...,
        ge=1, le=31,
        description="出生日期（公历）",
        examples=[15],
    )
    hour: int = Field(
        0,
        ge=0, le=23,
        description="出生小时（24 小时制）",
        examples=[14],
    )
    minute: int = Field(
        0,
        ge=0, le=59,
        description="出生分钟",
        examples=[30],
    )
    gender: str = Field(
        "male",
        pattern="^(male|female)$",
        description="性别：male（男）或 female（女）",
        examples=["male"],
    )
    location: str = Field(
        "Beijing",
        description="出生地点（用于真太阳时校正），支持中英文城市名",
        examples=["Beijing", "上海", "Guangzhou"],
    )
    use_solar_time: bool = Field(
        False,
        description="若为 True，表示 hour/minute 已经是真太阳时，服务端不再校正",
        examples=[False],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "year": 1993,
                    "month": 7,
                    "day": 15,
                    "hour": 14,
                    "minute": 30,
                    "gender": "male",
                    "location": "Beijing",
                    "use_solar_time": False,
                }
            ]
        }
    }


@app.post(
    "/api/chart",
    tags=["排盘"],
    summary="八字排盘",
    description="""
根据出生信息计算完整的八字命盘，包括：
- 四柱（年柱、月柱、日柱、时柱）
- 日主五行属性
- 十神关系
- 五行统计
- 大运排列
- 神煞列表

计算结果会缓存到内存并持久化到本地数据库。
返回的 `chart_id` 用于后续所有分析和工具调用。
    """,
    responses={
        200: {
            "description": "排盘成功",
            "content": {
                "application/json": {
                    "example": {
                        "chart_id": "a1b2c3d4e5f6",
                        "birth_info": {
                            "year": 1993, "month": 7, "day": 15,
                            "hour": 14, "minute": 30,
                            "gender": "male", "location": "Beijing",
                        },
                        "four_pillars": {
                            "year": {"gan": "癸", "zhi": "酉", "wuxing_gan": "水", "wuxing_zhi": "金"},
                            "month": {"gan": "己", "zhi": "未", "wuxing_gan": "土", "wuxing_zhi": "土"},
                            "day": {"gan": "丙", "zhi": "寅", "wuxing_gan": "火", "wuxing_zhi": "木"},
                            "hour": {"gan": "乙", "zhi": "未", "wuxing_gan": "木", "wuxing_zhi": "土"},
                        },
                        "day_master": {"gan": "丙", "wuxing": "火"},
                        "wuxing_stats": {"金": 2, "木": 3, "水": 1, "火": 3, "土": 3},
                    }
                }
            },
        },
        422: {
            "description": "参数校验失败",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {"loc": ["body", "year"], "msg": "ensure this value is greater than or equal to 1900", "type": "value_error.number.not_ge"}
                        ]
                    }
                }
            },
        },
    },
)
def calculate_chart(birth: BirthInfo):
    """排盘 -- calculate full BaZi chart, persist to local DB"""
    # ... 实现保持不变 ...
    pass
```

为 SSE 流式聊天端点添加文档：

```python
@app.get(
    "/api/chat/stream",
    tags=["分析"],
    summary="AI 流式对话",
    description="""
通过 Server-Sent Events (SSE) 进行流式 AI 命理对话。

**事件类型：**
- `tool`：当前使用的分析工具名称
- `reply`：AI 回复文本增量
- `report`：报告内容增量（含 tab 分类）
- `done`：对话结束信号

**使用方式：**
客户端通过 EventSource 或 HTTP 流读取方式连接，逐事件处理。

**注意：**
- 需要先通过 POST /api/chart 创建命盘
- 单次请求最大输出 16384 tokens
- 请求频率限制：每 IP 每 60 秒最多 30 次
    """,
    parameters=[
        {
            "name": "chart_id",
            "in": "query",
            "required": True,
            "description": "命盘 ID（由 POST /api/chart 返回）",
            "schema": {"type": "string"},
            "example": "a1b2c3d4e5f6",
        },
        {
            "name": "message",
            "in": "query",
            "required": True,
            "description": "用户提问内容",
            "schema": {"type": "string"},
            "example": "请分析我的财运",
        },
    ],
    responses={
        200: {
            "description": "SSE 流式响应",
            "content": {
                "text/event-stream": {
                    "example": 'event: tool\ndata: {"name": "四合出分析"}\n\nevent: reply\ndata: {"text": "根据命盘分析..."}\n\nevent: done\ndata: {"corrections": 0}\n\n'
                }
            },
        },
        400: {
            "description": "缺少有效的 chart_id",
        },
    },
)
async def chat_stream(chart_id: str, message: str):
    # ... 实现保持不变 ...
    pass
```

#### 方案二：用户使用指南结构

**文件：`docs/USER_GUIDE.md`**

```markdown
# 玄机子 用户使用指南

## 目录

1. [简介](#简介)
2. [快速开始](#快速开始)
3. [桌面版使用](#桌面版使用)
4. [Web 版使用](#web-版使用)
5. [Docker 部署](#docker-部署)
6. [功能详解](#功能详解)
   - 6.1 [八字排盘](#61-八字排盘)
   - 6.2 [AI 命理对话](#62-ai-命理对话)
   - 6.3 [择日工具](#63-择日工具)
   - 6.4 [流年日历](#64-流年日历)
   - 6.5 [取名评测](#65-取名评测)
   - 6.6 [合婚分析](#66-合婚分析)
   - 6.7 [PDF 报告导出](#67-pdf-报告导出)
7. [配置说明](#配置说明)
8. [常见问题 FAQ](#常见问题-faq)
9. [故障排除](#故障排除)

## 快速开始

### 系统要求

- Python 3.10 或更高版本
- Windows 10/11、macOS 12+、Linux（桌面版）
- 或 Docker 环境（服务端部署）

### 桌面版（推荐新手）

1. 从 [Releases 页面](https://github.com/example/xuanjizi/releases) 下载对应系统的安装包
2. 解压后双击 `XuanJiZi.exe`（Windows）或 `XuanJiZi.app`（macOS）
3. 在设置中配置 AI API Key（DeepSeek 或 Anthropic）
4. 输入出生信息，开始分析

### Web 版 / Docker 部署

```bash
# 1. 克隆仓库
git clone https://github.com/example/xuanjizi.git
cd xuanjizi

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key

# 3. 启动服务
docker compose up -d

# 4. 访问
# Web 界面: http://localhost:8000
# API 文档: http://localhost:8000/docs
```

## 常见问题 FAQ

### Q: 什么是真太阳时？需要开启吗？

**A:** 真太阳时是根据出生地的经度，将北京时间（东八区标准时）校正为当地实际太阳位置的时间。
例如，乌鲁木齐的真太阳时比北京时间晚约 2 小时。

**建议：** 如果您知道准确的当地时间，可以开启"已校正真太阳时"选项；
如果只知道北京时间，建议关闭此选项，系统会自动根据出生地点校正。

### Q: DeepSeek 和 Anthropic（Claude）该选哪个？

**A:**
| 对比项 | DeepSeek | Anthropic (Claude) |
|--------|----------|-------------------|
| 价格 | 较低，性价比高 | 较高 |
| 中文能力 | 优秀 | 优秀 |
| 命理分析质量 | 良好 | 略优 |
| 响应速度 | 快 | 中等 |

**建议：** 日常使用推荐 DeepSeek，追求极致分析质量可选 Claude。

### Q: 排盘结果与万年历不一致？

**A:** 可能原因：
1. 子时（23:00-01:00）的日柱归属问题——本系统采用"早子时/晚子时"分法
2. 真太阳时校正差异——请确认出生地点设置是否正确
3. 节气交接时间精度——本系统使用天文算法计算节气

### Q: 如何批量分析多个命盘？

**A:** 可通过 API 接口编程调用：
```python
import requests

API_BASE = "http://localhost:8000"
HEADERS = {"Authorization": "Bearer YOUR_API_KEY"}

# 排盘
resp = requests.post(f"{API_BASE}/api/chart", json={
    "year": 1993, "month": 7, "day": 15, "hour": 14, "gender": "male"
}, headers=HEADERS)
chart_id = resp.json()["chart_id"]

# AI 分析
resp = requests.get(f"{API_BASE}/api/chat/stream", params={
    "chart_id": chart_id,
    "message": "请全面分析此命盘"
}, headers=HEADERS, stream=True)
for line in resp.iter_lines():
    print(line.decode())
```

### Q: 报告 PDF 生成失败？

**A:** 请检查：
1. 系统是否安装了中文字体（Linux 需要 `fonts-noto-cjk`）
2. 临时目录是否有写入权限
3. 查看日志中的具体错误信息

## 故障排除

| 问题 | 可能原因 | 解决方法 |
|------|----------|----------|
| 启动闪退 | 缺少 VC++ 运行库 | 安装 [VC++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| AI 回复为空 | API Key 未配置或失效 | 检查 .env 文件中的 Key 是否正确 |
| 排盘结果异常 | 出生地点设置错误 | 确认城市名称拼写正确 |
| 端口被占用 | 8000 端口已被使用 | 修改 BAZI_API_PORT 环境变量 |
| Docker 启动失败 | 端口映射冲突 | 修改 docker-compose.yml 中的端口映射 |
```

#### 方案三：开发者文档

**文件：`docs/DEVELOPER_GUIDE.md`**

```markdown
# 玄机子 开发者文档

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     客户端层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  pywebview   │  │   Web 浏览器  │  │  MCP Client  │  │
│  │  桌面版       │  │  (任意浏览器) │  │  (AI 编辑器)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────┼──────────────────┼──────────────────┼──────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                    API 网关层                             │
│  ┌────────────────────────────────────────────────────┐ │
│  │  FastAPI (api_server.py)                           │ │
│  │  - CORS 中间件                                      │ │
│  │  - 认证中间件 (API Key)                             │ │
│  │  - 限流中间件 (per-IP sliding window)               │ │
│  │  - 请求体大小限制                                   │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│  排盘引擎     │ │  AI 分析层    │ │  知识库           │
│  bazi_calc   │ │  claude_api  │ │  knowledge-base/ │
│  lunar_calc  │ │  auto_analyze│ │  - bazi_kb.py    │
│              │ │  report_build│ │  - search.py     │
│              │ │  report_pdf  │ │  - case_retrieval│
└──────────────┘ └──────────────┘ └──────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    持久化层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  SQLite      │  │  文件系统     │  │  内存缓存     │  │
│  │  data_store  │  │  reports/    │  │  ChartCache  │  │
│  │  bazi_data.db│  │  data/charts │  │  (LRU)       │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 模块说明

| 模块 | 文件 | 职责 |
|------|------|------|
| API 服务 | `api_server.py` | FastAPI 路由、中间件、请求处理 |
| 排盘引擎 | `bazi_calculator.py` | 四柱计算、大运、五行统计 |
| 农历转换 | `lunar_calendar.py` | 农历/公历互转 |
| AI 接口 | `claude_api.py` | LLM API 调用（Anthropic/DeepSeek） |
| 自动分析 | `auto_analyzer.py` | 结构化命理分析预判 |
| 报告构建 | `report_builder.py` | Markdown 报告模板渲染 |
| PDF 导出 | `report_to_pdf.py` | Markdown → PDF 转换 |
| 数据存储 | `data_store.py` | SQLite CRUD 操作 |
| 桌面应用 | `desktop_app.py` | pywebview 桌面版入口 |
| MCP 服务 | `mcp_server.py` | Model Context Protocol 服务端 |
| 配置中心 | `config.py` | 环境变量加载与配置管理 |

## 开发环境搭建

```bash
# 1. 克隆仓库
git clone https://github.com/example/xuanjizi.git
cd xuanjizi

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements-dev.txt
pip install pre-commit
pre-commit install

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 5. 构建知识库
python -c "import sys; sys.path.insert(0, 'knowledge-base'); from bazi_kb import BaziKnowledgeBase; kb = BaziKnowledgeBase(); kb.build(); kb.close()"

# 6. 启动开发服务器
uvicorn api_server:app --reload --port 8000
```

## 测试指南

```bash
# 运行全部测试
pytest tests/ -v

# 仅运行单元测试
pytest tests/test_api.py tests/test_data_store.py -v

# 运行精度测试
pytest tests/test_accuracy.py -v

# 运行一致性测试
pytest tests/test_consistency.py -v

# 运行 E2E 测试（需要运行中的服务）
pytest tests/test_e2e.py -v

# 生成覆盖率报告
pytest --cov=. --cov-report=html
```

## 贡献指南

1. Fork 项目仓库
2. 创建功能分支：`git checkout -b feature/my-feature`
3. 编写代码和测试
4. 确保所有测试通过：`pytest tests/ -v`
5. 确保代码风格：`black . && isort . && ruff check .`
6. 提交变更：`git commit -am 'feat: add my feature'`
7. 推送分支：`git push origin feature/my-feature`
8. 创建 Pull Request

### Commit 消息规范

采用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档变更
- `style:` 代码格式（不影响逻辑）
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 构建/工具变更
```

### 5.2.3 实施步骤

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| 第 1 周 | 为所有 API 端点添加详细的 OpenAPI 文档（summary/description/examples/responses） | 3 天 |
| 第 2 周 | 编写完整的用户使用指南，包含 FAQ 和故障排除 | 2 天 |
| 第 2 周 | 编写开发者文档，包含架构图、模块说明、贡献指南 | 2 天 |
| 第 3 周 | 配置 Swagger UI 自定义主题和中文本地化 | 1 天 |

### 5.2.4 预期收益

- **降低使用门槛**：完整的用户指南使新用户上手时间从 30 分钟缩短至 5 分钟。
- **提升 API 可用性**：Swagger 文档中的示例和错误码说明，使第三方集成效率提升 60%。
- **减少重复答疑**：FAQ 覆盖 80% 的常见问题，减少重复答疑工作量。
- **促进社区贡献**：清晰的开发者文档和贡献指南有助于吸引开源贡献者。

---

## 5.3 监控和日志

### 5.3.1 当前问题分析

1. **日志格式不统一**：当前使用 `logging.basicConfig` 配置纯文本日志，格式为 `%(asctime)s [%(levelname)s] %(name)s: %(message)s`，不利于自动化解析和搜索。
2. **多处重复配置 logging**：`api_server.py`、`desktop_app.py`、`claude_api.py` 各自独立调用 `logging.basicConfig`，存在配置冲突风险。
3. **缺少错误追踪**：线上异常只能靠本地日志排查，缺少 Sentry 等集中式错误监控。
4. **Prometheus 指标过于简单**：仅有请求计数、限流计数等基础指标，缺少延迟分布、错误率、AI 调用耗时等关键指标。
5. **缺少请求追踪**：无法跟踪一个请求在各模块间的完整链路。
6. **缺少告警机制**：没有配置告警规则，异常情况无法主动发现。

### 5.3.2 详细改进方案

#### 方案一：结构化日志（structlog）

**新增文件：`logging_config.py`（统一日志配置模块）**

```python
"""
统一日志配置 — 使用 structlog 输出结构化 JSON 日志。

所有模块应通过此模块初始化日志，而非直接调用 logging.basicConfig。
使用方式：
    from logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("chart_created", chart_id="abc123", user_ip="1.2.3.4")
"""

import logging
import os
import sys
from typing import Optional

import structlog
from pythonjsonlogger import jsonlogger


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_output: bool = True,
) -> None:
    """
    初始化全局日志系统。

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 日志文件路径，None 表示仅输出到 stderr
        json_output: 是否输出 JSON 格式（生产环境推荐 True）
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # ── 共享处理器链 ──
    shared_processors = [
        structlog.contextvars.merge_contextvars,    # 合并上下文变量（如 request_id）
        structlog.stdlib.add_logger_name,           # 添加 logger 名称
        structlog.stdlib.add_log_level,             # 添加日志级别
        structlog.stdlib.ExtraAdder(),              # 添加额外字段
        structlog.processors.TimeStamper(fmt="iso"),  # ISO 格式时间戳
        structlog.processors.StackInfoRenderer(),   # 堆栈信息
    ]

    if json_output:
        # 生产环境：JSON 格式输出
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        # 开发环境：彩色控制台输出
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── 配置标准 logging handler ──
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)

    # 文件 handler（可选）
    handlers = [console_handler]
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # ── 配置根 logger ──
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    for handler in handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # ── 抑制第三方库的冗余日志 ──
    for noisy_logger in ["uvicorn.access", "werkzeug"]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取一个绑定了名称的结构化 logger。"""
    return structlog.get_logger(name)


def bind_request_context(**kwargs) -> None:
    """
    绑定请求级别的上下文变量，自动附加到该请求的所有日志。

    使用示例：
        bind_request_context(request_id="abc-123", client_ip="1.2.3.4")
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    """清除请求级别的上下文变量。"""
    structlog.contextvars.clear_contextvars()
```

**在 `api_server.py` 中集成结构化日志：**

```python
# api_server.py 顶部替换原有的 logging 配置

from logging_config import setup_logging, get_logger, bind_request_context, clear_request_context
from config import LOG_LEVEL, LOG_FILE

# 初始化日志系统（替代 logging.basicConfig）
setup_logging(level=LOG_LEVEL, log_file=LOG_FILE or None, json_output=True)
logger = get_logger("api")

# ── 请求追踪中间件 ──
import uuid

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """为每个请求绑定 request_id，记录请求/响应日志。"""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    bind_request_context(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else "unknown",
    )

    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response
    except Exception as e:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.error(
            "request_failed",
            error=str(e),
            duration_ms=duration_ms,
            exc_info=True,
        )
        raise
    finally:
        clear_request_context()
```

**依赖安装（添加到 `requirements.txt`）：**

```
structlog>=24.1.0
python-json-logger>=2.0.0
```

#### 方案二：Sentry 错误追踪集成

```python
# 文件：sentry_config.py

"""
Sentry 错误追踪集成。

在应用启动时初始化，自动捕获未处理异常并上报。
"""

import os
import sys
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration


def init_sentry():
    """
    初始化 Sentry SDK。
    通过环境变量 SENTRY_DSN 控制是否启用——未设置则跳过。
    """
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return

    environment = os.environ.get("SENTRY_ENVIRONMENT", "production")

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        # 性能追踪
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
        # 错误上报采样
        sample_rate=float(os.environ.get("SENTRY_SAMPLE_RATE", "1.0")),
        # 集成配置
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(
                level=None,       # 不自动捕获普通日志
                event_level=50,   # 仅 CRITICAL 级别上报为事件
            ),
        ],
        # 敏感数据过滤
        send_default_pii=False,
        # 请求体大小限制
        max_request_body_size="small",
        # 忽略特定异常
        ignore_errors=[
            KeyboardInterrupt,
            ConnectionResetError,
        ],
        # 环境标签
        release=os.environ.get("APP_VERSION", "dev"),
    )

    # 添加自定义标签
    sentry_sdk.set_tag("app", "xuanjizi")
    sentry_sdk.set_tag("python_version", f"{sys.version_info.major}.{sys.version_info.minor}")
```

**在 `api_server.py` 的 lifespan 中初始化：**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    from sentry_config import init_sentry
    init_sentry()
    logger.info("BaZi Analysis API starting")
    yield
    logger.info("Shutdown complete.")
```

**依赖：**

```
sentry-sdk[fastapi]>=2.0.0
```

**.env.example 新增配置项：**

```bash
# === Sentry 错误追踪 ===
# Sentry DSN（留空 = 不启用）
# SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0

# Sentry 环境标识（默认 production）
# SENTRY_ENVIRONMENT=production

# 性能追踪采样率 0.0-1.0（默认 0.1 = 10%）
# SENTRY_TRACES_RATE=0.1
```

#### 方案三：Prometheus + Grafana 监控面板

**增强 Prometheus 指标端点（替换 `api_server.py` 中的简单实现）：**

```python
# 文件：metrics.py

"""
Prometheus 指标定义与采集。

使用 prometheus_client 库替代手动计数器，支持：
- Counter（只增不减的计数器）
- Gauge（可增可减的仪表）
- Histogram（延迟分布）
- Summary（分位数统计）
"""

from prometheus_client import (
    Counter, Gauge, Histogram, Summary,
    generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry,
)
import time
from contextlib import contextmanager

# ── 使用默认注册器 ──

# HTTP 请求指标
HTTP_REQUESTS_TOTAL = Counter(
    'bazi_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code'],
)

HTTP_REQUEST_DURATION = Histogram(
    'bazi_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    'bazi_http_requests_in_progress',
    'Number of HTTP requests currently being processed',
)

# 限流指标
RATE_LIMIT_HITS_TOTAL = Counter(
    'bazi_rate_limit_hits_total',
    'Total rate limit rejections',
    ['endpoint'],
)

# 排盘指标
CHARTS_CREATED_TOTAL = Counter(
    'bazi_charts_created_total',
    'Total charts created',
)

CHARTS_CACHE_SIZE = Gauge(
    'bazi_charts_cache_size',
    'Current number of charts in memory cache',
)

# AI 调用指标
AI_CALLS_TOTAL = Counter(
    'bazi_ai_calls_total',
    'Total AI API calls',
    ['provider', 'model', 'status'],  # status: success/error/timeout
)

AI_CALL_DURATION = Histogram(
    'bazi_ai_call_duration_seconds',
    'AI API call duration in seconds',
    ['provider', 'model'],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0),
)

AI_TOKENS_TOTAL = Counter(
    'bazi_ai_tokens_total',
    'Total AI tokens consumed',
    ['provider', 'type'],  # type: input/output
)

# PDF 生成指标
PDF_JOBS_TOTAL = Counter(
    'bazi_pdf_jobs_total',
    'Total PDF generation jobs',
)

PDF_JOBS_ACTIVE = Gauge(
    'bazi_pdf_jobs_active',
    'Number of active PDF generation jobs',
)

PDF_JOB_DURATION = Histogram(
    'bazi_pdf_job_duration_seconds',
    'PDF generation duration in seconds',
    buckets=(1, 2, 5, 10, 30, 60, 120),
)

# 知识库指标
KB_SEARCH_DURATION = Histogram(
    'bazi_kb_search_duration_seconds',
    'Knowledge base search duration',
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# 系统指标
APP_INFO = Gauge(
    'bazi_app_info',
    'Application info',
    ['version', 'python_version'],
)


@contextmanager
def track_request(method: str, endpoint: str):
    """上下文管理器：追踪 HTTP 请求的延迟和状态。"""
    HTTP_REQUESTS_IN_PROGRESS.inc()
    start = time.time()
    try:
        yield
    except Exception:
        HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code="500").inc()
        raise
    finally:
        duration = time.time() - start
        HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
        HTTP_REQUESTS_IN_PROGRESS.dec()


@contextmanager
def track_ai_call(provider: str, model: str):
    """上下文管理器：追踪 AI 调用的延迟和结果。"""
    start = time.time()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.time() - start
        AI_CALLS_TOTAL.labels(provider=provider, model=model, status=status).inc()
        AI_CALL_DURATION.labels(provider=provider, model=model).observe(duration)
```

**在 `api_server.py` 中替换指标端点：**

```python
# 替换原有的 _metrics 字典和 _inc_metric 函数

from metrics import (
    HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION, HTTP_REQUESTS_IN_PROGRESS,
    RATE_LIMIT_HITS_TOTAL, CHARTS_CREATED_TOTAL, CHARTS_CACHE_SIZE,
    PDF_JOBS_TOTAL, PDF_JOBS_ACTIVE, APP_INFO,
    generate_latest, CONTENT_TYPE_LATEST,
    track_request,
)
import sys

@app.get("/api/metrics")
def metrics():
    """Prometheus-compatible metrics endpoint."""
    # 更新缓存大小
    CHARTS_CACHE_SIZE.set(len(chart_cache._cache))
    # 更新应用信息
    APP_INFO.labels(
        version="1.0.0",
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
    ).set(1)
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
```

**Grafana 面板配置（Docker Compose 扩展）：**

**文件：`monitoring/docker-compose.monitoring.yml`**

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.51.0
    container_name: bazi-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
    networks:
      - bazi-net

  grafana:
    image: grafana/grafana:10.4.0
    container_name: bazi-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=xuanjizi2024
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    depends_on:
      - prometheus
    networks:
      - bazi-net

volumes:
  prometheus_data:
  grafana_data:

networks:
  bazi-net:
    external: true
```

**文件：`monitoring/prometheus.yml`**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

scrape_configs:
  - job_name: 'bazi-api'
    static_configs:
      - targets: ['bazi-api:8000']
        labels:
          service: 'xuanjizi-api'
    metrics_path: '/api/metrics'
    scrape_interval: 10s

  - job_name: 'bazi-mcp'
    static_configs:
      - targets: ['bazi-mcp:8001']
        labels:
          service: 'xuanjizi-mcp'
    scrape_interval: 10s
```

**文件：`monitoring/alert_rules.yml`**

```yaml
groups:
  - name: bazi-api-alerts
    rules:
      # 服务宕机告警
      - alert: ServiceDown
        expr: up{job="bazi-api"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "玄机子 API 服务不可用"
          description: "服务 {{ $labels.instance }} 已离线超过 1 分钟"

      # 高错误率告警
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(bazi_http_requests_total{status_code=~"5.."}[5m]))
            /
            sum(rate(bazi_http_requests_total[5m]))
          ) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API 错误率超过 5%"
          description: "当前 5xx 错误率: {{ $value | humanizePercentage }}"

      # 高延迟告警
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(bazi_http_request_duration_seconds_bucket[5m])) by (le)
          ) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 延迟超过 5 秒"
          description: "当前 P95 延迟: {{ $value }}s"

      # AI 调用失败率告警
      - alert: AICallFailureRate
        expr: |
          (
            sum(rate(bazi_ai_calls_total{status="error"}[10m]))
            /
            sum(rate(bazi_ai_calls_total[10m]))
          ) > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "AI 调用失败率超过 20%"
          description: "当前 AI 调用失败率: {{ $value | humanizePercentage }}"

      # 内存缓存满告警
      - alert: CacheNearlyFull
        expr: bazi_charts_cache_size > 100
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "图表缓存接近上限"
          description: "当前缓存数量: {{ $value }}"
```

#### 方案四：健康检查增强

```python
# 替换 api_server.py 中的简单 health 端点

import sqlite3
import time

@app.get("/api/health", tags=["系统"])
def health():
    """
    健康检查端点 — 检查各子系统状态。

    返回各组件的健康状态，便于负载均衡器和监控系统探测。
    """
    checks = {}
    overall_healthy = True

    # 1. 数据库检查
    try:
        conn = sqlite3.connect(data_store.DB_PATH)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"
        overall_healthy = False

    # 2. AI API 连通性检查（仅检查 Key 是否配置，不实际调用）
    from claude_api import ANTHROPIC_API_KEY
    checks["ai_api_configured"] = bool(ANTHROPIC_API_KEY)

    # 3. 内存缓存状态
    checks["cache_size"] = len(chart_cache._cache)
    checks["cache_max_size"] = CHART_CACHE_SIZE

    # 4. 进程运行时间
    checks["uptime_seconds"] = round(time.time() - _start_time, 1)

    status_code = 200 if overall_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if overall_healthy else "degraded",
            "version": "1.0.0",
            "checks": checks,
        },
    )


# 轻量级存活探针（供 K8s livenessProbe 使用）
@app.get("/api/health/live", tags=["系统"])
def health_live():
    """存活探针 — 仅返回 200 表示进程存活。"""
    return {"status": "ok"}


# 就绪探针（供 K8s readinessProbe 使用）
@app.get("/api/health/ready", tags=["系统"])
def health_ready():
    """就绪探针 — 检查服务是否准备好接收流量。"""
    try:
        conn = sqlite3.connect(data_store.DB_PATH)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not ready"})


# 在 lifespan 中记录启动时间
_start_time = time.time()
```

#### 方案五：OpenTelemetry 请求追踪

```python
# 文件：tracing.py

"""
OpenTelemetry 分布式追踪配置。

追踪请求在各模块间的完整链路：
API 入口 → 排盘引擎 → 知识库检索 → AI 调用 → 报告生成
"""

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes


def init_tracing():
    """初始化 OpenTelemetry 追踪。通过 OTEL_ENDPOINT 环境变量控制是否启用。"""
    endpoint = os.environ.get("OTEL_ENDPOINT", "")
    if not endpoint:
        return

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: "xuanjizi-api",
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


# 全局 tracer
tracer = trace.get_tracer(__name__)
```

**在关键路径中添加追踪 span：**

```python
# 在 api_server.py 中的使用示例

from tracing import tracer

@app.post("/api/chart", tags=["排盘"])
def calculate_chart(birth: BirthInfo):
    with tracer.start_as_current_span("calculate_chart") as span:
        span.set_attribute("birth.year", birth.year)
        span.set_attribute("birth.month", birth.month)
        span.set_attribute("birth.day", birth.day)
        span.set_attribute("birth.gender", birth.gender)

        chart, chart_id = chart_cache.get_or_create(birth)
        CHARTS_CREATED_TOTAL.inc()

        span.set_attribute("chart.id", chart_id)
        span.set_attribute("chart.day_master", str(chart.get("day_master", "")))
        return chart


@app.get("/api/chat/stream", tags=["分析"])
async def chat_stream(chart_id: str, message: str):
    with tracer.start_as_current_span("chat_stream") as span:
        span.set_attribute("chart_id", chart_id)
        span.set_attribute("message.length", len(message))

        # ... 原有逻辑 ...

        # 知识库检索追踪
        with tracer.start_as_current_span("kb_search") as kb_span:
            try:
                kb = _get_kb()
                kb_results = kb.fulltext_search(kb_query, 5)
                kb.close()
                kb_span.set_attribute("results.count", len(kb_results))
            except Exception as e:
                kb_span.set_attribute("error", str(e))

        # AI 调用追踪
        with tracer.start_as_current_span("ai_call") as ai_span:
            ai_span.set_attribute("provider", _detect_provider(ANTHROPIC_API_KEY))
            for event in _stream_claude(enriched, enriched_msg):
                # ... 处理事件 ...
                pass
```

**依赖：**

```
opentelemetry-api>=1.25.0
opentelemetry-sdk>=1.25.0
opentelemetry-exporter-otlp>=1.25.0
prometheus-client>=0.21.0
```

### 5.3.3 实施步骤

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| 第 1 周 | 创建 `logging_config.py`，替换各模块的 logging 配置为 structlog | 1 天 |
| 第 1 周 | 创建 `metrics.py`，用 prometheus_client 替换手动计数器 | 1 天 |
| 第 2 周 | 增强 health 端点，