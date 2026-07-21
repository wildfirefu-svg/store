# bazi_calculator 测试套件实施方案 — 审核报告

**审核日期**：2026-07-18
**审核文档**：`docs/superpowers/plans/2026-07-17-bazi-calculator-test-suite.md`
**关联设计文档**：`docs/superpowers/specs/2026-07-17-bazi-calculator-test-suite-design.md`（四轮审核修订，已终审放行）
**审核结论**：**有条件批准，存在 5 个必须修复的问题和 7 个建议改进**（已执行两轮深度审计：接口验证 + 逻辑正确性）

**审核轮次**：
- 第一轮（结构审计）：接口签名验证、spec 覆盖追溯、CHANGSHENG_TABLE 缺陷确认、依赖链风险
- 第二轮（逻辑深度审计）：测试断言正确性、修复代码边界情况、遗漏覆盖点、农历后端冻结机制

---

## 一、总体评价

计划质量很高。13 个 Task 严格遵循 spec §8 的"红色证据 → 独立提交最小修复 → review diff → 全绿验收"流程，修复纪律明确。每个 Task 有可运行的代码片段、明确的 pytest 命令和预期输出，没有 TBD 或含糊表述。

Self-Review（§末尾）覆盖了 spec 对齐、占位符扫描、类型一致性和顺序依赖四个维度，达到可执行标准。计划末尾的"执行纪律"中 Git commit 需用户确认、3 例引擎修复独立提交、统一使用 `.venv/Scripts/python` 等约束务实。

以下是经源码级接口验证后的审计发现。

---

## 二、接口对齐验证结果（9/9 通过）

对计划中所有对外接口调用进行了源码签名验证：

| 计划调用 | 实际签名 | 匹配 |
|---|---|---|
| `bc.get_month_pillar(2024, '甲', 2, 20, 0, 0)` | `get_month_pillar(year, year_gan, month, day, hour=0, minute=0)` | 匹配 |
| `bc.get_hour_pillar('甲', 0, 30)` | `get_hour_pillar(day_gan, hour, minute=0)` | 匹配 |
| `bc.calculate_shensha(fp, '甲')` | `calculate_shensha(four_pillars, day_master)` | 匹配 |
| `bc.enhance_shensha(...)` | `enhance_shensha(shensha_dict)` | 匹配 |
| `bc.ziwei_position('水二局', 15)` | `ziwei_position(wuxing_ju, lunar_day)` | 匹配 |
| `bc.compute_chart(1993, 7, 15, 14, 0, 'male')` | `compute_chart(year, month, day, hour=0, minute=0, gender="male", location="Beijing", use_solar_time=False)` | 匹配（依赖默认值） |
| `bc.compare_charts(c1, c2)` | `compare_charts(chart1, chart2)` | 匹配 |
| `get_year_pillar(2024, 2, 4, 16, 26)` | `get_year_pillar(year, month=1, day=1, hour=0, minute=0)` | 匹配 |
| `get_solar_term_info(2024, 2, 4, 16, 26)` | `get_solar_term_info(year, month, day, hour=0, minute=0)` | 匹配 |

模块级属性验证：`TAOHUA_MAP`、`YIMA_MAP`、`HUAGAI_MAP`（公开 dict）、`_jiangxing`、`_jiesha`、`_zaisha`、`_wangshen`、`_ziwei_ss`、`_sanhelu`（私有 dict）全部存在，键结构为三合局 tuple → 目标支 string。计划正确引用了这些属性。

节气 fixture 数据验证：`2024|立春` = `[2, 4, 16, 27, True]`（分钟级 verified）、`2025|清明` = `[4, 4, 20, 49, True]`（分钟级 verified）、`2024|惊蛰` = `[3, 6, -1, 0, False]`（日期级非 verified）——与计划测试中的 `_verified_term` 解析逻辑一致。

