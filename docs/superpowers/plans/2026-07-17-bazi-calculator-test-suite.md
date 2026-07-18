# bazi_calculator 专属单元测试套件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 2,351 行的排盘核心引擎 `bazi_calculator.py` 建立专属单元测试套件（混合策略：手工规则断言 + 金标快照 + 不变量），并借权威规则测试修复 4 例已实测确认的生产缺陷。

**Architecture:** 6 个新测试文件按功能拆分（pillars/dayun/shensha/ziwei/derived/e2e）+ 1 个快照辅助模块 + 1 个基线再生成脚本 + 改造 `test_accuracy.py` 接入 pytest。快照对比前剥离时间敏感字段（`liu_nian`、大运当前标记）并 monkeypatch 固定内置农历后端。4 例引擎修复各自独立提交（缺陷 #1 三合系取组、#2 日柱系位置、#3 compare_charts 键名、#4 十二长生表——编号为 spec 身份标识，修复顺序按计划任务序）。

**Tech Stack:** pytest（无新依赖）、标准库、`bazi_calculator` / `lunar_calendar` 模块自身。

**Spec:** `docs/superpowers/specs/2026-07-17-bazi-calculator-test-suite-design.md`（终审放行 + 缺陷 4 例同步）

**审核修订:** 本计划历经四轮审核修订——第二轮（2026-07-18 review 报告）12 项；第三轮 7 项（Task 0 隔离、helper 导入推迟、solar_time 语义、大运补全、format_to_spec 直调、长生路径 A、去 tail 管道）；第四轮 5 项：全部命令改为绝对解释器路径、Task 0 增加未跟踪文档迁移与 `codex/` 分支约定、路径 A 决策来源书面化并要求执行前复述确认、`test_golden_accuracy` 增加 accuracy_report.json 备份恢复、Task 0 git 检查拆分为独立命令。

**执行纪律（仓库规则）：**
- 所有 `git commit` 需用户确认后执行；计划中的 commit 步骤给出建议信息，执行者确认后再跑。
- 4 例引擎修复必须各自独立提交，不与测试代码混提。
- 全程在 Task 0 创建的独立 worktree（`G:/project/agent-bazi-test-suite`，分支 `codex/bazi-calculator-test-suite`）中执行，红灯提交不污染主工作区。
- **所有命令中的解释器一律使用绝对路径 `G:/project/agent/.venv/Scripts/python`**（worktree 内无 `.venv`，绝对路径在主仓与 worktree 中均可用；禁止裸 `python`，它会落到 PATH 中无依赖的解释器）。
- 命令不依赖任何 shell 特定管道（如 `| tail`），直接保留完整 pytest 输出。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `tests/test_accuracy.py`（改） | 加 `test_golden_accuracy` 包装（含 accuracy_report.json 备份恢复），100 例金标接入 pytest |
| `tests/test_bazi_calculator_pillars.py`（新） | 四柱规则断言、金标参数化、节气边界、早/晚子时 |
| `tests/test_bazi_calculator_dayun.py`（新） | 大运四种方向/起运/10 步递进、流年、六十甲子往返 |
| `tests/test_bazi_calculator_shensha.py`（新） | 神煞：日干系 / 三合系矩阵 / 日柱系位置 / enhance / 3 盘快照 |
| `tests/test_bazi_calculator_derived.py`（新） | 统计不变量、支关系、宫位、长生、自合、五运六气、compare、format_to_spec（直接调用） |
| `tests/test_bazi_calculator_ziwei.py`（新） | 紫微结构断言、ziwei_position、1 盘快照 |
| `tests/test_bazi_calculator_e2e.py`（新） | compute_chart 22 键 schema、5 盘快照、时变字段结构断言、solar_time 开关 |
| `tests/bazi_snapshot_helper.py`（新） | 快照用例定义、时变字段剥离、后端冻结、快照读写与字段级 diff（**Task 13 才创建**） |
| `tests/fixtures/bazi_calculator_snapshots/regenerate.py`（新） | 基线再生成脚本（手动运行） |
| `tests/fixtures/bazi_calculator_snapshots/*.json`（生成） | 9 份快照基线（e2e×5、shensha×3、ziwei×1） |
| `bazi_calculator.py`（改，4 次独立提交） | 修复 #1 三合系取组（:944/:962-970）、#2 日柱系位置（:996-1003）、#3 compare 键名（:2174-2183）、#4 长生表（:616-627） |
| `docs/BAZI_CALCULATOR_ENGINE_DEFECTS_2026-07-17.md`（新） | 缺陷证据与修复记录 |

---

### Task 0: 隔离工作环境（前置，git 操作需用户确认）

**Files:** 无（git 操作 + 复制 3 份已批准文档）

- [ ] **Step 1: 检查工作区实况（两条独立命令）**

Run: `git status --short`
Run: `git worktree list`
Expected: 主工作区存在用户未提交改动——本计划的多个红灯/修复提交不得与之混杂。同时确认 `docs/superpowers/specs/2026-07-17-bazi-calculator-test-suite-design.md`、`docs/superpowers/plans/2026-07-17-bazi-calculator-test-suite.md`、`docs/superpowers/plans/2026-07-17-bazi-calculator-test-suite-review.md` 三份文档处于未跟踪（`??`）状态。

- [ ] **Step 2: 创建独立 worktree（经用户确认后执行；在主仓兄弟目录新建目录，需文件系统授权）**

```bash
git worktree add ../agent-bazi-test-suite -b codex/bazi-calculator-test-suite
```

Expected: 在 `G:/project/agent-bazi-test-suite` 创建 worktree，新分支 `codex/bazi-calculator-test-suite`。**注意：worktree 从 HEAD 创建，不包含 Step 1 中的三份未跟踪文档，下一步显式迁移。**

- [ ] **Step 3: 迁移已批准文档（仅这三份，不带入其他任何脏改动）**

```bash
mkdir -p ../agent-bazi-test-suite/docs/superpowers/specs ../agent-bazi-test-suite/docs/superpowers/plans
cp docs/superpowers/specs/2026-07-17-bazi-calculator-test-suite-design.md ../agent-bazi-test-suite/docs/superpowers/specs/
cp docs/superpowers/plans/2026-07-17-bazi-calculator-test-suite.md ../agent-bazi-test-suite/docs/superpowers/plans/
cp docs/superpowers/plans/2026-07-17-bazi-calculator-test-suite-review.md ../agent-bazi-test-suite/docs/superpowers/plans/
```

- [ ] **Step 4: 在 worktree 提交文档（首个提交，确认后）**

```bash
cd ../agent-bazi-test-suite
git add docs/superpowers/specs/2026-07-17-bazi-calculator-test-suite-design.md docs/superpowers/plans/2026-07-17-bazi-calculator-test-suite.md docs/superpowers/plans/2026-07-17-bazi-calculator-test-suite-review.md
git commit -m "docs: add bazi_calculator test suite spec, plan and review report"
```

**后续所有任务均在 `G:/project/agent-bazi-test-suite` 根目录执行。**

- [ ] **Step 5: 确认 worktree 可用性**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_location_matching.py -q`
Expected: 3 passed（确认主仓 venv 绝对路径可在 worktree 中驱动测试）

---

### Task 1: 基线捕获 + test_accuracy 接入 pytest

**Files:**
- Modify: `tests/test_accuracy.py`（在 `run_tests` 之后、`__main__` 之前插入包装函数）

- [ ] **Step 1: 捕获全量基线（Task 14 对照用）**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/ -q`
Expected: 记录通过/失败数（当前应全绿）。把输出数字记入实施笔记。

- [ ] **Step 2: 写包装测试（含 accuracy_report.json 备份恢复）**

在 `tests/test_accuracy.py` 的 `return report`（:93）之后、`if __name__ == '__main__':` 之前插入：

```python
def test_golden_accuracy():
    """pytest 入口：100 例金标四柱/大运回归（原 run_tests 脚本接入 pytest 收集）。

    run_tests 每次调用都会重写 accuracy_report.json（:119-121，含 test_date/elapsed_sec），
    直接接入会让每次测试运行（含 CI）都弄脏这个跟踪文件——先备份、结束后恢复。
    """
    report_path = os.path.join(os.path.dirname(__file__), 'accuracy_report.json')
    backup = None
    if os.path.exists(report_path):
        with open(report_path, 'rb') as f:
            backup = f.read()
    try:
        report = run_tests()
    finally:
        if backup is not None:
            with open(report_path, 'wb') as f:
                f.write(backup)
    assert report['failed'] == 0, (
        f"{report['failed']}/{report['total_cases']} 例金标失败: "
        f"{json.dumps(report.get('error_details', [])[:5], ensure_ascii=False)}"
    )
```

