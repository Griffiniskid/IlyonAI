import pytest

from src.optimizer.daemon import OptimizerDaemon


@pytest.mark.asyncio
async def test_daemon_refuses_to_start_without_opt_in(monkeypatch):
    daemon = OptimizerDaemon()
    monkeypatch.setattr("src.config.settings.OPTIMIZER_ENABLED", False)
    started = await daemon.start()
    assert started is False


@pytest.mark.asyncio
async def test_daemon_starts_and_stops(monkeypatch):
    daemon = OptimizerDaemon()
    monkeypatch.setattr("src.config.settings.OPTIMIZER_ENABLED", True)
    started = await daemon.start()
    assert started is True
    assert daemon._running is True
    await daemon.stop()
    assert daemon._running is False
