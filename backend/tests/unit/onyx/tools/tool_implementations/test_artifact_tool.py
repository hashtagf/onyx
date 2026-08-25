from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from onyx.server.query_and_chat.placement import Placement
from onyx.tools.models import ToolCallException
from onyx.tools.tool_implementations.artifact.artifact_tool import (
    ArtifactTool,
    ArtifactToolOverrideKwargs,
)


def _tool(emitter: MagicMock) -> ArtifactTool:
    return ArtifactTool(
        tool_id=41,
        emitter=emitter,
        user_id=uuid4(),
        chat_session_id=uuid4(),
        source_message_id=17,
    )


def test_artifact_tool_persists_compact_arguments() -> None:
    emitter = MagicMock()
    tool = _tool(emitter)
    artifact_id = uuid4()
    revision_id = uuid4()
    artifact = SimpleNamespace(
        id=artifact_id,
        name="Status board",
        chat_session_id=tool._chat_session_id,
    )
    revision = SimpleNamespace(id=revision_id, version=1)
    db_session = MagicMock()
    db_context = MagicMock()
    db_context.__enter__.return_value = db_session
    file_store = MagicMock()
    file_store.save_file.return_value = "stored-html"

    with (
        patch(
            "onyx.tools.tool_implementations.artifact.artifact_tool"
            ".get_default_file_store",
            return_value=file_store,
        ),
        patch(
            "onyx.tools.tool_implementations.artifact.artifact_tool"
            ".get_session_with_current_tenant",
            return_value=db_context,
        ),
        patch(
            "onyx.tools.tool_implementations.artifact.artifact_tool"
            ".create_chat_artifact__no_commit",
            return_value=artifact,
        ),
        patch(
            "onyx.tools.tool_implementations.artifact.artifact_tool"
            ".create_artifact_revision__no_commit",
            return_value=revision,
        ),
    ):
        response = tool.run(
            Placement(turn_index=0),
            ArtifactToolOverrideKwargs(),
            title="Status board",
            html="<!doctype html><html><body>Ready</body></html>",
        )

    assert response.rich_response is not None
    assert response.persisted_tool_args is not None
    assert response.persisted_tool_args["artifact_id"] == str(artifact_id)
    assert "html" not in response.persisted_tool_args
    assert response.persisted_tool_args["size_bytes"] > 0
    db_session.commit.assert_called_once()
    assert emitter.emit.call_count == 1


def test_artifact_tool_rejects_oversized_html() -> None:
    tool = _tool(MagicMock())
    with (
        patch(
            "onyx.tools.tool_implementations.artifact.artifact_tool"
            ".MAX_CHAT_ARTIFACT_SIZE_BYTES",
            20,
        ),
        pytest.raises(ToolCallException, match="size limit"),
    ):
        tool.run(
            Placement(turn_index=0),
            ArtifactToolOverrideKwargs(),
            title="Large",
            html="<!doctype html><html><body>Too large</body></html>",
        )


def test_artifact_tool_deletes_file_after_database_failure() -> None:
    tool = _tool(MagicMock())
    db_context = MagicMock()
    db_context.__enter__.side_effect = RuntimeError("database unavailable")
    file_store = MagicMock()
    file_store.save_file.return_value = "orphan-file"

    with (
        patch(
            "onyx.tools.tool_implementations.artifact.artifact_tool"
            ".get_default_file_store",
            return_value=file_store,
        ),
        patch(
            "onyx.tools.tool_implementations.artifact.artifact_tool"
            ".get_session_with_current_tenant",
            return_value=db_context,
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        tool.run(
            Placement(turn_index=0),
            ArtifactToolOverrideKwargs(),
            title="Failure",
            html="<!doctype html><html><body>Failure</body></html>",
        )

    file_store.delete_file.assert_called_once_with(
        "orphan-file", error_on_missing=False
    )
