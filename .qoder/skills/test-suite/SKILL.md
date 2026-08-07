---
name: test-suite
description: 运行玄机子测试套件，根据变更范围选择测试范围
trigger: 代码改动后需要验证回归、合并前需要跑全量套件、或需要按变更范围选择测试时使用
output: 测试结果报告：PASS/FAIL 计数、失败项的断言错误信息、缺失模块的跳过说明
validation: 选定的 pytest 命令退出码为 0；失败时给出具体断言信息且失败归因于实现而非测试选择错误
---
# Test Suite Skill — 玄机子

Run the project's test suite and report results. Choose the right test scope based on what changed.

## Quick smoke test (fast, runs first)

```
python -c "
from bazi_calculator import calculate_four_pillars, calculate_shensha, calculate_dayun, calculate_ziwei
fp = calculate_four_pillars(1993,7,15,14,0,'北京')
dm = fp['day_master']['gan']
ss = calculate_shensha(fp, dm)
dy = calculate_dayun(('癸','酉'),('庚','申'),'male',1993,7,15)
zw = calculate_ziwei(1993,7,15,14,'male')
print('PASS: pillars=' + str(len(fp)) + ' shensha=' + str(sum(len(v) for v in ss.values())) + ' dayun=' + str(len(dy.get('pillars',[]))) + ' ziwei_palaces=' + str(len(zw.get('twelve_palaces',[]))))
"
```

## Unit tests (medium)

Run individual test files based on what was changed:

| What changed | Test file |
|-------------|-----------|
| `bazi_calculator.py` | `python scripts/affected_tests.py --run bazi_calculator.py` |
| `claude_api.py` | `python -m pytest tests/test_claude_api.py -v --tb=short` |
| `api_server.py` | `python -m pytest tests/test_api.py -v --tb=short` |
| `data_store.py` | `python -m pytest tests/test_data_store.py -v --tb=short` |
| `knowledge-base/` | `python -m pytest tests/test_bazi_kb.py tests/test_gejue_search.py tests/test_bingyao.py -v --tb=short` |
| Frontend `static/` | `python -m pytest tests/test_e2e.py -v --tb=short` |

## Full suite (slow, run before merge)

```
python -m pytest tests/ -v --tb=short -x
```

## Interpretation

- Count PASS/FAIL lines
- For failures: show the assertion error message only (not full traceback)
- If a test module is missing, skip it gracefully with a note

## Automated affected-test routing

The mapping above is also encoded in `scripts/affected_tests.py` (machine-readable gate):

```
python scripts/affected_tests.py            # diff vs HEAD -> pytest file list
python scripts/affected_tests.py --run      # also execute the selected tests
```

CI runs this as the optional `affected-tests` fast-path job (`continue-on-error`); the full `test` job remains the authoritative gate.
