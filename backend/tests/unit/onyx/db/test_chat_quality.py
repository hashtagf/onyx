import pytest
from pydantic import ValidationError

from onyx.db.chat_quality import (
    QualityEvaluationInput,
    _paired_evaluation_metrics,
    _quality_review_reasons,
    preferred_evaluations_by_message,
    weighted_answer_quality_score,
)
from onyx.db.models import ChatMessageQualityEvaluation


def test_weighted_answer_quality_score() -> None:
    assert weighted_answer_quality_score(5, 4, 3, 4, 5) == pytest.approx(4.25)


def test_quality_evaluation_accepts_complete_scores() -> None:
    evaluation = QualityEvaluationInput(
        correctness=5,
        relevance=4,
        completeness=3,
        clarity=4,
        instruction_following=5,
    )

    assert evaluation.correctness == 5


def test_quality_evaluation_rejects_partial_scores() -> None:
    with pytest.raises(ValidationError, match="all five"):
        QualityEvaluationInput(correctness=5)


def test_quality_evaluation_rejects_out_of_range_score() -> None:
    with pytest.raises(ValidationError):
        QualityEvaluationInput(
            correctness=6,
            relevance=4,
            completeness=3,
            clarity=4,
            instruction_following=5,
        )


def test_human_evaluation_takes_precedence_over_judge() -> None:
    judge = ChatMessageQualityEvaluation(
        chat_message_id=10,
        evaluation_source="llm_judge",
        task_success=False,
    )
    human = ChatMessageQualityEvaluation(
        chat_message_id=10,
        evaluation_source="human",
        task_success=True,
    )

    selected = preferred_evaluations_by_message([judge, human])

    assert selected[10] is human


def test_paired_metrics_compare_human_and_judge() -> None:
    judge = ChatMessageQualityEvaluation(
        chat_message_id=10,
        evaluation_source="llm_judge",
        task_success=True,
        correctness=4,
    )
    human = ChatMessageQualityEvaluation(
        chat_message_id=10,
        evaluation_source="human",
        task_success=True,
        correctness=5,
    )

    paired_count, agreement, score_error = _paired_evaluation_metrics([judge, human])

    assert paired_count == 1
    assert agreement.value == 100
    assert agreement.sample_size == 1
    assert score_error.value == 1
    assert score_error.sample_size == 1


def test_review_queue_prioritizes_safety_over_random_sample() -> None:
    evaluation = QualityEvaluationInput(
        evaluation_source="llm_judge",
        confidence=0.9,
        harmful_response=True,
    )

    priority, reasons = _quality_review_reasons(
        chat_message_id=1,
        evaluation=evaluation,
        feedback=None,
        sample_rate=1,
        high_risk_categories=set(),
    )

    assert priority == 100
    assert reasons == ["safety_incident", "random_sample"]
