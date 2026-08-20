"""Pydantic models for LINE bot API."""

from datetime import datetime

from pydantic import BaseModel


class LineBotConfigResponse(BaseModel):
    configured: bool
    enabled: bool = True
    default_persona_id: int | None = None
    respond_to_dms: bool = True
    require_mention_in_groups: bool = True
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class LineBotConfigCreateRequest(BaseModel):
    channel_access_token: str
    channel_secret: str


class LineBotConfigUpdateRequest(BaseModel):
    enabled: bool
    default_persona_id: int | None
    respond_to_dms: bool
    require_mention_in_groups: bool
