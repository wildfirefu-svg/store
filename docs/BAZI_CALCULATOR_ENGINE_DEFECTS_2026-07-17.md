# bazi_calculator 引擎缺陷记录（测试套件建设中发现）

> 日期： 2026-07-17 | 分支： codex/bazi-calculator-test-suite | 关联： docs/superpowers/specs/2026-07-17-bazi-calculator-test-suite-design.md

## 缺陷 #1：三合系神煞取组错误（已修复 7a048ab）
- 现象： calculate_shensha 以候选支自身定三合局（:944），桃花/驿马/劫煞/灾煞/亡神/紫微/三合禄 永不命中，华盖/将星 凡含目标支必误中
- 证据： 申年+酉月构造盘桃花全盘不命中（实测）；红色矩阵 56 failed / 24 passed（docs/bazi_test_suite_notes.md）
- 修复： 以年支/日支所属三合局并集为参考（紫微仅日支）
- 生产影响： shensha 字段变化（7 类新增、2 类按规则收敛）

## 缺陷 #2：日柱系神煞位置限制缺失（已修复 9f81bd9）
- 现象： 魁罡/孤鸾煞/阴差阳错/十恶大败/八专/悬针/天赦 7 类判断无 key=='day' 限制，年/月/时柱误报
- 证据： 庚辰年柱误中魁罡+十恶大败等（实测）；红色 21 failed / 7 passed
- 修复： 判定块加 key=='day' 限制
- 遗留： 天赦未按季节区分（春戊寅/夏甲午/秋戊申/冬甲子），待命理复核

## 缺陷 #3：compare_charts 五行键名不匹配（已修复 d3b336e）
- 现象： 按中文 金/木/水/火/土 读 wuxing_stats 的 pinyin 键，五行占比恒 0.0
- 证据： chart1_pct 总和 0.0；assert 0.0 == 25.0（红色 3 failed）
- 修复： pinyin→中文键名映射对齐

## 缺陷 #4：十二长生表与教科书/自身注释矛盾（已修复 e208985）
- 现象： CHANGSHENG_TABLE 各行数据与注释矛盾（注释"甲:亥..."数据首元素为戌）；实测 甲亥→养/乙午→冠带/丙寅→墓/庚巳→绝 等 10 干全错
- 决策： 用户 2026-07-17 在 Kimi Code 会话中经结构化问答（AskUserQuestion）明确选择路径 A（修复为教科书表）
- 修复： 整体替换为教科书阳顺阴逆表
- 生产影响： changsheng 与 day_master.shier_changsheng 输出变化

## 缺陷 #5：detect_branch_relations 输出顺序不确定（已修复 564cc7e）
- 现象： SANHE 为 set，:665 迭代顺序随进程 PYTHONHASHSEED 随机化，branch_relations 列表顺序跨进程翻转，快照基线无法稳定
- 证据： 同一用例 seed 0/42 → ['未未合局','酉酉合局']，seed 3/5/7/99 → 翻转；快照首跑 1 红
- 修复： for group in sorted(SANHE)（1 行）
- 遗留： knowledge-base/hehun.py:104 存在同样未排序迭代（不在本次快照路径内，未动，建议后续同样处理）

## 待命理复核口径（非本轮修复）
- 紫微神煞仅日支（源码注释"日支三合查"，暂定工程口径）
- 三合禄年/日支并集（外部依据弱，暂定工程口径）
- 天赦季节细化

## 验证基线
- 新套件验收：188 passed, 4 skipped in 6.60s（命令：pytest 6 个新测试文件 + test_accuracy.py -q；< 60s 达标；4 skipped 均为 shensha.py:76 紫微年支用例，按"紫微仅日支"口径主动跳过）
- 全量回归：783 passed, 4 failed, 6 skipped, 7 errors in 95.63s，失败/错误清单为基线 14 项的子集，无新增红
  - 与基线（606 passed, 7 failed, 7 errors, 2 skipped）逐项一致的部分：
    - FAILED tests/test_bazi_kb.py::TestCLI::test_search_cli（缺 bazi_kb.db 构建产物）
    - FAILED tests/test_mcp.py::TestBaziKBSearch::test_returns_results / test_empty_query_handled（缺 bazi_kb.db）
    - FAILED tests/test_benchmark_runner.py::test_multi_turn_case_details_records_retrieved_answer_leak
    - ERROR tests/test_e2e.py ×7（需真实服务器：TestChartCreation×2 / TestChat×2 / TestMultiMingzhu×1 / TestToolBars×2）
  - 差异（向好）：基线 failed 中的 test_report_to_pdf×3 本次转绿（现 19 passed；该文件测 PDF 模板/字体/Markdown 解析，不依赖排盘引擎，本分支未改动 report_to_pdf.py，转绿属环境层面）
  - 计数对账：606 − 14（旧 test_accuracy 用例被改造替换）+ 188（新套件 passed）+ 3（report_to_pdf 转绿）= 783 ✓；skipped 2 + 4（新套件主动跳过）= 6 ✓