- [ ] **Step 3: 确认 pytest 现在能收集到它且工作区保持干净**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_accuracy.py -v`
Expected: `1 passed`（改造前收集 0 项）

Run: `git status --short -- tests/accuracy_report.json`
Expected: 无输出（备份恢复生效，文件未被弄脏）

- [ ] **Step 4: 确认脚本用法不受影响，并恢复生成物**

Run: `G:/project/agent/.venv/Scripts/python tests/test_accuracy.py`
Expected: 正常跑完 100 例，输出 accuracy 报告

Run: `git diff --stat -- tests/accuracy_report.json`
Expected: 仅 `test_date`/`elapsed_sec` 等生成字段变化（属脚本固有行为）

Run: `git restore -- tests/accuracy_report.json`
Expected: 工作区恢复干净（提交 `test_accuracy.py` 前必须执行，不夹带生成物）

- [ ] **Step 5: Commit（确认后）**

```bash
git add tests/test_accuracy.py
git commit -m "test: wire golden accuracy suite into pytest collection"
```

---

### Task 2: pillars 规则断言（五虎遁/五鼠遁/十神/空亡/金标参数化）

**Files:**
- Create: `tests/test_bazi_calculator_pillars.py`

- [ ] **Step 1: 写测试文件**

```python
"""四柱与边界测试：规则断言 + 金标参数化 + 节气边界 fixture + 早/晚子时。

断言来源：test_charts.json 金标、五虎遁/五鼠遁口诀、十神/旬空规则、
solar_terms.json 中 verified=True 的冻结数据 fixture（独立于比较算法，UTC+8）。
"""
import json
import os

import pytest

import bazi_calculator as bc

TESTS_DIR = os.path.dirname(__file__)
SOLAR_TERMS_PATH = os.path.join(TESTS_DIR, '..', 'knowledge-base', 'solar_terms.json')


def _load_golden(n=8):
    with open(os.path.join(TESTS_DIR, 'test_charts.json'), encoding='utf-8') as f:
        return json.load(f)['test_cases'][:n]


GOLDEN = _load_golden()


@pytest.mark.parametrize('tc', GOLDEN, ids=lambda t: t['id'])
def test_four_pillars_golden(tc):
    fp = bc.calculate_four_pillars(tc['year'], tc['month'], tc['day'], tc['hour'], 0, 'Beijing')
    exp = tc['expected']
    assert f"{fp['year']['gan']}{fp['year']['zhi']}" == exp['year']
    assert f"{fp['month']['gan']}{fp['month']['zhi']}" == exp['month']
    assert f"{fp['day']['gan']}{fp['day']['zhi']}" == exp['day']
    assert f"{fp['hour']['gan']}{fp['hour']['zhi']}" == exp['hour']
    assert fp['day_master'] == exp['day_master']


def test_wuhudun_month_stem():
    # 五虎遁：甲己之年丙作首 → 甲年正月（立春后）月柱 = 丙寅（已实证）
    assert bc.get_month_pillar(2024, '甲', 2, 20, 0, 0) == ('丙', '寅')


def test_wushudun_hour_stem():
    # 五鼠遁：甲己还加甲 → 甲日子时 = 甲子；乙庚丙作初 → 乙日子时 = 丙子（已实证）
    assert bc.get_hour_pillar('甲', 0, 30) == ('甲', '子')
    assert bc.get_hour_pillar('乙', 0, 30) == ('丙', '子')


def test_shishen_full_table():
    # 甲日主见十干（已实证）
    expected = {'甲': '比肩', '乙': '劫财', '丙': '食神', '丁': '伤官', '戊': '偏财',
                '己': '正财', '庚': '七杀', '辛': '正官', '壬': '偏印', '癸': '正印'}
    for gan, ss in expected.items():
        assert bc.get_shishen('甲', gan) == ss


def test_kongwang():
    assert bc.get_kongwang('甲', '子') == ('戌', '亥')  # 甲子旬中戌亥空（已实证）
    assert bc.get_kongwang('甲', '戌') == ('申', '酉')  # 甲戌旬中申酉空（已实证）


def test_nayin_cangan_present():
    fp = bc.calculate_four_pillars(1993, 7, 15, 14, 0, 'Beijing')
    for key in ['year', 'month', 'day', 'hour']:
        assert fp[key]['nayin']
        assert fp[key]['cangan_detail']
```

- [ ] **Step 2: 跑测试确认全绿**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_pillars.py -v`
Expected: 13 passed（8 金标 + 5 规则）

- [ ] **Step 3: Commit（确认后）**

```bash
git add tests/test_bazi_calculator_pillars.py
git commit -m "test: add pillar rule assertions for bazi_calculator"
```

---

### Task 3: pillars 边界（节气 fixture + 早/晚子时）

**Files:**
- Modify: `tests/test_bazi_calculator_pillars.py`（追加）

- [ ] **Step 1: 追加边界测试**

```python
# ── 节气边界（冻结 fixture：solar_terms.json 中 verified=True 条目，UTC+8）──

def _verified_term(year, name):
    """取自 solar_terms.json 的分钟级人工核验条目（独立于比较算法的数据表）。

    fixture 证明的是"比较算法按仓库数据表切换"，天文时刻正确性不在本轮范围。
    注意：本测试与数据表条目强绑定——若此 fixture 失败，先检查 solar_terms.json
    中对应条目是否被修改或降级（verified 变更），而不是测试本身的 bug。
    """
    with open(SOLAR_TERMS_PATH, encoding='utf-8') as f:
        st = json.load(f)
    key = f'{year}|{name}'
    assert key in st, f'fixture 缺失: {key}'
    m, d, h, mi, verified = st[key]
    assert verified is True and h >= 0, f'fixture 无分钟精度: {key}'
    return m, d, h, mi


def test_lichun_year_boundary_minute():
    # 2024 立春 2月4日 16:27（verified=True）：前 1 分钟癸卯年，整点甲辰年（已实证）
    m, d, h, mi = _verified_term(2024, '立春')
    assert bc.get_year_pillar(2024, m, d, h, mi - 1) == ('癸', '卯')
    assert bc.get_year_pillar(2024, m, d, h, mi) == ('甲', '辰')


def test_qingming_month_boundary_minute():
    # 2025 清明 4月4日 20:49（verified=True）：乙巳年 己卯月→庚辰月（已实证）
    m, d, h, mi = _verified_term(2025, '清明')
    assert bc.get_month_pillar(2025, '乙', m, d, h, mi - 1) == ('己', '卯')
    assert bc.get_month_pillar(2025, '乙', m, d, h, mi) == ('庚', '辰')


def test_jingzhe_month_boundary_date_only():
    # 2024 惊蛰 3月6日（verified=False → 日期级切换，已实证）
    # 断言的是"按日期切换"的外部行为，不验证内部 term_minutes=-1 的实现细节
    with open(SOLAR_TERMS_PATH, encoding='utf-8') as f:
        m, d, _h, _mi, verified = json.load(f)['2024|惊蛰']
    assert verified is False
    assert bc.get_month_pillar(2024, '甲', m, d - 1, 12, 0) == ('丙', '寅')
    assert bc.get_month_pillar(2024, '甲', m, d, 12, 0) == ('丁', '卯')


def test_solar_term_info_modes():
    # verified 条目分钟级 / 非 verified 条目日期级（读码确认行为 bazi_calculator.py:187-193）
    # 注：断言基于当前 solar_terms.json 全部为 5 字段条目的已知数据形状
    name_before, *_ = bc.get_solar_term_info(2024, 2, 4, 16, 26)
    name_after, *_ = bc.get_solar_term_info(2024, 2, 4, 16, 27)
    assert name_before != name_after  # 立春 16:27 精确切换
    name_d1, *_ = bc.get_solar_term_info(2024, 3, 5, 12, 0)
    name_d2, *_ = bc.get_solar_term_info(2024, 3, 6, 12, 0)
    assert name_d1 != name_d2  # 惊蛰按日切换


def test_month_branch_idx_boundary():
    before = bc.get_month_branch_idx(2024, 2, 4, 16, 26)
    after = bc.get_month_branch_idx(2024, 2, 4, 16, 27)
    assert (after - before) % 12 == 1


def test_next_jie_info_shape():
    name, m, d = bc.get_next_jie_info(2024, 6, 15, 12, 0)
    assert name in bc.SOLAR_TERM_NAMES
    assert 1 <= m <= 12 and 1 <= d <= 31


# ── 早/晚子时（特征化：锁定引擎当前语义，见 spec §4.1）──

def test_zi_hour_early_uses_same_day_stem():
    # 早子时 0:00-0:59：时干按当日干起（甲日 → 甲子，已实证）
    assert bc.get_hour_pillar('甲', 0, 30) == ('甲', '子')


def test_zi_hour_late_uses_next_day_stem():
    # 晚子时 23:00-23:59：时干按次日干起（甲日→次日乙→丙子；乙日→次日丙→戊子，已实证）
    assert bc.get_hour_pillar('甲', 23, 30) == ('丙', '子')
    assert bc.get_hour_pillar('乙', 23, 30) == ('戊', '子')


def test_zi_hour_day_pillar_not_rolled():
    # 引擎语义：日柱不随 23 点切换（get_day_pillar 无时刻参数）——特征化锁定
    early = bc.calculate_four_pillars(1990, 5, 10, 0, 30, 'Beijing')
    late = bc.calculate_four_pillars(1990, 5, 10, 23, 30, 'Beijing')
    assert f"{early['day']['gan']}{early['day']['zhi']}" == f"{late['day']['gan']}{late['day']['zhi']}"
    assert early['hour']['zhi'] == late['hour']['zhi'] == '子'
    assert early['hour']['gan'] != late['hour']['gan']
```

- [ ] **Step 2: 跑测试确认全绿**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_pillars.py -v`
Expected: 22 passed（13 + 9 新增）

- [ ] **Step 3: Commit（确认后）**

```bash
git add tests/test_bazi_calculator_pillars.py
git commit -m "test: add solar-term boundary and zi-hour characterization tests"
```

---

### Task 4: 大运 / 流年 / 六十甲子

**Files:**
- Create: `tests/test_bazi_calculator_dayun.py`

- [ ] **Step 1: 写测试文件**

```python
"""大运与流年测试：四种方向组合、起运区间、10 步递进、流年序列。"""
import bazi_calculator as bc


