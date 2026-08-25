from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from onyx.db.enums import SharingScope
from onyx.error_handling.exceptions import OnyxError
from onyx.server.artifacts.api import preview_artifact_revision, publish_artifact
from onyx.server.artifacts.models import PublishArtifactRequest


def test_preview_uses_strict_browser_isolation() -> None:
    artifact_id = uuid4()
    revision_id = uuid4()
    user = MagicMock()
    user.id = uuid4()
    revision_file = SimpleNamespace(
        storage_file_id="revision-file",
        mime_type="text/html",
    )
    file_store = MagicMock()
    file_store.read_file.return_value = BytesIO(b"<html>safe</html>")

    with (
        patch(
            "onyx.server.artifacts.api.get_artifact_revision_for_owner",
            return_value=(
                SimpleNamespace(id=artifact_id),
                SimpleNamespace(id=revision_id),
            ),
        ),
        patch(
            "onyx.server.artifacts.api.get_artifact_revision_file",
            return_value=revision_file,
        ),
        patch(
            "onyx.server.artifacts.api.get_default_file_store",
            return_value=file_store,
        ),
    ):
        response = preview_artifact_revision(
            artifact_id=artifact_id,
            revision_id=revision_id,
            user=user,
            db_session=MagicMock(),
        )

    assert response.body == b"<html>safe</html>"
    assert "connect-src 'none'" in response.headers["Content-Security-Policy"]
    assert "form-action 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_publish_rejects_private_visibility() -> None:
    with pytest.raises(OnyxError):
        publish_artifact(
            artifact_id=uuid4(),
            request=PublishArtifactRequest(visibility=SharingScope.PRIVATE),
            user=MagicMock(id=uuid4()),
            db_session=MagicMock(),
        )
