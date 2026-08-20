"""CRUD operations for LINE bot models."""

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.auth.api_key import build_displayable_api_key, generate_api_key, hash_api_key
from onyx.auth.schemas import UserRole
from onyx.configs.constants import LINE_SERVICE_API_KEY_NAME
from onyx.db.api_key import insert_api_key
from onyx.db.models import ApiKey, LineBotConfig, User
from onyx.server.api_key.models import APIKeyArgs
from onyx.utils.logger import setup_logger

logger = setup_logger()


# === LineBotConfig ===


def get_line_bot_config(db_session: Session) -> LineBotConfig | None:
    """Get the LINE bot config for this tenant (at most one)."""
    return db_session.scalar(select(LineBotConfig).limit(1))


def create_line_bot_config(
    db_session: Session,
    channel_access_token: str,
    channel_secret: str,
) -> LineBotConfig:
    """Create the LINE bot config. Raises ValueError if already exists."""
    existing = get_line_bot_config(db_session)
    if existing:
        raise ValueError("LINE bot config already exists")

    config = LineBotConfig(
        channel_access_token=channel_access_token,
        channel_secret=channel_secret,
    )
    db_session.add(config)
    try:
        db_session.flush()
    except IntegrityError:
        db_session.rollback()
        raise ValueError("LINE bot config already exists")
    return config


def update_line_bot_config(
    db_session: Session,
    config: LineBotConfig,
    enabled: bool,
    default_persona_id: int | None,
    respond_to_dms: bool,
    require_mention_in_groups: bool,
) -> LineBotConfig:
    """Update mutable LINE bot config fields."""
    config.enabled = enabled
    config.default_persona_id = default_persona_id
    config.respond_to_dms = respond_to_dms
    config.require_mention_in_groups = require_mention_in_groups
    db_session.flush()
    return config


def delete_line_bot_config(db_session: Session) -> bool:
    """Delete the LINE bot config. Returns True if deleted."""
    result = db_session.execute(delete(LineBotConfig))
    db_session.flush()
    return result.rowcount > 0  # ty: ignore[unresolved-attribute]


# === LINE Service API Key ===


def get_line_service_api_key(db_session: Session) -> ApiKey | None:
    """Get the LINE service API key if it exists."""
    return db_session.scalar(
        select(ApiKey).where(ApiKey.name == LINE_SERVICE_API_KEY_NAME)
    )


def get_or_create_line_service_api_key(
    db_session: Session,
    tenant_id: str,
) -> str:
    """Get existing LINE service API key or create one.

    The key authenticates the LINE webhook handler against the Onyx API
    server for chat requests. Only the hash is stored, so an existing key
    is regenerated to obtain the raw value.
    """
    existing = get_line_service_api_key(db_session)
    if existing:
        logger.debug("Regenerating LINE service API key for tenant %s", tenant_id)
        new_api_key = generate_api_key(tenant_id)
        existing.hashed_api_key = hash_api_key(new_api_key)
        existing.api_key_display = build_displayable_api_key(new_api_key)
        db_session.flush()
        return new_api_key

    logger.info("Creating LINE service API key for tenant %s", tenant_id)
    api_key_args = APIKeyArgs(
        name=LINE_SERVICE_API_KEY_NAME,
        role=UserRole.LIMITED,  # insert_api_key grants LIMITED keys chat scope
    )
    api_key_descriptor = insert_api_key(
        db_session=db_session,
        api_key_args=api_key_args,
        user_id=None,  # Service account, no owner
    )

    if not api_key_descriptor.api_key:
        raise RuntimeError(
            f"Failed to create LINE service API key for tenant {tenant_id}"
        )

    return api_key_descriptor.api_key


def delete_line_service_api_key(db_session: Session) -> bool:
    """Delete the LINE service API key. Returns True if deleted."""
    existing_key = get_line_service_api_key(db_session)
    if not existing_key:
        return False

    api_key_user = db_session.scalar(
        select(User).where(
            User.id == existing_key.user_id  # ty: ignore[invalid-argument-type]
        )
    )

    db_session.delete(existing_key)
    if api_key_user:
        db_session.delete(api_key_user)

    db_session.flush()
    logger.info("Deleted LINE service API key")
    return True
