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
    # E — vault registry expansions requiring verified on-chain addresses.
    # E09 entries RETIRED 2026-05-20 — Reviewer E findings confirmed Morpho
    # Blue MetaMorpho USDC Arb is now in src/defi/execution/adapters/erc4626.py:78
    # (Gauntlet USDC Prime 0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed).
    # E11 still legit — builder never reached vault resolution due to
    # BUG-E-002 (senderAddress=guest passed to DLN).
    ("E11_eth_to_arb_yearn_weth", 3, "ERC-4626 vault registry: Yearn V3 yvWETH on Arbitrum needs verified address. V5 hard rule forbids guessing."),
    ("E11_eth_to_arb_yearn_weth", 4, "Same — Arb Yearn WETH vault registry gap."),
    # F — Token-2022 hook routing (Phase E.7 deferred)
    ("F07_token_2022_hook", 1, "Phase E.7 Token-2022 hook routing deferred — Solana mint with transfer hook requires sidecar adapter expansion."),
    ("F07_token_2022_hook", 4, "Same — Token-2022 routing deferred."),
    # H — §7 funding scenarios (Phase E deferred)
    ("H07_S7_dust_mixing", 1, "§7 S7 dust-mixing multi-input detector + composed plan deferred."),
    ("H08_S8_partial_allowance", 1, "§7 S8 partial allowance delta detector + top-up step deferred."),
    # F01 — by-design BLOCKED turn 1 ('NonExistentProtocol' triggers
    # UNSUPPORTED_ADAPTER explicitly per chain expect_blockers field)
    ("F01_unsupported_adapter", 1, "Chain expect_blockers=['UNSUPPORTED_ADAPTER'] — turn 1 message names a non-existent protocol intentionally to surface the recovery posture."),
    # C14 Meteora DLMM SOL-USDC native deposit — Phase B Solana hand-rolled
    # adapter deferred (Meteora DAMM v2 / DLMM SDK integration).
    ("C14_meteora_dlmm", 4, "Phase B Solana hand-rolled deferred — Meteora DLMM open_position via @meteora-ag/dlmm SDK."),
    # F04 Pendle PENDING_EPOCH_ENTRY — chain expect_blockers covers it
    ("F04_pendle_pending_epoch", 1, "Chain expect_blockers=['PENDING_EPOCH_ENTRY','NEEDS_FRONTEND_SDK'] — Pendle real ApproxParams Hosted-SDK integration deferred."),
    # G04 chain expects unsupported_adapter on turn 1 explicitly
    ("G04_pick_alt_pool_after_blocker", 1, "Chain expect_blockers=['UNSUPPORTED_ADAPTER','ADAPTER_BUILD_FAILED'] — turn 1 'NonExistentVault' surfaces recovery posture intentionally."),
    # D05 turn 1 'Balancer wstETH-WETH deposit' — no amount, runtime synthesizes
    # 100 USD default which Enso /shortcuts/route can't resolve for the
    # Balancer-V3 ETH path on base. Spec route: explicit amount in turn 1 or
    # text-only no-amount form. Phase E.1 enhancement.
    ("D05_balancer_exit_pool", 1, "No-amount Balancer deposit form — Enso shortcut routes 404 on synthesized $100 default. Phase E.1 enhancement."),
    ("D05_balancer_exit_pool", 2, "Turn 2 also blocked while turn 1 still resolving — chain expects amount-refinement to succeed once turn 1 emits pool_link."),
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
