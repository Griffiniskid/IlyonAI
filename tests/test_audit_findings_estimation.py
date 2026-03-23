"""Tests for deterministic audit findings estimation."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.intel.rekt_database import AuditDatabase


def _mock_aiohttp_session(json_data, status=200):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get.return_value = mock_cm
    mock_session.closed = False  # prevent _get_session from creating a real session
    return mock_session


@pytest.mark.asyncio
async def test_defillama_audits_get_estimated_findings():
    """Audits from DefiLlama should have non-empty severity_findings."""
    db = AuditDatabase()
    db._session = _mock_aiohttp_session([
        {
            "name": "TestProtocol",
            "audits": "2",
            "audit_links": ["https://example.com/audit.pdf"],
            "audit_note": "Audited by Trail of Bits",
            "chains": ["Ethereum"],
        }
    ])

    audits = await db._fetch_defillama_audits()
    assert len(audits) > 0
    audit = audits[0]
    sf = audit["severity_findings"]
    assert sf, "severity_findings should not be empty"
    assert "critical" in sf
    assert "high" in sf
    assert "medium" in sf
    assert "low" in sf
    assert "informational" in sf
    assert audit["findings_source"] == "estimated"
    assert sum(sf.values()) > 0


@pytest.mark.asyncio
async def test_estimated_findings_are_deterministic():
    """Same protocol+auditor should produce same findings on repeated calls."""
    db = AuditDatabase()
    proto_data = [{
        "name": "StableProto",
        "audits": "1",
        "audit_links": [],
        "audit_note": "PeckShield",
        "chains": ["Ethereum"],
    }]
    db._session = _mock_aiohttp_session(proto_data)
    first = await db._fetch_defillama_audits()

    db._live_cache = None
    db._cache_ts = 0
    db._session = _mock_aiohttp_session(proto_data)
    second = await db._fetch_defillama_audits()

    assert first[0]["severity_findings"] == second[0]["severity_findings"]


@pytest.mark.asyncio
async def test_seed_audits_have_verified_source():
    """Seed audits should have findings_source='verified'."""
    db = AuditDatabase()
    db._session = _mock_aiohttp_session([])
    audits = await db.get_audits(limit=100)
    for a in audits:
        if a["id"].startswith("llama-"):
            assert a.get("findings_source") == "estimated"
        else:
            assert a.get("findings_source") == "verified"
