from onyx.configs.app_configs import TELEGRAM_BOT_TOKEN
from onyx.db.engine.sql_engine import get_session_with_tenant
from onyx.db.telegram_bot import get_telegram_bot_config
from onyx.utils.logger import setup_logger
from onyx.utils.sensitive import SensitiveValue
from shared_configs.configs import MULTI_TENANT, POSTGRES_DEFAULT_SCHEMA

logger = setup_logger()


def get_bot_token() -> str | None:
    """Get Telegram bot token from env var or database.

    Priority:
    1. TELEGRAM_BOT_TOKEN env var (always takes precedence)
    2. For self-hosted: TelegramBotConfig in database (default tenant),
       only when the config is enabled

    Returns:
        Bot token string, or None if not configured.
    """
    if TELEGRAM_BOT_TOKEN:
        return TELEGRAM_BOT_TOKEN

    if MULTI_TENANT:
        logger.warning("Cloud deployment missing TELEGRAM_BOT_TOKEN env var")
        return None

    try:
        with get_session_with_tenant(tenant_id=POSTGRES_DEFAULT_SCHEMA) as db:
            config = get_telegram_bot_config(db)
            if not config or not config.enabled or not config.bot_token:
                return None
            token = config.bot_token
    except Exception as e:
        logger.error("Failed to get bot token from database: %s", e)
        return None

    if isinstance(token, SensitiveValue):
        return token.get_value(apply_mask=False)
    return token


def split_message(text: str, max_length: int) -> list[str]:
    """Split text into chunks under max_length, preferring natural breaks."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        window = remaining[:max_length]
        split_at = -1
        for sep in ("\n\n", "\n", ". ", " "):
            idx = window.rfind(sep)
            if idx > 0:
                split_at = idx + len(sep)
                break
        if split_at <= 0:
            split_at = max_length
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