`get_solar_term_info` 的 verified 分钟级行为（:187-193）确认：`verified=True` 且 `len(val) > 4` 时读取 `val[2]`/`val[3]` 做分钟级比较，否则 `term_minutes = -1`。计划的 `test_solar_term_info_modes` 测试正确覆盖了这两种模式。

---

## 三、必须修复的问题（3 项）

### 问题 1：`regenerate.py` 的 sys.path 层级不足以导入 `bazi_calculator`

**位置**：Task 12 Step 2

`regenerate.py` 位于 `tests/fixtures/bazi_calculator_snapshots/regenerate.py`。路径设置：

```python
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # 注释说"仓库根"，实际到 tests/
sys.path.insert(0, os.path.dirname(_HERE))                   # 注释说"tests/"，实际到 tests/fixtures/
```

`os.path.dirname(os.path.dirname(_HERE))` 只上溯两层，到达 `tests/`，而不是仓库根目录。`regenerate.py` 直接 `import lunar_calendar` 和调用 `bc.compute_chart()`（通过 `compute_e2e` → `bazi_snapshot_helper.compute_e2e` → `bc.compute_chart`），均需仓库根目录在 sys.path 中。

虽然执行者从仓库根目录运行脚本时，Python 可能自动把 CWD 加到 sys.path，但这一行为非标准也不可靠。

**修复**：增加第三层 `os.path.dirname()`：

```python
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))  # 仓库根
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))       # tests/
```

---

### 问题 2：Task 7 Step 2 的 sanhe 测试计数自相矛盾

**位置**：Task 7 Step 2 预期输出

计划声明：三合系修复后 `pytest -k "sanhe"` 预期"76 passed + 2 skipped：紫微 by_year 4 例 skip"。以下为逐函数计数：

- `test_sanhe_by_year_branch[case×group]`：9 cases × 4 groups = 36 条。紫微（scope=day_only）在此测试中 skip 4 条（每 group 一例）。32 pass + 4 skip。
- `test_sanhe_by_day_branch[case×group]`：9 × 4 = 36 条。无 skip 条件。36 pass。
- `test_sanhe_negative[case]`：9 条参数化。9 pass。
- `test_sanhe_negative_ziwei_year_only`：1 条。1 pass。
- `test_sanhe_merge_year_and_day`：1 条。1 pass。
- `test_sanhe_no_duplicate`：1 条。1 pass。

**实际应为 80 pass + 4 skip**，而非 76 pass + 2 skip。差异为 pass 差 4、skip 差 2。建议执行者以实际 ran 输出为准，不纠结声明数字。

---

### 问题 3：`test_day_pillar_position_negative` 中对 `fp` 的赋值可能引入隐式依赖

**位置**：Task 8 Step 1

```python
@pytest.mark.parametrize('name, ganzhi', DAY_PILLAR_CASES)
@pytest.mark.parametrize('pos', ['year', 'month', 'hour'])
def test_day_pillar_position_negative(name, ganzhi, pos):
    fp = mk_fp('甲子', '甲子', '甲子', '甲子')
    fp[pos] = {'gan': ganzhi[0], 'zhi': ganzhi[1]}
    assert name not in bc.calculate_shensha(fp, '甲')[pos]
```

每次调用 `mk_fp` 创建新 dict，21 次参数化之间无相互污染。问题是 `fp[pos] = {...}` 把四柱结构中某一柱替换为测试干支，但其余三柱保持为 '甲子'——这意味着年/月/时柱（未被替换的两柱）的天干均为 '甲'。如果 `calculate_shensha` 内部有任何逻辑依赖未被替换柱的天干，则反例结果可能被干扰。

当前日柱系判定纯以 `gan+zhi in TABLE` 做表匹配，不涉及其他柱，因此此处无实际风险。但代码可读性不佳——读者需要推理"甲子"在所有位置是否产生碰撞。建议将各柱设为互不相同的干支（如 年=甲子、月=乙丑、时=丙寅），然后在 docstring 中注明"日柱系仅读本柱干支，其余柱内容不进入判定逻辑"。