def _dayun(year, month, day, hour, gender):
    fp = bc.calculate_four_pillars(year, month, day, hour, 0, 'Beijing')
    yp = (fp['year']['gan'], fp['year']['zhi'])
    mp = (fp['month']['gan'], fp['month']['zhi'])
    return bc.calculate_dayun(yp, mp, gender, year, month, day, hour, 0), mp


def test_direction_yang_male_forward():
    dy, _ = _dayun(2024, 3, 10, 10, 'male')    # 甲辰年 阳男 → 顺排（已实证）
    assert dy['direction'] == '顺排'


def test_direction_yang_female_backward():
    dy, _ = _dayun(2024, 3, 10, 10, 'female')  # 阳女 → 逆排（已实证）
    assert dy['direction'] == '逆排'


def test_direction_yin_male_backward():
    dy, _ = _dayun(1993, 7, 15, 14, 'male')    # 癸酉年 阴男 → 逆排（已实证）
    assert dy['direction'] == '逆排'


def test_direction_yin_female_forward():
    dy, _ = _dayun(1993, 7, 15, 14, 'female')  # 癸酉年 阴女 → 顺排（已实证）
    assert dy['direction'] == '顺排'


def test_starting_age_range():
    dy, _ = _dayun(1993, 7, 15, 14, 'male')
    assert 0 <= dy['starting_age'] <= 10                     # 范围兜底
    assert abs(dy['starting_age'] - 2.5) < 0.3               # 已知盘精确值（已实证 2.5）


def test_pillar_progression_forward():
    # 顺排：第 i 步大运 = 月柱沿六十甲子后移 i 位，连续 10 步且柱数=10（已实证 丁卯→戊辰→己巳…）
    dy, mp = _dayun(2024, 3, 10, 10, 'male')
    assert len(dy['pillars']) == 10
    idx = bc.sexagenary_index(*mp)
    for i, p in enumerate(dy['pillars'], start=1):
        assert (p['gan'], p['zhi']) == bc.sexagenary_by_index((idx + i) % 60)


def test_pillar_progression_backward():
    # 逆排：第 i 步大运 = 月柱前移 i 位（已实证 己未→戊午…）
    dy, mp = _dayun(1993, 7, 15, 14, 'male')
    assert len(dy['pillars']) == 10
    idx = bc.sexagenary_index(*mp)
    for i, p in enumerate(dy['pillars'], start=1):
        assert (p['gan'], p['zhi']) == bc.sexagenary_by_index((idx - i) % 60)


def test_sexagenary_roundtrip():
    for i in range(60):
        assert bc.sexagenary_index(*bc.sexagenary_by_index(i)) == i


def test_liunian_sequence():
    # 甲日主 2026 起 3 年（已实证：丙午食神/丁未伤官/戊申偏财）
    ln = bc.calculate_liunian(2026, '甲', 3)
    assert [e['year'] for e in ln] == [2026, 2027, 2028]
    assert [(e['gan'], e['zhi']) for e in ln] == [('丙', '午'), ('丁', '未'), ('戊', '申')]
    assert [e['shi_shen'] for e in ln] == ['食神', '伤官', '偏财']
    for i in range(1, 3):
        prev = bc.sexagenary_index(ln[i - 1]['gan'], ln[i - 1]['zhi'])
        cur = bc.sexagenary_index(ln[i]['gan'], ln[i]['zhi'])
        assert (cur - prev) % 60 == 1
```

- [ ] **Step 2: 跑测试确认全绿**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_dayun.py -v`
Expected: 9 passed

- [ ] **Step 3: Commit（确认后）**

```bash
git add tests/test_bazi_calculator_dayun.py
git commit -m "test: add dayun/liunian/sexagenary tests"
```

---

### Task 5: 神煞 A — 日干系（直接绿）

**Files:**
- Create: `tests/test_bazi_calculator_shensha.py`

**导入纪律（第三轮审核修订）**：本文件此刻**只导入 `pytest` 与 `bazi_calculator`**——`bazi_snapshot_helper` 到 Task 13 才创建，快照相关的 import 与测试统一在 Task 13 追加。任何"先写 import 再临时注释"的做法都会让 pytest 收集阶段全红，禁止使用。

- [ ] **Step 1: 写测试文件（A 部分，无快照 import）**

```python
"""神煞测试：A 日干系 / B 三合系(缺陷#1) / C 日柱系(缺陷#2) / enhance / 快照(Task 13 追加)。

B/C 两部分先按教科书规则写断言跑出红色证据，再按 spec §8 流程最小修复引擎转绿。
"""
import pytest

import bazi_calculator as bc


def mk_fp(year, month, day, hour):
    """构造最小 four_pillars 结构（calculate_shensha 只读各柱 gan/zhi，已验证）。"""
    def _p(ganzhi):
        return {'gan': ganzhi[0], 'zhi': ganzhi[1]}
    return {'year': _p(year), 'month': _p(month), 'day': _p(day), 'hour': _p(hour)}


def _ganzhi_for(zhi, offset=0):
    """天干仅起占位作用——三合系/日柱系神煞均不以天干判定，任意天干不影响结果。"""
    return bc.TIANGAN[offset % 10] + zhi


# ── A. 日干系（读码+实测确认实现正确，直接断言）──

def test_tianyi_guiren():
    # 甲戊庚日主见丑/未 = 天乙贵人（已实测命中）
    ss = bc.calculate_shensha(mk_fp('甲子', '乙丑', '甲子', '甲子'), '甲')
    assert '天乙贵人' in ss['month']


def test_wenchang():
    # 甲日主见巳 = 文昌贵人
    ss = bc.calculate_shensha(mk_fp('甲子', '己巳', '甲子', '甲子'), '甲')
    assert '文昌贵人' in ss['month']


def test_yangren():
    # 甲日主见卯 = 羊刃
    ss = bc.calculate_shensha(mk_fp('甲子', '丁卯', '甲子', '甲子'), '甲')
    assert '羊刃' in ss['month']


def test_enhance_shensha_meaning():
    enh = bc.enhance_shensha(bc.calculate_shensha(mk_fp('甲子', '乙丑', '甲子', '甲子'), '甲'))
    assert isinstance(enh, list) and enh
    for item in enh:
        assert set(item) >= {'name', 'position', 'meaning'}
    assert any(i['name'] == '天乙贵人' and i['meaning'] for i in enh)
```

- [ ] **Step 2: 跑 A 组测试**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_shensha.py -v`
Expected: 4 passed

- [ ] **Step 3: Commit（确认后）**

```bash
git add tests/test_bazi_calculator_shensha.py
git commit -m "test: add day-stem shensha assertions"
```

---

### Task 6: 神煞 B — 三合系 9 类 × 4 局矩阵（红色证据）

**Files:**
- Modify: `tests/test_bazi_calculator_shensha.py`（追加 B 部分）

- [ ] **Step 1: 追加三合系矩阵测试**

```python
# ── B. 三合系（缺陷#1：:944 以候选支自身定局。按教科书规则断言，修复后转绿）──

SANHE_GROUPS = [('申', '子', '辰'), ('寅', '午', '戌'), ('巳', '酉', '丑'), ('亥', '卯', '未')]

# (神煞名, 目标支映射表, 参考支口径)：紫微仅日支（源码注释口径，待命理复核）；其余年/日支并集
SANHE_CASES = [
    ('桃花', lambda: bc.TAOHUA_MAP, 'year_or_day'),
    ('驿马', lambda: bc.YIMA_MAP, 'year_or_day'),
    ('华盖', lambda: bc.HUAGAI_MAP, 'year_or_day'),
    ('将星', lambda: bc._jiangxing, 'year_or_day'),
    ('劫煞', lambda: bc._jiesha, 'year_or_day'),
    ('灾煞', lambda: bc._zaisha, 'year_or_day'),
    ('亡神', lambda: bc._wangshen, 'year_or_day'),
    ('紫微', lambda: bc._ziwei_ss, 'day_only'),
    ('三合禄', lambda: bc._sanhelu, 'year_or_day'),
]


@pytest.mark.parametrize('name, get_table, scope', SANHE_CASES)
@pytest.mark.parametrize('group', SANHE_GROUPS)
def test_sanhe_by_year_branch(name, get_table, scope, group):
    if scope == 'day_only':
        pytest.skip('紫微仅以日支为参考')
    target = get_table()[group]
    fp = mk_fp(_ganzhi_for(group[0]), '甲子', '甲子', _ganzhi_for(target, 1))
    ss = bc.calculate_shensha(fp, '甲')
    assert name in ss['hour'], f'年支{group[0]}属{"".join(group)}局，时支{target}应命中{name}'


@pytest.mark.parametrize('name, get_table, scope', SANHE_CASES)
@pytest.mark.parametrize('group', SANHE_GROUPS)
def test_sanhe_by_day_branch(name, get_table, scope, group):
    target = get_table()[group]
    fp = mk_fp('甲子', '甲子', _ganzhi_for(group[1]), _ganzhi_for(target, 1))
    ss = bc.calculate_shensha(fp, '甲')
    assert name in ss['hour'], f'日支{group[1]}属{"".join(group)}局，时支{target}应命中{name}'


