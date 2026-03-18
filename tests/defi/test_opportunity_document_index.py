import pytest
from typing import Any, cast
import asyncio

from src.config import settings
from src.defi.docs_analyzer import ProtocolDocsAnalyzer
from src.defi.history_store import DefiHistoryStore
from src.defi.stores.evidence_store import EvidenceStore
from src.storage.cache import CacheLayer
from src.storage.cache import get_cache


class StubScraper:
    def __init__(self):
        self.calls = 0

    async def scrape_website(self, target):
        self.calls += 1
        return {
            "success": True,
            "has_content": True,
            "url": target,
            "title": "Docs",
            "description": "Protocol docs",
            "content": "governance timelock multisig oracle bridge",
            "load_time": 0.2,
            "red_flags": [],
            "has_privacy_policy": True,
            "has_terms": True,
            "has_audit_mention": True,
            "has_contact_info": True,
            "has_github": True,
        }

    async def close(self):
        return None


class StubLlama:
    def __init__(self):
        self.calls = 0

    async def get_pool_chart(self, pool_id):
        self.calls += 1
        return [
            {"apy": 10.0, "tvlUsd": 1000},
            {"apy": 12.0, "tvlUsd": 1100},
        ]


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
async def test_docs_analyzer_reads_and_writes_via_evidence_store():
    await get_cache().clear()
    scraper = StubScraper()
    analyzer = ProtocolDocsAnalyzer(scraper=cast(Any, scraper))

    first = await analyzer.analyze("https://example.com")

    second_scraper = StubScraper()
    second = await ProtocolDocsAnalyzer(scraper=cast(Any, second_scraper)).analyze("https://example.com")

    assert first["url"] == "https://example.com"
    assert second["governance_signal_count"] == first["governance_signal_count"]
    assert scraper.calls == 1
    assert second_scraper.calls == 0


@pytest.mark.asyncio
async def test_history_store_reads_and_writes_via_evidence_store():
    await get_cache().clear()
    llama = StubLlama()
    history_store = DefiHistoryStore(cast(Any, llama))

    first = await history_store.get_pool_history("pool-1")

    second_llama = StubLlama()
    second = await DefiHistoryStore(cast(Any, second_llama)).get_pool_history("pool-1")

    assert first == second
    assert second[-1]["tvlUsd"] == 1100
    assert llama.calls == 1
    assert second_llama.calls == 0


@pytest.mark.asyncio
async def test_evidence_store_uses_defi_analysis_ttl_for_writes():
    cache = RecordingCache()
    store = EvidenceStore(cache=cast(Any, cache))

    await store.save_protocol_docs("https://example.com", {"available": True})
    await store.save_pool_history("pool-1", [{"apy": 10.0}])

    assert cache.calls[0][2] == settings.defi_analysis_ttl_seconds
    assert cache.calls[1][2] == settings.defi_analysis_ttl_seconds


@pytest.mark.asyncio
async def test_evidence_store_ttl_override_survives_memory_fallback_default_ttl():
    cache = CacheLayer(redis_url=None, ttl=cast(Any, 0.05), max_memory_items=10)
    store = EvidenceStore(cache=cache)

    await store.save_protocol_docs("https://example.com", {"available": True})
    await asyncio.sleep(0.08)

    saved = await store.get_protocol_docs("https://example.com")

    assert saved is not None
    assert saved["available"] is True
