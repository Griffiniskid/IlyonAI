"""
AI explainability helpers for advanced DeFi analysis.

This module keeps AI use evidence-bound and optional. Numeric scoring stays
deterministic in the risk engine; AI only synthesizes the evidence packet into
human-readable guidance.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.ai.openai_client import OpenAIClient
from src.config import settings

logger = logging.getLogger(__name__)


class DefiAIExplainer:
    """Optional AI explainer for protocol and opportunity detail views."""

    def __init__(self):
        self._client: Optional[OpenAIClient] = None

        if settings.openrouter_api_key:
            self._client = OpenAIClient(model=settings.ai_model, use_openrouter=True)

    @property
    def available(self) -> bool:
        return self._client is not None

    async def close(self):
        if self._client:
            await self._client.close()

    def _extract_json(self, raw_text: str) -> Dict[str, Any]:
        text = (raw_text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()

        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except Exception:
                    return {}
        return {}

    def _fallback_market_brief(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        top = (payload.get("top_opportunities") or [])[:3]
        if top:
            lead = top[0]
            summary = (
                f"Current flow favors {lead.get('kind', 'defi')} opportunities on "
                f"{lead.get('chain', 'top chains')} led by {lead.get('protocol_name', lead.get('protocol', 'known protocols'))}."
            )
        else:
            summary = "Coverage is available, but no strong DeFi opportunities passed the active filters."

        return {
            "available": False,
            "headline": "Deterministic market brief",
            "summary": summary,
            "market_regime": "mixed",
            "best_area": top[0].get("title") if top else "No standout setup",
            "avoid_zone": "Thin-liquidity, emission-heavy opportunities with low confidence.",
            "monitor_triggers": [
                "APY drifting materially above fee-backed yield",
                "TVL deterioration with no offsetting volume growth",
                "Utilization spikes or incident headlines on key protocols",
            ],
        }

    def _fallback_protocol(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        score = int(payload.get("summary", {}).get("safety_score") or 0)
        opportunity = int(payload.get("summary", {}).get("opportunity_score") or 0)
        risk_label = payload.get("summary", {}).get("risk_level") or "MEDIUM"
        return {
            "available": False,
            "headline": "Evidence-backed protocol brief",
            "summary": (
                f"This protocol screens as {risk_label.lower()} risk with safety {score}/100 and "
                f"capital attractiveness {opportunity}/100 based on audits, incidents, market depth, and deployment quality."
            ),
            "best_for": "Users comparing protocol quality before deploying capital.",
            "main_risks": [
                "Audit presence does not remove implementation or dependency risk.",
                "Protocol safety can diverge by chain deployment and market composition.",
                "Operational confidence drops quickly when coverage is partial or stale.",
            ],
            "monitor_triggers": [
                "New incident, emergency governance action, or pause event",
                "Audit freshness falling behind major upgrades",
                "Rapid TVL outflows across core markets",
            ],
            "safer_alternative": "Prefer battle-tested deployments with stronger confidence and lower dependency complexity.",
        }

    def _fallback_opportunity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        summary = payload.get("summary", {})
        return {
            "available": False,
            "headline": "Evidence-backed opportunity brief",
            "summary": (
                f"This setup scores {int(summary.get('opportunity_score') or 0)}/100 on a risk-adjusted basis, "
                f"with safety {int(summary.get('safety_score') or 0)}/100 and confidence {int(summary.get('confidence_score') or 0)}/100."
            ),
            "best_for": summary.get("strategy_fit", "balanced capital") + " capital",
            "why_it_exists": "Yield is only attractive when fee-backed economics, exit depth, and protocol quality align.",
            "main_risks": [
                "Nominal APY can overstate durable yield when incentives dominate.",
                "Exit quality matters as much as entry quality for real capital deployment.",
                "Underlying asset or dependency risk can impair an otherwise clean surface APY.",
            ],
            "monitor_triggers": [
                "Fee-backed yield ratio deteriorates",
                "Liquidity or utilization moves into stress territory",
                "Reward-token quality deteriorates or incidents appear around the protocol",
            ],
            "safer_alternative": "Prefer a lower-yield setup with stronger safety, exit quality, and confidence if capital preservation matters more.",
        }

    async def _ask_json(self, system_prompt: str, message: str) -> Dict[str, Any]:
        if not self._client:
            return {}

        try:
            response = await self._client.chat_json(message, system_prompt=system_prompt, max_tokens=900, temperature=0.1)
            return response if isinstance(response, dict) else {}
        except Exception as exc:
            logger.warning("DeFi AI explanation failed: %s", exc)
            return {}

    async def build_market_brief(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        fallback = self._fallback_market_brief(payload)
        if not self._client:
            return fallback

        system_prompt = (
            "You are a DeFi strategist. Never invent facts. Use only the supplied evidence. "
            "Return valid JSON only. Be concise and grounded."
        )
        message = (
            "Create a market brief from this DeFi analyzer snapshot. Focus on current regime, best area, avoid zone, and watchpoints.\n"
            "Return JSON with keys: headline, summary, market_regime, best_area, avoid_zone, monitor_triggers.\n\n"
            f"Snapshot:\n{json.dumps(payload, ensure_ascii=True)}"
        )
        result = await self._ask_json(system_prompt, message)
        if not result:
            return fallback

        return {
            "available": True,
            "headline": result.get("headline") or fallback["headline"],
            "summary": result.get("summary") or fallback["summary"],
            "market_regime": result.get("market_regime") or fallback["market_regime"],
            "best_area": result.get("best_area") or fallback["best_area"],
            "avoid_zone": result.get("avoid_zone") or fallback["avoid_zone"],
            "monitor_triggers": result.get("monitor_triggers") or fallback["monitor_triggers"],
        }

    async def build_protocol_analysis(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        fallback = self._fallback_protocol(payload)
        if not self._client:
            return fallback

        system_prompt = (
            "You are a strict DeFi protocol analyst. Use only the supplied evidence. "
            "Do not overstate audit quality. Distinguish protocol safety from opportunity quality. Return valid JSON only."
        )
        message = (
            "Analyze this DeFi protocol profile.\n"
            "Return JSON with keys: headline, summary, best_for, main_risks, monitor_triggers, safer_alternative.\n\n"
            f"Protocol Profile:\n{json.dumps(payload, ensure_ascii=True)}"
        )
        result = await self._ask_json(system_prompt, message)
        if not result:
            return fallback

        return {
            "available": True,
            "headline": result.get("headline") or fallback["headline"],
            "summary": result.get("summary") or fallback["summary"],
            "best_for": result.get("best_for") or fallback["best_for"],
            "main_risks": result.get("main_risks") or fallback["main_risks"],
            "monitor_triggers": result.get("monitor_triggers") or fallback["monitor_triggers"],
            "safer_alternative": result.get("safer_alternative") or fallback["safer_alternative"],
        }

    async def build_opportunity_analysis(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        fallback = self._fallback_opportunity(payload)
        if not self._client:
            return fallback

        system_prompt = (
            "You are a strict DeFi opportunity analyst. Explain why a setup is attractive or fragile. "
            "Use only supplied evidence and return valid JSON only."
        )
        message = (
            "Analyze this DeFi opportunity profile.\n"
            "Return JSON with keys: headline, summary, best_for, why_it_exists, main_risks, monitor_triggers, safer_alternative.\n\n"
            f"Opportunity Profile:\n{json.dumps(payload, ensure_ascii=True)}"
        )
        result = await self._ask_json(system_prompt, message)
        if not result:
            return fallback

        return {
            "available": True,
            "headline": result.get("headline") or fallback["headline"],
            "summary": result.get("summary") or fallback["summary"],
            "best_for": result.get("best_for") or fallback["best_for"],
            "why_it_exists": result.get("why_it_exists") or fallback["why_it_exists"],
            "main_risks": result.get("main_risks") or fallback["main_risks"],
            "monitor_triggers": result.get("monitor_triggers") or fallback["monitor_triggers"],
            "safer_alternative": result.get("safer_alternative") or fallback["safer_alternative"],
        }
