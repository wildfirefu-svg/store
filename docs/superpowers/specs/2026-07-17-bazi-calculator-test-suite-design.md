# bazi_calculator 专属单元测试套件 — 设计文档

> 日期： 2026-07-17 | 状态： 终审放行 + 第五轮审核同步（缺陷 5 例：#1-#4 实测确认 + #5 实施中快照发现；验收命令已固定为可复现形式） | 类型： 测试基建

## 1. 背景与目标

`bazi_calculator.py`（2,351 行）是系统最重的模块、所有交付面的唯一排盘入口，但长期没有专属单元测试。本设计为其建立专属测试套件，目标：

1. **防回归**：对全部公开函数与 `compute_chart` 端到端输出建立回归防线，后续改引擎（如 Phase 6 改排盘上下文）有安全网。
2. **救活存量金标**：现有 100 例金标精度测试（`tests/test_accuracy.py` + `tests/test_charts.json`）因入口函数命名不匹配 pytest 收集规则，从未进入 pytest/CI，改造后被每次 CI 强制执行。
3. **高危边界显式断言**：节气切换、立春、早/夜子时、大运顺逆排等边界逻辑用手工断言锁定语义。
4. **暴露并修复现存缺陷**：以教科书权威规则为断言来源，实测确认四例生产逻辑缺陷（§4.3 三合系取组、§4.3 日柱系位置、§4.5 compare_charts 键名、§4.5 十二长生表），实施中快照机制另发现一例输出不确定性缺陷（§2 缺陷 #5，SANHE 集合迭代序），共五例按 §8 流程最小修复。

## 2. 现状盘点（2026-07-17 实测）

| 已有覆盖 | 状态 |
|---|---|
| `tests/test_accuracy.py`：100 例金标校验四柱 + 大运方向（`test_charts.json`，当前 `run_tests()` 100/100 通过，约 0.04s） | **pytest 不收集**（入口为 `run_tests`，不匹配 `test_*`；`pytest tests/test_accuracy.py -q` 收集 0 项），CI 不执行 |
| `tests/test_bazi_calculator_location_matching.py`：3 例真太阳时地点匹配 | 正常收集 |
| `tests/test_tools.py` / `test_mcp.py` | 间接经过 calculator，无行为断言 |

**零直接覆盖的模块面**：神煞（30+ 种）、紫微、五运六气、五行/十神统计、流年、刑冲合害、空亡、胎元/命宫/身宫、十二长生、`compare_charts`、`format_to_spec`、`compute_chart` 端到端，以及节气/立春/子时边界。

**已实测确认的现存缺陷**（测试将暴露并按 §8 修复，证据均为本机实测）：

1. **三合系神煞取组错误**（`bazi_calculator.py:944`）：以"被检查地支自身"定三合局而非年支/日支所属局。实测 `申年+酉月` 构造盘 `桃花` 全盘不命中（教科书"申子辰在酉"应命中）。缺陷是双向的：桃花/驿马/劫煞/灾煞/亡神/紫微/三合禄 的目标支不在本组 → 永不命中；华盖/将星的目标支恰为本组成员 → 凡含该支的盘必命中（过度触发）。日干系（天乙贵人/文昌/羊刃）实测正常。
2. **日柱系神煞被错误应用到四柱**（`:996-1003`）：魁罡/孤鸾煞/阴差阳错/十恶大败/八专/悬针/天赦 7 类判断位于四柱循环内且无 `key == 'day'` 限制。实测 `庚辰年/戊寅月/甲子日/甲子时` 构造盘：年柱误中魁罡+十恶大败，月柱误中阴差阳错+天赦，时柱误中悬针+天赦。7 张表定义的源码注释全部标注"日柱为"，缺位置守卫是明确 bug。
3. **`compare_charts` 五行键名不匹配**（`:2174-2183`）：按中文 `金/木/水/火/土` 读 `wuxing_stats`，而 `calculate_wuxing_stats:1320-1326` 产出 `jin/mu/shui/huo/tu`，五行占比恒为 0.0（实测）。
4. **十二长生表数据与教科书/自身注释矛盾**（`:616-627`）：教科书（五行长生，阳顺阴逆）"甲长生在亥/乙午/丙寅/戊寅/庚巳/辛子/壬申/癸卯/丁酉/己酉"，实测 `get_changsheng('甲','亥') == '养'`；`CHANGSHENG_TABLE` 各行数据与其行尾注释矛盾（注释"甲: 亥...戌"，数据首元素为戌=10 而非亥=11），10 干全不符。**决策（书面化）**：用户于 2026-07-17 在 Kimi Code 会话中经结构化问答（AskUserQuestion）明确选择"路径 A：修复为教科书表"，按缺陷 #4 独立提交修复（改变 `changsheng` 与 `day_master.shier_changsheng` 生产输出）；执行修复任务前向用户复述该决策并再次确认。
5. **`detect_branch_relations` 输出顺序不确定**（`:665`）：`SANHE` 为 set，迭代顺序随进程 `PYTHONHASHSEED` 随机化，`branch_relations` 列表顺序跨进程翻转——实施中快照机制发现（同一用例 seed 0/42 与 seed 3/5/7/99 输出互翻，快照首跑 1 红）。修复为 `for group in sorted(SANHE):`（1 行，独立提交）；属可观察行为变化（`branch_relations` 列表顺序从此确定）。**第五轮审核（2026-07-18）正式纳入变更条款。**

