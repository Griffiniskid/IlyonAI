"""Protocol docs and governance metadata extraction for DeFi intelligence."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

from src.data.scraper import WebsiteScraper
from src.defi.stores.evidence_store import EvidenceStore

logger = logging.getLogger(__name__)


def _keyword_hits(content: str, *terms: str) -> int:
    text = (content or "").lower()
    return sum(text.count(term.lower()) for term in terms)


class ProtocolDocsAnalyzer:
    def __init__(self, scraper: Optional[WebsiteScraper] = None, evidence_store: Optional[EvidenceStore] = None):
        self.scraper = scraper or WebsiteScraper(timeout=10, max_content_length=8000)
        self.evidence_store = evidence_store or EvidenceStore()
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    async def close(self):
        await self.scraper.close()

    async def analyze(self, url: Optional[str], docs_url: Optional[str] = None) -> Dict[str, Any]:
        target = docs_url or url
        if not target:
            return self._empty("No protocol URL available")

        now = time.time()
        cached = self._cache.get(target)
        if cached and (now - cached[0]) < 3600:
            return cached[1]

        stored = await self.evidence_store.get_protocol_docs(target)
        if stored is not None:
            self._cache[target] = (now, stored)
            return stored

        try:
            page = await self.scraper.scrape_website(target)
        except Exception as exc:
            logger.warning("Protocol docs scrape failed for %s: %s", target, exc)
            page = {"success": False, "error": str(exc), "content": "", "url": target}

        content = page.get("content") or ""
        governance_hits = _keyword_hits(content, "governance", "vote", "delegate", "proposal", "dao")
        timelock_hits = _keyword_hits(content, "timelock", "time lock", "delay")
        multisig_hits = _keyword_hits(content, "multisig", "multi-sig", "safe")
        admin_hits = _keyword_hits(content, "admin", "owner", "pause guardian", "guardian", "upgrade")
        oracle_hits = _keyword_hits(content, "oracle", "chainlink", "price feed", "twap")
        bridge_hits = _keyword_hits(content, "bridge", "cross-chain", "wrapped asset", "canonical")

        profile = {
            "available": bool(page.get("success") and page.get("has_content")),
            "url": page.get("url") or target,
            "title": page.get("title") or "",
            "description": page.get("description") or "",
            "load_time": page.get("load_time") or 0,
            "red_flags": page.get("red_flags") or [],
            "has_docs": bool(page.get("success") and page.get("has_content")),
            "has_governance_mentions": governance_hits > 0,
            "has_timelock_mentions": timelock_hits > 0,
            "has_multisig_mentions": multisig_hits > 0,
            "has_admin_mentions": admin_hits > 0,
            "has_oracle_mentions": oracle_hits > 0,
            "has_bridge_mentions": bridge_hits > 0,
            "governance_signal_count": governance_hits,
            "timelock_signal_count": timelock_hits,
            "multisig_signal_count": multisig_hits,
            "admin_signal_count": admin_hits,
            "oracle_signal_count": oracle_hits,
            "bridge_signal_count": bridge_hits,
            "trust_signals": {
                "has_privacy_policy": bool(page.get("has_privacy_policy")),
                "has_terms": bool(page.get("has_terms")),
                "has_audit_mention": bool(page.get("has_audit_mention")),
                "has_contact_info": bool(page.get("has_contact_info")),
                "has_github": bool(page.get("has_github")),
            },
            "observability_score": self._observability_score(page, governance_hits, timelock_hits, multisig_hits),
            "governance_score": self._governance_score(page, governance_hits, timelock_hits, multisig_hits, admin_hits),
            "freshness_hours": 0.0,
        }

        self._cache[target] = (now, profile)
        await self.evidence_store.save_protocol_docs(target, profile)
        return profile

    def _observability_score(self, page: Dict[str, Any], governance_hits: int, timelock_hits: int, multisig_hits: int) -> int:
        score = 38
        if page.get("success"):
            score += 12
        if page.get("has_content"):
            score += 16
        if page.get("has_audit_mention"):
            score += 8
        if governance_hits > 0:
            score += 8
        if timelock_hits > 0 or multisig_hits > 0:
            score += 8
        if page.get("red_flags"):
            score -= min(12, len(page.get("red_flags") or []) * 3)
        return max(0, min(100, score))

    def _governance_score(self, page: Dict[str, Any], governance_hits: int, timelock_hits: int, multisig_hits: int, admin_hits: int) -> int:
        score = 52
        if governance_hits > 0:
            score += 10
        if timelock_hits > 0:
            score += 12
        if multisig_hits > 0:
            score += 8
        if admin_hits > 4 and timelock_hits == 0:
            score -= 18
        if not page.get("success"):
            score -= 12
        return max(0, min(100, score))

    def _empty(self, reason: str) -> Dict[str, Any]:
        return {
            "available": False,
            "url": None,
            "title": "",
            "description": "",
            "load_time": 0,
            "red_flags": [reason],
            "has_docs": False,
            "has_governance_mentions": False,
            "has_timelock_mentions": False,
            "has_multisig_mentions": False,
            "has_admin_mentions": False,
            "has_oracle_mentions": False,
            "has_bridge_mentions": False,
            "governance_signal_count": 0,
            "timelock_signal_count": 0,
            "multisig_signal_count": 0,
            "admin_signal_count": 0,
            "oracle_signal_count": 0,
            "bridge_signal_count": 0,
            "trust_signals": {
                "has_privacy_policy": False,
                "has_terms": False,
                "has_audit_mention": False,
                "has_contact_info": False,
                "has_github": False,
            },
            "observability_score": 25,
            "governance_score": 35,
            "freshness_hours": None,
        }
