"""Pydantic models for Telegram bot API."""

from datetime import datetime

from pydantic import BaseModel

# === Bot Config ===


class TelegramBotConfigResponse(BaseModel):
    configured: bool
    enabled: bool = True
    default_persona_id: int | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class TelegramBotConfigCreateRequest(BaseModel):
    bot_token: str


class TelegramBotConfigUpdateRequest(BaseModel):
    enabled: bool
    default_persona_id: int | None


# === Chat Config ===


class TelegramChatConfigResponse(BaseModel):
    id: int
    chat_id: int
    chat_name: str
    chat_type: str
    require_bot_invocation: bool
    persona_override_id: int | None
    enabled: bool
    first_seen_at: datetime

    class Config:
        from_attributes = True


class TelegramChatConfigUpdateRequest(BaseModel):
    enabled: bool
    require_bot_invocation: bool
    persona_override_id: int | None