## 3. 策略与范围

**混合策略**（已与用户确认）：

- **手工规则断言** — 用于语义明确、有教科书规则或天文算法可独立验证的逻辑：四柱、大运、边界条件、十神、空亡、刑冲合害、统计不变量、神煞规则、十二长生。
- **金标快照（characterization）** — 用于输出体量大、逐条断言不现实的部分：神煞全集、紫微盘、`compute_chart` 全量输出。快照 = 冻结现状防回归，不单独证明正确性；其可信度由手工断言层与存量金标共同托底。
- **内部一致性断言** — 对语义需读代码才能确定的部分，断言不变量而非硬编码值（例：五行计数总和 = 8，缺失集 = 计数为 0 的元素集）。

**范围**：全量覆盖——附录 A 覆盖矩阵内所有公开函数至少被直接断言一次。

## 4. 文件布局与测试清单

新增 6 个测试文件（命名沿用 `test_bazi_calculator_*.py` 既有前缀惯例）+ 改造 1 个 + fixtures 目录。

### 4.1 `tests/test_bazi_calculator_pillars.py` — 四柱与边界（手工断言）

| 测试点 | 断言来源 |
|---|---|
| 代表性已知案例的四柱（年/月/日/时柱干支）、日主 | 从 `tests/test_charts.json` 金标选取 ≥8 例（覆盖不同年份/性别/早晚子时）参数化 |
| 立春/节气边界：时刻前 1 分钟 vs 后 1 分钟，年柱/月柱切换 | 冻结数据 fixture（见下方说明），禁止用 `get_solar_term_info` 自证 |
| 早子时（0:00–1:00）与晚子时（23:00–24:00）的日柱/时柱行为 | 锁定引擎当前语义并注释说明 |
| 五虎遁：甲/己年正月月干为丙（丙寅起） | 口诀规则直接断言 |
| 五鼠遁：甲/己日子时时干为甲（甲子起） | 同上 |
| `get_shishen`：十神判定抽查（甲日主见甲=比肩、见乙=劫财、见丙=食神…全 10 种） | 十神规则 |
| `get_kongwang`：甲子旬中戌亥空 | 旬空规则 |
| 纳音、藏干字段存在且非空（结构断言） | schema |
| `get_year_pillar` / `get_month_pillar` / `get_day_pillar` / `get_hour_pillar` 直接调用断言 | 上述规则用例同时覆盖 |
| `get_month_branch_idx` / `get_next_jie_info` 边界前后返回值 | 边界 fixture |
| `get_solar_term_info` 行为：verified 条目分钟级比较、非 verified 条目日期级 | 读码确认的行为（`:187-193`） |

**边界测试的冻结 fixture（防循环验证）**：`get_solar_term_info` 仅对 `solar_terms.json` 中 `verified=True` 的条目做分钟级比较（`bazi_calculator.py:187-193`），其余按日期切换。因此边界时刻**不得**从 `get_solar_term_info` 取得再反证自身，而是：从 `knowledge-base/solar_terms.json` 选取 `verified=True` 且带时分字段的条目，作为**独立于比较算法的冻结数据 fixture**；测试前置断言该 fixture 条目确实 `verified=True` 且具有分钟精度；记录所用条目、来源与时区（UTC+8）；再断言其前后各 1 分钟的柱切换。注：该 fixture 证明的是"比较算法是否按仓库数据表切换"，天文时刻本身的正确性不由本轮测试证明。

