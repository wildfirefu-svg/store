# Task 6 红色证据：缺陷 #1 三合系取组

- 日期：2026-07-18
- 分支：`codex/bazi-calculator-test-suite`（worktree `G:/project/agent-bazi-test-suite`）
- 缺陷：`bazi_calculator.py:944` `group = _find_taohua_group(zhi)` —— `calculate_shensha` 以**候选支自身**定三合局，未按教科书规则以年支/日支为参考支定局。
- 本任务只追加测试与记录证据，**未改动任何引擎代码**（修复属 Task 7）。

## 运行命令与总计数

```
$ G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_shensha.py -v -k "sanhe"
=========== 56 failed, 24 passed, 4 skipped, 4 deselected in 0.71s ============
```

A 组回归（Task 5 既有测试，应保持绿）：

```
$ G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_shensha.py -v -k "tianyi or wenchang or yangren or enhance"
====================== 4 passed, 84 deselected in 0.34s =======================
```

## 失败分布（按测试名 × 神煞）

| 测试 | 失败神煞 | 失败数 | 通过/跳过 |
|---|---|---|---|
| `test_sanhe_by_year_branch`（36 例） | 桃花、驿马、劫煞、灾煞、亡神、三合禄 × 4 局 | 24 | 华盖、将星 × 4 局 PASSED（8）；紫微 × 4 局 SKIPPED |
| `test_sanhe_by_day_branch`（36 例） | 桃花、驿马、劫煞、灾煞、亡神、紫微、三合禄 × 4 局 | 28 | 华盖、将星 × 4 局 PASSED（8） |
| `test_sanhe_negative`（9 例） | 华盖、将星（反例误命中） | 2 | 其余 7 例 PASSED |
| `test_sanhe_negative_ziwei_year_only` | — | 0 | PASSED |
| `test_sanhe_merge_year_and_day` | 并集合并不生效（桃花不命中） | 1 | — |
| `test_sanhe_no_duplicate` | 桃花完全未命中（count 0 ≠ 1） | 1 | — |

合计 **56 failed / 24 passed / 4 skipped**。与预期一致：桃花/驿马/劫煞/灾煞/亡神/紫微/三合禄在 by_year/by_day 正例不命中；华盖/将星在 negative 反例误命中（这两煞的目标支恰为局内成员，候选支自身定局在正例上偶然命中、反例上必然误命中）。

## 代表性断言信息（原样摘录）

正例不命中（by_year，桃花）：

```
>       assert name in ss['hour'], f'年支{group[0]}属{"".join(group)}局，时支{target}应命中{name}'
E       AssertionError: 年支申属申子辰局，时支酉应命中桃花
E       assert '桃花' in ['流霞', '飞刃', '将星']
tests\test_bazi_calculator_shensha.py:76: AssertionError
```

正例不命中（by_year，驿马）：

```
E       AssertionError: 年支申属申子辰局，时支寅应命中驿马
E       assert '驿马' in ['禄神', '词馆']
tests\test_bazi_calculator_shensha.py:76: AssertionError
```

反例误命中（negative，华盖 / 将星）：

```
E       AssertionError: 年/日支均不属寅午戌局，时支戌不应命中华盖
E       assert '华盖' not in ['国印贵人', '华盖', '寡宿', '吊客', '天罗']
tests\test_bazi_calculator_shensha.py:94: AssertionError

E       AssertionError: 年/日支均不属寅午戌局，时支午不应命中将星
E       assert '将星' not in ['太极贵人', '红艳煞', '将星', '血刃']
tests\test_bazi_calculator_shensha.py:94: AssertionError
```

并集合并不生效（merge）与去重前提不成立（no_duplicate）：

```
>       assert '桃花' in bc.calculate_shensha(fp1, '甲')['hour']
E       AssertionError: assert '桃花' in ['流霞', '飞刃', '将星']
tests\test_bazi_calculator_shensha.py:107: AssertionError

>       assert ss['hour'].count('桃花') == 1
E       AssertionError: assert 0 == 1
E        +  where 0 = ['流霞', '飞刃', '将星'].count
tests\test_bazi_calculator_shensha.py:115: AssertionError
```

## 完整失败清单（pytest short summary 原样）

