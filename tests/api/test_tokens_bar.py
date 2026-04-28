import pytest
from aiohttp.test_utils import TestClient, TestServer
from src.api.app import create_api_app
from unittest.mock import patch


@pytest.mark.asyncio
async def test_ticker_returns_503_when_flag_off():
    with patch("src.config.settings.FEATURE_TOKENS_BAR", False):
        app = create_api_app()
        async with TestClient(TestServer(app)) as client:
            r = await client.get("/api/v1/tokens/ticker")
            assert r.status == 503
