from collections import defaultdict
import asyncio
from typing import Awaitable, Callable

from src.platform.circuit_breaker import CircuitBreaker
from src.platform.dead_letter_queue import DeadLetterQueue
from src.platform.retry import run_async_with_retry


EventSubscriber = Callable[[dict], Awaitable[None]]


class InMemoryEventBus:
    def __init__(
        self,
        *,
        max_retry_attempts: int = 1,
        retry_base_delay_seconds: float = 0.0,
        retry_backoff_factor: float = 2.0,
        failure_threshold: int = 3,
        recovery_seconds: int = 30,
        dead_letter_queue: DeadLetterQueue | None = None,
    ) -> None:
        self.subscribers: dict[str, list[EventSubscriber]] = defaultdict(list)
        self.max_retry_attempts = max_retry_attempts
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_backoff_factor = retry_backoff_factor
        self.dead_letter_queue = dead_letter_queue or DeadLetterQueue()
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._circuit_breakers: dict[tuple[str, EventSubscriber], CircuitBreaker] = {}

    def subscribe(self, topic: str, subscriber: EventSubscriber) -> Callable[[], None]:
        self.subscribers[topic].append(subscriber)

        def _unsubscribe() -> None:
            topic_subscribers = self.subscribers.get(topic)
            if not topic_subscribers:
                return
            try:
                topic_subscribers.remove(subscriber)
            except ValueError:
                return
            if not topic_subscribers:
                self.subscribers.pop(topic, None)
            self._circuit_breakers.pop((topic, subscriber), None)

        return _unsubscribe

    async def publish(self, topic: str, event: dict) -> None:
        subscribers = list(self.subscribers.get(topic, []))
        if not subscribers:
            return

        await asyncio.gather(*(self._deliver(topic, event, subscriber) for subscriber in subscribers))

    async def _deliver(self, topic: str, event: dict, subscriber: EventSubscriber) -> None:
        source = (topic, subscriber)
        breaker = self._circuit_breakers.get(source)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=self.failure_threshold,
                recovery_seconds=self.recovery_seconds,
            )
            self._circuit_breakers[source] = breaker

        if not breaker.can_execute():
            self.dead_letter_queue.write(
                {
                    "topic": topic,
                    "event": event,
                    "source": source,
                    "reason": "circuit_open",
                }
            )
            return

        try:
            await run_async_with_retry(
                lambda: subscriber(event),
                max_attempts=self.max_retry_attempts,
                base_delay_seconds=self.retry_base_delay_seconds,
                backoff_factor=self.retry_backoff_factor,
            )
            breaker.record_success()
        except Exception as exc:
            breaker.record_failure()
            self.dead_letter_queue.write(
                {
                    "topic": topic,
                    "event": event,
                    "source": source,
                    "reason": str(exc),
                }
            )

    def get_circuit_state(self, topic: str, subscriber: EventSubscriber) -> str:
        breaker = self._circuit_breakers.get((topic, subscriber))
        if breaker is None:
            return "closed"
        return breaker.state

    @property
    def circuit_breakers(self) -> dict[tuple[str, EventSubscriber], CircuitBreaker]:
        return dict(self._circuit_breakers)