---

---

## 四、第二轮深度审计 — 逻辑正确性验证（2026-07-18 补充）

第二轮审计逐 Task 验证了测试断言的语义正确性和修复代码的边界覆盖，发现以下新增问题。

### 问题 4：Task 9 `test_shishen_stats_invariants` 缺少 `strongest` 和 `most_frequent_count` 验证

**位置**：Task 9 Step 1

Spec §4.5 对 `calculate_shishen_stats` 明确列出三项验证点："总数不变量"、"缺失 = 计数 0 集合"、"**最强 = argmax**"。计划当前测试：

```python
def test_shishen_stats_invariants():
    ...
    assert sum(ss['counts'].values()) == expected_total
    assert set(ss['missing']) == {s for s, c in ss['counts'].items() if c == 0}
```

只覆盖了前两项。未验证 `ss['strongest']` 确实是 counts 中计数最多的十神。此外 `most_frequent_count` 字段（`:1373`）也未覆盖——该字段对于"无十神缺失"的常见命盘应有正值。

对比 `test_wuxing_stats_invariants` 完整测试了三项不变量（sum=8 / missing / strongest），shishen 的测试不完整。

**修复**：追加断言：

```python
# 最强 = argmax
assert ss['strongest'] == max(ss['counts'], key=ss['counts'].get)
assert ss['most_frequent_count'] == max(ss['counts'].values())
```

**严重程度**：中等——不影响现有测试的正确性，但导致 `strongest` 字段的回归防护缺失。如果未来有人改了 `calculate_shishen_stats` 的排序逻辑，当前测试不会捕捉到。

---

### 问题 5：Task 7 三合系修复——`sanhe_day_group` 在日支不属于任何三合局时行为正确但隐含假设

**位置**：Task 7 Step 1

修复代码：

```python
sanhe_ref_groups = {g for g in (_find_taohua_group(year_zhi), _find_taohua_group(day_zhi)) if g}
sanhe_day_group = _find_taohua_group(day_zhi)
```

`_find_taohua_group` 对输入的地支如果在四个三合局中任一找不到匹配，返回 `None`。当前 12 地支全部属于已知三合局——申子辰/寅午戌/巳酉丑/亥卯未 全覆盖——因此 `_find_taohua_group` 对任何合法地支输入永不返回 `None`。`sanhe_day_group` 也永不可能是 `None`。

但这是**未文档化的隐含不变式**。如果将来新增地支或三合局定义改变，`_find_taohua_group(x)` 返回 `None` 的情况可能出现。此时的修复代码：

- `sanhe_ref_groups` 的 set comprehension 中 `if g` 过滤了 `None`——正确
- `sanhe_day_group` 没有过滤——如果为 `None`，则 `_ziwei_ss.get(None)` 返回 `None`，紫微判定 `if sanhe_day_group and zhi == None` 因 `sanhe_day_group` 为假值而跳过——行为等价于"紫微不命中"

实际行为正确，但缺乏防御性注释。建议在修复处加一行：

```python
# 12 地支全覆盖三合局，_find_taohua_group 永不返回 None（不变式保证）
```

**严重程度**：低——当前无运行时风险，属代码可维护性改进。

---

### 第二轮验证通过项（无需修改，记录备查）

以下逻辑点经逐行源码核对，确认正确：

**Task 3 节气边界测试**：`_verified_term` 从 `solar_terms.json` 直接读取 fixture（不从 `get_solar_term_info` 获取），避免了循环验证。`test_lichun_year_boundary_minute` 中 `mi - 1` 对 `mi=27` 产生 `mi=26`，无负数边界风险。`test_jingzhe_month_boundary_date_only` 正确断言了 `verified=False` 条目的日期级切换行为。