@pytest.mark.parametrize('name, get_table, scope', SANHE_CASES)
def test_sanhe_negative(name, get_table, scope):
    # 目标支在盘，但年支(子)与日支(子)均属申子辰局；取寅午戌局目标 → 不命中
    target = get_table()[('寅', '午', '戌')]
    fp = mk_fp('甲子', '甲子', '甲子', _ganzhi_for(target, 1))
    ss = bc.calculate_shensha(fp, '甲')
    assert name not in ss['hour'], f'年/日支均不属寅午戌局，时支{target}不应命中{name}'


def test_sanhe_negative_ziwei_year_only():
    # 紫微(仅日支)：年支属申子辰局、日支午不属局 → 时支酉不命中
    fp = mk_fp('甲申', '甲子', '甲午', '乙酉')
    ss = bc.calculate_shensha(fp, '甲')
    assert '紫微' not in ss['hour']


def test_sanhe_merge_year_and_day():
    # 年支属申子辰局、日支属寅午戌局 → 两局目标支均命中（并集合并）
    fp1 = mk_fp('甲申', '甲子', '甲寅', '乙酉')   # 时支酉 = 申子辰局桃花
    assert '桃花' in bc.calculate_shensha(fp1, '甲')['hour']
    fp2 = mk_fp('甲申', '甲子', '甲寅', _ganzhi_for('申', 1))  # 时支申 = 寅午戌局驿马
    assert '驿马' in bc.calculate_shensha(fp2, '甲')['hour']


def test_sanhe_no_duplicate():
    # 年支(申)与日支(辰)同属申子辰局 → 同柱桃花只出现一次
    ss = bc.calculate_shensha(mk_fp('甲申', '甲子', '甲辰', '乙酉'), '甲')
    assert ss['hour'].count('桃花') == 1
```

- [ ] **Step 2: 跑 B 组，记录红色证据**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_shensha.py -v -k "sanhe"`
Expected: **大量 FAIL**——桃花/驿马/劫煞/灾煞/亡神/紫微/三合禄在 by_year/by_day 正例上不命中；华盖/将星在 negative 反例上误命中（自分组过度触发）。把失败计数与代表性失败信息**原样粘贴**到实施笔记（Task 14 缺陷记录用）。

- [ ] **Step 3: Commit 红色证据（确认后）**

```bash
git add tests/test_bazi_calculator_shensha.py
git commit -m "test: add sanhe-series shensha matrix exposing grouping defect (red evidence)"
```

---

### Task 7: 引擎修复 #1 — 三合系取组（独立提交）

**Files:**
- Modify: `bazi_calculator.py:934-970`

- [ ] **Step 1: 改 `calculate_shensha` 的参考局取法**

`bazi_calculator.py:939-945` 当前：

```python
    result = {}
    for key in ['year', 'month', 'day', 'hour']:
        p = four_pillars[key]
        gan, zhi = p['gan'], p['zhi']
        ss = []
        group = _find_taohua_group(zhi)  # shared 三合 group for this zhi
```

改为（在循环外建立参考局集合，删除循环内 `group` 赋值；`year_zhi` 复用 `:934` 已有变量）：

```python
    day_zhi = four_pillars['day']['zhi']
    # 三合系参考局：年支/日支所属三合局并集（紫微仅日支）——spec §4.3 B 口径冻结表
    # 12 地支全覆盖四个三合局，_find_taohua_group 对合法地支永不返回 None（不变式）；
    # 若该不变式未来被破坏，set 推导的 if g 过滤与下方 sanhe_day_group 的假值判定仍可安全降级
    sanhe_ref_groups = {g for g in (_find_taohua_group(year_zhi), _find_taohua_group(day_zhi)) if g}
    sanhe_day_group = _find_taohua_group(day_zhi)

    result = {}
    for key in ['year', 'month', 'day', 'hour']:
        p = four_pillars[key]
        gan, zhi = p['gan'], p['zhi']
        ss = []
```

`bazi_calculator.py:960-970` 当前：

```python
        # ── 三合系 (check per-pillar zhi) ──
        if group:
            if zhi == TAOHUA_MAP.get(group):          ss.append('桃花')
            if zhi == YIMA_MAP.get(group):             ss.append('驿马')
            if zhi == HUAGAI_MAP.get(group):           ss.append('华盖')
            if zhi == _jiangxing.get(group):           ss.append('将星')
            if zhi == _jiesha.get(group):              ss.append('劫煞')
            if zhi == _zaisha.get(group):              ss.append('灾煞')
            if zhi == _wangshen.get(group):            ss.append('亡神')
            if zhi == _ziwei_ss.get(group):            ss.append('紫微')
            if zhi == _sanhelu.get(group):             ss.append('三合禄')
```

改为：

```python
        # ── 三合系：以年支/日支所属三合局为参考（紫微仅以日支）──
        if any(zhi == TAOHUA_MAP.get(g) for g in sanhe_ref_groups):   ss.append('桃花')
        if any(zhi == YIMA_MAP.get(g) for g in sanhe_ref_groups):     ss.append('驿马')
        if any(zhi == HUAGAI_MAP.get(g) for g in sanhe_ref_groups):   ss.append('华盖')
        if any(zhi == _jiangxing.get(g) for g in sanhe_ref_groups):   ss.append('将星')
        if any(zhi == _jiesha.get(g) for g in sanhe_ref_groups):      ss.append('劫煞')
        if any(zhi == _zaisha.get(g) for g in sanhe_ref_groups):      ss.append('灾煞')
        if any(zhi == _wangshen.get(g) for g in sanhe_ref_groups):    ss.append('亡神')
        if sanhe_day_group and zhi == _ziwei_ss.get(sanhe_day_group): ss.append('紫微')
        if any(zhi == _sanhelu.get(g) for g in sanhe_ref_groups):     ss.append('三合禄')
```

**纪律**：不碰 `:981` 月德取组（`month_zhi` 参考是对的）及其他神煞逻辑。

- [ ] **Step 2: 跑 B 组矩阵确认转绿**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_shensha.py -v -k "sanhe"`
Expected: 全绿——应为 **80 passed + 4 skipped**（by_year 36 例中紫微 4 例 skip 余 32 pass；by_day 36 pass；negative 9 pass；ziwei_year_only/merge/no_duplicate 各 1 pass；以实际 ran 输出为准）

- [ ] **Step 3: 跑 A 组与已建套件确认无回归**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_shensha.py tests/test_bazi_calculator_pillars.py tests/test_bazi_calculator_dayun.py tests/test_accuracy.py -q`
Expected: 全绿

- [ ] **Step 4: Commit（独立提交，确认后）**

```bash
git add bazi_calculator.py
git commit -m "fix: resolve sanhe-series shensha by year/day branch group instead of candidate branch"
```

---

### Task 8: 神煞 C — 日柱系位置口径（红色证据 → 修复 #2）

**Files:**
- Modify: `tests/test_bazi_calculator_shensha.py`（追加 C 部分）
- Modify: `bazi_calculator.py:996-1003`

- [ ] **Step 1: 追加日柱系测试**

```python
# ── C. 日柱系（缺陷#2：:996-1003 无 key=='day' 限制。修复后转绿）──

DAY_PILLAR_CASES = [
    ('魁罡', '庚辰'), ('孤鸾煞', '甲寅'), ('阴差阳错', '丙子'),
    ('十恶大败', '甲辰'), ('八专', '丁未'), ('悬针', '甲午'), ('天赦', '戊寅'),
]

# 填充柱均不在 7 张日柱系表内——日柱系仅读本柱干支，他柱内容不进入判定逻辑
NEUTRAL_FP = ('乙丑', '丙寅', '丁卯', '戊辰')


@pytest.mark.parametrize('name, ganzhi', DAY_PILLAR_CASES)
def test_day_pillar_positive(name, ganzhi):
    # 对应干支位于日柱时命中（7 张表注释均为"日柱为"）
    fp = mk_fp('甲子', '甲子', ganzhi, '甲子')
    assert name in bc.calculate_shensha(fp, '甲')['day']


@pytest.mark.parametrize('name, ganzhi', DAY_PILLAR_CASES)
@pytest.mark.parametrize('pos', ['year', 'month', 'hour'])
def test_day_pillar_position_negative(name, ganzhi, pos):
    # 同一干支仅位于年/月/时柱时不命中（其余柱填充互不相同的非表干支）
    fp = mk_fp(*NEUTRAL_FP)
    fp[pos] = {'gan': ganzhi[0], 'zhi': ganzhi[1]}
    assert name not in bc.calculate_shensha(fp, '甲')[pos]
```

- [ ] **Step 2: 跑 C 组，记录红色证据**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_shensha.py -v -k "day_pillar"`
Expected: 7 正例 passed；21 位置反例 **FAIL**（非日柱误报）。失败计数记入实施笔记。

- [ ] **Step 3: Commit 红色证据（确认后）**

```bash
git add tests/test_bazi_calculator_shensha.py
git commit -m "test: add day-pillar-only shensha position assertions (red evidence)"
```

- [ ] **Step 4: 修引擎——加日柱位置限制**

`bazi_calculator.py:996-1003` 当前：

```python
        # ── 日柱系 ──
        if gan + zhi in KUIGANG:                       ss.append('魁罡')
        if gan + zhi in _guluan:                       ss.append('孤鸾煞')
        if gan + zhi in _yincha:                       ss.append('阴差阳错')
        if gan + zhi in _shiedabai:                    ss.append('十恶大败')
        if gan + zhi in _bazhuan:                      ss.append('八专')
        if gan + zhi in _xuanzhen:                     ss.append('悬针')
        if gan + zhi in _tianshe:                      ss.append('天赦')
