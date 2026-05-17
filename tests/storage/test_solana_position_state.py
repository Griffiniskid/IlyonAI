"""Pin test for V7-004 (agent_010): Solana position-state columns.

Verifies that the 5 new fields on UserPosition (redemption_program,
receipt_mint, lockup_end_ts, underlying_custody, position_nft) round
through `to_row()` and the `insert_position` SQL path. Both
all-populated and all-None paths are exercised so we catch:

  - a missing column in the INSERT statement,
  - a missing field in the dataclass,
  - a regression where to_row() silently drops one of them.

The receipt verifier path (src/defi/execution/adapters/solana_yield_builder.py)
relies on these fields being persisted; without them JLP 1h lockup,
Marinade delayed-unstake, and Sanctum INF redemption all lose state on
restart.
"""
from __future__ import annotations

import asyncio

import pytest

from src.defi.position_store import UserPosition, insert_position


_SOLANA_FIELDS = (
    "redemption_program",
    "receipt_mint",
    "lockup_end_ts",
    "underlying_custody",
    "position_nft",
)


class _FakeSession:
    """Minimal async session capturing executed (sql, params) tuples."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict | None]] = []

    async def execute(self, statement, params=None, *a, **kw):
        self.statements.append((str(statement), params))

        class _R:
            def mappings(self):
                return self

            def all(self):
                return []

        return _R()


def _populated_position() -> UserPosition:
    return UserPosition.new(
        user_id=99,
        wallet_address="So11111111111111111111111111111111111111112",
        chain_id=900,  # Solana per chain catalog
        protocol="marinade",
        pool_id="marinade-msol",
        receipt_kind="SPL_MINT",
        tx_hash="5xSig",
        redemption_program="MarBmsSgKXdrN1egZf5sqe1TMThczhMLJedb2BHptgB",
        receipt_mint="mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
        lockup_end_ts=1_777_777_777,
        underlying_custody="CustodyPDA1111111111111111111111111111111111",
        position_nft="PositionNFTMint11111111111111111111111111111",
    )


def test_dataclass_accepts_all_solana_fields():
    """All 5 fields are settable + readable on UserPosition."""
    p = _populated_position()
    assert p.redemption_program == "MarBmsSgKXdrN1egZf5sqe1TMThczhMLJedb2BHptgB"
    assert p.receipt_mint == "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"
    assert p.lockup_end_ts == 1_777_777_777
    assert p.underlying_custody == "CustodyPDA1111111111111111111111111111111111"
    assert p.position_nft == "PositionNFTMint11111111111111111111111111111"


def test_to_row_serialises_solana_fields():
    """All 5 fields land in the row dict that insert_position binds."""
    row = _populated_position().to_row()
    for field in _SOLANA_FIELDS:
        assert field in row, f"to_row dropped {field!r}"
    assert row["redemption_program"] == "MarBmsSgKXdrN1egZf5sqe1TMThczhMLJedb2BHptgB"
    assert row["receipt_mint"] == "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"
    assert row["lockup_end_ts"] == 1_777_777_777
    assert row["underlying_custody"] == "CustodyPDA1111111111111111111111111111111111"
    assert row["position_nft"] == "PositionNFTMint11111111111111111111111111111"


def test_insert_position_round_trips_solana_fields():
    """Populated path: SQL + params carry all 5 new columns."""
    session = _FakeSession()
    p = _populated_position()
    asyncio.run(insert_position(session, p))

    assert len(session.statements) == 1
    sql, params = session.statements[0]
    assert "INSERT INTO user_positions" in sql

    for field in _SOLANA_FIELDS:
        # column appears in the INSERT clause
        assert field in sql, f"INSERT statement missing column {field!r}"
        # value is bound via the params dict
        assert field in params, f"params dict missing {field!r}"

    assert params["redemption_program"] == p.redemption_program
    assert params["receipt_mint"] == p.receipt_mint
    assert params["lockup_end_ts"] == p.lockup_end_ts
    assert params["underlying_custody"] == p.underlying_custody
    assert params["position_nft"] == p.position_nft


def test_insert_position_accepts_all_none_solana_fields():
    """Nullable path: EVM-only positions don't break the insert."""
    session = _FakeSession()
    p = UserPosition.new(
        user_id=1,
        wallet_address="0xa",
        chain_id=1,
        protocol="uniswap-v3",
        pool_id="0xp",
        receipt_kind="V3_NFT",
        tx_hash="0xt",
    )
    # Sanity: defaults are None for all 5.
    for field in _SOLANA_FIELDS:
        assert getattr(p, field) is None

    asyncio.run(insert_position(session, p))

    assert len(session.statements) == 1
    sql, params = session.statements[0]
    for field in _SOLANA_FIELDS:
        assert field in sql
        assert params[field] is None


def test_migration_module_imports_cleanly():
    """agent_010 migration body parses + exposes revision metadata.

    Loaded via spec_from_file_location because the filename starts
    with a digit (not a valid Python identifier for import_module) and
    so we can stub `alembic.op` when alembic isn't installed in the
    unit-test env — we only care that the module body executes and
    declares the correct revision/down_revision linkage.
    """
    import importlib.util
    import sys
    import types
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    mig_path = (
        repo_root
        / "migrations"
        / "versions"
        / "20260517_agent_010_solana_position_state.py"
    )
    assert mig_path.exists(), f"migration file missing: {mig_path}"

    # Stub `alembic.op` if alembic isn't installed so the module body
    # can execute. Real `alembic upgrade head` uses the actual package.
    if "alembic" not in sys.modules:
        alembic_stub = types.ModuleType("alembic")
        op_stub = types.SimpleNamespace(
            add_column=lambda *a, **kw: None,
            drop_column=lambda *a, **kw: None,
        )
        alembic_stub.op = op_stub
        sys.modules["alembic"] = alembic_stub

    spec = importlib.util.spec_from_file_location(
        "agent_010_solana_position_state", str(mig_path)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "agent_010"
    assert mod.down_revision == "agent_009"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    # Smoke-call upgrade/downgrade against the stubbed op — verifies no
    # NameError / typo in column definitions at module-eval time.
    mod.upgrade()
    mod.downgrade()
