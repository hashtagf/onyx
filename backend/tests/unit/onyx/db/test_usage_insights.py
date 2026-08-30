"""Unit tests for CSV export row formatting."""

from datetime import datetime, timezone

from onyx.configs.constants import MessageType
from onyx.db.models import ChatMessageQualityEvaluation
from onyx.db.usage_insights import format_export_row


def test_row_basic_fields() -> None:
    row = format_export_row(
        datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc),
        "user@example.com",
        "Assistant",
        MessageType.USER,
        42,
        "gpt-5-mini",
        "hello",
    )
    assert row[:6] == [
        "2026-08-21T10:00:00+00:00",
        "user@example.com",
        "Assistant",
        "user",
        "42",
        "gpt-5-mini",
    ]
    assert row[-1] == "hello"


def test_row_handles_missing_values() -> None:
    row = format_export_row(
        datetime(2026, 8, 21, tzinfo=timezone.utc),
        None,
        None,
        "ASSISTANT",
        None,
        None,
        None,
    )
    assert row[1:6] == ["", "", "ASSISTANT", "0", ""]
    assert row[-1] == ""


def test_row_truncates_long_messages() -> None:
    row = format_export_row(
        datetime(2026, 8, 21, tzinfo=timezone.utc),
        None,
        None,
        MessageType.ASSISTANT,
        1,
        None,
        "x" * 5000,
    )
    assert len(row[-1]) == 2001
    assert row[-1].endswith("…")


def test_row_includes_quality_evaluation() -> None:
    evaluation = ChatMessageQualityEvaluation(
        evaluation_source="human",
        task_success=True,
        first_answer_resolution=True,
        required_rephrase=False,
        correctness=5,
        relevance=4,
        completeness=3,
        clarity=4,
        instruction_following=5,
        grounded=True,
        hallucination_detected=False,
    )
    row = format_export_row(
        datetime(2026, 8, 21, tzinfo=timezone.utc),
        None,
        None,
        MessageType.ASSISTANT,
        1,
        "model",
        "answer",
        processing_duration_seconds=1.25,
        citation_count=2,
        feedback=True,
        evaluation=evaluation,
    )

    assert row[6:16] == [
        "1.25",
        "",
        "2",
        "true",
        "human",
        "",
        "true",
        "true",
        "false",
        "4.25",
    ]
    assert row[-1] == "answer"
