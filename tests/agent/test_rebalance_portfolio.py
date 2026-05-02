import sys
import pytest
from src.agent.tools._base import ToolCtx


def _make_prefs(**kwargs):
    class Prefs:
        auto_rebalance_opt_in = 1
        risk_budget = "balanced"
    for k, v in kwargs.items():
        setattr(Prefs, k, v)
    return Prefs()


def _get_rebalance_module():
    return sys.modules["src.agent.tools.rebalance_portfolio"]


@pytest.mark.asyncio
async def test_rebalance_proposes_plan_when_idle_usdc_high(monkeypatch):
    from src.agent.tools.rebalance_portfolio import rebalance_portfolio
    mod = _get_rebalance_module()

    async def _fake_get_or_default(db, uid):
        return _make_prefs()

    async def _fake_snapshot(*a, **k):
        return [
            {"token": "USDC", "usd": 5000, "apy": 1.5, "sentinel": 95},
        ]

    def _fake_target(*a, **k):
        return [
            {"token": "USDC", "usd": 5000, "apy": 5.5, "sentinel": 92,
             "protocol": "aave-v3", "chain_id": 42161},
        ]

    monkeypatch.setattr(mod, "get_or_default", _fake_get_or_default)
    monkeypatch.setattr(mod, "snapshot_from_user", _fake_snapshot)
    monkeypatch.setattr(mod, "build_target", _fake_target)
    monkeypatch.setattr(mod, "should_move", lambda *a, **k: True)
    monkeypatch.setattr(
        mod, "build_rebalance_intent", lambda moves: {
            "title": "Rebalance USDC",
            "steps": [{"action": "stake", "params": {"token": "USDC",
                                                      "protocol": "aave-v3",
                                                      "chain_id": 42161,
                                                      "amount": "5000"}}],
        },
    )

    ctx = ToolCtx(services=type("S", (), {})(), user_id=1, wallet="0xUser")
    env = await rebalance_portfolio(ctx, total_usd=None)
    assert env.ok
    assert env.card_type == "execution_plan_v2"


@pytest.mark.asyncio
async def test_rebalance_no_op_when_no_moves(monkeypatch):
    from src.agent.tools.rebalance_portfolio import rebalance_portfolio
    mod = _get_rebalance_module()

    async def _fake_get_or_default(db, uid):
        return _make_prefs()

    async def _fake_snapshot(*a, **k):
        return [{"token": "USDC", "usd": 5000, "apy": 1.5, "sentinel": 95}]

    def _fake_target(*a, **k):
        return [{"token": "USDC", "usd": 5000, "apy": 5.5, "sentinel": 92,
                 "protocol": "aave-v3", "chain_id": 42161}]

    monkeypatch.setattr(mod, "get_or_default", _fake_get_or_default)
    monkeypatch.setattr(mod, "snapshot_from_user", _fake_snapshot)
    monkeypatch.setattr(mod, "build_target", _fake_target)
    monkeypatch.setattr(mod, "should_move", lambda *a, **k: False)
    ctx = ToolCtx(services=type("S", (), {})(), user_id=1, wallet="0xUser")
    env = await rebalance_portfolio(ctx, total_usd=None)
    assert env.ok
    assert env.card_type in {"text", "no_change"}
    assert "no change" in env.card_payload.get("message", "").lower()
