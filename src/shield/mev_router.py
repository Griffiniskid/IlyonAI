"""V7-037 — MEV auto-flip to private relays.

Routes execution through MEVBlocker (EVM) or Jito (Solana) bundle lanes
when slippage > 30 bps OR notional > $5k. Below thresholds: public mempool.
"""

from __future__ import annotations

from typing import Optional

MEV_SLIPPAGE_THRESHOLD_BPS: int = 30
MEV_NOTIONAL_THRESHOLD_USD: float = 5_000.0

MEVBLOCKER_RPC = "https://rpc.mevblocker.io"
JITO_TIP_LAMPORTS_DEFAULT = 100_000  # 0.0001 SOL


def should_route_private(slippage_bps: int, notional_usd: float) -> bool:
    """True if trade should be routed via private relay."""
    return slippage_bps > MEV_SLIPPAGE_THRESHOLD_BPS or notional_usd > MEV_NOTIONAL_THRESHOLD_USD


def private_rpc_for_chain(
    chain: str, slippage_bps: int, notional_usd: float
) -> Optional[dict]:
    """Return private-relay config for chain, or None if below threshold / unsupported."""
    if not should_route_private(slippage_bps, notional_usd):
        return None
    c = (chain or "").lower()
    if c in ("ethereum", "eth", "1"):
        return {"rpc_url": MEVBLOCKER_RPC, "lane": "mevblocker"}
    if c in ("solana", "sol"):
        return {"jito_tip_lamports": JITO_TIP_LAMPORTS_DEFAULT, "lane": "jito"}
    return None
