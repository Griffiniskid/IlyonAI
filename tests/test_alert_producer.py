import pytest
from unittest.mock import patch, AsyncMock
from src.alerts.store import InMemoryAlertStore
from src.alerts.producer import AlertProducer


@pytest.mark.asyncio
async def test_alert_producer_generates_whale_alerts():
    """Producer should generate alerts from whale transactions above threshold."""
    store = InMemoryAlertStore()
    producer = AlertProducer(store=store, whale_threshold_usd=100_000)

    mock_overview = {
        "transactions": [
            {"type": "buy", "amount_usd": 500_000, "wallet_address": "whale1", "direction": "inflow"},
            {"type": "sell", "amount_usd": 50_000, "wallet_address": "small1", "direction": "outflow"},
        ],
    }
    mock_db = AsyncMock()
    mock_db.get_whale_overview = AsyncMock(return_value=mock_overview)

    with patch("src.alerts.producer.get_database", return_value=mock_db):
        await producer.check_whale_flows()

    alerts = await store.list_alerts()
    # Only the $500K transaction should generate an alert (above $100K threshold)
    assert len(alerts) == 1
    assert "500" in alerts[0].title
    assert alerts[0].severity == "high"


@pytest.mark.asyncio
async def test_alert_producer_generates_rekt_alerts():
    """Producer should generate alerts for new rekt incidents."""
    store = InMemoryAlertStore()
    producer = AlertProducer(store=store)

    mock_incidents = [
        {"id": "test-hack-1", "name": "TestProtocol", "amount_usd": 5_000_000, "severity": "HIGH"},
    ]

    mock_rekt = AsyncMock()
    mock_rekt.get_incidents = AsyncMock(return_value=mock_incidents)
    mock_rekt.close = AsyncMock()

    with patch("src.alerts.producer.RektDatabase", return_value=mock_rekt):
        await producer.check_rekt_incidents()

    alerts = await store.list_alerts()
    assert len(alerts) == 1
    assert "TestProtocol" in alerts[0].title
