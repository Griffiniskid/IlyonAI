"""Matrix Pass A wave 7 — additional drain + sanitizer fixes.

Wave 6 closed many but: (1) D-P0-10b Balancer exit STILL emitted READY
DEPOSIT plan because the dispatcher selected `execute_pool_position`
tool BEFORE the lifecycle detectors I re-ordered; (2) F04 t2 fabricated
Pendle epoch schedule regex didn't fire; (3) E02 t2/t4 sanitizer
regression — model used U+202F NARROW NO-BREAK SPACE between digits and
units defeating `\b` boundaries; (4) E01 t2/t3/t4 "Execution Plan will
move from `draft` to `executed` and the bridge will proceed" not
covered; (5) E04 t2 bare bridge claim "deBridge DLN is the bridge used
to move USDT" not covered; (6) H02 t2/t3 "**Swap leg** – Swap…" /
"**Split confirmed** –" not covered; (7) G04 T4 en-dash "Execution
Plan –" header bypass; (8) I02 t2 "$100 USDC per day" currency-token
cap paraphrase.

Wave 7 ships:
1. `execute_pool_position` tool early-guard refuses verb-inverted
   dispatch (`extra.action ∈ {exit, withdraw, remove, redeem, unstake,
   close, claim}`) — closes D-P0-10b regardless of dispatcher.
2. `_normalize_unicode_whitespace` pre-normalizer at sanitizer entry —
   coerces U+202F / U+00A0 / figure-space / IDEOGRAPHIC SPACE / etc.
   to plain ASCII space so `\b` and `\s` match.
3. Sanitizer regex expansion: state-machine narration ("Execution Plan
   will move from draft to executed", "bridge will proceed"); bare
   bridge claim ("X is the bridge used to"); "ready-to-sign plan" /
   "I can generate a signable plan" variants; swap-leg fabrication
   ("Swap leg – Swap X to Y", "Split confirmed –"); en-dash Execution
   Plan header ("**Execution Plan – Supply USDC to Aave V3 (Ethereum)**");
   broadened Pendle schedule (standalone "epochs open every Thursday",
   "next epoch starts Day Month Year", "Discord/announcements" citation);
   currency-token cap paraphrase ("$100 USDC per day").
"""
from __future__ import annotations

import asyncio

