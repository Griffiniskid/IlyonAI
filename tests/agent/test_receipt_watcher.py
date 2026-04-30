import pytest

from src.agent.receipt_watcher import ReceiptWatcher


@pytest.mark.asyncio
async def test_evm_receipt_watcher_polls_until_receipt():
    calls = {"count": 0}

    async def rpc(method, params):
        calls["count"] += 1
        if calls["count"] < 2:
            return None
        return {"transactionHash": params[0], "status": "0x1"}

    watcher = ReceiptWatcher(rpc_call=rpc, sleep=lambda _seconds: None)
    receipt = await watcher.wait_evm_receipt("0xabc", max_attempts=3)

    assert receipt["transactionHash"] == "0xabc"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_solana_receipt_watcher_uses_confirmed_status():
    async def rpc(method, params):
        assert method == "getSignatureStatuses"
        return {"value": [{"confirmationStatus": "confirmed", "err": None}]}

    watcher = ReceiptWatcher(rpc_call=rpc, sleep=lambda _seconds: None)

    receipt = await watcher.wait_solana_signature("sig", max_attempts=1)

    assert receipt["signature"] == "sig"
    assert receipt["confirmationStatus"] == "confirmed"
