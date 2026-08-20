"""LINE Messaging API webhook.

LINE delivers messages to bots only via webhook — there is no polling API.
This router receives events, verifies the X-Line-Signature HMAC, returns 200
immediately, and answers in a background task through the Onyx chat API
(mirroring the Discord bot's HTTP-based answer path).

The deployment must expose this endpoint on a public HTTPS URL and that URL
must be set as the webhook URL in the LINE Developers console:
    https://<your-domain>/api/line/webhook
"""

import base64
import hashlib
import hmac
import json
from typing import Any, cast

import requests
from fastapi import APIRouter, BackgroundTasks, Request

from onyx.chat.models import ChatFullResponse
from onyx.configs.app_configs import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET
from onyx.db.engine.sql_engine import get_session_with_tenant
from onyx.db.line_bot import get_line_bot_config, get_or_create_line_service_api_key
from onyx.db.models import LineBotConfig
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.query_and_chat.models import (
    ChatSessionCreationRequest,
    MessageOrigin,
    SendMessageRequest,
)
from onyx.utils.logger import setup_logger
from onyx.utils.sensitive import SensitiveValue
from onyx.utils.variable_functionality import build_api_server_url_for_http_requests
from shared_configs.configs import MULTI_TENANT, POSTGRES_DEFAULT_SCHEMA

logger = setup_logger()

router = APIRouter()

_LINE_API_BASE = "https://api.line.me"

# LINE text message hard limit
_MAX_MESSAGE_LENGTH = 5000
# LINE allows at most 5 message objects per reply/push call
_MAX_MESSAGES_PER_CALL = 5
# Seconds to wait for the Onyx chat API to answer
_API_REQUEST_TIMEOUT = 180
# Max source links appended to an answer
_MAX_SOURCES = 5

# Cached raw service API key (regenerated on 401)
_api_key_cache: str | None = None


class _LineCredentials:
    def __init__(self, access_token: str, secret: str) -> None:
        self.access_token = access_token
        self.secret = secret


def _unwrap(value: SensitiveValue[str] | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, SensitiveValue):
        return cast(str, value.get_value(apply_mask=False))
    return value


def _get_credentials_and_config() -> tuple[
    _LineCredentials | None, LineBotConfig | None
]:
    """Resolve LINE credentials (env vars win) and the behavior config."""
    with get_session_with_tenant(tenant_id=POSTGRES_DEFAULT_SCHEMA) as db:
        config = get_line_bot_config(db)
        if config is not None:
            db.refresh(config)
            db.expunge(config)

    if LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET:
        return (
            _LineCredentials(LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET),
            config,
        )

    if config is None:
        return None, None

    access_token = _unwrap(config.channel_access_token)
    secret = _unwrap(config.channel_secret)
    if not access_token or not secret:
        return None, config
    return _LineCredentials(access_token, secret), config


