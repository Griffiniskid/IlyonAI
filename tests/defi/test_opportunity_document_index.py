import pytest

from src.defi.docs_analyzer import ProtocolDocsAnalyzer
from src.defi.history_store import DefiHistoryStore
from src.defi.stores.evidence_store import EvidenceStore


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


@pytest.mark.asyncio
async def test_docs_analyzer_reads_and_writes_via_evidence_store():
    scraper = StubScraper()
    store = EvidenceStore()
    analyzer = ProtocolDocsAnalyzer(scraper=scraper, evidence_store=store)

    first = await analyzer.analyze("https://example.com")
    second = await analyzer.analyze("https://example.com")

    assert first["url"] == "https://example.com"
    assert second["governance_signal_count"] == first["governance_signal_count"]
    assert scraper.calls == 1


@pytest.mark.asyncio
async def test_history_store_reads_and_writes_via_evidence_store():
    llama = StubLlama()
    store = EvidenceStore()
    history_store = DefiHistoryStore(llama, evidence_store=store)

    first = await history_store.get_pool_history("pool-1")
    second = await history_store.get_pool_history("pool-1")

    assert first == second
    assert second[-1]["tvlUsd"] == 1100
    assert llama.calls == 1
