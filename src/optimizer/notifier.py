"""Spec §9 — Notifier surface for optimizer proposals.

When the positions watcher (`src.indexer.positions_watcher`) detects
drift (out-of-range CL position, fee-APR drop, TVL exodus, gas window
opening), it synthesises a candidate execution plan and asks the
Notifier to surface it to the user.

Spec §35 ("Position indexing") and §40 ("Indexer alerting channels in
v1: In-app only at launch") together say:

  - persist the proposal so the user sees it on next chat reconnect
    (useAgentStream resume logic re-renders open cards), AND
  - optionally publish to an in-process pub/sub so SSE consumers
    attached *right now* get the card pushed without polling.

This module ships:

  - `notification_channel(has_active_session)` — picks `sse` vs `email`
    (Telegram + email deferred per §40 to v1.1).
  - `notify_proposal(user_id, plan_id, title, *, db, payload=None)` —
    persists a `position_alerts` row with `alert_type="proposal_pending"`,
    publishes to the in-process bus, and returns the persisted row id.
  - `ProposalBus` — tiny asyncio fan-out so SSE handlers can `subscribe`
    and receive a payload dict when a proposal is published.

Migration follow-up: the current persistence target is the existing
`position_alerts` table (V7-023). A dedicated `agent_proposals` table
is out-of-scope for this gap-closer; the contract surface is stable
because the notifier returns a row id regardless of table.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# In-process pub/sub (for SSE consumers attached right now)
# ─────────────────────────────────────────────────────────────────────────────


class ProposalBus:
    """Tiny asyncio fan-out for proposal notifications.

    SSE handlers `subscribe(user_id)` to get an `asyncio.Queue` that
    will receive proposal payload dicts. `notify_proposal` calls
    `publish(user_id, payload)` after the row is persisted; every
    subscriber for that user gets a non-blocking put.
    """

    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, user_id: int) -> asyncio.Queue:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._subscribers.setdefault(user_id, []).append(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        if user_id not in self._subscribers:
            return
        with suppress(ValueError):
            self._subscribers[user_id].remove(q)
        if not self._subscribers[user_id]:
            del self._subscribers[user_id]

    async def publish(self, user_id: int, payload: dict[str, Any]) -> int:
        """Put `payload` on every queue for `user_id`. Returns the
        number of subscribers that received it (full queues are dropped
        with a warning — SSE consumers must keep up).
        """
        delivered = 0
        for q in list(self._subscribers.get(user_id, [])):
            try:
                q.put_nowait(payload)
                delivered += 1
            except asyncio.QueueFull:
                logger.warning(
                    "proposal_bus: dropping payload for user_id=%s "
                    "(SSE queue full)",
                    user_id,
                )
        return delivered

    def subscriber_count(self, user_id: int) -> int:
        return len(self._subscribers.get(user_id, []))


_BUS: ProposalBus | None = None


def get_proposal_bus() -> ProposalBus:
    """Lazy global ProposalBus — one per process. SSE handlers and the
    notifier resolve through this so they share the same bus instance.
    """
    global _BUS
    if _BUS is None:
        _BUS = ProposalBus()
    return _BUS


def reset_proposal_bus() -> None:
    """Test helper — drop the global bus so each test gets a fresh one.
    Production code never calls this.
    """
    global _BUS
    _BUS = None


# In-memory fallback for environments where the DB is offline.
_PENDING_FALLBACK: list[dict[str, Any]] = []


def get_pending_fallback() -> list[dict[str, Any]]:
    """Return the in-memory pending-proposal list. Used when `db` is
    `None` or uninitialised — guarantees the notifier contract surface
    is observable even without persistence.
    """
    return _PENDING_FALLBACK


def reset_pending_fallback() -> None:
    _PENDING_FALLBACK.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Channel selector — spec §40
# ─────────────────────────────────────────────────────────────────────────────


def notification_channel(*, has_active_session: bool) -> str:
    """Spec §40 ("Indexer alerting channels in v1: In-app only at
    launch"): SSE while the chat is open, email fallback once Telegram
    + email deliverability ship in v1.1.
    """
    return "sse" if has_active_session else "email"


# ─────────────────────────────────────────────────────────────────────────────
# Core notifier — async DB write + bus publish
# ─────────────────────────────────────────────────────────────────────────────


async def notify_proposal(
    user_id: int,
    plan_id: str,
    title: str,
    *,
    db: Any,
    payload: Optional[dict[str, Any]] = None,
) -> Optional[int]:
    """Persist a proposal-pending alert and publish to SSE consumers.

    Args:
        user_id: User identifier (Database.users.id).
        plan_id: The synthesised execution plan id (`agent_plans.plan_id`).
        title: Human-readable card title ("Rebalance ETH/USDC 5bp", …).
        db: `src.storage.database.Database` instance, or `None` to skip
            persistence (in-memory fallback only).
        payload: Optional extra metadata (drift_bps, current_price,
            suggested_range, …) — merged into the persisted JSON.

    Returns:
        The persisted `position_alerts.id` (or the fallback list index
        when persistence was skipped). `None` only when the DB write
        raised and no fallback was usable — extremely defensive path.
    """
    fired_at = datetime.utcnow()
    full_payload: dict[str, Any] = {
        "plan_id": plan_id,
        "title": title,
        "user_id": user_id,
        "fired_at": fired_at.isoformat() + "Z",
    }
    if payload:
        full_payload.update(payload)

    row_id: Optional[int] = None

    # ── 1. Persist to position_alerts (alert_type="proposal_pending"). ──
    # Routed through `src.storage.repositories.position_alert.insert_alert`
    # which is dialect-aware: PG uses RETURNING; SQLite uses
    # last_insert_rowid(). Same call signature both ways.
    if db is not None and getattr(db, "_initialized", False):
        try:
            from src.storage.repositories.position_alert import insert_alert

            # Use plan_id as the position_id surrogate — the notifier
            # is plan-scoped, not position-scoped, but the V7-023 schema
            # requires a non-null position_id.
            async with db.async_session() as session:
                row_id = await insert_alert(
                    session,
                    position_id=plan_id,
                    alert_type="proposal_pending",
                    payload=full_payload,
                )
                await session.commit()
                logger.info(
                    "notify_proposal: persisted row id=%s plan_id=%s user_id=%s",
                    row_id,
                    plan_id,
                    user_id,
                )
                if not row_id:
                    row_id = None
        except Exception as exc:  # noqa: BLE001 — log and fall back
            logger.warning(
                "notify_proposal: DB write failed (%s); using in-memory fallback",
                exc,
            )
            row_id = None

    # ── 2. In-memory fallback when DB unavailable. ──
    if row_id is None:
        _PENDING_FALLBACK.append(dict(full_payload))
        row_id = len(_PENDING_FALLBACK)  # 1-based pseudo-id
        logger.info(
            "notify_proposal: in-memory fallback id=%s plan_id=%s user_id=%s "
            "(no DB)",
            row_id,
            plan_id,
            user_id,
        )

    # ── 3. Publish to SSE bus for live consumers. ──
    bus = get_proposal_bus()
    delivered = await bus.publish(
        user_id,
        {
            "kind": "proposal_pending",
            "row_id": row_id,
            **full_payload,
        },
    )
    logger.debug(
        "notify_proposal: bus published to %s subscriber(s) for user_id=%s",
        delivered,
        user_id,
    )

    return row_id