```

改为：

```python
        # ── 日柱系（7 张表注释均为"日柱为"，仅以日柱论）──
        if key == 'day':
            if gan + zhi in KUIGANG:                   ss.append('魁罡')
            if gan + zhi in _guluan:                   ss.append('孤鸾煞')
            if gan + zhi in _yincha:                   ss.append('阴差阳错')
            if gan + zhi in _shiedabai:                ss.append('十恶大败')
            if gan + zhi in _bazhuan:                  ss.append('八专')
            if gan + zhi in _xuanzhen:                 ss.append('悬针')
            if gan + zhi in _tianshe:                  ss.append('天赦')
```

**纪律**：不改 7 张表内容；天赦季节细化不做（spec §8 非目标）。

- [ ] **Step 5: 跑 C 组转绿 + 全文件回归**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_shensha.py -v`
Expected: 全绿（含 A/B 组无回归）

- [ ] **Step 6: Commit（独立提交，确认后）**

```bash
git add bazi_calculator.py
git commit -m "fix: restrict day-pillar shensha (kuigang etc.) to day pillar only"
```

---

### Task 9: derived 全套（含缺陷 #4 红色证据；format_to_spec 直接调用）

**Files:**
- Create: `tests/test_bazi_calculator_derived.py`

- [ ] **Step 1: 写测试文件**

```python
"""衍生计算测试：统计不变量 / 支关系 / 宫位 / 长生 / 自合 / 五运六气 / format_to_spec。

changsheng 教科书断言先跑出缺陷 #4 的红色证据，Task 10 修复后转绿。
"""
import pytest

import bazi_calculator as bc

PINYIN_ELEMENTS = [('jin', '金'), ('mu', '木'), ('shui', '水'), ('huo', '火'), ('tu', '土')]


def _fp():
    return bc.calculate_four_pillars(1993, 7, 15, 14, 0, 'Beijing')


def _crafted(branches):
    """按 year/month/day/hour 顺序造四支（干统一甲）。"""
    return {k: {'gan': '甲', 'zhi': z} for k, z in zip(['year', 'month', 'day', 'hour'], branches)}


# ── 统计不变量 ──

def test_wuxing_stats_invariants():
    ws = bc.calculate_wuxing_stats(_fp())
    counts = {e: ws[k] for k, e in PINYIN_ELEMENTS}
    assert sum(counts.values()) == 8                          # 四干 + 四支本气
    assert set(ws['missing']) == {e for e, c in counts.items() if c == 0}
    assert counts[ws['strongest']] == max(counts.values())


def test_shishen_stats_invariants():
    fp = _fp()
    ss = bc.calculate_shishen_stats(fp)
    present = [fp[k] for k in ['year', 'month', 'day', 'hour'] if k in fp]
    expected_total = len(present) + sum(len(p.get('cangan_detail', [])) for p in present)
    assert sum(ss['counts'].values()) == expected_total       # 四干 + 全部藏干（:1329-1352）
    assert set(ss['missing']) == {s for s, c in ss['counts'].items() if c == 0}
    # 最强 = argmax（对并列稳健，不假设 tie-break 顺序）
    assert ss['counts'][ss['strongest']] == max(ss['counts'].values())
    assert ss['most_frequent_count'] == max(ss['counts'].values())


# ── 支关系 ──

def test_liuchong():
    rels = bc.detect_branch_relations(_crafted(['子', '午', '子', '丑']))
    assert any(r['type'] == '六冲' for r in rels)


def test_liuhe():
    rels = bc.detect_branch_relations(_crafted(['子', '午', '子', '丑']))
    assert any(r['type'] == '六合' and '子丑' in r['detail'] for r in rels)


def test_sanhe_full():
    rels = bc.detect_branch_relations(_crafted(['申', '子', '辰', '寅']))
    assert any(r['type'] == '三合' and r['pillars'] == 'year-month-day' for r in rels)


def test_sanxing():
    rels = bc.detect_branch_relations(_crafted(['寅', '巳', '申', '戌']))
    assert any(r['type'] == '三刑' for r in rels)


def test_liuhai():
    rels = bc.detect_branch_relations(_crafted(['子', '未', '午', '丑']))
    assert any(r['type'] == '六害' for r in rels)


# ── 宫位 ──

def test_gong_positions_legal():
    fp = _fp()
    for key in ['taiyuan', 'minggong', 'shengong']:
        assert fp[key]['gan'] in bc.TIANGAN
        assert fp[key]['zhi'] in bc.DIZHI
        assert fp[key]['nayin']
    # 直接调用覆盖（附录 A 矩阵）
    ty = bc.get_taiyuan(fp['month']['gan'], fp['month']['zhi'], fp['year']['gan'], fp['year']['zhi'])
    assert ty['gan'] in bc.TIANGAN and ty['zhi'] in bc.DIZHI
    mg = bc.get_minggong(fp['month']['zhi'], fp['hour']['zhi'])
    assert mg['zhi'] in bc.DIZHI
    sg = bc.get_shengong(fp['month']['zhi'], fp['hour']['zhi'])
    assert sg['zhi'] in bc.DIZHI


# ── 十二长生（教科书五行长生：阳顺阴逆。缺陷#4 红色证据，Task 10 修复后转绿）──

CHANGSHENG_TEXTBOOK = [
    ('甲', '亥'), ('乙', '午'), ('丙', '寅'), ('戊', '寅'), ('庚', '巳'),
    ('辛', '子'), ('壬', '申'), ('癸', '卯'), ('丁', '酉'), ('己', '酉'),
]


@pytest.mark.parametrize('gan, zhi', CHANGSHENG_TEXTBOOK)
def test_changsheng_textbook(gan, zhi):
    assert bc.get_changsheng(gan, zhi) == '长生'


# ── 日柱干支自合 ──

def test_rizhu_zihe_positive():
    for gan, zhi in [('丁', '亥'), ('戊', '子'), ('辛', '巳')]:
        r = bc.detect_rizhu_zihe(gan, zhi)
        assert r['is_zihe'] is True and r['he_type']


def test_rizhu_zihe_negative():
    assert bc.detect_rizhu_zihe('甲', '子')['is_zihe'] is False


# ── 五运六气（现有 6 键公共契约，不凭空扩展）──

def test_wuyun_liuqi_schema():
    r = bc.calculate_wuyun_liuqi('甲', '子')
    assert set(r.keys()) == {'五运', '主事脏腑', '体质倾向', '六气', '外邪倾向', '易感季节'}


# ── format_to_spec（直接调用，精确 20 键）──

FORMAT_SPEC_KEYS = {
    'status', 'four_pillars', 'dayun_summary', 'day_master', 'wuxing_stats', 'shishen_stats',
    'shensha', 'tai_yuan', 'ming_gong', 'shen_gong', 'da_yun', 'liu_nian', 'ziwei',
    'wuyun_liuqi', 'branch_relations', 'rizhu_zihe', 'nayin_wuxing', 'changsheng',
    'precision_note', 'solar_time',
}


def test_format_to_spec_direct_20_keys():
    # 构造 9 个参数直接调用 format_to_spec（非仅经 compute_chart 间接覆盖）
    fp = _fp()
    dm = fp['day_master']
    yp = (fp['year']['gan'], fp['year']['zhi'])
    mp = (fp['month']['gan'], fp['month']['zhi'])
    dayun = bc.calculate_dayun(yp, mp, 'male', 1993, 7, 15, 14, 0)
    shensha = bc.calculate_shensha(fp, dm)
    ziwei = bc.calculate_ziwei(1993, 7, 15, 14, 'male')
    wuyun = bc.calculate_wuyun_liuqi(yp[0], yp[1])
    wuxing = bc.calculate_wuxing_stats(fp)
    shishen = bc.calculate_shishen_stats(fp)
    liunian = bc.calculate_liunian(2026, dm, 3)
    true_solar_info = {'method': 'no_correction'}
    result = bc.format_to_spec(fp, dayun, shensha, ziwei, wuyun, wuxing, shishen, liunian, true_solar_info)
    assert set(result.keys()) == FORMAT_SPEC_KEYS
```

- [ ] **Step 2: 跑测试——changsheng 红色证据，其余绿**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_derived.py -v`
Expected: `test_changsheng_textbook` 多数 FAIL（已实测 `get_changsheng('甲','亥')` 返回 `'养'`；`CHANGSHENG_TABLE` 各行数据与其自身注释矛盾），其余测试 passed。失败详情**原样粘贴**到实施笔记（Task 14 缺陷记录用）。

- [ ] **Step 3: Commit 红色证据（确认后）**

```bash
git add tests/test_bazi_calculator_derived.py
git commit -m "test: add derived-calculation tests exposing changsheng table defect (red evidence)"
```

---

### Task 10: 引擎修复 #4 — 十二长生表（独立提交）

**Files:**
- Modify: `bazi_calculator.py:616-627`

**决策依据（书面化，第三轮审核要求）**：用户于 2026-07-17 在 Kimi Code 会话中经结构化问答（AskUserQuestion）明确选择"路径 A：修复为教科书表"。spec §2 缺陷 #4 已据此登记。**执行本任务前向用户复述该决策并再次确认**；若用户翻转为路径 B，则本任务跳过、Task 9 的 changsheng 测试改为特征化断言（注释"引擎现行口径，待命理复核"）。

- [ ] **Step 1: 替换 CHANGSHENG_TABLE 为教科书表（阳顺阴逆）**

`bazi_calculator.py:616-627` 当前数据行与注释矛盾，整体替换为：

```python
CHANGSHENG_TABLE = {
    '甲': [11, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],   # 阳顺：长生亥
    '乙': [6, 5, 4, 3, 2, 1, 0, 11, 10, 9, 8, 7],   # 阴逆：长生午
    '丙': [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1],   # 阳顺：长生寅
    '丁': [9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 11, 10],   # 阴逆：长生酉
    '戊': [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1],   # 阳顺：长生寅（火土同宫）
    '己': [9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 11, 10],   # 阴逆：长生酉
    '庚': [5, 6, 7, 8, 9, 10, 11, 0, 1, 2, 3, 4],   # 阳顺：长生巳
    '辛': [0, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],   # 阴逆：长生子
    '壬': [8, 9, 10, 11, 0, 1, 2, 3, 4, 5, 6, 7],   # 阳顺：长生申
    '癸': [3, 2, 1, 0, 11, 10, 9, 8, 7, 6, 5, 4],   # 阴逆：长生卯
}
```

**注意**：此修复改变 `changsheng` 与 `day_master.shier_changsheng` 生产输出，Task 13 快照必须在此之后生成。

- [ ] **Step 2: 跑 changsheng 转绿 + 全文件回归**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_derived.py -q`
Expected: 全绿

