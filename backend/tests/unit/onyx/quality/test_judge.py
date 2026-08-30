from unittest.mock import MagicMock, patch

from onyx.db.chat_quality import ChatQualityReviewCandidate
from onyx.quality.judge import (
    MAX_ASSISTANT_MESSAGE_CHARS,
    MAX_CITATION_CHARS,
    MAX_CITATIONS,
    MAX_USER_MESSAGE_CHARS,
    build_quality_judge_prompt,
    evaluate_response_with_llm_judge,
)


def test_build_quality_judge_prompt_limits_untrusted_content() -> None:
    candidate = ChatQualityReviewCandidate(
        chat_message_id=1,
        user_message="u" * (MAX_USER_MESSAGE_CHARS + 100),
        assistant_message="a" * (MAX_ASSISTANT_MESSAGE_CHARS + 100),
        citation_blurbs=["c" * (MAX_CITATION_CHARS + 100)] * (MAX_CITATIONS + 2),
    )

    prompt = build_quality_judge_prompt(candidate)

    assert "u" * (MAX_USER_MESSAGE_CHARS + 1) not in prompt
    assert "a" * (MAX_ASSISTANT_MESSAGE_CHARS + 1) not in prompt
    assert f"Source {MAX_CITATIONS + 1}:" not in prompt


def test_evaluate_response_with_llm_judge_parses_complete_result() -> None:
    candidate = ChatQualityReviewCandidate(
        chat_message_id=1,
        user_message="Summarize the policy.",
        assistant_message="The policy requires approval.",
        citation_blurbs=["Approval is required."],
    )
    response_json = """{
      "confidence": 0.9,
      "task_category": "summary",
      "task_success": true,
      "first_answer_resolution": true,
      "required_rephrase": false,
      "correctness": 5,
      "relevance": 5,
      "completeness": 4,
      "clarity": 5,
      "instruction_following": 5,
      "grounded": true,
      "citation_accuracy": 5,
      "retrieval_relevance": 5,
      "hallucination_detected": false,
      "appropriate_refusal": null,
      "false_refusal": false,
      "harmful_response": false,
      "sensitive_data_leakage": false,
      "unauthorized_document_exposure": false,
      "policy_violation": false,
      "prompt_injection_succeeded": false,
      "notes": "The response matches the source."
    }"""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock()

    with (
        patch("onyx.quality.judge.llm_generation_span") as generation_span,
        patch("onyx.quality.judge.record_llm_response"),
        patch("onyx.quality.judge.llm_response_to_string", return_value=response_json),
    ):
        generation_span.return_value.__enter__.return_value = MagicMock()
        evaluation = evaluate_response_with_llm_judge(candidate, llm)

    assert evaluation.evaluation_source == "llm_judge"
    assert evaluation.confidence == 0.9
    assert evaluation.judge_version == "chat-quality-v1"
    assert evaluation.task_success is True
    assert evaluation.correctness == 5
    llm.invoke.assert_called_once()
