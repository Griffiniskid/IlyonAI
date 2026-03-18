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
