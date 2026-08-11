# Phase 8 婚姻类能力改进前提分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **修订历史：** v1 → v2（依赖链重排、C1 拆 6A/6B、基础设施早建）→ v3（required_knowledge 结构化 schema、classic/prompt 审计可复算化、C1 单版本单次回放、命令全显式双 shell）→ v3.1（复审修订：top_n 去重与六入口允许键 fail-closed、C1 evaluator 移入 6A 双 SHA 冻结、Task 2.5 完整命令、prompt fingerprint 全值、classic_texts 检索语义冻结、quarantine 命中标记、Task 5/6B manifest 步骤显式化）→ v3.2（NEEDS_FIX 修订：classic_texts 字段对齐真实 schema（rule/original_text 主检索 + subject/condition/category 辅助 + 启动 fail-closed）、6A fixture 含三目标 case 合成记录、6B eval 已存在拒绝覆盖 + replay_count=1）

**Goal:** 按设计 v1.3.1 完成 Phase 8 零 API 前提分析：35 题亚型拆分 → 需求拆解 → 查询计划与输入冻结 → 计算探针 → 逐知识项多标签缺口归类 → C1 回放筛选 → 密封双集规约，产出 `docs/phase8/marriage-capability/` 全套可复算产物。

**Architecture:** 全部为只读分析 + 独立分析脚本（落盘于产物目录），不修改任何生产代码。测试集中放 `tests/test_phase8_marriage_capability.py`。

**设计依据：** `docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md`（v1.3.1，commit `90c536b`）。

