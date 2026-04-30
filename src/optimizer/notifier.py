from __future__ import annotations


def notification_channel(*, has_active_session: bool) -> str:
    return "sse" if has_active_session else "email"
