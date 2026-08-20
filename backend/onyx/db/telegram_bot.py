"""CRUD operations for Telegram bot models."""

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.auth.api_key import build_displayable_api_key, generate_api_key, hash_api_key
from onyx.auth.schemas import UserRole
from onyx.configs.constants import TELEGRAM_SERVICE_API_KEY_NAME
from onyx.db.api_key import insert_api_key
from onyx.db.models import ApiKey, TelegramBotConfig, TelegramChatConfig, User
from onyx.server.api_key.models import APIKeyArgs
from onyx.utils.logger import setup_logger

logger = setup_logger()


# === TelegramBotConfig ===


def get_telegram_bot_config(db_session: Session) -> TelegramBotConfig | None:
    """Get the Telegram bot config for this tenant (at most one)."""
    return db_session.scalar(select(TelegramBotConfig).limit(1))


def create_telegram_bot_config(
    db_session: Session,
    bot_token: str,
) -> TelegramBotConfig:
    """Create the Telegram bot config. Raises ValueError if already exists."""
    existing = get_telegram_bot_config(db_session)
    if existing:
        raise ValueError("Telegram bot config already exists")

    config = TelegramBotConfig(bot_token=bot_token)
    db_session.add(config)
    try:
        db_session.flush()
    except IntegrityError:
        db_session.rollback()
        raise ValueError("Telegram bot config already exists")
    return config


def update_telegram_bot_config(
    db_session: Session,
    config: TelegramBotConfig,
    enabled: bool,
    default_persona_id: int | None,
) -> TelegramBotConfig:
    """Update mutable Telegram bot config fields."""
    config.enabled = enabled
    config.default_persona_id = default_persona_id
    db_session.flush()
    return config


def delete_telegram_bot_config(db_session: Session) -> bool:
    """Delete the Telegram bot config. Returns True if deleted."""
    result = db_session.execute(delete(TelegramBotConfig))
    db_session.flush()
    return result.rowcount > 0  # ty: ignore[unresolved-attribute]


# === Telegram Service API Key ===


def get_telegram_service_api_key(db_session: Session) -> ApiKey | None:
    """Get the Telegram service API key if it exists."""
    return db_session.scalar(
        select(ApiKey).where(ApiKey.name == TELEGRAM_SERVICE_API_KEY_NAME)
    )


def get_or_create_telegram_service_api_key(
    db_session: Session,
    tenant_id: str,
) -> str:
    """Get existing Telegram service API key or create one.

    The key authenticates the Telegram bot process against the Onyx API
    server for chat requests. Only the hash is stored, so an existing key
    is regenerated to obtain the raw value.
    """
    existing = get_telegram_service_api_key(db_session)
    if existing:
        logger.debug("Regenerating Telegram service API key for tenant %s", tenant_id)
        new_api_key = generate_api_key(tenant_id)
        existing.hashed_api_key = hash_api_key(new_api_key)
        existing.api_key_display = build_displayable_api_key(new_api_key)
        db_session.flush()
        return new_api_key

    logger.info("Creating Telegram service API key for tenant %s", tenant_id)
    api_key_args = APIKeyArgs(
        name=TELEGRAM_SERVICE_API_KEY_NAME,
        role=UserRole.LIMITED,  # insert_api_key grants LIMITED keys chat scope
    )
    api_key_descriptor = insert_api_key(
        db_session=db_session,
        api_key_args=api_key_args,
        user_id=None,  # Service account, no owner
    )

    if not api_key_descriptor.api_key:
        raise RuntimeError(
            f"Failed to create Telegram service API key for tenant {tenant_id}"
        )

    return api_key_descriptor.api_key


def delete_telegram_service_api_key(db_session: Session) -> bool:
    """Delete the Telegram service API key. Returns True if deleted."""
    existing_key = get_telegram_service_api_key(db_session)
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
    logger.info("Deleted Telegram service API key")
    return True


# === TelegramChatConfig ===


def get_telegram_chat_configs(db_session: Session) -> list[TelegramChatConfig]:
    """Get all chat configs, newest first."""
    return list(
        db_session.scalars(
            select(TelegramChatConfig).order_by(TelegramChatConfig.id.desc())
        ).all()
    )


def get_telegram_chat_config_by_chat_id(
    db_session: Session,
    chat_id: int,
) -> TelegramChatConfig | None:
    """Get a chat config by Telegram chat ID."""
    return db_session.scalar(
        select(TelegramChatConfig).where(TelegramChatConfig.chat_id == chat_id)
    )


def get_telegram_chat_config_by_internal_id(
    db_session: Session,
    internal_id: int,
) -> TelegramChatConfig | None:
    """Get a chat config by its internal ID."""
    return db_session.scalar(
        select(TelegramChatConfig).where(TelegramChatConfig.id == internal_id)
    )


def upsert_telegram_chat_config(
    db_session: Session,
    chat_id: int,
    chat_name: str,
    chat_type: str,
) -> TelegramChatConfig:
    """Auto-discover a chat: create a disabled row on first sight, refresh
    the name/type on later sightings."""
    config = get_telegram_chat_config_by_chat_id(db_session, chat_id)
    if config:
        if config.chat_name != chat_name or config.chat_type != chat_type:
            config.chat_name = chat_name
            config.chat_type = chat_type
            db_session.flush()
        return config

    config = TelegramChatConfig(
        chat_id=chat_id,
        chat_name=chat_name,
        chat_type=chat_type,
    )
    db_session.add(config)
    try:
        db_session.flush()
    except IntegrityError:
        # Race: another poll iteration created the row concurrently
        db_session.rollback()
        existing = get_telegram_chat_config_by_chat_id(db_session, chat_id)
        if existing is None:
            raise
        return existing
    return config


def update_telegram_chat_config(
    db_session: Session,
    config: TelegramChatConfig,
    enabled: bool,
    require_bot_invocation: bool,
    persona_override_id: int | None,
) -> TelegramChatConfig:
    """Update chat config fields."""
    config.enabled = enabled
    config.require_bot_invocation = require_bot_invocation
    config.persona_override_id = persona_override_id
    db_session.flush()
    return config


def delete_telegram_chat_config(
    db_session: Session,
    internal_id: int,
) -> bool:
    """Delete a chat config. Returns True if deleted."""
    result = db_session.execute(
        delete(TelegramChatConfig).where(TelegramChatConfig.id == internal_id)
    )
    db_session.flush()
    return result.rowcount > 0  # ty: ignore[unresolved-attribute]
