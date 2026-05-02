"""Notify the user of an optimizer proposal (SSE push or email fallback)."""
from __future__ import annotations

from typing import Any


def notification_channel(*, has_active_session: bool) -> str:
    return "sse" if has_active_session else "email"


async def notify_proposal(
    user_id: int,
    plan_id: str,
    title: str,
    *,
    db: Any,
) -> None:
    """Push an SSE event if the user has an active session; else email fallback."""
    # Active-session push via an in-memory broadcast bus or SSE queue.
    # For now, the proposal is stored in agent_plans; the user will see it
    # on their next chat reconnect (handled by useAgentStream resume logic).
    pass
