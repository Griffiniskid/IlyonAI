"""Pin tests for BUG-M02 projection-jump exceptions in plan-level status.

Spec §5 defines the per-pipeline state machine: PROMPTED → PARSING → … →
READY_TO_SIGN. The plan-level ``status`` field is a *coarser projection*
that rolls up per-step statuses. Some legitimate plan trajectories
(deterministic build paths, zero-step research plans, blocker fast-paths)
skip the intermediate plan-level statuses because the per-step state
machine already walked them. The ``_validate_pipeline_transition`` helper
admits those known-good projection jumps silently and only soft-warns on
truly illegal jumps.

These tests pin the projection-jump exception set so any future addition
or removal is intentional + reviewed.
"""
from __future__ import annotations

import logging

import pytest

from src.defi.execution.models import ExecutionPlanV3


def _make_plan(status: str = "draft") -> ExecutionPlanV3:
    plan = ExecutionPlanV3.new(title="t", summary="s")
    plan.status = status
    return plan


@pytest.mark.parametrize(
    ("prior", "nxt"),
    [
        ("draft", "ready"),
        ("draft", "blocked"),
        ("draft", "executing"),
        ("draft", "failed"),
        ("ready", "complete"),
        ("blocked", "ready"),
        ("blocked", "draft"),
    ],
)
def test_known_projection_jumps_are_silent(prior, nxt, caplog):
    """Coarse-rollup jumps the per-step machine already justified must
    not soft-warn — they would flood production logs every chat turn."""
    plan = _make_plan(prior)
    caplog.set_level(logging.WARNING, logger="src.defi.execution.models")
    plan._validate_pipeline_transition(prior, nxt)
    assert "illegal state transition" not in caplog.text


def test_truly_illegal_jump_still_warns(caplog):
    """Sanity: a transition outside the projection-jump set should still
    soft-warn so genuine state-machine bugs aren't suppressed.

    Use ready→blocked — it's not in the projection-jump allowlist AND
    isn't admitted by spec §5 (READY_TO_SIGN can only go to RE_SIMULATING
    or SIGNING)."""
    plan = _make_plan("ready")
    caplog.set_level(logging.WARNING, logger="src.defi.execution.models")
    plan._validate_pipeline_transition("ready", "blocked")
    assert "illegal state transition" in caplog.text


def test_initial_entry_is_tolerated(caplog):
    """Unmapped statuses (e.g. internal sentinel values) are silent — the
    validator only enforces against the known plan-status vocabulary."""
    plan = _make_plan()
    caplog.set_level(logging.WARNING, logger="src.defi.execution.models")
    plan._validate_pipeline_transition("__pristine__", "draft")
    assert "illegal state transition" not in caplog.text
