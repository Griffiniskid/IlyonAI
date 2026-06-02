"""Single source of truth for "is this pool one-click executable right now?".

Three call sites used to keep their own copies of the reliable-protocol list
and the major-token set (search badge, ranking boost, and — once execution is
re-enabled — the executor gate). They drifted. This module is the ONE place
that decides reliability, so the EXECUTE badge a user sees in search can never
disagree with what the executor will actually build.

Scope of the currently-ENABLED set: EVM lending (Aave / Compound / Morpho /
Spark / Fluid / Sky / Ethena) + EVM liquid staking (Lido / Rocket Pool /
EtherFi) + EVM V2 LP (Uniswap V2 / PancakeSwap). Curve (multi-asset stable) and
all Solana protocols are deferred to a later pass and intentionally NOT here —
they deep-link until their own fork matrix is green.

Execution is additionally master-gated by `pool_exec_enabled()` (env
`POOL_EXEC_ENABLED`) so a regression reverts to deep-link-only with no redeploy.
"""
from __future__ import annotations

import os
import re

from src.agent.protocol_urls import SOLANA_NON_ONECLICK_PROTOS, classify_pool_kind

# Protocol slug prefixes verified to build a signable EVM deposit. Matched with
# str.startswith so "aave-v3", "aave-v2" all hit "aave".
RELIABLE_EXEC_PROTOCOLS: tuple[str, ...] = (
    # EVM lending
    "aave", "compound", "sky-lending", "sky", "fluid", "morpho", "spark", "ethena",
    # EVM liquid staking (single-asset, trivially reliable)
    "lido", "rocket-pool", "rocketpool", "ether.fi", "etherfi",
    # EVM V2 LP
    "uniswap-v2", "pancakeswap",
)

# Tokens we can always resolve to a contract address + route through Enso. A
# multi-leg LP whose every leg is here is one-click routable; an exotic leg is
# not (it fails the Enso route), so it deep-links.
MAJOR_TOKENS = frozenset({
    "USDC", "USDT", "DAI", "USDS", "SUSDS", "CRVUSD", "GHO", "FRAX", "USDE",
    "PYUSD", "TUSD", "BUSD", "FDUSD", "USDG", "SUSD", "LUSD", "MIM", "USD₮0", "USDT0",
    "WETH", "ETH", "WBTC", "BTC", "CBBTC", "TBTC",
    "SOL", "WSOL", "MSOL", "JITOSOL",
    "BNB", "WBNB", "AVAX", "WAVAX", "MATIC", "WMATIC", "POL", "ARB", "OP",
    "STETH", "WSTETH", "RETH", "WEETH", "CBETH",
})

_LP_ACTIONS = {"deposit_lp", "provide_liquidity", "add_liquidity"}

# Combos we have ACTUALLY broadcast-proven on a mainnet fork (the tx landed:
# Aave/Compound aToken received; uniswap-v2 LP minted). `eth_call`-sim passing
# is NOT enough — BSC PancakeSwap/Aave passed sim but reverted on broadcast, so
# only fork-proven (chain, protocol) pairs get an EXECUTE button; everything
# else deep-links until its own fork run is green. Keyed by chain → protocol
# prefixes (str.startswith). Expand only after a green fork broadcast.
PROVEN_EXEC: dict[str, tuple[str, ...]] = {
    "ethereum": ("aave", "compound", "uniswap-v2"),
    "base": ("aave", "compound"),
    "arbitrum": ("aave", "compound"),
}


def pool_exec_enabled() -> bool:
    """Master kill-switch. Default OFF — execution stays deep-link-only until
    explicitly enabled, so the safe state needs no code change to restore."""
    return os.environ.get("POOL_EXEC_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def is_reliable_exec(
    *,
    protocol: str | None,
    chain: str | None,
    symbol: str | None = None,
    action: str = "deposit_lp",
    pool_id: str | None = None,
    strict_tokens: bool = True,
) -> tuple[bool, str | None]:
    """Return (executable, reason). reason is None when executable; otherwise a
    human string explaining why the pool deep-links instead. Deterministic +
    fast (no network) so search can call it inline.

    `strict_tokens` (default True) rejects multi-leg pairs with a non-major
    leg — a conservative HINT for the search badge so it doesn't advertise an
    EXECUTE button on a pair Enso might not route. At EXECUTE time pass
    `strict_tokens=False`: the real Enso build + verify-on-commit is the gate
    (it deep-links if the route can't be built), so a routable-but-non-listed
    token like CAKE isn't blocked by an always-incomplete allowlist."""
    slug = (protocol or "").lower()
    ch = (chain or "").lower()
    if not any(slug.startswith(p) for p in RELIABLE_EXEC_PROTOCOLS):
        return False, (
            f"{protocol} isn't wired for one-click deposit yet — "
            "open the pool on its protocol to deposit."
        )
    # On-chain-proof gate: only show EXECUTE for (chain, protocol) combos whose
    # tx we've actually broadcast on a fork. Sim-passing isn't enough (BSC
    # PancakeSwap passed sim but reverted on broadcast). Everything unproven
    # deep-links until its own fork run is green.
    if not any(slug.startswith(p) for p in PROVEN_EXEC.get(ch, ())):
        return False, (
            f"{protocol} on {chain} isn't on-chain-verified for one-click "
            "deposit yet — open the pool on its protocol to deposit."
        )
    legs = [t for t in re.split(r"[-/_·]", (symbol or "").upper()) if t]
    if strict_tokens and len(legs) >= 2 and not all(t in MAJOR_TOKENS for t in legs):
        return False, (
            f"{symbol} has a token that isn't one-click routable — "
            "open the pool on its protocol to deposit."
        )
    if ch in {"solana", "sol"}:
        # Solana is out of the enabled set this pass; this stays correct if/when
        # the protocol list adds Solana families.
        if slug in SOLANA_NON_ONECLICK_PROTOS:
            return False, (
                f"{protocol} deposits aren't routable through Jupiter "
                "(no one-click path) — open the protocol app to deposit."
            )
        return True, None
    if action in _LP_ACTIONS:
        if classify_pool_kind(protocol=slug, pool_symbol=symbol, pool_id=pool_id) == "v3":
            return False, (
                f"{protocol} is a concentrated-liquidity pool — "
                "range deposits aren't one-click yet. Open the protocol app."
            )
    return True, None