**命令约定（v3 P0-4 冻结）**：所有命令为**单行、正斜杠路径、PowerShell 与 Git Bash 双兼容**——禁止 `\` 续行、`tail`、`Out-File`。每个 COMMIT 步骤逐文件写全 pathspec，无占位符。

**设计冻结事实（执行者必须逐条遵守）：**

- 输入：Phase 7 r2 归档 `docs/phase7/phase7-mingli-v4flash-nt-20260811-r2/` + `docs/phase7/error-analysis/error_classification.jsonl`（35 道 `category=婚姻 且 error_type=knowledge` 错题）。
- **任务链**：P8-1 亚型 → P8-2A 需求拆解（先冻结）→ 查询计划与 allowlist 生成（只生成不执行）→ KB 快照 + 查询集 + classic_texts 冻结 → 原库/快照等价性通过 → P8-1.5 探针 → P8-2B 正式审计 → C1（6A 单版本开发冻结 / 6B 单次回放）→ P8-4/P8-5 规约。阶段间 case_id / item_id / 输入 SHA 三方对账。
- 亚型五类 + 主优先级 `多段婚姻 > 事件反查 > 配偶特征 > 结婚离婚应期 > 婚姻状态` + `secondary_subtypes`。
- **required_knowledge 结构化 schema（v3 P0-1 冻结）**——每知识项：
  ```text
  item_id          # {case_id}#k{n}
  item_type        # computation | doctrine
  computation_type # item_type=computation 时：dayun | liunian | sihua | other（值域冻结）
  target_years     # 题目所问年份/范围（计算项必填，doctrine 项为 null）
  required_inputs  # 所需输入字段清单（如 year_pillar/month_pillar/gender/target_year）
  query_specs[]    # item_type=doctrine 时必填，每条：
    query_id       # {item_id}#q{n}
    entrypoint     # KB_ALLOWED_QUERIES 白名单内函数名
    args           # 仅入口业务参数，禁止包含 top_n（防重复定义）
    top_n          # 支持 top_n 的入口为 int；不支持的入口为 null
    synonym_source # 同义词来源说明（冻结词表或"无"）
  ```
  **六入口允许键逐一冻结（v3.1；未知键/缺键/args 内含 top_n 均 fail-closed）**：
  ```text
  search_gejue:         args={query, category}      top_n=int
  search_shishen_combo: args={combo_name}           top_n=int
  search_shensha:       args={name}                 top_n=null
  search_nayin:         args={gan, zhi}             top_n=null
  search_bingyao:       args={query}                top_n=int
  search_xiangyi:       args={gan_or_zhi}           top_n=int
  ```
  `kb_query_set.json` 保存的是**入口名 + 类型化参数**，不是裸查询词字符串。
- 探针：`computability_status` 四态；只保留稳定字段，**排除全部 `current_*`**（`bazi_calculator.py:896-912` 的 `date.today()` 依赖已核实）；双跑字节一致门。
- 缺口 schema：`gap_class` 五类 + `undetermined`；`no_interface→计算缺失`、`missing_input→undetermined(reason=input_missing)`、`semantic_gap→undetermined`；`primary_gap` 仅从确定类派生，优先级 `计算缺失 > 注入缺失 > 检索不可见 > 知识缺失 > 模型未利用`。
- **KB 查询入口白名单与依赖表映射（v2 冻结）**：
  ```text
  KB_ALLOWED_QUERIES = {
    search_gejue:        [gejue, gejue_fts(+shadow)],   # FTS5 MATCH（bazi_kb.py:253-263）
    search_shishen_combo: [shishen_combos],
    search_shensha:      [shensha],
    search_nayin:        [nayin],
    search_bingyao:      [bingyao],
    search_xiangyi:      [xiangyi],
  }
  ```
  审计只允许白名单入口；快照覆盖映射全部表；`ziwei_patterns` 无公开入口不进快照不进审计。
- **等价性口径（v3 中优 1/2）**：除命中 ID/顺序/行数外，逐条比较返回记录的 **canonical 内容**（防同 ID 内容漂移）；`search_gejue` 存在 FTS 异常静默退回 LIKE 的路径，等价性测试必须**直接执行 FTS `MATCH` 并证明未走 fallback**（对 gejue_fts 直接 MATCH 的结果与入口返回比对一致）。
- KB 零命中只记 `not_found_by_frozen_search`；标"知识缺失"需附快照检索 + classic_texts 冻结版核查双记录；"模型未利用"须引 prompt 现存字段证据。
- **classic_texts / prompt 审计可复算（v3 P0-2 冻结）**：
  - `classic_texts_search.py` + `classic_texts_search_results.json`：匹配字段、规范化规则（去空白/繁简不转换/大小写）、同义词表、文件 blob SHA、命中定位（**JSON pointer + 逐字摘录**）全部落盘；
  - prompt 审计：从 Phase 7 固定 commit + profile + normalized case **重建 prompt**（调用 `format_official_cot_prompt`），重建所用 `prompt_fingerprint()` 必须等于 Phase 7 receipt 的 `prompt_fingerprint` 完整值 `e136106a8e8730020eb3631b32b6c24424beaf73f5f0fcbc82a274e2120cb22d`（不一致即停）；`prompt_evidence` 记字段路径 + 逐字摘录。
- C1：**6A 只允许一个 detector 版本**（合成 fixture 开发，SHA 冻结）；**6B 单次回放后立即形成 `C1_PASS` 或 `C1_TERMINATED`**；`C1_TERMINATED` 后**本计划内禁止创建新版本**；新 detector 必须另立设计/计划，旧结果保留不得覆盖。逐题 `old_letter/new_letter/expected/change_result` 四态；未触发 `new_letter=null`；触发且候选==old → `new_letter=old_letter` + unchanged。
- 引擎接口（已核实）：`calculate_dayun(year_pillar, month_pillar, gender, birth_year, birth_month, birth_day, birth_hour=0, birth_minute=0)`（pillar 为 (gan,zhi) 元组，gender 'male'/'female'；**年/月柱从 `official_astro.chinese_date` 解析**，解析规则落盘）；`calculate_liunian(current_year, day_master_gan, num_years=3)`，历史目标年 Y 用 `current_year=Y, num_years=1`。
- 目录区分：KB 在 `knowledge-base/`（连字符），classic_texts 在 `knowledge_base/`（下划线）。
- SHA 四策略：JSON canonical（`sort_keys=True, ensure_ascii=False, separators=(",", ":")` + 末尾 `\n`）/ JSONL 逐行 canonical+冻结行序 / 二进制 raw-byte / 普通 Git 文本 git-canonical-lf。

---

## 实施边界与基线

只新建：`docs/phase8/marriage-capability/` 全部产物 + `tests/test_phase8_marriage_capability.py` + `tests/fixtures/phase8/c1_synth.jsonl`。
不修改：`benchmark/`、`bazi_calculator.py`、`knowledge-base/`、`knowledge_base/`、`scripts/` 全部既有文件、`docs/phase7/`。全程零 LLM API。

**工作区警告**：蒸馏线并行变更仍在 churn。**所有 commit 用显式 pathspec；绝不 `git commit -a` 或裸 commit**。

### TDD 约定

- 代码类任务 RED-GREEN-COMMIT；分析产物类任务校验脚本先行。
- `phase8_freeze_manifest.json` 与 `p8_reconcile.py` 在 Task 1 创建并提交，后续任务增量扩展。**freeze manifest 原子更新必须用公共 helper**（`p8_freeze.py` 的 `atomic_add(sha_entries)`：写 tmp → 校验 JSON 可解析 → os.replace），并配**故障测试**（模拟写中断后 manifest 仍可解析、无半写状态）。
- pre-commit stash 冲突可原样重试一次，禁止 `--no-verify`。

---

## Task 0: 基线验证与工作区检查

- [ ] 0.1 `git log --oneline -1` 显示 `90c536b`；`git status --short docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md` 无输出。
- [ ] 0.2 工作区全口径基线 → `.tmp/phase8-workspace-baseline.txt`（porcelain + 非 Phase 8 文件 SHA）。
- [ ] 0.3 同口径基线（单行命令）：
  - `.venv/Scripts/python.exe -m pytest -m "not e2e" -q --deselect tests/test_api.py::TestCaseSearch --deselect tests/test_mcp.py::TestBaziCaseSearch`（结果尾部记入 `.tmp/phase8-baseline.txt`）
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m mypy`
- [ ] 0.4 输入 SHA 预记录（四策略）→ `.tmp/phase8-baseline.txt`。

