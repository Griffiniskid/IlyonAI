import asyncio

import pytest

from src.defi.pipeline.coalescing import CoalescedAnalysisRunner


@pytest.mark.asyncio
async def test_coalescing_reuses_the_same_in_flight_task():
    calls = 0

    async def build():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"analysis_id": "ana_1"}

    runner = CoalescedAnalysisRunner()
    first, second = await asyncio.gather(runner.run("key", build), runner.run("key", build))

    assert calls == 1
    assert first == second


@pytest.mark.asyncio
async def test_coalescing_clears_finished_task_for_future_runs():
    calls = 0

    async def build():
        nonlocal calls
        calls += 1
        return {"calls": calls}

    runner = CoalescedAnalysisRunner()

    first = await runner.run("key", build)
    second = await runner.run("key", build)

    assert first == {"calls": 1}
    assert second == {"calls": 2}


@pytest.mark.asyncio
async def test_coalescing_shields_shared_task_from_waiter_cancellation():
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def build():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"analysis_id": "ana_1"}

    runner = CoalescedAnalysisRunner()
    first = asyncio.create_task(runner.run("key", build))
    await started.wait()
    second = asyncio.create_task(runner.run("key", build))

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    release.set()
    result = await second

    assert calls == 1
    assert result == {"analysis_id": "ana_1"}


@pytest.mark.asyncio
async def test_coalescing_keeps_inflight_entry_until_shared_task_finishes():
    started = asyncio.Event()
    release = asyncio.Event()

    async def build():
        started.set()
        await release.wait()
        return {"analysis_id": "ana_1"}

    runner = CoalescedAnalysisRunner()
    first = asyncio.create_task(runner.run("key", build))
    await started.wait()
    second = asyncio.create_task(runner.run("key", build))

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    assert "key" in runner._inflight

    release.set()
    await second

    assert "key" not in runner._inflight