### 4.2 `tests/test_bazi_calculator_dayun.py` — 大运与流年（手工断言）

- 四种方向组合全覆盖：阳年男 → 顺排；阳年女 → 逆排；阴年男 → 逆排；**阴年女 → 顺排**（`direction` 字段）
- 起运岁数 ∈ [0, 10] 且为非负数
- 顺排时第 1 步大运 = 月柱沿六十甲子后移一位，逆排 = 前移一位；**连续 10 步递进正确、大运柱数为 10**（递进断言直接调用 `sexagenary_index` / `sexagenary_by_index`，同时覆盖这两个函数）
- `calculate_liunian`：返回 N 年、年份连续、干支沿六十甲子递进、流年十神与日干关系正确（抽查）

### 4.3 `tests/test_bazi_calculator_shensha.py` — 神煞（断言 + 快照）

**A. 日干系（读码+实测确认实现正确，直接断言）**：天乙贵人（甲戊庚日主见丑/未）、文昌（甲日主见巳）、羊刃（甲日主见卯）。

**B. 三合系（9 类）——已实测确认现存缺陷 #1，按 §8 最小修复路径处理**：

缺陷：`calculate_shensha` 以被检查地支自身定三合局（`:944`），共享的 `group` 同时驱动 **9 类**神煞（`:962-970`），修复会改变全部 9 类生产输出，因此先把 9 类口径逐类冻结再动手。

**9 类口径冻结表**（以"申子辰局"为例的目标支；修复后的判定基准）：

| 神煞 | 参考支口径 | 申子辰局目标支 | 依据 |
|---|---|---|---|
| 桃花 | 年支或日支（并集） | 酉 | 通行规则"申子辰在酉"以年/日支查 |
| 驿马 | 年支或日支（并集） | 寅 | 同上 |
| 华盖 | 年支或日支（并集） | 辰 | 同上 |
| 将星 | 年支或日支（并集） | 子 | 源码注释"三合局查"；公开资料与四柱讲义普遍支持"以年支或日支查其余支" |
| 劫煞 | 年支或日支（并集） | 巳 | 通行规则 |
| 灾煞 | 年支或日支（并集） | 午 | 通行规则 |
| 亡神 | 年支或日支（并集） | 亥 | 通行规则 |
| 紫微 | **仅日支** | 酉 | 源码注释"日支三合查"（`:358`）；**暂定工程口径，未获外部权威验证，待命理复核** |
| 三合禄 | 年支或日支（并集） | 亥 | 源码注释"三合临官位"；外部依据弱，**暂定工程口径，待命理复核** |

**合并与去重规则**：参考局集合 = {年支所属局} ∪ {日支所属局}（紫微仅 {日支所属局}）；候选支命中任一参考局的目标支即触发；同一柱同一神煞仅输出一次（年支与日支同时触发不重复）。

**测试矩阵**：
- 参数化正例：4 组三合局（申子辰/寅午戌/巳酉丑/亥卯未）× 9 类型，以年支为参考 + 以日支为参考各一轮（紫微只测日支路径）
- 反例：每类型 ≥1 例——目标支在盘、但年/日支均不属对应局 → 不命中；紫微额外测"年支属局但日支不属局 → 不命中"
- 年日异组合并：年支属 A 局、日支属 B 局，两局目标支均命中
- 去重：年支与日支同局时，同柱同一神煞只出现一次

**修复范围纪律**：仅重写三合系判定块（`:944` 的取组及 `:962-970` 的判定——紫微需用不同参考集，不是改 `:944` 一行能解决），**不触碰**月德等正确使用参考支分组的逻辑（如 `:981` 的 `month_zhi` 取组是对的）及其他神煞逻辑。

**C. 日柱系（7 类）——已实测确认现存缺陷 #2，按 §8 最小修复路径处理**：

缺陷：7 类判断位于四柱循环内且无位置限制（`:996-1003`），任何柱的干支命中表即误报。实测证据：`庚辰年/戊寅月/甲子日/甲子时` 构造盘，年柱误中魁罡+十恶大败、月柱误中阴差阳错+天赦、时柱误中悬针+天赦。

**7 类口径冻结表**（依据：表定义源码注释全部标注"日柱为"，与教科书规则一致）：

