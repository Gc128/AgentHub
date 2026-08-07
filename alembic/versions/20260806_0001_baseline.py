"""Create the trusted AgentHub schema from a clean database."""

import sqlalchemy as sa

from alembic import op

revision = "20260806_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversationrecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("agent_ids_json", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "messagerecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("sender_id", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("artifacts_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("reply_to_id", sa.String(), nullable=True),
        sa.Column("regenerated_from_id", sa.String(), nullable=True),
        sa.Column("is_context_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="completed"),
        sa.Column("error_json", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "customagentrecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.String(), nullable=False),
        sa.Column("capabilities_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "workspacerecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("root_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "workspacepreviewrecord",
        sa.Column("workspace_id", sa.String(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("preview_url", sa.String(), nullable=True),
        sa.Column("entry_path", sa.String(), nullable=True),
    )
    op.create_table(
        "workspacefilerecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "applieddiffrecordrow",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("diff", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("before_content", sa.String(), nullable=True),
        sa.Column("after_content", sa.String(), nullable=True),
        sa.Column("before_exists", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("change_set_id", sa.String(), nullable=True),
        sa.Column("reverted_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "changesetrecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("source_message_id", sa.String(), nullable=True),
        sa.Column("parent_change_set_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="generated"),
        sa.Column("base_snapshot_sha256", sa.String(), nullable=False),
        sa.Column("repair_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entry_path", sa.String(), nullable=True),
        sa.Column("preview_checks_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("review_report_json", sa.String(), nullable=True),
        sa.Column("preview_report_json", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "changesetfilerecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("change_set_id", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False, server_default="upsert"),
        sa.Column("before_exists", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("before_sha256", sa.String(), nullable=False),
        sa.Column("before_content", sa.String(), nullable=False, server_default=""),
        sa.Column("after_content", sa.String(), nullable=True),
        sa.Column("after_sha256", sa.String(), nullable=False),
        sa.Column("diff", sa.String(), nullable=False, server_default=""),
    )
    op.create_table(
        "validationrunrecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("change_set_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("report_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(), nullable=False, server_default=""),
        sa.Column("error_message", sa.String(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "memorysummaryrecord",
        sa.Column("conversation_id", sa.String(), primary_key=True),
        sa.Column("up_to_message_id", sa.String(), nullable=False),
        sa.Column("summary_json", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ready"),
        sa.Column("error_message", sa.String(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    for table_name in (
        "memorysummaryrecord",
        "validationrunrecord",
        "changesetfilerecord",
        "changesetrecord",
        "applieddiffrecordrow",
        "workspacefilerecord",
        "workspacepreviewrecord",
        "workspacerecord",
        "customagentrecord",
        "messagerecord",
        "conversationrecord",
    ):
        op.drop_table(table_name)
