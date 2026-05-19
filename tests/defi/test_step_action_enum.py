"""Pin test for spec §12 StepAction enum coverage.

Spec quote (IlyonAi_LP_Execution_Spec.pdf v1.0, plan schema, page ~36):

    steps: [ // ordered, dependency-aware {
      step_id: int, kind: enum(APPROVE, PERMIT2_SIG, SWAP, BRIDGE, WRAP_NATIVE,
        UNWRAP_NATIVE, ATA_CREATE, TICK_ARRAY_INIT, BIN_ARRAY_INIT,
        MINT_POSITION, INCREASE_LIQUIDITY, DEPOSIT, STAKE, COMPOUND, MULTICALL),
      ...
    }

This test pins the canonical 15-verb vocabulary against the
`StepAction` Literal in `src/defi/execution/models.py`. If the spec
adds/removes a verb, this test must fail loudly so the enum is
re-synced.

NOTE: 6 of the 15 spec verbs (APPROVE, SWAP, BRIDGE, DEPOSIT, STAKE,
COMPOUND) are already represented by the legacy lowercase form
(approve / swap / bridge / deposit_lp+supply / stake / compound_rewards).
The pin accepts either spelling — but the 9 verbs introduced by this
patch (PERMIT2_SIG, WRAP_NATIVE, UNWRAP_NATIVE, ATA_CREATE,
TICK_ARRAY_INIT, BIN_ARRAY_INIT, MINT_POSITION, INCREASE_LIQUIDITY,
MULTICALL) must be present in UPPER_SNAKE form because no legacy
lowercase emitter exists yet.
"""
from __future__ import annotations

import typing

from src.defi.execution import models


# --- Spec §12 ground truth (verbatim from PDF) -----------------------------
SPEC_KINDS = frozenset({
    "APPROVE", "PERMIT2_SIG", "SWAP", "BRIDGE", "WRAP_NATIVE", "UNWRAP_NATIVE",
    "ATA_CREATE", "TICK_ARRAY_INIT", "BIN_ARRAY_INIT", "MINT_POSITION",
    "INCREASE_LIQUIDITY", "DEPOSIT", "STAKE", "COMPOUND", "MULTICALL",
})

# Legacy lowercase aliases for the 6 verbs the codebase already wires.
# When the Literal contains either spelling, the spec verb counts as covered.
LEGACY_ALIASES = {
    "APPROVE": {"approve"},
    "SWAP": {"swap"},
    "BRIDGE": {"bridge"},
    "DEPOSIT": {"deposit_lp", "supply"},
    "STAKE": {"stake"},
    "COMPOUND": {"compound_rewards"},
}


def _literal_values() -> frozenset[str]:
    """Extract the string values out of the StepAction Literal."""
    args = typing.get_args(models.StepAction)
    return frozenset(args)


# --- Tests -----------------------------------------------------------------
def test_spec_step_kinds_constant_matches_spec_quote():
    """`SPEC_STEP_KINDS` in models.py must equal the verbatim §12 enum."""
    assert models.SPEC_STEP_KINDS == SPEC_KINDS


def test_all_15_spec_verbs_present_in_step_action_literal():
    """Every spec §12 verb must be reachable via the StepAction Literal,
    either as UPPER_SNAKE (canonical) or via a legacy lowercase alias."""
    lit = _literal_values()
    missing: list[str] = []
    for verb in SPEC_KINDS:
        aliases = LEGACY_ALIASES.get(verb, set())
        if verb in lit:
            continue
        if aliases & lit:
            continue
        missing.append(verb)
    assert not missing, (
        f"Spec §12 verbs missing from StepAction Literal: {sorted(missing)}. "
        f"Literal values: {sorted(lit)}"
    )


def test_new_upper_snake_verbs_present():
    """The 9 verbs introduced to close the §12 gap must be present in
    UPPER_SNAKE form (no legacy lowercase emitter exists for these yet)."""
    lit = _literal_values()
    required = {
        "PERMIT2_SIG", "WRAP_NATIVE", "UNWRAP_NATIVE", "ATA_CREATE",
        "TICK_ARRAY_INIT", "BIN_ARRAY_INIT", "MINT_POSITION",
        "INCREASE_LIQUIDITY", "MULTICALL",
    }
    missing = required - lit
    assert not missing, f"New §12 verbs missing from Literal: {sorted(missing)}"


def test_legacy_12_verbs_unchanged_backwards_compat():
    """Backwards-compat pin: the original 12 lowercase verbs must remain
    in the StepAction Literal so existing adapters/preflight checks
    continue to type-check."""
    lit = _literal_values()
    legacy = {
        "approve", "swap", "bridge", "deposit_lp", "supply", "stake",
        "wait_receipt", "verify_balance", "claim_rewards",
        "compound_rewards", "withdraw", "revoke_session_key",
    }
    missing = legacy - lit
    assert not missing, (
        f"Backwards-compat regression: legacy verbs dropped from "
        f"StepAction Literal: {sorted(missing)}"
    )


def test_public_constants_match_literal():
    """The module-level UPPER_SNAKE constants must equal the string
    values they alias inside the Literal."""
    pairs = [
        (models.PERMIT2_SIG, "PERMIT2_SIG"),
        (models.WRAP_NATIVE, "WRAP_NATIVE"),
        (models.UNWRAP_NATIVE, "UNWRAP_NATIVE"),
        (models.ATA_CREATE, "ATA_CREATE"),
        (models.TICK_ARRAY_INIT, "TICK_ARRAY_INIT"),
        (models.BIN_ARRAY_INIT, "BIN_ARRAY_INIT"),
        (models.MINT_POSITION, "MINT_POSITION"),
        (models.INCREASE_LIQUIDITY, "INCREASE_LIQUIDITY"),
        (models.MULTICALL, "MULTICALL"),
        (models.REVOKE_SESSION_KEY, "revoke_session_key"),
    ]
    lit = _literal_values()
    for const_value, expected in pairs:
        assert const_value == expected, (
            f"Constant value drift: got {const_value!r}, want {expected!r}"
        )
        assert const_value in lit, (
            f"Constant {expected!r} not present in StepAction Literal"
        )