| 神煞 | 现行表内容 | 口径 | 依据 |
|---|---|---|---|
| 魁罡 | 庚辰/庚戌/壬辰/戊戌 | **仅日柱** | 注释"exact stem-branch combos"，魁罡日通行规则 |
| 孤鸾煞 | 甲寅/乙卯/丙午/丁巳/戊午/己巳/庚申/辛酉/壬子/癸亥 | **仅日柱** | 注释"日柱为" |
| 阴差阳错 | 丙子/丁丑/戊寅/辛卯/壬辰/癸巳/丙午/丁未/戊申/辛酉/壬戌/癸亥 | **仅日柱** | 注释"日柱为" |
| 十恶大败 | 甲辰/乙巳/壬申/丙申/丁亥/庚辰/戊戌/辛巳/己丑/癸亥 | **仅日柱** | 注释"日柱为" |
| 八专 | 甲寅/乙卯/丁未/己未/庚申/辛酉/癸丑 | **仅日柱** | 注释"日柱为" |
| 悬针 | 甲卯/甲午/辛酉/辛子/甲子/辛卯/甲酉/辛午 | **仅日柱** | 注释"日柱干支组合" |
| 天赦 | 戊寅/甲午/戊申/甲子 | **仅日柱** | 注释"日柱为"；传统规则另需按出生季节区分（春戊寅/夏甲午/秋戊申/冬甲子），当前表未分季节——**本轮只修位置口径，季节细化标注待命理复核，不改表** |

**测试矩阵**：每类 ① 正例——对应干支位于**日柱**时命中；② 位置反例——同一干支仅位于年/月/时柱时**不命中**（构造盘覆盖至少年柱与时柱两个位置）。

**修复范围纪律**：仅给 `:996-1003` 判定块加日柱位置限制，不改 7 张表内容、不碰其他神煞。

**D. B/C 两项修复后的 API/报告行为变化清单**：
- `compute_chart` / `POST /api/chart` 的 `shensha` 字段：桃花/驿马/劫煞/灾煞/亡神/紫微/三合禄 从"恒不出现"变为按规则出现；华盖/将星 从"凡含目标支必出现"变为按年/日支局判定；7 类日柱系从"任意柱误报"变为仅日柱出现——存量盘的 `shensha` 列表普遍会变化（部分新增、部分消失）
- 下游消费方：`report_builder` 神煞段、`auto_analyzer` 与在线 chat 上下文、PDF 报告；`bazi_features` / `case_retrieval` 的特征文本若含神煞，实施时核对并记录
- 受影响快照全部重生成并人工 review diff

**E. 其他**：`enhance_shensha` 输出附带含义文本；3 个完整命盘的神煞全集 JSON 快照（在引擎修复后生成）。

### 4.4 `tests/test_bazi_calculator_ziwei.py` — 紫微（结构断言 + 少量快照）

- `calculate_ziwei` 是**仓库内纯 Python 实现**（iztro 仅以注释形式作为算法来源存在，无子进程、无 iztro_py 运行时依赖，实测 5 盘 <0.01s）。**不设** `importorskip`、不设子进程超时、无跳过策略
- 命宫、身宫落在十二地支之一；五行局为合法五局之一
- `ziwei_position`（五行局 + 农历日 → 紫微星位）直接单测
- 十四主星每颗均有落宫；十二宫齐全
- 1–2 个已知案例快照（快照后端约束见 §5 末节）

### 4.5 `tests/test_bazi_calculator_derived.py` — 衍生计算（手工断言/不变量）

- `calculate_wuxing_stats`：计数总和 = 8（四干 + 四支本气，读码确认口径正确）；缺失列表 = 计数 0 集合；最强 = argmax
- `calculate_shishen_stats`：总数不变量 = 有效柱数 + Σ 各柱 `len(cangan_detail)`（实现统计"四柱天干 + 每柱全部藏干"，`:1329-1352`）；缺失 = 计数 0 集合；最强 = argmax（含 `most_frequent_count`）
- `detect_branch_relations`：子午六冲、子丑六合、申子辰三合、寅巳申三刑、子未六害（构造盘逐一命中）
- `get_taiyuan` / `get_minggong` / `get_shengong`：返回合法干支/宫位
- `get_changsheng`：**教科书五行长生规则断言（阳顺阴逆：甲亥/乙午/丙寅/戊寅/庚巳/辛子/壬申/癸卯/丁酉/己酉）——已实测确认缺陷 #4，用户拍板路径 A 按 §8 独立最小修复**（替换 `CHANGSHENG_TABLE` 为教科书表；改变 `changsheng` 与 `day_master.shier_changsheng` 生产输出，快照在修复后生成）
- `detect_rizhu_zihe`：日柱干支自合规则抽查（丁亥/戊子/辛巳为正例）
- `calculate_wuyun_liuqi`：按现有公共契约断言 6 键——`五运 / 主事脏腑 / 体质倾向 / 六气 / 外邪倾向 / 易感季节`（`:1289-1296`），不凭空断言不存在的 schema
- `compare_charts`——结构 + **数值断言**（已实测确认缺陷 #3：按中文键读 pinyin 键，五行占比恒 0.0，§2）：
  - 每张有效命盘的五行百分比总和 ≈ 100（±0.5，舍入容差）
  - 至少一个元素比例非零
  - 百分比与输入 `wuxing_stats`（pinyin 键）重新计算的结果一致
  - 两张相同命盘的对应差值全部为 0
  - 上述断言先跑出红色证据，按 §8 流程做独立最小修复（键名映射对齐）
