"""Local case-level retrieval index over BaziQA corpus rows.

Aggregates rows by ``person_id`` so each case carries the chart context together
with the factual events disclosed by the dataset answers, and exposes a
``top_k_cases`` lookup with structured filters and a keyword fallback.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


HOLDOUT_MARKERS = ("holdout", "_holdout")

DOMAIN_HINTS = {
    "career": ("事业", "工作", "职位", "官", "权", "名", "升", "职", "创业", "管理", "仕途"),
    "wealth": ("财", "富", "钱", "收入", "致富", "投资", "经商", "破财", "合作", "挥霍", "守财", "财源", "暴起暴跌"),
    "relationship": ("婚", "感情", "配偶", "夫妻", "恋", "桃花", "离", "伴侣", "再婚", "外遇", "争吵"),
    "health": ("健康", "病", "疾", "伤", "灾", "寿", "身体", "手术", "意外", "慢性"),
    "family": ("父", "母", "子", "女", "家庭", "兄弟", "亲人", "家境", "祖业"),
    "annual_fortune": ("流年", "年份", "大运", "岁运", "应期", "转折", "年份"),
    "study": ("学", "考试", "文凭", "读书", "学历", "升学", "科研"),
    "personality": ("性格", "个性", "为人", "脾气", "保守", "开朗", "固执"),
}

STOP_PHRASES = (
    "命主", "是否", "哪个", "哪项", "以下", "最", "比较", "容易", "可能", "明显", "情况", "选项", "正确", "判断",
    "此命", "出生", "如何", "请问", "现在", "发生", "何事", "哪一", "哪种", "一种", "命局",
)

GENERIC_PHRASES = {
    "出生", "如何", "此命", "命主", "情况", "发生", "何事", "现在", "请问", "父母", "家中", "身材", "外貌",
    "哪个", "哪项", "一种", "哪种", "正确", "判断", "问题", "选项", "比较", "容易",
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_enabled(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


_TOKEN_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]+")


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    tokens: List[str] = []
    for chunk in _TOKEN_RE.findall(text):
        if re.match(r"[\u4e00-\u9fa5]+", chunk):
            tokens.extend(list(chunk))
        else:
            tokens.append(chunk.lower())
    return tokens


def _hint_matches(text: str, hints) -> List[str]:
    haystack = str(text or "")
    return [h for h in hints if h and h in haystack]


def _semantic_phrases(text: str) -> List[str]:
    text = re.sub(r"[A-D][\.、\s]*", " ", str(text or ""))
    chunks = re.split(r"[，。；、,.?？!！\s]+", text)
    phrases = set()
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        for stop in STOP_PHRASES:
            chunk = chunk.replace(stop, "")
        if len(chunk) >= 3 and chunk not in GENERIC_PHRASES:
            phrases.add(chunk[:12])
        for i in range(0, max(len(chunk) - 2, 0)):
            gram = chunk[i:i + 3]
            if len(gram) == 3 and gram not in GENERIC_PHRASES:
                phrases.add(gram)
        for i in range(0, max(len(chunk) - 3, 0)):
            gram = chunk[i:i + 4]
            if len(gram) == 4 and gram not in GENERIC_PHRASES:
                phrases.add(gram)
    return sorted(
        p for p in phrases
        if p and p not in GENERIC_PHRASES and not p.isdigit() and not p.startswith("的")
    )


class CaseIndex:
    def __init__(
        self,
        corpus_path: Path,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
    ):
        path = Path(corpus_path)
        name = path.name.lower()
        if any(marker in name for marker in HOLDOUT_MARKERS):
            raise ValueError(
                f"Refusing to load holdout file as corpus: {path}. "
                "case_index must never index holdout data."
            )
        if not path.exists():
            raise FileNotFoundError(path)

        self.path = path
        self._embed_fn = embed_fn
        self._cases: List[Dict[str, Any]] = self._load(path)
        self._doc_tokens = [_tokenize(c["text_blob"]) for c in self._cases]
        self._idf = self._build_idf(self._doc_tokens)

    # ------------------------------------------------------------ loading
    def _load(self, path: Path) -> List[Dict[str, Any]]:
        people: Dict[str, Dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                person = row.get("person") or {}
                pid = person.get("person_id") or row.get("case_id")
                if not pid:
                    continue
                bucket = people.setdefault(pid, {"person": person, "facts": [], "domains": Counter()})
                fact = self._row_fact(row)
                if fact:
                    bucket["facts"].append(fact)
                domain = str(row.get("domain") or "unknown")
                bucket["domains"][domain] += 1

        cases: List[Dict[str, Any]] = []
        for pid, bucket in people.items():
            person = bucket["person"]
            birth = person.get("birth") or {}
            year = birth.get("year")
            decade = (int(year) // 10) * 10 if isinstance(year, int) else None
            domains = dict(bucket["domains"])
            text_blob = self._make_text_blob(person, bucket["facts"], domains)
            cases.append({
                "person_id": pid,
                "name": person.get("name") or pid,
                "gender": str(person.get("gender") or ""),
                "birth_year": year,
                "birth_decade": decade,
                "facts": bucket["facts"],
                "text_blob": text_blob,
                "domains": domains,
                "keywords": self._case_keywords(bucket["facts"], domains),
                "semantic_phrases": _semantic_phrases(text_blob),
            })
        return cases

    @staticmethod
    def _row_fact(row: Dict[str, Any]) -> str:
        answer = str(row.get("answer") or "").strip().upper()
        options = row.get("options") or []
        question = str(row.get("question") or "").strip()
        if not answer or not options:
            return ""
        idx_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        idx = idx_map.get(answer)
        if idx is None or idx >= len(options):
            return ""
        return f"{question} -> {options[idx]}"

    @staticmethod
    def _case_keywords(facts: List[str], domains: Dict[str, int]) -> List[str]:
        text = "；".join(facts)
        keywords = set()
        for hints in DOMAIN_HINTS.values():
            keywords.update(_hint_matches(text, hints))
        return sorted(keywords)

    @staticmethod
    def _make_text_blob(person: Dict[str, Any], facts: List[str], domains: Dict[str, int]) -> str:
        birth = person.get("birth") or {}
        domain_text = " ".join(domains.keys())
        keyword_text = " ".join(CaseIndex._case_keywords(facts, domains))
        head = (
            f"{person.get('name') or ''}，"
            f"出生 {birth.get('year', '?')}-{birth.get('month', '?')}-{birth.get('day', '?')} "
            f"性别 {person.get('gender') or ''} "
            f"领域 {domain_text} 关键词 {keyword_text}"
        )
        body = "；".join(facts[:8])
        text = f"{head}。事实：{body}"
        return text[:1200]

    # --------------------------------------------------------------- bm25
    @staticmethod
    def _build_idf(doc_tokens: List[List[str]]) -> Dict[str, float]:
        n = max(len(doc_tokens), 1)
        df: Counter = Counter()
        for tokens in doc_tokens:
            df.update(set(tokens))
        return {term: math.log((n - f + 0.5) / (f + 0.5) + 1.0) for term, f in df.items()}

    def _bm25_scores(self, query_tokens: List[str]) -> List[float]:
        if not query_tokens:
            return [0.0] * len(self._cases)
        k1 = 1.5
        b = 0.75
        avg_dl = (sum(len(t) for t in self._doc_tokens) / max(len(self._doc_tokens), 1)) or 1.0
        scores = []
        for tokens in self._doc_tokens:
            tf = Counter(tokens)
            dl = len(tokens) or 1
            score = 0.0
            for term in query_tokens:
                if term not in tf:
                    continue
                idf = self._idf.get(term, 0.0)
                num = tf[term] * (k1 + 1)
                den = tf[term] + k1 * (1 - b + b * dl / avg_dl)
                score += idf * num / max(den, 1e-6)
            scores.append(score)
        return scores

    def _score_semantic_overlap(self, case: Dict[str, Any], query_text: str) -> tuple:
        query_phrases = set(_semantic_phrases(query_text))
        case_phrases = set(case.get("semantic_phrases") or [])
        overlap = sorted(query_phrases & case_phrases, key=lambda x: (-len(x), x))
        if not overlap:
            return 0.0, []
        long_overlap = [p for p in overlap if len(p) >= 3]
        score = min(0.18 * len(overlap) + 0.12 * len(long_overlap), 1.2)
        return score, overlap[:6]

    def _score_structured_match(self, case: Dict[str, Any], structured: Dict[str, Any]) -> tuple:
        score = 0.0
        reasons = []
        decade = structured.get("birth_decade")
        gender = structured.get("gender")
        day_master = structured.get("day_master_gan")
        month_zhi = structured.get("month_zhi")
        query_domain = structured.get("query_domain")
        query_text = str(structured.get("query_text") or "")
        branches = set(structured.get("branches") or [])

        if gender and case["gender"] == gender:
            score += 0.4
            reasons.append("same_gender")
        if decade and case["birth_decade"] is not None:
            gap = abs((case["birth_decade"] or 0) - int(decade))
            if gap == 0:
                score += 0.35
                reasons.append("same_decade")
            elif gap <= 10:
                score += 0.2
                reasons.append("near_decade")
        if query_domain and case.get("domains", {}).get(query_domain):
            score += 1.2
            reasons.append(f"same_domain:{query_domain}")
        domain_hits = _hint_matches(query_text, DOMAIN_HINTS.get(query_domain, ()))
        if domain_hits:
            overlap = [kw for kw in case.get("keywords", []) if kw in domain_hits]
            if overlap:
                score += min(0.25 * len(overlap), 0.75)
                reasons.append("intent_overlap:" + ",".join(overlap[:4]))
        if day_master and day_master in case["text_blob"]:
            score += 0.2
            reasons.append("day_master_text")
        if month_zhi and month_zhi in case["text_blob"]:
            score += 0.15
            reasons.append("month_branch_text")
        if branches:
            overlap = sum(1 for b in branches if b in case["text_blob"])
            if overlap:
                score += min(overlap * 0.08, 0.32)
                reasons.append(f"branch_overlap:{overlap}")
        return score, reasons

    # --------------------------------------------------------------- public
    def top_k_cases(
        self,
        features: Dict[str, Any],
        k: int = 3,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not self._cases:
            return []
        query = str(features.get("text_blob") or "")

        if self._embed_fn is not None:
            try:
                _ = self._embed_fn(query)
            except Exception:
                pass

        query_tokens = _tokenize(query)
        scores = self._bm25_scores(query_tokens)

        structured = features.get("structured") or {}
        active_filters = filters or {}

        ranked = []
        for case, score in zip(self._cases, scores):
            if active_filters.get("gender") and case["gender"] != active_filters["gender"]:
                continue
            structured_weight = _env_float("BAZI_RAG_STRUCTURED_WEIGHT", 1.0)
            semantic_enabled = _env_enabled("BAZI_RAG_SEMANTIC", True)
            semantic_weight = _env_float("BAZI_RAG_SEMANTIC_WEIGHT", 1.0)

            structured_score, reasons = self._score_structured_match(case, structured)
            structured_score *= structured_weight
            semantic_score, phrase_hits = (0.0, [])
            if semantic_enabled:
                semantic_score, phrase_hits = self._score_semantic_overlap(case, structured.get("query_text") or query)
                semantic_score *= semantic_weight
            all_reasons = list(reasons)
            if phrase_hits:
                all_reasons.append("semantic_overlap:" + ",".join(phrase_hits[:4]))
            adj = score + structured_score + semantic_score
            ranked.append((adj, all_reasons, case))

        ranked.sort(
            key=lambda x: (
                -x[0],
                str(x[2].get("person_id") or ""),
                str(x[2].get("birth_year") or ""),
                str(x[2].get("name") or ""),
            )
        )
        seen: set = set()
        out: List[Dict[str, Any]] = []
        for score, reasons, case in ranked:
            if case["person_id"] in seen:
                continue
            seen.add(case["person_id"])
            item = dict(case)
            item["_score"] = round(float(score), 6)
            item["match_reasons"] = list(reasons)
            out.append(item)
            if len(out) >= k:
                break
        return out