**Task 4 大运递进**：`_dayun` helper 调用 `calculate_dayun(yp, mp, gender, year, month, day, hour, 0)` 传递 8 参数完全匹配签名 `calculate_dayun(year_pillar, month_pillar, gender, birth_year, birth_month, birth_day, birth_hour=0, birth_minute=0)`。`test_liunian_sequence` 中硬编码年份 2026 的断言（丙午/丁未/戊申）经六十甲子公式验证正确：2026 ≡ 丙午，甲日主见丙=食神/丁=伤官/戊=偏财。

**Task 5 日干系神煞**：`test_tianyi_guiren` 构造盘 `mk_fp('甲子', '乙丑', '甲子', '甲子')`→月支丑→`TIANYI_GUIREN['甲']` 包含 '丑'，判定正确。`test_yangren` 的 `mk_fp('甲子', '丁卯', '甲子', '甲子')`→月支卯→`YANGREN_MAP['甲']` = '卯'，判定正确。`test_enhance_shensha_meaning` 对 `enhance_shensha` 输出的 dict 结构断言（name/position/meaning）与源码 line 1949-1951 完全一致。

**Task 8 日柱系修复**：`if key == 'day':` 守卫覆盖了 7 张表的所有判定路径。原 7 行缩进增加一级，不改变表查逻辑，无副作用。天赦季节细化不在本轮范围（spec §8 非目标）。

**Task 9 统计不变量**：`test_wuxing_stats_invariants` 的 sum=8 断言对应 `calculate_wuxing_stats` 的四干+四支本气计数（line 1306-1317），strongest argmax 断言对应 `ranked[0][0]`（line 1324），语义完全正确。

**Task 9 format_to_spec 20 键断言**：使用 `FORMAT_SPEC_KEYS <= set(chart.keys())`（子集断言），`compute_chart` 额外追加的 `birth_info` 和 `true_solar_info` 不触发失败。Task 12 的 `EXPECTED_TOP_KEYS` 使用 `==` 做完整 22 键校验，两者互补。

**Task 10 compare_charts 修复**：修复代码将 `['金','木','水','火','土']` 替换为 `[('jin','金'),('mu','木'),('shui','水'),('huo','火'),('tu','土')]` 的 pinyin→中文 键名映射，与 `calculate_wuxing_stats` line 1320-1326 的拼音键名产出对齐。`test_compare_wuxing_matches_input` 的重新计算逻辑（`round(ws[k] / total * 100, 1)`）与修复后的 `compare_charts` 代码（`round(ws1.get(k, 0) / total1 * 100, 1)`）一致。

**Task 11 紫微**：`calculate_ziwei(year, month, day, hour, gender)` 使用 `get_year_pillar(year, month, day, hour, 0)` 内部调用（line 1033），minute 固定为 0。`compute_ziwei` helper 只传 5 参数——与签名匹配，不传 minute 是当前引擎行为，快照以特征化方式锁定。

**Task 12 农历后端冻结机制**：`lunar_calendar._IZTRO_PYTHON` 是模块级变量（line 46），每次 `_call_iztro` 调用都重新读取（line 77），不会缓存引用。`regenerate.py` 中 `lunar_calendar._IZTRO_PYTHON = None` 和 `freeze_lunar_backend` 中 `monkeypatch.setattr(lunar_calendar, '_IZTRO_PYTHON', None)` 语义等价，均在 `import` 完成后、首次函数调用前生效。

**Task 12 `compute_e2e`/`compute_shensha` 签名**：`compute_e2e` 传递 8 个参数到 `compute_chart`（全显式 positional），`compute_shensha` 传递 6 个参数到 `calculate_four_pillars`（全显式 positional），均与源码签名精确匹配。

---

## 五、Spec 覆盖追溯（13/13 Task 无遗漏）