- `format_to_spec`：**直接调用断言**（构造 9 个参数直调 `bc.format_to_spec`，非仅经 `compute_chart` 间接覆盖）——输出精确等于 §4.6 所列 20 个键

### 4.6 `tests/test_bazi_calculator_e2e.py` — compute_chart 端到端（快照为主）

- 顶层 schema 完整性：以 `format_to_spec`（`bazi_calculator.py:1960-2087`）返回的 20 个键 + `compute_chart` 追加的 2 个键为准，共 22 个：`status / four_pillars / dayun_summary / day_master / wuxing_stats / shishen_stats / shensha / tai_yuan / ming_gong / shen_gong / da_yun / liu_nian / ziwei / wuyun_liuqi / branch_relations / rizhu_zihe / nayin_wuxing / changsheng / precision_note / solar_time / birth_info / true_solar_info`。注意 `solar_time`（`format_to_spec` 写入，`:2080`）与 `true_solar_info`（`compute_chart` 追加，`:2147`）是两个并存的键、内容同源，均断言存在
- 5 个代表命盘全量 JSON 快照（含 1 例 `use_solar_time=True`、1 例子时盘、1 例女命），快照对比前先剥离时间敏感字段、并固定农历后端（见 §5 末节两条）
- `use_solar_time` 开关行为（已实测修正语义）：`False` → 自动调用 `calculate_true_solar_time` 经度校正（`method == 'longitude_correction'`）；`True` → 输入视为已校正（`method == 'user_adjusted'`，不再自动校正）

### 4.7 `tests/test_accuracy.py` 改造 — 金标接入 pytest

- 新增 `def test_golden_accuracy():` 包装：调用现有 `run_tests()`（返回含 `passed/failed/error_details` 的 report 字典，`test_accuracy.py:93`），断言 `failed == 0`，失败时输出 `error_details` 明细
- 不改动 `run_tests` 签名与 `__main__` 入口，保持手动脚本用法不变

## 5. 快照机制

- 基线文件：`tests/fixtures/bazi_calculator_snapshots/{case_name}.json`（沿用仓库 JSON fixture 惯例）
- 再生成脚本：`tests/fixtures/bazi_calculator_snapshots/regenerate.py`，仿 `tests/build_case_db.py` 模式，手动运行重写全部基线；变更引擎后人工 review diff 再提交
- 对比方式：规范化（key 排序）后精确 JSON 对比，失败时输出字段级 diff 路径与期望值/实际值
- 快照用例清单集中在 e2e/神煞/紫微测试文件顶部的常量中定义，三处共享同一组出生参数（避免各测各的盘）
- **农历后端冻结（审核发现，必须项）**：`lunar_calendar` 在导入时探测 `iztro_py`（`lunar_calendar.py:46`），装了走 iztro、没装走内置算法——"自动兜底"不等于跨环境输出一致，快照会随机器漂移。所有涉及 `compute_chart` / `calculate_ziwei` 的快照测试统一 `monkeypatch.setattr(lunar_calendar, "_IZTRO_PYTHON", None)` 强制内置后端，并在快照元数据记录 `lunar_backend: "builtin"`；iztro 与内置算法的一致性校验另设可选测试，不进本轮硬门禁
- **时间敏感字段剥离（审核发现，必须项）**：`compute_chart` 输出有两处随运行日期变化，快照对比前必须从基线与实际输出中同时删除，否则跨年（甚至隔天）必红——
  - `liu_nian`：`calculate_liunian(date.today().year, ...)`（`bazi_calculator.py:2138`），流年列表随当前年份变
  - 大运当前标记：`calculate_dayun` 内 `date.today().year`（`:896-911`）产生 `dayun_summary.current_pillar` 与 `da_yun[*].is_current`

  被剥离字段改用结构断言单独锁定：`liu_nian` 为 3 条、年份依次为 [当年, +1, +2]、每条含干支与十神键；`da_yun` 中 `is_current` 至多一个为 true，`dayun_summary.current_pillar` 与该柱一致或为 None。

