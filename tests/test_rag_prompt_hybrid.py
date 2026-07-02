from __future__ import annotations

from unittest.mock import MagicMock


def test_build_system_prompt_hybrid_mode_calls_option_evidence():
    from rag_prompt_builder import build_system_prompt

    mock_index = MagicMock()
    mock_index.option_evidence.return_value = {
        "A": [{"person_id": "p1", "fact_excerpt": "fact", "score": 1.0, "match_reasons": [], "stance": "related", "source_domain": "career", "source_answer_option_text": ""}],
        "B": [],
        "C": [],
        "D": [],
    }

    prompt = build_system_prompt(
        base_system="base",
        chart={"query_domain": "career", "query_text": "问事业", "four_pillars": {}},
        case_index=mock_index,
        enable_rag=True,
        retrieval_mode="option_grounded_hybrid",
        question="问事业",
        options=["A. 升职", "B. 跳槽", "C. 稳定", "D. 转行"],
        option_evidence_k=1,
    )
    mock_index.option_evidence.assert_called_once()
    call_kwargs = mock_index.option_evidence.call_args.kwargs
    assert call_kwargs.get("retrieval_mode") == "option_grounded_hybrid"
    assert "<选项证据>" in prompt
