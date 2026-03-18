import pytest

from src.defi.pipeline.enrich import EnrichmentPipeline


@pytest.mark.asyncio
async def test_enrichment_marks_timeout_sources_as_fallbacks():
    pipeline = EnrichmentPipeline(provider_timeout_seconds=0)

    enriched = await pipeline.enrich_candidate({"id": "opp_1", "protocol_slug": "aave-v3"})

    assert enriched["evidence_sources"]["docs"]["fallback_used"] is True
    assert enriched["evidence_sources"]["history"]["fallback_used"] is True


@pytest.mark.asyncio
async def test_enrichment_preserves_payloads_and_source_metadata():
    class DocsStub:
        async def analyze(self, url, docs_url=None):
            return {
                "available": True,
                "url": docs_url or url,
                "freshness_hours": 4.5,
                "placeholder": False,
            }

    class HistoryStub:
        async def get_pool_history(self, pool_id):
            return [{"apy": 7.2, "tvlUsd": 1000}]

        def summarize_pool_history(self, history):
            return {"available": True, "observations": len(history), "freshness_hours": 1.0}

    pipeline = EnrichmentPipeline(docs=DocsStub(), history=HistoryStub(), provider_timeout_seconds=1)

    enriched = await pipeline.enrich_candidate(
        {
            "id": "opp_1",
            "pool_id": "pool_1",
            "protocol_url": "https://protocol.example",
            "docs_url": "https://docs.example",
        }
    )

    assert enriched["docs_profile"]["available"] is True
    assert enriched["history_summary"]["observations"] == 1
    assert enriched["evidence_sources"]["docs"] == {
        "source": "provider",
        "fallback_used": False,
        "freshness_hours": 4.5,
        "available": True,
    }
    assert enriched["evidence_sources"]["history"] == {
        "source": "provider",
        "fallback_used": False,
        "freshness_hours": 1.0,
        "available": True,
    }
