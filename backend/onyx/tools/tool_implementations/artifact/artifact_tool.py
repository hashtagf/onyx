import hashlib
from io import BytesIO
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from typing_extensions import override

from onyx.chat.emitter import Emitter
from onyx.configs.app_configs import (
    ENABLE_CHAT_ARTIFACTS,
    MAX_CHAT_ARTIFACT_SIZE_BYTES,
)
from onyx.configs.constants import FileOrigin
from onyx.db.artifact import (
    create_artifact_revision__no_commit,
    create_chat_artifact__no_commit,
    get_artifact_for_owner,
)
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.file_store.file_store import get_default_file_store
from onyx.server.query_and_chat.placement import Placement
from onyx.server.query_and_chat.streaming_models import (
    ArtifactToolFinal,
    ArtifactToolStart,
    Packet,
)
from onyx.tools.interface import Tool
from onyx.tools.models import ToolCallException, ToolResponse
from onyx.tools.tool_implementations.artifact.models import ArtifactToolResponse


class ArtifactToolOverrideKwargs(BaseModel):
    pass


class ArtifactTool(Tool[ArtifactToolOverrideKwargs]):
    NAME = "create_or_update_html_artifact"
    DISPLAY_NAME = "HTML Artifact"
    DESCRIPTION = (
        "Create a polished, interactive HTML artifact for the user. Use this tool "
        "when the user asks for a webpage, dashboard, visualization, game, UI, "
        "diagram, or other content that benefits from an interactive preview. "
        "Return one complete self-contained HTML document. Put CSS and JavaScript "
        "inside the document. Do not use remote assets or network requests. To edit "
        "an earlier artifact, pass its artifact_id and the full replacement HTML."
    )

    def __init__(
        self,
        *,
        tool_id: int,
        emitter: Emitter,
        user_id: UUID,
        chat_session_id: UUID,
        source_message_id: int | None,
    ) -> None:
        super().__init__(emitter=emitter)
        self._id = tool_id
        self._user_id = user_id
        self._chat_session_id = chat_session_id
        self._source_message_id = source_message_id

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    @override
    @classmethod
    def is_available(cls, db_session: Any) -> bool:  # noqa: ARG003
        return ENABLE_CHAT_ARTIFACTS

    @override
    def tool_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "A short user-facing artifact title.",
                        },
                        "html": {
                            "type": "string",
                            "description": "The complete self-contained HTML document.",
                        },
                        "artifact_id": {
                            "type": "string",
                            "description": "The existing artifact UUID when editing.",
                        },
                    },
                    "required": ["title", "html"],
                },
            },
        }

    @override
    def emit_start(self, placement: Placement) -> None:
        self.emitter.emit(Packet(placement=placement, obj=ArtifactToolStart()))

    @override
    def run(
        self,
        placement: Placement,
        override_kwargs: ArtifactToolOverrideKwargs,  # noqa: ARG002
        **llm_kwargs: Any,
    ) -> ToolResponse:
        title = str(llm_kwargs.get("title") or "HTML Artifact").strip()[:200]
        html = llm_kwargs.get("html")
        if not isinstance(html, str) or not html.strip():
            raise ToolCallException(
                message="Artifact HTML is missing",
                llm_facing_message="The artifact requires a complete HTML document.",
            )
        html_bytes = html.encode("utf-8")
        if len(html_bytes) > MAX_CHAT_ARTIFACT_SIZE_BYTES:
            raise ToolCallException(
                message="Artifact HTML exceeds the configured size limit",
                llm_facing_message=(
                    "The artifact is too large. Simplify it and keep all HTML, CSS, "
                    "and JavaScript under the configured size limit."
                ),
            )
        lowered = html.lstrip().lower()
        if "<html" not in lowered and "<!doctype html" not in lowered:
            raise ToolCallException(
                message="Artifact input is not a complete HTML document",
                llm_facing_message="Return a complete HTML document with an html element.",
            )

        artifact_id_value = llm_kwargs.get("artifact_id")
        try:
            artifact_id = UUID(str(artifact_id_value)) if artifact_id_value else None
        except ValueError as exc:
            raise ToolCallException(
                message="Artifact ID is invalid",
                llm_facing_message="The artifact_id is invalid. Create a new artifact instead.",
            ) from exc

        content_hash = hashlib.sha256(html_bytes).hexdigest()
        file_store = get_default_file_store()
        storage_file_id = file_store.save_file(
            BytesIO(html_bytes),
            display_name="index.html",
            file_origin=FileOrigin.ARTIFACT_REVISION,
            file_type="text/html",
            file_metadata={"content_hash": content_hash},
        )

        try:
            with get_session_with_current_tenant() as db_session:
                if artifact_id is None:
                    artifact = create_chat_artifact__no_commit(
                        chat_session_id=self._chat_session_id,
                        user_id=self._user_id,
                        name=title,
                        db_session=db_session,
                    )
                else:
                    artifact = get_artifact_for_owner(
                        artifact_id, self._user_id, db_session
                    )
                    if (
                        artifact is None
                        or artifact.chat_session_id != self._chat_session_id
                    ):
                        raise ToolCallException(
                            message="Artifact not found for Chat owner",
                            llm_facing_message=(
                                "The artifact could not be updated. Create a new artifact."
                            ),
                        )
                    artifact.name = title
                revision = create_artifact_revision__no_commit(
                    artifact=artifact,
                    content_hash=content_hash,
                    storage_file_id=storage_file_id,
                    size_bytes=len(html_bytes),
                    source_message_id=self._source_message_id,
                    source_tool_call_id=None,
                    db_session=db_session,
                )
                db_session.commit()
                db_session.refresh(revision)
                result = ArtifactToolResponse(
                    artifact_id=artifact.id,
                    revision_id=revision.id,
                    version=revision.version,
                    title=artifact.name,
                    preview_url=(
                        f"/api/artifacts/{artifact.id}/revisions/{revision.id}/preview"
                    ),
                    content_hash=content_hash,
                    size_bytes=len(html_bytes),
                )
        except Exception:
            file_store.delete_file(storage_file_id, error_on_missing=False)
            raise

        self.emitter.emit(
            Packet(
                placement=placement,
                obj=ArtifactToolFinal(**result.model_dump()),
            )
        )
        return ToolResponse(
            rich_response=result,
            llm_facing_response=(
                "Artifact created successfully. "
                f"artifact_id={result.artifact_id}, revision={result.version}."
            ),
            persisted_tool_args={
                "title": title,
                "artifact_id": str(result.artifact_id),
                "content_hash": content_hash,
                "size_bytes": len(html_bytes),
            },
        )
