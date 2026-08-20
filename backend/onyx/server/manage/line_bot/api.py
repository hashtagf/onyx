"""LINE bot admin API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.line_bot import (
    create_line_bot_config,
    delete_line_bot_config,
    delete_line_service_api_key,
    get_line_bot_config,
    update_line_bot_config,
)
from onyx.db.models import LineBotConfig, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.manage.line_bot.models import (
    LineBotConfigCreateRequest,
    LineBotConfigResponse,
    LineBotConfigUpdateRequest,
)
from shared_configs.configs import MULTI_TENANT

router = APIRouter(prefix="/manage/admin/line-bot")


def _check_bot_config_api_access() -> None:
    """Raise 403 if bot config cannot be managed via API.

    Bot config endpoints are disabled:
    - On Cloud (managed by Onyx)
    - When LINE_CHANNEL_ACCESS_TOKEN + LINE_CHANNEL_SECRET env vars are set
    """
    if MULTI_TENANT:
        raise OnyxError(
            OnyxErrorCode.SINGLE_TENANT_ONLY,
            "LINE bot configuration is managed by Onyx on Cloud.",
        )
    if LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET:
        raise OnyxError(
            OnyxErrorCode.ENV_VAR_GATED,
            "LINE bot is configured via environment variables. API access disabled.",
        )


def _to_response(config: LineBotConfig | None) -> LineBotConfigResponse:
    if config is None:
        return LineBotConfigResponse(configured=False)
    return LineBotConfigResponse(
        configured=True,
        enabled=config.enabled,
        default_persona_id=config.default_persona_id,
        respond_to_dms=config.respond_to_dms,
        require_mention_in_groups=config.require_mention_in_groups,
        created_at=config.created_at,
    )


@router.get("/config")
def get_bot_config(
    _: None = Depends(_check_bot_config_api_access),
    __: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> LineBotConfigResponse:
    """Get LINE bot config. Returns 403 on Cloud or if env vars set."""
    config = get_line_bot_config(db_session)
    return _to_response(config)


@router.post("/config")
def create_bot_request(
    request: LineBotConfigCreateRequest,
    _: None = Depends(_check_bot_config_api_access),
    __: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> LineBotConfigResponse:
    """Create LINE bot config. Returns 403 on Cloud or if env vars set."""
    try:
        config = create_line_bot_config(
            db_session,
            channel_access_token=request.channel_access_token,
            channel_secret=request.channel_secret,
        )
    except ValueError:
        raise OnyxError(
            OnyxErrorCode.DUPLICATE_RESOURCE,
            "LINE bot config already exists. Delete it first to create a new one.",
        )

    db_session.commit()
    return _to_response(config)


@router.patch("/config")
def update_bot_request(
    request: LineBotConfigUpdateRequest,
    _: None = Depends(_check_bot_config_api_access),
    __: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> LineBotConfigResponse:
    """Update LINE bot config behavior settings."""
    config = get_line_bot_config(db_session)
    if not config:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Bot config not found")

    config = update_line_bot_config(
        db_session,
        config,
        enabled=request.enabled,
        default_persona_id=request.default_persona_id,
        respond_to_dms=request.respond_to_dms,
        require_mention_in_groups=request.require_mention_in_groups,
    )
    db_session.commit()
    return _to_response(config)


@router.delete("/config")
def delete_bot_config_endpoint(
    _: None = Depends(_check_bot_config_api_access),
    __: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict:
    """Delete LINE bot config and the bot's service API key."""
    deleted = delete_line_bot_config(db_session)
    if not deleted:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Bot config not found")

    delete_line_service_api_key(db_session)

    db_session.commit()
    return {"deleted": True}
