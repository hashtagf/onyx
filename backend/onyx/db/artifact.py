"""Database operations for generated artifacts and their publications."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.db.enums import ArtifactSource, ArtifactType, SharingScope
from onyx.db.models import (
    Artifact,
    ArtifactPublication,
    ArtifactPublicationFile,
    ArtifactRevision,
    ArtifactRevisionFile,
    BuildSession,
    ChatSession,
)


def get_or_create_webapp_artifact(session_id: UUID, db_session: Session) -> Artifact:
    artifact_id = uuid5(NAMESPACE_URL, f"onyx:webapp:{session_id}")
    artifact = db_session.get(Artifact, artifact_id)
    if artifact is None:
        owner_user_id = db_session.scalar(
            select(BuildSession.user_id).where(BuildSession.id == session_id)
        )
        if owner_user_id is None:
            raise ValueError("Build session not found")
        artifact = Artifact(
            id=artifact_id,
            owner_user_id=owner_user_id,
            source=ArtifactSource.CRAFT,
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


def get_artifact_for_owner(
    artifact_id: UUID, user_id: UUID, db_session: Session
) -> Artifact | None:
    return db_session.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id, Artifact.owner_user_id == user_id
        )
    )


def create_chat_artifact__no_commit(
    *,
    chat_session_id: UUID,
    user_id: UUID,
    name: str,
    db_session: Session,
) -> Artifact:
    owns_chat = db_session.scalar(
        select(ChatSession.id).where(
            ChatSession.id == chat_session_id,
            ChatSession.user_id == user_id,
            ChatSession.deleted.is_(False),
        )
    )
    if owns_chat is None:
        raise ValueError("Chat session not found")
    artifact = Artifact(
        owner_user_id=user_id,
        source=ArtifactSource.CHAT,
        chat_session_id=chat_session_id,
        type=ArtifactType.WEB_APP,
        path="index.html",
        name=name,
    )
    db_session.add(artifact)
    db_session.flush()
    return artifact


def create_artifact_revision__no_commit(
    *,
    artifact: Artifact,
    content_hash: str,
    storage_file_id: str,
    size_bytes: int,
    source_message_id: int | None,
    source_tool_call_id: str | None,
    db_session: Session,
) -> ArtifactRevision:
    db_session.execute(
        select(Artifact).where(Artifact.id == artifact.id).with_for_update()
    )
    latest_version = db_session.scalar(
        select(func.max(ArtifactRevision.version)).where(
            ArtifactRevision.artifact_id == artifact.id
        )
    )
    revision = ArtifactRevision(
        id=uuid4(),
        artifact_id=artifact.id,
        version=(latest_version or 0) + 1,
        content_hash=content_hash,
        source_message_id=source_message_id,
        source_tool_call_id=source_tool_call_id,
        files=[
            ArtifactRevisionFile(
                path="index.html",
                storage_file_id=storage_file_id,
                mime_type="text/html",
                size_bytes=size_bytes,
            )
        ],
    )
    artifact.updated_at = datetime.now(tz=timezone.utc)
    db_session.add(revision)
    db_session.flush()
    return revision


def get_artifact_revision_for_owner(
    *,
    artifact_id: UUID,
    user_id: UUID,
    db_session: Session,
    revision_id: UUID | None = None,
) -> tuple[Artifact, ArtifactRevision] | None:
    query = (
        select(Artifact, ArtifactRevision)
        .join(ArtifactRevision, ArtifactRevision.artifact_id == Artifact.id)
        .where(Artifact.id == artifact_id, Artifact.owner_user_id == user_id)
    )
    if revision_id is not None:
        query = query.where(ArtifactRevision.id == revision_id)
    else:
        query = query.order_by(desc(ArtifactRevision.version)).limit(1)
    row = db_session.execute(query).first()
    return (row[0], row[1]) if row is not None else None


def get_artifact_revision_file(
    revision_id: UUID, path: str, db_session: Session
) -> ArtifactRevisionFile | None:
    return db_session.get(ArtifactRevisionFile, (revision_id, path))


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
        .where(
            Artifact.session_id == session_id,
            Artifact.owner_user_id == user_id,
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
        select(ArtifactPublication, Artifact.owner_user_id)
        .join(Artifact, Artifact.id == ArtifactPublication.artifact_id)
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
        .where(
            ArtifactPublication.id == publication_id,
            Artifact.session_id == session_id,
            Artifact.owner_user_id == user_id,
        )
    )
    if publication is None:
        return False
    publication.revoked_at = datetime.now(tz=timezone.utc)
    db_session.commit()
    return True


def get_latest_publication_for_artifact_owner(
    artifact_id: UUID, user_id: UUID, db_session: Session
) -> ArtifactPublication | None:
    return db_session.scalar(
        select(ArtifactPublication)
        .join(Artifact, Artifact.id == ArtifactPublication.artifact_id)
        .where(
            Artifact.id == artifact_id,
            Artifact.owner_user_id == user_id,
            ArtifactPublication.revoked_at.is_(None),
        )
        .order_by(desc(ArtifactPublication.version))
        .limit(1)
    )


def revoke_publication_for_artifact_owner(
    publication_id: UUID,
    artifact_id: UUID,
    user_id: UUID,
    db_session: Session,
) -> bool:
    publication = db_session.scalar(
        select(ArtifactPublication)
        .join(Artifact, Artifact.id == ArtifactPublication.artifact_id)
        .where(
            ArtifactPublication.id == publication_id,
            Artifact.id == artifact_id,
            Artifact.owner_user_id == user_id,
        )
    )
    if publication is None:
        return False
    publication.revoked_at = datetime.now(tz=timezone.utc)
    db_session.commit()
    return True


def revoke_all_publications_for_artifact_owner(
    artifact_id: UUID,
    user_id: UUID,
    db_session: Session,
) -> bool:
    artifact = get_artifact_for_owner(artifact_id, user_id, db_session)
    if artifact is None:
        return False
    publications = db_session.scalars(
        select(ArtifactPublication).where(
            ArtifactPublication.artifact_id == artifact_id,
            ArtifactPublication.revoked_at.is_(None),
        )
    ).all()
    revoked_at = datetime.now(tz=timezone.utc)
    for publication in publications:
        publication.revoked_at = revoked_at
    db_session.commit()
    return True
