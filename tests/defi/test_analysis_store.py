import pytest

from src.defi.stores.analysis_store import AnalysisStore
from src.storage.cache import get_cache


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
