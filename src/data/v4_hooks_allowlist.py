# Curated allowlist of audited Uniswap V4 hook addresses (lowercase).
# Hooks not in this set are refused by preflight to prevent malicious-hook
# drains (Spec §6a / §11 D.4).
#
# Each non-zero entry MUST be sourced from an official registry and
# verified on a public block explorer (source code "Exact Match"). New
# entries require a code review that includes the registry URL, explorer
# URL, and a one-line behavior rationale.
#
# Schema is keyed by (chain_id, hook_addr_lowercase) to support hook
# contracts that share a vanity prefix across chains. The lookup helper
# `is_hook_allowed` accepts the legacy (single-set) calling shape AND
# the new (chain_id, addr) shape for backwards compatibility with
# callers that don't pass chain context yet.
from typing import Optional

# (chain_id, lowercase_addr) → human-readable label. The label is purely
# informational — presence in this dict is what gates the preflight check.
V4_HOOKS_ALLOWLIST_BY_CHAIN: dict[tuple[int, str], str] = {
    # ───────────────────────────────────────────────────────────────────
    # Ethereum mainnet (chain id 1)
    # ───────────────────────────────────────────────────────────────────
    # Angstrom — Sorella Labs MEV-resistant DEX hook. Internalizes MEV
    # via application-specific auctions; redirects extracted value back
    # to LPs / traders (prevents sandwich attacks, reduces gas).
    # Sources (fetched 2026-05-19):
    #   registry: https://github.com/Uniswap/hooklist/blob/main/hooks/ethereum/0x0000000aa232009084Bd71A5797d089AA4Edfad4.json
    #   explorer: https://etherscan.io/address/0x0000000aa232009084Bd71A5797d089AA4Edfad4 (verified "Exact Match", contract "Angstrom", IPoolManager/IHooks)
    #   audit:    https://github.com/spearbit/portfolio/blob/master/pdfs/Sorella-Spearbit-Security-Review-October-2024.pdf
    (1, "0x0000000aa232009084bd71a5797d089aa4edfad4"): "Angstrom (Sorella Labs, MEV-resistant)",
    # BunniHook — Bunni v2 core hook (concentrated-liquidity vAMM with
    # dynamic fees: TWAP + surge detection, am-AMM bidding for LVR
    # recapture, FloodPlain auto-rebalancing, on-chain oracle).
    # Sources (fetched 2026-05-19):
    #   registry: https://github.com/Uniswap/hooklist/blob/main/hooks/ethereum/0x00001f3b9712708127b1fcad61cb892535951888.json
    #   explorer: https://etherscan.io/address/0x00001f3b9712708127b1fcad61cb892535951888 (verified "Exact Match", contract "BunniHook", IPoolManager/IHooks)
    (1, "0x00001f3b9712708127b1fcad61cb892535951888"): "BunniHook (Bunni v2, dynamic fee + am-AMM)",
}

# Backwards-compatible flat set — preserved so callers that don't yet
# pass chain_id continue to work. The zero-address sentinel lives here
# because it's chain-agnostic (a V4 PoolKey with hooks=address(0) is a
# vanilla pool on any chain).
V4_HOOKS_ALLOWLIST: set[str] = {
    "0x0000000000000000000000000000000000000000",  # zero address = no hook (allowed on every chain)
} | {addr for (_chain, addr) in V4_HOOKS_ALLOWLIST_BY_CHAIN}


def is_hook_allowed(hook_addr: str, chain_id: Optional[int] = None) -> bool:
    """Return True iff the V4 hook is on the audited allowlist.

    Empty string and the zero address are always allowed (they encode
    "no hook attached"). When ``chain_id`` is supplied, the lookup is
    strict — a hook approved for chain X is NOT auto-allowed on chain Y
    because the same bytecode redeployed on a different chain hasn't
    been audited there. When ``chain_id`` is None, falls back to the
    chain-agnostic flat set for backwards compatibility.
    """
    if not hook_addr:
        return True  # no hook attached, allowed
    addr_l = hook_addr.lower()
    if addr_l == "0x0000000000000000000000000000000000000000":
        return True
    if chain_id is not None:
        return (int(chain_id), addr_l) in V4_HOOKS_ALLOWLIST_BY_CHAIN
    return addr_l in V4_HOOKS_ALLOWLIST


def check_v4_hook(hook_addr: str, chain_id: Optional[int] = None) -> Optional[str]:
    """Returns DISALLOWED_V4_HOOK blocker code if not allowed, else None.

    Preflight is expected to wire this on the V4 deposit_lp branch — see
    src/defi/execution/preflight.py. The chain_id is optional for the
    same backwards-compat reason as is_hook_allowed; callers SHOULD
    pass it whenever they have it so a hook approved for mainnet can't
    be silently accepted on an L2 where it isn't audited.
    """
    if not is_hook_allowed(hook_addr, chain_id):
        return "DISALLOWED_V4_HOOK"
    return None
