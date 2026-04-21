"""Atomic account merge: link a wallet identity to an email identity."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def merge_accounts(
    conn: AsyncConnection,
    *,
    email_id: int,
    wallet_id: int,
    sentinel: str,
    real_wallet: str,
) -> None:
    """Atomic 5-step merge: email-only user links a wallet.

    Steps:
      1. Delete stale sessions for both identities.
      2. Repoint chats from wallet row to email row.
      3. Delete obsolete wallet row (if different from email row).
      4. Update email row's wallet_address to the real wallet.
      5. (Caller commits the transaction.)
    """
    # 1. Delete stale sessions for both identities
    await conn.execute(
        text("DELETE FROM user_sessions WHERE wallet_address IN (:s, :r)"),
        {"s": sentinel, "r": real_wallet},
    )
    # 2. Repoint chats from wallet row to email row
    await conn.execute(
        text("UPDATE chats SET user_id = :eid WHERE user_id = :wid"),
        {"eid": email_id, "wid": wallet_id},
    )
    # 3. Delete obsolete wallet row (if different from email row)
    if email_id != wallet_id:
        await conn.execute(
            text("DELETE FROM web_users WHERE id = :wid"),
            {"wid": wallet_id},
        )
    # 4. Update email row's wallet_address to the real wallet
    await conn.execute(
        text("UPDATE web_users SET wallet_address = :real WHERE id = :eid"),
        {"real": real_wallet, "eid": email_id},
    )
