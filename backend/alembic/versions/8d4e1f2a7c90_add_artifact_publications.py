"""Add immutable artifact publications.

Revision ID: 8d4e1f2a7c90
Revises: 6a7281043a40
Create Date: 2026-08-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8d4e1f2a7c90"
down_revision = "6a7281043a40"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "artifact_publication",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_id", "version", name="uq_artifact_publication_version"
        ),
    )
    op.create_index(
        "ix_artifact_publication_artifact_created",
        "artifact_publication",
        ["artifact_id", "created_at"],
    )
    op.create_table(
        "artifact_publication_file",
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("storage_file_id", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["publication_id"], ["artifact_publication.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["storage_file_id"], ["file_record.file_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("publication_id", "path"),
        sa.UniqueConstraint("storage_file_id"),
    )


def downgrade() -> None:
    op.drop_table("artifact_publication_file")
    op.drop_index(
        "ix_artifact_publication_artifact_created",
        table_name="artifact_publication",
    )
    op.drop_table("artifact_publication")
