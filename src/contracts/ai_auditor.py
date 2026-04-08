"""
AI-powered smart contract auditor.

Takes contract source/bytecode + static findings and runs them
through an AI model for deep semantic analysis and vulnerability explanation.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from src.config import settings

logger = logging.getLogger(__name__)

# AI audit system prompt
AUDIT_SYSTEM_PROMPT = """You are an expert Solidity and smart contract security auditor.
You will be given contract source code and/or static analysis findings.

Your job is to:
1. Identify genuine security vulnerabilities and their severity
2. Distinguish false positives from real issues
3. Assess the overall contract risk level
4. Provide clear, actionable recommendations

Severity levels:
- CRITICAL: Can result in immediate loss of funds (reentrancy, unauthorized minting, etc.)
- HIGH: Significant risk that requires owner action to exploit
- MEDIUM: Concerning patterns that users should be aware of
- LOW: Minor issues or best practice violations
- INFO: Informational findings, not directly exploitable

Return a JSON object with this exact structure:
{
  "risk_verdict": "SAFE|LOW|MEDIUM|HIGH|CRITICAL",
  "confidence": 0-100,
  "audit_summary": "2-3 sentence plain English summary",
  "key_findings": ["finding 1", "finding 2", ...],
  "false_positives": ["item that is NOT actually a risk and why"],
  "recommendations": ["specific action 1", "specific action 2", ...],
  "is_likely_scam": true/false,
  "scam_indicators": ["indicator if any"]
}"""


class AIContractAuditor:
    """
    Uses AI to perform deep semantic analysis of smart contracts.
    """

    def __init__(self):
        self._ai_client = None

    def _get_ai_client(self):
        """Lazy-initialize the AI client."""
        if self._ai_client is None:
            try:
                from src.ai.openai_client import OpenAIClient
                self._ai_client = OpenAIClient(model=settings.ai_model, use_openrouter=True)
            except Exception as e:
                logger.warning(f"AI client unavailable: {e}")
        return self._ai_client

    def _build_audit_prompt(
        self,
        address: str,
        chain: str,
        contract_name: Optional[str],
        source_code: str,
        static_findings: List[Dict[str, Any]],
        is_proxy: bool,
    ) -> str:
        """Build the audit prompt for the AI model."""
        parts = [
            f"## Contract Audit Request",
            f"**Address:** {address}",
            f"**Chain:** {chain}",
            f"**Name:** {contract_name or 'Unknown'}",
            f"**Is Proxy:** {is_proxy}",
            "",
        ]

        if static_findings:
            parts.append("## Static Analysis Findings")
            for f in static_findings[:30]:  # Cap at 30 findings
                parts.append(
                    f"- [{f.get('severity', '?').upper()}] {f.get('title', '')} "
                    f"(line {f.get('line_number', '?')}): {f.get('description', '')}"
                )
            parts.append("")

        if source_code:
            # Limit source code to 8000 chars for token budget
            truncated = source_code[:8000]
            if len(source_code) > 8000:
                truncated += "\n... [truncated]"
            parts.append("## Source Code")
            parts.append("```solidity")
            parts.append(truncated)
            parts.append("```")
        else:
            parts.append("## Source Code")
            parts.append("*Contract source not verified/available. Analysis based on bytecode only.*")

        return "\n".join(parts)

    async def audit(
        self,
        address: str,
        chain: str,
        contract_name: Optional[str],
        source_code: str,
        static_findings: List[Dict[str, Any]],
        is_proxy: bool = False,
    ) -> Dict[str, Any]:
        """
        Run AI audit on a contract.

        Returns dict with: risk_verdict, confidence, audit_summary,
        key_findings, recommendations, is_likely_scam
        """
        default_result = {
            "risk_verdict": "UNKNOWN",
            "confidence": 0,
            "audit_summary": "AI audit unavailable.",
            "key_findings": [],
            "false_positives": [],
            "recommendations": [],
            "is_likely_scam": False,
            "scam_indicators": [],
        }

        client = self._get_ai_client()
        if not client:
            return default_result

        prompt = self._build_audit_prompt(
            address, chain, contract_name, source_code, static_findings, is_proxy
        )

        try:
            import aiohttp
            api_url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.ai_model,
                "messages": [
                    {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 2000,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning(f"AI audit API error: {resp.status}")
                        return default_result
                    data = await resp.json()

            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)

            logger.info(
                f"AI audit complete for {address[:8]}: "
                f"verdict={result.get('risk_verdict')}, "
                f"confidence={result.get('confidence')}"
            )
            return result

        except Exception as e:
            logger.warning(f"AI audit failed: {e}")
            return default_result