---

## Task 1: P8-1 亚型拆分 + 基础设施早建

- [ ] 1.1 RED：校验测试（35 题集合、五类枚举、优先级、计数和=35）。初跑 FAIL。
- [ ] 1.2 GREEN：`p8_subtype_split.py` → `subtype_split.json`（"感情细节"/"其他"逐题归并，`merge_reason` 落盘）。
- [ ] 1.3 创建 `p8_reconcile.py`（首项：亚型 35 题对账）、`p8_freeze.py`（原子更新 helper + 故障测试）、`phase8_freeze_manifest.json`（首条目：subtype_split SHA）。
- [ ] 1.4 COMMIT：
  ```powershell
  git add -- docs/phase8/marriage-capability/p8_subtype_split.py docs/phase8/marriage-capability/subtype_split.json docs/phase8/marriage-capability/p8_reconcile.py docs/phase8/marriage-capability/p8_freeze.py docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  git diff --cached --name-only
  git commit -m "feat(phase8): subtype split + reconcile/freeze infrastructure" -- docs/phase8/marriage-capability/p8_subtype_split.py docs/phase8/marriage-capability/subtype_split.json docs/phase8/marriage-capability/p8_reconcile.py docs/phase8/marriage-capability/p8_freeze.py docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  ```
  `git diff --cached --name-only` 输出必须恰好为上述 6 个文件。

---

## Task 2: P8-2A 需求拆解（结构化 schema，校验先行）

- [ ] 2.1 校验先行：schema 测试——35 行；`item_id` 稳定；`item_type/computation_type/target_years/required_inputs/query_specs` 按 v3.1 schema 齐全；doctrine 项 `query_specs` 非空且 `entrypoint` ∈ 白名单；**`args` 键恰对应该入口冻结允许键、`args` 内不得含 `top_n`、未知键/缺键均 fail-closed**；`top_n` 按入口为 int 或 null；computation 项 `target_years` 非 null。初跑 FAIL。
- [ ] 2.2 内容产出（控制者 + 子代理）：读 question/options/expected_answer（**禁止读 raw_answer**），按结构化 schema 写每题知识项。
- [ ] 2.3 复核：独立子代理复核；分歧与裁决写入 `required_knowledge_review.md`。
- [ ] 2.4 冻结：canonical JSONL；`p8_freeze.py` 原子写入 manifest。
- [ ] 2.5 COMMIT（完整命令，逐文件显式）：
  ```powershell
  git add -- docs/phase8/marriage-capability/required_knowledge.jsonl docs/phase8/marriage-capability/required_knowledge_review.md docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  git diff --cached --name-only
  git commit -m "feat(phase8): structured required_knowledge (P8-2A) with review adjudication" -- docs/phase8/marriage-capability/required_knowledge.jsonl docs/phase8/marriage-capability/required_knowledge_review.md docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  ```
  `git diff --cached --name-only` 输出必须恰好为上述 4 个文件。

