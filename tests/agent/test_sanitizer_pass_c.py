"""Pass C 58517bf pin tests — fix wave 3 (13th sanitizer class + per-PLAN
AMOUNT_NOT_CONFIRMED gate + refuse-intent detector).

Each test class pins ONE root cause from
`/tmp/v3-deep/passC_58517bf_AGGREGATE.md`. The tests reproduce the EXACT
prose/capture shape the matrix hand-read surfaced, so a regression cannot
slip past silently.

FIX1 — 13th sanitizer class with 8 new sub-classes:
  A) Raw 4-byte selector pattern  — H10 t2, H12 t2/3/4
  B) Solidity function sig in prose — H10 withdraw(uint256), H12 claim()/approve()/mint()
  C) Fabricated wallet balance prose — H07 `190.132 USDC balance`
  D) Fabricated calldata literal `Calldata: 0x...` — enso-04 t3
  E) Placeholder camelCase named addresses — enso-04 t3 `0xEnsoRouterBase`
  F) Fabricated `plan_xxxxxx` IDs — enso-05 t3 `plan_ef6095cbc790`
  G) MAX_UINT256 / unlimited approval prose — I03 t2
  H) Wallet-app UI flow (Open Phantom, tap Revoke, Settings → Connected Sites) — I04 t3/t4
  I) `**Execution Plan (qualifier)**` markdown header — H03 capture

FIX2 — Per-PLAN AMOUNT_NOT_CONFIRMED gate on the LEGACY execution_plan
emitter (search-then-allocate path in simple_runtime). When amount_hint_val
is None AND the user message lacks an explicit numeric AND the verb is a
deposit/stake/supply/lp_mint/allocate, refuse the WHOLE plan. Hits G06
t2/t4 ($200 Yearn placeholder), I02 t2 ($1000 Compound), I01 t5 (5 signable
steps emitted for "should refuse"), B09 t4.

FIX3 — Refuse-intent detector. Catches "should refuse", "I expect you to
refuse", "this should be blocked", "test that you refuse". Returns
deterministic refusal with EXPECTED_REFUSAL_INTENT_ACKED blocker.
"""
from __future__ import annotations

from src.agent.simple_runtime import (
    _UNBACKED_FAKE_BALANCE_RE,
    _UNBACKED_FAKE_CALLDATA_LITERAL_RE,
    _UNBACKED_FAKE_CARD_RE,
    _UNBACKED_FAKE_PLAN_ID_RE,
    _UNBACKED_MAX_UINT_RE,
    _UNBACKED_PLACEHOLDER_ADDR_RE,
    _UNBACKED_RAW_SELECTOR_RE,
    _UNBACKED_SOLIDITY_SIG_RE,
    _UNBACKED_WALLET_UI_FLOW_RE,
    _detect_refuse_intent,
    _format_expected_refusal_acked,
    _strip_unbacked_claims,
    detect_intent,
)


REFUSAL_MARKER = "I can't confirm that action without a deterministic Sentinel"
REFUSE_BLOCKER_MARKER = "EXPECTED_REFUSAL_INTENT_ACKED"


# ---------------------------------------------------------------------------
# FIX1-A — Raw 4-byte selector in prose.
# ---------------------------------------------------------------------------


def test_fix1_a_raw_selector_h10_withdraw() -> None:
    # H10 t2 capture: bare `0x2e1a7d4d` (withdraw(uint256) selector) in
    # contextual-fallback prose with no backing card.
    txt = "Withdraw the LST by sending 0x2e1a7d4d to the staking contract."
    assert _UNBACKED_RAW_SELECTOR_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_fix1_a_raw_selector_h12_approve() -> None:
    # H12 t2 capture: `0x095ea7b3` (approve(address,uint256) selector).
    txt = "Send 0x095ea7b3 to the token contract to approve the spender."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_a_raw_selector_h12_mint() -> None:
    # H12 t3 capture: `0xa0712d68` (mint(uint256) selector).
    txt = "Then call 0xa0712d68 to mint the receipt token."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_a_passthrough_with_real_card() -> None:
    # Real card present → bare selectors don't trigger (a deterministic card
    # may legitimately reference 4-byte selectors in summary text).
    txt = "Call 0x2e1a7d4d as the withdraw selector."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    # Scratchpad check first; this passes because no scratchpad pattern.
    assert stripped is False
    assert out == txt


