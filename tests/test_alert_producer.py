import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.alerts.producer import AlertProducer
from tests.helpers import AsyncInMemoryAlertStore


@pytest.mark.asyncio
async def test_alert_producer_generates_whale_alerts():
    """Producer should generate alerts from whale transactions above threshold."""
    store = AsyncInMemoryAlertStore()
    producer = AlertProducer(store=store, whale_threshold_usd=100_000)

    mock_overview = {
        "transactions": [
            {"type": "buy", "amount_usd": 500_000, "wallet_address": "whale1", "chain": "solana"},
            {"type": "sell", "amount_usd": 50_000, "wallet_address": "small1", "chain": "solana"},
        ]
    }

    mock_db = AsyncMock()
    mock_db.get_whale_overview = AsyncMock(return_value=mock_overview)

    with patch("src.alerts.producer.get_database", new_callable=AsyncMock, return_value=mock_db):
        await producer.check_whale_flows()

    alerts = await store.list_alerts()
    # Only the $500K transaction should generate an alert (above $100K threshold)
    assert len(alerts) == 1
    assert "500" in alerts[0].title
    assert alerts[0].severity == "high"


@pytest.mark.asyncio
async def test_alert_producer_generates_rekt_alerts():
    """Producer should generate alerts for new rekt incidents."""
    store = AsyncInMemoryAlertStore()
    producer = AlertProducer(store=store)

    mock_incidents = [
        {"id": "test-hack-1", "name": "TestProtocol", "amount_usd": 5_000_000, "severity": "HIGH"},
    ]

    with patch("src.alerts.producer.RektDatabase") as MockRekt:
        instance = AsyncMock()
        instance.get_incidents = AsyncMock(return_value=mock_incidents)
        instance.close = AsyncMock()
        MockRekt.return_value = instance

        await producer.check_rekt_incidents()

    alerts = await store.list_alerts()
    assert len(alerts) == 1
    assert "TestProtocol" in alerts[0].title
