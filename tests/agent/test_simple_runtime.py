import json

import pytest

from src.api.schemas.agent import ExtraCard, ToolEnvelope
from src.agent.simple_runtime import detect_intent, run_ephemeral_turn


class _FakeTool:
    def __init__(self, name, result):
        self.name = name
        self._result = result

    async def ainvoke(self, _tool_input):
        return self._result


class _FakeRouter:
    async def complete(self, **_kwargs):
        return {
            "content": (
                "We need to answer: user has 200 USDT and asks for 6 months with reinvestment. "
                "Need to calculate compounding. Let's compute: APY=12.7%, half year return = "
                "sqrt(1.127)-1.\n\n"
                "With **12.7% APY**, reinvesting for 6 months turns **$200** into about "
                "**$212.36**, so estimated profit is **$12.36** before any extra wallet gas or protocol changes."
            ),
            "tool_calls": [],
        }


def _events_from_wire(wire: str) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    for part in wire.strip().split("\n\n"):
        if not part.startswith("event:"):
            continue
        event = part.split("\n", 1)[0].replace("event:", "").strip()
        payload = part.split("data: ", 1)[1]
        events.setdefault(event, []).append(json.loads(payload))
    return events


@pytest.mark.asyncio
async def test_run_ephemeral_turn_strips_llm_reasoning_leak_from_final_answer():
    chunks = []
    async for chunk in run_ephemeral_turn(
        router=_FakeRouter(),
        tools=[],
        message="How much will I earn from $200 if I reinvest for 6 months?",
        wallet="0x1111111111111111111111111111111111111111",
    ):
        chunks.append(chunk.decode())

    events = _events_from_wire("".join(chunks))
    final = events["final"][0]["content"]

    assert "We need to answer" not in final
    assert "Need to calculate" not in final
    assert "Let's compute" not in final
    assert "**$12.36**" in final


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


def test_detect_intent_routes_high_apy_pool_search_to_opportunity_search():
    intent = detect_intent("show me medium and high risk pools that give me around 100% APY")

    assert intent is not None
    tool_name, params = intent
    assert tool_name == "search_defi_opportunities"
    assert params["risk_levels"] == ["MEDIUM", "HIGH"]
    assert params["target_apy"] == 100.0
    assert params["min_apy"] >= 60.0
    assert params["max_apy"] <= 180.0
    assert params["ranking_objective"] == "constraint_fit_then_risk_adjusted_return"


def test_detect_intent_keeps_highest_scoring_capital_request_as_allocation():
    intent = detect_intent("allocate 10k USDT with highest scoring opportunities")

    assert intent == (
        "allocate_plan",
        {
            "usd_amount": 10_000.0,
            "risk_budget": "balanced",
            "asset_hint": "USDT",
        },
    )


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


@pytest.mark.asyncio
async def test_run_ephemeral_turn_emits_demo_depth_reasoning_for_allocation():
    allocation_payload = {
        "total_usd": "$10,000",
        "blended_apy": "~5.6%",
        "chains": 3,
        "weighted_sentinel": 89,
        "risk_mix": {"low": 4, "medium": 1, "high": 0},
        "combined_tvl": "$31.2B",
        "positions": [
            {"rank": 1, "protocol": "Lido", "asset": "stETH", "chain": "eth", "apy": "3.1%", "sentinel": 94, "risk": "low", "fit": "conservative", "weight": 35, "usd": "$3,500", "tvl": "$24.5B", "router": "Enso", "safety": 96, "durability": 92, "exit": 98, "confidence": 95, "flags": []},
        ],
    }
    env = ToolEnvelope(
        ok=True,
        card_id="allocation-1",
        card_type="allocation",
        card_payload=allocation_payload,
        data={
            **allocation_payload,
            "analysis_trace": [
                "Queried DefiLlama yield pools and normalized candidates across supported chains.",
                "Filtered TVL >= $200M and removed pools without enough operating history.",
                "Scored candidates via Sentinel pool framework: Safety x Yield durability x Exit x Confidence.",
                "Cross-checked each protocol against Ilyon Shield: approvals, admin keys, incident history.",
                "Selected 1 positions across 1 chains; Sentinel >= 70 and position cap <= 35%.",
                "Composed execution plan: Enso/Jupiter routes with gas and slippage buffers.",
            ],
        },
        extra_cards=[
            ExtraCard(card_id="matrix-1", card_type="sentinel_matrix", payload={**allocation_payload, "low_count": 1, "medium_count": 0, "high_count": 0}),
            ExtraCard(card_id="exec-1", card_type="execution_plan", payload={"steps": [], "total_gas": "~$4.80", "slippage_cap": "0.5%", "wallets": "MetaMask", "tx_count": 1, "requires_signature": True}),
        ],
    )

    chunks = []
    async for chunk in run_ephemeral_turn(
        router=None,
        tools=[_FakeTool("allocate_plan", env)],
        message="I have $10,000 USDC. Allocate it across staking and yield.",
    ):
        chunks.append(chunk.decode())

    events = _events_from_wire("".join(chunks))
    thoughts = [frame["content"] for frame in events["thought"]]

    assert len(thoughts) >= 8
    assert any("Parsed intent" in line for line in thoughts)
    assert any("DefiLlama" in line for line in thoughts)
    assert any("TVL" in line and "history" in line for line in thoughts)
    assert any("Sentinel" in line and "Safety" in line for line in thoughts)
    assert any("Ilyon Shield" in line for line in thoughts)
    assert any("execution plan" in line.lower() for line in thoughts)
    assert {card["card_type"] for card in events["card"]} >= {"allocation", "sentinel_matrix", "execution_plan"}


