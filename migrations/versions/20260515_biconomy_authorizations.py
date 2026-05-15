"""biconomy_session_authorizations — Phase 7 EIP-7702 signing index

Revision ID: agent_009
Revises: agent_008
Create Date: 2026-05-15

Tracks every EIP-7702 authorization the user signs to upgrade their EOA
into a Biconomy Nexus smart account (or any other auth-conformant impl).

One row per (user_wallet, impl_addr, nonce) signature so we can:
  - replay-protect (nonce gate);
  - render the user's active delegation in Settings;
  - retire an auth (`expired_at`) when the user signs a deauthorize tuple
    or rotates the impl contract.

Schema follows dev-plan §7. Code path src/auth/smart_account.py already
emits the digest the user signs; this table is the off-chain index.
"""
from alembic import op
import sqlalchemy as sa

revision = "agent_009"
down_revision = "agent_008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biconomy_session_authorizations",
        sa.Column("auth_id", sa.Text(), primary_key=True),
        sa.Column("user_wallet", sa.Text(), nullable=False, index=True),
        sa.Column("impl_addr", sa.Text(), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.Numeric(), nullable=False),
        sa.Column("signature_r", sa.Text(), nullable=False),
        sa.Column("signature_s", sa.Text(), nullable=False),
        sa.Column("signature_v", sa.Integer(), nullable=False),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_wallet", "chain_id", "nonce",
                            name="uq_user_chain_nonce"),
    )
    op.create_index(
        "ix_biconomy_auth_wallet_active",
        "biconomy_session_authorizations",
        ["user_wallet", "expired_at", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_biconomy_auth_wallet_active",
                  table_name="biconomy_session_authorizations")
    op.drop_table("biconomy_session_authorizations")
