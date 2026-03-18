import pytest
from typing import Any, cast

from src.config import settings
from src.defi.stores.analysis_store import AnalysisStore
from src.storage.cache import get_cache


class RecordingCache:
    def __init__(self):
        self.data = {}
        self.calls = []

    async def set(self, key, value, ttl=None):
        self.calls.append((key, value, ttl))
        self.data[key] = value

    async def get(self, key):
        return self.data.get(key)


@pytest.mark.asyncio
async def test_analysis_store_round_trips_provisional_payload():
    await get_cache().clear()
    writer = AnalysisStore()
    await writer.save_status(
        "ana_1",
        {"status": "running", "provisional_shortlist": [{"id": "opp_1"}]},
    )

    reader = AnalysisStore()
    saved = await reader.get_status("ana_1")

    assert saved is not None
    assert saved["provisional_shortlist"][0]["id"] == "opp_1"


@pytest.mark.asyncio
async def test_analysis_store_uses_defi_analysis_ttl_for_writes():
    cache = RecordingCache()
    store = AnalysisStore(cache=cast(Any, cache))

    await store.save_status("ana_1", {"status": "running"})
    await store.save_opportunity_document("opp_1", {"identity": {"id": "opp_1"}})

    assert cache.calls[0][2] == settings.defi_analysis_ttl_seconds
    assert cache.calls[1][2] == settings.defi_analysis_ttl_seconds


@pytest.mark.asyncio
async def test_analysis_store_round_trips_completed_opportunity_by_id():
    await get_cache().clear()
    writer = AnalysisStore()
    await writer.save_opportunity_document(
        "opp_1",
        {"identity": {"id": "opp_1"}, "recommendation": {"action": "watch"}},
    )

    reader = AnalysisStore()
    saved = await reader.get_opportunity_document("opp_1")

    assert saved is not None
    assert saved["identity"]["id"] == "opp_1"