def verify_line_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Verify the X-Line-Signature header for a webhook body."""
    if not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


# --- LINE Messaging API helpers ---


def _line_post(path: str, access_token: str, payload: dict[str, object]) -> None:
    response = requests.post(
        f"{_LINE_API_BASE}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"LINE API {path} failed ({response.status_code}): {response.text}"
        )


def _split_message(text: str, max_length: int) -> list[str]:
    if len(text) <= max_length:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        window = remaining[:max_length]
        split_at = -1
        for sep in ("\n\n", "\n", ". ", " "):
            idx = window.rfind(sep)
            if idx > 0:
                split_at = idx + len(sep)
                break
        if split_at <= 0:
            split_at = max_length
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _send_answer(
    credentials: _LineCredentials,
    reply_token: str | None,
    target_id: str | None,
    text: str,
) -> None:
    """Reply with the reply token; fall back to push (tokens expire fast)."""
    messages = [
        {"type": "text", "text": chunk}
        for chunk in _split_message(text, _MAX_MESSAGE_LENGTH)[:_MAX_MESSAGES_PER_CALL]
    ]
    if reply_token:
        try:
            _line_post(
                "/v2/bot/message/reply",
                credentials.access_token,
                {"replyToken": reply_token, "messages": messages},
            )
            return
        except RuntimeError as e:
            logger.warning("LINE reply failed, falling back to push: %s", e)
    if target_id:
        _line_post(
            "/v2/bot/message/push",
            credentials.access_token,
            {"to": target_id, "messages": messages},
        )


# --- Onyx chat API ---


def _get_service_api_key(force_refresh: bool = False) -> str:
    global _api_key_cache
    if _api_key_cache and not force_refresh:
        return _api_key_cache
    with get_session_with_tenant(tenant_id=POSTGRES_DEFAULT_SCHEMA) as db:
        api_key = get_or_create_line_service_api_key(db, POSTGRES_DEFAULT_SCHEMA)
        db.commit()
    _api_key_cache = api_key
    return api_key


def _answer(message_text: str, persona_id: int | None) -> ChatFullResponse:
    base_url = build_api_server_url_for_http_requests(
        respect_env_override_if_set=True
    ).rstrip("/")
    request = SendMessageRequest(
        message=message_text,
        stream=False,
        origin=MessageOrigin.LINEBOT,
        chat_session_info=ChatSessionCreationRequest(
            persona_id=persona_id if persona_id is not None else 0,
        ),
    )
    for attempt in range(2):
        response = requests.post(
            f"{base_url}/chat/send-chat-message",
            json=request.model_dump(mode="json"),
            headers={"Authorization": f"Bearer {_get_service_api_key()}"},
            timeout=_API_REQUEST_TIMEOUT,
        )
        if response.status_code == 401 and attempt == 0:
            _get_service_api_key(force_refresh=True)
            continue
        response.raise_for_status()
        return ChatFullResponse.model_validate(response.json())
    raise RuntimeError("unreachable")


def _append_citations(answer: str, response: ChatFullResponse) -> str:
    if not response.citation_info or not response.top_documents:
        return answer

    cited_docs: list[tuple[int, str, str | None]] = []
    for citation in response.citation_info:
        doc = next(
            (
                d
                for d in response.top_documents
                if d.document_id == citation.document_id
            ),
            None,
        )
        if doc:
            cited_docs.append(
                (
                    citation.citation_number,
                    doc.semantic_identifier or "Source",
                    doc.link,
                )
            )

    if not cited_docs:
        return answer

    cited_docs.sort(key=lambda x: x[0])
    citations = "\n\nSources:\n"
    for num, name, link in cited_docs[:_MAX_SOURCES]:
        if link:
            citations += f"{num}. {name} — {link}\n"
        else:
            citations += f"{num}. {name}\n"
    return answer + citations


# --- Event handling ---


def _extract_question(event: dict[str, Any], config: LineBotConfig) -> str | None:
    """Return the question text when the bot should answer, else None."""
    message = event.get("message", {})
    if message.get("type") != "text":
        return None
    text = str(message.get("text", ""))
    if not text.strip():
        return None

    source_type = event.get("source", {}).get("type")
    if source_type == "user":
        if not config.respond_to_dms:
            return None
        return text.strip()

    # group / room: check the mention gate
    mentionees = (message.get("mention") or {}).get("mentionees") or []
    self_mentions = [m for m in mentionees if m.get("isSelf")]
    if config.require_mention_in_groups and not self_mentions:
        return None

    # Strip the bot's own mention spans from the text (back to front)
    for m in sorted(self_mentions, key=lambda m: int(m.get("index", 0)), reverse=True):
        start = int(m.get("index", 0))
        length = int(m.get("length", 0))
        text = text[:start] + text[start + length :]
    return text.strip() or None


def process_line_events(body: dict[str, Any]) -> None:
    """Handle webhook events. Runs as a background task after the 200."""
    credentials, config = _get_credentials_and_config()
    if credentials is None or config is None or not config.enabled:
        return

    for event in body.get("events", []):
        if event.get("type") != "message":
            continue
        try:
            question = _extract_question(event, config)
            if not question:
                continue

            source = event.get("source", {})
            target_id = (
                source.get("groupId") or source.get("roomId") or source.get("userId")
            )

            try:
                response = _answer(question, config.default_persona_id)
                answer = response.answer or "I could not find an answer to that."
                answer = _append_citations(answer, response)
            except Exception as e:
                logger.error("Chat API request failed: %s", e)
                answer = "Sorry, something went wrong while generating an answer."

            _send_answer(credentials, event.get("replyToken"), target_id, answer)
        except Exception:
            logger.exception("Failed to handle LINE event")


@router.post("/line/webhook")
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """Receive LINE webhook events.

    Signature verification with the channel secret is the authentication for
    this endpoint; it is registered as public in auth_check.py.
    """
    if MULTI_TENANT:
        # Webhook receivers need tenant routing that does not exist yet
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Not available on Cloud")

    body = await request.body()

    credentials, _config = _get_credentials_and_config()
    if credentials is None:
        # Not configured yet. Answer 200 so the LINE console's "Verify"
        # button does not hard-fail before setup is complete.
        logger.warning("LINE webhook called but no credentials are configured")
        return {"ok": True}

    signature = request.headers.get("X-Line-Signature")
    if not verify_line_signature(body, signature, credentials.secret):
        raise OnyxError(OnyxErrorCode.UNAUTHENTICATED, "Invalid LINE signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Invalid JSON body")

    if payload.get("events"):
        background_tasks.add_task(process_line_events, payload)

    return {"ok": True}
