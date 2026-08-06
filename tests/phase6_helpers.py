"""Phase 6 共享测试设施。

RunnerEnv / RunnerSpy / fake_config / make_case / with_chart / write_jsonl。

执行偏离登记（随各 Task 提交累积）：
- fake_config 的 AblationConfig 为函数内延迟导入（Task 9 才建该模块，Task 2 已登记）。
- RunnerEnv 默认 case_factory 为 `with_chart(make_case(cid))` 而非裸 make_case：
  计划原文 `factory = case_factory or make_case`，但 6A0 可见性门禁（profiles
  assert_visibility）要求 approved 全量 chart_input；裸 make_case 无 chart_input，
  门禁全部 BLOCK → 零模型调用，resume/路由测试无法成立。计划提及 "with_chart 注入"
  但未给出定义，此处补齐并设为默认（Task 6 登记）。
- RunnerEnv.__init__ 额外两处 monkeypatch（Task 6 登记）：data_store.save_benchmark_run
  → no-op（避免集成测试反复写真实 sqlite）；run_benchmark.time.sleep → no-op（每 case
  1s sleep 会拖慢套件）。均为测试副作用隔离，不改变被测语义。
- RunnerEnv.run 的 call_model_messages_sync_with_meta patch 改为条件 patch（Task 3
  登记）：仅当当前绑定仍是 claude_api 真实函数时才替换为 _fake_call_with_meta；测试
  已自行 monkeypatch 自定义 fake（如 thinking_mode/response_model 协议测试）时保留
  测试的 fake，否则 run 会覆盖测试 patch 使计划逐字测试无法成立。resume 二次运行
  时绑定已是 _fake_call_with_meta，跳过 patch 语义不变。
- with_chart 形状照 tests/fixtures/phase6/case_sample_1.json 的最小批准字段集；
  不含 kong_wang / liu_nian（denylist：空亡：/空亡（/【流年】）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import claude_api as _claude_api

# 真实边界函数引用：RunnerEnv.run 据此判断测试是否已自行 patch（见模块 docstring）
_REAL_CALL_WITH_META = _claude_api.call_model_messages_sync_with_meta


def make_case(case_id: str = "c1", answer: str = "B", person_id: str = "p1") -> dict:
    """最小合法 BaziQA case；chart_input 按需经 with_chart 注入。"""
    return {
        "case_id": case_id, "answer": answer, "domain": "wealth",
        "question": "命主财运如何？", "options": ["A 普通", "B 富裕", "C 破财", "D 平稳"],
        "source_year": "2024",
        "person": {
            "person_id": person_id, "name": f"命主{person_id}", "gender": "male",
            "birth": {"year": 1990, "month": 1, "day": 2, "hour": 3, "minute": 0, "place": "北京"},
        },
    }


def with_chart(case: dict) -> dict:
    """注入全量 approved chart_input（baziqa approved 可见性 required 全过的最小集）。

    覆盖：four_pillars(含藏干) / day_master / da_yun+dayun_summary(起运) /
    胎元命宫身宫 / 真太阳时 / 纳音 / 五行统计 / 十神统计 / 地支关系 / 神煞。
    """
    case = dict(case)
    case["chart_input"] = {
        "status": "success",
        "birth_info": {"year": 1990, "month": 1, "day": 2, "hour": 3, "minute": 0,
                       "gender": "male", "location": "北京"},
        "four_pillars": {
            key: {"gan": gan, "zhi": zhi, "gan_wuxing": "木", "zhi_wuxing": "水",
                  "shi_shen_gan": "比肩", "shi_shen_zhi_main": "正印",
                  "cang_gan": ["癸"], "cang_gan_shi_shen": ["正印"], "nayin": "海中金"}
            for key, gan, zhi in (("year", "庚", "午"), ("month", "戊", "子"),
                                  ("day", "甲", "子"), ("hour", "甲", "寅"))
        },
        "day_master": {"gan": "甲", "wuxing": "木", "yinyang": "阳",
                       "shier_changsheng": "沐浴"},
        "dayun_summary": {"direction": "顺排", "starting_age": 6.2,
                          "current_pillar": {"gan": "辛", "zhi": "巳"}},
        "da_yun": [
            {"index": idx, "gan": gan, "zhi": zhi,
             "start_age": start, "end_age": start + 9,
             "shi_shen_gan": "正官", "shi_shen_zhi": "正财",
             "is_current": idx == 3}
            for idx, (gan, zhi, start) in enumerate(
                (("己", "丑", 6), ("庚", "寅", 16), ("辛", "卯", 26), ("辛", "巳", 36)),
                start=1)
        ],
        "tai_yuan": {"gan": "癸", "zhi": "亥", "nayin": "大海水"},
        "ming_gong": {"gan": "丙", "zhi": "子", "nayin": "涧下水"},
        "shen_gong": {"gan": "庚", "zhi": "辰", "nayin": "白蜡金"},
        "true_solar_info": {"original_time": "1990-01-02T03:00:00",
                            "adjusted_time": "1990-01-02T02:40:00",
                            "adjustment_minutes": -20,
                            "method": "longitude_correction",
                            "location_matched": True},
        "nayin_wuxing": {"year": "土", "month": "金", "day": "金", "hour": "水"},
        "wuxing_stats": {"jin": 1, "mu": 2, "shui": 2, "huo": 1, "tu": 2,
                         "missing": [], "strongest": "木", "weakest": "金"},
        "shishen_stats": {"counts": {"比肩": 2, "正官": 1, "正财": 1}, "missing": []},
        "branch_relations": [],
        "shensha": [{"name": "天乙贵人", "position": "year_zhi", "meaning": "主贵人扶助"}],
    }
    return case


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")


class RunnerEnv:
    """run_benchmark 进程内集成测试环境：monkeypatch 模型边界，脚本化成功/失败/崩溃。"""

    def __init__(self, tmp_path: Path, monkeypatch, n_cases: int = 4, case_factory=None):
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.dataset = tmp_path / "cases.jsonl"
        self.detail = tmp_path / "detail.jsonl"
        self.events = tmp_path / "detail.events.jsonl"
        self.summary = tmp_path / "summary.json"
        factory = case_factory or (lambda cid: with_chart(make_case(cid)))
        write_jsonl(self.dataset, [factory(f"c{i}") for i in range(n_cases)])
        self._script: list[tuple[str, object]] = []
        self.received: list = []          # 每次模型调用的 messages，按调用顺序
        self.received_kw: list = []       # 每次模型调用的 **kw（temperature 等），按调用顺序
        # 测试副作用隔离（执行偏离，见模块 docstring）
        self.monkeypatch.setattr("data_store.save_benchmark_run", lambda **kw: None)
        self.monkeypatch.setattr(
            "benchmark.runners.run_benchmark.time.sleep", lambda *_a, **_k: None)

    # ---- 模型脚本 ----
    def model_returns(self, text: str) -> None:
        self._script = [("ok", text)] * 1000

    def model_fails(self, times: int) -> None:
        self._script = [("fail", RuntimeError("model_call_failed: boom"))] * times \
            + [("ok", "A")] * 1000

    def model_truncates(self, times: int, text: str = "根据命主出生信息") -> None:
        """前 times 次返回 finish_reason='length' 的截断响应，之后正常返回 'A'。"""
        self._script = [("trunc", text)] * times + [("ok", "A")] * 1000

    def model_truncates_then_crash(self, truncations: int) -> None:
        """先 N 次截断响应，再抛非重试异常模拟进程崩溃（截断预算守恒测试用）。"""
        self._script = (
            [("trunc", "截断")] * truncations
            + [("crash", RuntimeError("unexpected crash"))]
        )

    def model_fails_then_crash(self, failures: int) -> None:
        """先 N 次可重试网络失败，再抛非重试异常模拟进程崩溃。"""
        self._script = (
            [("fail", RuntimeError("model_call_failed: net"))] * failures
            + [("crash", RuntimeError("unexpected crash"))]
        )

    def model_succeeds_then_crash(self, text: str, successes: int) -> None:
        """先 N 次成功返回，再抛非重试异常模拟进程崩溃（calls_attempted 恢复测试用）。"""
        self._script = [("ok", text)] * successes + [("crash", RuntimeError("unexpected crash"))]

    def model_sequence(self, texts: list) -> None:
        """按序返回不同响应（emit_samples 逐样本差异化用）；耗尽后恒返回 "A"。"""
        self._script = [("ok", t) for t in texts] + [("ok", "A")] * 1000

    def _fake_call_with_meta(self, messages, **kw):
        self.received.append(messages)
        self.received_kw.append(kw)
        action, payload = self._script.pop(0)
        if action in ("fail", "crash"):
            raise payload
        meta = {
            "finish_reason": "length" if action == "trunc" else "stop",
            "http_status": 200,
            "latency_ms": 302000 if action == "trunc" else 123,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "response_id": f"fake-{len(self.received)}",
            "provider": kw.get("provider"),
            "model": kw.get("model"),
            "requested_model": kw.get("model"),
            "response_model": None,
            "thinking_mode": kw.get("thinking_mode"),
        }
        return payload, meta

    # ---- 运行 ----
    def run(self, resume: bool = False, model: str = "deepseek-chat",
            scheduled_calls: int | None = None, hard_cap: int | None = None,
            profile: str | None = None, thinking_mode: str | None = None,
            extra_argv: list[str] | None = None) -> int:
        import run_benchmark_proxy  # tests 内薄封装：转发到 benchmark.runners.run_benchmark.main(argv)
        import claude_api
        # 条件 patch（执行偏离，见模块 docstring）：测试已自行 patch 时保留其 fake
        if claude_api.call_model_messages_sync_with_meta is _REAL_CALL_WITH_META:
            self.monkeypatch.setattr(
                "claude_api.call_model_messages_sync_with_meta", self._fake_call_with_meta)
        argv = ["--dataset", str(self.dataset), "--model-runner", "--provider", "deepseek",
                "--model", model, "--case-details-jsonl", str(self.detail),
                "--output-dir", str(self.tmp)]
        if resume:
            argv.append("--resume")
        if scheduled_calls is not None:
            argv += ["--scheduled-calls", str(scheduled_calls)]
        if hard_cap is not None:
            argv += ["--hard-cap", str(hard_cap)]
        if profile:
            argv += ["--profile", profile]
        if thinking_mode is not None:
            argv += ["--thinking-mode", thinking_mode]
        argv += extra_argv or []
        return run_benchmark_proxy.main(argv)

    def run_expect_crash(self, **kw) -> None:
        import pytest
        with pytest.raises(RuntimeError, match="unexpected crash"):
            self.run(**kw)

    def run_subprocess(self, argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "benchmark.runners.run_benchmark", *argv],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )

    # ---- 读取 ----
    def read_detail(self) -> list[dict]:
        if not self.detail.exists():
            return []
        return [json.loads(x) for x in self.detail.read_text(encoding="utf-8").splitlines()
                if x.strip()]

    def read_events(self, kind: str | None = None) -> list[dict]:
        if not self.events.exists():
            return []
        rows = [json.loads(x) for x in self.events.read_text(encoding="utf-8").splitlines()
                if x.strip()]
        if kind is not None:
            rows = [r for r in rows if r.get("kind") == kind]
        return rows

    def read_summary(self) -> dict:
        if not self.summary.exists():
            return {}
        return json.loads(self.summary.read_text(encoding="utf-8"))


class RunnerSpy:
    """编排器 arm-run 边界探针（Task 9 使用）：记录每次调用的 SliceRun 与 kwargs。"""

    def __init__(self):
        self.calls: list = []

    def __call__(self, slice_run, **kwargs):
        self.calls.append(type("Call", (), {"slice": slice_run, "kwargs": kwargs}))
        return type("ArmRunResult", (), {"exit_code": 0, "records": [], "calls_attempted": 0})


def fake_config(**overrides):
    # 延迟导入：scripts.run_phase6_6a0_ablation 在 Task 9 才创建（Task 2 已登记）
    from scripts.run_phase6_6a0_ablation import AblationConfig
    base = dict(run_id="test-run", year=2024, root=Path(".tmp/phase6/test"),
                enriched_path=Path("enriched.jsonl"))
    base.update(overrides)
    return AblationConfig(**base)
