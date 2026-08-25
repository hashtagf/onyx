import hashlib
import mimetypes
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import WEB_DOMAIN
from onyx.configs.constants import FileOrigin
from onyx.db.artifact import (
    create_artifact_publication__no_commit,
    get_latest_artifact_publication_for_owner,
    get_or_create_webapp_artifact,
    revoke_artifact_publication_for_owner,
)
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission, SharingScope
from onyx.db.models import ArtifactPublication, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.server.features.build.artifacts.models import (
    ArtifactPublicationResponse,
    PublishArtifactRequest,
)
from onyx.server.features.build.db.build_session import (
    set_build_session_sharing_scope,
    set_build_session_sharing_scope__no_commit,
)
from onyx.server.features.build.session.manager import SessionManager
from onyx.utils.logger import setup_logger

logger = setup_logger()
router = APIRouter(prefix="/sessions")


def _publication_response(
    publication: ArtifactPublication,
) -> ArtifactPublicationResponse:
    return ArtifactPublicationResponse(
        id=publication.id,
        version=publication.version,
        visibility=publication.visibility,
        url=f"{WEB_DOMAIN.rstrip('/')}/api/build/artifacts/{publication.id}",
        content_hash=publication.content_hash,
        created_at=publication.created_at,
    )


@router.post("/{session_id}/artifact-publications")
def publish_webapp_artifact(
    session_id: UUID,
    request: PublishArtifactRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ArtifactPublicationResponse:
    publication_id = uuid4()
    try:
        files = SessionManager(db_session).build_static_webapp_files(
            session_id, user.id, publication_id
        )
    except ValueError as e:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, str(e)) from e
    except RuntimeError as e:
        raise OnyxError(OnyxErrorCode.SERVICE_UNAVAILABLE, str(e)) from e

    content_hasher = hashlib.sha256()
    for path, content in files:
        content_hasher.update(path.encode())
        content_hasher.update(b"\0")
        content_hasher.update(content)

    file_store = get_default_file_store()
    stored_file_ids: list[str] = []
    publication_files: list[tuple[str, str, str, int]] = []
    try:
        for path, content in files:
            mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
            storage_file_id = file_store.save_file(
                BytesIO(content),
                display_name=path,
                file_origin=FileOrigin.ARTIFACT_PUBLICATION,
                file_type=mime_type,
                file_metadata={"publication_id": str(publication_id), "path": path},
            )
            stored_file_ids.append(storage_file_id)
            publication_files.append((path, storage_file_id, mime_type, len(content)))

        artifact = get_or_create_webapp_artifact(session_id, db_session)
        publication = create_artifact_publication__no_commit(
            publication_id=publication_id,
            artifact=artifact,
            visibility=request.visibility,
            content_hash=content_hasher.hexdigest(),
            files=publication_files,
            db_session=db_session,
        )
        set_build_session_sharing_scope__no_commit(
            session_id, user.id, request.visibility, db_session
        )
        db_session.commit()
        db_session.refresh(publication)
    except Exception:
        db_session.rollback()
        for storage_file_id in stored_file_ids:
            try:
                file_store.delete_file(storage_file_id, error_on_missing=False)
            except Exception:
                logger.warning(
                    "Failed to clean up publication file %s",
                    storage_file_id,
                    exc_info=True,
                )
        raise
    return _publication_response(publication)


@router.get("/{session_id}/artifact-publications/latest")
def get_latest_webapp_publication(
    session_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ArtifactPublicationResponse | None:
    publication = get_latest_artifact_publication_for_owner(
        session_id, user.id, db_session
    )
    return _publication_response(publication) if publication else None


@router.delete("/{session_id}/artifact-publications/{publication_id}")
def revoke_webapp_publication(
    session_id: UUID,  # noqa: ARG001 - retained for a session-scoped API
    publication_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    if not revoke_artifact_publication_for_owner(
        publication_id, session_id, user.id, db_session
    ):
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Artifact publication not found")
    set_build_session_sharing_scope(
        session_id, user.id, SharingScope.PRIVATE, db_session
    )
    return Response(status_code=204)
