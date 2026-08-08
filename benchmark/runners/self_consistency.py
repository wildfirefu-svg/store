from __future__ import annotations

from collections.abc import Callable, Sequence


def majority_vote(votes: Sequence[str | None]) -> str | None:
    if len(votes) == 0:
        raise ValueError("majority_vote requires at least one vote")

    counts: dict = {}
    first_seen_order: list[str] = []
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
    call_fn: Callable[[float], tuple[str, str | None]],
    n: int,
    temperatures: Sequence[float] | None = None,
    default_temperature: float = 0.4,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    inter_sample_delay: float = 0.5,
) -> list[tuple[str, str | None]]:
    if not isinstance(n, int) or n <= 0:
        raise ValueError(f"sample_answers n must be a positive int, got {n!r}")
    if temperatures is None:
        temp_list: list[float] = [float(default_temperature)] * n
    else:
        temp_list = list(temperatures)
        if len(temp_list) != n:
            raise ValueError(
                f"sample_answers temperatures length {len(temp_list)} != n={n}"
            )

    import time

    results: list[tuple[str, str | None]] = []
    for idx, temp in enumerate(temp_list):
        if idx > 0 and inter_sample_delay > 0:
            time.sleep(inter_sample_delay)
        last_err: Exception | None = None
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


def strict_majority(votes: Sequence[str | None], threshold: int = 3) -> str | None:
    """严格多数投票（Phase 6 6A1，设计 §5.2.4）。

    与 majority_vote 的区别：majority_vote 取相对多数并按首次出现破平局
    （2/1/1/1 会选出 2 票选项），不满足严格协议，故新增且**不复用**。

    - 任一选项票数 >= threshold 且唯一 → 该选项；
    - 否则（含双达阈值、无达阈值、全 None）→ None（unresolved，按错误计入分母）；
    - None 票（invalid/call_failed）不参与计票但留在 votes 长度内——分母恒为采样次数；
    - 禁止任何形式的破平局。
    """
    if len(votes) == 0:
        raise ValueError("strict_majority requires at least one vote")
    counts: dict = {}
    for vote in votes:
        if vote is None:
            continue
        counts[vote] = counts.get(vote, 0) + 1
    winners = [label for label, n in counts.items() if n >= threshold]
    return winners[0] if len(winners) == 1 else None
