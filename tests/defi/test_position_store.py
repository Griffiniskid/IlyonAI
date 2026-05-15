"""Tests for src/defi/position_store.py."""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from src.defi.position_store import UserPosition


def test_new_position_assigns_uuid():
    p = UserPosition.new(
        user_id=1,
        wallet_address="0xAAA",
        chain_id=1,
        protocol="uniswap-v3",
        pool_id="0xpool",
        receipt_kind="V3_NFT",
        tx_hash="0xtx",
    )
    assert p.position_id
    assert len(p.position_id) == 36  # uuid4 form
    assert p.status == "open"
    assert p.wallet_address == "0xaaa"  # lowercased


def test_new_position_accepts_extras():
    p = UserPosition.new(
        user_id=1, wallet_address="0xa", chain_id=1, protocol="uniswap-v3",
        pool_id="0xp", receipt_kind="V3_NFT", tx_hash="0xt",
        tick_lower=-100, tick_upper=100,
        amount0_deposited=Decimal("1.5"),
        amount1_deposited=Decimal("3000.0"),
        liquidity=Decimal("12345"),
        receipt_token_id="42",
    )
    assert p.tick_lower == -100
    assert p.amount0_deposited == Decimal("1.5")
    assert p.receipt_token_id == "42"


def test_to_row_stringifies_decimals():
    p = UserPosition.new(
        user_id=1, wallet_address="0xa", chain_id=1, protocol="uniswap-v3",
        pool_id="0xp", receipt_kind="V3_NFT", tx_hash="0xt",
        amount0_deposited=Decimal("1.5"),
    )
    row = p.to_row()
    assert row["amount0_deposited"] == "1.5"
    assert row["amount1_deposited"] is None
    assert row["status"] == "open"


def test_to_row_serialises_metadata_json():
    p = UserPosition.new(
        user_id=1, wallet_address="0xa", chain_id=1, protocol="uniswap-v3",
        pool_id="0xp", receipt_kind="V3_NFT", tx_hash="0xt",
        metadata={"slippage_bps": 50, "range_preset": "balanced"},
    )
    row = p.to_row()
    assert json.loads(row["metadata_json"]) == {"slippage_bps": 50, "range_preset": "balanced"}


def test_to_row_handles_no_metadata():
    p = UserPosition.new(
        user_id=1, wallet_address="0xa", chain_id=1, protocol="uniswap-v3",
        pool_id="0xp", receipt_kind="V3_NFT", tx_hash="0xt",
    )
    assert p.to_row()["metadata_json"] is None


def test_to_row_lowercased_wallet():
    p = UserPosition.new(
        user_id=1, wallet_address="0xAbCdEf1234",
        chain_id=1, protocol="uniswap-v3",
        pool_id="0xp", receipt_kind="V3_NFT", tx_hash="0xt",
    )
    assert p.to_row()["wallet_address"] == "0xabcdef1234"


class _FakeSession:
    """Stub sqlalchemy AsyncSession capturing executed statements."""

    def __init__(self):
        self.statements: list[tuple[str, dict | None]] = []

    async def execute(self, statement, params=None, *a, **kw):
        # sqlalchemy text() compiles to a TextClause — capture its raw text.
        text_repr = str(statement)
        self.statements.append((text_repr, params))
        # Return a stub with .mappings().all() shape for SELECTs.
        class _R:
            def mappings(self):
                return self
            def all(self):
                return []
        return _R()


def test_insert_position_emits_correct_sql():
    from src.defi.position_store import insert_position

    session = _FakeSession()
    p = UserPosition.new(
        user_id=42, wallet_address="0xa", chain_id=1, protocol="uniswap-v3",
        pool_id="0xp", receipt_kind="V3_NFT", tx_hash="0xtx",
    )
    asyncio.run(insert_position(session, p))
    assert len(session.statements) == 1
    sql_text, params = session.statements[0]
    assert "INSERT INTO user_positions" in sql_text
    assert params["position_id"] == p.position_id
    assert params["user_id"] == 42


def test_find_open_positions_filters_by_chain():
    from src.defi.position_store import find_open_positions

    session = _FakeSession()
    asyncio.run(find_open_positions(session, wallet_address="0xa", chain_id=1))
    sql_text, params = session.statements[0]
    assert "wallet_address = :wallet" in sql_text
    assert "chain_id = :chain_id" in sql_text
    assert params["wallet"] == "0xa"
    assert params["chain_id"] == 1


def test_find_open_positions_filters_by_protocol():
    from src.defi.position_store import find_open_positions

    session = _FakeSession()
    asyncio.run(find_open_positions(session, wallet_address="0xa", protocol="uniswap-v3"))
    sql_text, params = session.statements[0]
    assert "protocol = :protocol" in sql_text
    assert params["protocol"] == "uniswap-v3"


def test_close_position_emits_update():
    from src.defi.position_store import close_position

    session = _FakeSession()
    asyncio.run(close_position(session, position_id="pid-123", tx_hash="0xtx"))
    sql_text, params = session.statements[0]
    assert "UPDATE user_positions" in sql_text
    assert "status = 'closed'" in sql_text
    assert params["pid"] == "pid-123"
