from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from ee.onyx.server.query_history.models import (
    QUERY_HISTORY_PREVIEW_MAX_CHARS,
    ChatSessionMinimal,
    truncate_query_history_preview,
)
from onyx.configs.constants import MessageType
from onyx.db.models import ChatSession


def test_truncate_query_history_preview_keeps_short_message() -> None:
    message = "Short answer"

    assert truncate_query_history_preview(message) == message


def test_chat_session_minimal_limits_large_message_previews() -> None:
    large_message = "a" * (QUERY_HISTORY_PREVIEW_MAX_CHARS + 100)
    chat_session = cast(
        ChatSession,
        SimpleNamespace(
            id=uuid4(),
            user=None,
            description=None,
            messages=[
                SimpleNamespace(
                    message=large_message,
                    message_type=MessageType.USER,
                    chat_message_feedbacks=[],
                ),
                SimpleNamespace(
                    message=large_message,
                    message_type=MessageType.ASSISTANT,
                    chat_message_feedbacks=[],
                ),
            ],
            persona_id=None,
            persona=None,
            time_created=datetime.now(timezone.utc),
            onyxbot_flow=False,
        ),
    )

    result = ChatSessionMinimal.from_chat_session(chat_session)

    assert len(result.first_user_message) == QUERY_HISTORY_PREVIEW_MAX_CHARS
    assert result.first_user_message.endswith("…")
    assert len(result.first_ai_message) == QUERY_HISTORY_PREVIEW_MAX_CHARS
    assert result.first_ai_message.endswith("…")
