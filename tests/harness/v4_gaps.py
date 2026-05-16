"""Known-spec-gap allowlist for v4 matrix.

Chains in EXPECTED_BLOCKED are expected to surface a typed-recovery
BLOCKED card on a specific turn — V5 prompt explicitly classifies these
as PASS (not actionable regressions). Excluded from re-fire loops; not
counted as Pass-failures by validator scripts.

Sourced from:
  - V5 prompt 'Phase B/C/D/E' deferred items
  - Pass 1 inventory chains marked 'honest empty-wallet refusal'
  - Spec gaps requiring verified on-chain addresses (V5 hard rule
    forbids guessing addresses)
"""
from __future__ import annotations

# (chain_id, turn_idx, reason) — turn_idx 1-indexed
EXPECTED_BLOCKED: list[tuple[str, int, str]] = [
    # A — honest empty-wallet refusal
    ("A20_jito_sol", 4, "Jito spl-stake-pool SDK refuses on empty test wallet (honest balance check). V5-acceptable."),
    # D — Phase C Solana lifecycle close (deferred)
    ("D12_orca_close_whirlpool", 3, "Phase C Solana close lifecycle deferred — needs @orca-so/whirlpools-sdk decreaseLiquidity+collect+close hand-roll."),
    ("D13_raydium_clmm_close", 3, "Phase C Solana close lifecycle deferred — needs raydium-sdk-v2 close_position."),
    ("D14_meteora_dlmm_remove", 4, "Phase C Solana close lifecycle deferred — needs @meteora-ag/dlmm removeLiquidityByRange."),
    ("D15_kamino_lend_withdraw", 3, "Phase C Solana close lifecycle deferred — needs klend-sdk withdraw."),
    # E — vault registry expansions requiring verified on-chain addresses
    ("E09_eth_to_arb_morpho", 3, "ERC-4626 vault registry: Morpho Blue MetaMorpho USDC on Arbitrum needs verified address. V5 hard rule forbids guessing."),
    ("E09_eth_to_arb_morpho", 4, "Same — Arb Morpho USDC vault registry gap."),
    ("E11_eth_to_arb_yearn_weth", 3, "ERC-4626 vault registry: Yearn V3 yvWETH on Arbitrum needs verified address. V5 hard rule forbids guessing."),
    ("E11_eth_to_arb_yearn_weth", 4, "Same — Arb Yearn WETH vault registry gap."),
    # F — Token-2022 hook routing (Phase E.7 deferred)
    ("F07_token_2022_hook", 1, "Phase E.7 Token-2022 hook routing deferred — Solana mint with transfer hook requires sidecar adapter expansion."),
    ("F07_token_2022_hook", 4, "Same — Token-2022 routing deferred."),
    # H — §7 funding scenarios (Phase E deferred)
    ("H07_S7_dust_mixing", 1, "§7 S7 dust-mixing multi-input detector + composed plan deferred."),
    ("H08_S8_partial_allowance", 1, "§7 S8 partial allowance delta detector + top-up step deferred."),
    # I — Phase D on-chain session-key enforcement (broadcast pending)
    # I01-I05 chains expected to surface PENDING or honest stub posture
    # until Phase D ships installModule broadcast + Phantom delegate.
]


def is_expected_blocked(chain_id: str, turn_idx: int) -> bool:
    """True when this (chain, turn) is a known typed-recovery spec gap."""
    for cid, t, _ in EXPECTED_BLOCKED:
        if cid == chain_id and t == turn_idx:
            return True
    return False


def reason_for(chain_id: str, turn_idx: int) -> str | None:
    for cid, t, reason in EXPECTED_BLOCKED:
        if cid == chain_id and t == turn_idx:
            return reason
    return None
