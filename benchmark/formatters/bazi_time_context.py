# -*- coding: utf-8 -*-
"""Bazi time-context relation computation.

Migrated from benchmark.formatters.two_stage_reasoning to centralize
Earthly-Branch / Heavenly-Stem relation logic and stream-year (流年) computation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum

from bazi_calculator import get_shishen, sexagenary_by_index

# Time/location keywords for identifying time-location questions
_TIME_KEYWORDS = [
    "哪年", "何时", "什么时候", "时间", "年份", "何年", "哪一年",
    "几年", "几时", "何時", "那年", "多久", "大运", "流年",
    "岁运", "年运", "年份",
]

# Wuxing generation cycle for computing gan relations
_WUXING_CYCLE = {
    "金": {"生": "水", "克": "木", "被生": "土", "被克": "火"},
    "木": {"生": "火", "克": "土", "被生": "水", "被克": "金"},
    "水": {"生": "木", "克": "火", "被生": "金", "被克": "土"},
    "火": {"生": "土", "克": "金", "被生": "木", "被克": "水"},
    "土": {"生": "金", "克": "水", "被生": "火", "被克": "木"},
}

# Gan to wuxing mapping
_GAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# Key shensha names relevant to common life events (shared with dayun evidence)
_KEY_SHENSHA = [
    "桃花", "红鸾", "天喜", "丧门", "白虎", "驿马", "华盖", "天乙贵人",
    "文昌贵人", "将星", "魁罡", "十恶大败", "阴差阳错", "孤鸾煞", "红艳煞",
]


def compute_branch_relation(zhi1: str, zhi2: str) -> list[str]:
    """Compute branch relations between two zhi (地支).

    Returns list of relation descriptions (六冲/六合/三合/六害/三刑).
    """
    relations = []
    # 六冲
    chong = {
        ("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"),
        ("辰", "戌"), ("巳", "亥"),
    }
    # 六合
    liuhe = {
        ("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"),
        ("巳", "申"), ("午", "未"),
    }
    # 三合 (partial match - any two of the three)
    sanhe = [
        {"申", "子", "辰"}, {"寅", "午", "戌"}, {"巳", "酉", "丑"}, {"亥", "卯", "未"},
    ]
    # 六害
    liuhai = {
        ("子", "未"), ("丑", "午"), ("寅", "巳"), ("卯", "辰"),
        ("申", "亥"), ("酉", "戌"),
    }
    # 三刑
    sanxing = [
        {"寅", "巳", "申"}, {"丑", "戌", "未"},
    ]

    pair = (zhi1, zhi2)
    pair_rev = (zhi2, zhi1)

    if pair in chong or pair_rev in chong:
        relations.append("冲")
    if pair in liuhe or pair_rev in liuhe:
        relations.append("合")
    if pair in liuhai or pair_rev in liuhai:
        relations.append("害")
    for group in sanhe:
        if zhi1 in group and zhi2 in group:
            relations.append("三合")
            break
    for group in sanxing:
        if zhi1 in group and zhi2 in group:
            relations.append("刑")
            break

    return relations


def compute_gan_relation(gan1: str, gan2: str) -> str:
    """Compute relation between two gan (天干) based on wuxing.

    Returns a description like '生', '克', '被生', '被克', '同'.
    """
    wx1 = _GAN_WUXING.get(gan1, "")
    wx2 = _GAN_WUXING.get(gan2, "")
    if not wx1 or not wx2:
        return ""
    if wx1 == wx2:
        return "同"
    cycle = _WUXING_CYCLE.get(wx1, {})
    if cycle.get("生") == wx2:
        return f"{gan1}生{gan2}"
    if cycle.get("克") == wx2:
        return f"{gan1}克{gan2}"
    if cycle.get("被生") == wx2:
        return f"{gan2}生{gan1}"
    if cycle.get("被克") == wx2:
        return f"{gan2}克{gan1}"
    return ""


def compute_shishen_combo(dy_shishen: str, ln_shishen: str) -> str:
    """Compute combination-effect hint between dayun and liunian shishen.

    Returns a hint string like '，组合效应：伤官见官' or empty string if no match.
    """
    combo = f"{dy_shishen}+{ln_shishen}"
    if "伤官" in combo and "正官" in combo:
        return "，组合效应：伤官见官"
    if "七杀" in combo and "食神" in combo:
        return "，组合效应：食神制杀"
    if "偏财" in combo and "正印" in combo:
        return "，组合效应：财坏印"
    if "劫财" in combo and "正财" in combo:
        return "，组合效应：劫财夺财"
    if "正官" in combo and "七杀" in combo:
        return "，组合效应：官杀混杂"
    if "正印" in combo and "正财" in combo:
        return "，组合效应：财坏印"
    if "偏印" in combo and "食神" in combo:
        return "，组合效应：枭神夺食"
    return ""


def calculate_liunian_for_year(target_year: int, day_master_gan: str) -> dict:
    """Compute the liunian (流年) pillar for a target year via the 60-jiazi cycle.

    Uses idx = (target_year - 4) % 60 to locate the sexagenary pillar, then
    derives the ten-god (十神) relative to the day master.

    Returns dict with keys: year, gan, zhi, shi_shen.
    Raises ValueError if target_year is outside [1900, 2100].
    """
    if not 1900 <= target_year <= 2100:
        raise ValueError(
            f"target_year {target_year} out of range [1900, 2100]"
        )
    idx = (target_year - 4) % 60
    gan, zhi = sexagenary_by_index(idx)
    shi_shen = get_shishen(day_master_gan, gan)
    return {
        "year": target_year,
        "gan": gan,
        "zhi": zhi,
        "shi_shen": shi_shen,
    }


# Option prefix pattern (e.g. "A. ", "B. ")
_OPTION_PREFIX = re.compile(r"^[A-D]\.\s*")

# Keywords that mark dayun/liunian routing questions (R4)
_DAYUN_KEYWORDS = ("大运", "流年", "岁运", "年运")

# When-keywords used by R5
_WHEN_KEYWORDS = ("何时", "哪年", "几年后", "几年")


def detect_temporal_rules(question: str, options: list[str]) -> frozenset[str]:
    """Detect temporal/routing rules in a BaziQA question and its options.

    Returns a frozenset of matched rule names (R1..R7). Each rule is an
    independent signal; multiple rules may fire for the same question.
    """
    matched: set[str] = set()

    stripped = [_OPTION_PREFIX.sub("", o) for o in options]

    # R1: question contains any time keyword
    if any(kw in question for kw in _TIME_KEYWORDS):
        matched.add("R1")

    # R2: all options (>=2) are bare 4-digit years
    if len(stripped) >= 2 and all(re.match(r"^\d{4}$", s) for s in stripped):
        matched.add("R2")

    # R3: any option contains a numeric range AND "岁"
    if any(re.search(r"\d+[-–]\d+", s) and "岁" in s for s in stripped):
        matched.add("R3")

    # R4: question contains dayun/liunian routing keywords
    if any(kw in question for kw in _DAYUN_KEYWORDS):
        matched.add("R4")

    # R5: question contains a when-keyword AND any option has a 4-digit year
    if any(kw in question for kw in _WHEN_KEYWORDS) and any(
        re.search(r"\d{4}", s) for s in stripped
    ):
        matched.add("R5")

    # R6: question body contains a standalone 4-digit year in [1900, 2100]
    for m in re.finditer(r"(?<!\d)\d{4}(?!\d)", question):
        year = int(m.group())
        if 1900 <= year <= 2100:
            matched.add("R6")
            break

    # R7: any option is a bare age (with optional 岁) in [1, 120]
    for s in stripped:
        m = re.match(r"^(\d+)岁?$", s)
        if m and 1 <= int(m.group(1)) <= 120:
            matched.add("R7")
            break

    return frozenset(matched)

# -*- coding: utf-8 -*-
"""Task 4 new code to append to bazi_time_context.py (appended verbatim)."""

# --- Target year extraction (Task 4) ---

# Standalone 4-digit year in text
_YEAR_RE = re.compile(r"(?<!\d)\d{4}(?!\d)")
# Any 4 consecutive digits (for options)
_FOUR_DIGIT_RE = re.compile(r"\d{4}")
# "N年后" / "N 年后" pattern
_YEARS_AFTER_RE = re.compile(r"(\d+)\s*年后")
# Age range "25-30"
_AGE_RANGE_RE = re.compile(r"(\d+)[-–](\d+)")
# Single age "30" or "30岁"
_SINGLE_AGE_RE = re.compile(r"^(\d+)岁?$")


def _validate_year_range(year: int) -> int:
    """Raise ValueError if year falls outside [1900, 2100] (fail-closed)."""
    if not 1900 <= year <= 2100:
        raise ValueError(f"year {year} out of range [1900, 2100]")
    return year


class TemporalRouteState(Enum):
    ROUTED_WITH_TARGETS = "ROUTED_WITH_TARGETS"
    ROUTED_WITHOUT_TARGETS = "ROUTED_WITHOUT_TARGETS"
    NOT_ROUTED = "NOT_ROUTED"


class TimeContextKind(Enum):
    NATAL = "natal"
    DAYUN = "dayun"
    LIUNIAN = "liunian"


@dataclass(frozen=True)
class NatalStructure:
    day_master: str
    four_pillars: tuple
    missing_shishen: tuple
    branch_relations: tuple
    key_shensha: tuple


@dataclass(frozen=True)
class DayunRow:
    start_age: int
    end_age: int
    start_year: int
    gan: str
    zhi: str
    shishen: str


@dataclass(frozen=True)
class OptionLiunian:
    target_year: int
    gan: str
    zhi: str
    shishen: str
    branch_relation: tuple
    gan_relation: str


@dataclass(frozen=True)
class TimeContext:
    natal: NatalStructure
    dayun_table: tuple
    option_liunian: tuple
    time_kind: TimeContextKind
    route_state: TemporalRouteState
    target_years: tuple
    extraction_hash: str

    def to_dict(self) -> dict:
        """Return JSON-serializable dict with all fields."""
        return {
            "natal": {
                "day_master": self.natal.day_master,
                "four_pillars": list(self.natal.four_pillars),
                "missing_shishen": list(self.natal.missing_shishen),
                "branch_relations": list(self.natal.branch_relations),
                "key_shensha": list(self.natal.key_shensha),
            },
            "dayun_table": [
                {
                    "start_age": r.start_age,
                    "end_age": r.end_age,
                    "start_year": r.start_year,
                    "gan": r.gan,
                    "zhi": r.zhi,
                    "shishen": r.shishen,
                }
                for r in self.dayun_table
            ],
            "option_liunian": [
                {
                    "target_year": o.target_year,
                    "gan": o.gan,
                    "zhi": o.zhi,
                    "shishen": o.shishen,
                    "branch_relation": list(o.branch_relation),
                    "gan_relation": o.gan_relation,
                }
                for o in self.option_liunian
            ],
            "time_kind": self.time_kind.value,
            "route_state": self.route_state.value,
            "target_years": list(self.target_years),
            "extraction_hash": self.extraction_hash,
        }

    def canonical_json(self) -> str:
        """Return canonical JSON string (sorted keys, no whitespace)."""
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

    def sha256(self) -> str:
        """Return SHA-256 of canonical_json."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def extract_target_years(
    question: str, options: list[str], birth_year: int | None
) -> tuple[int, ...]:
    """Extract target years from a question and its options.

    Rules (spec §3.5): 4-digit years in options (R2/R5), standalone 4-digit
    years in the question (R6), age ranges (R3) and single ages (R7) in
    options (require ``birth_year``), and "N年后" patterns that combine with
    the nearest preceding base year found in the question.

    Returns a sorted tuple of unique years. Raises ``ValueError`` if any
    computed year falls outside [1900, 2100] (fail-closed). Returns an empty
    tuple when no years can be extracted.
    """
    years: set[int] = set()
    stripped = [_OPTION_PREFIX.sub("", o) for o in options]

    # R2/R5: first 4-digit year (1900-2100) in each option
    for s in stripped:
        m = _FOUR_DIGIT_RE.search(s)
        if m:
            y = int(m.group())
            if 1900 <= y <= 2100:
                years.add(y)

    # R6: standalone 4-digit years in the question
    for m in _YEAR_RE.finditer(question):
        y = int(m.group())
        if 1900 <= y <= 2100:
            years.add(y)

    if birth_year is not None:
        # R3: age range in options ("25-30岁") -> keep BOTH endpoints
        for s in stripped:
            m = _AGE_RANGE_RE.search(s)
            if m and "岁" in s:
                start_year = birth_year + int(m.group(1))
                end_year = birth_year + int(m.group(2))
                years.add(_validate_year_range(start_year))
                years.add(_validate_year_range(end_year))

        # R7: single age in options ("30岁" or "30")
        for s in stripped:
            m = _SINGLE_AGE_RE.match(s.strip())
            if m and 1 <= int(m.group(1)) <= 120:
                target = birth_year + int(m.group(1))
                years.add(_validate_year_range(target))

    # "N年后" pattern: pair each offset with the nearest preceding base year
    base_years = [
        (m.start(), int(m.group()))
        for m in _YEAR_RE.finditer(question)
        if 1900 <= int(m.group()) <= 2100
    ]
    for om in _YEARS_AFTER_RE.finditer(question):
        n = int(om.group(1))
        base = None
        for pos, y in base_years:
            if pos < om.start():
                base = y
            else:
                break
        if base is not None:
            years.add(_validate_year_range(base + n))

    return tuple(sorted(years))


