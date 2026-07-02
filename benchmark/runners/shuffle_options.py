from __future__ import annotations

import copy
import random
from typing import Any, Dict, List, Optional


_LABELS = ("A", "B", "C", "D")


def _strip_prefix(option_text: str) -> str:
    text = str(option_text or "")
    if len(text) >= 2 and text[0].upper() in _LABELS and text[1] in {".", "、", ")", "．"}:
        return text[2:].lstrip()
    return text.lstrip()


def _relabel(option_body: str, new_label: str) -> str:
    return f"{new_label}. {option_body}"


def shuffle_options(row: Dict[str, Any], seed: Optional[int]) -> Dict[str, Any]:
    if seed is None:
        raise ValueError("shuffle_options requires an explicit int seed for reproducibility")
    if not isinstance(seed, int):
        raise ValueError(f"shuffle_options seed must be int, got {type(seed).__name__}")

    original_options: List[str] = list(row.get("options") or [])
    original_answer: str = str(row.get("answer") or "")

    indices = list(range(len(original_options)))
    rng = random.Random(seed)
    rng.shuffle(indices)

    new_options: List[str] = []
    label_map: Dict[str, str] = {}
    for new_idx, original_idx in enumerate(indices):
        new_label = _LABELS[new_idx] if new_idx < len(_LABELS) else chr(ord("A") + new_idx)
        body = _strip_prefix(original_options[original_idx])
        new_options.append(_relabel(body, new_label))
        old_label = _LABELS[original_idx] if original_idx < len(_LABELS) else chr(ord("A") + original_idx)
        label_map[old_label] = new_label

    new_answer = label_map.get(original_answer, original_answer)

    shuffled = copy.deepcopy(row)
    shuffled["options"] = new_options
    shuffled["answer"] = new_answer
    shuffled["answer_label_map"] = label_map
    shuffled["_original_options"] = list(original_options)
    shuffled["_original_answer"] = original_answer
    return shuffled


def unshuffle_predicted_answer(
    predicted: Optional[str],
    answer_label_map: Dict[str, str],
) -> Optional[str]:
    if predicted is None:
        return None
    reverse_map = {new: old for old, new in (answer_label_map or {}).items()}
    return reverse_map.get(predicted, predicted)
