"""Failing tests for the yet-to-be-implemented self-consistency helpers.

Interface under test (see docs/superpowers/plans/2026-07-01-phase1-evaluation-infra.md
Task 2.2):

- benchmark.runners.self_consistency.majority_vote(votes) -> Optional[str]
- benchmark.runners.self_consistency.sample_answers(call_fn, n, temperatures) -> List[Tuple[str, Optional[str]]]

Behaviour contract covered here:
1. majority_vote returns the label with the highest count.
2. majority_vote breaks ties by first-seen order.
3. majority_vote ignores None entries when counting.
4. majority_vote returns None when every vote is None.
5. majority_vote raises ValueError on empty input (surface caller bug fast).
6. sample_answers calls the provided callback n times, with the given temperatures,
   and returns the (raw, predicted_label) pairs in order.
7. sample_answers rejects mismatched temperatures length.
8. sample_answers defaults to a uniform temperature list when temperatures=None.
"""

from __future__ import annotations

import pytest

try:
    from benchmark.runners.self_consistency import majority_vote, sample_answers
except ImportError:
    majority_vote = None
    sample_answers = None


def _require_impl():
    if majority_vote is None or sample_answers is None:
        pytest.fail(
            "benchmark.runners.self_consistency is not implemented yet; "
            "see docs/superpowers/plans/2026-07-01-phase1-evaluation-infra.md Task 2.2"
        )


def test_majority_vote_returns_mode():
    _require_impl()
    assert majority_vote(["A", "B", "A", "A", "C"]) == "A"


def test_majority_vote_breaks_tie_by_first_seen():
    _require_impl()
    assert majority_vote(["A", "B", "A", "B"]) == "A"
    assert majority_vote(["C", "B", "C", "B"]) == "C"


def test_majority_vote_ignores_none():
    _require_impl()
    assert majority_vote(["A", None, "A", None, "B"]) == "A"


def test_majority_vote_all_none_returns_none():
    _require_impl()
    assert majority_vote([None, None, None]) is None


def test_majority_vote_empty_raises():
    _require_impl()
    with pytest.raises(ValueError):
        majority_vote([])


def test_sample_answers_calls_callback_n_times_with_given_temperatures():
    _require_impl()
    call_log: list[float] = []

    def fake_call(temperature: float):
        call_log.append(temperature)
        return f"raw@{temperature}", "A"

    results = sample_answers(fake_call, n=3, temperatures=[0.3, 0.5, 0.9])

    assert call_log == [0.3, 0.5, 0.9]
    assert results == [("raw@0.3", "A"), ("raw@0.5", "A"), ("raw@0.9", "A")]


def test_sample_answers_rejects_mismatched_temperature_length():
    _require_impl()

    def fake_call(temperature: float):
        return "raw", "A"

    with pytest.raises(ValueError):
        sample_answers(fake_call, n=3, temperatures=[0.3, 0.5])


def test_sample_answers_defaults_to_uniform_temperature():
    _require_impl()
    seen: list[float] = []

    def fake_call(temperature: float):
        seen.append(temperature)
        return "raw", "B"

    results = sample_answers(fake_call, n=4, temperatures=None, default_temperature=0.4)

    assert seen == [0.4, 0.4, 0.4, 0.4]
    assert len(results) == 4
    assert all(pair == ("raw", "B") for pair in results)


def test_sample_answers_rejects_non_positive_n():
    _require_impl()

    def fake_call(temperature: float):
        return "raw", "A"

    with pytest.raises(ValueError):
        sample_answers(fake_call, n=0, temperatures=None)
    with pytest.raises(ValueError):
        sample_answers(fake_call, n=-1, temperatures=None)
