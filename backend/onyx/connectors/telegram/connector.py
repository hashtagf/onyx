from collections.abc import Generator
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import requests

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.exceptions import CredentialInvalidError
from onyx.connectors.interfaces import (
    GenerateDocumentsOutput,
    PollConnector,
    SecondsSinceUnixEpoch,
)
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    HierarchyNode,
    ImageSection,
    TextSection,
)
from onyx.file_store.staging import RawFileCallback
from onyx.utils.logger import setup_logger

logger = setup_logger()

_TELEGRAM_API_BASE = "https://api.telegram.org"
_GET_UPDATES_CHUNK = 100
_HTTP_TIMEOUT_S = 30
_LONG_POLL_TIMEOUT_S = 55
# Message content fields the Bot API returns; checked in priority order.
_FILE_MEDIA_KEYS = ("document", "video", "animation", "audio", "voice", "video_note")


def _to_datetime(ts: int | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the effective message out of an update envelope."""
    message = update.get("message") or update.get("edited_message")
    if isinstance(message, dict) and message:
        return message
    return None


def _chat_description(message: dict[str, Any]) -> str:
    chat = message.get("chat") or {}
    title = chat.get("title")
    if title:
        prefix = {"group": "group", "supergroup": "group", "channel": "channel"}
        chat_type = str(chat.get("type") or "")
        label = prefix.get(chat_type, chat_type)
        return f"{label}: {title}"
    peer_id = chat.get("id")
    if peer_id is not None:
        return f"chat {peer_id}"
    return "unknown chat"


def _sender_name(message: dict[str, Any]) -> str | None:
    sender = message.get("from") or {}
    name = " ".join(
        part for part in (sender.get("first_name"), sender.get("last_name")) if part
    ).strip()
    if name:
        return name
    username = sender.get("username")
    if username:
        return f"@{username}"
    return None


def _message_text(message: dict[str, Any]) -> str:
    """Best-effort text of a message: plain text, caption, or a type marker."""
    text = message.get("text") or message.get("caption")
    if text:
        return str(text)

    for key in _FILE_MEDIA_KEYS:
        if message.get(key):
            return f"[{key} message]"
    if "sticker" in message:
        return "[sticker]"
    if "poll" in message:
        poll = message.get("poll") or {}
        question = poll.get("question")
        return f"[poll: {question}]" if question else "[poll]"
    if "location" in message and message.get("venue"):
        venue = message.get("venue") or {}
        return f"[location: {venue.get('title') or 'unknown'}]"
    if "location" in message:
        return "[location]"
    if "contact" in message:
        contact = message.get("contact") or {}
        name = " ".join(
            k for k in (contact.get("first_name"), contact.get("last_name")) if k
        ).strip()
        return f"[contact: {name or 'unknown'}]"
    if "dice" in message:
        return "[dice roll]"
    if "new_speech" in message:
        return "[voice message]"
    if "invoice" in message:
        return "[invoice]"
    if "game" in message:
        return "[game]"
    return "[message]"


def _chat_link(message: dict[str, Any]) -> str | None:
    """t.me deep link when the chat has a public username."""
    chat = message.get("chat") or {}
    username = chat.get("username")
    if not username or not message.get("message_id"):
        return None
    return f"https://t.me/{username}/{message['message_id']}"


class TelegramConnector(PollConnector):
    """Indexes messages the bot receives via the Telegram Bot API.

    The Bot API has no message-history endpoint: the bot only sees updates
    delivered to it (chats it was added to and users who start it), exposed
    through ``getUpdates``. Each run drains the queue; updates not consumed
    within ~24h are dropped by Telegram, so keep the refresh frequency below
    that. Document IDs are stable by ``update_id``, so re-fetching is a no-op.
    """

    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._bot_token: str | None = None
        self._session: requests.Session | None = None
        self._raw_file_callback: RawFileCallback | None = None

    @property
    def bot_token(self) -> str:
        if self._bot_token is None:
            raise ConnectorMissingCredentialError("Telegram")
        return self._bot_token

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._bot_token = credentials["telegram_bot_token"]
        return None

    def set_raw_file_callback(self, callback: RawFileCallback) -> None:
        self._raw_file_callback = callback

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _api(self, method: str, **params: Any) -> Any:
        response = self._get_session().post(
            f"{_TELEGRAM_API_BASE}/bot{self.bot_token}/{method}",
            json=params,
            timeout=_HTTP_TIMEOUT_S + _LONG_POLL_TIMEOUT_S,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            error_code = body.get("error_code")
            description = body.get("description", "unknown error")
            if error_code == 401:
                raise CredentialInvalidError(
                    f"Invalid Telegram bot token: {description}"
                )
            raise Exception(f"Telegram Bot API error {error_code}: {description}")
        return body["result"]

    def validate_connector_settings(self) -> None:
        me = self._api("getMe")
        logger.info("Validated Telegram bot @%s", me.get("username"))

    def _fetch_updates(self) -> Generator[dict[str, Any], None, None]:
        """Drain the queued getUpdates queue. Updates left in the queue carry
        their original timestamps, so no backfill is possible on first connect.
        """
        while True:
            updates: list[dict[str, Any]] = self._api(
                "getUpdates",
                limit=_GET_UPDATES_CHUNK,
                timeout=_LONG_POLL_TIMEOUT_S,
            )
            if not updates:
                return
            yield from updates
            if len(updates) < _GET_UPDATES_CHUNK:
                return

    def _stage_media(
        self, message: dict[str, Any], update_id: int
    ) -> ImageSection | None:
        """Download a media file via getFile and stage it through the raw-file
        callback. Returns None when no callback is wired or the download fails.
        """
        if self._raw_file_callback is None:
            return None
        for key in _FILE_MEDIA_KEYS:
            media = message.get(key)
            if not isinstance(media, dict) or not media.get("file_id"):
                continue
            file_id = str(media["file_id"])
            filename = str(media.get("file_name") or f"telegram_{key}_{update_id}")
            try:
                file_info = self._api("getFile", file_id=file_id)
                file_path = file_info.get("file_path")
                if not file_path:
                    # Large files (>20MB) cannot be downloaded via the Bot API.
                    return None
                url = f"{_TELEGRAM_API_BASE}/file/bot{self.bot_token}/{file_path}"
                with self._get_session().get(url, timeout=_HTTP_TIMEOUT_S + 60) as resp:
                    resp.raise_for_status()
                    file_id_out = self._raw_file_callback(
                        BytesIO(resp.content), filename
                    )
                return ImageSection(image_file_id=file_id_out, link=_chat_link(message))
            except Exception:
                logger.warning(
                    "Skipping Telegram media %s/%s: %s",
                    key,
                    file_id,
                    "download or staging failed",
                    exc_info=True,
                )
                return None
        return None

    def _convert_update(self, update: dict[str, Any]) -> Document | None:
        message = _extract_message(update)
        update_id = update.get("update_id")
        if message is None or update_id is None:
            return None

        chat_desc = _chat_description(message)
        sender = _sender_name(message)
        text = _message_text(message)
        created_at = _to_datetime(message.get("date"))
        link = _chat_link(message)

        # Keep the semantic identifier short: truncate long messages to a
        # 30-char snippet + ellipsis.
        snippet = text[:30] if len(text) <= 30 else text[:27].rstrip() + "..."
        title = ""
        if sender:
            semantic_identifier = f"{sender} said in {chat_desc}: {snippet}"
        else:
            semantic_identifier = f"Message in {chat_desc}: {snippet}"

        sections: list[TextSection | ImageSection] = [TextSection(text=text, link=link)]
        if (media_section := self._stage_media(message, int(update_id))) is not None:
            sections.append(media_section)

        metadata: dict[str, str | list[str]] = {"Chat": chat_desc}
        if sender:
            metadata["Sender"] = sender

        return Document(
            id=f"TELEGRAM_{update_id}",
            source=DocumentSource.TELEGRAM,
            semantic_identifier=semantic_identifier,
            title=title,
            sections=sections,
            metadata=metadata,
            doc_created_at=created_at,
            doc_updated_at=created_at,
        )

    def _drain_updates_as_batches(self) -> GenerateDocumentsOutput:
        batch: list[Document | HierarchyNode] = []
        for update in self._fetch_updates():
            document = self._convert_update(update)
            if document is None:
                continue
            batch.append(document)
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def poll_source(
        self,
        start: SecondsSinceUnixEpoch,  # noqa: ARG002
        end: SecondsSinceUnixEpoch,  # noqa: ARG002
    ) -> GenerateDocumentsOutput:
        # start/end define Onyx's poll window; the Bot API cannot backfill, so
        # the queue simply contains what has been missed.
        return self._drain_updates_as_batches()

    def load_from_state(self) -> GenerateDocumentsOutput:
        return self._drain_updates_as_batches()