- [ ] **Step 3: 跑已建套件确认无回归**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_derived.py tests/test_bazi_calculator_shensha.py tests/test_bazi_calculator_pillars.py tests/test_bazi_calculator_dayun.py tests/test_accuracy.py -q`
Expected: 全绿

- [ ] **Step 4: Commit（独立提交，确认后）**

```bash
git add bazi_calculator.py
git commit -m "fix: correct twelve-growth (changsheng) table to textbook yang-forward/yin-backward order"
```

---

### Task 11: compare_charts 数值断言（红色证据 → 修复 #3）

**Files:**
- Modify: `tests/test_bazi_calculator_derived.py`（追加）
- Modify: `bazi_calculator.py:2174-2183`

- [ ] **Step 1: 追加 compare_charts 测试**

```python
# ── compare_charts（缺陷#3：按中文键读 pinyin 键，占比恒 0。修复后转绿）──

def _two_charts():
    c1 = bc.compute_chart(1993, 7, 15, 14, 0, 'male', 'Beijing', False)
    c2 = bc.compute_chart(1988, 2, 20, 10, 0, 'female', 'Beijing', False)
    return c1, c2


def test_compare_structure():
    cc = bc.compare_charts(*_two_charts())
    assert {'wuxing_compare', 'dm_relation', 'nayin', 'shensha', 'dayun'} <= set(cc.keys())


def test_compare_wuxing_pct_sums_100():
    cc = bc.compare_charts(*_two_charts())
    for side in ['chart1_pct', 'chart2_pct']:
        total = sum(v[side] for v in cc['wuxing_compare'].values())
        assert abs(total - 100) <= 0.6, f'{side} 总和 {total}（修复前恒为 0）'


def test_compare_wuxing_nonzero():
    cc = bc.compare_charts(*_two_charts())
    assert any(v['chart1_pct'] > 0 for v in cc['wuxing_compare'].values())


def test_compare_wuxing_matches_input():
    c1, _ = _two_charts()
    cc = bc.compare_charts(*_two_charts())
    ws = c1['wuxing_stats']
    total = sum(ws[k] for k, _ in PINYIN_ELEMENTS)
    for k, e in PINYIN_ELEMENTS:
        assert cc['wuxing_compare'][e]['chart1_pct'] == round(ws[k] / total * 100, 1)


def test_compare_identical_charts_zero_diff():
    c1, _ = _two_charts()
    cc = bc.compare_charts(c1, c1)
    assert all(v['diff'] == 0 for v in cc['wuxing_compare'].values())
```

- [ ] **Step 2: 跑 compare 组，记录红色证据**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_derived.py -v -k "compare"`
Expected: `pct_sums_100` / `nonzero` / `matches_input` **FAIL**（占比恒 0.0），structure 与 zero_diff passed。失败信息记入实施笔记。

- [ ] **Step 3: Commit 红色证据（确认后）**

```bash
git add tests/test_bazi_calculator_derived.py
git commit -m "test: add compare_charts wuxing numeric assertions (red evidence)"
```

- [ ] **Step 4: 修引擎——键名映射对齐**

`bazi_calculator.py:2174-2183` 当前：

```python
    ws1 = chart1.get('wuxing_stats', {})
    ws2 = chart2.get('wuxing_stats', {})
    all_elements = ['金', '木', '水', '火', '土']
    total1 = sum(ws1.get(e, 0) for e in all_elements) or 1
    total2 = sum(ws2.get(e, 0) for e in all_elements) or 1
    wuxing_compare = {}
    for e in all_elements:
        pct1 = round(ws1.get(e, 0) / total1 * 100, 1)
        pct2 = round(ws2.get(e, 0) / total2 * 100, 1)
        wuxing_compare[e] = {'chart1_pct': pct1, 'chart2_pct': pct2, 'diff': round(pct1 - pct2, 1)}
```

改为：

```python
    ws1 = chart1.get('wuxing_stats', {})
    ws2 = chart2.get('wuxing_stats', {})
    # wuxing_stats 产出 pinyin 键（calculate_wuxing_stats）——按键名映射对齐
    pinyin_elements = [('jin', '金'), ('mu', '木'), ('shui', '水'), ('huo', '火'), ('tu', '土')]
    total1 = sum(ws1.get(k, 0) for k, _ in pinyin_elements) or 1
    total2 = sum(ws2.get(k, 0) for k, _ in pinyin_elements) or 1
    wuxing_compare = {}
    for k, e in pinyin_elements:
        pct1 = round(ws1.get(k, 0) / total1 * 100, 1)
        pct2 = round(ws2.get(k, 0) / total2 * 100, 1)
        wuxing_compare[e] = {'chart1_pct': pct1, 'chart2_pct': pct2, 'diff': round(pct1 - pct2, 1)}
```

- [ ] **Step 5: 跑 compare 组转绿 + 全文件回归**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_derived.py -q`
Expected: 全绿

- [ ] **Step 6: Commit（独立提交，确认后）**

```bash
git add bazi_calculator.py
git commit -m "fix: read pinyin wuxing keys in compare_charts percentage calculation"
```

---

### Task 12: 紫微结构测试

**Files:**
- Create: `tests/test_bazi_calculator_ziwei.py`

**导入纪律（同 Task 5）**：本文件此刻**只导入 `pytest` 与 `bazi_calculator`**；快照 import 与 `test_ziwei_snapshot` 统一在 Task 13 追加。

- [ ] **Step 1: 写测试文件（仅结构测试，无快照 import）**

```python
"""紫微结构测试（calculate_ziwei 为仓库内纯 Python 实现，无 iztro 运行时依赖）。

快照测试由 Task 13 追加（依赖届时创建的 bazi_snapshot_helper）。
"""
import pytest

import bazi_calculator as bc

MAIN_STARS = {'紫微', '天机', '太阳', '武曲', '天同', '廉贞', '天府',
              '太阴', '贪狼', '巨门', '天相', '天梁', '七杀', '破军'}


def test_gong_positions():
    zw = bc.calculate_ziwei(1993, 7, 15, 14, 'male')
    assert zw['minggong'] in bc.DIZHI      # 已实证：亥
    assert zw['shengong'] in bc.DIZHI      # 已实证：丑
    assert '局' in zw['wuxing_ju']         # 已实证：含"水二局"


def test_twelve_palaces():
    zw = bc.calculate_ziwei(1993, 7, 15, 14, 'male')
    assert len(zw['palaces']) == 12
    for _name, p in zw['palaces'].items():
        assert p['zhi'] in bc.DIZHI
        assert p['gan'] in bc.TIANGAN
        assert set(p) >= {'stars', 'aux_stars', 'daxian'}


def test_14_main_stars_deployed():
    zw = bc.calculate_ziwei(1993, 7, 15, 14, 'male')
    deployed = {s['name'] for p in zw['palaces'].values() for s in p['stars']}
    assert MAIN_STARS <= deployed


def test_ziwei_position():
    # 特征化锁定当前算法输出（已实证：水二局 + 农历十五 → 10）
    assert bc.ziwei_position('水二局', 15) == 10
    for ju in ['水二局', '木三局', '金四局', '土五局', '火六局']:
        for day in [1, 15, 30]:
            pos = bc.ziwei_position(ju, day)
            assert isinstance(pos, int)
```

- [ ] **Step 2: 跑结构测试**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_ziwei.py -v`
Expected: 4 passed

- [ ] **Step 3: Commit（确认后）**

```bash
git add tests/test_bazi_calculator_ziwei.py
git commit -m "test: add ziwei structural tests"
```

---

### Task 13: 快照基建 + e2e/shensha/ziwei 快照

**Files:**
- Create: `tests/bazi_snapshot_helper.py`
- Create: `tests/fixtures/bazi_calculator_snapshots/regenerate.py`
- Create: `tests/test_bazi_calculator_e2e.py`
- Modify: `tests/test_bazi_calculator_shensha.py`（顶部加 import、末尾加快照测试）
- Modify: `tests/test_bazi_calculator_ziwei.py`（顶部加 import、末尾加快照测试）
- Generate: `tests/fixtures/bazi_calculator_snapshots/*.json`（9 份）

- [ ] **Step 1: 写快照辅助模块**

