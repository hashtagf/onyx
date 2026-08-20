"""Unit tests for the Telegram bot's pure helpers."""

from onyx.onyxbot.telegram.client import TelegramBotRunner
from onyx.onyxbot.telegram.utils import split_message


def _make_runner() -> TelegramBotRunner:
    runner = TelegramBotRunner.__new__(TelegramBotRunner)
    runner._bot_id = 42
    runner._bot_username = "OnyxBot"
    return runner


# === split_message ===


def test_split_message_short_text_is_untouched() -> None:
    assert split_message("hello", 100) == ["hello"]


def test_split_message_prefers_paragraph_breaks() -> None:
    text = "a" * 90 + "\n\n" + "b" * 90
    chunks = split_message(text, 100)
    assert chunks == ["a" * 90, "b" * 90]


def test_split_message_hard_splits_unbreakable_text() -> None:
    text = "x" * 250
    chunks = split_message(text, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == text


def test_split_message_all_chunks_within_limit() -> None:
    text = ("word " * 100).strip()
    chunks = split_message(text, 60)
    assert all(len(c) <= 60 for c in chunks)


# === _is_invoked ===


def test_private_chat_is_always_invoked() -> None:
    runner = _make_runner()
    assert runner._is_invoked({}, "hello", "private") is True


def test_group_message_with_mention_is_invoked() -> None:
    runner = _make_runner()
    assert runner._is_invoked({}, "hey @OnyxBot what is up", "group") is True


def test_group_mention_is_case_insensitive() -> None:
    runner = _make_runner()
    assert runner._is_invoked({}, "hey @onyxbot", "supergroup") is True


def test_group_message_without_mention_is_not_invoked() -> None:
    runner = _make_runner()
    assert runner._is_invoked({}, "hello everyone", "group") is False


def test_reply_to_bot_message_is_invoked() -> None:
    runner = _make_runner()
    message = {"reply_to_message": {"from": {"id": 42}}}
    assert runner._is_invoked(message, "and this?", "group") is True


def test_reply_to_other_user_is_not_invoked() -> None:
    runner = _make_runner()
    message = {"reply_to_message": {"from": {"id": 7}}}
    assert runner._is_invoked(message, "sure", "group") is False


# === _strip_mention ===


def test_strip_mention_removes_bot_handle() -> None:
    runner = _make_runner()
    assert runner._strip_mention("@OnyxBot what is Onyx?") == "what is Onyx?"


def test_strip_mention_is_case_insensitive() -> None:
    runner = _make_runner()
    assert runner._strip_mention("@onyxbot hello") == "hello"


def test_strip_mention_without_mention_returns_trimmed_text() -> None:
    runner = _make_runner()
    assert runner._strip_mention("  plain question  ") == "plain question"
