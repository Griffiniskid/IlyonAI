"""agent_platform

Revision ID: agent_001
Revises: None
Create Date: 2026-04-21

Extends web_users with id/email/password_hash/display_name.
Creates chats and chat_messages tables for the agent platform.
"""
from alembic import op
import sqlalchemy as sa

revision = 'agent_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgcrypto extension is available for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── Add BIGSERIAL id to web_users ──────────────────────────────────────
    op.add_column("web_users", sa.Column("id", sa.BigInteger(), autoincrement=True))
    op.execute("CREATE SEQUENCE IF NOT EXISTS web_users_id_seq OWNED BY web_users.id")
    op.execute("UPDATE web_users SET id = nextval('web_users_id_seq') WHERE id IS NULL")
    op.alter_column("web_users", "id", nullable=False,
                    server_default=sa.text("nextval('web_users_id_seq')"))
    op.create_unique_constraint("web_users_id_unique", "web_users", ["id"])

    # ── Auth columns on web_users ──────────────────────────────────────────
    op.add_column("web_users", sa.Column("email", sa.String(255), nullable=True))
    op.add_column("web_users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("web_users", sa.Column("display_name", sa.String(100), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX ix_web_users_email ON web_users (email) "
        "WHERE email IS NOT NULL"
    )

    # ── chats table ────────────────────────────────────────────────────────
    op.create_table(
        "chats",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.BigInteger(),
                  sa.ForeignKey("web_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="New Chat"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_chats_user_updated", "chats",
                    ["user_id", sa.text("updated_at DESC")])
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER chats_set_updated_at
        BEFORE UPDATE ON chats FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)

    # ── chat_messages table ────────────────────────────────────────────────
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("cards", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("tool_trace", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="complete"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_chat_messages_chat_id", "chat_messages",
                    ["chat_id", "created_at"])


def downgrade() -> None:
    # chat_messages
    op.drop_index("ix_chat_messages_chat_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    # chats (trigger + function)
    op.execute("DROP TRIGGER IF EXISTS chats_set_updated_at ON chats")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.drop_index("ix_chats_user_updated", table_name="chats")
    op.drop_table("chats")

    # web_users new columns
    op.drop_index("ix_web_users_email", table_name="web_users")
    op.drop_column("web_users", "display_name")
    op.drop_column("web_users", "password_hash")
    op.drop_column("web_users", "email")
    op.drop_constraint("web_users_id_unique", "web_users", type_="unique")
    op.execute("DROP SEQUENCE IF EXISTS web_users_id_seq CASCADE")
    op.drop_column("web_users", "id")
