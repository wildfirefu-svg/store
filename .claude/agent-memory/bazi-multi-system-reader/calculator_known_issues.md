---
name: calculator-known-issues
description: BaZi calculator script bugs — reversed zheng/pian 十神 logic and ziwei indexing mismatch
metadata:
  type: reference
---

# bazi_calculator.py 已知问题

## 1. 十神正偏倒置 (Confirmed)
**位置**: `get_shishen()` function, 我克/克我/生我 三类关系

**问题**: `same_yy` 的逻辑与经典定义相反。
- 经典: 阴阳相反=正 (正官/正印/正财), 阴阳相同=偏 (七杀/偏印/偏财)
- 脚本: `same_yy → 正`, `!same_yy → 偏` — 完全颠倒

**影响范围**: 正官vs七杀, 正印vs偏印, 正财vs偏财 全部反转。
比肩/劫财 和 食神/伤官 逻辑正确。

**修正方法**: 在分析前手动翻转以上三类十神的正/偏。

## 2. 紫微星曜索引混用 (Confirmed)
**位置**: `calculate_ziwei()` 中 star deployment vs palace lookup

**问题**: 
- `ziwei_position()` 和 star deployment 使用 0=寅 索引
- `stars.get(DIZHI.index(pzhi), [])` 使用标准 DIZHI.index (0=子) 查找
- 两者 offset 相差2位，导致星曜排入错误的宫位

**影响范围**: 所有14主星在十二宫的分布可能偏移约2-4个宫位。

**修正方法**: 需要统一索引体系后再排星。目前分析策略：使用脚本输出并注明可能偏差，关键判断辅以经典手算验证。

## 3. 身宫函数重复定义
**位置**: 两个 `get_shengong()` 函数定义，后者覆盖前者，逻辑可能不同。

## 4. Solar term boundary handling
**位置**: `get_month_branch_idx()` 和 dayun junction finding
使用简化的月/日阈值判断节气，对于正好出生在节气交界的用户可能产生1天的误差。
脚本已输出 `precision_note` 提醒。

## 5. Lunar day approximation
**位置**: `calculate_ziwei()` 中 `lunar_day = day if day <= 30 else 30`
直接使用公历日期代替农历日期，可能影响紫微星位置计算（农历日数用于紫微定位）。
