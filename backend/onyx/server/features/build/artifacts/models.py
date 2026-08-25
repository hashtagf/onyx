from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from onyx.db.enums import SharingScope


class PublishArtifactRequest(BaseModel):
    visibility: SharingScope = SharingScope.PUBLIC

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, value: SharingScope) -> SharingScope:
        if value not in {SharingScope.PUBLIC, SharingScope.PUBLIC_ORG}:
            raise ValueError("Published artifacts must be public or organization-only")
        return value


class ArtifactPublicationResponse(BaseModel):
    id: UUID
    version: int
    visibility: SharingScope
    url: str
    content_hash: str
    created_at: datetime
