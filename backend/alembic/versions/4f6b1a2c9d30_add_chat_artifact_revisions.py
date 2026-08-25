"""Add Chat artifact ownership and immutable revisions.

Revision ID: 4f6b1a2c9d30
Revises: 8d4e1f2a7c90
Create Date: 2026-08-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4f6b1a2c9d30"
down_revision = "8d4e1f2a7c90"
branch_labels: None = None
depends_on: None = None


ARTIFACT_TOOL = {
    "name": "create_or_update_html_artifact",
    "display_name": "HTML Artifact",
    "description": "Create or update an interactive HTML artifact in Chat.",
    "in_code_tool_id": "ArtifactTool",
    "enabled": True,
}


def upgrade() -> None:
    op.add_column(
        "artifact",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "artifact",
        sa.Column("source", sa.String(), nullable=True),
    )
    op.add_column(
        "artifact",
        sa.Column("chat_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_artifact_owner_user_id",
        "artifact",
        "user",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_artifact_chat_session_id",
        "artifact",
        "chat_session",
        ["chat_session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        sa.text(
            """
            UPDATE artifact
            SET owner_user_id = build_session.user_id,
                source = 'craft'
            FROM build_session
            WHERE artifact.session_id = build_session.id
            """
        )
    )
    op.alter_column("artifact", "owner_user_id", nullable=False)
    op.alter_column("artifact", "source", nullable=False)
    op.alter_column("artifact", "session_id", nullable=True)
    op.create_check_constraint(
        "ck_artifact_source_parent",
        "artifact",
        "(source = 'craft' AND session_id IS NOT NULL AND chat_session_id IS NULL) "
        "OR (source = 'chat' AND chat_session_id IS NOT NULL AND session_id IS NULL)",
    )
    op.create_index(
        "ix_artifact_chat_session_created",
        "artifact",
        ["chat_session_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_artifact_owner_updated",
        "artifact",
        ["owner_user_id", sa.text("updated_at DESC")],
    )

    op.create_table(
        "artifact_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_message_id", sa.Integer(), nullable=True),
        sa.Column("source_tool_call_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_message_id"], ["chat_message.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id", "version", name="uq_artifact_revision_version"
        ),
    )
    op.create_index(
        "ix_artifact_revision_artifact_created",
        "artifact_revision",
        ["artifact_id", "created_at"],
    )
    op.create_table(
        "artifact_revision_file",
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("storage_file_id", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["artifact_revision.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["storage_file_id"], ["file_record.file_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("revision_id", "path"),
        sa.UniqueConstraint("storage_file_id"),
    )

    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
        {"in_code_tool_id": ARTIFACT_TOOL["in_code_tool_id"]},
    ).fetchone()
    if existing:
        conn.execute(
            sa.text(
                """
                UPDATE tool
                SET name = :name, display_name = :display_name,
                    description = :description, enabled = :enabled
                WHERE in_code_tool_id = :in_code_tool_id
                """
            ),
            ARTIFACT_TOOL,
        )
    else:
        conn.execute(
            sa.text(
                """
                INSERT INTO tool
                    (name, display_name, description, in_code_tool_id, enabled)
                VALUES
                    (:name, :display_name, :description, :in_code_tool_id, :enabled)
                """
            ),
            ARTIFACT_TOOL,
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
        {"in_code_tool_id": ARTIFACT_TOOL["in_code_tool_id"]},
    )
    op.drop_table("artifact_revision_file")
    op.drop_index(
        "ix_artifact_revision_artifact_created", table_name="artifact_revision"
    )
    op.drop_table("artifact_revision")
    op.drop_index("ix_artifact_owner_updated", table_name="artifact")
    op.drop_index("ix_artifact_chat_session_created", table_name="artifact")
    op.drop_constraint("ck_artifact_source_parent", "artifact", type_="check")
    op.execute(sa.text("DELETE FROM artifact WHERE source = 'chat'"))
    op.alter_column("artifact", "session_id", nullable=False)
    op.drop_constraint("fk_artifact_chat_session_id", "artifact", type_="foreignkey")
    op.drop_constraint("fk_artifact_owner_user_id", "artifact", type_="foreignkey")
    op.drop_column("artifact", "chat_session_id")
    op.drop_column("artifact", "source")
    op.drop_column("artifact", "owner_user_id")