## 6. 约束

- 全离线：无网络、无 LLM、无模型下载；不新增任何第三方依赖（仅用 pytest + 标准库；iztro_py 为可选已有依赖且快照测试强制绕开）
- 不打 `slow` / `e2e` 标记，进默认收集与 CI；新套件总运行时长 < 60 秒
- 不改 `pytest.ini`、不改 CI 配置

## 7. 验收标准

1. `python -m pytest tests/test_bazi_calculator_pillars.py tests/test_bazi_calculator_dayun.py tests/test_bazi_calculator_shensha.py tests/test_bazi_calculator_ziwei.py tests/test_bazi_calculator_derived.py tests/test_bazi_calculator_e2e.py tests/test_accuracy.py -q` 全绿（xfail 仅应急路径时存在，strict xfail 不计入失败）
2. `python -m pytest tests/ -q` 全量无新增失败（与改动前基线对比）
3. 附录 A 覆盖矩阵每一行均有对应测试且通过（实现计划逐项勾选）

## 8. 非目标（YAGNI）与变更条款

- **默认不修改 `bazi_calculator.py` 本体**。唯一例外（审核修订 + 用户拍板）：权威规则/语义断言测试暴露的现存缺陷走**独立提交最小修复**路径，**不走 xfail**（用户 2026-07-17 决策：这是影响命理判断准确率的生产逻辑错误，长期保留 xfail 等于持续输出已知错误）。当前已确认五例：① 三合系神煞取组逻辑（§4.3 B）；② 日柱系神煞位置限制缺失（§4.3 C）；③ `compare_charts` 五行键名不匹配（§4.5）；④ 十二长生表与教科书矛盾（§4.5，路径 A 决策来源见 §2 缺陷 #4 的书面化记录）；⑤ `detect_branch_relations` 的 SANHE 集合迭代序不确定（§2 缺陷 #5，实施中快照发现，第五轮审核纳入）。统一处理流程：① 测试跑出红色证据并存档（写入实施总结/缺陷记录）→ ② 以**独立提交**对引擎做最小修复（仅修缺陷点，不顺手改其他逻辑）→ ③ 修复后重新生成受影响快照并人工 review diff → ④ 再执行全绿验收。xfail 仅保留为用户明确要求延迟生产行为变更时的应急路径，且必须限定 `pytest.mark.xfail(strict=True, raises=AssertionError, reason="known<缺陷名>")`，防止导入错误/环境错误等无关失败被当成已知缺陷吞掉
- 不补 `desktop_app.py` 测试（另立任务）
- 不做覆盖率工具接入、不做快照自动更新 CI
- 不扩展五运六气算法（如未来需要"岁运/主运/客运"细分，另立功能需求）
- 不做 iztro 与内置农历算法的一致性校验（另设可选测试，不进本轮门禁）
- 不做天赦季节细化（仅标注待命理复核，见 §4.3 C）
- `tests/test_charts.json` 逐例溯源元数据（`source` / `verified_at` / `timezone` / `verification_method`）本轮不补，列为后续建议：当前 100 例定位为**回归基准**（整体描述"手工计算+元亨利贞网交叉验证"），足以防回归，暂不足以独立证明算法准确率

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `compute_chart` 输出含随日期变化字段（`liu_nian`、大运当前标记），不处理则快照跨年必红 | §5：快照只锁确定性字段，时变字段改结构断言 |
| 农历双后端导致快照跨机器漂移 | §5：快照测试 monkeypatch 强制内置后端 + 元数据记录 `lunar_backend` |
| 三合系修复改变 9 类神煞生产输出 | §4.3 B：9 类口径冻结表 + 4 局 × 9 类型参数化矩阵先行，测试补齐后再修引擎；仅重写三合系判定块，不碰月德等正确逻辑 |
| 日柱系修复使非日柱不再误报 7 类神煞（存量盘 shensha 列表收缩） | §4.3 C：7 类口径表（代码注释"日柱为"自证）+ 正例/位置反例矩阵先行；天赦季节问题单列待复核、不夹带进本轮 |
| `compare_charts` 键名缺陷修复改变命盘对比 API 输出 | §4.5：数值断言先出红色证据，独立最小修复（从恒 0 变为真实占比，是纯修复无争议） |
| 十二长生表修复改变 `changsheng` / `day_master.shier_changsheng` 生产输出 | §4.5：教科书断言先出红色证据，路径 A 已拍板，独立提交修复；快照在修复后生成 |
| SANHE 集合迭代序随 PYTHONHASHSEED 随机化导致快照跨进程翻转（缺陷 #5） | 实施中快照首跑即暴露；`sorted(SANHE)` 1 行修复，5 个 hash 种子复验稳定；已纳入变更条款 |
| 快照冻结了潜在错误输出 | 手工断言层覆盖教科书规则托底；快照 diff 必须人工 review 后提交 |
| 节气边界测试循环验证（用 `get_solar_term_info` 自证） | §4.1：边界时刻取自 `solar_terms.json` 中 `verified=True` 条目的冻结 fixture，前置断言分钟精度，记录来源与时区（UTC+8） |
| 早/夜子时等边界语义锁定的是"当前行为"而非"公认正确" | 测试中显式注释说明语义来源；如后续确认引擎行为有误，测试与引擎同修 |

