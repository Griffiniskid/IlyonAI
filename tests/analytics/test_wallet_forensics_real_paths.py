from datetime import datetime
from types import SimpleNamespace

import pytest

from src.analytics.wallet_forensics import WalletForensicsEngine, WalletRiskLevel


@pytest.mark.asyncio
async def test_forensics_reads_deployments_from_persisted_records(monkeypatch):
    rugged_at = datetime(2025, 1, 2)

    async def fake_load_token_deployments(wallet_address: str):
        assert wallet_address == "wallet-1"
        return [
            SimpleNamespace(
                token_address="token-1",
                token_symbol=None,
                chain=None,
                deployed_at=datetime(2025, 1, 1),
                status="active",
                peak_liquidity_usd=None,
                final_liquidity_usd=None,
                liquidity_removal_pct=None,
                lifespan_hours=None,
                rugged_at=rugged_at,
            )
        ]

    monkeypatch.setattr(
        "src.analytics.wallet_forensics.load_token_deployments",
        fake_load_token_deployments,
        raising=False,
    )

    engine = WalletForensicsEngine()
    records = await engine._get_token_deployments("wallet-1")

    assert isinstance(records, list)
    assert len(records) == 1
    record = records[0]
    assert record.token_address == "token-1"
    assert record.token_symbol == ""
    assert record.chain == "solana"
    assert record.peak_liquidity_usd == 0.0
    assert record.final_liquidity_usd == 0.0
    assert record.liquidity_removal_pct == 0.0
    assert record.lifespan_hours == 0.0
    assert record.rugged_at == rugged_at


@pytest.mark.asyncio
async def test_forensics_handles_partial_rows_with_defaults(monkeypatch):
    async def fake_load_token_deployments(wallet_address: str):
        assert wallet_address == "wallet-partial"
        return [SimpleNamespace(token_address="token-2")]

    monkeypatch.setattr(
        "src.analytics.wallet_forensics.load_token_deployments",
        fake_load_token_deployments,
        raising=False,
    )

    engine = WalletForensicsEngine()
    records = await engine._get_token_deployments("wallet-partial")

    assert len(records) == 1
    assert records[0].status == "active"
    assert isinstance(records[0].deployed_at, datetime)


@pytest.mark.asyncio
async def test_forensics_analyze_wallet_degrades_when_deployments_load_fails(monkeypatch):
    async def fake_load_token_deployments(wallet_address: str):
        assert wallet_address == "wallet-error"
        raise RuntimeError("db unavailable")

    async def fake_trace_funding_chain(self, wallet_address: str, depth: int = 3):
        return []

    async def fake_find_related_wallets(self, wallet_address: str):
        return []

    monkeypatch.setattr(
        "src.analytics.wallet_forensics.load_token_deployments",
        fake_load_token_deployments,
        raising=False,
    )
    monkeypatch.setattr(
        WalletForensicsEngine,
        "_trace_funding_chain",
        fake_trace_funding_chain,
    )
    monkeypatch.setattr(
        WalletForensicsEngine,
        "_find_related_wallets",
        fake_find_related_wallets,
    )

    engine = WalletForensicsEngine()
    result = await engine.analyze_wallet("wallet-error")

    assert result.wallet_address == "wallet-error"
    assert result.tokens_deployed == 0
    assert result.rugged_tokens == 0
    assert result.risk_level == WalletRiskLevel.MEDIUM
    assert result.evidence_summary == "No token deployment history found for this wallet."
