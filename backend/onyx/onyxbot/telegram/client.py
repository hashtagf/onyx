"""Telegram bot for Onyx.

Long-polls the Telegram Bot API (getUpdates) and answers messages with
responses from the Onyx chat API. Runs as a standalone supervisord program,
mirroring the Discord bot's design: a small process that talks to the API
server over HTTP with a service API key.

NOTE: Telegram allows only ONE getUpdates consumer per bot token. Use a
different bot for this integration than for the Telegram connector.
"""

import time
from typing import Any

import requests

from onyx.chat.models import ChatFullResponse
from onyx.db.engine.sql_engine import SqlEngine, get_session_with_tenant
from onyx.db.models import TelegramBotConfig, TelegramChatConfig
from onyx.db.telegram_bot import (
    get_or_create_telegram_service_api_key,
    get_telegram_bot_config,
    upsert_telegram_chat_config,
)
from onyx.onyxbot.telegram.constants import (
    API_REQUEST_TIMEOUT,
    DORMANT_LOG_EVERY,
    DORMANT_SLEEP_S,
    LONG_POLL_TIMEOUT,
    MAX_MESSAGE_LENGTH,
    MAX_SOURCES,
)
from onyx.onyxbot.telegram.utils import get_bot_token, split_message
from onyx.server.query_and_chat.models import (
    ChatSessionCreationRequest,
    MessageOrigin,
    SendMessageRequest,
)
from onyx.utils.logger import setup_logger
from onyx.utils.variable_functionality import (
    build_api_server_url_for_http_requests,
    set_is_ee_based_on_env_variable,
)
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA

logger = setup_logger()

_TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramAPIError(Exception):
    def __init__(self, status_code: int, description: str) -> None:
        self.status_code = status_code
        self.description = description
        super().__init__(f"Telegram API error {status_code}: {description}")


