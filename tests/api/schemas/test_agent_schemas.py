import pytest
from pydantic import ValidationError
from src.api.schemas.agent import (
    ToolEnvelope, SentinelBlock, ShieldBlock, AgentCard,
    AllocationPayload, SwapQuotePayload, PoolPayload, TokenPayload,
    PositionPayload, PlanPayload, BalancePayload, BridgePayload,
    StakePayload, MarketOverviewPayload, PairListPayload,
    SSEFrame, ObservationFrame, CardFrame, FinalFrame,
)


def test_tool_envelope_round_trip_minimal_success():
    env = ToolEnvelope(
        ok=True, data={"x": 1}, card_type=None,
        card_id="00000000-0000-0000-0000-000000000001", card_payload=None,
    )
    assert env.ok is True
    assert env.error is None
    assert env.model_dump()["card_id"] == "00000000-0000-0000-0000-000000000001"


def test_tool_envelope_failure_requires_error():
    with pytest.raises(Exception):
        ToolEnvelope(ok=False, data=None, card_type=None, card_id="x", card_payload=None)


def test_agent_card_discriminator_routes_to_correct_payload():
    raw = {
        "card_id": "00000000-0000-0000-0000-000000000001",
        "card_type": "allocation",
        "payload": {
            "positions": [], "total_usd": "10000",
            "weighted_sentinel": 89, "risk_mix": {"LOW": 4, "MEDIUM": 1, "HIGH": 0},
        },
    }
    parsed = AgentCard.model_validate(raw)
    assert parsed.card_type == "allocation"
    assert isinstance(parsed.payload, AllocationPayload)


def test_sse_frame_observation_forbids_data():
    ObservationFrame(step_index=1, name="get_token_price", ok=True, error=None)
    with pytest.raises(ValidationError):
        ObservationFrame(step_index=1, name="x", ok=True, error=None, data={"y": 1})


def test_sentinel_block_bounds():
    with pytest.raises(ValidationError):
        SentinelBlock(sentinel=101, safety=50, durability=50, exit=50, confidence=50,
                      risk_level="LOW", strategy_fit="balanced")


def test_shield_block_requires_valid_verdict():
    with pytest.raises(ValidationError):
        ShieldBlock(verdict="OK", grade="A")  # type: ignore


def test_final_frame_shape():
    f = FinalFrame(content="done", card_ids=["a"], elapsed_ms=1234, steps=3)
    assert f.elapsed_ms == 1234
