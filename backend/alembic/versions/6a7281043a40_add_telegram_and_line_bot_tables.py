"""Add Telegram and LINE bot tables

Revision ID: 6a7281043a40
Revises: f8048443da9e
Create Date: 2026-08-21

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "6a7281043a40"
down_revision = "f8048443da9e"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    # TelegramBotConfig (singleton table - one per tenant)
    op.create_table(
        "telegram_bot_config",
        sa.Column(
            "id",
            sa.String(),
            primary_key=True,
            server_default=sa.text("'SINGLETON'"),
        ),
        sa.Column("bot_token", sa.LargeBinary(), nullable=False),  # EncryptedString
        sa.Column(
            "default_persona_id",
            sa.Integer(),
            sa.ForeignKey("persona.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 'SINGLETON'", name="ck_telegram_bot_config_singleton"),
    )

    # TelegramChatConfig
    op.create_table(
        "telegram_chat_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("chat_name", sa.String(), nullable=False),
        sa.Column(
            "chat_type",
            sa.String(20),
            server_default=sa.text("'private'"),
            nullable=False,
        ),
        sa.Column(
            "require_bot_invocation",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "persona_override_id",
            sa.Integer(),
            sa.ForeignKey("persona.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # LineBotConfig (singleton table - one per tenant)
    op.create_table(
        "line_bot_config",
        sa.Column(
            "id",
            sa.String(),
            primary_key=True,
            server_default=sa.text("'SINGLETON'"),
        ),
        # EncryptedString columns
        sa.Column("channel_access_token", sa.LargeBinary(), nullable=False),
        sa.Column("channel_secret", sa.LargeBinary(), nullable=False),
        sa.Column(
            "default_persona_id",
            sa.Integer(),
            sa.ForeignKey("persona.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "respond_to_dms",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "require_mention_in_groups",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 'SINGLETON'", name="ck_line_bot_config_singleton"),
    )


def downgrade() -> None:
    op.drop_table("line_bot_config")
    op.drop_table("telegram_chat_config")
    op.drop_table("telegram_bot_config")
