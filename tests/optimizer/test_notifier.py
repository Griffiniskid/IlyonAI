import pytest

from src.optimizer.notifier import notify_proposal


@pytest.mark.asyncio
async def test_notify_proposal_is_noop_when_no_session():
    await notify_proposal(user_id=1, plan_id="p", title="t", db=None)
    # no-op: simply does not raise
