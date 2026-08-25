from uuid import UUID

from pydantic import BaseModel


class ArtifactToolResponse(BaseModel):
    artifact_id: UUID
    revision_id: UUID
    version: int
    title: str
    preview_url: str
    content_hash: str
    size_bytes: int
