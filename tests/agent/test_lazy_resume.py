"""Lazy-resume + execute-named-proto regression pins.

v4-A01/A06/A09 caught vague final-confirm verbs falling through to
search_defi_opportunities instead of rebuilding from prior plan card.
"""
from __future__ import annotations


def test_lazy_resume_picks_last_execution_plan():
    from src.agent.simple_runtime import _detect_lazy_resume_from_history

    history = [
        {
            "card_type": "execution_plan_v3",
            "payload": {
                "chain": "optimism",
                "steps": [
                    {"action": "approve", "chain": "optimism", "protocol": "aave-v3",
                     "asset_in": "USDC", "amount_in": "250"},
                    {"action": "supply", "chain": "optimism", "protocol": "aave-v3",
                     "asset_in": "USDC", "amount_in": "250"},
                ],
            },
        }
    ]
    for msg in ["Execute", "Execute it", "Confirm", "Do that", "Sign now",
                "Execute the deposit", "Proceed", "Run it"]:
        out = _detect_lazy_resume_from_history(msg, history)
        assert out is not None, f"{msg!r} should resume"
        _, args = out
        assert args["chain"] == "optimism"
        assert args["protocol"] == "aave-v3"
        assert args["asset_in"] == "USDC"
        assert args["amount_in"] == "250"
        assert args["action"] == "supply"


def test_lazy_resume_picks_pool_link_when_no_execution_plan():
    from src.agent.simple_runtime import _detect_lazy_resume_from_history

    history = [
        {
            "card_type": "pool_link",
            "payload": {
                "chain": "ethereum", "protocol": "lido",
                "asset_in": "ETH", "amount": "0.05",
            },
        }
    ]
    out = _detect_lazy_resume_from_history("Execute", history)
    assert out is not None
    _, args = out
    assert args["protocol"] == "lido"
    assert args["action"] == "stake"


def test_lazy_resume_refuses_random_text():
    from src.agent.simple_runtime import _detect_lazy_resume_from_history

    history = [
        {"card_type": "execution_plan_v3", "payload": {"chain": "base",
         "steps": [{"action": "supply", "chain": "base", "protocol": "aave-v3",
                    "asset_in": "USDC", "amount_in": "100"}]}}
    ]
    assert _detect_lazy_resume_from_history("Tell me about Uniswap", history) is None
    assert _detect_lazy_resume_from_history("What's TVL?", history) is None


def test_execute_named_proto_aliases():
    from src.agent.simple_runtime import _detect_execute_named_proto

    cases = [
        ("Execute on Aave V3 with 250 USDC", "aave-v3", "supply", "USDC", "250"),
        ("Sign Lido 0.05 ETH", "lido", "stake", "ETH", "0.05"),
        ("Execute Compound V3 supply 100 USDC on Optimism", "compound-v3", "supply", "USDC", "100"),
        ("Run Renzo 0.05 ETH", "renzo", "stake", "ETH", "0.05"),
    ]
    for msg, proto, action, asset, amt in cases:
        out = _detect_execute_named_proto(msg)
        assert out is not None, f"{msg!r} should detect"
        _, args = out
        assert args["protocol"] == proto, (msg, args)
        assert args["action"] == action, (msg, args)
        assert args["asset_in"] == asset, (msg, args)
        assert args["amount_in"] == amt, (msg, args)


def test_execute_named_proto_refuses_vague():
    from src.agent.simple_runtime import _detect_execute_named_proto

    assert _detect_execute_named_proto("Execute the deposit") is None
    assert _detect_execute_named_proto("Just confirm") is None


def test_lifecycle_detector_bare_chain_suffix():
    """v4-D02 caught 'Withdraw all USDC from Aave V3 Base' chain=ethereum."""
    from src.agent.simple_runtime import detect_intent

    out = detect_intent("Withdraw all USDC from Aave V3 Base")
    assert out is not None
    _, args = out
    assert args.get("chain") == "base"
    assert args.get("protocol") == "aave-v3"
    assert args.get("asset_in") == "USDC"