| Spec 节 | 对应 Task | 实现方式 |
|---|---|---|
| §4.1 四柱/边界 | Task 2/3 | 金标参数化 + 五虎/五鼠遁 + 十神全表 + 旬空 + 节气 fixture + 子时特征化 |
| §4.2 大运/流年 | Task 4 | 顺逆排方向 + 起运区间 + 六十甲子递进 + 流年序列 |
| §4.3 A 日干系 | Task 5 | 天乙贵人/文昌/羊刃断言 + enhance 结构 |
| §4.3 B 三合系 | Task 6/7 | 9类×4局矩阵（正例/反例/合并/去重）+ 红色证据 → 修复 → 转绿 |
| §4.3 C 日柱系 | Task 8 | 7类正例 + 年月时柱21例反例 + 红色证据 → 加 key=='day' → 转绿 |
| §4.3 D/E 行为变化/快照 | Task 12/13 | 快照重生成 + review diff + 缺陷记录文档 |
| §4.4 紫微 | Task 11 | 命宫/身宫/十二宫/十四主星 + ziwei_position 单测 + 快照 |
| §4.5 衍生计算 | Task 9/10 | 统计不变量 + 支关系 + 宫位 + 长生 + 自合 + 五运六气 + 键名修复 |
| §4.6 e2e | Task 12 | 22键schema + 5盘快照 + 时变字段结构断言 + solar_time开关 |
| §4.7 金标接入 | Task 1 | test_golden_accuracy 包装 + 不改 run_tests |
| §5 快照机制 | Task 12 | 后端冻结 + 时变剥离 + 再生成脚本 + 字段级diff |
| §7 验收标准 | Task 13 | 三步骤验收 + 全量回归 + 覆盖矩阵核对 |
| §8 修复流程 | Task 6-10 | 红色证据 → 独立提交 → review → 全绿（三例缺陷均走此路径） |

---

## 六、源码级审计发现

### CHANGSHENG_TABLE 缺陷确认

计划 Task 9 对 `CHANGSHENG_TABLE`（:616-627）的分析完全正确。当前数据：

```
'甲': [10,9,8,7,6,5,4,3,2,1,0,11]  # 注释：亥...戌
```

DIZHI 索引：子=0, 丑=1, 寅=2, 卯=3, 辰=4, 巳=5, 午=6, 未=7, 申=8, 酉=9, 戌=10, 亥=11。

第一元素 10=戌（而非注释所说的亥=11）。教科书"甲长生在亥"要求首元素为 11。

对乙的验证：`'乙': [4,5,6,7,8,9,10,11,0,1,2,3]`——首元素 4=辰，但教科书"乙长生在午"要求首元素 6。逐行核对后，全表 10 干无一正确。

计划 Task 9 Step 3 提供的修复表（阳顺阴逆教科书规则）经逐干验证正确：甲长生亥（索引11, 0,1,2,3,4,5,6,7,8,9,10）、乙长生午（6,5,4,3,2,1,0,11,10,9,8,7）等全部匹配。

### 三合系修复中 `year_zhi` 的作用域

Task 7 的修复代码使用 `year_zhi` 变量（`_find_taohua_group(year_zhi)`），该变量在 `bazi_calculator.py:934` 已定义（`year_zhi = four_pillars['year']['zhi']`），修复插入在 `:939` 循环之前，作用域正确复用。但修复代码新增的 `day_zhi` 定义（`day_zhi = four_pillars['day']['zhi']`）与现有代码无冲突——当前函数体内未使用该变量名。

### `_ganzhi_for` 的参数设计

```python
def _ganzhi_for(zhi, offset=0):
    return bc.TIANGAN[offset % 10] + zhi
```

`offset=0` 产生"甲zhi"，`offset=1` 产生"乙zhi"。三合系测试仅依赖支柱（zhi）判定，不关心天干——因此任意天干值不影响结果。但如果未来有人把 `_ganzhi_for` 用于天干敏感的神煞测试（如天乙贵人），`offset` 的隐式语义可能导致困惑。建议在测试 helper 上方加注释："天干仅起占位作用，三合系/日柱系神煞不以天干判定"。

---

## 七、依赖链风险

### 快照 helper 的提前引用

Task 5（shensha.py）和 Task 11（ziwei.py）均 import `bazi_snapshot_helper`，但该模块在 Task 12 才创建。计划已注明处理方式：

