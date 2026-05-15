"""pool_index + user_positions tables (dev-plan §1.2 + §1.3)

Revision ID: agent_005
Revises: agent_004
Create Date: 2026-05-15

Creates two tables that the Pool Index service + Phase 4 lifecycle code
depend on:

  - pool_index: daily-refreshed cache of (chain, protocol, pool) tuples
    with TVL / volume / APR / Shield-status for sub-50ms candidate
    resolution. Replaces the 12-entry hardcoded catalog in
    execute_pool_position.py:55-95.
  - user_positions: source-of-truth for opened positions. Written on
    every confirmed deposit (after receipt verifier flips
    confirmed=True). Phase 4 lifecycle code (decrease / collect /
    rebalance) reads from here.

Both tables ship per spec §12 DepositPlan schema + dev-plan §1.2/§1.3.
"""
from alembic import op
import sqlalchemy as sa

revision = "agent_005"
down_revision = "agent_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pool_index",
        sa.Column("pool_id", sa.Text(), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.Text(), nullable=False),
        sa.Column("protocol_version", sa.Text(), nullable=True),       # v2 | v3 | v4 | ng | clmm | dlmm | cpmm
        sa.Column("pool_address", sa.Text(), nullable=True),           # EVM; null for V4 (use pool_key_hash)
        sa.Column("pool_key_hash", sa.Text(), nullable=True),          # Uniswap V4 only
        sa.Column("pool_pubkey", sa.Text(), nullable=True),            # Solana
        sa.Column("token0_address", sa.Text(), nullable=False),
        sa.Column("token1_address", sa.Text(), nullable=True),
        sa.Column("token2_address", sa.Text(), nullable=True),         # 3-coin pools (Curve 3pool, tricrypto)
        sa.Column("fee_bps", sa.Integer(), nullable=True),
        sa.Column("tick_spacing", sa.Integer(), nullable=True),
        sa.Column("bin_step_bps", sa.Integer(), nullable=True),
        sa.Column("hooks_address", sa.Text(), nullable=True),          # Uniswap V4 hooks
        sa.Column("tvl_usd", sa.Numeric(), nullable=True),
        sa.Column("volume_7d_usd", sa.Numeric(), nullable=True),
        sa.Column("fee_apr_30d", sa.Float(), nullable=True),
        sa.Column("reward_apr_30d", sa.Float(), nullable=True),
        sa.Column("pool_age_days", sa.Integer(), nullable=True),
        sa.Column("audit_status", sa.Text(), nullable=True),
        sa.Column("shield_status", sa.Text(), nullable=True),          # 'allowed' | 'experimental' | 'blocked'
        sa.Column("last_refreshed", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_pool_index_lookup", "pool_index",
                    ["chain_id", "token0_address", "token1_address"])
    op.create_index("ix_pool_index_protocol", "pool_index",
                    ["chain_id", "protocol"])
    op.create_index("ix_pool_index_score", "pool_index",
                    ["chain_id", "tvl_usd"])
    op.create_index("ix_pool_index_shield", "pool_index",
                    ["shield_status"])

    op.create_table(
        "user_positions",
        sa.Column("position_id", sa.Text(), primary_key=True),         # UUID
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("wallet_address", sa.Text(), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.Text(), nullable=False),
        sa.Column("pool_id", sa.Text(), nullable=False),               # references pool_index.pool_id but not FK so positions can predate index entries
        sa.Column("receipt_kind", sa.Text(), nullable=False),          # see src/defi/verification/receipt_table.ReceiptKind
        sa.Column("receipt_address", sa.Text(), nullable=True),
        sa.Column("receipt_token_id", sa.Text(), nullable=True),       # V3/V4 NFT tokenId
        sa.Column("tick_lower", sa.Integer(), nullable=True),
        sa.Column("tick_upper", sa.Integer(), nullable=True),
        sa.Column("bin_lower", sa.Integer(), nullable=True),
        sa.Column("bin_upper", sa.Integer(), nullable=True),
        sa.Column("amount0_deposited", sa.Numeric(), nullable=True),
        sa.Column("amount1_deposited", sa.Numeric(), nullable=True),
        sa.Column("liquidity", sa.Numeric(), nullable=True),
        sa.Column("tx_hash", sa.Text(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("metadata_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_user_positions_wallet", "user_positions",
                    ["wallet_address", "chain_id"])
    op.create_index("ix_user_positions_user_status", "user_positions",
                    ["user_id", "status"])
    op.create_index("ix_user_positions_pool", "user_positions",
                    ["pool_id"])


def downgrade() -> None:
    op.drop_index("ix_user_positions_pool", table_name="user_positions")
    op.drop_index("ix_user_positions_user_status", table_name="user_positions")
    op.drop_index("ix_user_positions_wallet", table_name="user_positions")
    op.drop_table("user_positions")
    op.drop_index("ix_pool_index_shield", table_name="pool_index")
    op.drop_index("ix_pool_index_score", table_name="pool_index")
    op.drop_index("ix_pool_index_protocol", table_name="pool_index")
    op.drop_index("ix_pool_index_lookup", table_name="pool_index")
    op.drop_table("pool_index")