- `git status --short -- tests/accuracy_report.json` 无输出（未被测试运行污染）
- 预存在环境噪声（与本套件无关）：6 个收集错误模块（HEAD 版 config.py 缺 DEEPSEEK_API_KEY、benchmark.reports.accuracy_stats 缺失，主仓未提交改动可解）；7 failed + 7 errors 见上

## 覆盖矩阵核对
对照 docs/superpowers/specs/2026-07-17-bazi-calculator-test-suite-design.md 附录 A（实际 26 行数据行），逐行确认对应测试存在且通过（Step 1 全绿；location_matching 3 例在全量回归中通过）：

| 公开函数 | 测试位置 | 结果 |
|---|---|---|
| `compute_chart` | e2e：test_compute_chart_schema_22_keys / test_e2e_snapshot / test_use_solar_time_flag_controls_auto_correction | ✓ |
| `compare_charts` | derived：test_compare_structure / test_compare_wuxing_pct_sums_100 / test_compare_wuxing_nonzero / test_compare_wuxing_matches_input / test_compare_identical_charts_zero_diff | ✓ |
| `calculate_four_pillars` | pillars：test_four_pillars_golden（8 例金标）+ test_accuracy（100 例） | ✓ |
| `get_year_pillar` | pillars：test_lichun_year_boundary_minute（pillars.py:88-89 直接调用）+ 金标年柱断言 | ✓ |
| `get_month_pillar` | pillars：test_wuhudun_month_stem / test_qingming_month_boundary_minute / test_jingzhe_month_boundary_date_only | ✓ |
| `get_day_pillar` | pillars：金标日柱断言（test_four_pillars_golden :31）+ test_zi_hour_day_pillar_not_rolled；注：无独立直接调用，经 calculate_four_pillars 金标日柱覆盖 | ✓ |
| `get_hour_pillar` | pillars：test_wushudun_hour_stem / test_zi_hour_early_uses_same_day_stem / test_zi_hour_late_uses_next_day_stem | ✓ |
| `get_month_branch_idx` | pillars：test_month_branch_idx_boundary | ✓ |
| `get_next_jie_info` | pillars：test_next_jie_info_shape | ✓ |
| `get_solar_term_info` | pillars：test_solar_term_info_modes（verified 分钟级 / 非 verified 日期级） | ✓ |
| `get_shishen` | pillars：test_shishen_full_table（全 10 种十神） | ✓ |
| `get_kongwang` | pillars：test_kongwang（甲子旬戌亥空等） | ✓ |
| `sexagenary_index` / `sexagenary_by_index` | dayun：test_sexagenary_roundtrip + test_pillar_progression_forward/backward | ✓ |
| `calculate_dayun` | dayun：test_direction_×4 / test_starting_age_range / test_pillar_progression_forward/backward | ✓ |
| `calculate_liunian` | dayun：test_liunian_sequence | ✓ |
| `calculate_shensha` / `enhance_shensha` | shensha：test_tianyi_guiren / test_wenchang / test_yangren / test_enhance_shensha_meaning / 三合系矩阵 test_sanhe_by_year_branch / test_sanhe_by_day_branch / test_sanhe_negative / test_sanhe_negative_ziwei_year_only / test_sanhe_merge_year_and_day / test_sanhe_no_duplicate / 日柱系 test_day_pillar_positive / test_day_pillar_position_negative / test_shensha_snapshot（3 盘） | ✓（4 个紫微年支用例按口径 skipped） |
| `calculate_ziwei` / `ziwei_position` | ziwei：test_gong_positions / test_twelve_palaces / test_14_main_stars_deployed / test_ziwei_position / test_ziwei_snapshot | ✓ |
| `calculate_wuyun_liuqi` | derived：test_wuyun_liuqi_schema（6 键契约） | ✓ |
| `calculate_wuxing_stats` | derived：test_wuxing_stats_invariants（总和=8 等） | ✓ |
| `calculate_shishen_stats` | derived：test_shishen_stats_invariants | ✓ |
| `detect_branch_relations` | derived：test_liuchong / test_liuhe / test_sanhe_full / test_sanxing / test_liuhai | ✓ |
| `get_taiyuan` / `get_minggong` / `get_shengong` | derived：test_gong_positions_legal | ✓ |
| `get_changsheng` | derived：test_changsheng_textbook（10 干教科书断言，缺陷 #4 修复后转绿） | ✓ |
| `detect_rizhu_zihe` | derived：test_rizhu_zihe_positive（丁亥/戊子/辛巳）/ test_rizhu_zihe_negative | ✓ |
| `calculate_true_solar_time` | location_matching：test_malaysia_chinese_location_matches_kuala_lumpur / test_malaysia_english_location_does_not_match_la_alias / test_la_short_alias_still_matches_los_angeles + e2e：test_use_solar_time_flag_controls_auto_correction | ✓ |
| `format_to_spec` | derived：test_format_to_spec_direct_20_keys（直接调用，20 键 schema） | ✓ |
