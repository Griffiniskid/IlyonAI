import pytest

from src.defi.stores.analysis_store import AnalysisStore


@pytest.mark.asyncio
async def test_analysis_store_round_trips_provisional_payload():
    store = AnalysisStore()
    await store.save_status(
        "ana_1",
        {"status": "running", "provisional_shortlist": [{"id": "opp_1"}]},
    )

    saved = await store.get_status("ana_1")

    assert saved["provisional_shortlist"][0]["id"] == "opp_1"


@pytest.mark.asyncio
async def test_analysis_store_round_trips_completed_opportunity_by_id():
    store = AnalysisStore()
    await store.save_opportunity_document(
        "opp_1",
        {"identity": {"id": "opp_1"}, "recommendation": {"action": "watch"}},
    )

    saved = await store.get_opportunity_document("opp_1")

    assert saved["identity"]["id"] == "opp_1"