```
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group0-桃花-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group0-驿马-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group0-劫煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group0-灾煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group0-亡神-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group0-三合禄-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group1-桃花-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group1-驿马-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group1-劫煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group1-灾煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group1-亡神-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group1-三合禄-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group2-桃花-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group2-驿马-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group2-劫煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group2-灾煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group2-亡神-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group2-三合禄-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group3-桃花-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group3-驿马-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group3-劫煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group3-灾煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group3-亡神-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_year_branch[group3-三合禄-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group0-桃花-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group0-驿马-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group0-劫煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group0-灾煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group0-亡神-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group0-紫微-<lambda>-day_only]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group0-三合禄-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group1-桃花-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group1-驿马-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group1-劫煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group1-灾煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group1-亡神-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group1-紫微-<lambda>-day_only]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group1-三合禄-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group2-桃花-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group2-驿马-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group2-劫煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group2-灾煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group2-亡神-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group2-紫微-<lambda>-day_only]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group2-三合禄-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group3-桃花-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group3-驿马-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group3-劫煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group3-灾煞-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group3-亡神-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group3-紫微-<lambda>-day_only]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_by_day_branch[group3-三合禄-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_negative[华盖-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_negative[将星-<lambda>-year_or_day]
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_merge_year_and_day
FAILED tests/test_bazi_calculator_shensha.py::test_sanhe_no_duplicate
```

（注：终端实际输出中参数 id 以 `\uXXXX` 转义形式打印，上表已解码为可读中文；分组：group0=申子辰、group1=寅午戌、group2=巳酉丑、group3=亥卯未。）

## 下一步（Task 7，另一代理）

按教科书规则修复 `calculate_shensha` 三合系取组：以年支/日支（紫微仅日支）定三合局并取并集，目标支命中且同年/日同局不重复计入。修复后本文件 B 部分应整体转绿。


## Task 8 红色证据：缺陷 #2 日柱系位置限制缺失

命令：`python -m pytest tests/test_bazi_calculator_shensha.py -v -k "day_pillar"`

结果：**21 failed, 7 passed, 88 deselected**。7 个正例（干支位于日柱）全部 passed；21 个位置反例（同一干支仅位于年/月/时柱）全部 FAIL——`calculate_shensha` 在四柱循环内无 `key == 'day'` 限制，非日柱命中 7 张日柱系表即误报。

失败清单（逐字）：

```
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[year-魁罡-庚辰]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[year-孤鸾煞-甲寅]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[year-阴差阳错-丙子]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[year-十恶大败-甲辰]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[year-八专-丁未]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[year-悬针-甲午]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[year-天赦-戊寅]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[month-魁罡-庚辰]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[month-孤鸾煞-甲寅]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[month-阴差阳错-丙子]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[month-十恶大败-甲辰]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[month-八专-丁未]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[month-悬针-甲午]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[month-天赦-戊寅]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[hour-魁罡-庚辰]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[hour-孤鸾煞-甲寅]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[hour-阴差阳错-丙子]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[hour-十恶大败-甲辰]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[hour-八专-丁未]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[hour-悬针-甲午]
FAILED tests/test_bazi_calculator_shensha.py::test_day_pillar_position_negative[hour-天赦-戊寅]
```

（注：同前，终端实际输出中参数 id 以 `\uXXXX` 转义形式打印，上表已解码为可读中文；7 张日柱系表为魁罡/孤鸾煞/阴差阳错/十恶大败/八专/悬针/天赦，源码注释口径均为"日柱为"。）

## 下一步（Task 8 后半，同代理）

最小修复：`bazi_calculator.py` 日柱系判定块整体包入 `if key == 'day':`。不改 7 张表内容、不碰其他神煞逻辑、不做天赦季节细化。修复后本文件 C 部分应转绿且 A/B 无回归。

## Task 9 红色证据：缺陷 #4 十二长生表

来源：`tests/test_bazi_calculator_derived.py::test_changsheng_textbook`（10 组教科书五行长生断言，阳顺阴逆），
运行 `G:/project/agent/.venv/Scripts/python -m pytest tests/test_bazi_calculator_derived.py -v`。

### 测试结果汇总

- 总计 22 项：11 passed / 11 failed
- 10 组 changsheng 参数化断言**全部 FAILED**（预期红色证据，Task 10 修复引擎后转绿）
- 另有 `test_gong_positions_legal` FAILED（TypeError，与 changsheng 无关，见文末备注）

### changsheng 10 组 (gan, zhi) 实际返回值

教科书期望全部为 `长生`；逐一调用 `bc.get_changsheng(gan, zhi)` 实测：

| (gan, zhi) | 期望 | 实际返回 |
|---|---|---|
| 甲亥 | 长生 | 养 |
| 乙午 | 长生 | 冠带 |
| 丙寅 | 长生 | 墓 |
| 戊寅 | 长生 | 墓 |
| 庚巳 | 长生 | 绝 |
| 辛子 | 长生 | 胎 |
| 壬申 | 长生 | 绝 |
| 癸卯 | 长生 | 胎 |
| 丁酉 | 长生 | 绝 |
| 己酉 | 长生 | 绝 |

### pytest -v 失败输出（节选，原样）

