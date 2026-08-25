from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from onyx.db.enums import SharingScope


class ArtifactRevisionResponse(BaseModel):
    id: UUID
    version: int
    content_hash: str
    size_bytes: int
    preview_url: str
    created_at: datetime


class ArtifactResponse(BaseModel):
    id: UUID
    title: str
    revision: ArtifactRevisionResponse


class ArtifactPublicationResponse(BaseModel):
    id: UUID
    artifact_id: UUID
    version: int
    visibility: SharingScope
    url: str
    content_hash: str
    created_at: datetime


class PublishArtifactRequest(BaseModel):
    visibility: SharingScope
    revision_id: UUID | None = None
