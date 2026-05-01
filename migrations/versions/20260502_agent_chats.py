"""agent_chats

Revision ID: agent_003
Revises: agent_002
Create Date: 2026-05-02

Creates agent_chats and agent_chat_messages tables for chat history parity.
"""
from alembic import op
import sqlalchemy as sa

revision = 'agent_003'
down_revision = 'agent_002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_chats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_agent_chats_user_id", "agent_chats", ["user_id"])

    op.create_table(
        "agent_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("cards_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_agent_chat_messages_chat_id", "agent_chat_messages", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_chat_messages_chat_id", table_name="agent_chat_messages")
    op.drop_table("agent_chat_messages")
    op.drop_index("ix_agent_chats_user_id", table_name="agent_chats")
    op.drop_table("agent_chats")
