import json

import pytest

from src.agent.simple_runtime import detect_intent, run_ephemeral_turn


def test_detect_intent_parses_allocate_chain_and_asset_hint():
    intent = detect_intent(
        "I have $1,000 USDT. Allocate it across the best staking and yield opportunities on solana, risk-weighted using Sentinel scores."
    )

    assert intent == (
        "allocate_plan",
        {
            "usd_amount": 1000.0,
            "risk_budget": "balanced",
            "chains": ["solana"],
            "asset_hint": "USDT",
        },
    )


def test_detect_intent_routes_sentinel_explanation_away_from_allocate_plan():
    intent = detect_intent(
        "How does the Ilyon Sentinel scoring actually work? Explain every criterion."
    )

    assert intent == ("explain_sentinel_methodology", {})


def test_detect_intent_routes_generic_scoring_methodology_to_sentinel():
    intent = detect_intent("explain your scoring methodology")

    assert intent == ("explain_sentinel_methodology", {})


def test_detect_intent_parses_bridge_then_stake_plan():
    intent = detect_intent("bridge 1000 USDC from Ethereum to Arbitrum and stake it on Aave")

    assert intent == (
        "compose_plan",
        {
            "title": "Bridge USDC to Arbitrum and stake on Aave",
            "steps": [
                {
                    "step_id": "step-1",
                    "action": "bridge",
                    "params": {
                        "token_in": "USDC",
                        "amount": "1000000000",
                        "src_chain_id": 1,
                        "dst_chain_id": 42161,
                    },
                },
                {
                    "step_id": "step-2",
                    "action": "stake",
                    "params": {"token": "USDC", "protocol": "aave", "chain_id": 42161},
                    "resolves_from": {"amount": "step-1.received_amount"},
                },
            ],
        },
    )


def test_detect_intent_parses_bridge_comma_then_stake_plan():
    intent = detect_intent("bridge 1,000 USDC from Ethereum to Arbitrum, then stake it on Aave")

    assert intent is not None
    assert intent[0] == "compose_plan"
    assert intent[1]["steps"][0]["params"]["amount"] == "1000000000"
    assert intent[1]["steps"][1]["params"]["chain_id"] == 42161


def test_detect_intent_parses_swap_then_deposit_lp_plan():
    intent = detect_intent("swap 0.5 ETH to USDC then provide liquidity to USDC/USDT on Curve")

    assert intent is not None
    assert intent[0] == "compose_plan"
    assert [step["action"] for step in intent[1]["steps"]] == ["swap", "deposit_lp"]


def test_detect_intent_parses_single_transfer_plan():
    intent = detect_intent("send 100 USDC to vitalik.eth")

    assert intent is not None
    assert intent[0] == "compose_plan"
    assert [step["action"] for step in intent[1]["steps"]] == ["transfer"]


def test_detect_intent_parses_stake_all_idle_eth_resolution_plan():
    intent = detect_intent("stake all my idle ETH")

    assert intent is not None
    assert intent[0] == "compose_plan"
    assert [step["action"] for step in intent[1]["steps"]] == ["get_balance", "stake"]


@pytest.mark.asyncio
async def test_run_ephemeral_turn_emits_execution_plan_card_for_bridge_then_stake():
    chunks = []
    async for chunk in run_ephemeral_turn(
        router=None,
        tools=[],
        message="bridge 1000 USDC from Ethereum to Arbitrum and stake it on Aave",
        wallet="0x1111111111111111111111111111111111111111",
    ):
        chunks.append(chunk.decode())

    wire = "".join(chunks)
    card_events = []
    for part in wire.strip().split("\n\n"):
        if part.startswith("event: card"):
            payload = part.split("data: ", 1)[1]
            card_events.append(json.loads(payload))

    assert card_events
    assert card_events[0]["card_type"] == "execution_plan_v2"
    assert [step["action"] for step in card_events[0]["payload"]["steps"]] == [
        "approve",
        "bridge",
        "wait_receipt",
        "stake",
    ]
