---
name: calculator-known-issues
description: BaZi calculator script known issues — verified June 2, 2026
metadata:
  type: reference
---

# bazi_calculator.py 已知问题

## 已排除的误报

### 1. 十神正偏倒置 — ❌ 误报 (2026-06-02 已确认)

**原声称**: `get_shishen()` 的 `same_yy` 逻辑与经典定义相反。

**验证结果**: 代码逻辑**完全正确**：
- 我克: `return '偏财' if same_yy else '正财'` ✓ 同阴阳=偏财，异阴阳=正财
- 克我: `return '七杀' if same_yy else '正官'` ✓ 同阴阳=七杀，异阴阳=正官
- 生我: `return '偏印' if same_yy else '正印'` ✓ 同阴阳=偏印，异阴阳=正印
- 比肩/劫财、食神/伤官也全部正确

**测试**: 10 组经典对应关系全部通过（甲→庚七杀、甲→辛正官、甲→戊偏财、甲→己正财、甲→壬偏印、甲→癸正印等）

### 2. 紫微星曜索引混用 — ❌ 误报 (2026-06-02 已确认)

**原声称**: star deployment 使用 0=寅 而 palace lookup 使用 DIZHI.index (0=子)，offset 差 2 位。

**验证结果**: 代码使用 `_to_std = lambda i0: (i0 + 2) % 12` 将 iztro 的 0=寅 坐标正确转换为标准 DIZHI 索引 (0=子)。所有星曜排布（`stars[pos]`）和宫位查找（`stars.get(DIZHI.index(pzhi), [])`）都使用统一的标准索引，无错位问题。

### 3. 身宫函数重复定义 — ❌ 误报 (2026-06-02 已确认)

**验证结果**: 代码中只有一处 `get_shengong()` 定义（line 677）。无重复定义。

### 4. 紫微农历日近似 — ✅ 已修复

**原问题**: `lunar_day = day if day <= 30 else 30`

**现状**: `calculate_ziwei` 第 1185 行已改为 `lunar_year, lunar_month, lunar_day, _is_leap = solar_to_lunar(year, month, day)`，正确获取农历日期。

---

## 待修复

### 5. 节气交界处理精度不足 (Confirmed, 待修复)

**位置**: `bazi_calculator.py` — `get_month_pillar()` 和相关函数

**问题**: 使用简化的月/日阈值判断节气（例如：立春 ≈ 2月4日），对于正好出生在节气交界处（精确到小时/分钟）的用户可能产生月柱错误。虽然大多数情况下 1-2 天的误差不影响月柱判定，但在节气精确时刻前后出生的用户需要精确判断。

**影响范围**: 出生日期正好在节气交界日（约每月 1-2 天）的用户，小时级别的精度需要确认。

**修正方案**: 
- 利用 `knowledge-base/solar_terms.json` 中的精确节气时间（151 年数据），将节气判断从月/日级提升到分钟级
- 对当前代码来说，由于 `get_month_pillar()` 已经使用了生日对比节气的简化逻辑，核心风险是出生在节气当日但时间在精确时刻之前/之后的情况
