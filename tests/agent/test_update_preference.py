import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools.update_preference import update_preference
from src.storage.agent_preferences import get_or_default
from src.storage.database import get_database


@pytest.mark.asyncio
async def test_update_preference_persists_slippage_cap():
    ctx = ToolCtx(services=type("S", (), {})(), user_id=77, wallet="0xU")
    env = await update_preference(ctx, slippage_cap_bps=30)
    assert env.ok

    db = await get_database()
    prefs = await get_or_default(db, user_id=77)
    assert prefs.slippage_cap_bps == 30


@pytest.mark.asyncio
async def test_update_preference_lists_chains():
    ctx = ToolCtx(services=type("S", (), {})(), user_id=88, wallet="0xU")
    env = await update_preference(ctx, preferred_chains=["arbitrum", "base"])
    assert env.ok
    db = await get_database()
    prefs = await get_or_default(db, user_id=88)
    assert prefs.preferred_chains == ["arbitrum", "base"]


@pytest.mark.asyncio
async def test_update_preference_rejects_guest():
    ctx = ToolCtx(services=type("S", (), {})(), user_id=0, wallet=None)
    env = await update_preference(ctx, slippage_cap_bps=30)
    assert not env.ok
    assert env.error is not None
    assert env.error.code == "not_authenticated"


@pytest.mark.asyncio
async def test_update_preference_rejects_unknown_field():
    ctx = ToolCtx(services=type("S", (), {})(), user_id=99, wallet="0xU")
    env = await update_preference(ctx, bogus_field="x")
    assert not env.ok
    assert env.error is not None
    assert env.error.code == "nothing_to_update"
