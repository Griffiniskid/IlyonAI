import asyncio
import logging

import pytest

from src.defi.pipeline.enrich import EnrichmentPipeline

from tests.defi_fixtures import CHAIN_MATRIX, SOLANA_FIXTURE, EVM_FIXTURE

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


@pytest.mark.asyncio
async def test_enrichment_runs_docs_and_history_concurrently():
    release = asyncio.Event()
    started = []

    class DocsStub:
        async def analyze(self, url, docs_url=None):
            started.append("docs")
            await asyncio.sleep(0)
            await release.wait()
            return {"available": True, "freshness_hours": 2.0}

    class HistoryStub:
        async def get_pool_history(self, pool_id):
            started.append("history")
            release.set()
            return [{"apy": 7.2, "tvlUsd": 1000}]

        def summarize_pool_history(self, history):
            return {"available": True, "observations": len(history), "freshness_hours": 1.0}

    pipeline = EnrichmentPipeline(docs=DocsStub(), history=HistoryStub(), provider_timeout_seconds=1)

    enriched = await asyncio.wait_for(pipeline.enrich_candidate({"id": "opp_1", "pool_id": "pool_1"}), timeout=0.1)

    assert started == ["docs", "history"]
    assert enriched["history_summary"]["observations"] == 1


@pytest.mark.asyncio
async def test_enrichment_logs_and_reraises_unexpected_loader_exceptions(caplog):
    class DocsStub:
        async def analyze(self, url, docs_url=None):
            raise RuntimeError("boom")

    class HistoryStub:
        async def get_pool_history(self, pool_id):
            return []

        def summarize_pool_history(self, history):
            return {"available": False, "observations": 0, "freshness_hours": None}

    pipeline = EnrichmentPipeline(docs=DocsStub(), history=HistoryStub(), provider_timeout_seconds=1)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="boom"):
            await pipeline.enrich_candidate({"id": "opp_1"})

    assert "docs enrichment failed" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", CHAIN_MATRIX)
async def test_enrichment_supports_chain_matrix(chain):
    class DocsStub:
        async def analyze(self, url, docs_url=None):
            return {"available": True, "freshness_hours": 1.0}

    class HistoryStub:
        async def get_pool_history(self, pool_id):
            return [{"apy": 7.2, "tvlUsd": 1000}]

        def summarize_pool_history(self, history):
            return {"available": True, "observations": 1, "freshness_hours": 1.0}

    pipeline = EnrichmentPipeline(docs=DocsStub(), history=HistoryStub(), provider_timeout_seconds=1)

    enriched = await pipeline.enrich_candidate(
        {
            "id": f"opp_{chain}",
            "pool_id": "pool_1",
            "chain": chain,
            "protocol_slug": "test-protocol",
        }
    )

    assert enriched["docs_profile"]["available"] is True
    assert enriched["history_summary"]["observations"] == 1


@pytest.mark.asyncio
async def test_enrichment_supports_solana_fixture():
    class DocsStub:
        async def analyze(self, url, docs_url=None):
            return {"available": True, "freshness_hours": 1.0}

    class HistoryStub:
        async def get_pool_history(self, pool_id):
            return [{"apy": 7.2, "tvlUsd": 1000}]

        def summarize_pool_history(self, history):
            return {"available": True, "observations": 1, "freshness_hours": 1.0}

    pipeline = EnrichmentPipeline(docs=DocsStub(), history=HistoryStub(), provider_timeout_seconds=1)

    enriched = await pipeline.enrich_candidate(
        {
            "id": "opp_solana",
            "pool_id": "pool_solana",
            "chain": SOLANA_FIXTURE["chain"],
            "protocol_slug": SOLANA_FIXTURE["protocol_slug"],
        }
    )

    assert enriched["docs_profile"]["available"] is True


@pytest.mark.asyncio
async def test_enrichment_supports_evm_fixture():
    class DocsStub:
        async def analyze(self, url, docs_url=None):
            return {"available": True, "freshness_hours": 1.0}

    class HistoryStub:
        async def get_pool_history(self, pool_id):
            return [{"apy": 7.2, "tvlUsd": 1000}]

        def summarize_pool_history(self, history):
            return {"available": True, "observations": 1, "freshness_hours": 1.0}

    pipeline = EnrichmentPipeline(docs=DocsStub(), history=HistoryStub(), provider_timeout_seconds=1)

    enriched = await pipeline.enrich_candidate(
        {
            "id": "opp_evm",
            "pool_id": "pool_evm",
            "chain": EVM_FIXTURE["chain"],
            "protocol_slug": EVM_FIXTURE["protocol_slug"],
        }
    )

    assert enriched["docs_profile"]["available"] is True