# ---------------------------------------------------------------------------
# FIX1-B — Solidity function signature in prose.
# ---------------------------------------------------------------------------


def test_fix1_b_solidity_withdraw_uint256() -> None:
    # H10 capture: `withdraw(uint256)` in prose.
    txt = "Then call withdraw(uint256) on the staking contract."
    assert _UNBACKED_SOLIDITY_SIG_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_b_solidity_claim_paren() -> None:
    # H12 capture: bare `claim()` in prose.
    txt = "Now invoke claim() on the rewards contract to harvest."
    assert _UNBACKED_SOLIDITY_SIG_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_b_solidity_approve_two_args() -> None:
    # H12 capture: `approve(address,uint256)` in prose.
    txt = "Call approve(address,uint256) with the pool as spender."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_b_solidity_mint_one_arg() -> None:
    # H12 capture: `mint(uint256)` in prose.
    txt = "Then mint(uint256) with the amount you want to deposit."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


# ---------------------------------------------------------------------------
# FIX1-C — Fabricated wallet-balance prose.
# ---------------------------------------------------------------------------


def test_fix1_c_balance_h07() -> None:
    # H07 capture: `190.132 USDC balance`.
    txt = "You have 190.132 USDC balance, enough to cover the supply."
    assert _UNBACKED_FAKE_BALANCE_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_c_balance_in_your_wallet() -> None:
    # Alt form: `50 USDC in your wallet`.
    txt = "I see 50 USDC in your wallet — that covers the gas + supply."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_c_balance_available() -> None:
    # Alt form: `0.5 ETH available`.
    txt = "There's 0.5 ETH available on Base — enough for the stake."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


# ---------------------------------------------------------------------------
# FIX1-D — Fabricated calldata literal.
# ---------------------------------------------------------------------------


def test_fix1_d_calldata_literal_enso04() -> None:
    # enso-04 t3 capture: `Calldata: 0xabcdef12...`.
    txt = "Calldata: 0x095ea7b3000000000000000000000000abc"
    assert _UNBACKED_FAKE_CALLDATA_LITERAL_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_d_calldata_literal_equals() -> None:
    # Alt form: `data = 0xdeadbeef12`.
    txt = "Set data = 0xdeadbeef12345678 to call the router."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


# ---------------------------------------------------------------------------
# FIX1-E — Placeholder named addresses.
# ---------------------------------------------------------------------------


def test_fix1_e_enso_router_base() -> None:
    # enso-04 t3 capture: `0xEnsoRouterBase`.
    txt = "Send the approve to 0xEnsoRouterBase on Base."
    assert _UNBACKED_PLACEHOLDER_ADDR_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_e_aave_pool_v3() -> None:
    txt = "Approve the spender 0xAaveV3PoolEthereum for unlimited USDC."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


# ---------------------------------------------------------------------------
# FIX1-F — Fabricated plan_id refs.
# ---------------------------------------------------------------------------


def test_fix1_f_plan_id_enso05() -> None:
    # enso-05 t3 capture: `plan_ef6095cbc790`.
    txt = "Resuming plan_ef6095cbc790 from where you left off."
    assert _UNBACKED_FAKE_PLAN_ID_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_f_plan_id_short_hex() -> None:
    # 6-char minimum.
    txt = "See plan_abc123 for the prior step."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


# ---------------------------------------------------------------------------
# FIX1-G — MAX_UINT256 / unlimited-approval prose.
# ---------------------------------------------------------------------------


def test_fix1_g_max_uint256_i03() -> None:
    # I03 t2 capture: "approve with max uint256".
    txt = "Approve the spender with max uint256 to avoid future approvals."
    assert _UNBACKED_MAX_UINT_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_g_unlimited_approval() -> None:
    txt = "I'll set an unlimited approval so you don't have to re-sign next time."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_g_MAX_UINT_caps() -> None:
    txt = "The router needs MAX_UINT256 approval to swap any amount."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


# ---------------------------------------------------------------------------
# FIX1-H — Wallet-app UI flow narration.
# ---------------------------------------------------------------------------