- Task 5："本任务不跑 pytest，与 Task 6 一起跑"——正确，因为快照测试部分是追加的，A 组手工断言不依赖 helper。
- Task 11："snapshot 用例在 Task 12 基线生成后才会绿"——正确。

但存在一个操作风险：若执行者在 Task 5 提交前运行 `pytest tests/test_bazi_calculator_shensha.py`，会因为 `import bazi_snapshot_helper` 不存在而**收集阶段全红**，即使 A 组测试本身正确。建议在 Task 5 的 import 语句上方添加注释：

```python
# NOTE: bazi_snapshot_helper not created until Task 12.
# Tests above this import (日干系 A) use manual assertions only.
# Snapshot tests appended after Task 12 helper creation.
```

或更简单的做法：将 4 个 snapshot 相关的 import 包裹在 `try/except ImportError` 中，未创建时不阻塞 A/C 组测试。

---

## 八、建议改进（7 项）

### 建议 1：`regenerate.py` 导入更健壮

除了问题 1 的路径层级修复外，建议 `regenerate.py` 也用 `try/except ImportError` 包裹导入并给出友好错误信息，因为该脚本作为手动工具会被不同环境的用户运行。

### 建议 2：Task 9 的 `compute_chart` 调用显式传参

多个 `compute_chart(1993, 7, 15, 14, 0, 'male')` 调用依赖 `location='Beijing'` 和 `use_solar_time=False` 的默认值。在理解上没问题，但若未来 `compute_chart` 的默认值改变（如默认 `use_solar_time=True`），这些测试会静默偏移。建议显式写出全部参数。

### 建议 3：节气 boundary 测试补充 2025 年非 verified 条目的行为验证

计划已覆盖 `2024|立春`（verified）和 `2024|惊蛰`（非 verified）两种模式，但 `test_solar_term_info_modes` 测试中只用了 2024 立春（verified）和 2024 惊蛰（非 verified）。如果 `_load_solar_terms` 返回的条目中 `len(val)` 不足 4（无 verified 字段），实际行为与测试预期可能不同。当前 solar_terms.json 中所有条目均有 5 个字段，无风险。但建议加一条注释说明这是对当前已知数据结构的断言，不是对所有可能形状的保证。

### 建议 4：Task 13 的缺陷记录文档模板中预留 commit hash 占位符

模板中 `<commit-hash>` 需要在实验完成后回填。建议在 Step 4 的 `--` 行增加一个 checklist 子步骤："回填实际 commit hash 并移除 <commit-hash> 占位符"，避免提交含占位符的文档。

### 建议 5：Task 4 `test_starting_age_range` 断言过于宽松

`assert 0 <= dy['starting_age'] <= 10` 仅校验起运岁数在合法区间内。对已知输入（1993-07-15 14:00 male），起运岁数应约为 2.5 岁——当前范围断言即使算法产生 9.9 也能通过。建议针对此已知盘增加更精确的子断言（如 `abs(dy['starting_age'] - 2.5) < 0.3`），同时保留范围断言作为异常值兜底。此改进可将 spec 注释中"已实证 2.5"转化为可验证的断言。

### 建议 6：Task 2/3 节气测试中的 fixture 数据年份与 `solar_terms.json` 已验证条目绑定

`_verified_term` 硬编码了 `2024|立春` 和 `2025|清明` 两个 key。如果这些条目在 `solar_terms.json` 中被修改（如 verified 字段从 True 变为 False，或时分值被更正），测试将因 `assert verified is True` 失败——这正是设计意图（防数据表意外修改）。但建议在 `_verified_term` 的 docstring 中显式说明这一语义："如果此 fixture 失败，可能是因为 solar_terms.json 中对应条目被修改或降级——检查数据表，不是测试的 bug"。

### 建议 7：Task 3 节气测试对 `2024|惊蛰` 的 `verified=False` 行为仅用日期比较

