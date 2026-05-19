"""Pin tests for spec §6c unified pending primitive.

Locks the wire shape of `PendingPrimitive.as_blocker_payload()` so the
front-end watch-strategy router + receipt watcher can rely on a single
schema across deBridge fills, Pendle epochs, Lido queue, and Solana
confirmations.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.defi.execution.pending import (
    PendingPrimitive,
    debridge_fill,
    lido_queue,
    pendle_epoch,
    solana_confirmation,
)


# ---------------------------------------------------------------------------
# Construct each of the four kinds.
# ---------------------------------------------------------------------------

def test_construct_debridge_fill() -> None:
    p = PendingPrimitive(
        kind="DEBRIDGE_FILL",
        expected_resolve_ms=300_000,
        watch_strategy="both",
        webhook_url="https://hooks.example/dln",
        rpc_check_fn_name="src.routing.debridge_client.DeBridgeBridge.status",
    )
    assert p.kind == "DEBRIDGE_FILL"
    assert p.expected_resolve_ms == 300_000
    assert p.watch_strategy == "both"
    assert p.webhook_url == "https://hooks.example/dln"
    assert p.rpc_check_fn_name.endswith("DeBridgeBridge.status")


def test_construct_pendle_epoch() -> None:
    p = PendingPrimitive(
        kind="PENDLE_EPOCH",
        expected_resolve_ms=86_400_000,
        watch_strategy="rpc_poll",
    )
    assert p.kind == "PENDLE_EPOCH"
    assert p.expected_resolve_ms == 86_400_000
    assert p.watch_strategy == "rpc_poll"
    assert p.webhook_url is None


def test_construct_lido_queue() -> None:
    p = PendingPrimitive(
        kind="LIDO_QUEUE",
        expected_resolve_ms=7_200_000,
        watch_strategy="rpc_poll",
    )
    assert p.kind == "LIDO_QUEUE"
    assert p.expected_resolve_ms == 7_200_000


def test_construct_solana_confirmation() -> None:
    p = PendingPrimitive(
        kind="SOLANA_CONFIRMATION",
        expected_resolve_ms=30_000,
        watch_strategy="rpc_poll",
    )
    assert p.kind == "SOLANA_CONFIRMATION"
    assert p.expected_resolve_ms == 30_000


# ---------------------------------------------------------------------------
# as_blocker_payload — spec wire-shape lock.
# ---------------------------------------------------------------------------

def test_as_blocker_payload_debridge_shape() -> None:
    p = PendingPrimitive(
        kind="DEBRIDGE_FILL",
        expected_resolve_ms=300_000,
        watch_strategy="both",
        webhook_url="https://hooks.example/dln",
        rpc_check_fn_name="status_fn",
    )
    payload = p.as_blocker_payload()
    assert payload["kind"] == "DEBRIDGE_FILL"
    assert payload["expected_resolve_ms"] == 300_000
    assert payload["watch_strategy"] == "both"
    assert payload["webhook_url"] == "https://hooks.example/dln"
    assert payload["rpc_check_fn_name"] == "status_fn"
    # canonical blocker_code derived from kind
    assert payload["code"] == "PENDING_DST_FILL"


def test_as_blocker_payload_pendle_epoch_code() -> None:
    payload = PendingPrimitive(
        kind="PENDLE_EPOCH",
        expected_resolve_ms=86_400_000,
        watch_strategy="rpc_poll",
    ).as_blocker_payload()
    assert payload["code"] == "PENDING_EPOCH_ENTRY"
    assert payload["webhook_url"] is None


def test_as_blocker_payload_lido_code() -> None:
    payload = PendingPrimitive(
        kind="LIDO_QUEUE",
        expected_resolve_ms=7_200_000,
        watch_strategy="rpc_poll",
    ).as_blocker_payload()
    assert payload["code"] == "PENDING_LIDO_QUEUE"


def test_as_blocker_payload_solana_code() -> None:
    payload = PendingPrimitive(
        kind="SOLANA_CONFIRMATION",
        expected_resolve_ms=30_000,
        watch_strategy="rpc_poll",
    ).as_blocker_payload()
    assert payload["code"] == "PENDING_SOLANA_CONFIRMATION"


def test_as_blocker_payload_keys_are_stable() -> None:
    """Locks the exact key set so frontend renderers don't break."""
    p = PendingPrimitive(
        kind="DEBRIDGE_FILL",
        expected_resolve_ms=300_000,
        watch_strategy="rpc_poll",
    )
    assert set(p.as_blocker_payload().keys()) == {
        "code",
        "kind",
        "expected_resolve_ms",
        "watch_strategy",
        "webhook_url",
        "rpc_check_fn_name",
    }


# ---------------------------------------------------------------------------
# Frozen-dataclass immutability.
# ---------------------------------------------------------------------------

def test_frozen_dataclass_rejects_mutation() -> None:
    p = PendingPrimitive(
        kind="DEBRIDGE_FILL",
        expected_resolve_ms=1000,
        watch_strategy="rpc_poll",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.expected_resolve_ms = 9999  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.kind = "LIDO_QUEUE"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Optional fields default to None.
# ---------------------------------------------------------------------------

def test_webhook_url_and_rpc_check_fn_optional() -> None:
    p = PendingPrimitive(
        kind="PENDLE_EPOCH",
        expected_resolve_ms=86_400_000,
        watch_strategy="rpc_poll",
    )
    assert p.webhook_url is None
    assert p.rpc_check_fn_name is None
    payload = p.as_blocker_payload()
    assert payload["webhook_url"] is None
    assert payload["rpc_check_fn_name"] is None


def test_only_webhook_url_set() -> None:
    p = PendingPrimitive(
        kind="DEBRIDGE_FILL",
        expected_resolve_ms=300_000,
        watch_strategy="webhook",
        webhook_url="https://hooks.example/x",
    )
    assert p.webhook_url == "https://hooks.example/x"
    assert p.rpc_check_fn_name is None


def test_only_rpc_check_fn_set() -> None:
    p = PendingPrimitive(
        kind="LIDO_QUEUE",
        expected_resolve_ms=7_200_000,
        watch_strategy="rpc_poll",
        rpc_check_fn_name="lido.check",
    )
    assert p.webhook_url is None
    assert p.rpc_check_fn_name == "lido.check"


# ---------------------------------------------------------------------------
# Convenience constructors — sanity check defaults align with spec ETAs.
# ---------------------------------------------------------------------------

def test_convenience_debridge_fill_defaults() -> None:
    p = debridge_fill()
    assert p.kind == "DEBRIDGE_FILL"
    assert p.expected_resolve_ms == 300_000  # 5 minutes
    # No webhook → rpc_poll, never "both"
    assert p.watch_strategy == "rpc_poll"


def test_convenience_debridge_fill_with_webhook_promotes_to_both() -> None:
    p = debridge_fill(webhook_url="https://hooks.example/dln")
    assert p.watch_strategy == "both"
    assert p.webhook_url == "https://hooks.example/dln"


def test_convenience_pendle_epoch_defaults() -> None:
    p = pendle_epoch()
    assert p.kind == "PENDLE_EPOCH"
    assert p.expected_resolve_ms == 86_400_000  # 24h


def test_convenience_lido_queue_defaults() -> None:
    p = lido_queue()
    assert p.kind == "LIDO_QUEUE"
    assert p.expected_resolve_ms == 7_200_000  # 2h


def test_convenience_solana_confirmation_defaults() -> None:
    p = solana_confirmation()
    assert p.kind == "SOLANA_CONFIRMATION"
    assert p.expected_resolve_ms == 30_000
