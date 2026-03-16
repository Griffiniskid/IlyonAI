"""Specialist AI routing for evidence-grounded DeFi explanations."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from src.ai.openai_client import OpenAIClient
from src.config import settings

logger = logging.getLogger(__name__)


class DefiAIRouter:
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

    async def build_market_brief(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        fallback = {
            "available": True,
            "headline": "Balanced risk-adjusted yield remains the default ranking lens.",
            "summary": "The discover surface ranks opportunities by balanced risk-adjusted yield with hard safety caps, so fragile high-APY setups do not dominate the board.",
            "market_regime": "balanced",
            "best_area": "Battle-tested protocols with durable fee-backed yield and clean exits.",
            "avoid_zone": "Emission-heavy or thin-liquidity setups with partial coverage.",
            "monitor_triggers": [
                "APY rising while TVL falls",
                "Utilization or exit depth moving into stress",
                "New protocol incident or governance intervention",
            ],
        }
        if not self._client:
            return fallback

        result = await self._ask_json(
            "You are a DeFi strategist. Use only the supplied evidence. Return valid JSON only.",
            "Return JSON with keys: headline, summary, market_regime, best_area, avoid_zone, monitor_triggers.\n"
            f"Snapshot:\n{json.dumps(payload, ensure_ascii=True)}",
        )
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
        fallback = {
            "available": True,
            "headline": "Protocol quality comes from battle-testing, governance posture, and dependency discipline.",
            "summary": "This protocol view weighs audits, incident history, docs observability, dependencies, and deployment breadth rather than treating TVL alone as safety.",
            "best_for": "Users doing protocol due diligence before deploying capital.",
            "main_risks": [
                "Audit presence does not eliminate implementation risk.",
                "Risk can differ across deployments even under one brand.",
                "Dependency complexity matters as much as base protocol quality.",
            ],
            "monitor_triggers": [
                "New exploit or emergency governance action",
                "Major upgrade with stale audits",
                "Liquidity concentrating into one weak deployment",
            ],
            "safer_alternative": "Prefer the deepest, best-documented deployment when several branded surfaces exist.",
        }
        return await self._build_entity_analysis("protocol", payload, fallback)

    async def build_opportunity_analysis(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        fallback = {
            "available": True,
            "headline": "A capital path only ranks well when safety, yield quality, exit quality, and confidence align.",
            "summary": "The opportunity view discounts nominal APY when emissions, weak exits, dependency depth, or low-quality assets undermine the surface yield.",
            "best_for": payload.get("summary", {}).get("strategy_fit", "balanced") + " capital",
            "why_it_exists": "Yield exists because some mix of fees, utilization, incentives, or structural imbalance is paying you to take risk.",
            "main_risks": [
                "Nominal APY can hide weak organic demand.",
                "Dependency chains can fail before the core protocol does.",
                "Exit depth can invalidate an otherwise appealing score.",
            ],
            "monitor_triggers": [
                "Fee-backed share or reserve health deteriorates",
                "Reward-token quality weakens",
                "Protocol incident or governance intervention appears",
            ],
            "safer_alternative": "Prefer a lower-yield setup with cleaner exits and stronger confidence when preservation matters more than upside.",
        }
        return await self._build_entity_analysis("opportunity", payload, fallback)

    async def _build_entity_analysis(self, kind: str, payload: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
        if not self._client:
            return fallback

        packet = json.dumps(payload, ensure_ascii=True)
        technical = await self._ask_json(
            "You are a strict DeFi technical risk analyst. Use only supplied evidence. Return JSON only.",
            f"Analyze the {kind} for technical and governance risk. Return JSON with keys: headline, main_risks, safer_alternative.\nEvidence:\n{packet}",
        )
        sustainability = await self._ask_json(
            "You are a strict DeFi yield sustainability analyst. Use only supplied evidence. Return JSON only.",
            f"Explain why the yield exists and who it suits. Return JSON with keys: summary, why_it_exists, best_for.\nEvidence:\n{packet}",
        )
        dependency = await self._ask_json(
            "You are a strict DeFi dependency and scenario analyst. Use only supplied evidence. Return JSON only.",
            f"Explain what breaks first and what to monitor. Return JSON with keys: main_risks, monitor_triggers.\nEvidence:\n{packet}",
        )
        judge = await self._ask_json(
            "You are a DeFi verifier. Reject unsupported claims. Use only supplied evidence and draft fields. Return JSON only.",
            "Return JSON with keys: headline, summary, best_for, why_it_exists, main_risks, monitor_triggers, safer_alternative.\n"
            f"Evidence:\n{packet}\nDraft technical:\n{json.dumps(technical, ensure_ascii=True)}\nDraft sustainability:\n{json.dumps(sustainability, ensure_ascii=True)}\nDraft dependency:\n{json.dumps(dependency, ensure_ascii=True)}",
        )
        if not judge:
            return fallback

        return {
            "available": True,
            "headline": judge.get("headline") or technical.get("headline") or fallback["headline"],
            "summary": judge.get("summary") or sustainability.get("summary") or fallback["summary"],
            "best_for": judge.get("best_for") or sustainability.get("best_for") or fallback.get("best_for", ""),
            "why_it_exists": judge.get("why_it_exists") or sustainability.get("why_it_exists") or fallback.get("why_it_exists"),
            "main_risks": judge.get("main_risks") or dependency.get("main_risks") or technical.get("main_risks") or fallback["main_risks"],
            "monitor_triggers": judge.get("monitor_triggers") or dependency.get("monitor_triggers") or fallback["monitor_triggers"],
            "safer_alternative": judge.get("safer_alternative") or technical.get("safer_alternative") or fallback["safer_alternative"],
        }

    async def _ask_json(self, system_prompt: str, message: str) -> Dict[str, Any]:
        if not self._client:
            return {}
        try:
            raw = await self._client.chat_json(message, system_prompt=system_prompt, max_tokens=900, temperature=0.1)
        except Exception as exc:
            logger.warning("DeFi AI pass failed: %s", exc)
            return {}
        return raw if isinstance(raw, dict) else {}

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