```python
"""bazi_calculator 快照测试辅助：用例定义、时变字段剥离、农历后端冻结、快照读写与字段级 diff。

快照 = 冻结现状防回归（characterization），基线由 regenerate.py 手动生成，
变更引擎后人工 review diff 再提交（spec §5）。
"""
import copy
import json
from pathlib import Path

import bazi_calculator as bc
import lunar_calendar

SNAPSHOT_DIR = Path(__file__).parent / 'fixtures' / 'bazi_calculator_snapshots'

SNAPSHOT_CASES = [
    {'name': 'male_1993',   'year': 1993, 'month': 7,  'day': 15, 'hour': 14, 'minute': 0,  'gender': 'male',   'location': 'Beijing', 'use_solar_time': False},
    {'name': 'female_1988', 'year': 1988, 'month': 2,  'day': 20, 'hour': 10, 'minute': 0,  'gender': 'female', 'location': 'Beijing', 'use_solar_time': False},
    {'name': 'solar_my',    'year': 2000, 'month': 1,  'day': 15, 'hour': 8,  'minute': 12, 'gender': 'male',   'location': '马来西亚', 'use_solar_time': True},
    {'name': 'zi_hour',     'year': 1990, 'month': 5,  'day': 10, 'hour': 23, 'minute': 30, 'gender': 'male',   'location': 'Beijing', 'use_solar_time': False},
    {'name': 'female_2000', 'year': 2000, 'month': 12, 'day': 31, 'hour': 8,  'minute': 0,  'gender': 'female', 'location': 'Beijing', 'use_solar_time': False},
]


def freeze_lunar_backend(monkeypatch):
    """强制内置农历后端，快照跨机器不漂移（lunar_calendar.py:46 导入时探测 iztro）。"""
    monkeypatch.setattr(lunar_calendar, '_IZTRO_PYTHON', None)


def strip_volatile(chart):
    """剥离随运行日期变化的字段（spec §5）：liu_nian + 大运当前标记。"""
    c = copy.deepcopy(chart)
    c.pop('liu_nian', None)
    if isinstance(c.get('dayun_summary'), dict):
        c['dayun_summary'].pop('current_pillar', None)
    for p in c.get('da_yun') or []:
        p.pop('is_current', None)
    return c


def compute_e2e(case):
    chart = bc.compute_chart(case['year'], case['month'], case['day'], case['hour'],
                             case['minute'], case['gender'], case['location'], case['use_solar_time'])
    return strip_volatile(chart)


def compute_shensha(case):
    fp = bc.calculate_four_pillars(case['year'], case['month'], case['day'],
                                   case['hour'], case['minute'], case['location'])
    return bc.enhance_shensha(bc.calculate_shensha(fp, fp['day_master']))


def compute_ziwei(case):
    return bc.calculate_ziwei(case['year'], case['month'], case['day'], case['hour'], case['gender'])


def save_snapshot(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {'_meta': {'lunar_backend': 'builtin',
                         'generator': 'tests/fixtures/bazi_calculator_snapshots/regenerate.py'},
               'data': data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def load_snapshot(path):
    return json.loads(path.read_text(encoding='utf-8'))['data']


def assert_snapshot_equal(expected, actual, path=''):
    """规范化后的字段级 diff 断言。"""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in sorted(set(expected) | set(actual)):
            assert k in expected, f'{path}/{k}: 实际输出多出键'
            assert k in actual, f'{path}/{k}: 实际输出缺少键（期望 {expected[k]!r}）'
            assert_snapshot_equal(expected[k], actual[k], f'{path}/{k}')
    elif isinstance(expected, list) and isinstance(actual, list):
        assert len(expected) == len(actual), f'{path}: 长度 {len(expected)} != {len(actual)}'
        for i, (e, a) in enumerate(zip(expected, actual)):
            assert_snapshot_equal(e, a, f'{path}[{i}]')
    else:
        assert expected == actual, f'{path}: 期望 {expected!r}，实际 {actual!r}'
```

- [ ] **Step 2: 写再生成脚本（三层 sys.path 上溯到仓库根）**

```python
"""手动再生成全部快照基线。变更引擎后运行，并人工 review diff 再提交（spec §5）。"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))                     # tests/fixtures/bazi_calculator_snapshots/
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))       # 仓库根（三层上溯）
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))            # tests/

import lunar_calendar  # noqa: E402
lunar_calendar._IZTRO_PYTHON = None  # 固定内置后端（spec §5）

try:
    from bazi_snapshot_helper import (  # noqa: E402
        SNAPSHOT_CASES, SNAPSHOT_DIR, compute_e2e, compute_shensha, compute_ziwei, save_snapshot,
    )
except ImportError as e:
    raise SystemExit(f"导入 bazi_snapshot_helper 失败：请从仓库根目录运行本脚本（{e}）")


def main():
    for case in SNAPSHOT_CASES:
        save_snapshot(SNAPSHOT_DIR / f"e2e_{case['name']}.json", compute_e2e(case))
    for case in SNAPSHOT_CASES[:3]:
        save_snapshot(SNAPSHOT_DIR / f"shensha_{case['name']}.json", compute_shensha(case))
    save_snapshot(SNAPSHOT_DIR / f"ziwei_{SNAPSHOT_CASES[0]['name']}.json", compute_ziwei(SNAPSHOT_CASES[0]))
    print(f"regenerated 9 snapshots in {SNAPSHOT_DIR}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: 写 e2e 测试文件（use_solar_time 语义已实测修正）**

```python
"""compute_chart 端到端：22 键 schema + 5 盘快照 + 时变字段结构断言 + solar_time 开关。"""
from datetime import date

import pytest

import bazi_calculator as bc
from bazi_snapshot_helper import (
    SNAPSHOT_CASES, SNAPSHOT_DIR,
    assert_snapshot_equal, compute_e2e, freeze_lunar_backend, load_snapshot,
)

EXPECTED_TOP_KEYS = {
    'status', 'four_pillars', 'dayun_summary', 'day_master', 'wuxing_stats', 'shishen_stats',
    'shensha', 'tai_yuan', 'ming_gong', 'shen_gong', 'da_yun', 'liu_nian', 'ziwei',
    'wuyun_liuqi', 'branch_relations', 'rizhu_zihe', 'nayin_wuxing', 'changsheng',
    'precision_note', 'solar_time', 'birth_info', 'true_solar_info',
}


def test_compute_chart_schema_22_keys():
    chart = bc.compute_chart(1993, 7, 15, 14, 0, 'male', 'Beijing', False)  # 显式传参
    assert set(chart.keys()) == EXPECTED_TOP_KEYS


@pytest.mark.parametrize('case', SNAPSHOT_CASES, ids=lambda c: c['name'])
def test_e2e_snapshot(case, monkeypatch):
    freeze_lunar_backend(monkeypatch)
    actual = compute_e2e(case)
    expected = load_snapshot(SNAPSHOT_DIR / f"e2e_{case['name']}.json")
    assert_snapshot_equal(expected, actual)


def test_liunian_structure():
    # 时变字段改用结构断言（spec §5）：3 条、年份依次 [当年,+1,+2]、含干支/十神
    chart = bc.compute_chart(1993, 7, 15, 14, 0, 'male', 'Beijing', False)
    ln = chart['liu_nian']
    assert len(ln) == 3
    assert [e['year'] for e in ln] == [date.today().year + i for i in range(3)]
    for e in ln:
        assert set(e) >= {'year', 'gan', 'zhi', 'shi_shen'}
        assert e['gan'] in bc.TIANGAN and e['zhi'] in bc.DIZHI


def test_dayun_current_structure():
    chart = bc.compute_chart(1993, 7, 15, 14, 0, 'male', 'Beijing', False)
    currents = [p for p in chart['da_yun'] if p.get('is_current')]
    assert len(currents) <= 1
    cp = chart['dayun_summary'].get('current_pillar')
    if currents:
        assert cp and cp['gan'] == currents[0]['gan'] and cp['zhi'] == currents[0]['zhi']
    # 起运前 current_pillar 为 None 亦合法


def test_use_solar_time_flag_controls_auto_correction():
    # 实测语义（bazi_calculator.py:2110-2114）：
    #   use_solar_time=False → 自动调用 calculate_true_solar_time 经度校正（马来西亚 8:12→6:50，辰时→卯时）
    #   use_solar_time=True  → 输入视为已校正（user_adjusted），保持原辰时
    corrected = bc.compute_chart(2000, 1, 15, 8, 12, 'male', '马来西亚', False)
    pre_adjusted = bc.compute_chart(2000, 1, 15, 8, 12, 'male', '马来西亚', True)
    assert corrected['true_solar_info']['method'] == 'longitude_correction'
    assert pre_adjusted['true_solar_info']['method'] == 'user_adjusted'
    assert corrected['four_pillars']['hour']['zhi'] == '卯'
    assert pre_adjusted['four_pillars']['hour']['zhi'] == '辰'
```

- [ ] **Step 4: 向 shensha 文件追加快照 import 与测试**

在 `tests/test_bazi_calculator_shensha.py` 顶部 `import bazi_calculator as bc` 之后追加：

```python
from bazi_snapshot_helper import (
    SNAPSHOT_CASES, SNAPSHOT_DIR,
    assert_snapshot_equal, compute_shensha, freeze_lunar_backend, load_snapshot,
)
```

在该文件末尾追加：

```python
# ── 快照（引擎修复后生成基线）──

