"""Standalone entrypoint to start the optimizer daemon."""
import asyncio
import signal

from src.optimizer.daemon import OptimizerDaemon


daemon = OptimizerDaemon()


def shutdown(sig, frame) -> None:
    asyncio.create_task(daemon.stop())


async def main() -> None:
    started = await daemon.start()
    if not started:
        print("Optimizer is disabled (OPTIMIZER_ENABLED=0).")
        return
    print("Optimizer daemon started.")
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    while daemon._running:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
