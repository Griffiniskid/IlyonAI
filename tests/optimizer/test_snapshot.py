import pytest

from src.optimizer.snapshot import snapshot_from_user


@pytest.mark.asyncio
async def test_snapshot_empty_for_missing_wallet():
    positions = await snapshot_from_user("")
    assert positions == []
