"""user_smart_accounts + session_key_policies + session_key_audit_log

Revision ID: agent_007
Revises: agent_006
Create Date: 2026-05-15

Phase 7 EIP-7702 smart-account + session-key autonomy foundation:

  - user_smart_accounts: tracks which user wallets have opted into
    EIP-7702 (or a 4337 equivalent) and the delegation implementation
    contract they upgraded to.
  - session_key_policies: per-policy scope/cap/expiry/revoke state.
    On-chain enforcement is mandatory (Biconomy/ZeroDev policy);
    off-chain DB row is the index for the user-facing Settings page.
  - session_key_audit_log: every autonomous action gets a row here
    AND a chat-thread `agent_autonomous` message. HMAC-chained per
    spec §11 D.8.

Tables ship per dev-plan §7 schema. Code paths in src/auth/ pending.
"""
from alembic import op
import sqlalchemy as sa

revision = "agent_007"
down_revision = "agent_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_smart_accounts",
        sa.Column("wallet_address", sa.Text(), primary_key=True),
        sa.Column("implementation", sa.Text(), nullable=False),
        # implementation = biconomy-nexus | zerodev-kernel | mm-smart-accounts | ...
        sa.Column("delegation_tx_hash", sa.Text(), nullable=False),
        sa.Column("delegated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "session_key_policies",
        sa.Column("policy_id", sa.Text(), primary_key=True),         # UUID
        sa.Column("user_wallet", sa.Text(), nullable=False),
        sa.Column("session_key_address", sa.Text(), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False),
        # scope_json shape:
        #   {
        #     "position_id": uuid,
        #     "protocol": "uniswap-v3",
        #     "pool_address": "0x...",
        #     "allowed_selectors": ["0x...", "0x..."],
        #     "cumulative_value_moved_usd": "decimal-as-str"
        #   }
        sa.Column("spending_cap_per_24h_usd", sa.Numeric(), nullable=False),
        sa.Column("spending_cap_total_usd", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("on_chain_signature", sa.Text(), nullable=False),
        # EIP-712 signature embedding the policy fields. Mirror this
        # on-chain (Biconomy / ZeroDev policy framework) so off-chain
        # tamper is detected on every session-key broadcast.
    )
    op.create_index("ix_session_key_policies_wallet", "session_key_policies",
                    ["user_wallet", "revoked_at"])
    op.create_index("ix_session_key_policies_active", "session_key_policies",
                    ["user_wallet", "expires_at"])

    op.create_table(
        "session_key_audit_log",
        sa.Column("log_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("tx_hash", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        # action enum: rebalance | compound | decrease | close | swap
        sa.Column("value_moved_usd", sa.Numeric(), nullable=True),
        sa.Column("prompt_hash", sa.Text(), nullable=True),
        sa.Column("plan_hash", sa.Text(), nullable=True),
        sa.Column("entry_hmac", sa.Text(), nullable=False),       # spec §11 D.8 chain
        sa.Column("prev_hmac", sa.Text(), nullable=False, server_default=sa.text("'" + "0" * 64 + "'")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_session_key_audit_policy_time", "session_key_audit_log",
                    ["policy_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_session_key_audit_policy_time", table_name="session_key_audit_log")
    op.drop_table("session_key_audit_log")
    op.drop_index("ix_session_key_policies_active", table_name="session_key_policies")
    op.drop_index("ix_session_key_policies_wallet", table_name="session_key_policies")
    op.drop_table("session_key_policies")
    op.drop_table("user_smart_accounts")