```
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[甲-亥] - AssertionError: assert '养' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[乙-午] - AssertionError: assert '冠带' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[丙-寅] - AssertionError: assert '墓' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[戊-寅] - AssertionError: assert '墓' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[庚-巳] - AssertionError: assert '绝' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[辛-子] - AssertionError: assert '胎' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[壬-申] - AssertionError: assert '绝' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[癸-卯] - AssertionError: assert '胎' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[丁-酉] - AssertionError: assert '绝' == '长生'
FAILED tests/test_bazi_calculator_derived.py::test_changsheng_textbook[己-酉] - AssertionError: assert '绝' == '长生'
```

（注：终端原始输出中参数 id 以 `\uXXXX` 转义形式打印，上表已解码为可读中文。）

### 备注：changsheng 之外的失败（按要求未改测试，原样记录）

`test_gong_positions_legal` FAILED：

```
    ty = bc.get_taiyuan(fp['month']['gan'], fp['month']['zhi'], fp['year']['gan'], fp['year']['zhi'])
>   assert ty['gan'] in bc.TIANGAN and ty['zhi'] in bc.DIZHI
E   TypeError: tuple indices must be integers or slices, not str
```

原因：`bc.get_taiyuan` 返回 `tuple`（实测 `('戊', '戌')`），测试按 dict 访问 `ty['gan']`。
按任务约定测试未修改，留待 Task 10 决定修测试还是修引擎返回类型。

---

## Task 11 红色证据：缺陷 #3 compare_charts 五行键名不匹配

命令：`pytest tests/test_bazi_calculator_derived.py -v -k "compare"`

预期与实测一致：`pct_sums_100` / `nonzero` / `matches_input` 三个数值断言 FAIL（占比恒 0.0），`structure` 与 `zero_diff` passed。原始输出：

```
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0 -- G:\project\agent\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: G:\project\agent-bazi-test-suite
configfile: pytest.ini
plugins: anyio-4.14.2, timeout-2.4.0
collecting ... collected 27 items / 22 deselected / 5 selected

tests/test_bazi_calculator_derived.py::test_compare_structure PASSED     [ 20%]
tests/test_bazi_calculator_derived.py::test_compare_wuxing_pct_sums_100 FAILED [ 40%]
tests/test_bazi_calculator_derived.py::test_compare_wuxing_nonzero FAILED [ 60%]
tests/test_bazi_calculator_derived.py::test_compare_wuxing_matches_input FAILED [ 80%]
tests/test_bazi_calculator_derived.py::test_compare_identical_charts_zero_diff PASSED [100%]

================================== FAILURES ===================================
______________________ test_compare_wuxing_pct_sums_100 _______________________

    def test_compare_wuxing_pct_sums_100():
        cc = bc.compare_charts(*_two_charts())
        for side in ['chart1_pct', 'chart2_pct']:
            total = sum(v[side] for v in cc['wuxing_compare'].values())
>           assert abs(total - 100) <= 0.6, f'{side} 总和 {total}（修复前恒为 0）'
E           AssertionError: chart1_pct 总和 0.0（修复前恒为 0）
E           assert 100.0 <= 0.6
E            +  where 100.0 = abs((0.0 - 100))

tests\test_bazi_calculator_derived.py:162: AssertionError
_________________________ test_compare_wuxing_nonzero _________________________

    def test_compare_wuxing_nonzero():
        cc = bc.compare_charts(*_two_charts())
>       assert any(v['chart1_pct'] > 0 for v in cc['wuxing_compare'].values())
E       assert False
E        +  where False = any(<generator object test_compare_wuxing_nonzero.<locals>.<genexpr> at 0x000001FEF5014D40>)

tests\test_bazi_calculator_derived.py:167: AssertionError
______________________ test_compare_wuxing_matches_input ______________________

    def test_compare_wuxing_matches_input():
        c1, _ = _two_charts()
        cc = bc.compare_charts(*_two_charts())
        ws = c1['wuxing_stats']
        total = sum(ws[k] for k, _ in PINYIN_ELEMENTS)
        for k, e in PINYIN_ELEMENTS:
>           assert cc['wuxing_compare'][e]['chart1_pct'] == round(ws[k] / total * 100, 1)
E           assert 0.0 == 25.0
E            +  where 25.0 = round(((2 / 8) * 100), 1)

tests\test_bazi_calculator_derived.py:176: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_bazi_calculator_derived.py::test_compare_wuxing_pct_sums_100
FAILED tests/test_bazi_calculator_derived.py::test_compare_wuxing_nonzero - a...
FAILED tests/test_bazi_calculator_derived.py::test_compare_wuxing_matches_input
================= 3 failed, 2 passed, 22 deselected in 3.75s ==================
```

根因：`compare_charts` 按中文键 `金/木/水/火/土` 读 `wuxing_stats`，而 `calculate_wuxing_stats` 产出 pinyin 键 `jin/mu/shui/huo/tu`，`ws.get(e, 0)` 全部落空，占比恒 0.0。
