"""Add chat response quality evaluations.

Revision ID: 7a9c2e4f1b60
Revises: 4f6b1a2c9d30
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7a9c2e4f1b60"
down_revision = "4f6b1a2c9d30"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "chat_message_quality_evaluation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_message_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_source", sa.String(), nullable=False),
        sa.Column("task_category", sa.String(), nullable=True),
        sa.Column("task_success", sa.Boolean(), nullable=True),
        sa.Column("first_answer_resolution", sa.Boolean(), nullable=True),
        sa.Column("required_rephrase", sa.Boolean(), nullable=True),
        sa.Column("correctness", sa.Integer(), nullable=True),
        sa.Column("relevance", sa.Integer(), nullable=True),
        sa.Column("completeness", sa.Integer(), nullable=True),
        sa.Column("clarity", sa.Integer(), nullable=True),
        sa.Column("instruction_following", sa.Integer(), nullable=True),
        sa.Column("grounded", sa.Boolean(), nullable=True),
        sa.Column("citation_accuracy", sa.Integer(), nullable=True),
        sa.Column("retrieval_relevance", sa.Integer(), nullable=True),
        sa.Column("hallucination_detected", sa.Boolean(), nullable=True),
        sa.Column("appropriate_refusal", sa.Boolean(), nullable=True),
        sa.Column("false_refusal", sa.Boolean(), nullable=True),
        sa.Column("harmful_response", sa.Boolean(), nullable=True),
        sa.Column("sensitive_data_leakage", sa.Boolean(), nullable=True),
        sa.Column("unauthorized_document_exposure", sa.Boolean(), nullable=True),
        sa.Column("policy_violation", sa.Boolean(), nullable=True),
        sa.Column("prompt_injection_succeeded", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "time_created",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "time_updated",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "evaluation_source IN ('human', 'llm_judge')",
            name="ck_chat_quality_evaluation_source",
        ),
        sa.CheckConstraint(
            "correctness IS NULL OR correctness BETWEEN 1 AND 5",
            name="ck_chat_quality_correctness_score",
        ),
        sa.CheckConstraint(
            "relevance IS NULL OR relevance BETWEEN 1 AND 5",
            name="ck_chat_quality_relevance_score",
        ),
        sa.CheckConstraint(
            "completeness IS NULL OR completeness BETWEEN 1 AND 5",
            name="ck_chat_quality_completeness_score",
        ),
        sa.CheckConstraint(
            "clarity IS NULL OR clarity BETWEEN 1 AND 5",
            name="ck_chat_quality_clarity_score",
        ),
        sa.CheckConstraint(
            "instruction_following IS NULL OR instruction_following BETWEEN 1 AND 5",
            name="ck_chat_quality_instruction_following_score",
        ),
        sa.CheckConstraint(
            "citation_accuracy IS NULL OR citation_accuracy BETWEEN 1 AND 5",
            name="ck_chat_quality_citation_accuracy_score",
        ),
        sa.CheckConstraint(
            "retrieval_relevance IS NULL OR retrieval_relevance BETWEEN 1 AND 5",
            name="ck_chat_quality_retrieval_relevance_score",
        ),
        sa.ForeignKeyConstraint(
            ["chat_message_id"], ["chat_message.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chat_message_id", name="uq_chat_message_quality_evaluation_message"
        ),
    )
    op.create_index(
        "ix_chat_quality_evaluation_updated",
        "chat_message_quality_evaluation",
        ["time_updated"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_quality_evaluation_updated",
        table_name="chat_message_quality_evaluation",
    )
    op.drop_table("chat_message_quality_evaluation")
