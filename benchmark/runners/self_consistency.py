from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple


def majority_vote(votes: Sequence[Optional[str]]) -> Optional[str]:
    if len(votes) == 0:
        raise ValueError("majority_vote requires at least one vote")

    counts: dict = {}
    first_seen_order: List[str] = []
    for vote in votes:
        if vote is None:
            continue
        if vote not in counts:
            counts[vote] = 0
            first_seen_order.append(vote)
        counts[vote] += 1

    if not counts:
        return None

    best_label = first_seen_order[0]
    best_count = counts[best_label]
    for label in first_seen_order[1:]:
        if counts[label] > best_count:
            best_label = label
            best_count = counts[label]
    return best_label


def sample_answers(
    call_fn: Callable[[float], Tuple[str, Optional[str]]],
    n: int,
    temperatures: Optional[Sequence[float]] = None,
    default_temperature: float = 0.4,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    inter_sample_delay: float = 0.5,
) -> List[Tuple[str, Optional[str]]]:
    if not isinstance(n, int) or n <= 0:
        raise ValueError(f"sample_answers n must be a positive int, got {n!r}")
    if temperatures is None:
        temp_list: List[float] = [float(default_temperature)] * n
    else:
        temp_list = list(temperatures)
        if len(temp_list) != n:
            raise ValueError(
                f"sample_answers temperatures length {len(temp_list)} != n={n}"
            )

    import time

    results: List[Tuple[str, Optional[str]]] = []
    for idx, temp in enumerate(temp_list):
        if idx > 0 and inter_sample_delay > 0:
            time.sleep(inter_sample_delay)
        last_err: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                raw, predicted = call_fn(temp)
                results.append((raw, predicted))
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    wait = retry_delay * (attempt + 1)
                    time.sleep(wait)
        if last_err is not None:
            results.append(("", None))
    return results
