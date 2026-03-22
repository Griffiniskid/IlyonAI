import pytest
from unittest.mock import patch, AsyncMock

from src.data.solana import SolanaClient


@pytest.mark.asyncio
async def test_solana_client_async_context_manager():
    """SolanaClient must support async with and call close() on exit."""
    with patch.object(SolanaClient, "close", new_callable=AsyncMock) as mock_close:
        async with SolanaClient(rpc_url="https://example.com") as client:
            assert isinstance(client, SolanaClient)
        mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_solana_client_context_manager_calls_close_on_error():
    """SolanaClient must call close() even when body raises."""
    with patch.object(SolanaClient, "close", new_callable=AsyncMock) as mock_close:
        with pytest.raises(RuntimeError):
            async with SolanaClient(rpc_url="https://example.com"):
                raise RuntimeError("boom")
        mock_close.assert_awaited_once()
