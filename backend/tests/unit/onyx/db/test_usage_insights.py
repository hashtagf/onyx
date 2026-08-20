"""Unit tests for CSV export row formatting."""

from datetime import datetime, timezone

from onyx.configs.constants import MessageType
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
    assert row == [
        "2026-08-21T10:00:00+00:00",
        "user@example.com",
        "Assistant",
        "user",
        "42",
        "gpt-5-mini",
        "hello",
    ]


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
    assert row[1:] == ["", "", "ASSISTANT", "0", "", ""]


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
    assert len(row[6]) == 2001
    assert row[6].endswith("…")
