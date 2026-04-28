import pytest
from src.storage.greenfield import GreenfieldClient


@pytest.mark.asyncio
async def test_stub_mode_put_get_roundtrip(monkeypatch):
    monkeypatch.setattr("src.config.settings.FEATURE_GREENFIELD_MEMORY", False)
    client = GreenfieldClient()
    await client.put_object("1/chat.json", b'{"summary":"test"}')
    data = await client.get_object("1/chat.json")
    assert data == b'{"summary":"test"}'


@pytest.mark.asyncio
async def test_stub_mode_missing_key_returns_none(monkeypatch):
    monkeypatch.setattr("src.config.settings.FEATURE_GREENFIELD_MEMORY", False)
    client = GreenfieldClient()
    data = await client.get_object("nonexistent.json")
    assert data is None