`test_jingzhe_month_boundary_date_only` 断言 `verified=False` 的条目按日期级切换（非分钟级）。但该测试未覆盖"非 verified 条目的时分值是否被正确忽略"——即 `solar_terms.json` 中若某些非 verified 条目的时分值碰巧与分钟级边界重合，引擎是否仍坚持日期级比较。当前测试的 `d-1` vs `d` 断言已覆盖此场景的外部行为，但建议在注释中说明这是日期级行为，不验证内部 `term_minutes = -1` 的实现细节。

---

## 九、设计亮点（无需修改）

1. **Self-Review 机制**：计划末尾的 4 维度自查（spec 覆盖/占位符/类型一致性/顺序依赖）是计划质量的自检闭环，不属于实施步骤，但提供了执行前的交叉验证。

2. **Task 9 决策门设计**：十二长生表修复设为用户二选一决策点（路径 A 修复/路径 B 特征化），明确阻塞后续 Task 执行。这种"停下来问用户"的控制点在自动化实施计划中非常必要。

3. **神煞修复的"先冻结再动手"策略**：Task 6 先补齐 9 类×4 局矩阵的红绿证据，Task 7 才是引擎修复——这确保修复前有完整的 FAIL 记录作为对照基线。

4. **快照机制的三层防御**：农历后端 monkeypatch（防跨机器漂移）+ 时变字段剥离（防跨时间漂移）+ 结构断言替代（防信息丢失）——三个维度各自独立验证，没有单点。

5. **执行纪律的明确性**：Git commit 需用户确认、3 例引擎修复各自独立提交（不夹带重构）、统一使用 `.venv/Scripts/python`——这些约束直接防止了最常见的一类实施事故。

6. **接口签名全部通过源码验证**：9 个对外 API 调用点与源码签名完全匹配，无参数顺序错误或缺失必要参数。

---

## 十、判定汇总

| 类别 | 数量 | 说明 |
|---|---|---|
| 必须修复 | 5 | regenerate.py 路径层级、sanhe 测试计数矛盾、fp 共享变量可读性、shishen_stats 缺 strongest 验证（新增）、三合系 `sanhe_day_group` 隐含不变式缺注释（新增） |
| 接口验证 | 9/9 通过 | 所有 API 调用与源码签名匹配 |
| 逻辑验证 | 16/16 通过 | 第二轮逐 Task 断言语义验证（见第四节"验证通过项"） |
| 建议改进 | 7 | regenerate 导入健壮性、compute_chart 显式传参、节气边界补充注释、缺陷记录占位符清理、dayun 起运岁数精确断言（新增）、fixture 数据表绑定语义说明（新增）、节气非 verified 行为注释（新增） |
| 设计亮点 | 6 | Self-Review、决策门、"先冻结再动手"、三层快照防御、执行纪律、全接口验证 |
| Spec 覆盖 | 13/13 Task | 无遗漏，每个 spec 节均有对应 Task |

**综合结论**：两轮审计确认计划将设计文档意图完整翻译为可执行步骤。5 个必须修复项中，regenerate.py 路径问题（唯一运行时故障点）和 shishen_stats strongest 验证缺失（回归防护缺口）为关键项，其余三项为计数/可读性/注释改进。修复后批准进入实现阶段。

---

## 十一、第三轮审核 — 修订落实情况验证（2026-07-18）

计划于 2026-07-18 修订（见 line 13 审核修订说明），声明"5 个必须修复项 + 7 项建议全部落入"。逐项核对结果如下。

### 必须修复项核验

