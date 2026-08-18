"""Unit tests for the Telegram connector.

The Bot API is faked at the `requests.Session` boundary: no real network
calls. Coverage: credential handling, getUpdates drain + batching, document
conversion (text / group / channel + media), and media download failure.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from onyx.configs.constants import DocumentSource
from onyx.connectors.exceptions import CredentialInvalidError
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    ImageSection,
    TextSection,
)
from onyx.connectors.telegram import connector as telegram_connector
from onyx.connectors.telegram.connector import (
    TelegramConnector,
    _chat_description,
    _extract_message,
    _message_text,
    _sender_name,
)

_UPDATES: list[dict[str, Any]] = [
    {
        "update_id": 101,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "from": {"first_name": "Ada", "last_name": "L", "username": "ada"},
            "chat": {"id": 1, "type": "private"},
            "text": "hello telegram",
        },
    },
    {
        "update_id": 102,
        "message": {
            "message_id": 2,
            "date": 1700000001,
            "from": {
                "first_name": "Grace",
                "last_name": "Hopper",
                "username": "grace",
            },
            "chat": {"id": 2, "type": "group", "title": "eng-standup"},
            "text": "standup notes",
        },
    },
    {
        "update_id": 103,
        "message": {
            "message_id": 3,
            "date": 1700000002,
            "from": {"username": "admin"},
            "chat": {"id": 3, "type": "channel", "title": "announcements"},
            "document": {"file_id": "file-abc", "file_name": "report.pdf"},
            "caption": "quarterly report",
        },
    },
]


class _FakeApiResponse:
    def __init__(
        self,
        ok: bool,
        result: Any,
        error_code: int | None = None,
        description: str | None = None,
    ) -> None:
        self._ok = ok
        self._result = result
        self._error_code = error_code
        self._description = description

    def json(self) -> dict[str, Any]:
        return {
            "ok": self._ok,
            "result": self._result,
            "error_code": self._error_code,
            "description": self._description,
        }

    def raise_for_status(self) -> None:
        return None


class _FakeGetResponse:
    content = b"pdf-bytes"
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def __enter__(self) -> "_FakeGetResponse":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


class _FakeSession:
    def __init__(
        self,
        updates: list[dict[str, Any]],
        get_file_result: Any = None,
        file_error: Exception | None = None,
    ) -> None:
        self._updates = [dict(u) for u in updates]
        self._get_file_result = (
            {"file_path": "docs/report.pdf"}
            if get_file_result is None
            else get_file_result
        )
        self._file_error = file_error
        self.posted_urls: list[str] = []

    def post(self, url: str, **kwargs: Any) -> _FakeApiResponse:  # noqa: ARG002
        self.posted_urls.append(url)
        method = url.rsplit("/", 1)[-1]
        if method == "getMe":
            return _FakeApiResponse(True, {"id": 42, "username": "testbot"})
        if method == "getUpdates":
            page = self._updates[:100]
            self._updates = self._updates[100:]
            return _FakeApiResponse(True, page)
        if method == "getFile":
            if self._file_error is not None:
                raise self._file_error
            return _FakeApiResponse(True, self._get_file_result)
        raise AssertionError(f"unexpected Telegram method: {method}")

    def get(self, url: str, **kwargs: Any) -> _FakeGetResponse:  # noqa: ARG002
        return _FakeGetResponse()


def _install_fake_session(
    monkeypatch: pytest.MonkeyPatch,
    updates: list[dict[str, Any]] = _UPDATES,
    file_error: Exception | None = None,
) -> _FakeSession:
    session = _FakeSession(updates, file_error=file_error)

    class _FakeRequests:
        Session = _FakeSession

    fake_requests = MagicMock()
    fake_requests.Session = lambda: session
    monkeypatch.setattr(telegram_connector, "requests", fake_requests)
    return session


def _make_connector(batch_size: int = 10) -> TelegramConnector:
    connector = TelegramConnector(batch_size=batch_size)
    connector.load_credentials({"telegram_bot_token": "test-token"})
    return connector


def _run_poll(connector: TelegramConnector) -> list[Document]:
    docs: list[Document] = []
    for batch in connector.poll_source(0, 1_700_000_999):
        docs.extend(doc for doc in batch if isinstance(doc, Document))
    return docs


@pytest.fixture
def staged_files() -> dict[str, tuple[bytes, str]]:
    return {}


def _make_stage_callback(staged: dict[str, tuple[bytes, str]]) -> Any:
    def stage(content: Any, content_type: str) -> str:
        file_id = f"staged-{len(staged)}"
        staged[file_id] = (content.read(), content_type)
        return file_id

    return stage


@pytest.fixture
def connector(
    monkeypatch: pytest.MonkeyPatch, staged_files: dict[str, tuple[bytes, str]]
) -> TelegramConnector:
    c = _make_connector()
    c.set_raw_file_callback(_make_stage_callback(staged_files))
    _install_fake_session(monkeypatch)
    return c


def test_missing_credentials_raises() -> None:
    c = TelegramConnector()
    with pytest.raises(ConnectorMissingCredentialError):
        _ = c.bot_token


def test_validate_connector_settings_calls_get_me(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _make_connector()
    session = _install_fake_session(monkeypatch)
    c.validate_connector_settings()
    assert any(url.endswith("/getMe") for url in session.posted_urls)


def test_validate_invalid_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_connector()

    class _InvalidRequests:
        class Session:
            def post(self, url: str, **kwargs: Any) -> _FakeApiResponse:  # noqa: ARG002
                if url.endswith("/getMe"):
                    raise CredentialInvalidError("Invalid Telegram bot token: 401")
                return _FakeApiResponse(True, [])

    monkeypatch.setattr(telegram_connector, "requests", _InvalidRequests())
    with pytest.raises(CredentialInvalidError):
        c.validate_connector_settings()


def test_poll_source_yields_three_docs(connector: TelegramConnector) -> None:
    docs = _run_poll(connector)
    assert len(docs) == 3
    ids = {d.id for d in docs}
    assert ids == {"TELEGRAM_101", "TELEGRAM_102", "TELEGRAM_103"}
    assert all(d.source == DocumentSource.TELEGRAM for d in docs)


def test_first_doc_has_text_section(connector: TelegramConnector) -> None:
    docs = _run_poll(connector)
    doc101 = next(d for d in docs if d.id == "TELEGRAM_101")
    assert isinstance(doc101.sections[0], TextSection)
    assert doc101.sections[0].text == "hello telegram"
    assert doc101.doc_created_at is not None
    assert doc101.metadata.get("Chat") is not None


def test_media_doc_stages_file(
    connector: TelegramConnector, staged_files: dict[str, tuple[bytes, str]]
) -> None:
    docs = _run_poll(connector)
    doc103 = next(d for d in docs if d.id == "TELEGRAM_103")
    assert isinstance(doc103.sections[0], TextSection)
    assert doc103.sections[0].text == "quarterly report"
    assert len(doc103.sections) == 2
    assert isinstance(doc103.sections[1], ImageSection)
    assert len(staged_files) == 1
    file_id = doc103.sections[1].image_file_id
    assert staged_files[file_id] == (b"pdf-bytes", "report.pdf")


def test_load_from_state_yields_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_connector()
    c.set_raw_file_callback(_make_stage_callback({}))
    _install_fake_session(monkeypatch)
    docs: list[Document] = []
    for batch in c.load_from_state():
        docs.extend(doc for doc in batch if isinstance(doc, Document))
    assert len(docs) == 3


def test_batching_respects_batch_size(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_connector(batch_size=1)
    c.set_raw_file_callback(_make_stage_callback({}))
    _install_fake_session(monkeypatch)
    batch_sizes = [len(batch) for batch in c.poll_source(0, 1_700_000_999)]
    assert batch_sizes == [1, 1, 1]


def test_empty_updates_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_connector()
    _install_fake_session(monkeypatch, updates=[])
    assert _run_poll(c) == []


def test_media_download_failure_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    staged: dict[str, tuple[bytes, str]] = {}
    c = _make_connector()
    c.set_raw_file_callback(_make_stage_callback(staged))
    _install_fake_session(monkeypatch, file_error=Exception("network down"))
    docs = _run_poll(c)

    doc103 = next(d for d in docs if d.id == "TELEGRAM_103")
    # Media failed -> caption text section remains, no staged file.
    assert len(doc103.sections) == 1
    assert isinstance(doc103.sections[0], TextSection)
    assert staged == {}


def test_extract_message_handles_edited_message() -> None:
    update = {"update_id": 5, "edited_message": {"message_id": 9, "text": "edited"}}
    message = _extract_message(update)
    assert message is not None
    assert _message_text(message) == "edited"


def test_sender_name_prefers_full_name() -> None:
    message = {"from": {"first_name": "Ada", "last_name": "L", "username": "ada"}}
    assert _sender_name(message) == "Ada L"


def test_sender_name_falls_back_to_username() -> None:
    message = {"from": {"username": "anonymous"}}
    assert _sender_name(message) == "@anonymous"


def test_chat_description_for_group() -> None:
    message = {"chat": {"id": 1, "type": "group", "title": "eng"}}
    assert _chat_description(message) == "group: eng"


def test_media_message_text_placeholder_when_no_caption() -> None:
    message = {"document": {"file_id": "f", "file_name": "x.png"}}
    assert _message_text(message) == "[document message]"