def classify_route_state(
    matched_rules: frozenset[str], target_years: tuple[int, ...]
) -> TemporalRouteState:
    """Classify the temporal route state from matched rules and target years."""
    if not matched_rules:
        return TemporalRouteState.NOT_ROUTED
    if target_years:
        return TemporalRouteState.ROUTED_WITH_TARGETS
    return TemporalRouteState.ROUTED_WITHOUT_TARGETS


def _resolve_birth_year(case: dict) -> int | None:
    """Resolve birth_year from a case dict (top-level or person.birth.year)."""
    birth_year = case.get("birth_year")
    if birth_year is None:
        birth_year = case.get("person", {}).get("birth", {}).get("year")
    return birth_year


def build_time_context(
    case: dict, route_state: TemporalRouteState | None = None
) -> TimeContext | None:
    """Build a TimeContext from a case dict.

    When ``route_state`` is None it is derived from the case via
    ``detect_temporal_rules`` + ``extract_target_years``. Returns None when the
    resolved state is NOT_ROUTED. ROUTED_WITHOUT_TARGETS builds the context
    with empty option_liunian; ROUTED_WITH_TARGETS builds the full context.
    """
    question = case.get("question", "")
    options = case.get("options", [])
    birth_year = _resolve_birth_year(case)

    if route_state is not None:
        state = route_state
    else:
        rules = detect_temporal_rules(question, options)
        state = classify_route_state(
            rules, extract_target_years(question, options, birth_year)
        )

    if state == TemporalRouteState.NOT_ROUTED:
        return None

    chart = case.get("chart_input") or {}
    target_years = extract_target_years(question, options, birth_year)

    # --- Natal structure ---
    day_master_raw = chart.get("day_master", "")
    if isinstance(day_master_raw, dict):
        day_master_gan = day_master_raw.get("gan", "")
    else:
        day_master_gan = day_master_raw

    four_pillars_raw = chart.get("four_pillars") or {}
    pillar_names = ["year", "month", "day", "hour"]
    four_pillars = tuple(
        f"{(four_pillars_raw.get(p) or {}).get('gan', '')}"
        f"{(four_pillars_raw.get(p) or {}).get('zhi', '')}"
        for p in pillar_names
    )
    natal_zhi = tuple(
        (four_pillars_raw.get(p) or {}).get("zhi", "") for p in pillar_names
    )

    missing_shishen = tuple(chart.get("shishen_stats", {}).get("missing", []) or [])

    branch_relations_raw = chart.get("branch_relations") or []
    branch_relations = tuple(
        f"{r.get('detail', '')}（{r.get('type', '')}）" for r in branch_relations_raw
    )

    shensha_raw = chart.get("shensha") or []
    key_shensha = tuple(
        s.get("name", "") for s in shensha_raw if s.get("name") in _KEY_SHENSHA
    )

    natal = NatalStructure(
        day_master=day_master_gan,
        four_pillars=four_pillars,
        missing_shishen=missing_shishen,
        branch_relations=branch_relations,
        key_shensha=key_shensha,
    )

    # --- Dayun table ---
    da_yun = chart.get("da_yun") or []
    base_year = birth_year or 0
    dayun_table = tuple(
        DayunRow(
            start_age=int(dy.get("start_age", 0)),
            end_age=int(dy.get("end_age", 0)),
            start_year=base_year + int(dy.get("start_age", 0)),
            gan=dy.get("gan", ""),
            zhi=dy.get("zhi", ""),
            shishen=dy.get("shi_shen_gan", ""),
        )
        for dy in da_yun
    )

    # --- Extraction hash ---
    extraction_hash = hashlib.sha256(
        json.dumps(
            list(target_years),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    # --- Option liunian (only when routed with targets) ---
    option_liunian: tuple = ()
    if (
        state == TemporalRouteState.ROUTED_WITH_TARGETS
        and day_master_gan
        and target_years
    ):
        opts = []
        for ty in target_years:
            ln = calculate_liunian_for_year(ty, day_master_gan)
            rels: list[str] = []
            for nz in natal_zhi:
                if nz:
                    rels.extend(compute_branch_relation(nz, ln["zhi"]))
            opts.append(
                OptionLiunian(
                    target_year=ty,
                    gan=ln["gan"],
                    zhi=ln["zhi"],
                    shishen=ln["shi_shen"],
                    branch_relation=tuple(rels),
                    gan_relation=compute_gan_relation(day_master_gan, ln["gan"]),
                )
            )
        option_liunian = tuple(opts)

    if option_liunian:
        time_kind = TimeContextKind.LIUNIAN
    elif dayun_table:
        time_kind = TimeContextKind.DAYUN
    else:
        time_kind = TimeContextKind.NATAL

    return TimeContext(
        natal=natal,
        dayun_table=dayun_table,
        option_liunian=option_liunian,
        time_kind=time_kind,
        route_state=state,
        target_years=target_years,
        extraction_hash=extraction_hash,
    )