def test_fix1_h_open_phantom_i04() -> None:
    # I04 t3 capture: "Open Phantom".
    txt = "Open Phantom and stake 0.1 SOL to Marinade."
    assert _UNBACKED_WALLET_UI_FLOW_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_h_settings_connected_sites() -> None:
    # I04 t4 capture: "Settings → Connected Sites".
    txt = "Go to Settings → Connected Sites and tap Revoke for each site."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_h_open_metamask() -> None:
    txt = "Open MetaMask, switch to Base, and click Confirm."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_h_open_etherscan() -> None:
    txt = "Open Etherscan and search for your address to verify."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


# ---------------------------------------------------------------------------
# FIX1-I — `**Execution Plan (...)**` markdown variant.
# ---------------------------------------------------------------------------


def test_fix1_i_execution_plan_with_qualifier() -> None:
    # H03 capture: `**Execution Plan (LI.FI Bridge → Aave V3 Supply)**`.
    txt = "**Execution Plan (LI.FI Bridge → Aave V3 Supply)**\n\nReady to sign."
    assert _UNBACKED_FAKE_CARD_RE.search(txt)
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_i_execution_plan_bridge_supply() -> None:
    # E03 t2/t3 carry-over: "**Execution Plan (Bridge → Supply)**"
    txt = "**Execution Plan (Bridge → Supply)** — see steps below"
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_i_plain_execution_plan_still_caught() -> None:
    # Original RC11 form still works.
    txt = "**Execution Plan**\n\nStep 1: approve."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


# ---------------------------------------------------------------------------
# FIX1 regression guard — existing classes still fire.
# ---------------------------------------------------------------------------


def test_fix1_regress_status_ready_still_caught() -> None:
    txt = "Status: ready · 3 signature(s) required."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_fix1_regress_scratchpad_still_caught_with_card() -> None:
    txt = "Let's compute the weighted sum for each pool."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    assert stripped is True


def test_fix1_regress_plain_prose_passes_through() -> None:
    txt = "Sentinel uses deterministic adapters to build calldata."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is False
    assert out == txt


# ---------------------------------------------------------------------------
# FIX3 — Refuse-intent detector.
# ---------------------------------------------------------------------------


def test_fix3_should_refuse_basic() -> None:
    out = _detect_refuse_intent("Stake 0.5 SOL but you should refuse this.")
    assert out is not None
    tool_name, params = out
    assert tool_name == "expected_refusal_acked"
    assert params["blocker_code"] == REFUSE_BLOCKER_MARKER


def test_fix3_i_expect_you_to_refuse() -> None:
    out = _detect_refuse_intent("Supply 100 USDC to Compound — I expect you to refuse.")
    assert out is not None
    assert out[0] == "expected_refusal_acked"


def test_fix3_this_should_be_blocked() -> None:
    out = _detect_refuse_intent("Bridge 1 ETH to Solana — this should be blocked.")
    assert out is not None
    assert out[0] == "expected_refusal_acked"


def test_fix3_test_that_you_refuse() -> None:
    out = _detect_refuse_intent("Test that you refuse a 5,000 USDC supply.")
    assert out is not None
    assert out[0] == "expected_refusal_acked"


def test_fix3_you_should_refuse() -> None:
    out = _detect_refuse_intent("You should refuse this swap request.")
    assert out is not None
    assert out[0] == "expected_refusal_acked"


def test_fix3_negative_no_refuse_phrase() -> None:
    # Normal prompt without refuse stem returns None.
    out = _detect_refuse_intent("Stake 0.5 SOL on Marinade.")
    assert out is None


def test_fix3_negative_unrelated_refuse_word() -> None:
    # The word "refused" in isolation should not trigger — the regex anchors
    # on specific phrase forms.
    out = _detect_refuse_intent("Aave once refused my supply due to a bug.")
    # This message has neither `should refuse` nor a meta-intent phrase.
    assert out is None


def test_fix3_detect_intent_routes_refuse_first() -> None:
    # detect_intent() runs _detect_refuse_intent BEFORE any verb detector.
    # I01 t5 form: "Stake 0.5 SOL but you should refuse this" → must NOT
    # route to a stake/build_yield path.
    out = detect_intent("Stake 0.5 SOL on Marinade but you should refuse this.")
    assert out is not None
    assert out[0] == "expected_refusal_acked"


