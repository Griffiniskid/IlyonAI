"""Matrix Pass A wave 9 — chokepoint additions for E10 "Once confirmed"
and related sub-paraphrase shapes.

Wave-8 mechanical sweep + regression sweep proved the validation infra
works. Wave-9 closes the residual P0 paraphrases that escaped the
wave-7/8 sanitizer:
  - E10 "submit the 'Increase liquidity' transaction" — narrow verb
    set in wave-7 only covered stake/supply/deposit/swap/bridge/approve/
    withdraw, missing increase_liquidity/decrease_liquidity/add/remove
    LP variants.
  - E10 "Once confirmed, your LP-NFT will reflect" — wave-7 regex
    required "Once confirmed, X TOKEN will be supplied/staked/...";
    needs broader "will reflect/appear/show/update" verbs.
  - E10 "double-check the pool address before signing" — imperative
    sign-narration without backing card.
  - E10 "Approve 50 ARB and ≈0.0306 ETH in Enso" — two-token approval
    narration with U+202F narrow no-break space.
"""
from __future__ import annotations

from src.agent.simple_runtime import (
    _FREEFORM_HALLUCINATION_REFUSAL,
    _strip_freeform_tx_state_hallucinations,
)


def test_e10_submit_increase_liquidity_refused():
    """E10 wave-8: 'submit the Increase liquidity transaction'."""
    leak = (
        "Approve 50 ARB and 0.0306 ETH in Enso, then submit the "
        "'Increase liquidity' transaction for the Uniswap V3 ARB/ETH "
        "0.3% pool on Arbitrum."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e10_once_confirmed_will_reflect_refused():
    """E10 wave-8: 'Once confirmed, your LP-NFT will reflect'."""
    leak = (
        "Sign step 2 in your wallet. Once confirmed, your LP-NFT will "
        "reflect the added liquidity."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e10_once_confirmed_will_appear_refused():
    leak = "Once confirmed, the position will appear in your portfolio."
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e10_double_check_before_signing_refused():
    leak = "Keep slippage around 0.5% and double-check the pool address before signing."
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_e10_two_token_approve_in_enso_refused():
    """'Approve 50 ARB and ≈0.0306 ETH in Enso' two-token narration."""
    leak = "Approve 50 ARB and ≈0.0306 ETH in Enso to proceed."
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_full_e10_leak_refused():
    """The exact wave-8 enso-02 t2 leak end-to-end."""
    nbsp = " "
    leak = (
        f"Approve{nbsp}50{nbsp}ARB and{nbsp}≈0.0306{nbsp}ETH in Enso, then "
        f"submit the 'Increase liquidity' transaction for the Uniswap{nbsp}V3 "
        f"ARB/ETH{nbsp}0.3% pool on Arbitrum. Keep slippage around{nbsp}0.5% "
        f"and double-check the pool address before signing. Once confirmed, "
        f"your LP-NFT will reflect the added liquidity."
    )
    out = _strip_freeform_tx_state_hallucinations(leak, card_ids=[])
    assert out == _FREEFORM_HALLUCINATION_REFUSAL


def test_benign_once_confirmed_passes():
    """Educational mention of confirmation flow without verb-action."""
    benign = (
        "Most EVM transactions take 12-30 seconds to confirm on Ethereum. "
        "You can monitor confirmation status in your wallet."
    )
    out = _strip_freeform_tx_state_hallucinations(benign, card_ids=[])
    assert out == benign