def test_lifecycle_detector_bare_chain_aliases():
    from src.agent.simple_runtime import detect_intent

    cases = [
        ("Withdraw all USDC from Aave V3 BNB", "bsc"),
        ("Withdraw all USDC from Aave V3 Avax", "avalanche"),
    ]
    for msg, expected_chain in cases:
        out = detect_intent(msg)
        assert out is not None
        _, args = out
        assert args.get("chain") == expected_chain, (msg, args)


def test_lazy_resume_matches_bridge_variants():
    from src.agent.simple_runtime import _detect_lazy_resume_from_history

    hc = [
        {
            "card_type": "execution_plan_v3",
            "payload": {
                "chain": "ethereum",
                "steps": [
                    {"action": "bridge", "chain": "ethereum", "protocol": "debridge-dln",
                     "asset_in": "USDC", "amount_in": "100"},
                    {"action": "supply", "chain": "base", "protocol": "aave-v3",
                     "asset_in": "USDC", "amount_in": "100"},
                ],
            },
        }
    ]
    for msg in ["Confirm", "Execute the bridge step now", "Confirm bridge",
                "Execute destination step", "Execute step 2"]:
        out = _detect_lazy_resume_from_history(msg, hc)
        assert out is not None, f"{msg!r} should resume"


def test_lazy_resume_matches_withdraw_suffix():
    from src.agent.simple_runtime import _LAZY_RESUME_RE

    for msg in ["Confirm withdraw", "Confirm withdrawal", "Execute withdraw",
                "Confirm exit", "Confirm redeem", "Confirm repay", "Execute claim"]:
        assert _LAZY_RESUME_RE.search(msg), f"{msg!r} should match"


def test_lazy_resume_action_aware_picks_withdraw_over_supply():
    """When user says 'Confirm withdraw' with mixed history, pick withdraw."""
    from src.agent.simple_runtime import _detect_lazy_resume_from_history

    hc = [
        {"card_type": "execution_plan_v3", "payload": {"chain": "base",
         "steps": [{"action": "supply", "chain": "base", "protocol": "aave-v3",
                    "asset_in": "USDC", "amount_in": "100"}]}},
        {"card_type": "execution_plan_v3", "payload": {"chain": "base",
         "steps": [{"action": "withdraw", "chain": "base", "protocol": "aave-v3",
                    "asset_in": "USDC", "amount_in": "100"}]}},
    ]
    out = _detect_lazy_resume_from_history("Confirm withdraw", hc)
    assert out is not None
    assert out[1]["action"] == "withdraw"


def test_lazy_resume_action_aware_picks_supply_when_named():
    from src.agent.simple_runtime import _detect_lazy_resume_from_history

    hc = [
        {"card_type": "execution_plan_v3", "payload": {"chain": "base",
         "steps": [{"action": "supply", "chain": "base", "protocol": "aave-v3",
                    "asset_in": "USDC", "amount_in": "100"}]}},
        {"card_type": "execution_plan_v3", "payload": {"chain": "base",
         "steps": [{"action": "withdraw", "chain": "base", "protocol": "aave-v3",
                    "asset_in": "USDC", "amount_in": "100"}]}},
    ]
    out = _detect_lazy_resume_from_history("Confirm supply", hc)
    assert out is not None
    assert out[1]["action"] == "supply"


def test_lazy_resume_returns_none_when_no_matching_action_in_history():
    """'Confirm bridge' with no bridge plan in history → None (fall through)."""
    from src.agent.simple_runtime import _detect_lazy_resume_from_history

    hc = [
        {"card_type": "execution_plan_v3", "payload": {"chain": "base",
         "steps": [{"action": "supply", "chain": "base", "protocol": "aave-v3",
                    "asset_in": "USDC", "amount_in": "100"}]}},
    ]
    out = _detect_lazy_resume_from_history("Confirm bridge", hc)
    assert out is None


def test_extract_action_hint_returns_canonical_action():
    from src.agent.simple_runtime import _extract_action_hint

    assert _extract_action_hint("Confirm withdraw") == "withdraw"
    assert _extract_action_hint("Execute withdrawal") == "withdraw"
    assert _extract_action_hint("Confirm exit") == "exit_pool"
    assert _extract_action_hint("Execute remove") == "remove_liquidity"
    assert _extract_action_hint("Confirm bridge") == "bridge"
    assert _extract_action_hint("Confirm supply") == "supply"
    assert _extract_action_hint("Confirm") is None