| # | 问题 | 修订位置 | 状态 |
|---|---|---|---|
| 1 | regenerate.py 路径层级不足 | Task 12 Step 2: `_REPO` 三层上溯（line 1183），注释标注每层含义 | **通过** |
| 2 | sanhe 测试计数自相矛盾 | Task 7 Step 2: 改为"80 passed + 4 skipped"并附逐函数计数说明（line 609） | **通过** |
| 3 | fp 变量可读性（共享 甲子 隐式依赖） | Task 8 Step 1: 引入 `NEUTRAL_FP = ('乙丑', '丙寅', '丁卯', '戊辰')` 各柱干支互异，注释说明日柱系仅读本柱（lines 641-642, 656-657） | **通过** |
| 4 | shishen_stats 缺 strongest 验证 | Task 9 Step 1: 新增 `ss['counts'][ss['strongest']] == max(...)` 和 `most_frequent_count == max(...)` 两条断言，注释"对并列稳健"（lines 760-762） | **通过** |
| 5 | sanhe_day_group 隐含不变式缺注释 | Task 7 Step 1: 新增三行注释说明"12 地支全覆盖→永不返回 None"不变式及降级行为（lines 561-562） | **通过** |

### 建议改进项核验

| # | 建议 | 修订位置 | 状态 |
|---|---|---|---|
| 1 | regenerate.py 导入健壮性 | Task 12 Step 2: try/except ImportError + SystemExit 友好信息（lines 1190-1195） | **通过** |
| 2 | compute_chart 显式传参 | 全部 7 处调用均显式传递 8 个参数（lines 852, 912-913, 1133-1134, 1234, 1248, 1258, 1269-1270） | **通过** |
| 3 | 节气 fixture 数据形状注释 | Task 3: `test_solar_term_info_modes` 加注"断言基于当前 5 字段已知形状"（line 225） | **通过** |
| 4 | 缺陷记录 commit hash 占位符清理 | Task 13: 新增 Step 4b "回填 commit hash"子步骤，"含占位符的文档不得提交"（lines 1368-1370）；Self-Review §2 同步反映（line 1385） | **通过** |
| 5 | dayun 起运岁数精确断言 | Task 4: 保留 `0<=...<=10` 兜底 + 新增 `abs(...-2.5)<0.3` 精确断言（lines 318-319） | **通过** |
| 6 | fixture 数据表绑定语义说明 | Task 3: `_verified_term` docstring 加"若失败先检查 solar_terms.json 是否被修改"（lines 187-188） | **通过** |
| 7 | 非 verified 节气行为注释 | Task 3: `test_jingzhe_month_boundary_date_only` 加注"断言外部行为，不验证内部实现"（lines 214-215） | **通过** |

### 附带修正核验

审核报告中未强制要求的附带改进也一并确认：

- `_ganzhi_for` 加注"天干仅占位，三合系/日柱系不以天干判定"（line 401-402）——解决助手函数语义模糊
- shensha.py 顶部 bazi_snapshot_helper import 加注 NOTE 说明 Task 12 前不可用（lines 385-391）——解决依赖链操作风险
- Self-Review 章节标题改为"含审核报告修订核对"（line 1382）——透明度追溯

### 修订引入的新问题检查

逐一扫描修订区域的代码逻辑：

- `NEUTRAL_FP` 的四柱（乙丑/丙寅/丁卯/戊辰）均不在 7 张日柱系表中，确认不会干扰 day_pillar_position_negative 的反例语义
- `ss['counts'][ss['strongest']] == max(ss['counts'].values())` 使用了"通过 strongest 键名回查 counts 取最大值"的间接方式，对并列 strongest 的情况不假设 tie-break 顺序——比直接比较 `ss['strongest'] == max(ss['counts'], key=...)` 更稳健
- `regenerate.py` 中 `_REPO` 现在正确指向仓库根，`sys.path.insert(0, _REPO)` 可以导入 `bazi_calculator` 和 `lunar_calendar`
- 所有 `compute_chart` 调用显式传参后，若未来默认值改变测试不会静默偏移

**无新增问题。**

### 第三轮审核结论

修订完整覆盖了审核报告的全部 5 个必须修复项和 7 个建议改进项，无遗漏。新增代码逻辑正确，未引入副作用。附带修正合理且不越界。

**最终结论：计划达到可执行标准，批准进入实现阶段。**
