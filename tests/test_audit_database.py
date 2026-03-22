import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.intel.rekt_database import AuditDatabase


def _mock_aiohttp_session(json_data, status=200):
    """Create a mock aiohttp session with proper async context manager for get()."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)

    # aiohttp session.get() returns a context manager, not a coroutine
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get.return_value = mock_cm
    return mock_session


@pytest.mark.asyncio
async def test_audit_database_fetches_from_defillama():
    """AuditDatabase should supplement seed data with DefiLlama protocol audits."""
    mock_protocols = [
        {
            "name": "Lido",
            "audits": "2",
            "audit_links": ["https://example.com/lido-audit.pdf"],
            "audit_note": "Audited by Quantstamp",
            "chains": ["Ethereum"],
            "category": "Liquid Staking",
        },
        {
            "name": "Uniswap V3",  # duplicate with seed data — should be deduplicated
            "audits": "3",
            "audit_links": ["https://example.com/uni-audit.pdf"],
            "chains": ["Ethereum"],
        },
    ]

    db = AuditDatabase()
    mock_session = _mock_aiohttp_session(mock_protocols)

    with patch.object(db, "_get_session", AsyncMock(return_value=mock_session)):
        audits = await db.get_audits()

    protocol_names = [a["protocol"] for a in audits]
    assert "Lido" in protocol_names
    assert len(audits) > 4


@pytest.mark.asyncio
async def test_audit_database_cache_prevents_refetch():
    """AuditDatabase should cache DefiLlama results for 1 hour."""
    db = AuditDatabase()
    mock_session = _mock_aiohttp_session([])

    with patch.object(db, "_get_session", AsyncMock(return_value=mock_session)):
        await db.get_audits()
        await db.get_audits()  # second call should use cache

    # get() should only be called once due to caching
    assert mock_session.get.call_count == 1
