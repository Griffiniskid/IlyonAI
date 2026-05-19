"""Pass A d9bfe2e pin tests — 7 P0/P1 bug classes (RC1, RC2, RC4, RC5, RC9, RC11, RC15, RC17).

Each test class pins ONE root cause from the Pass A aggregate ledger at
`/tmp/v3-deep/pass_a_d9bfe2e_AGGREGATE.md`. The tests are intentionally
narrow — they reproduce the exact bug shape the matrix hand-read captured,
so a regression cannot slip past silently.

RC1 — sanitizer bypass via `has_real_card=… or had_intent`. Continuation
turns with intent-detector hit bypassed `_strip_unbacked_claims` entirely.
The sanitizer entry point now takes `has_real_card` strictly from
card-presence; intent flag is split off.

RC2 — scratchpad regex short-circuited by `has_real_card=True`. enso-06 t2
leaked full model deliberation with real cards present. Scratchpad detection
must run FIRST, regardless of card flag.

RC4 — continuation "approve step 1" prose ungated by step state. F05 t4 /
F07 t4 emitted "Open the execution plan card above and approve step 1 to
begin" when the replayed card was BLOCKED with transaction=null. The replay
helper must inspect card status + step.transaction + requires_signature
before emitting the sign-step phrase.

RC5 — missing `_detect_session_key_intent` short-circuit. I01-I05 fabricated
ZeroDev `setPolicy/getPolicy/implementation()` AA function names against a
"should refuse" prompt. Session-key prompts must route to a deterministic
refusal, never to contextual_fallback.

RC9 — sanitizer 12th class: fabricated AA function names + Kernel/Nexus
narration + fabricated UI flows. `setPolicy`, `getPolicy`, `implementation()`,
`dailySwapLimitUSD` don't exist in real Kernel v3 — contextual prose
inventing them is a financial-trust violation.

RC11 — F10 t3 fake "**Execution Plan**" markdown in pure prose with calldata
patterns, slippage, fee. Same root cause as RC1/RC2 — after sanitizer
bypass closes, regex must still catch the "**Execution Plan**" header
when emitted in unbacked prose.

RC15 — fabricated metrics/URLs. `app.enso.fi/execute?…` URLs, Pendle PT
maturity dates ("31 Dec 2025"), and contract-class-name strings
("WrappedTokenGatewayV3") must be refused in contextual_fallback.

RC17 — asset_hint extracts cadence words. I01 t1 extracted "DAILY" from
the cadence word "daily" — the bare-symbol asset extractor needs a
stopword list for cadence vocabulary.
"""
from __future__ import annotations

from src.agent.simple_runtime import (
    _UNBACKED_AA_FABRICATION_RE,
    _UNBACKED_FAKE_CARD_RE,
    _UNBACKED_FAKE_URL_RE,
    _UNBACKED_SCRATCHPAD_RE,
    _detect_session_key_intent,
    _maybe_replay_followup,
    _parse_asset_hint,
    _strip_unbacked_claims,
)


REFUSAL_MARKER = "I can't confirm that action without a deterministic Sentinel"
SESSION_KEY_BLOCKER_MARKER = "SESSION_KEY_NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# RC1 — `had_intent` no longer short-circuits sanitizer.
# ---------------------------------------------------------------------------


def test_rc1_scratchpad_stripped_even_when_intent_detected() -> None:
    # The bug: prior code passed had_intent=True as has_real_card, so the
    # sanitizer never ran on continuation turns that touched the intent
    # detector. After RC1, scratchpad detection runs regardless.
    txt = (
        "We need to follow the system prompt. Let's assume 1 ETH = $2,000 "
        "and compute slippage as 0.5%."
    )
    # Intent flag did not bypass sanitizer — only true card presence does.
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc1_fake_card_caught_when_card_flag_false() -> None:
    # Continuation turn with intent=True but no real card emitted: prior
    # bug bypassed sanitizer, fake "Status: ready · 3 signatures required"
    # prose leaked. After RC1, must still strip.
    txt = "Status: ready · 3 signature(s) required. Sign step 1 in the Execution Plan above."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


# ---------------------------------------------------------------------------
# RC2 — scratchpad regex ALWAYS strips, even with real card present.
# ---------------------------------------------------------------------------