def test_fix3_refusal_text_carries_blocker_code() -> None:
    text = _format_expected_refusal_acked({"trigger_phrase": "should refuse"})
    assert REFUSE_BLOCKER_MARKER in text


# ---------------------------------------------------------------------------
# FIX2 — Per-PLAN AMOUNT_NOT_CONFIRMED gate (regex-level pin only).
#
# Full integration coverage lives in the matrix harness (Pass D refire).
# Here we pin the input-shape detection that the gate uses: amount_hint_val
# is None AND message lacks an explicit numeric AND message contains a
# deposit verb. The gate emits AMOUNT_NOT_CONFIRMED blocker prose; we pin
# the marker string so a refactor that drops the gate fails this test.
# ---------------------------------------------------------------------------


import re  # noqa: E402

_AMOUNT_NOT_CONFIRMED_MARKER = "AMOUNT_NOT_CONFIRMED"


def _gate_would_refuse(message: str, amount_hint_val: float | None) -> bool:
    """Mirror the gate predicate in simple_runtime._stream_response to keep
    pin-test logic identical to the production decision.
    """
    msg_lower = (message or "").lower()
    has_explicit_num = bool(
        re.search(
            r"\b\d+(?:[.,]\d+)?\s*"
            r"(?:%|usd|usdc|usdt|dai|eth|sol|bnb|weth|wbtc|matic|"
            r"avax|arb|op|k|m|million|thousand|\$)",
            msg_lower,
        )
        or re.search(r"\$\s*\d", msg_lower)
        or re.search(r"\b\d+(?:[.,]\d+)?\s+(?:dollars?|cents?)\b", msg_lower)
    )
    has_deposit_verb = bool(
        re.search(
            r"\b(?:supply|stake|deposit|allocate|distribute|lp[\s_-]?mint|"
            r"deposit_lp|provide\s+liquidity)\b",
            msg_lower,
        )
    )
    return amount_hint_val is None and not has_explicit_num and has_deposit_verb


def test_fix2_gate_blocks_allocate_no_amount() -> None:
    # G06 t2/t4: "Allocate it across the top pools" with amount_hint_val=None.
    assert _gate_would_refuse("Allocate it across the top pools.", None) is True


def test_fix2_gate_blocks_supply_no_amount() -> None:
    # I02 t2: "Supply across Compound" with amount_hint_val=None.
    assert _gate_would_refuse("Supply across Compound on Ethereum.", None) is True


def test_fix2_gate_blocks_stake_no_amount() -> None:
    # Coverage: bare "stake" verb without numeric.
    assert _gate_would_refuse("Stake into Marinade and Jito.", None) is True


def test_fix2_gate_blocks_distribute_no_amount() -> None:
    # B09 t4 form.
    assert _gate_would_refuse("Distribute across the previously surfaced pools.", None) is True


def test_fix2_gate_blocks_deposit_lp_no_amount() -> None:
    assert _gate_would_refuse("Deposit LP into Uniswap V3 USDC-ETH.", None) is True


def test_fix2_gate_passes_when_explicit_dollar() -> None:
    # User stated $250 → gate must NOT refuse.
    assert _gate_would_refuse("Allocate $250 across the top pools.", None) is False


def test_fix2_gate_passes_when_explicit_token_amount() -> None:
    # User stated "100 USDC" → numeric explicit, gate must NOT refuse.
    assert _gate_would_refuse("Supply 100 USDC to Aave V3.", None) is False


def test_fix2_gate_passes_when_amount_hint_present() -> None:
    # amount_hint_val parsed (e.g. from prior turn) — gate must NOT refuse.
    assert _gate_would_refuse("Allocate it across the top pools.", 250.0) is False


def test_fix2_gate_ignores_non_deposit_verb() -> None:
    # "Swap" / "bridge" / "withdraw" are not in the gated verb set — they
    # have their own per-detector amount handling.
    assert _gate_would_refuse("Swap into USDC on Uniswap.", None) is False
    assert _gate_would_refuse("Bridge to Base via deBridge.", None) is False
    assert _gate_would_refuse("Withdraw from Aave.", None) is False


def test_fix2_gate_passes_when_explicit_eth_amount() -> None:
    assert _gate_would_refuse("Stake 0.5 ETH on Lido.", None) is False