@pytest.mark.parametrize('case', SNAPSHOT_CASES[:3], ids=lambda c: c['name'])
def test_shensha_snapshot(case, monkeypatch):
    freeze_lunar_backend(monkeypatch)
    actual = compute_shensha(case)
    expected = load_snapshot(SNAPSHOT_DIR / f"shensha_{case['name']}.json")
    assert_snapshot_equal(expected, actual)
```

- [ ] **Step 5: 向 ziwei 文件追加快照 import 与测试**

在 `tests/test_bazi_calculator_ziwei.py` 顶部 `import bazi_calculator as bc` 之后追加：

```python
from bazi_snapshot_helper import (
    SNAPSHOT_CASES, SNAPSHOT_DIR,
    assert_snapshot_equal, compute_ziwei, freeze_lunar_backend, load_snapshot,
)
```

在该文件末尾追加：

```python
def test_ziwei_snapshot(monkeypatch):
    freeze_lunar_backend(monkeypatch)
    case = SNAPSHOT_CASES[0]
    actual = compute_ziwei(case)
    expected = load_snapshot(SNAPSHOT_DIR / f"ziwei_{case['name']}.json")
    assert_snapshot_equal(expected, actual)
```

- [ ] **Step 6: 生成基线**

Run: `G:/project/agent/.venv/Scripts/python tests/fixtures/bazi_calculator_snapshots/regenerate.py`
Expected: `regenerated 9 snapshots in ...`

**人工 review**：`git status` + 抽查 1 份基线（如 `e2e_male_1993.json`）确认 `_meta.lunar_backend == "builtin"`、无 `liu_nian` 键、`da_yun` 各柱无 `is_current`、`changsheng` 字段为 Task 10 新表输出。

- [ ] **Step 7: 全部快照测试转绿**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_e2e.py tests/test_bazi_calculator_ziwei.py tests/test_bazi_calculator_shensha.py -q`
Expected: 全绿（含 9 个快照用例）

- [ ] **Step 8: Commit（确认后）**

```bash
git add tests/bazi_snapshot_helper.py tests/test_bazi_calculator_e2e.py tests/fixtures/bazi_calculator_snapshots/ tests/test_bazi_calculator_shensha.py tests/test_bazi_calculator_ziwei.py
git commit -m "test: add snapshot infrastructure and e2e/shensha/ziwei baselines"
```

---

### Task 14: 全量验证 + 缺陷记录

**Files:**
- Create: `docs/BAZI_CALCULATOR_ENGINE_DEFECTS_2026-07-17.md`

- [ ] **Step 1: 新套件整体验收（spec §7.1）**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_pillars.py tests/test_bazi_calculator_dayun.py tests/test_bazi_calculator_shensha.py tests/test_bazi_calculator_ziwei.py tests/test_bazi_calculator_derived.py tests/test_bazi_calculator_e2e.py tests/test_accuracy.py -q`
Expected: 全绿，总耗时 < 60s

- [ ] **Step 2: 全量回归对照基线（spec §7.2）**

Run: `G:/project/agent/.venv/Scripts/python -m pytest tests/ -q`
Expected: 与 Task 1 Step 1 基线相比**无新增失败**（通过数应增加本套件用例数）；并确认 `git status --short -- tests/accuracy_report.json` 无输出（备份恢复生效）

- [ ] **Step 3: 覆盖矩阵核对（spec §7.3）**

逐行对照 spec 附录 A 的 27 行矩阵，确认每行都有对应测试且通过。在执行总结中列出勾选结果。

- [ ] **Step 4: 写缺陷记录**

创建 `docs/BAZI_CALCULATOR_ENGINE_DEFECTS_2026-07-17.md`，模板：

```markdown
# bazi_calculator 引擎缺陷记录（测试套件建设中发现）

> 日期： 2026-07-17 | 关联： docs/superpowers/specs/2026-07-17-bazi-calculator-test-suite-design.md

## 缺陷 #1：三合系神煞取组错误（已修复）
- 现象： calculate_shensha 以候选支自身定三合局（:944），桃花/驿马/劫煞/灾煞/亡神/紫微/三合禄 永不命中，华盖/将星 凡含目标支必误中
- 证据： <粘贴 Task 6 Step 2 的红色输出摘要；构造盘 申年+酉月 桃花不命中>
- 修复： 以年支/日支所属三合局并集为参考（紫微仅日支），独立提交 <commit-hash>
- 生产影响： shensha 字段变化（7 类新增、2 类按规则收敛）

## 缺陷 #2：日柱系神煞位置限制缺失（已修复）
- 现象： 魁罡/孤鸾煞/阴差阳错/十恶大败/八专/悬针/天赦 在年/月/时柱误报（:996-1003 无 key=='day' 限制）
- 证据： <Task 8 Step 2 红色输出摘要；庚辰年柱误报魁罡实测>
- 修复： 判定块加 key=='day' 限制，独立提交 <commit-hash>
- 遗留： 天赦未按季节区分（春戊寅/夏甲午/秋戊申/冬甲子），待命理复核

## 缺陷 #3：compare_charts 五行键名不匹配（已修复）
- 现象： 按中文键读 pinyin 键（:2174-2183），五行占比恒 0.0
- 证据： <Task 11 Step 2 红色输出摘要>
- 修复： 键名映射对齐，独立提交 <commit-hash>

## 缺陷 #4：十二长生表与教科书/自身注释矛盾（已修复）
- 现象： CHANGSHENG_TABLE 各行数据与注释矛盾（注释"甲:亥..."数据首元素为戌）；实测 get_changsheng('甲','亥')=='养'，教科书"甲长生在亥"
- 决策： 用户 2026-07-17 在 Kimi Code 会话中经结构化问答（AskUserQuestion）明确选择路径 A
- 证据： <Task 9 Step 2 红色输出摘要>
- 修复： 整体替换为教科书阳顺阴逆表，独立提交 <commit-hash>
- 生产影响： changsheng 与 day_master.shier_changsheng 输出变化

## 待命理复核口径（非本轮修复）
- 紫微神煞仅日支（源码注释"日支三合查"，暂定工程口径）
- 三合禄年/日支并集（外部依据弱，暂定工程口径）
- 天赦季节细化
```

- [ ] **Step 4b: 回填 commit hash**

提交前检查：缺陷记录中所有 `<commit-hash>` 占位符已替换为实际提交哈希（`git log --oneline` 查取）。**含占位符的文档不得提交。**

- [ ] **Step 5: Commit（确认后）**

```bash
git add docs/BAZI_CALCULATOR_ENGINE_DEFECTS_2026-07-17.md
git commit -m "docs: record bazi_calculator engine defects found by test suite"
```

- [ ] **Step 6: 合并回主分支（用户决策，不在本计划内自动执行）**

向用户报告 worktree 分支 `codex/bazi-calculator-test-suite` 的全部提交与验证结果，由用户决定合并方式（merge / rebase / 先评审）。

---

## Self-Review 结果（计划落盘前已执行；含四轮审核修订核对）

**1. Spec 覆盖**：spec §4.1→Task 2/3；§4.2→Task 4（四方向+10 步+柱数=10）；§4.3 A→Task 5、B→Task 6/7、C→Task 8、D/E→Task 13/14；§4.4→Task 12；§4.5→Task 9/10/11（含 format_to_spec 直接调用）；§4.6→Task 13；§4.7→Task 1；§5→Task 13；§7→Task 14；§8→Task 6-11（红色证据→独立提交→review→全绿，四例缺陷同流程）；附录 A→Task 14 Step 3 核对。**无遗漏。**

**2. 占位符扫描**：所有测试步骤含完整可运行代码；所有期望值经本机实测或读码验证；缺陷记录模板占位由 Task 14 Step 4b 显式回填；无 TBD/TODO。

**3. 类型一致性**：`mk_fp`/`_ganzhi_for`（Task 5 定义）在 Task 6/8 复用一致；`NEUTRAL_FP`（Task 8 定义）自洽；`PINYIN_ELEMENTS`（Task 9 定义）在 Task 11 复用一致；`FORMAT_SPEC_KEYS`（Task 9 定义）与 e2e `EXPECTED_TOP_KEYS`（Task 13 定义）为 20/22 键互补关系；`SNAPSHOT_CASES`/`freeze_lunar_backend`/`compute_*`/`load_snapshot`/`assert_snapshot_equal`（Task 13 定义）在 Task 13 各 Step 引用一致；`SOLAR_TERMS_PATH`（Task 2 定义）在 Task 3 复用一致。

**4. 顺序依赖**：`bazi_snapshot_helper` 在 Task 13 创建，Task 5/12 的文件均不提前 import；快照基线在 4 例引擎修复全部完成后的 Task 13 Step 6 生成；Task 0 隔离环境（含三份未跟踪文档迁移）是所有任务的前置。

**5. 四轮审核修订核对**：第二轮 12 项 → 见各 Task 标注；第三轮 7 项（Task 0 隔离/helper 导入推迟/solar_time 语义/大运补全/format_to_spec 直调/长生路径 A/去 tail）→ 同上；第四轮 5 项——绝对解释器路径 → 全部 Run 命令；未跟踪文档迁移 + `codex/` 分支 → Task 0 Step 3/4/2；路径 A 决策书面化 + 执行前复述确认 → Task 10 决策依据段（spec §2/§8 同步登记）；accuracy_report.json 备份恢复 → Task 1 Step 2/3/4 与 Task 14 Step 2；git 检查拆分为独立命令 + 文件系统授权提示 → Task 0 Step 1/2。**24 项全部落入。**
