"""Matrix Pass A wave 6 — multi-defect fix pin tests.

Wave 5 hand-read across A/B/C/D/E/F/G/H/I surfaced:
1. **CRITICAL** D02 t3 Aave V3 ERC20 USDC `withdraw(amount=0)` drains entire
   aUSDC balance via MAX_UINT256 calldata — same defect class as wave-3
   ERC-4626 and Aave WTG3 drain-guards but on a THIRD adapter.
2. **DRAIN-EQUIV** D05 t2 "Exit Balancer wsteth-weth with 0.5 BPT" was
   matching `_detect_add_liquidity` or sibling deposit-side detector BEFORE
   `_detect_lifecycle_withdraw`, producing a READY 3-step `joinPool` deposit
   plan instead of the expected exit_pool path.
3. Sanitizer regex evasions: F10 t3 "gives you about N ETH", H09 "Top-up
   confirmed", H14 backticked Solidity verbs, H08 bare 40-hex spender,
   H04 t2 bridge-fee fabrication, H05 t2 JLP composition, H07 t2 wallet-
   state, E02 t3 / E05 t2 slippage/protocol-fee invention, F02 t4
   confirmation-without-card, A17 t2 future-tense "you'll receive a tx
   hash", I05 t1 MUTATED "impl address will be the contract address
   created in that transaction", F04 t2 fabricated Pendle epoch dates.
4. Sanitizer `card_ids` bypass too permissive: I02 t3 "Enable a keeper-
   based trigger (e.g., Gelato or Sentinel's autonomous module)" leaks
   through because the same turn emitted defi_opportunities + allocation
   cards. A research/allocation card does NOT back third-party-keeper
   recommendations or imperative dApp UI flows.
5. Body-scan misses CoT AFTER markdown structural block: A09 t3 4 kB
   leak after alloc table; B11 t4 / B13 t4 second `## Allocation`
   heading override.

Wave 6 ships:
1. `AaveV3SupplyAdapter` ERC20 `pool.withdraw` path requires
   `extra.withdraw_all=true` to mint MAX_UINT256; refuses amount=0 otherwise.
2. Detector dispatch order: `_detect_lifecycle_withdraw` +
   `_detect_lifecycle_borrow_repay` run BEFORE `_detect_direct_pool_deposit`
   / `_detect_slipstream_lp` / `_detect_add_liquidity` / `_detect_lp_with_my`.
3. `_FREEFORM_TX_STATE_HALLUCINATION_RE` broadened with 14 new shapes.
4. `_FREEFORM_IMPERATIVE_UI_HALLUCINATION_RE` NEW — UNGATED pass that
   runs regardless of `card_ids` (closes keeper / dApp-UI / invented-cap /
   sign-AA-policy patterns).
5. `_BODY_SCRATCHPAD_STRONG_RE` extended with "We need to allocate",
   "I'll choose/show", "Better to allocate", "Safer to", "Now compute
   blended" — first-person planning markers that escape lead-strip.
6. `_SECOND_ALLOCATION_HEADING_RE` truncates body at second `## Allocation`
   heading.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.agent.simple_runtime import (
    _FREEFORM_HALLUCINATION_REFUSAL,
    _FREEFORM_IMPERATIVE_UI_HALLUCINATION_RE,
    _FREEFORM_TX_STATE_HALLUCINATION_RE,
    _strip_freeform_tx_state_hallucinations,
    _strip_strategy_scratchpad,
)


# ─── Aave V3 ERC20 withdraw(0) drain-guard (CRITICAL) ─────────────────────


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_aave_v3_erc20_withdraw_zero_refused_without_withdraw_all():
    """D02 t3 wave-5 drain regression: Aave V3 ERC20 USDC withdraw(0)
    silently rewrote to MAX_UINT256 calldata. User signing a "Withdraw
    0 USDC" plan would have drained the entire aUSDC balance.

    Wave-6: same defense as wave-3 ERC-4626/WTG3 — refuse amount_in=0
    unless extra.withdraw_all=true."""
    from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter
    from src.defi.execution.adapters.base import YieldBuildRequest

    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="base",
        protocol="aave-v3",
        asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    with pytest.raises(ValueError, match="amount_in must be > 0"):
        _run(a.build(req))


def test_aave_v3_erc20_withdraw_all_explicit_passes():
    """When extra.withdraw_all=true, amount=0 is accepted and calldata
    correctly uses MAX_UINT256 + description says "Withdraw ALL"."""
    from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter
    from src.defi.execution.adapters.base import YieldBuildRequest

    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="base",
        protocol="aave-v3",
        asset_in="USDC",
        amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw", "withdraw_all": True},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    s = steps[0]
    assert s.transaction.data.startswith("0x69328dec")
    assert "f" * 64 in s.transaction.data.lower()
    assert "ALL" in s.description


def test_aave_v3_erc20_withdraw_real_amount_works():
    """Non-zero amount works without the flag — regression check."""
    from src.defi.execution.adapters.aave_v3 import AaveV3SupplyAdapter
    from src.defi.execution.adapters.base import YieldBuildRequest

    a = AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="base",
        protocol="aave-v3",
        asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "withdraw"},
    )
    steps = _run(a.build(req))
    assert len(steps) == 1
    s = steps[0]
    assert s.transaction.data.startswith("0x69328dec")
    assert "f" * 64 not in s.transaction.data.lower()
    assert "ALL" not in s.description


# ─── Balancer exit verb router (DRAIN-EQUIV) ──────────────────────────────


def test_balancer_exit_routes_to_withdraw_not_deposit():
    """D05 t2: 'Exit Balancer wsteth-weth with 0.5 BPT' must route to
    the lifecycle withdraw path (action=exit_pool), NOT the add-liquidity
    deposit path. Wave-5 was emitting a READY 3-step joinPool deposit
    plan — drain-equivalent."""
    from src.agent.simple_runtime import detect_intent

    intent = detect_intent("Exit Balancer wsteth-weth with 0.5 BPT")
    assert intent is not None
    tool, args = intent
    assert tool == "build_yield_execution_plan"
    assert args.get("action") in ("exit_pool", "withdraw"), (
        f"Balancer exit must NOT route to deposit_lp; got action={args.get('action')!r}"
    )
    assert args.get("protocol") in ("balancer", "balancer-v2", "balancer-v3")


def test_balancer_bare_exit_still_routes_to_withdraw():
    """Bare 'Exit Balancer wsteth-weth' (no amount) — adapter substitutes
    max-uint BPT for full position close. Must NOT misroute to deposit_lp."""
    from src.agent.simple_runtime import detect_intent

    intent = detect_intent("Exit Balancer wsteth-weth")
    assert intent is not None
    tool, args = intent
    assert tool == "build_yield_execution_plan"
    assert args.get("action") in ("exit_pool", "withdraw"), (
        f"Bare Balancer exit must NOT route to deposit_lp; got action={args.get('action')!r}"
    )


def test_balancer_deposit_still_routes_to_deposit_lp():
    """Regression: Balancer DEPOSIT phrasing must still route to
    deposit_lp/supply path. Re-ordering must not break the normal flow."""
    from src.agent.simple_runtime import detect_intent

    intent = detect_intent("Deposit 0.05 ETH into Balancer wstETH-WETH")
    assert intent is not None
    tool, args = intent
    # Either build_yield_execution_plan with action=deposit_lp/supply OR
    # execute_pool_position — both correct for deposit.
    assert tool in ("build_yield_execution_plan", "execute_pool_position")
    if tool == "build_yield_execution_plan":
        assert args.get("action") in (
            "deposit_lp",
            "supply",
            "add_liquidity",
        ), f"Balancer deposit should not route to withdraw; got action={args.get('action')!r}"


# ─── Sanitizer regex expansions (wave-5 evading shapes) ───────────────────


def test_f10_t3_gives_you_about_refused():
    """F10 t3 mutation: 'Swapping 100 USDC to ETH on Base gives you about
    0.062 ETH (≈$100).' Wave-5 only caught `yields|delivers`; wave-6 adds
    `gives you about`."""
    leak = (
        "Swapping 100 USDC to ETH on Base gives you about 0.062 ETH (≈$100). "
        "This is a MEDIUM-risk trade; use a modest slippage tolerance "
        "(≈0.5%) and verify the router contract before confirming."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_h09_top_up_confirmed_refused():
    """H09 t3: 'Top-up confirmed. Please approve the bridge transaction'
    — verified the chokepoint catches the bare phrase regardless of
    surrounding clause."""
    leak = (
        "Top-up confirmed. Please approve the bridge transaction (step 1) "
        "in your wallet; once it's confirmed, the supply step will be ready "
        "to execute."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_h04_t2_bridge_fee_fabrication_refused():
    """H04 t2: 'Estimated bridge fee: ~0.1% of amount + Ethereum gas
    (≈ $0.50–$1.00). Typical execution time: 2–5 minutes after
    confirmation on Ethereum.'"""
    leak = (
        "Bridge Leg (Ethereum → Solana) — Asset: 100 USDC (ERC-20) — "
        "Route: Ethereum Mainnet → Solana Mainnet via deBridge (DLN) — "
        "Estimated bridge fee: ~0.1% of amount + Ethereum gas (≈ $0.50–$1.00 "
        "at current gas prices) — Typical execution time: 2–5 minutes after "
        "confirmation on Ethereum"
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_h05_t2_jlp_composition_refused():
    """H05 t2: 'JLP composition (approx.) — SOL ≈ 45%, ETH ≈ 20%,
    USDC ≈ 15%, USDT ≈ 10%, Other ≈ 10%'"""
    leak = (
        "JLP (Jupiter Liquidity Pool) composition (approx.):\n"
        "- SOL ≈ 45%\n"
        "- ETH ≈ 20%\n"
        "- USDC ≈ 15%\n"
        "- USDT ≈ 10%\n"
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_h07_t2_wallet_state_assertion_refused():
    """H07 t2: 'You already hold 50 USDC, 50 USDT, and 50 DAI…'"""
    leak = (
        "You already hold 50 USDC, 50 USDT, and 50 DAI, which matches the "
        "Curve 3pool ratio, so no token swaps are needed before the deposit."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_h07_t3_dust_mix_confirmed_refused():
    """H07 t3: 'Dust mix confirmed – no residual dust remains'"""
    leak = "Dust mix confirmed – no residual dust remains after the deposit."
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e05_t2_fabricated_protocol_fee_refused():
    """E05 t2: 'Protocol fee: ~0.10% → ≈ 0.20 USDC; Gas on Arbitrum:
    ~0.0004 ETH → ≈ 0.70 USDC; Total ≈ 0.90 USDC (≈ 0.45%)'"""
    leak = (
        "Bridge fee estimate for 200 USDC (Arbitrum → Base via deBridge DLN): "
        "Protocol fee: ~0.10% → ≈ 0.20 USDC; "
        "Gas on Arbitrum: ~0.0004 ETH → ≈ 0.70 USDC (≈ $1,750/ETH); "
        "Total ≈ 0.90 USDC (≈ 0.45%)"
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e02_t3_slippage_band_invention_refused():
    """E02 t3: 'slippage band for the Arbitrum Gateway bridge is 0.5%'"""
    leak = (
        "The slippage band for the Arbitrum Gateway bridge is 0.5%. Once "
        "you connect a wallet, approve and sign the transaction in your "
        "wallet to bridge 200 USDC from Ethereum to Arbitrum and then "
        "supply it to Compound V3 on Arbitrum."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e03_t3_ill_generate_plan_refused():
    """E03 t3: 'I'll generate the exact LI.FI bridge transaction followed
    by the Aave V3 supply approval and deposit steps'"""
    leak = (
        "Once your wallet is connected, I'll generate the exact LI.FI "
        "bridge transaction followed by the Aave V3 supply approval and "
        "deposit steps for Arbitrum."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e13_t2_bridge_route_invention_refused():
    """E13 t2: 'Bridge route: Ethereum → deBridge DLN → Polygon (DAI, 100 DAI)'"""
    leak = (
        "Bridge route: Ethereum → deBridge DLN → Polygon (DAI, 100 DAI). "
        "Risk: Medium."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_f04_t2_pendle_epoch_schedule_fabrication_refused():
    """F04 t2: 'Pendle's PT-USDe minting epochs open every Thursday at
    00:00 UTC…'"""
    leak = (
        "Pendle's PT-USDe minting epochs open every Thursday at 00:00 UTC "
        "and run through the following Wednesday. Based on today's date "
        "(Wednesday 24 Sep 2025), the next epoch starts Thursday 25 Sep 2025 "
        "at 00:00 UTC."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_f02_t4_confirmation_without_card_refused():
    """F02 t4: 'Supply 100 USDC to Aave V3 on Base. Risk: MEDIUM. Confirm
    if you'd like to proceed.' — primes user to type yes → cascades to fake
    tx-state next turn."""
    leak = (
        "Supply 100 USDC to Aave V3 on Base. Risk: MEDIUM (smart-contract "
        "exposure). Confirm if you'd like to proceed."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_a17_t2_future_tense_narrated_wallet_steps_refused():
    """A17 t2: 'approve the contract for 0.05 ETH, then submit the stake
    transaction. Once signed, you'll receive a transaction hash you can
    track on a Mantle explorer.'"""
    leak = (
        "Staking on Mantle: approve the contract for 0.05 ETH, then submit "
        "the stake transaction. Once signed, you'll receive a transaction "
        "hash you can track on a Mantle explorer."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_i05_t1_impl_address_paraphrase_refused():
    """I05 t1 MUTATED: 'After you sign and submit the ZeroDev Kernel
    policy, the impl address will be the contract address created in that
    transaction. You can verify it in your wallet's transaction details
    or by looking up the tx on a block explorer.' — model paraphrased
    around the wave-5 regex; wave-6 catches the bare phrase 'impl address'."""
    leak = (
        "After you sign and submit the ZeroDev Kernel policy, the impl "
        "address will be the contract address created in that transaction. "
        "You can verify it in your wallet's transaction details or by "
        "looking up the tx on a block explorer."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_c05_approvals_already_set_refused():
    """C05 T1: 'Approvals for 0.05 ETH WETH and 100 USDC are already set
    for Velodrome CL on Optimism' — wave-5 missed "are already set" form."""
    leak = (
        "Approvals for 0.05 ETH WETH and 100 USDC are already set for "
        "Velodrome CL on Optimism."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Imperative UI / named keeper (UNGATED — runs regardless of card_ids) ─


def test_keeper_recommendation_refused_even_with_card_ids():
    """I02 t3: 'Enable a keeper-based trigger (e.g., Gelato or Sentinel's
    autonomous module) to repeat the allocation every 24h' — leaked
    through wave-5 chokepoint because card_ids was non-empty (defi_opps
    + allocation cards). Wave-6 UNGATED pass catches this."""
    leak = (
        "Enable a keeper-based trigger (e.g., Gelato or Sentinel's "
        "autonomous module) to repeat the allocation every 24 h; pause "
        "any pool whose APY falls below 2.5% and redistribute."
    )
    out = _strip_freeform_tx_state_hallucinations(
        leak, card_ids=["d019db6f-card", "280f8e0f-card"]
    )
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_nexus_dapp_imperative_ui_refused_even_with_card_ids():
    """I01 t2: 'Open the Nexus dApp, go to Portfolio, select your Aave V3
    position, tap Settings, enable Autonomous Rebalancing, set the daily
    cap to $500'"""
    leak = (
        "Open the Nexus dApp, go to Portfolio, select your Aave V3 position, "
        "tap Settings, enable Autonomous Rebalancing, set the daily cap to "
        "$500, and confirm the change."
    )
    out = _strip_freeform_tx_state_hallucinations(
        leak, card_ids=["some-card-id"]
    )
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_phantom_wallet_imperative_ui_refused():
    """I04 t2: 'Open your Phantom wallet, locate the signing request for
    the session keypair, review the message details, and approve.'"""
    leak = (
        "Open your Phantom wallet, locate the signing request for the "
        "session keypair, review the message details, and approve the "
        "signature."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_invented_daily_cap_refused():
    """I01 t2 / I05 t3: '$500 daily cap', '$200 daily budget'"""
    leak = (
        "Sign the ZeroDev Kernel policy for autonomous rebalancing with a "
        "$200 daily budget."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_sign_zerodev_policy_imperative_refused():
    """I05 t3 sign-imperative for AA policy."""
    leak = (
        "Sign the ZeroDev Kernel policy for autonomous rebalancing with a "
        "$200 daily budget."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Body-scan: trailing CoT after structured block ───────────────────────


def test_body_scan_strips_we_need_to_allocate_after_table():
    """A09 t3 wave-5 leak: 4 kB CoT AFTER alloc table starts with 'We
    need to allocate $500 across the same pools'."""
    leak = (
        "## Allocation\n"
        "\n"
        "| pool | weight | $ |\n"
        "|------|--------|---|\n"
        "| aave-usdc | 14.29% | $71.43 |\n"
        "| compound | 14.29% | $71.43 |\n"
        "\n"
        "Blended APY ~80%\n"
        "\n"
        "We need to allocate $500 across the same pools surfaced in prior "
        "turn. No explicit weighting request, so default to even split.\n"
        "So 7 pools => weight = 100/7 ≈ 14.2857% each.\n"
        "Plug w=14.284, w_h=14.296.\n"
    )
    out = _strip_strategy_scratchpad(leak)
    assert "We need to allocate" not in out
    assert "Plug w=" not in out
    assert "| aave-usdc | 14.29% | $71.43 |" in out
    assert "Blended APY" in out


def test_body_scan_truncates_second_allocation_heading():
    """B11 t4 wave-5: SECOND `## Allocation` heading with override pool
    not in canonical alloc card."""
    leak = (
        "## Allocation\n"
        "\n"
        "| # | pool | weight | $ |\n"
        "|---|------|--------|---|\n"
        "| 1 | uniswap-v4 GITLAWB | 20% | $200 |\n"
        "| 2 | uniswap-v4 POD | 20% | $200 |\n"
        "\n"
        "Total $1,000 across 5 positions — blended APY ~184.4%\n"
        "\n"
        "## Allocation\n"
        "\n"
        "| # | pool | weight | APY |\n"
        "|---|------|--------|-----|\n"
        "| 1 | uniswap-v4 ETH-PITCH | 100% | 513.6% |\n"
    )
    out = _strip_strategy_scratchpad(leak)
    # Second table cut.
    assert "ETH-PITCH" not in out
    assert "513.6%" not in out
    # First (canonical) preserved.
    assert "GITLAWB" in out
    assert "Total $1,000" in out


def test_body_scan_preserves_legitimate_single_allocation():
    """Single `## Allocation` heading should pass through unchanged
    (no second-heading truncation)."""
    plan = (
        "## Allocation\n"
        "\n"
        "| pool | weight |\n"
        "|------|--------|\n"
        "| aave-usdc | 50% |\n"
        "| compound | 50% |\n"
        "\n"
        "Blended APY 6.5%\n"
    )
    out = _strip_strategy_scratchpad(plan)
    assert "aave-usdc" in out
    assert "Blended APY 6.5%" in out


# ─── Positive cases — must not over-strip ─────────────────────────────────


def test_legitimate_plan_prose_passes_through_with_card_ids():
    """Real signable plan narration must pass through when card_ids
    attached."""
    prose = (
        "Your Aave V3 Supply transaction for 100 USDC is ready. Review and "
        "sign with your wallet to execute."
    )
    out = _strip_freeform_tx_state_hallucinations(
        prose, card_ids=["plan_real_card_id"]
    )
    assert out == prose


def test_benign_prose_passes_through():
    """Plain prose without tx-state must pass through."""
    benign = (
        "Aave V3 lets you supply USDC on Base. The current supply APY is "
        "around 5.2%. To start, send `Supply 100 USDC to Aave V3 on Base` "
        "as your next message."
    )
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    assert out == benign


def test_general_word_hold_does_not_trigger():
    """`you ... hold` matches a fabricated-balance ASSERTION; generic
    "BPT tokens are held by..." or "hold for the long term" must NOT
    trigger."""
    benign = (
        "BPT tokens are held by the pool. Once you mint LP, you hold a "
        "claim on the underlying tokens."
    )
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    assert out == benign


def test_imperative_ui_does_not_match_benign_prose():
    """`Open` followed by a non-dApp word must not trigger."""
    benign = (
        "The Aave V3 protocol is open-source. To interact, you can connect "
        "any wallet."
    )
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    assert out == benign
