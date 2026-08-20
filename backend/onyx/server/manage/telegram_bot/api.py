"""Telegram bot admin API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import TELEGRAM_BOT_TOKEN
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import User
from onyx.db.telegram_bot import (
    create_telegram_bot_config,
    delete_telegram_bot_config,
    delete_telegram_chat_config,
    delete_telegram_service_api_key,
    get_telegram_bot_config,
    get_telegram_chat_config_by_internal_id,
    get_telegram_chat_configs,
    update_telegram_bot_config,
    update_telegram_chat_config,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.manage.telegram_bot.models import (
    TelegramBotConfigCreateRequest,
    TelegramBotConfigResponse,
    TelegramBotConfigUpdateRequest,
    TelegramChatConfigResponse,
    TelegramChatConfigUpdateRequest,
)
from shared_configs.configs import MULTI_TENANT

router = APIRouter(prefix="/manage/admin/telegram-bot")


def _check_bot_config_api_access() -> None:
    """Raise 403 if bot config cannot be managed via API.

    Bot config endpoints are disabled:
    - On Cloud (managed by Onyx)
    - When TELEGRAM_BOT_TOKEN env var is set (managed via env)
    """
    if MULTI_TENANT:
        raise OnyxError(
            OnyxErrorCode.SINGLE_TENANT_ONLY,
            "Telegram bot configuration is managed by Onyx on Cloud.",
        )
    if TELEGRAM_BOT_TOKEN:
        raise OnyxError(
            OnyxErrorCode.ENV_VAR_GATED,
            "Telegram bot is configured via environment variables. API access disabled.",
        )


# === Bot Config ===


@router.get("/config")
def get_bot_config(
    _: None = Depends(_check_bot_config_api_access),
    __: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> TelegramBotConfigResponse:
    """Get Telegram bot config. Returns 403 on Cloud or if env vars set."""
    config = get_telegram_bot_config(db_session)
    if not config:
        return TelegramBotConfigResponse(configured=False)

    return TelegramBotConfigResponse(
        configured=True,
        enabled=config.enabled,
        default_persona_id=config.default_persona_id,
        created_at=config.created_at,
    )


@router.post("/config")
def create_bot_request(
    request: TelegramBotConfigCreateRequest,
    _: None = Depends(_check_bot_config_api_access),
    __: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> TelegramBotConfigResponse:
    """Create Telegram bot config. Returns 403 on Cloud or if env vars set."""
    try:
        config = create_telegram_bot_config(
            db_session,
            bot_token=request.bot_token,
        )
    except ValueError:
        raise OnyxError(
            OnyxErrorCode.DUPLICATE_RESOURCE,
            "Telegram bot config already exists. Delete it first to create a new one.",
        )

    db_session.commit()

    return TelegramBotConfigResponse(
        configured=True,
        enabled=config.enabled,
        default_persona_id=config.default_persona_id,
        created_at=config.created_at,
    )


@router.patch("/config")
def update_bot_request(
    request: TelegramBotConfigUpdateRequest,
    _: None = Depends(_check_bot_config_api_access),
    __: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> TelegramBotConfigResponse:
    """Update Telegram bot config (enabled flag + default agent)."""
    config = get_telegram_bot_config(db_session)
    if not config:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Bot config not found")

    config = update_telegram_bot_config(
        db_session,
        config,
        enabled=request.enabled,
        default_persona_id=request.default_persona_id,
    )
    db_session.commit()

    return TelegramBotConfigResponse(
        configured=True,
        enabled=config.enabled,
        default_persona_id=config.default_persona_id,
        created_at=config.created_at,
    )


@router.delete("/config")
def delete_bot_config_endpoint(
    _: None = Depends(_check_bot_config_api_access),
    __: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict:
    """Delete Telegram bot config and the bot's service API key."""
    deleted = delete_telegram_bot_config(db_session)
    if not deleted:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Bot config not found")

    delete_telegram_service_api_key(db_session)

    db_session.commit()
    return {"deleted": True}


# === Chat Config ===


@router.get("/chats")
def list_chat_configs(
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[TelegramChatConfigResponse]:
    """List all discovered chats."""
    configs = get_telegram_chat_configs(db_session)
    return [TelegramChatConfigResponse.model_validate(c) for c in configs]


@router.patch("/chats/{chat_config_id}")
def update_chat_request(
    chat_config_id: int,
    request: TelegramChatConfigUpdateRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> TelegramChatConfigResponse:
    """Update chat config."""
    config = get_telegram_chat_config_by_internal_id(db_session, chat_config_id)
    if not config:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Chat config not found")

    config = update_telegram_chat_config(
        db_session,
        config,
        enabled=request.enabled,
        require_bot_invocation=request.require_bot_invocation,
        persona_override_id=request.persona_override_id,
    )
    db_session.commit()

    return TelegramChatConfigResponse.model_validate(config)


@router.delete("/chats/{chat_config_id}")
def delete_chat_request(
    chat_config_id: int,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict:
    """Delete a chat config. The bot re-creates it (disabled) if the chat
    messages the bot again."""
    deleted = delete_telegram_chat_config(db_session, chat_config_id)
    if not deleted:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Chat config not found")
    db_session.commit()
    return {"deleted": True}