from src.agent.simple_runtime import (
    _FREEFORM_HALLUCINATION_REFUSAL,
    _normalize_unicode_whitespace,
    _strip_freeform_tx_state_hallucinations,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── D-P0-10b — Balancer exit at execute_pool_position guard ──────────────


def test_execute_pool_position_refuses_exit_pool_verb():
    """D-P0-10b wave-5/6 drain-equivalent: dispatcher selected
    `execute_pool_position` for "Exit Balancer wsteth-weth with 0.5 BPT"
    and the tool built a READY 3-step joinPool deposit plan. Wave-7
    early-guard refuses verb-inverted dispatch."""
    from src.agent.tools.execute_pool_position import execute_pool_position

    class _Ctx:
        wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        evm_wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        solana_wallet = None

    res = _run(execute_pool_position(
        _Ctx(),
        pool="balancer-wsteth-weth",
        amount="0.5",
        asset_in="BPT",
        chain="ethereum",
        extra={"action": "exit_pool"},
    ))
    # err_envelope returns a ToolEnvelope: res.error.code / res.error.message
    assert res.ok is False
    assert res.error.code.lower() == "verb_inverted"
    assert "deposit-only" in res.error.message


def test_execute_pool_position_refuses_all_exit_family_verbs():
    """All withdraw/exit/remove/redeem/unstake/close/claim verbs."""
    from src.agent.tools.execute_pool_position import execute_pool_position

    class _Ctx:
        wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        evm_wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        solana_wallet = None

    for verb in ("exit", "exit_pool", "withdraw", "withdraw_lp",
                 "remove", "remove_lp", "remove_liquidity",
                 "redeem", "redeem_bpt", "unstake", "liquid_unstake",
                 "close", "close_position", "claim", "harvest"):
        res = _run(execute_pool_position(
            _Ctx(),
            pool="balancer-wsteth-weth",
            amount="0.5",
            extra={"action": verb},
        ))
        assert res.ok is False, f"verb={verb!r} not refused"
        assert res.error.code.lower() == "verb_inverted", f"verb={verb!r} got {res.error.code!r}"


def test_execute_pool_position_accepts_deposit_verbs():
    """Regression: deposit/supply/stake/add must pass the guard."""
    from src.agent.tools.execute_pool_position import execute_pool_position

    class _Ctx:
        wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        evm_wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        solana_wallet = None

    for verb in ("deposit", "supply", "stake", "add_liquidity", "deposit_lp"):
        res = _run(execute_pool_position(
            _Ctx(),
            pool="aave-v3 USDC",
            amount="100",
            asset_in="USDC",
            chain="ethereum",
            extra={"action": verb},
        ))
        # Must not be verb_inverted refusal. May still error for other
        # reasons (missing pool resolver, etc.) but the verb guard must
        # have passed.
        if not res.ok:
            assert res.error.code.lower() != "verb_inverted", (
                f"verb={verb!r} blocked by guard"
            )


def test_execute_pool_position_pool_strip_signature_present():
    """Wave-7 strips trailing whitespace from `pool` argument. Verify
    the strip line exists in the tool (regression guard)."""
    src_path = "src/agent/tools/execute_pool_position.py"
    with open(src_path, encoding="utf-8") as f:
        body = f.read()
    # The wave-7 fix line strips whitespace before further processing.
    assert "pool = str(pool).strip()" in body


# ─── Unicode whitespace normalization ─────────────────────────────────────


def test_unicode_narrow_no_break_space_normalized():
    """U+202F NARROW NO-BREAK SPACE coerced to ASCII space."""
    src = "200 USDC supplied to Aave V3 with 0.5 % slippage."
    out = _normalize_unicode_whitespace(src)
    assert out == "200 USDC supplied to Aave V3 with 0.5 % slippage."


def test_unicode_no_break_space_normalized():
    """U+00A0 NO-BREAK SPACE coerced."""
    src = "Bridge 200 USDC from Ethereum."
    out = _normalize_unicode_whitespace(src)
    assert out == "Bridge 200 USDC from Ethereum."


def test_unicode_figure_space_normalized():
    """U+2007 FIGURE SPACE coerced."""
    src = "100 USDC supply at 5.2 % APY."
    out = _normalize_unicode_whitespace(src)
    assert out == "100 USDC supply at 5.2 % APY."


def test_e02_narrow_space_bypass_now_refused():
    """E02 t2/t4 wave-6 regression: "0.5 % slippage" with U+202F in
    "200 USDC" / "0.5 % slippage" defeats `\\b` boundaries. Wave-7
    normalizer pre-strips so the existing slippage_band regex fires."""
    leak = (
        "Please approve and sign the transaction in your wallet to bridge "
        "200 USDC from Ethereum to Arbitrum via deBridge (Arbitrum "
        "Gateway) with 0.5 % slippage band, then supply the bridged USDC "
        "to Compound V3 on Arbitrum."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── State-machine narration ──────────────────────────────────────────────


def test_e01_execution_plan_state_machine_narration_refused():
    """E01 t2/t3/t4 wave-6: "Execution Plan will move from `draft` to
    `executed` and the bridge will proceed"."""
    leak = (
        "Please sign the transaction in your connected wallet; once "
        "signed the Execution Plan will move from `draft` to `executed` "
        "and the bridge will proceed."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e08_ready_to_sign_plan_variant_refused():
    """E08 t3 wave-6: "I'll create a ready-to-sign plan to: 1. Bridge…
    2. Deposit…"."""
    leak = (
        "Once your wallet is linked, I'll create a ready-to-sign plan "
        "to: 1. Bridge 0.05 WETH from Ethereum → Base (via deBridge or "
        "the official Base bridge). 2. Deposit the received WETH into "
        "the Balancer WETH/WSTETH pool on Base."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e03_i_can_generate_signable_plan_refused():
    """E03 t2 wave-6 variant: "I can generate a signable Execution Plan"."""
    leak = (
        "Once your wallet is connected, I can generate a signable "
        "Execution Plan that bundles the LI.FI bridge step with the "
        "Aave V3 supply step."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e04_bare_bridge_claim_refused():
    """E04 t2 wave-6: "deBridge DLN is the bridge used to move USDT from
    Ethereum to Optimism"."""
    leak = (
        "deBridge DLN is the bridge used to move USDT from Ethereum to "
        "Optimism. Once your wallet is connected, the bridge order can "
        "be created."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Swap-leg + en-dash Execution Plan ────────────────────────────────────


def test_h02_swap_leg_fabrication_refused():
    """H02 t2 wave-6: "**Swap leg** – Swap 93.84 USDC → WETH on Base
    via Aerodrome Slipstream"."""
    leak = (
        "**Swap leg** – Swap 93.837662 USDC → WETH on Base via "
        "Aerodrome Slipstream (USDC-WETH pool) - **Route:** Aerodrome "
        "Slipstream (USDC-WETH) - **Estimated gas:** ~0.00045 ETH "
        "(≈ $0.80)"
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_h02_split_confirmed_refused():
    """H02 t3 wave-6: "**Split confirmed** – Swap 93.84 USDC → WETH"."""
    leak = (
        "**Split confirmed** – Swap 93.837662 USDC → WETH via "
        "Aerodrome Slipstream on Base. The remaining 106.162338 USDC "
        "will be supplied."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_g04_en_dash_execution_plan_refused():
    """G04 T4 wave-6: "**Execution Plan – Supply USDC to Aave V3
    (Ethereum)**" uses en-dash + "Execution Plan" verb header."""
    leak = (
        "**Execution Plan – Supply USDC to Aave V3 (Ethereum)**\n"
        "- **Action:** Supply USDC to Aave V3\n"
        "- **Amount:** 100 USDC\n"
        "- **Pool:** aave-v3 USDC (Ethereum) – pool_id aa70268e-...\n"
        "- **Expected APY:** 4.8%\n"
        "- **Estimated gas:** ~80k for approval + ~150k for supply\n"
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Pendle schedule actually-fires ───────────────────────────────────────


def test_pendle_schedule_actually_fires_now():
    """F04 t2 wave-6: wave-6 regex was too narrow. Wave-7 broadens to
    fire on standalone "epochs open every Thursday" + "next epoch starts
    Thursday DD Month YYYY" + "Discord/announcements" citation."""
    leak = (
        "Pendle's PT-USDe minting epochs open every Thursday at 00:00 "
        "UTC and run through the following Wednesday. Based on today's "
        "date (Wednesday 24 Sep 2025), the next epoch starts Thursday "
        "25 Sep 2025 at 00:00 UTC. You can see the live countdown in "
        "the Pendle app or their Discord/announcements for the exact "
        "time remaining."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_pendle_schedule_standalone_form_fires():
    """Bare standalone: "epochs open every Thursday" without protocol
    name nearby — wave-7 broadened the regex to match this form."""
    leak = (
        "Yield farming windows open every Thursday at 00:00 UTC. You can "
        "track the next round in their Discord/announcements."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Currency-token cap paraphrase ────────────────────────────────────────


def test_currency_token_cap_paraphrase_refused():
    """I02 t2 wave-6: "$100 USDC per day" / "$20 USDC to each" — token
    symbol between $<num> and per-day breaks wave-6 cap regex."""
    leak = (
        "The spend cap for your autonomous Compound V3 rebalance is "
        "**$100 USDC per day**. With the equal-weight allocation shown, "
        "each daily transaction will supply roughly **$20 USDC** to each "
        "of the five pools."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_currency_token_cap_with_card_ids_still_refused():
    """Currency-token cap fabrication runs through UNGATED imperative-UI
    pass (imperative-UI pattern matches) so it fires even when card_ids
    is non-empty."""
    leak = "Set a daily $200 USDC spend cap on your Compound V3 position."
    out = _strip_freeform_tx_state_hallucinations(
        leak, card_ids=["some-card-id"]
    )
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


# ─── Positive cases ───────────────────────────────────────────────────────


def test_benign_pendle_mention_passes_through():
    """Plain mention of Pendle without fabricated schedule passes."""
    benign = (
        "Pendle offers PT (principal token) and YT (yield token) "
        "instruments. Use `Pendle Mint PT-USDe on Ethereum` to begin."
    )
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    assert out == benign


def test_benign_unicode_space_passes_through():
    """Unicode-space normalization doesn't false-trigger on benign prose."""
    benign = "The current ETH price is around $3,500 USD on most CEXes."
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    assert out == benign
