"""user_positions: Solana lifecycle state columns (V7-004)

Revision ID: agent_010
Revises: agent_009
Create Date: 2026-05-17

Adds 5 nullable columns to user_positions to persist Solana-side
position state that the runtime currently stamps onto step.transaction
at build time but loses on restart:

  - redemption_program: Solana program that owns the closing/unstake ix
    (e.g. JLP Perpetuals, Marinade staking, Sanctum router, Raydium
    AMM/CPMM, Orca Whirlpool, Kamino lend, Meteora vault).
  - receipt_mint: token-2022 / SPL receipt mint the user holds (mSOL,
    INF, JLP, kSOL, LP). Used by close/withdraw to find the user's
    associated token account without re-deriving from on-chain state.
  - lockup_end_ts: unix seconds when the position becomes redeemable
    (JLP 1h lockup, Marinade delayed-unstake epoch boundary). The
    runtime gates retry-on-unstake on this so users don't burn gas
    reverting before the lockup clears.
  - underlying_custody: JLP custody PDA pinning the underlying asset
    side (SOL custody vs BTC custody vs USDC custody). Required for
    correct unstake routing back to the deposited asset.
  - position_nft: Meteora DAMM v2 / Orca Whirlpool / Raydium CLMM
    position NFT mint that uniquely identifies the LP position
    on-chain. Required for decrease/collect.

Spec ref: dev-plan §V7-004; runtime path
src/defi/execution/adapters/solana_yield_builder.py:269-285.
"""
from alembic import op
import sqlalchemy as sa

revision = "agent_010"
down_revision = "agent_009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_positions",
        sa.Column("redemption_program", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_positions",
        sa.Column("receipt_mint", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_positions",
        sa.Column("lockup_end_ts", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "user_positions",
        sa.Column("underlying_custody", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_positions",
        sa.Column("position_nft", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_positions", "position_nft")
    op.drop_column("user_positions", "underlying_custody")
    op.drop_column("user_positions", "lockup_end_ts")
    op.drop_column("user_positions", "receipt_mint")
    op.drop_column("user_positions", "redemption_program")
