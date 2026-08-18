"""Unit tests for the LINE connector.

The Messaging API is faked at the `requests.Session` boundary. Coverage:
credential handling, token validation, follower pagination, document
conversion, profile failure tolerance, and slim (ID-only) retrieval.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from onyx.configs.constants import DocumentSource
from onyx.connectors.exceptions import CredentialInvalidError
from onyx.connectors.line import connector as line_connector
from onyx.connectors.line.connector import LineConnector
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    SlimDocument,
    TextSection,
)

_PROFILE = {
    "displayName": "Ada Lovelace",
    "userId": "Ua1b2c3d4",
    "language": "en",
    "pictureUrl": "https://profile.example.com/a.png",
    "statusMessage": "Computing",
}


class _FakeResponse:
    def __init__(self, json_payload: Any = None, status_code: int = 200) -> None:
        self._json = json_payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, user_ids: list[str], fail_user_id: str | None = None) -> None:
        self._user_ids = list(user_ids)
        self._next_tokens = iter(list(_chunk(list(user_ids), 2)))
        self.fail_user_id = fail_user_id
        self.get_calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.get_calls.append((url, kwargs))
        if url.endswith("/v2/bot/info"):
            return _FakeResponse({"displayName": "TestBot", "userId": "Ubot1"})
        if url.endswith("/v2/bot/followers/ids"):
            user_ids = next(self._next_tokens, [])
            return _FakeResponse(
                {
                    "userIds": user_ids,
                    "next": f"next-{len(self.get_calls)}"
                    if len(user_ids) == 2
                    else None,
                }
            )
        if "/v2/bot/profile/" in url:
            user_id = url.rsplit("/", 1)[-1]
            if user_id == self.fail_user_id:
                raise Exception("network down")
            return _FakeResponse({**_PROFILE, "userId": user_id})
        return _FakeResponse({})


def _chunk(items: list[str], size: int) -> Any:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _install_fake_session(
    monkeypatch: pytest.MonkeyPatch,
    user_ids: list[str],
    fail_user_id: str | None = None,
) -> _FakeSession:
    session = _FakeSession(user_ids, fail_user_id=fail_user_id)

    class _FakeRequests:
        Session = _FakeSession

    fake = MagicMock()
    fake.Session = lambda: session
    monkeypatch.setattr(line_connector, "requests", fake)
    return session


def _make_connector(batch_size: int = 10) -> LineConnector:
    connector = LineConnector(batch_size=batch_size)
    connector.load_credentials({"line_channel_access_token": "test-token"})
    return connector


@pytest.fixture
def connector(monkeypatch: pytest.MonkeyPatch) -> LineConnector:
    c = _make_connector()
    _install_fake_session(monkeypatch, user_ids=["U1", "U2", "U3"])
    return c


def test_missing_credentials_raises() -> None:
    c = LineConnector()
    with pytest.raises(ConnectorMissingCredentialError):
        _ = c.channel_access_token


def test_validate_connector_settings_calls_bot_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _make_connector()
    session = _install_fake_session(monkeypatch, user_ids=[])
    c.validate_connector_settings()
    assert any(url.endswith("/v2/bot/info") for url, _ in session.get_calls)


def test_validate_invalid_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_connector()

    class _BadRequests:
        class Session:
            def get(self, url: str, **kwargs: Any) -> _FakeResponse:  # noqa: ARG002
                if url.endswith("/v2/bot/info"):
                    return _FakeResponse({}, status_code=401)
                return _FakeResponse({})

    monkeypatch.setattr(line_connector, "requests", _BadRequests())
    with pytest.raises(CredentialInvalidError):
        c.validate_connector_settings()


def test_load_from_state_yields_follower_documents(connector: LineConnector) -> None:
    docs: list[Document] = []
    for batch in connector.load_from_state():
        docs.extend(doc for doc in batch if isinstance(doc, Document))

    assert len(docs) == 3
    ids = {d.id for d in docs}
    assert ids == {"LINE_U1", "LINE_U2", "LINE_U3"}
    assert all(d.source == DocumentSource.LINE for d in docs)

    doc = next(d for d in docs if d.id == "LINE_U1")
    assert doc.title == "Ada Lovelace"
    assert doc.semantic_identifier == "Ada Lovelace"
    assert isinstance(doc.sections[0], TextSection)
    assert "Ada Lovelace" in (doc.sections[0].text or "")
    assert doc.metadata["User ID"] == "U1"


def test_follower_pagination_uses_next_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _make_connector()
    session = _install_fake_session(monkeypatch, user_ids=["A", "B", "C", "D"])
    docs: list[Document] = []
    for batch in c.load_from_state():
        docs.extend(d for d in batch if isinstance(d, Document))

    assert len(docs) == 4
    followers_calls = [
        url
        for url, kwargs in session.get_calls
        if url.endswith("/v2/bot/followers/ids")
    ]
    assert len(followers_calls) >= 2
    # The first call has no start; a later call resumes via the first page's
    # next token (non-empty). Both are under the 2,000/s rate limit.
    start_params = [
        (kwargs.get("params") or {}).get("start")
        for _url, kwargs in session.get_calls
        if _url.endswith("/v2/bot/followers/ids")
    ]
    assert start_params[0] is None
    assert any(start is not None for start in start_params)


def test_profile_failure_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_connector()
    _install_fake_session(monkeypatch, user_ids=["Good", "Bad"], fail_user_id="Bad")

    docs: list[Document] = []
    for batch in c.load_from_state():
        docs.extend(d for d in batch if isinstance(d, Document))
    assert [d.id for d in docs] == ["LINE_Good"]


def test_load_from_state_empty_followers_yields_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _make_connector()
    _install_fake_session(monkeypatch, user_ids=[])
    docs: list[Document] = []
    for batch in c.load_from_state():
        docs.extend(d for d in batch if isinstance(d, Document))
    assert docs == []


def test_batching_respects_batch_size(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_connector(batch_size=2)
    _install_fake_session(monkeypatch, user_ids=["1", "2", "3"])
    batch_sizes = [len(b) for b in c.load_from_state()]
    assert batch_sizes == [2, 1]


def test_retrieve_all_slim_docs_yields_ids_only(
    connector: LineConnector,
) -> None:
    slim: list[SlimDocument] = []
    for batch in connector.retrieve_all_slim_docs():
        slim.extend(item for item in batch if isinstance(item, SlimDocument))
    assert [s.id for s in slim] == ["LINE_U1", "LINE_U2", "LINE_U3"]
