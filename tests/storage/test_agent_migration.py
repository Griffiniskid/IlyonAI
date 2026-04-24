"""
Tests for agent_platform migration (agent_001).

Verifies that:
- web_users has new columns: id, email, password_hash, display_name
- chats and chat_messages tables exist
- FK cascade deletes work (deleting web_users cascades to chats)

These tests require a running PostgreSQL instance with the migration applied.
They are intended to run via:  alembic upgrade head  &&  pytest tests/storage/
"""
import pytest
from sqlalchemy import text
from src.storage.database import get_database


@pytest.mark.asyncio
async def test_web_users_has_new_columns():
    """web_users must contain id, email, password_hash, display_name after migration."""
    db = await get_database()
    async with db._engine.connect() as conn:
        cols = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'web_users'"
        ))
        names = {r[0] for r in cols}
    assert {"id", "email", "password_hash", "display_name"}.issubset(names)


@pytest.mark.asyncio
async def test_chats_and_chat_messages_exist():
    """Both chats and chat_messages tables must exist after migration."""
    db = await get_database()
    async with db._engine.connect() as conn:
        for table in ("chats", "chat_messages"):
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = :t)"
            ), {"t": table})
            assert result.scalar() is True


@pytest.mark.asyncio
async def test_chat_messages_fk_cascades():
    """Deleting a web_users row must cascade-delete its chats (and chat_messages)."""
    db = await get_database()
    async with db._engine.begin() as conn:
        # Insert a test user
        await conn.execute(text(
            "INSERT INTO web_users (wallet_address) VALUES ('test_cascade') "
            "ON CONFLICT DO NOTHING"
        ))
        r = await conn.execute(text(
            "SELECT id FROM web_users WHERE wallet_address='test_cascade'"
        ))
        uid = r.scalar_one()

        # Insert a chat for that user
        await conn.execute(text(
            "INSERT INTO chats (id, user_id, title) "
            "VALUES (gen_random_uuid(), :uid, 'x')"
        ), {"uid": uid})

        # Delete the user -- cascades to chats
        await conn.execute(text(
            "DELETE FROM web_users WHERE id=:uid"
        ), {"uid": uid})

        # Verify the chat was cascade-deleted
        left = await conn.execute(text(
            "SELECT count(*) FROM chats WHERE user_id=:uid"
        ), {"uid": uid})
        assert left.scalar_one() == 0
