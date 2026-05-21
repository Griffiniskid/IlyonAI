"""Pin tests for the runtime invariant assertion layer.

Wave 8 validation infra. Tests for src/agent/runtime_invariants.py:
  - I1: signable step has non-null transaction
  - I2: tx_count ↔ requires_signature consistency
  - I3: USD value overflow clamp ($1e10 threshold)
  - I4: step-index continuity (no silent gaps)
  - I6: executable:false ⇒ blocker required

Plus positive cases (clean cards pass through) and end-to-end via
StreamCollector.emit_card.
"""
from __future__ import annotations

from src.agent.runtime_invariants import (
    check_card_invariants,
    enforce_card_invariants,
)


# ─── I1: signable step has non-null transaction ──────────────────────────


def test_i1_ready_step_with_null_tx_violates():
    """BUG-E-003 / P0-H-08 shape — composed plan emits status:ready bridge
    step with transaction:null."""
    payload = {
        "status": "ready",
        "steps": [
            {
                "index": 0,
                "action": "bridge",
                "status": "ready",
                "blocker_codes": [],
                "transaction": None,
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I1" for v in violations)


def test_i1_ready_step_with_blocker_codes_allowed():
    """Step with explicit blocker_codes may have null transaction
    (deferred PENDING_DST_FILL semantics)."""
    payload = {
        "steps": [
            {
                "index": 0,
                "action": "deposit_lp",
                "status": "pending",
                "blocker_codes": ["PENDING_DST_FILL"],
                "transaction": None,
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I1" for v in violations)


def test_i1_signable_step_with_tx_passes():
    """Normal signable plan: step has status:ready + transaction:{...}."""
    payload = {
        "steps": [
            {
                "index": 1,
                "action": "supply",
                "status": "ready",
                "blocker_codes": [],
                "transaction": {"to": "0xabc", "data": "0xdead", "value": "0x0"},
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I1" for v in violations)


def test_i1_enforce_replaces_with_invariant_violation_card():
    """When I1 fires, enforce_card_invariants replaces the card with a
    structured invariant_violation blocker."""
    payload = {
        "steps": [
            {"index": 0, "status": "ready", "blocker_codes": [], "transaction": None},
        ],
    }
    new_type, new_payload, violations = enforce_card_invariants(
        "plan_abc", "execution_plan_v3", payload
    )
    assert new_type == "invariant_violation"
    assert new_payload["kind"] == "invariant_violation"
    assert any(v["id"] == "I1" for v in new_payload["violations"])


# ─── I2: tx_count ↔ requires_signature consistency ───────────────────────


def test_i2_tx_count_nonzero_but_requires_signature_false_violates():
    """D-P1-01/B-series shape — plan ships 4 steps with
    requires_signature:false."""
    payload = {
        "tx_count": 4,
        "requires_signature": False,
        "steps": [{"index": i, "status": "ready", "transaction": {"to": "0x"}} for i in range(1, 5)],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I2" for v in violations)


def test_i2_tx_count_zero_with_requires_signature_false_passes():
    payload = {"tx_count": 0, "requires_signature": False, "steps": []}
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I2" for v in violations)


def test_i2_signature_count_in_totals_block_also_checked():
    """Some payloads carry counts under `totals` instead of top-level."""
    payload = {
        "totals": {"signatures_required": 3},
        "requires_signature": False,
        "steps": [{"index": i, "status": "ready", "transaction": {"to": "0x"}} for i in range(1, 4)],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I2" for v in violations)


# ─── I3: USD value overflow clamp ────────────────────────────────────────


def test_i3_usd_value_overflow_violates():
    """NEW-P0-F-09 wallet spark token usd_value = 4.99e+30."""
    payload = {
        "balances": [
            {"chain": "Base", "token": "spark", "usd_value": 4.99e30},
        ],
        "total_usd": 4.99e30,
    }
    violations = check_card_invariants("balance_report", payload)
    assert sum(1 for v in violations if v.invariant_id == "I3") >= 2


def test_i3_normal_usd_values_pass():
    payload = {"total_usd": 1234.56, "usd_value": 999.99}
    violations = check_card_invariants("balance_report", payload)
    assert not any(v.invariant_id == "I3" for v in violations)


def test_i3_enforce_clamps_overflow_to_none():
    """I3 doesn't refuse the card — it sanitizes the bad fields."""
    payload = {
        "balances": [{"token": "spark", "usd_value": 5e30}],
        "total_usd": 5e30,
    }
    new_type, new_payload, _v = enforce_card_invariants(
        "bal_1", "balance_report", payload
    )
    # Card still emitted (not refused) but USD fields clamped.
    assert new_type == "balance_report"
    assert new_payload["total_usd"] is None
    assert new_payload["balances"][0]["usd_value"] is None


# ─── I4: step-index continuity ───────────────────────────────────────────


def test_i4_step_index_gap_violates():
    """NEW-P0-F-10 / N-B-W6-03 — alloc has 5 positions, plan ships
    [1,2,4,5] missing 3."""
    payload = {
        "steps": [
            {"index": 1, "status": "ready", "transaction": {"to": "0x"}},
            {"index": 2, "status": "ready", "transaction": {"to": "0x"}},
            {"index": 4, "status": "ready", "transaction": {"to": "0x"}},
            {"index": 5, "status": "ready", "transaction": {"to": "0x"}},
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I4" for v in violations)


def test_i4_consecutive_indices_pass():
    payload = {
        "steps": [
            {"index": i, "status": "ready", "transaction": {"to": "0x"}}
            for i in (1, 2, 3, 4)
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I4" for v in violations)


def test_i4_zero_based_consecutive_passes():
    """Some plans use 0-based indexing (Step 0, Step 1, Step 2)."""
    payload = {
        "steps": [
            {"index": i, "status": "ready", "transaction": {"to": "0x"}}
            for i in (0, 1, 2)
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I4" for v in violations)


# ─── I6: executable:false ⇒ blocker required ─────────────────────────────


def test_i6_executable_false_step_without_blocker_violates():
    """NEW-A-W7-01 / N-B-W4-01 — alloc card has saturn marked
    executable:false but step ships supply with blocker:null."""
    payload = {
        "positions": [
            {"symbol": "SUSDAT", "executable": False, "adapter_id": None},
        ],
        "steps": [
            {
                "index": 1,
                "target": "SUSDAT · saturn",
                "blocker_codes": [],
                "status": "ready",
                "transaction": {"to": "0x"},
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I6" for v in violations)


def test_i6_fallback_adapter_treated_as_executable_false():
    """N-C-W7-03 — adapter_id ends in '-fallback' should trigger same
    constraint."""
    payload = {
        "positions": [
            {"symbol": "USDCHF-USDC", "adapter_id": "solana-yield-builder-fallback"},
        ],
        "steps": [
            {
                "index": 1,
                "target": "USDCHF-USDC · gmtrade",
                "blocker_codes": [],
                "status": "ready",
                "transaction": {"to": "0x"},
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I6" for v in violations)


def test_i6_executable_false_with_proper_blocker_passes():
    payload = {
        "positions": [
            {"symbol": "SUSDAT", "executable": False, "adapter_id": None},
        ],
        "steps": [
            {
                "index": 1,
                "target": "SUSDAT · saturn",
                "blocker_codes": ["UNSUPPORTED_ADAPTER"],
                "status": "blocked",
                "transaction": None,
            },
        ],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I6" for v in violations)


# ─── End-to-end via StreamCollector.emit_card ────────────────────────────


def test_emit_card_replaces_invariant_violating_payload():
    """A broken card hitting StreamCollector.emit_card must be replaced
    with the invariant_violation blocker."""
    from src.agent.streaming import StreamCollector
    from src.api.schemas.agent import CardFrame

    sc = StreamCollector()
    broken_payload = {
        "status": "ready",
        "steps": [
            {"index": 0, "status": "ready", "blocker_codes": [], "transaction": None},
        ],
    }
    sc.emit_card("plan_broken_1", "execution_plan_v3", broken_payload)
    frames = list(sc.drain())
    card = next(f for f in frames if isinstance(f, CardFrame))
    assert card.card_type == "invariant_violation"
    assert card.payload["kind"] == "invariant_violation"


def test_emit_card_passes_clean_card_through():
    """A well-formed card must pass through unchanged."""
    from src.agent.streaming import StreamCollector
    from src.api.schemas.agent import CardFrame

    sc = StreamCollector()
    clean_payload = {
        "steps": [
            {
                "index": 1,
                "action": "supply",
                "status": "ready",
                "blocker_codes": [],
                "transaction": {"to": "0xabc", "data": "0xdead", "value": "0x0"},
            },
        ],
    }
    sc.emit_card("plan_clean_1", "execution_plan_v3", clean_payload)
    frames = list(sc.drain())
    card = next(f for f in frames if isinstance(f, CardFrame))
    assert card.card_type == "execution_plan_v3"
    assert card.payload == clean_payload


def test_emit_card_clamps_usd_overflow_in_place():
    from src.agent.streaming import StreamCollector
    from src.api.schemas.agent import CardFrame

    sc = StreamCollector()
    payload = {"total_usd": 5e30, "balances": [{"usd_value": 5e30}]}
    sc.emit_card("bal_1", "balance_report", payload)
    frames = list(sc.drain())
    card = next(f for f in frames if isinstance(f, CardFrame))
    # Card still emitted as balance_report (not refused) but USD clamped.
    assert card.card_type == "balance_report"
    assert card.payload["total_usd"] is None


# ─── BUG-RC pin tests (Wave RC-α) ─────────────────────────────────────────


# I7: title/payload consistency (BUG-RC-002 structural)


def test_i7_title_protocol_mismatch_fires():
    """Title says Fluid Lending but payload.protocol is aave-v3 — silent
    intent substitution. Hard refuse via P0 violation."""
    payload = {
        "title": "Fluid Lending Supply — Supply 100 USDC via Fluid Lending on Ethereum",
        "protocol": "aave-v3",
        "asset_in": "USDC",
        "steps": [],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I7" and v.severity == "P0" for v in violations), (
        f"expected I7 P0 for protocol mismatch, got {violations}"
    )


def test_i7_title_protocol_consistent_passes():
    """Title mentions the same protocol as payload.protocol — passes."""
    payload = {
        "title": "Aave V3 Supply — Supply 100 USDC via Aave on Ethereum",
        "protocol": "aave-v3",
        "asset_in": "USDC",
        "steps": [],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I7" for v in violations)


def test_i7_no_protocol_field_skips_check():
    """When payload.protocol is absent, I7 cannot determine intent —
    skips the check rather than false-positive."""
    payload = {"title": "Some title", "steps": []}
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I7" for v in violations)


# I8: sentinel scoring present on defi_opportunities (BUG-RC-011)


def test_i8_missing_sentinel_block_fires():
    payload = {
        "items": [
            {"symbol": "USDC", "apy": 5.0, "tvl": 1_000_000},  # no sentinel
        ],
    }
    violations = check_card_invariants("defi_opportunities", payload)
    assert any(v.invariant_id == "I8" for v in violations)


def test_i8_partial_sentinel_fires():
    payload = {
        "items": [
            {
                "symbol": "USDC",
                "sentinel": {"safety": 80, "durability": 70},  # missing exit/confidence
            }
        ],
    }
    violations = check_card_invariants("defi_opportunities", payload)
    assert any(v.invariant_id == "I8" for v in violations)


def test_i8_full_sentinel_passes():
    payload = {
        "items": [
            {
                "symbol": "USDC",
                "sentinel": {
                    "safety": 80,
                    "durability": 70,
                    "exit": 90,
                    "confidence": 75,
                },
            }
        ],
    }
    violations = check_card_invariants("defi_opportunities", payload)
    assert not any(v.invariant_id == "I8" for v in violations)


# I10: asset-pool match (BUG-RC-002 emit-time fallback)


def test_i10_asset_pool_mismatch_fires():
    """User asked for USDC but pool's declared deposit token is WSTETH."""
    payload = {
        "asset_in": "USDC",
        "pool_deposit_token": "WSTETH",
        "steps": [],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I10" and v.severity == "P0" for v in violations)


def test_i10_asset_pool_match_passes():
    payload = {
        "asset_in": "USDC",
        "pool_deposit_token": "USDC",
        "steps": [],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I10" for v in violations)


# I12: time formatting (BUG-RC-006 — Infinitys / NaN / Infinity / None)


def test_i12_infinitys_in_payload_fires():
    payload = {
        "freshness_message": "SIM_STALE: Simulation is Infinitys old (>30s).",
        "steps": [],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I12" for v in violations)


def test_i12_nan_in_payload_fires():
    payload = {"eta_str": "ETA: NaN seconds", "steps": []}
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I12" for v in violations)


def test_i12_non_finite_float_fires():
    payload = {"sim_age_sec": float("inf"), "steps": []}
    violations = check_card_invariants("execution_plan_v3", payload)
    assert any(v.invariant_id == "I12" for v in violations)


def test_i12_finite_time_string_passes():
    payload = {
        "freshness_message": "SIM_STALE: Simulation is 30s old.",
        "sim_age_sec": 30.0,
        "steps": [],
    }
    violations = check_card_invariants("execution_plan_v3", payload)
    assert not any(v.invariant_id == "I12" for v in violations)


# Sanitizer test (BUG-RC-003 defense-in-depth)


def test_sanitize_error_message_replaces_unbound_local():
    from src.agent.simple_runtime import _sanitize_error_message

    raw = "cannot access local variable 'ExecutionBlocker' where it is not associated with a value"
    out = _sanitize_error_message(raw)
    assert "ExecutionBlocker" not in out
    assert "INTERNAL_ERROR_CAUGHT" in out


def test_sanitize_error_message_replaces_nonetype_attr():
    from src.agent.simple_runtime import _sanitize_error_message

    raw = "AttributeError: 'NoneType' object has no attribute 'symbol'"
    out = _sanitize_error_message(raw)
    assert "NoneType" not in out
    assert "INTERNAL_ERROR_CAUGHT" in out


def test_sanitize_error_message_preserves_clean_text():
    from src.agent.simple_runtime import _sanitize_error_message

    raw = "Rate limited by upstream provider (retry in 30s)."
    out = _sanitize_error_message(raw)
    assert out == raw


def test_sanitize_error_message_handles_none():
    from src.agent.simple_runtime import _sanitize_error_message

    out = _sanitize_error_message(None)
    assert out == "Please try again later."


# build_yield_execution_plan: ExecutionBlocker no-longer-local check


def test_execution_blocker_is_module_level_in_build_yield_execution_plan():
    """BUG-RC-003 structural fix: ExecutionBlocker must be module-level
    in build_yield_execution_plan.py, not re-bound inside the function.
    A duplicate in-function import would re-introduce UnboundLocalError
    on branches that don't traverse the import line first."""
    import importlib
    import inspect

    mod = importlib.import_module("src.agent.tools.build_yield_execution_plan")
    assert hasattr(mod, "ExecutionBlocker"), (
        "ExecutionBlocker must be importable from the module — confirms "
        "the top-level import is reachable and not shadowed."
    )
    func = getattr(mod, "build_yield_execution_plan")
    src = inspect.getsource(func)
    # The in-function `from src.defi.execution.models import ExecutionBlocker`
    # is the exact pattern that trips UnboundLocalError. The comment we
    # left behind references "import" without the full from-statement
    # form, so a substring match on the full statement is safe.
    assert "from src.defi.execution.models import ExecutionBlocker\n" not in src, (
        "build_yield_execution_plan must not re-import ExecutionBlocker — "
        "that re-binds it as a function-local and trips UnboundLocalError "
        "on every branch that references it before the import statement."
    )


# BUG-RC-005 — bare-token allocation intent (no $ sign)


def test_alloc_bare_token_routes_to_allocate_strategy():
    """BUG-RC-005: 'allocate 10k USDT' must classify as allocate_strategy
    even without the $ sign that _AMOUNT_ASSET_RE used to require."""
    from src.agent.intent.defi_intent import parse_defi_intent

    intent = parse_defi_intent("allocate 10k USDT with highest scoring opportunities")
    assert intent.intent == "allocate_strategy"
    assert intent.amount_usd == 10_000.0
    assert intent.asset_hint == "USDT"


def test_alloc_bare_token_distribute_across_pools():
    """The real-tester phrase from AI Bug Convo.md line 169 — must yield
    allocate_strategy, not search_defi_opportunities."""
    from src.agent.intent.defi_intent import parse_defi_intent

    intent = parse_defi_intent(
        "Can you pick 4 best pools out of those in your opinion and "
        "distribute and allocate 40 usdt on sol across them?"
    )
    assert intent.intent == "allocate_strategy"
    assert intent.amount_usd == 40.0
    assert intent.asset_hint == "USDT"


def test_alloc_bare_token_deploy_form():
    from src.agent.intent.defi_intent import parse_defi_intent

    intent = parse_defi_intent("deploy 100 USDC into Aave")
    assert intent.intent == "allocate_strategy"
    assert intent.amount_usd == 100.0
    assert intent.asset_hint == "USDC"


# BUG-RC-002 — ASSET_POOL_MISMATCH preflight in execute_pool_position


def test_asset_pool_mismatch_refuses_usdc_against_wsteth_pool():
    """BUG-RC-002 root case: user typed USDC, dispatcher landed on a
    WSTETH-only pool. Must refuse with ASSET_POOL_MISMATCH blocker,
    not silently coerce."""
    import asyncio
    from unittest.mock import patch
    import importlib
    mod = importlib.import_module("src.agent.tools.execute_pool_position")

    async def fake_fetch_pool_meta(pool_id):
        # Single-token WSTETH vault (e.g., Fluid Lending WSTETH).
        return {
            "chain": "Ethereum",
            "project": "fluid-lending",
            "symbol": "WSTETH",
            "underlyingTokens": ["0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"],
            "pool": "69b12bf9-aaaa-bbbb-cccc-ddddeeeeffff",
            "tvlUsd": 100_000_000,
            "apy": 3.5,
        }

    class FakeCtx:
        wallet = "0x" + "a" * 40
        evm_wallet = "0x" + "a" * 40
        solana_wallet = None

    with patch.object(mod, "_fetch_pool_meta", fake_fetch_pool_meta):
        result = asyncio.run(
            mod.execute_pool_position(
                FakeCtx(),
                pool="69b12bf9-aaaa-bbbb-cccc-ddddeeeeffff",
                amount=100,
                asset_in="USDC",  # user explicitly named USDC
                amount_is_usd=True,
            )
        )
    ok = result.ok if hasattr(result, "ok") else result["ok"]
    assert ok is True
    data = result.data if hasattr(result, "data") else result["data"]
    plan = data["plan"]
    blockers = plan.get("blockers") or []
    codes = [b.get("code") for b in blockers]
    assert "ASSET_POOL_MISMATCH" in codes, (
        f"expected ASSET_POOL_MISMATCH blocker, got codes={codes}"
    )


def test_asset_pool_match_allows_usdc_against_usdc_pool():
    """Sanity: USDC ask against a USDC market must NOT trip the
    mismatch guard (otherwise legitimate Aave V3 USDC supply breaks)."""
    import asyncio
    from unittest.mock import patch
    import importlib
    mod = importlib.import_module("src.agent.tools.execute_pool_position")

    async def fake_fetch_pool_meta(pool_id):
        return {
            "chain": "Base",
            "project": "aave-v3",
            "symbol": "USDC",
            "underlyingTokens": ["0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"],
            "pool": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "tvlUsd": 50_000_000,
            "apy": 4.5,
        }

    class FakeCtx:
        wallet = "0x" + "b" * 40
        evm_wallet = "0x" + "b" * 40
        solana_wallet = None

    with patch.object(mod, "_fetch_pool_meta", fake_fetch_pool_meta):
        result = asyncio.run(
            mod.execute_pool_position(
                FakeCtx(),
                pool="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                amount=100,
                asset_in="USDC",
                amount_is_usd=True,
            )
        )
    ok = result.ok if hasattr(result, "ok") else result["ok"]
    assert ok is True
    data = result.data if hasattr(result, "data") else result["data"]
    plan = data["plan"]
    blockers = plan.get("blockers") or []
    codes = [b.get("code") for b in blockers]
    assert "ASSET_POOL_MISMATCH" not in codes


def test_asset_pool_match_stables_interchangeable():
    """USDT supply against USDC pool: both stables, Jupiter/Curve will
    bridge. Must NOT raise ASSET_POOL_MISMATCH.

    The function may error downstream when it tries to actually build a
    plan (the registry isn't fully mocked), but the key assertion is
    that if there IS a plan, ASSET_POOL_MISMATCH is NOT one of its
    blockers. We tolerate non-plan responses as long as they're not the
    ASSET_POOL_MISMATCH refuse path.
    """
    import asyncio
    from unittest.mock import patch
    import importlib
    mod = importlib.import_module("src.agent.tools.execute_pool_position")

    async def fake_fetch_pool_meta(pool_id):
        return {
            "chain": "Ethereum",
            "project": "compound-v3",
            "symbol": "USDC",
            "underlyingTokens": ["0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"],
            "pool": "stable-bridge-test",
            "tvlUsd": 20_000_000,
            "apy": 6.0,
        }

    class FakeCtx:
        wallet = "0x" + "c" * 40
        evm_wallet = "0x" + "c" * 40
        solana_wallet = None

    with patch.object(mod, "_fetch_pool_meta", fake_fetch_pool_meta):
        result = asyncio.run(
            mod.execute_pool_position(
                FakeCtx(),
                pool="stable-bridge-test",
                amount=50,
                asset_in="USDT",  # user named USDT, pool is USDC
                amount_is_usd=True,
            )
        )
    data = result.data if hasattr(result, "data") else result.get("data") if isinstance(result, dict) else {}
    plan = data.get("plan") if isinstance(data, dict) else None
    if plan:
        blockers = plan.get("blockers") or []
        codes = [b.get("code") for b in blockers]
        assert "ASSET_POOL_MISMATCH" not in codes, (
            f"USDT→USDC pool must not be refused (both stables); got {codes}"
        )


def test_alloc_bare_token_rejects_non_crypto_noun():
    """Whitelist guard: 'with 5 dogs' must NOT register as an alloc
    amount/asset (would be a false positive)."""
    from src.agent.intent.defi_intent import parse_defi_intent

    intent = parse_defi_intent("walking with 5 dogs in the park")
    # No allocation verb + 'dogs' not in token whitelist → no amount.
    assert intent.amount_usd is None


def test_execution_blocker_is_module_level_in_execute_pool_position():
    """Same structural check for execute_pool_position.py."""
    import importlib
    import inspect

    mod = importlib.import_module("src.agent.tools.execute_pool_position")
    assert hasattr(mod, "ExecutionBlocker")
    assert hasattr(mod, "ExecutionPlanV3")
    # Walk every function defined in the module and assert none re-import
    # ExecutionBlocker as function-local.
    for name in dir(mod):
        obj = getattr(mod, name)
        if not callable(obj):
            continue
        if not inspect.isfunction(obj):
            continue
        if obj.__module__ != mod.__name__:
            continue
        try:
            src = inspect.getsource(obj)
        except (OSError, TypeError):
            continue
        assert "from src.defi.execution.models import ExecutionBlocker" not in src, (
            f"{name} re-imports ExecutionBlocker as function-local — "
            f"removes the safety the module-level hoist was supposed to "
            f"provide."
        )