@pytest.mark.asyncio
async def test_run_ephemeral_turn_emits_advanced_reasoning_for_swap():
    env = ToolEnvelope(
        ok=True,
        card_id="swap-1",
        card_type="swap_quote",
        card_payload={
            "pay": {"symbol": "ETH", "amount": "0.5"},
            "receive": {"symbol": "USDC", "amount": "1500"},
            "rate": "3000 USDC / ETH",
            "router": "0x / Uniswap",
            "price_impact_pct": 0.18,
        },
        data={
            "pay": {"symbol": "ETH", "amount": "0.5"},
            "receive": {"symbol": "USDC", "amount": "1500"},
            "rate": "3000 USDC / ETH",
            "router": "0x / Uniswap",
            "price_impact_pct": 0.18,
        },
    )

    chunks = []
    async for chunk in run_ephemeral_turn(
        router=None,
        tools=[_FakeTool("simulate_swap", env)],
        message="swap 0.5 ETH to USDC on Ethereum",
    ):
        chunks.append(chunk.decode())

    events = _events_from_wire("".join(chunks))
    thoughts = [frame["content"] for frame in events["thought"]]

    assert len(thoughts) >= 5
    assert any("Parsed swap intent" in line for line in thoughts)
    assert any("route" in line.lower() or "quote" in line.lower() for line in thoughts)
    assert any("price impact" in line.lower() for line in thoughts)
    assert events["card"][0]["card_type"] == "swap_quote"


@pytest.mark.asyncio
async def test_run_ephemeral_turn_formats_unsupported_yield_execution_without_plan_card():
    env = ToolEnvelope(
        ok=True,
        card_id="search-1",
        data={
            "execution_requested": True,
            "primary_candidates": [
                {"protocol": "meteora", "symbol": "SOL-USDC", "chain": "solana", "apy": 64.0, "risk_level": "HIGH"}
            ],
            "execution_readiness_summary": {"executable_count": 0, "research_only_count": 1},
            "execution_blockers": [
                {
                    "code": "unsupported_adapter",
                    "title": "Direct execution is not supported yet",
                    "detail": "Meteora Solana pool deposits need a verified Solana pool adapter before signing is enabled.",
                }
            ],
            "analysis_trace": ["Separated executable candidates from research-only Solana pools."],
        },
    )

    chunks = []
    async for chunk in run_ephemeral_turn(
        router=None,
        tools=[_FakeTool("search_defi_opportunities", env)],
        message="Research Solana pools targeting 60% APY, then execute it",
    ):
        chunks.append(chunk.decode())

    events = _events_from_wire("".join(chunks))
    final = events["final"][0]["content"]

    assert "Direct execution is not supported yet" in final
    assert "signing" in final.lower()
    assert "card" not in events or all(card["card_type"] != "execution_plan" for card in events["card"])
