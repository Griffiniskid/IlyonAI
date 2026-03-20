import pytest

from src.platform.circuit_breaker import CircuitBreaker
from src.platform.event_bus import InMemoryEventBus
from src.platform.retry import run_with_retry


def test_retry_stops_after_bounded_attempts():
    attempts: list[int] = []

    def flaky() -> None:
        attempts.append(1)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run_with_retry(flaky, max_attempts=3)

    assert len(attempts) == 3


def test_retry_uses_bounded_exponential_backoff_delays():
    attempts: list[int] = []
    delays: list[float] = []

    def flaky() -> None:
        attempts.append(1)
        raise RuntimeError("boom")

    def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    with pytest.raises(RuntimeError):
        run_with_retry(
            flaky,
            max_attempts=3,
            base_delay_seconds=0.01,
            backoff_factor=2.0,
            sleep_fn=record_sleep,
        )

    assert len(attempts) == 3
    assert delays == [0.01, 0.02]


@pytest.mark.asyncio
async def test_async_retry_uses_bounded_exponential_backoff_delays():
    from src.platform.retry import run_async_with_retry

    attempts: list[int] = []
    delays: list[float] = []

    async def flaky() -> None:
        attempts.append(1)
        raise RuntimeError("boom")

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    with pytest.raises(RuntimeError):
        await run_async_with_retry(
            flaky,
            max_attempts=3,
            base_delay_seconds=0.01,
            backoff_factor=2.0,
            sleep_fn=record_sleep,
        )

    assert len(attempts) == 3
    assert delays == [0.01, 0.02]


def test_circuit_breaker_opens_after_threshold_failures():
    breaker = CircuitBreaker(failure_threshold=3, recovery_seconds=30)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == "open"


@pytest.mark.asyncio
async def test_event_bus_writes_failed_event_to_dlq_and_opens_breaker():
    event_bus = InMemoryEventBus(max_retry_attempts=2, failure_threshold=2, recovery_seconds=60)

    async def always_fail(_: dict) -> None:
        raise RuntimeError("subscriber unavailable")

    event_bus.subscribe("analysis.progress", always_fail)
    payload = {"event_type": "analysis.progress", "analysis_id": "a-1"}

    await event_bus.publish("analysis.progress", payload)
    await event_bus.publish("analysis.progress", payload)

    assert event_bus.get_circuit_state("analysis.progress", always_fail) == "open"
    assert len(event_bus.dead_letter_queue.items) == 2


@pytest.mark.asyncio
async def test_event_bus_isolates_circuit_breakers_per_source():
    event_bus = InMemoryEventBus(max_retry_attempts=1, failure_threshold=1, recovery_seconds=60)

    failed_calls: list[int] = []
    healthy_calls: list[int] = []

    async def always_fail(_: dict) -> None:
        failed_calls.append(1)
        raise RuntimeError("subscriber unavailable")

    async def healthy(_: dict) -> None:
        healthy_calls.append(1)

    event_bus.subscribe("analysis.progress", always_fail)
    event_bus.subscribe("analysis.progress", healthy)
    payload = {"event_type": "analysis.progress", "analysis_id": "a-1"}

    await event_bus.publish("analysis.progress", payload)
    await event_bus.publish("analysis.progress", payload)

    assert event_bus.get_circuit_state("analysis.progress", always_fail) == "open"
    assert event_bus.get_circuit_state("analysis.progress", healthy) == "closed"
    assert failed_calls == [1]
    assert healthy_calls == [1, 1]
