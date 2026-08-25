import hashlib
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import WEB_DOMAIN
from onyx.configs.constants import FileOrigin
from onyx.db.artifact import (
    create_artifact_publication__no_commit,
    get_artifact_revision_file,
    get_artifact_revision_for_owner,
    get_latest_publication_for_artifact_owner,
    revoke_all_publications_for_artifact_owner,
    revoke_publication_for_artifact_owner,
)
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission, SharingScope
from onyx.db.models import ArtifactPublication, ArtifactRevision, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.server.artifacts.models import (
    ArtifactPublicationResponse,
    ArtifactResponse,
    ArtifactRevisionResponse,
    PublishArtifactRequest,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()
router = APIRouter(prefix="/artifacts")

_CHAT_ARTIFACT_CSP = (
    "sandbox allow-scripts allow-modals allow-downloads; "
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; "
    "object-src 'none'; base-uri 'none'; form-action 'none'"
)


def _revision_response(
    artifact_id: UUID, revision: ArtifactRevision
) -> ArtifactRevisionResponse:
    size_bytes = sum(file.size_bytes for file in revision.files)
    return ArtifactRevisionResponse(
        id=revision.id,
        version=revision.version,
        content_hash=revision.content_hash,
        size_bytes=size_bytes,
        preview_url=(f"/api/artifacts/{artifact_id}/revisions/{revision.id}/preview"),
        created_at=revision.created_at,
    )


def _publication_response(
    publication: ArtifactPublication,
) -> ArtifactPublicationResponse:
    return ArtifactPublicationResponse(
        id=publication.id,
        artifact_id=publication.artifact_id,
        version=publication.version,
        visibility=publication.visibility,
        url=f"{WEB_DOMAIN.rstrip('/')}/api/build/artifacts/{publication.id}",
        content_hash=publication.content_hash,
        created_at=publication.created_at,
    )


@router.get("/{artifact_id}")
def get_artifact(
    artifact_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ArtifactResponse:
    result = get_artifact_revision_for_owner(
        artifact_id=artifact_id,
        user_id=user.id,
        db_session=db_session,
    )
    if result is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Artifact not found")
    artifact, revision = result
    return ArtifactResponse(
        id=artifact.id,
        title=artifact.name,
        revision=_revision_response(artifact.id, revision),
    )


@router.get("/{artifact_id}/revisions/{revision_id}/preview")
def preview_artifact_revision(
    artifact_id: UUID,
    revision_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    result = get_artifact_revision_for_owner(
        artifact_id=artifact_id,
        revision_id=revision_id,
        user_id=user.id,
        db_session=db_session,
    )
    if result is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Artifact revision not found")
    revision_file = get_artifact_revision_file(revision_id, "index.html", db_session)
    if revision_file is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Artifact file not found")
    content = get_default_file_store().read_file(revision_file.storage_file_id).read()
    response = Response(content=content, media_type=revision_file.mime_type)
    response.headers["Content-Security-Policy"] = _CHAT_ARTIFACT_CSP
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/{artifact_id}/publications")
def publish_artifact(
    artifact_id: UUID,
    request: PublishArtifactRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ArtifactPublicationResponse:
    if request.visibility not in {SharingScope.PUBLIC, SharingScope.PUBLIC_ORG}:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Published artifacts must be public or organization-only",
        )
    result = get_artifact_revision_for_owner(
        artifact_id=artifact_id,
        revision_id=request.revision_id,
        user_id=user.id,
        db_session=db_session,
    )
    if result is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Artifact not found")
    artifact, revision = result
    revision_file = get_artifact_revision_file(revision.id, "index.html", db_session)
    if revision_file is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Artifact file not found")

    source = get_default_file_store().read_file(revision_file.storage_file_id).read()
    content_hash = hashlib.sha256(b"index.html\0" + source).hexdigest()
    publication_id = uuid4()
    storage_file_id = get_default_file_store().save_file(
        BytesIO(source),
        display_name="index.html",
        file_origin=FileOrigin.ARTIFACT_PUBLICATION,
        file_type="text/html",
        file_metadata={
            "publication_id": str(publication_id),
            "artifact_id": str(artifact.id),
            "revision_id": str(revision.id),
            "path": "index.html",
        },
    )
    try:
        publication = create_artifact_publication__no_commit(
            publication_id=publication_id,
            artifact=artifact,
            visibility=request.visibility,
            content_hash=content_hash,
            files=[
                (
                    "index.html",
                    storage_file_id,
                    "text/html",
                    len(source),
                )
            ],
            db_session=db_session,
        )
        db_session.commit()
        db_session.refresh(publication)
    except Exception:
        db_session.rollback()
        get_default_file_store().delete_file(storage_file_id, error_on_missing=False)
        raise
    return _publication_response(publication)


@router.get("/{artifact_id}/publications/latest")
def get_latest_publication(
    artifact_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ArtifactPublicationResponse | None:
    publication = get_latest_publication_for_artifact_owner(
        artifact_id, user.id, db_session
    )
    return _publication_response(publication) if publication else None


@router.delete("/{artifact_id}/publications/{publication_id}")
def revoke_publication(
    artifact_id: UUID,
    publication_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    if not revoke_publication_for_artifact_owner(
        publication_id, artifact_id, user.id, db_session
    ):
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Artifact publication not found")
    return Response(status_code=204)


@router.delete("/{artifact_id}/publications")
def revoke_all_publications(
    artifact_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    if not revoke_all_publications_for_artifact_owner(artifact_id, user.id, db_session):
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Artifact not found")
    return Response(status_code=204)