class TelegramBotRunner:
    """One polling run for a specific bot token. Returns from run() when the
    token changes, is deleted, or becomes invalid."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._offset: int | None = None
        self._bot_id: int | None = None
        self._bot_username: str | None = None
        self._api_key: str | None = None
        self._chat_api_base = build_api_server_url_for_http_requests(
            respect_env_override_if_set=True
        ).rstrip("/")

    # --- Telegram API helpers ---

    def _tg(
        self,
        method: str,
        payload: dict[str, object] | None = None,
        http_timeout: int = 30,
    ) -> Any:
        response = requests.post(
            f"{_TELEGRAM_API_BASE}/bot{self._token}/{method}",
            json=payload or {},
            timeout=http_timeout,
        )
        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(
                response.status_code, str(data.get("description", "unknown error"))
            )
        return data["result"]

    def _send_reply(self, chat_id: int, reply_to_message_id: int, text: str) -> None:
        for i, chunk in enumerate(split_message(text, MAX_MESSAGE_LENGTH)):
            params: dict[str, object] = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if i == 0:
                params["reply_to_message_id"] = reply_to_message_id
                params["allow_sending_without_reply"] = True
            try:
                self._tg("sendMessage", {**params, "parse_mode": "Markdown"})
            except TelegramAPIError:
                # Markdown parse failures return 400; resend as plain text
                self._tg("sendMessage", params)

    # --- Onyx chat API ---

    def _get_api_key(self, force_refresh: bool = False) -> str:
        if self._api_key and not force_refresh:
            return self._api_key
        with get_session_with_tenant(tenant_id=POSTGRES_DEFAULT_SCHEMA) as db:
            api_key = get_or_create_telegram_service_api_key(
                db, POSTGRES_DEFAULT_SCHEMA
            )
            db.commit()
        self._api_key = api_key
        return api_key

    def _answer(self, message_text: str, persona_id: int | None) -> ChatFullResponse:
        request = SendMessageRequest(
            message=message_text,
            stream=False,
            origin=MessageOrigin.TELEGRAMBOT,
            chat_session_info=ChatSessionCreationRequest(
                persona_id=persona_id if persona_id is not None else 0,
            ),
        )
        for attempt in range(2):
            response = requests.post(
                f"{self._chat_api_base}/chat/send-chat-message",
                json=request.model_dump(mode="json"),
                headers={"Authorization": f"Bearer {self._get_api_key()}"},
                timeout=API_REQUEST_TIMEOUT,
            )
            if response.status_code == 401 and attempt == 0:
                # Key may have been rotated or deleted; regenerate once
                self._get_api_key(force_refresh=True)
                continue
            response.raise_for_status()
            return ChatFullResponse.model_validate(response.json())
        raise RuntimeError("unreachable")

    # --- Message handling ---

    def _chat_display_name(self, chat: dict[str, Any]) -> str:
        if chat.get("title"):
            return str(chat["title"])
        parts = [chat.get("first_name"), chat.get("last_name")]
        name = " ".join(p for p in parts if p)
        if name:
            return name
        if chat.get("username"):
            return f"@{chat['username']}"
        return str(chat.get("id", "unknown"))

    def _is_invoked(self, message: dict[str, Any], text: str, chat_type: str) -> bool:
        """True when the bot should treat the message as directed at it."""
        if chat_type == "private":
            return True
        if self._bot_username and f"@{self._bot_username}".lower() in text.lower():
            return True
        reply = message.get("reply_to_message")
        if reply and reply.get("from", {}).get("id") == self._bot_id:
            return True
        return False

    def _strip_mention(self, text: str) -> str:
        if not self._bot_username:
            return text.strip()
        mention = f"@{self._bot_username}"
        # Case-insensitive removal of the mention
        lowered = text.lower()
        needle = mention.lower()
        result = []
        i = 0
        while True:
            idx = lowered.find(needle, i)
            if idx == -1:
                result.append(text[i:])
                break
            result.append(text[i:idx])
            i = idx + len(needle)
        return "".join(result).strip()

    def _append_citations(self, answer: str, response: ChatFullResponse) -> str:
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
        for num, name, link in cited_docs[:MAX_SOURCES]:
            if link:
                citations += f"{num}. {name} — {link}\n"
            else:
                citations += f"{num}. {name}\n"
        return answer + citations

    def _load_configs(
        self, chat: dict
    ) -> tuple[TelegramBotConfig | None, TelegramChatConfig]:
        """Upsert the chat row and return detached copies of both configs."""
        with get_session_with_tenant(tenant_id=POSTGRES_DEFAULT_SCHEMA) as db:
            bot_config = get_telegram_bot_config(db)
            chat_config = upsert_telegram_chat_config(
                db,
                chat_id=int(chat["id"]),
                chat_name=self._chat_display_name(chat),
                chat_type=str(chat.get("type", "private")),
            )
            db.commit()
            db.refresh(chat_config)
            db.expunge(chat_config)
            if bot_config is not None:
                db.refresh(bot_config)
                db.expunge(bot_config)
        return bot_config, chat_config

    def _handle_message(self, message: dict[str, Any]) -> None:
        text = message.get("text") or message.get("caption")
        chat = message.get("chat")
        sender = message.get("from", {})
        if not text or not chat or sender.get("is_bot"):
            return

        bot_config, chat_config = self._load_configs(chat)
        if bot_config is None or not chat_config.enabled:
            return

        chat_type = str(chat.get("type", "private"))
        if chat_type != "private" and chat_config.require_bot_invocation:
            if not self._is_invoked(message, text, chat_type):
                return

        question = self._strip_mention(text)
        if not question:
            return

        persona_id = chat_config.persona_override_id or bot_config.default_persona_id

        chat_id = int(chat["id"])
        message_id = int(message["message_id"])
        try:
            self._tg("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except TelegramAPIError:
            pass

        try:
            response = self._answer(question, persona_id)
        except Exception as e:
            logger.error("Chat API request failed: %s", e)
            self._send_reply(
                chat_id,
                message_id,
                "Sorry, something went wrong while generating an answer.",
            )
            return

        answer = response.answer or "I could not find an answer to that."
        answer = self._append_citations(answer, response)
        self._send_reply(chat_id, message_id, answer)

    # --- Polling loop ---

    def run(self) -> None:
        me = self._tg("getMe")
        self._bot_id = me["id"]
        self._bot_username = me.get("username")
        logger.info("Telegram bot connected as @%s", self._bot_username)

        while True:
            try:
                updates = self._tg(
                    "getUpdates",
                    {
                        "offset": self._offset,
                        "allowed_updates": ["message"],
                        "timeout": LONG_POLL_TIMEOUT,  # Telegram long-poll param
                    },
                    http_timeout=LONG_POLL_TIMEOUT + 10,
                )
            except TelegramAPIError as e:
                if e.status_code == 401:
                    logger.error("Telegram bot token is invalid; going dormant")
                    return
                if e.status_code == 409:
                    logger.error(
                        "Another getUpdates consumer is using this bot token "
                        "(likely the Telegram connector). Use a separate bot "
                        "for the integration. Retrying in 30s."
                    )
                    time.sleep(30)
                    continue
                logger.error("getUpdates failed: %s", e)
                time.sleep(5)
                continue
            except requests.RequestException as e:
                logger.error("getUpdates network error: %s", e)
                time.sleep(5)
                continue

            for update in updates:
                self._offset = update["update_id"] + 1
                message = update.get("message")
                if not message:
                    continue
                try:
                    self._handle_message(message)
                except Exception:
                    logger.exception("Failed to handle Telegram message")

            # Token changed or config disabled -> hand control back to main()
            current_token = get_bot_token()
            if current_token != self._token:
                logger.info("Telegram bot token changed or removed; restarting")
                return


def main() -> None:
    SqlEngine.init_engine(pool_size=5, max_overflow=2)
    set_is_ee_based_on_env_variable()

    logger.info("Starting Telegram bot")
    dormant_probes = 0
    while True:
        token = get_bot_token()
        if not token:
            if dormant_probes % DORMANT_LOG_EVERY == 0:
                logger.info("Telegram bot dormant: no bot token configured")
            dormant_probes += 1
            time.sleep(DORMANT_SLEEP_S)
            continue

        dormant_probes = 0
        try:
            TelegramBotRunner(token).run()
        except TelegramAPIError as e:
            logger.error("Telegram API error: %s", e)
        except Exception:
            logger.exception("Telegram bot crashed; restarting")
        time.sleep(DORMANT_SLEEP_S)


if __name__ == "__main__":
    main()
