"""Database operations for generated artifacts and their publications."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.db.enums import ArtifactType, SharingScope
from onyx.db.models import (
    Artifact,
    ArtifactPublication,
    ArtifactPublicationFile,
    BuildSession,
)


def get_or_create_webapp_artifact(session_id: UUID, db_session: Session) -> Artifact:
    artifact_id = uuid5(NAMESPACE_URL, f"onyx:webapp:{session_id}")
    artifact = db_session.get(Artifact, artifact_id)
    if artifact is None:
        artifact = Artifact(
            id=artifact_id,
            session_id=session_id,
            type=ArtifactType.WEB_APP,
            path="outputs/web",
            name="Web Application",
        )
        db_session.add(artifact)
        try:
            db_session.commit()
            db_session.refresh(artifact)
        except IntegrityError:
            db_session.rollback()
            artifact = db_session.get(Artifact, artifact_id)
            if artifact is None:
                raise
    return artifact


def create_artifact_publication__no_commit(
    *,
    publication_id: UUID,
    artifact: Artifact,
    visibility: SharingScope,
    content_hash: str,
    files: list[tuple[str, str, str, int]],
    db_session: Session,
) -> ArtifactPublication:
    db_session.execute(
        select(Artifact).where(Artifact.id == artifact.id).with_for_update()
    )
    latest_version = db_session.scalar(
        select(func.max(ArtifactPublication.version)).where(
            ArtifactPublication.artifact_id == artifact.id
        )
    )
    publication = ArtifactPublication(
        id=publication_id,
        artifact_id=artifact.id,
        version=(latest_version or 0) + 1,
        visibility=visibility,
        content_hash=content_hash,
    )
    publication.files = [
        ArtifactPublicationFile(
            path=path,
            storage_file_id=storage_file_id,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
        for path, storage_file_id, mime_type, size_bytes in files
    ]
    db_session.add(publication)
    db_session.flush()
    return publication


def get_latest_artifact_publication_for_owner(
    session_id: UUID, user_id: UUID, db_session: Session
) -> ArtifactPublication | None:
    return db_session.scalar(
        select(ArtifactPublication)
        .join(Artifact, Artifact.id == ArtifactPublication.artifact_id)
        .join(BuildSession, BuildSession.id == Artifact.session_id)
        .where(
            Artifact.session_id == session_id,
            BuildSession.user_id == user_id,
            ArtifactPublication.revoked_at.is_(None),
        )
        .order_by(desc(ArtifactPublication.version))
        .limit(1)
    )


def get_artifact_publication(
    publication_id: UUID, db_session: Session
) -> ArtifactPublication | None:
    return db_session.get(ArtifactPublication, publication_id)


def get_artifact_publication_access(
    publication_id: UUID, db_session: Session
) -> tuple[ArtifactPublication, UUID] | None:
    row = db_session.execute(
        select(ArtifactPublication, BuildSession.user_id)
        .join(Artifact, Artifact.id == ArtifactPublication.artifact_id)
        .join(BuildSession, BuildSession.id == Artifact.session_id)
        .where(ArtifactPublication.id == publication_id)
    ).first()
    return (row[0], row[1]) if row is not None else None


def get_artifact_publication_file(
    publication_id: UUID, path: str, db_session: Session
) -> ArtifactPublicationFile | None:
    return db_session.get(ArtifactPublicationFile, (publication_id, path))


def revoke_artifact_publication_for_owner(
    publication_id: UUID, session_id: UUID, user_id: UUID, db_session: Session
) -> bool:
    publication = db_session.scalar(
        select(ArtifactPublication)
        .join(Artifact, Artifact.id == ArtifactPublication.artifact_id)
        .join(BuildSession, BuildSession.id == Artifact.session_id)
        .where(
            ArtifactPublication.id == publication_id,
            Artifact.session_id == session_id,
            BuildSession.user_id == user_id,
        )
    )
    if publication is None:
        return False
    publication.revoked_at = datetime.now(tz=timezone.utc)
    db_session.commit()
    return True
