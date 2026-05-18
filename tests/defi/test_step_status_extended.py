"""V7 §1 — pin tests for StepStatus extended with queued + verified."""
from __future__ import annotations

from typing import get_args

from src.defi.execution.models import StepStatus


def test_step_status_includes_queued():
    assert "queued" in get_args(StepStatus)


def test_step_status_includes_verified():
    assert "verified" in get_args(StepStatus)


def test_legacy_values_preserved():
    values = set(get_args(StepStatus))
    for legacy in (
        "blocked",
        "pending",
        "ready",
        "signing",
        "submitted",
        "confirmed",
        "failed",
        "skipped",
    ):
        assert legacy in values


def test_step_status_count():
    assert len(get_args(StepStatus)) == 10
