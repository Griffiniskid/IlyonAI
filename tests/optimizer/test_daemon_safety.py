from datetime import datetime, timedelta, timezone

import pytest

from src.optimizer.safety import SafetyGates


@pytest.fixture(autouse=True)
def _enable_optimizer(monkeypatch):
    monkeypatch.setattr("src.config.settings.OPTIMIZER_ENABLED", True)


def test_safety_blocks_without_opt_in(monkeypatch):
    gates = SafetyGates(user_id=1)
    monkeypatch.setattr(gates, "_opt_in", lambda: False)
    ok, reason = gates.can_propose(last_proposal_at=None, total_proposals_today=0)
    assert ok is False and "opted in" in reason.lower()


def test_safety_blocks_during_cooldown():
    gates = SafetyGates(user_id=1)
    recent = datetime.now(timezone.utc) - timedelta(days=3)
    ok, reason = gates.can_propose(last_proposal_at=recent, total_proposals_today=0)
    assert ok is False and "cooldown" in reason


def test_safety_blocks_daily_limit():
    gates = SafetyGates(user_id=1)
    ok, reason = gates.can_propose(last_proposal_at=None, total_proposals_today=2)
    assert ok is False and "limit" in reason
