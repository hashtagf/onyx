"""LINE Messaging API connector.

Indexes the **follower roster** of a LINE Official Account: every user who
added the account as a friend becomes a directory entry (display name, status
message, picture). The Messaging API exposes no message-history endpoint
(messages are webhook-only), so this is a pull-based *load* source, not a
poll source.

Access requirements:
- A channel access token with the ``profile`` and ``chat_message.read`` scopes.
- The follower ID listing (``/v2/bot/followers/ids``) requires a
  *verified* or *premium* LINE Official Account.
"""

from collections.abc import Generator
from typing import Any

import requests

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.exceptions import CredentialInvalidError
from onyx.connectors.interfaces import (
    GenerateDocumentsOutput,
    GenerateSlimDocumentOutput,
    LoadConnector,
    SlimConnector,
)
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    HierarchyNode,
    SlimDocument,
    TextSection,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

_LINE_API_BASE = "https://api.line.me"
_FOLLOWERS_PAGE_SIZE = 1000
_HTTP_TIMEOUT_S = 30


class LineConnector(LoadConnector, SlimConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._channel_access_token: str | None = None
        self._session: requests.Session | None = None

    @property
    def channel_access_token(self) -> str:
        if self._channel_access_token is None:
            raise ConnectorMissingCredentialError("LINE")
        return self._channel_access_token

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._channel_access_token = credentials["line_channel_access_token"]
        return None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.channel_access_token}"}

    def validate_connector_settings(self) -> None:
        # /v2/bot/info returns 200 with bot info for any valid token, or 401
        # for an invalid one. This works for all account types (unlike the
        # follower listing, which needs a verified/premium account).
        try:
            response = self._get_session().get(
                f"{_LINE_API_BASE}/v2/bot/info",
                headers=self._headers(),
                timeout=_HTTP_TIMEOUT_S,
            )
            if response.status_code == 404:
                # Valid token but no bot info (rare); treat as valid anyway.
                return
            response.raise_for_status()
        except Exception as e:
            raise CredentialInvalidError(f"Invalid LINE channel access token: {e}")
        bot_info = response.json()
        logger.info("Validated LINE bot %s", bot_info.get("displayName", "unknown"))

    def _fetch_follower_id_pages(self) -> Generator[list[str], None, None]:
        """Yield pages of follower user IDs via /v2/bot/followers/ids.

        Pagination: repeat the request, passing the response's ``next``
        value as the ``start`` query param, until ``next`` is absent.
        """
        start: str | None = None
        while True:
            params: dict[str, Any] = {"limit": _FOLLOWERS_PAGE_SIZE}
            if start is not None:
                params["start"] = start
            response = self._get_session().get(
                f"{_LINE_API_BASE}/v2/bot/followers/ids",
                headers=self._headers(),
                params=params,
                timeout=_HTTP_TIMEOUT_S,
            )
            response.raise_for_status()
            body = response.json()
            page = [str(user_id) for user_id in body.get("userIds", [])]
            yield page

            next_token = body.get("next")
            if next_token is None:
                return
            start = str(next_token)

    def _fetch_profile(self, user_id: str) -> dict[str, Any] | None:
        response = self._get_session().get(
            f"{_LINE_API_BASE}/v2/bot/profile/{user_id}",
            headers=self._headers(),
            timeout=_HTTP_TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json()

    def _profile_to_document(self, profile: dict[str, Any]) -> Document:
        user_id = str(profile.get("userId", ""))
        display_name = str(profile.get("displayName", user_id) or user_id)
        status_message = str(profile.get("statusMessage", "") or "")
        picture_url = str(profile.get("pictureUrl", "") or "")
        language = str(profile.get("language", "") or "")

        lines: list[str] = [f"LINE user: {display_name}"]
        if status_message:
            lines.append(f"Status message: {status_message}")
        if picture_url:
            lines.append(f"Profile picture: {picture_url}")
        if language:
            lines.append(f"Language: {language}")

        return Document(
            id=f"LINE_{user_id}",
            source=DocumentSource.LINE,
            semantic_identifier=display_name,
            title=display_name,
            sections=[TextSection(text="\n".join(lines))],
            metadata={
                "User ID": user_id,
                "Display Name": display_name,
                "Status Message": status_message or "(none)",
                "Picture URL": picture_url or "(none)",
                "Language": language or "(none)",
            },
        )

    def _load_documents(self) -> Generator[Document, None, None]:
        for page in self._fetch_follower_id_pages():
            for user_id in page:
                try:
                    profile = self._fetch_profile(user_id)
                except Exception:
                    logger.warning(
                        "Skipping LINE follower %s: profile fetch failed",
                        user_id,
                        exc_info=True,
                    )
                    continue
                if profile is None:
                    continue
                yield self._profile_to_document(profile)

    def _batched_documents(self) -> GenerateDocumentsOutput:
        batch: list[Document | HierarchyNode] = []
        for document in self._load_documents():
            batch.append(document)
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def load_from_state(self) -> GenerateDocumentsOutput:
        return self._batched_documents()

    def retrieve_all_slim_docs(
        self,
        start: Any = None,  # noqa: ARG002
        end: Any = None,  # noqa: ARG002
        callback: Any = None,  # noqa: ARG002
    ) -> GenerateSlimDocumentOutput:
        """ID-only pass for pruning, using the cheap follower listing."""
        batch: list[SlimDocument | HierarchyNode] = []
        for page in self._fetch_follower_id_pages():
            for user_id in page:
                batch.append(SlimDocument(id=f"LINE_{user_id}"))
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
