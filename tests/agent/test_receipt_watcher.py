from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.receipt_watcher import ReceiptWatcher


@pytest.fixture
def watcher():
    return ReceiptWatcher(
        rpc_call=AsyncMock(),
        sol_rpc_call=AsyncMock(),
    )


class TestWaitEvmReceipt:
    @pytest.mark.asyncio
    async def test_returns_receipt_on_first_attempt(self, watcher):
        expected = {"status": "0x1", "logs": []}
        watcher._rpc_call.return_value = expected

        result = await watcher.wait_evm_receipt("0xabc")

        assert result["status"] == "0x1"
        assert result["decoded_logs"] == []
        watcher._rpc_call.assert_awaited_once_with("eth_getTransactionReceipt", ["0xabc"])

    @pytest.mark.asyncio
    async def test_retries_then_raises_timeout(self, watcher):
        watcher._rpc_call.return_value = None

        with pytest.raises(TimeoutError, match="receipt not found"):
            await watcher.wait_evm_receipt("0xabc", max_attempts=3)

        assert watcher._rpc_call.await_count == 3

    @pytest.mark.asyncio
    async def test_decodes_logs_when_present(self, watcher):
        receipt = {
            "status": "0x1",
            "logs": [
                {
                    "address": "0xContract",
                    "topics": [
                        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                        "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    ],
                    "data": "0x0000000000000000000000000000000000000000000000000000000000000064",
                }
            ],
        }
        watcher._rpc_call.return_value = receipt

        result = await watcher.wait_evm_receipt("0xabc")

        assert result["status"] == "0x1"
        assert "decoded_logs" in result
        assert len(result["decoded_logs"]) == 1
        assert result["decoded_logs"][0]["event_signature"] == "Transfer(address,address,uint256)"

    @pytest.mark.asyncio
    async def test_no_decoded_logs_when_empty(self, watcher):
        watcher._rpc_call.return_value = {"status": "0x1", "logs": []}

        result = await watcher.wait_evm_receipt("0xabc")

        assert result.get("decoded_logs") == []


class TestWaitSolanaSignature:
    @pytest.mark.asyncio
    async def test_returns_status_when_confirmed(self, watcher):
        watcher._sol_rpc_call.return_value = {
            "value": [
                {
                    "slot": 123,
                    "confirmationStatus": "confirmed",
                    "err": None,
                }
            ]
        }

        result = await watcher.wait_solana_signature("sig123")

        assert result["signature"] == "sig123"
        assert result["slot"] == 123
        watcher._sol_rpc_call.assert_awaited_once_with(
            "getSignatureStatuses", [["sig123"], {"searchTransactionHistory": True}]
        )

    @pytest.mark.asyncio
    async def test_retries_then_raises_timeout(self, watcher):
        watcher._sol_rpc_call.return_value = {"value": [None]}

        with pytest.raises(TimeoutError, match="signature not confirmed"):
            await watcher.wait_solana_signature("sig123", max_attempts=3)

        assert watcher._sol_rpc_call.await_count == 3

    @pytest.mark.asyncio
    async def test_raises_when_error_in_status(self, watcher):
        watcher._sol_rpc_call.return_value = {
            "value": [
                {
                    "slot": 123,
                    "confirmationStatus": "confirmed",
                    "err": {"InstructionError": [0, "Custom", 1]},
                }
            ]
        }

        with pytest.raises(TimeoutError, match="signature not confirmed"):
            await watcher.wait_solana_signature("sig123", max_attempts=2)


class TestLogDecoding:
    def test_decode_transfer_event(self):
        log = {
            "address": "0xToken",
            "topics": [
                "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            ],
            "data": "0x0000000000000000000000000000000000000000000000000000000000000064",
        }

        decoded = ReceiptWatcher.decode_log(log)

        assert decoded["event_signature"] == "Transfer(address,address,uint256)"
        assert decoded["from"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        assert decoded["to"] == "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        assert decoded["value"] == "100"

    def test_decode_unknown_event(self):
        log = {
            "address": "0xContract",
            "topics": ["0x1234567890abcdef"],
            "data": "0x",
        }

        decoded = ReceiptWatcher.decode_log(log)

        assert decoded["event_signature"] == "unknown"
        assert decoded["topic0"] == "0x1234567890abcdef"


class TestFromSettings:
    def test_uses_sentinel_api_target(self):
        with patch("src.agent.receipt_watcher.settings") as mock_settings:
            mock_settings.SENTINEL_API_TARGET = "http://sentinel:8080"
            watcher = ReceiptWatcher.from_settings()
            assert watcher._base_url == "http://sentinel:8080"

    def test_fallback_to_localhost(self):
        with patch("src.agent.receipt_watcher.settings") as mock_settings:
            mock_settings.SENTINEL_API_TARGET = ""
            watcher = ReceiptWatcher.from_settings()
            assert watcher._base_url == "http://localhost:8080"