## 附录 A：公开函数覆盖矩阵（验收标准 3 的判定依据）

| 公开函数 | 测试文件 | 测试点 |
|---|---|---|
| `compute_chart` | e2e | 22 键 schema + 5 盘快照 + solar_time 开关 |
| `compare_charts` | derived | 结构维度键 + 五行数值断言（占比总和/非零/一致/相同盘零差） |
| `calculate_four_pillars` | pillars | 金标参数化 ≥8 例（另见 test_accuracy 100 例） |
| `get_year_pillar` | pillars | 立春边界 + 已知年柱 |
| `get_month_pillar` | pillars | 节气边界 + 五虎遁 |
| `get_day_pillar` | pillars | 金标已知日柱 + 已知日期直接调用断言（1989-01-15→乙亥、2018-11-06→壬寅） |
| `get_hour_pillar` | pillars | 五鼠遁 + 早/晚子时 |
| `get_month_branch_idx` | pillars | 边界前后月建索引 |
| `get_next_jie_info` | pillars | 下一节令名/月/日 |
| `get_solar_term_info` | pillars | verified 分钟级 / 非 verified 日期级行为 |
| `get_shishen` | pillars | 全 10 种十神 |
| `get_kongwang` | pillars | 甲子旬戌亥空 |
| `sexagenary_index` / `sexagenary_by_index` | dayun | 六十甲子往返一致 + 大运递进 |
| `calculate_dayun` | dayun | 四种方向组合 / 起运区间 / 10 步递进且柱数=10 |
| `calculate_liunian` | dayun | 年份连续 / 干支递进 / 十神 |
| `calculate_shensha` / `enhance_shensha` | shensha | 日干系断言 + 三合系 9 类 × 4 局矩阵（含反例/合并/去重）+ 日柱系 7 类位置口径（正例 + 年月时柱反例）+ 3 盘快照 |
| `calculate_ziwei` / `ziwei_position` | ziwei | 结构断言 + 星位 + 1–2 盘快照（固定内置后端） |
| `calculate_wuyun_liuqi` | derived | 现有 6 键契约 |
| `calculate_wuxing_stats` | derived | 总和=8 等不变量 |
| `calculate_shishen_stats` | derived | 修正后的总数不变量 + strongest/most_frequent_count |
| `detect_branch_relations` | derived | 冲/合/刑/害/三合 |
| `get_taiyuan` / `get_minggong` / `get_shengong` | derived | 合法干支/宫位 |
| `get_changsheng` | derived | 教科书五行长生断言（缺陷 #4 修复后转绿） |
| `detect_rizhu_zihe` | derived | 丁亥/戊子/辛巳正例 |
| `calculate_true_solar_time` | 既有 location_matching（3 例）+ e2e | 地点匹配 + solar_time 开关行为（False=自动校正 / True=user_adjusted） |
| `format_to_spec` | derived（直接调用）+ e2e | 20 键 schema |
