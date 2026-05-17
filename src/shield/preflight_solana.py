"""V7-007 — Solana preflight shield.

Spec §13 row 5 (`IlyonAi_LP_Execution_Spec.pdf`) defines the FROZEN_ACCOUNT
blocker token for SPL token-frozen state but the runtime never actually ran
`is_frozen` against the user's ATA. This module is the pipeline hook that
turns the spec's promise into a real on-chain check.

Pipeline contract
-----------------
`evaluate_solana_frozen_preflight(pairs, rpc_url)` takes a list of
`(mint, owner)` tuples from the candidate Solana execution plan (e.g. all
SPL assets the plan will move out of the user's wallet — asset_in side of
each Jupiter swap, supply leg of every Kamino/Marinade/Orca deposit) and
returns one ExecutionBlocker per frozen (mint, owner). Empty list means
the plan passes the freeze check.

Fail-soft: RPC errors do not synthesise blockers. Surfacing a fake
"frozen" warning would corrupt the spec semantic ("Shield emits
FROZEN_ACCOUNT only when on-chain state says so").

The blocker is informational by default (severity="blocker") but its
`recoverable=True` flag tells the frontend the user may, with explicit
consent, sign anyway — frozen accounts can be drained via a permissioned
issuer flow on Token-2022, so we don't lock the user out, we just refuse
to silently sign.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import aiohttp

from src.data.solana import check_account_frozen
from src.defi.execution.models import ExecutionBlocker

logger = logging.getLogger(__name__)


async def evaluate_solana_frozen_preflight(
    pairs: Iterable[tuple[str, str]],
    rpc_url: str,
    *,
    affected_step_ids: list[str] | None = None,
    timeout_s: float = 8.0,
) -> list[ExecutionBlocker]:
    """Return one FROZEN_ACCOUNT blocker per (mint, owner) that is frozen.

    Args:
        pairs: iterable of (mint_b58, owner_b58) pairs. Empty / falsy entries
               are skipped. Pairs are deduped before fan-out.
        rpc_url: Solana mainnet RPC endpoint (Helius / public / custom).
        affected_step_ids: optional step_ids to tag on the emitted blocker.
        timeout_s: RPC timeout per call (default 8s).

    Returns:
        list[ExecutionBlocker] — empty when no frozen accounts are detected
        or when `pairs` is empty. Never raises.
    """
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for mint, owner in pairs or ():
        if not mint or not owner:
            continue
        key = (str(mint), str(owner))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)

    if not deduped or not rpc_url:
        return []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as session:
        async def _check(pair: tuple[str, str]) -> tuple[tuple[str, str], bool]:
            mint, owner = pair
            try:
                frozen = await check_account_frozen(
                    mint=mint,
                    owner=owner,
                    rpc_url=rpc_url,
                    session=session,
                    timeout_s=timeout_s,
                )
            except Exception as exc:
                # Fail-soft per module docstring: transport flakes must not
                # synthesise blockers.
                logger.debug("frozen-check raised for %s/%s: %s",
                             mint[:8], owner[:8], exc)
                frozen = False
            return pair, bool(frozen)

        results = await asyncio.gather(
            *(_check(p) for p in deduped),
            return_exceptions=False,
        )

    blockers: list[ExecutionBlocker] = []
    for (mint, owner), frozen in results:
        if not frozen:
            continue
        short_mint = mint[:8] + "…" if len(mint) > 9 else mint
        short_owner = owner[:8] + "…" if len(owner) > 9 else owner
        blockers.append(ExecutionBlocker(
            code="FROZEN_ACCOUNT",
            severity="blocker",
            title=f"SPL account frozen for mint {short_mint}",
            detail=(
                f"The owner's SPL token account for mint {mint} is in state=Frozen. "
                f"Signing any transfer/swap/supply leg moving this asset out of "
                f"{short_owner} will revert with AccountFrozen (0x11) and burn gas. "
                f"Issuer freeze authorities are common on regulated stables (USDC, "
                f"USDT) and Token-2022 permissioned mints."
            ),
            affected_step_ids=list(affected_step_ids or []),
            recoverable=True,
            cta=(
                "Pick a different asset, or contact the issuer to unfreeze the "
                "account before re-attempting this plan."
            ),
        ))

    return blockers
