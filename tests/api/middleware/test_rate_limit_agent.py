"""Tests for per-session agent rate limiting (PerSessionGap)."""
from src.api.middleware.rate_limit import PerSessionGap


def test_same_user_different_sessions_allowed():
    gap = PerSessionGap(0.5)
    assert gap.allow(1, "sess-a") is True
    assert gap.allow(1, "sess-b") is True


def test_same_user_same_session_throttled():
    gap = PerSessionGap(0.5)
    assert gap.allow(1, "sess-a") is True
    assert gap.allow(1, "sess-a") is False


def test_different_users_independent():
    gap = PerSessionGap(0.5)
    assert gap.allow(1, "sess-a") is True
    assert gap.allow(2, "sess-a") is True


def test_agent_gap_is_module_level_singleton():
    from src.api.middleware.rate_limit import agent_gap

    assert isinstance(agent_gap, PerSessionGap)
