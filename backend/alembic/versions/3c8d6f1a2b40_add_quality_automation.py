"""Add source-aware quality automation and review work.

Revision ID: 3c8d6f1a2b40
Revises: 7a9c2e4f1b60
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "3c8d6f1a2b40"
down_revision = "7a9c2e4f1b60"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_chat_message_quality_evaluation_message",
        "chat_message_quality_evaluation",
        type_="unique",
    )
    op.add_column(
        "chat_message_quality_evaluation",
        sa.Column("judge_model", sa.String(), nullable=True),
    )
    op.add_column(
        "chat_message_quality_evaluation",
        sa.Column("judge_version", sa.String(), nullable=True),
    )
    op.add_column(
        "chat_message_quality_evaluation",
        sa.Column("rubric_version", sa.String(), nullable=True),
    )
    op.add_column(
        "chat_message_quality_evaluation",
        sa.Column("confidence", sa.Float(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_chat_quality_evaluation_message_source",
        "chat_message_quality_evaluation",
        ["chat_message_id", "evaluation_source"],
    )

    op.create_table(
        "chat_quality_evaluation_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_message_id", sa.Integer(), nullable=False),
        sa.Column("judge_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('pending', 'running', 'completed', 'failed', 'skipped')",
            name="ck_chat_quality_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["chat_message_id"], ["chat_message.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chat_message_id",
            "judge_version",
            name="uq_chat_quality_job_message_judge_version",
        ),
    )
    op.create_index(
        "ix_chat_quality_job_status_updated",
        "chat_quality_evaluation_job",
        ["status", "time_updated"],
    )

    op.create_table(
        "chat_quality_review_queue_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_message_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("root_cause", sa.String(), nullable=True),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('pending', 'claimed', 'completed', 'skipped')",
            name="ck_chat_quality_review_queue_status",
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["chat_message_id"], ["chat_message.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chat_message_id", name="uq_chat_quality_review_queue_message"
        ),
    )
    op.create_index(
        "ix_chat_quality_review_queue_status_priority",
        "chat_quality_review_queue_item",
        ["status", "priority", "time_created"],
    )

    op.create_table(
        "ai_configuration_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("runtime_persona_id", sa.Integer(), nullable=True),
        sa.Column(
            "configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "time_created",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_type IN ('agent', 'custom_skill', 'builtin_skill')",
            name="ck_ai_configuration_target_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'evaluating', 'approved', 'canary', "
            "'production', 'rejected', 'archived')",
            name="ck_ai_configuration_status",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id"],
            ["ai_configuration_version.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["runtime_persona_id"], ["persona.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_type",
            "target_id",
            "version_number",
            name="uq_ai_configuration_target_version",
        ),
    )
    op.create_index(
        "uq_ai_configuration_production_target",
        "ai_configuration_version",
        ["target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'production'"),
    )

    op.create_table(
        "ai_improvement_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("root_cause", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column(
            "source_message_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
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
            "status IN ('open', 'in_progress', 'evaluating', 'completed', 'rejected')",
            name="ck_ai_improvement_item_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_evaluation_dataset",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "time_created",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'frozen', 'archived')",
            name="ck_ai_evaluation_dataset_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_ai_evaluation_dataset_version"),
    )

    op.create_table(
        "ai_evaluation_dataset_case",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("task_category", sa.String(), nullable=True),
        sa.Column("source_message_id", sa.Integer(), nullable=True),
        sa.Column("is_masked", sa.Boolean(), nullable=False),
        sa.Column(
            "case_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["ai_evaluation_dataset.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"], ["chat_message.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_evaluation_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_version_id", sa.Integer(), nullable=False),
        sa.Column("baseline_version_id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("gates_passed", sa.Boolean(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "time_created",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("time_completed", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'invalid')",
            name="ck_ai_evaluation_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["baseline_version_id"],
            ["ai_configuration_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_version_id"],
            ["ai_configuration_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["ai_evaluation_dataset.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_evaluation_result",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("variant", sa.String(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_seconds", sa.Float(), nullable=True),
        sa.Column("estimated_cost_cents", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "variant IN ('baseline', 'candidate')",
            name="ck_ai_evaluation_result_variant",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["ai_evaluation_dataset_case.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["ai_evaluation_run.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "case_id", "variant", name="uq_ai_evaluation_result_variant"
        ),
    )

    op.create_table(
        "ai_canary_release",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_version_id", sa.Integer(), nullable=False),
        sa.Column("baseline_version_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_run_id", sa.Integer(), nullable=False),
        sa.Column("traffic_percentage", sa.Float(), nullable=False),
        sa.Column(
            "eligible_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("automatic_stop_reason", sa.Text(), nullable=True),
        sa.Column("time_started", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_stopped", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'stopped', 'promoted', 'failed')",
            name="ck_ai_canary_release_status",
        ),
        sa.CheckConstraint(
            "traffic_percentage > 0 AND traffic_percentage <= 100",
            name="ck_ai_canary_release_percentage",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["baseline_version_id"],
            ["ai_configuration_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_version_id"],
            ["ai_configuration_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["ai_evaluation_run.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "chat_session",
        sa.Column("ai_configuration_version_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chat_session",
        sa.Column("runtime_persona_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_session_ai_configuration_version",
        "chat_session",
        "ai_configuration_version",
        ["ai_configuration_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_chat_session_runtime_persona",
        "chat_session",
        "persona",
        ["runtime_persona_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "chat_message",
        sa.Column("ai_configuration_version_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_message_ai_configuration_version",
        "chat_message",
        "ai_configuration_version",
        ["ai_configuration_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_chat_message_ai_configuration_version", "chat_message", type_="foreignkey"
    )
    op.drop_column("chat_message", "ai_configuration_version_id")
    op.drop_constraint(
        "fk_chat_session_runtime_persona", "chat_session", type_="foreignkey"
    )
    op.drop_column("chat_session", "runtime_persona_id")
    op.drop_constraint(
        "fk_chat_session_ai_configuration_version", "chat_session", type_="foreignkey"
    )
    op.drop_column("chat_session", "ai_configuration_version_id")
    op.drop_table("ai_canary_release")
    op.drop_table("ai_evaluation_result")
    op.drop_table("ai_evaluation_run")
    op.drop_table("ai_evaluation_dataset_case")
    op.drop_table("ai_evaluation_dataset")
    op.drop_table("ai_improvement_item")
    op.drop_index(
        "uq_ai_configuration_production_target",
        table_name="ai_configuration_version",
    )
    op.drop_table("ai_configuration_version")

    op.drop_index(
        "ix_chat_quality_review_queue_status_priority",
        table_name="chat_quality_review_queue_item",
    )
    op.drop_table("chat_quality_review_queue_item")
    op.drop_index(
        "ix_chat_quality_job_status_updated",
        table_name="chat_quality_evaluation_job",
    )
    op.drop_table("chat_quality_evaluation_job")

    op.drop_constraint(
        "uq_chat_quality_evaluation_message_source",
        "chat_message_quality_evaluation",
        type_="unique",
    )
    op.drop_column("chat_message_quality_evaluation", "confidence")
    op.drop_column("chat_message_quality_evaluation", "rubric_version")
    op.drop_column("chat_message_quality_evaluation", "judge_version")
    op.drop_column("chat_message_quality_evaluation", "judge_model")
    op.create_unique_constraint(
        "uq_chat_message_quality_evaluation_message",
        "chat_message_quality_evaluation",
        ["chat_message_id"],
    )
