"""Unit tests for the LINE webhook's signature check and event routing."""

import base64
import hashlib
import hmac

from onyx.db.models import LineBotConfig
from onyx.server.manage.line_bot.webhook import (
    _extract_question,
    verify_line_signature,
)


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _Config(
    respond_to_dms: bool = True,
    require_mention_in_groups: bool = True,
) -> LineBotConfig:
    return LineBotConfig(
        respond_to_dms=respond_to_dms,
        require_mention_in_groups=require_mention_in_groups,
    )


# === verify_line_signature ===


def test_valid_signature_passes() -> None:
    body = b'{"events": []}'
    secret = "channel-secret"
    assert verify_line_signature(body, _sign(body, secret), secret) is True


def test_invalid_signature_fails() -> None:
    body = b'{"events": []}'
    assert verify_line_signature(body, "not-a-signature", "channel-secret") is False


def test_missing_signature_fails() -> None:
    assert verify_line_signature(b"{}", None, "channel-secret") is False


def test_signature_for_different_body_fails() -> None:
    secret = "channel-secret"
    signature = _sign(b'{"events": []}', secret)
    assert verify_line_signature(b'{"events": [1]}', signature, secret) is False


# === _extract_question ===


def _dm_event(text: str) -> dict:
    return {
        "type": "message",
        "source": {"type": "user", "userId": "U1"},
        "message": {"type": "text", "text": text},
    }


def _group_event(text: str, mentionees: list[dict] | None = None) -> dict:
    message: dict = {"type": "text", "text": text}
    if mentionees is not None:
        message["mention"] = {"mentionees": mentionees}
    return {
        "type": "message",
        "source": {"type": "group", "groupId": "G1"},
        "message": message,
    }


def test_dm_returns_text() -> None:
    assert _extract_question(_dm_event("hello"), _Config()) == "hello"


def test_dm_disabled_returns_none() -> None:
    config = _Config(respond_to_dms=False)
    assert _extract_question(_dm_event("hello"), config) is None


def test_non_text_message_returns_none() -> None:
    event = {
        "type": "message",
        "source": {"type": "user"},
        "message": {"type": "image"},
    }
    assert _extract_question(event, _Config()) is None


def test_group_without_mention_returns_none() -> None:
    assert _extract_question(_group_event("hello all"), _Config()) is None


def test_group_with_self_mention_strips_mention() -> None:
    # "@Onyx what is up" — the mention span covers "@Onyx "
    event = _group_event(
        "@Onyx what is up",
        mentionees=[{"index": 0, "length": 6, "isSelf": True}],
    )
    assert _extract_question(event, _Config()) == "what is up"


def test_group_with_other_mention_returns_none() -> None:
    event = _group_event(
        "@Alice what is up",
        mentionees=[{"index": 0, "length": 7, "userId": "U9"}],
    )
    assert _extract_question(event, _Config()) is None


def test_group_mention_not_required_returns_text() -> None:
    config = _Config(require_mention_in_groups=False)
    assert _extract_question(_group_event("hello all"), config) == "hello all"


def test_empty_text_returns_none() -> None:
    assert _extract_question(_dm_event("   "), _Config()) is None
