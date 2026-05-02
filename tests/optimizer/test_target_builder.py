import pytest

from src.optimizer.target_builder import build_target


@pytest.mark.asyncio
async def test_target_builder_returns_empty_for_no_holdings(monkeypatch):
    target = await build_target([], risk_budget="balanced", total_usd=None)
    assert target == []
