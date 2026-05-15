"""Spec §12 — canonical PlanStatus vocabulary regression pin.

The runtime is migrating from legacy lowercase statuses (draft / blocked
/ ready) to the spec's canonical SCREAMING_SNAKE_CASE form (DRAFTING /
READY_TO_SIGN / ...). This test pins the canonical set so the migration
can't silently drop or rename a status.
"""
from __future__ import annotations

import typing

from src.defi.execution.models import PlanStatus, _PLAN_TO_PIPELINE_STATE


# Per spec §12 — exact 12 canonical statuses.
_CANONICAL_STATUSES = (
    "DRAFTING",
    "READY_TO_SIGN",
    "SIGNING_IN_PROGRESS",
    "BROADCASTED",
    "PENDING_DST_FILL",
    "REBUILDING",
    "CONFIRMING",
    "VERIFYING",
    "INDEXED",
    "FAILED",
    "STUCK_BALANCE",
    "CANCELLED",
)


def test_every_canonical_status_admitted():
    """PlanStatus Literal type admits every §12 canonical status."""
    args = typing.get_args(PlanStatus)
    for canonical in _CANONICAL_STATUSES:
        assert canonical in args, f"PlanStatus missing canonical status {canonical}"


def test_legacy_lowercase_statuses_still_admitted():
    """Backward-compat: legacy lowercase statuses coexist with canonical
    until every writer is migrated."""
    args = typing.get_args(PlanStatus)
    for legacy in ("draft", "blocked", "ready", "executing", "complete", "failed", "aborted"):
        assert legacy in args, f"Legacy status {legacy} dropped"


def test_canonical_maps_to_pipeline_state():
    """Every canonical status has a §5 state-machine mapping."""
    for canonical in _CANONICAL_STATUSES:
        assert canonical in _PLAN_TO_PIPELINE_STATE, (
            f"Canonical status {canonical} missing _PLAN_TO_PIPELINE_STATE entry"
        )


def test_canonical_set_size_exactly_12():
    """Spec §12 lists exactly 12 statuses. If a 13th appears the spec
    contract changed — surface explicitly."""
    assert len(_CANONICAL_STATUSES) == 12


def test_screaming_snake_case_naming():
    """Canonical statuses use SCREAMING_SNAKE_CASE, not lowercase."""
    for canonical in _CANONICAL_STATUSES:
        assert canonical.isupper(), f"{canonical} should be uppercase"
        assert "_" in canonical or canonical.isalpha(), (
            f"{canonical} should be a single token or use underscores"
        )


def test_no_canonical_status_collides_with_legacy_lowercase():
    """A canonical status name must not be a lowercase legacy alias."""
    legacy = {"draft", "blocked", "ready", "executing", "complete", "failed", "aborted"}
    for canonical in _CANONICAL_STATUSES:
        assert canonical.lower() not in legacy or canonical == "FAILED", (
            f"{canonical} clashes with legacy {canonical.lower()}"
        )