---

## Task 3: 查询计划 + 输入冻结 + 等价性

- [ ] 3.1 查询计划（只生成不执行）：从 doctrine 项 `query_specs` 汇总 → `kb_query_set.json`（入口名 + 类型化参数 + 来源 item_id/query_id）。
- [ ] 3.2 classic_texts allowlist：冻结四书 `all_rules.json` + `quarantine_rules.jsonl`（以冻结 commit 实际存在为准），逐文件 blob SHA + 可达 commit → `classic_texts_freeze.json`。
- [ ] 3.3 RED：等价性测试——`kb_query_set.json` 全部查询 + 每白名单入口固定探针查询：命中 ID/顺序/行数/**返回记录 canonical 内容**一致；gejue 直接 FTS `MATCH` 比对证明无 LIKE fallback；FTS shadow tables/schema/行数核对。初跑 FAIL（快照不存在）。
- [ ] 3.4 GREEN：`p8_kb_snapshot.py` 全表全字段导出 → `kb_snapshot.db`；等价性结果落盘 `kb_equivalence.json`。
- [ ] 3.5 manifest 原子更新（kb_query_set/classic_texts_freeze/kb_snapshot.db raw-byte SHA/kb_equivalence）。
- [ ] 3.6 COMMIT：
  ```powershell
  git add -- docs/phase8/marriage-capability/p8_kb_snapshot.py docs/phase8/marriage-capability/kb_snapshot.db docs/phase8/marriage-capability/kb_query_set.json docs/phase8/marriage-capability/classic_texts_freeze.json docs/phase8/marriage-capability/kb_equivalence.json docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  git diff --cached --name-only
  git commit -m "feat(phase8): KB sqlite snapshot + query set + classic_texts freeze + equivalence" -- docs/phase8/marriage-capability/p8_kb_snapshot.py docs/phase8/marriage-capability/kb_snapshot.db docs/phase8/marriage-capability/kb_query_set.json docs/phase8/marriage-capability/classic_texts_freeze.json docs/phase8/marriage-capability/kb_equivalence.json docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  ```

---

## Task 4: P8-1.5 计算能力探针

- [ ] 4.1 RED：测试——computation 项四态齐全；输出无 `current_*`（递归扫描）；双跑字节一致；**缺失三态**（gender 缺失/非男女 → `missing_input`；chinese_date 解析失败 → `missing_input`+原因；无接口 → `no_interface`）。初跑 FAIL。
- [ ] 4.2 GREEN：`p8_probe.py`（chinese_date→年/月柱解析规则落盘；gender 映射；历史年 `current_year=Y, num_years=1`；稳定字段白名单）→ `computability_probe.json`。
- [ ] 4.3 对账：`p8_reconcile.py` 增量（探针 item_id 集 == computation 项集）。
- [ ] 4.4 COMMIT：
  ```powershell
  git add -- docs/phase8/marriage-capability/p8_probe.py docs/phase8/marriage-capability/computability_probe.json docs/phase8/marriage-capability/p8_reconcile.py docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  git diff --cached --name-only
  git commit -m "feat(phase8): computability probe with stable-field output and byte-consistency gate" -- docs/phase8/marriage-capability/p8_probe.py docs/phase8/marriage-capability/computability_probe.json docs/phase8/marriage-capability/p8_reconcile.py docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  ```

---

## Task 5: P8-2B 四源核对与缺口归类

**前置硬门：Task 3 等价性已绿；审计查询只打快照。**

- [ ] 5.1 classic_texts 检索实现：`classic_texts_search.py`——**匹配语义冻结（v3.1）**：搜索字段 = **主要正文 `rule`、`original_text`；辅助检索 `subject`、`condition`、`category`**；**不检索 `id`、`source_book`、`source_chapter`、`quarantine_reason`**（真实 schema 已核实：四书 `all_rules.json` 均为 `id/category/subject/condition/rule/original_text/source_book/source_chapter`）；每条结果记录 `matched_fields`；**启动时文件 schema ≠ 允许 schema 即 fail-closed，禁止静默跳过未知字段**；测试用四书各至少一条真实结构 fixture 验证。同义词组内 **OR**、不同词组间 **AND**；**子串匹配**（去空白后）；结果排序 = 文件序 + 行序（稳定序），去重 = 同一 `(file, line)` 只记一次；quarantine 文件命中必须标 `quarantined=true`——**不得单独作为"经典文本已有可靠知识"的证据**（只作佐证，知识缺失判定以非 quarantine 文件为准）。读取 git object 冻结版 → `classic_texts_search_results.json`（命中定位 = JSON pointer + 逐字摘录）。
- [ ] 5.2 prompt 重建审计：从 Phase 7 固定 commit + profile + normalized case 重建 prompt；**先校验 `prompt_fingerprint()` == Phase 7 receipt 完整值 `e136106a8e8730020eb3631b32b6c24424beaf73f5f0fcbc82a274e2120cb22d`**（不一致即停）；`prompt_evidence` = 字段路径 + 逐字摘录。
- [ ] 5.3 RED：归类校验测试（gap_class 枚举、探针映射一致、primary_gap 优先级、双口径分母对账）。初跑 FAIL。
- [ ] 5.4 GREEN：`p8_audit.py` + 人工裁决 → `knowledge_audit.jsonl` + `knowledge_audit_summary.md`（题级多标签 + 知识项级 + undetermined 单列 + 层级指向）。
- [ ] 5.5 manifest 原子更新（用 `p8_freeze.py` helper 写入本任务全部新产物 SHA：classic_texts_search.py、classic_texts_search_results.json、p8_audit.py、knowledge_audit.jsonl、knowledge_audit_summary.md）。
- [ ] 5.6 COMMIT：
  ```powershell
  git add -- docs/phase8/marriage-capability/classic_texts_search.py docs/phase8/marriage-capability/classic_texts_search_results.json docs/phase8/marriage-capability/p8_audit.py docs/phase8/marriage-capability/knowledge_audit.jsonl docs/phase8/marriage-capability/knowledge_audit_summary.md docs/phase8/marriage-capability/p8_reconcile.py docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  git diff --cached --name-only
  git commit -m "feat(phase8): four-source audit with multi-label gap classification (P8-2B)" -- docs/phase8/marriage-capability/classic_texts_search.py docs/phase8/marriage-capability/classic_texts_search_results.json docs/phase8/marriage-capability/p8_audit.py docs/phase8/marriage-capability/knowledge_audit.jsonl docs/phase8/marriage-capability/knowledge_audit_summary.md docs/phase8/marriage-capability/p8_reconcile.py docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  ```

---

## Task 6: C1 转换器（6A 单版本开发冻结 / 6B 单次回放）

### 6A 开发（detector + evaluator 都只用合成 fixture，各只允许一个版本）

- [ ] 6A.1 合成 fixture：`tests/fixtures/phase8/c1_synth.jsonl`（自造冲突正例/一致负例/边界例，不含真实输出内容）。**必须包含三个目标 case ID（mingli_ftb_0018/0034/0073）的合成记录**——PASS/TERMINATED 终态裁决的测试只依赖这些合成记录，不读真实输出。
- [ ] 6A.2 RED-GREEN：`c1_detector.py`（检测/候选提取/重选）对 fixture 全绿。
- [ ] 6A.3 **evaluator 同步开发冻结（v3.1 P0-2）**：`c1_replay.py` 的纯评估逻辑（逐题 `old/new/expected/change_result` 计算、四态分母对账、0018/0034/0073 判定、PASS/TERMINATED 终态裁决）在 6A 内用合成 fixture 测试全绿——**不得等到接触真实数据才写**。
- [ ] 6A.4 **双冻结**：`c1_detector.py` 与 `c1_replay.py` 两个 SHA 都写入 manifest 并 commit；此后本计划内两文件均不得再改。
- [ ] 6A.5 COMMIT：
  ```powershell
  git add -- docs/phase8/marriage-capability/c1_detector.py docs/phase8/marriage-capability/c1_replay.py tests/fixtures/phase8/c1_synth.jsonl docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  git diff --cached --name-only
  git commit -m "feat(phase8): C1 detector + replay evaluator on synthetic fixtures (single version, dual-frozen)" -- docs/phase8/marriage-capability/c1_detector.py docs/phase8/marriage-capability/c1_replay.py tests/fixtures/phase8/c1_synth.jsonl docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  ```

### 6B 回放（只执行已冻结 evaluator，单次，双终态）

- [ ] 6B.1 运行前校验：`c1_detector.py` 与 `c1_replay.py` 当前 SHA == manifest 双冻结值（**任一漂移即拒绝运行**）；**`c1_detector_eval.json` 已存在即拒绝覆盖**（单次回放的机械门），产出必须记录 `replay_count=1`；通过后对 r2 merged_details **单次运行**已冻结 evaluator。
- [ ] 6B.2 逐题输出四态 `change_result`；未触发 `new_letter=null`；触发且候选==old → unchanged；对账四态和 == 160。
- [ ] 6B.3 终态判定并写入 `c1_detector_eval.json` 的 `verdict`：0018/0034/0073 全 improved 且 harmed=0 → `C1_PASS`；否则 `C1_TERMINATED`。**`C1_TERMINATED` 后本计划内禁止创建 detector/evaluator 新版本**；新 detector 另立设计/计划，旧结果保留不覆盖。
- [ ] 6B.4 manifest 原子更新（写入 `c1_detector_eval.json` SHA）。
- [ ] 6B.5 COMMIT：
  ```powershell
  git add -- docs/phase8/marriage-capability/c1_detector_eval.json docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  git diff --cached --name-only
  git commit -m "feat(phase8): C1 single-shot replay on 160 historical outputs" -- docs/phase8/marriage-capability/c1_detector_eval.json docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  ```

---

## Task 7: P8-4/P8-5 规约文档

- [ ] 7.1 写 `sealed_marriageset_spec.md`（双集规约 + 配对框架 + 指纹组成，对照设计 §P8-4/P8-5 与 v1.3.1 增补逐条覆盖）。
- [ ] 7.2 文末附冻结点自检清单。
- [ ] 7.3 manifest 原子更新（写入 `sealed_marriageset_spec.md` 的 git-canonical-lf SHA）。
- [ ] 7.4 COMMIT：
  ```powershell
  git add -- docs/phase8/marriage-capability/sealed_marriageset_spec.md docs/phase8/marriage-capability/phase8_freeze_manifest.json
  git diff --cached --name-only
  git commit -m "docs(phase8): sealed marriage set + non-marriage guardrail set spec" -- docs/phase8/marriage-capability/sealed_marriageset_spec.md docs/phase8/marriage-capability/phase8_freeze_manifest.json
  ```

---

## Task 8: provenance、总对账与收尾

- [ ] 8.1 从 manifest 生成 `provenance.json`（全量 SHA + 四策略分列 + 对账入口）。
- [ ] 8.2 `p8_reconcile.py` 全量对账（35 题链、item_id 链、C1 160 行、KB 等价性、探针双跑、manifest 与磁盘产物 SHA 一致）。
- [ ] 8.3 全量回归（逐命令单行执行，与 Task 0.3 同口径，对照 `.tmp/phase8-baseline.txt` 不得新增失败）：
  - `.venv/Scripts/python.exe -m pytest -m "not e2e" -q --deselect tests/test_api.py::TestCaseSearch --deselect tests/test_mcp.py::TestBaziCaseSearch`
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m mypy`
- [ ] 8.4 工作区审计（porcelain+SHA 对照 Task 0.2；逐 commit 核对 pathspec）。
- [ ] 8.5 最终 COMMIT（文件清单以 8.1/8.2 实际产出为准，逐文件显式列出，不得用占位符）：
  ```powershell
  git add -- docs/phase8/marriage-capability/provenance.json docs/phase8/marriage-capability/p8_reconcile.py docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  git diff --cached --name-only
  git commit -m "chore(phase8): provenance + final reconciliation" -- docs/phase8/marriage-capability/provenance.json docs/phase8/marriage-capability/p8_reconcile.py docs/phase8/marriage-capability/phase8_freeze_manifest.json tests/test_phase8_marriage_capability.py
  ```

---

## 完成定义（对齐设计 §8）

1. 设计 v1.3.1 已过审（`90c536b`）。
2. Task 1–8 全部完成，阶段间对账通过；C1 终态为 `C1_PASS` 或 `C1_TERMINATED` 之一，结论闭合。
3. 全程零 API、零生产代码改动；产物满足 SHA 四策略与可复算纪律。
