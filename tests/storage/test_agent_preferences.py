"""Tests for agent_preferences storage layer."""
import pytest
from src.storage.agent_preferences import AgentPreferences, get_or_default, upsert
from src.storage.database import get_database


@pytest.mark.asyncio
async def test_agent_preferences_dataclass():
    """AgentPreferences dataclass must have all fields and as_dict() method."""
    prefs = AgentPreferences(
        user_id=42,
        risk_budget="aggressive",
        preferred_chains=["solana", "ethereum"],
        blocked_protocols=["protocol_a"],
        gas_cap_usd=50.0,
        slippage_cap_bps=100,
        notional_double_confirm_usd=5000.0,
        auto_rebalance_opt_in=1,
        rebalance_auth_signature="0xabc",
        rebalance_auth_nonce=123,
    )
    
    assert prefs.user_id == 42
    assert prefs.risk_budget == "aggressive"
    assert prefs.preferred_chains == ["solana", "ethereum"]
    assert prefs.blocked_protocols == ["protocol_a"]
    assert prefs.gas_cap_usd == 50.0
    assert prefs.slippage_cap_bps == 100
    assert prefs.notional_double_confirm_usd == 5000.0
    assert prefs.auto_rebalance_opt_in == 1
    assert prefs.rebalance_auth_signature == "0xabc"
    assert prefs.rebalance_auth_nonce == 123
    assert prefs.updated_at is None
    
    d = prefs.as_dict()
    assert d["user_id"] == 42
    assert d["risk_budget"] == "aggressive"
    assert d["preferred_chains"] == ["solana", "ethereum"]


@pytest.mark.asyncio
async def test_get_or_default_returns_defaults_for_missing_user():
    """get_or_default must return default preferences when user has no record."""
    db = await get_database()
    prefs = await get_or_default(db, 999999)
    
    assert prefs.user_id == 999999
    assert prefs.risk_budget == "balanced"
    assert prefs.preferred_chains is None
    assert prefs.blocked_protocols is None
    assert prefs.gas_cap_usd is None
    assert prefs.slippage_cap_bps == 50
    assert prefs.notional_double_confirm_usd == 10000.0
    assert prefs.auto_rebalance_opt_in == 0
    assert prefs.rebalance_auth_signature is None
    assert prefs.rebalance_auth_nonce is None


@pytest.mark.asyncio
async def test_upsert_creates_and_get_or_default_reads():
    """upsert must create a record; get_or_default must read it back."""
    db = await get_database()
    user_id = 999998
    
    # Upsert
    result = await upsert(
        db,
        user_id,
        risk_budget="conservative",
        preferred_chains=["solana"],
        blocked_protocols=["bad_protocol"],
        gas_cap_usd=25.0,
        slippage_cap_bps=30,
    )
    assert result is True
    
    # Read back
    prefs = await get_or_default(db, user_id)
    assert prefs.user_id == user_id
    assert prefs.risk_budget == "conservative"
    assert prefs.preferred_chains == ["solana"]
    assert prefs.blocked_protocols == ["bad_protocol"]
    assert prefs.gas_cap_usd == 25.0
    assert prefs.slippage_cap_bps == 30


@pytest.mark.asyncio
async def test_upsert_updates_existing():
    """upsert must update an existing record."""
    db = await get_database()
    user_id = 999997
    
    # Create
    await upsert(db, user_id, risk_budget="aggressive")
    prefs1 = await get_or_default(db, user_id)
    assert prefs1.risk_budget == "aggressive"
    
    # Update
    await upsert(db, user_id, risk_budget="conservative", gas_cap_usd=10.0)
    prefs2 = await get_or_default(db, user_id)
    assert prefs2.risk_budget == "conservative"
    assert prefs2.gas_cap_usd == 10.0
    # Other fields should remain
    assert prefs2.slippage_cap_bps == 50


@pytest.mark.asyncio
async def test_upsert_json_list_fields():
    """upsert must correctly serialize/deserialize JSON list fields."""
    db = await get_database()
    user_id = 999996
    
    chains = ["solana", "ethereum", "base"]
    protocols = ["protocol_x", "protocol_y"]
    
    await upsert(
        db,
        user_id,
        preferred_chains=chains,
        blocked_protocols=protocols,
    )
    
    prefs = await get_or_default(db, user_id)
    assert prefs.preferred_chains == chains
    assert prefs.blocked_protocols == protocols


@pytest.mark.asyncio
async def test_upsert_partial_update_preserves_unchanged_fields():
    """upsert with partial kwargs must preserve existing fields not in kwargs."""
    db = await get_database()
    user_id = 999995
    
    await upsert(
        db,
        user_id,
        risk_budget="aggressive",
        gas_cap_usd=100.0,
        slippage_cap_bps=75,
    )
    
    # Update only risk_budget
    await upsert(db, user_id, risk_budget="balanced")
    
    prefs = await get_or_default(db, user_id)
    assert prefs.risk_budget == "balanced"
    assert prefs.gas_cap_usd == 100.0
    assert prefs.slippage_cap_bps == 75
