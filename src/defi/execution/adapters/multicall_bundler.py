"""V7-002 §7 S11/S14 — Multicall bundler for refinance + V2→V3 migrate.

Spec quote (`IlyonAi_Development_Plan_v2.md` §V7-002):
  "S11 refinance, S14 migrate ... write multicall bundler ... for
  refinance/migrate"

Refinance (§7 S11) is a same-protocol range rebalance on a V3 NFT
position: the old position is decreased + collected, then a fresh mint
opens a new range using the released token0/token1. Migrate (§7 S14) is
the cross-protocol cousin: V2 LP tokens are pulled via removeLiquidity,
then the resulting underlying pair is minted as a fresh V3 NFT range.

Both shapes collapse to a 3-step plan:
  1. decrease/remove from the *old* pool
  2. collect (refinance) or aggregate output (migrate)
  3. add_liquidity / deposit_lp into the *new* pool

This module is intentionally calldata-free — the real calldata is
encoded inside `UniswapV3NFTAdapter.build` / `UniswapV2DualTokenAdapter.build`
when the upstream `build_yield_execution_plan` routes the composed
action through them. The bundler's job is to (a) prove the action is
expressible as an ordered ExecutionStepV3 list and (b) give the
state-machine + frontend a stable depends-on chain so the third step
cannot fire before the first two confirm.

Shape contract (pin-tested in `tests/defi/test_s11_s14_s12_end_to_end.py`):
  build_refinance(old_position, new_pool) -> 3-step list, actions
    are [decrease_liquidity, collect, add_liquidity], all on the same
    `protocol` (same-pool rebalance).
  build_migrate(old_position, new_pool) -> 3-step list, actions are
    [remove_liquidity, collect, add_liquidity], where step 0's protocol
    is the *old* V2 protocol and steps 1/2 land on the *new* V3 protocol.

`depends_on` is wired so step N >0 references step N-1 by step_id —
the state-machine refuses to flip a later step to 'ready' until its
dependency confirms (see `ExecutionPlanV3._recompute_step_statuses`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.defi.execution.models import ExecutionStepV3, make_step


@dataclass(frozen=True)
class PositionRef:
    """Pointer to an on-chain LP position the bundler can read.

    Refinance (§7 S11): both `old` and `new` are the same protocol;
    `token_id` identifies the V3 NFT being rebalanced.
    Migrate   (§7 S14): `old.protocol` is the V2 source, `new.protocol`
    is the V3 destination; V2 has no NFT — `token_id` is None and the
    bundler pulls liquidity by pair address instead.
    """
    chain: str
    protocol: str
    pool_symbol: str  # e.g. "USDC-WETH"
    token_a: str       # e.g. "USDC"
    token_b: str       # e.g. "WETH"
    token_id: int | None = None
    pool_address: str | None = None
    range_lower: float | None = None
    range_upper: float | None = None
    range_kind: str | None = None  # narrow|tight|wide|broad|full
    extra: dict[str, Any] | None = None


@dataclass
class MulticallBundler:
    """Compose refinance + migrate into ordered ExecutionStepV3 lists.

    The bundler does not touch ABI encoding — it sequences the three
    spec-§7 phases (unwind → settle → re-deploy) and wires
    `depends_on` so the state-machine cannot fire phase N until phase
    N-1 confirms. Adapter `build()` methods stamp the real calldata
    later when the runtime walks each step.
    """

    bundler_id: str = "multicall-v7-002"

    def build_refinance(
        self,
        old_position: PositionRef,
        new_pool: PositionRef,
    ) -> list[ExecutionStepV3]:
        """§7 S11 — same-protocol range rebalance on a V3 NFT.

        Phases:
          0. decrease_liquidity  — burn the existing range, freeing
             token0/token1 back to the position contract.
          1. collect              — pull token0/token1 (incl. any
             accrued fees) into the user wallet so the mint leg has
             a clean inventory to consume.
          2. add_liquidity        — mint a fresh range on `new_pool`.
             Same protocol/chain as `old_position`; only the range
             (and possibly fee tier) changes.
        """
        if old_position.protocol.lower() != new_pool.protocol.lower():
            raise ValueError(
                "refinance is same-protocol only — got "
                f"{old_position.protocol} -> {new_pool.protocol}; "
                "use build_migrate for cross-protocol moves."
            )
        wallet: str = "MetaMask"  # V3 NFT is EVM-only
        step0 = make_step(
            index=0,
            action="withdraw",  # legacy StepAction alias for V3 decreaseLiquidity
            title=f"Decrease {old_position.pool_symbol} range",
            description=(
                f"Burn liquidity from V3 NFT #{old_position.token_id} on "
                f"{old_position.protocol} ({old_position.chain})."
            ),
            chain=old_position.chain,
            wallet=wallet,
            protocol=old_position.protocol,
            asset_in=f"{old_position.token_a}+{old_position.token_b}",
        )
        step1 = make_step(
            index=1,
            action="claim_rewards",  # collect() in V3 NFT terms
            title=f"Collect {old_position.pool_symbol}",
            description=(
                f"Pull token0/token1 (+ accrued fees) from V3 NFT "
                f"#{old_position.token_id} into the wallet."
            ),
            chain=old_position.chain,
            wallet=wallet,
            protocol=old_position.protocol,
            asset_in=f"{old_position.token_a}+{old_position.token_b}",
            depends_on=[step0.step_id],
        )
        rng_desc = ""
        if new_pool.range_lower is not None and new_pool.range_upper is not None:
            rng_desc = f" in range {new_pool.range_lower}–{new_pool.range_upper}"
        elif new_pool.range_kind:
            rng_desc = f" ({new_pool.range_kind} range)"
        step2 = make_step(
            index=2,
            action="deposit_lp",
            title=f"Mint {new_pool.pool_symbol}{rng_desc}",
            description=(
                f"Mint fresh V3 NFT on {new_pool.protocol} ({new_pool.chain}) "
                f"with the released {new_pool.token_a}/{new_pool.token_b}."
            ),
            chain=new_pool.chain,
            wallet=wallet,
            protocol=new_pool.protocol,
            asset_in=f"{new_pool.token_a}+{new_pool.token_b}",
            depends_on=[step1.step_id],
        )
        return [step0, step1, step2]

    def build_migrate(
        self,
        old_position: PositionRef,
        new_pool: PositionRef,
    ) -> list[ExecutionStepV3]:
        """§7 S14 — cross-protocol V2 → V3 migrate.

        Phases:
          0. remove_liquidity  — burn V2 LP tokens (router.removeLiquidity),
             releasing token0 + token1 back into the wallet.
          1. collect/aggregate — settle the V2 unwind output; this step
             is a no-op wait when the V2 router auto-credits the wallet,
             but it preserves a stable depends_on hop so the mint step
             cannot race ahead of the unwind confirmation.
          2. add_liquidity     — mint a fresh V3 NFT on `new_pool`.

        Step 0 lands on the V2 protocol; steps 1+2 land on the V3
        protocol — the bundler honours the cross-protocol split so the
        capability registry routes each step to the right adapter
        (`UniswapV2DualTokenAdapter` vs `UniswapV3NFTAdapter`).
        """
        if old_position.protocol.lower() == new_pool.protocol.lower():
            raise ValueError(
                "migrate is cross-protocol — got identical "
                f"{old_position.protocol}; use build_refinance for same-protocol "
                "range rebalances."
            )
        wallet: str = "MetaMask"
        step0 = make_step(
            index=0,
            action="withdraw",  # V2 removeLiquidity rides the withdraw alias
            title=f"Remove {old_position.pool_symbol} from {old_position.protocol}",
            description=(
                f"Burn V2 LP tokens on {old_position.protocol} ({old_position.chain}) "
                f"to release {old_position.token_a} + {old_position.token_b}."
            ),
            chain=old_position.chain,
            wallet=wallet,
            protocol=old_position.protocol,
            asset_in=f"{old_position.token_a}+{old_position.token_b}",
        )
        step1 = make_step(
            index=1,
            action="verify_balance",  # settle/aggregate hop for the V2 → V3 handoff
            title=f"Confirm {old_position.pool_symbol} unwind",
            description=(
                f"Wait for V2 removeLiquidity receipt and read the actual "
                f"{old_position.token_a}/{old_position.token_b} delta in the wallet "
                "before the V3 mint reads inventory."
            ),
            chain=new_pool.chain,
            wallet=wallet,
            protocol=new_pool.protocol,
            asset_in=f"{old_position.token_a}+{old_position.token_b}",
            depends_on=[step0.step_id],
        )
        rng_desc = ""
        if new_pool.range_lower is not None and new_pool.range_upper is not None:
            rng_desc = f" in range {new_pool.range_lower}–{new_pool.range_upper}"
        elif new_pool.range_kind:
            rng_desc = f" ({new_pool.range_kind} range)"
        step2 = make_step(
            index=2,
            action="deposit_lp",
            title=f"Mint {new_pool.pool_symbol}{rng_desc} on {new_pool.protocol}",
            description=(
                f"Mint fresh V3 NFT on {new_pool.protocol} ({new_pool.chain}) "
                f"using the {new_pool.token_a}/{new_pool.token_b} freed from "
                f"the V2 position."
            ),
            chain=new_pool.chain,
            wallet=wallet,
            protocol=new_pool.protocol,
            asset_in=f"{new_pool.token_a}+{new_pool.token_b}",
            depends_on=[step1.step_id],
        )
        return [step0, step1, step2]