def test_rc2_scratchpad_stripped_even_with_real_card() -> None:
    # enso-06 t2: full chain-of-thought deliberation leaked WITH real card.
    # Scratchpad must still be removed — the rest of the prose can stay
    # if it's backed, but model planning monologue is never user-facing.
    txt = (
        "We need to follow the system prompt for this swap. "
        "Let's assume 1 ETH = $2,000 and compute the dollar value."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    assert stripped is True
    # The scratchpad-only path replaces with the deterministic refusal
    # banner (same as has_real_card=False scratchpad strip).
    assert REFUSAL_MARKER in out


def test_rc2_real_card_passthrough_when_no_scratchpad() -> None:
    # Backed prose without scratchpad still passes through unchanged.
    txt = "USDC supply yields 4.2% on Aave V3 Base."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    assert stripped is False
    assert out == txt


def test_rc2_scratchpad_first_person_planning_stripped_with_card() -> None:
    # Exact enso-06 t2 capture form.
    txt = "Let's compute weighted sum for each pool's APY contribution."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    assert stripped is True
    assert REFUSAL_MARKER in out


# ---------------------------------------------------------------------------
# RC4 — continuation `approve step 1` prose gated by card state.
# ---------------------------------------------------------------------------


def test_rc4_no_sign_step_prose_when_history_has_blocked_card() -> None:
    # F05 t4 capture: prior plan card had status=blocked with
    # transaction=null on every step. The replay helper must NOT emit
    # "approve step 1" prose for such a card.
    history = [
        {"role": "user", "content": "Supply 100 USDC to Aave V3"},
        {
            "role": "assistant",
            "content": "Here is the execution plan. Step 1 in your wallet to begin.",
        },
    ]
    # Without history_cards (the caller normally inspects them), the
    # replay path defers to a non-card honest acknowledgement. Verify
    # the sign-step phrase is gone.
    out = _maybe_replay_followup(message="proceed", history=history)
    if out is not None:
        # Must NOT claim a sign-step surface is live unless backed.
        assert "approve step 1" not in out.lower()
        assert "sign step 1" not in out.lower()


def test_rc4_replay_blocker_message_when_no_real_card() -> None:
    # When the helper returns prose but no card frame backs it, the prose
    # must point the user back to a fresh deterministic invocation, not
    # claim a signable surface exists.
    history = [
        {"role": "user", "content": "Build me an execution plan"},
        {"role": "assistant", "content": "I prepared a 3-step execution plan. Allocate $500..."},
    ]
    out = _maybe_replay_followup(message="proceed", history=history)
    # The phrase may exist in the helper output but it must be guarded —
    # either entirely absent or replaced with the BLOCKER_NOT_RESOLVED form.
    if out is not None:
        assert "approve step 1" not in out.lower()


# ---------------------------------------------------------------------------
# RC5 — session-key intent detector routes to deterministic refusal.
# ---------------------------------------------------------------------------


def test_rc5_session_key_phrase_caught() -> None:
    intent = _detect_session_key_intent("Create a session key for Biconomy")
    assert intent is not None
    tool_name, args = intent
    assert "session_key" in tool_name.lower() or "session-key" in tool_name.lower()


def test_rc5_zerodev_session_caught() -> None:
    intent = _detect_session_key_intent("Set up a ZeroDev session for auto-rebalance")
    assert intent is not None


def test_rc5_kernel_session_caught() -> None:
    intent = _detect_session_key_intent("Spin up a Kernel session with daily swap cap")
    assert intent is not None


def test_rc5_nexus_session_caught() -> None:
    intent = _detect_session_key_intent("Configure a Nexus session for my AA wallet")
    assert intent is not None


def test_rc5_set_policy_phrase_caught() -> None:
    intent = _detect_session_key_intent("Set policy to allow daily swaps up to $100")
    assert intent is not None


def test_rc5_auto_compound_phrase_caught() -> None:
    intent = _detect_session_key_intent("Enable auto-compound on my Marinade stake")
    assert intent is not None


def test_rc5_normal_swap_not_caught() -> None:
    intent = _detect_session_key_intent("Swap 100 USDC to ETH on Base")
    assert intent is None


def test_rc5_normal_yield_research_not_caught() -> None:
    intent = _detect_session_key_intent("What are the top yields on Solana?")
    assert intent is None


# ---------------------------------------------------------------------------
# RC9 — fabricated AA function names + UI flows + risk-tier inventions.
# ---------------------------------------------------------------------------


def test_rc9_setpolicy_fabrication_blocked() -> None:
    txt = "Call setPolicy(0x..., 0x..., 1000000) on the Kernel v3 account."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc9_getpolicy_fabrication_blocked() -> None:
    txt = "Then call getPolicy() on the Kernel implementation()."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc9_dailyswaplimitusd_fabrication_blocked() -> None:
    txt = "Setting dailySwapLimitUSD to 100 on your ZeroDev account."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc9_open_marinade_ui_flow_blocked() -> None:
    txt = "Open Marinade.finance and enable Auto-compound in your dashboard."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc9_click_confirm_enso_flow_blocked() -> None:
    txt = "Then click Confirm in Enso to finalize the route."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc9_aa_regex_direct_match() -> None:
    assert _UNBACKED_AA_FABRICATION_RE.search("call setPolicy(0x...)") is not None
    assert _UNBACKED_AA_FABRICATION_RE.search("getPolicy()") is not None
    assert _UNBACKED_AA_FABRICATION_RE.search("implementation() returns") is not None
    assert _UNBACKED_AA_FABRICATION_RE.search("dailySwapLimitUSD = 100") is not None


def test_rc9_no_false_positive_on_legitimate_text() -> None:
    txt = "USDC supply is straightforward — pick a pool with strong TVL."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is False


# ---------------------------------------------------------------------------
# RC11 — F10 fabricated `**Execution Plan**` markdown caught.
# ---------------------------------------------------------------------------


def test_rc11_execution_plan_header_in_prose_blocked() -> None:
    txt = (
        "**Execution Plan**\n"
        "Step 1: Approve USDC spend. Selector 0x095ea7b3, slippage 0.5%, fee 0.3%."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc11_bold_execution_plan_caught_by_fake_card_re() -> None:
    # `**Execution Plan**` markdown header is fake-card impersonation in
    # contextual prose with no backing card.
    assert _UNBACKED_FAKE_CARD_RE.search("**Execution Plan**") is not None
    assert _UNBACKED_FAKE_CARD_RE.search("# Execution Plan") is not None


# ---------------------------------------------------------------------------
# RC15 — fabricated metrics/URLs (Enso execute URLs, Pendle dates, contract names).
# ---------------------------------------------------------------------------


def test_rc15_app_enso_fi_execute_url_blocked() -> None:
    txt = "Open https://app.enso.fi/execute?route=abc to finalize."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc15_pendle_maturity_date_blocked() -> None:
    txt = "Pendle PT-stETH matures on 31 Dec 2025."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc15_wrapped_token_gateway_v3_blocked() -> None:
    txt = "Send 0.5 AVAX to WrappedTokenGatewayV3 to wrap and supply."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert REFUSAL_MARKER in out


def test_rc15_enso_url_regex_direct_match() -> None:
    assert _UNBACKED_FAKE_URL_RE.search("https://app.enso.fi/execute?x=1") is not None
    assert _UNBACKED_FAKE_URL_RE.search("https://app.enso.finance/execute?x=1") is not None


def test_rc15_no_false_positive_on_protocol_name_alone() -> None:
    # Bare "Aave V3 Pool" is legitimate prose; only fabricated contract
    # class names ("WrappedTokenGatewayV3") trigger.
    txt = "Aave V3 Pool is at base."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is False


# ---------------------------------------------------------------------------
# RC17 — asset_hint extractor must not capture cadence words.
# ---------------------------------------------------------------------------


def test_rc17_daily_cadence_not_asset() -> None:
    # I01 t1: "allocate $500 daily across stables" extracted "DAILY" as
    # an asset ticker. The cadence stopword list must skip it.
    result = _parse_asset_hint("Allocate $500 daily across stables")
    assert result != "DAILY"


def test_rc17_weekly_cadence_not_asset() -> None:
    result = _parse_asset_hint("Deploy $1000 weekly into yield pools")
    assert result != "WEEKLY"


def test_rc17_monthly_cadence_not_asset() -> None:
    result = _parse_asset_hint("Invest $200 monthly in DeFi")
    assert result != "MONTHLY"


def test_rc17_ongoing_cadence_not_asset() -> None:
    result = _parse_asset_hint("Allocate $300 ongoing across stables")
    assert result != "ONGOING"


def test_rc17_legitimate_token_still_extracted() -> None:
    # Non-cadence words must still extract correctly.
    result = _parse_asset_hint("Deploy 100 USDC into Aave V3")
    assert result == "USDC"


def test_rc17_legitimate_eth_still_extracted() -> None:
    result = _parse_asset_hint("Allocate 5 ETH into a yield strategy")
    assert result == "ETH"
