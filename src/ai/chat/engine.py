"""
AI Chat Engine for Ilyon AI.

Handles multi-turn conversations with tool-use (function calling).
Uses OpenRouter/OpenAI-compatible API with agentic loop:
  1. Send user message + history + tool schemas to model
  2. If model returns tool_calls, execute them and feed results back
  3. Repeat until model returns a plain text response (no more tool_calls)

The AI ONLY reads and analyzes data — it never executes transactions.
"""

import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

from src.config import settings
from src.ai.chat.memory import ChatMessage, ConversationMemory, Session
from src.ai.chat.tools import TOOL_SCHEMAS, dispatch_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Ilyon AI, an elite multi-chain DeFi intelligence assistant.

Your capabilities:
- Token security analysis (Solana + all major EVM chains)
- Smart contract vulnerability scanning
- Wallet approval management (identify risky token approvals)
- DeFi pool and yield opportunity research
- REKT incident database (DeFi hacks and exploits)
- Protocol TVL and risk analysis

Your principles:
1. PROTECTION FIRST: Always warn about real risks clearly and directly.
2. ACCURACY: Use tools to fetch real data — never invent token data or prices.
3. NO EXECUTION: You can analyze and advise, but you NEVER execute transactions or move funds.
4. CONCISENESS: Give clear, actionable answers. Lead with the most important finding.
5. CONTEXT AWARENESS: When a user asks about a token, contract, or wallet, use the appropriate tool automatically.
6. GROUNDED FACTS ONLY: For token safety, exploits, audits, approvals, TVL, pools, APY, or protocol history, you must rely on tool data.

When the user provides a token address, contract address, or wallet address, proactively call the relevant tool.
When discussing DeFi yields or pools, fetch real data to back your answer.
If tools return no verified data, say that clearly. Absence of a match is not proof that something never happened.
Format numbers clearly: use $X.XM for millions, $X.XK for thousands.
"""

# Max tool-call rounds per turn to prevent infinite loops
MAX_TOOL_ROUNDS = 5

CHAIN_ALIASES = {
    "sol": "solana",
    "solana": "solana",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "base": "base",
    "arb": "arbitrum",
    "arbitrum": "arbitrum",
    "bsc": "bsc",
    "bnb": "bsc",
    "polygon": "polygon",
    "matic": "polygon",
    "optimism": "optimism",
    "op": "optimism",
    "avalanche": "avalanche",
    "avax": "avalanche",
}

HACK_KEYWORDS = {"hack", "hacked", "exploit", "exploited", "rekt", "incident", "breach", "drain", "drained"}
AUDIT_KEYWORDS = {"audit", "audited", "auditor", "security review"}
DEFI_KEYWORDS = {"yield", "yields", "apy", "pool", "pools", "farm", "farming", "lending", "borrow", "supply", "tvl", "protocol"}
WALLET_KEYWORDS = {"approval", "approvals", "allowance", "allowances", "spender", "revoke"}
CONTRACT_KEYWORDS = {"contract", "code", "proxy", "implementation", "vulnerability", "vulnerabilities", "reentrancy", "backdoor", "scan"}
GENERIC_FOCUS_WORDS = {
    "what", "which", "when", "where", "why", "how", "is", "are", "was", "were", "has", "have", "had",
    "the", "this", "that", "these", "those", "token", "tokens", "protocol", "protocols", "safe", "safer",
    "safest", "risk", "risky", "security", "history", "best", "top", "show", "find", "list", "check",
    "compare", "vs", "for", "with", "from", "into", "about", "on", "in", "at", "to", "of", "and",
    "or", "a", "an", "today", "now", "current", "latest", "uses", "use", "using", "rates", "rate",
    "yield", "yields", "apy", "pool", "pools", "farm", "farming", "lending", "borrow", "supply", "tvl",
    "hack", "hacked", "exploit", "exploited", "rekt", "incident", "incidents", "audit", "audited", "wallet",
    "approvals", "approval", "allowance", "allowances", "contract", "code", "scan", "new", "old", "ever",
    "been", "did", "does", "do", "can", "could", "should", "would", "tell", "me"
}

EVM_ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
SOLANA_ADDRESS_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


class ChatEngine:
    """
    Agentic chat engine with tool-use support.

    One instance is shared across all sessions.
    """

    def __init__(self):
        self.memory = ConversationMemory()
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._base_url = "https://openrouter.ai/api/v1/chat/completions"
        self._api_key = settings.openrouter_api_key or settings.openai_api_key or ""
        self._model = getattr(settings, "ai_model", None) or getattr(settings, "openai_model", "gpt-4o-mini")

    async def _session(self) -> aiohttp.ClientSession:
        if not self._http_session or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120)
            )
        return self._http_session

    # ------------------------------------------------------------------
    # Core agentic loop
    # ------------------------------------------------------------------

    async def _call_model(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        tool_choice: Any = "auto",
    ) -> Dict[str, Any]:
        """
        Call the LLM with the current message list and tool schemas.
        Returns the raw API response dict.
        """
        session = await self._session()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ilyon.ai",
            "X-Title": "Ilyon AI",
        }
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": tool_choice,
            "temperature": 0.4,
            "max_tokens": 1500,
        }
        if stream:
            payload["stream"] = True

        async with session.post(self._base_url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                err = await resp.text()
                raise RuntimeError(f"LLM API error {resp.status}: {err[:300]}")
            return await resp.json()

    def _extract_chain(self, message: str) -> Optional[str]:
        lowered = message.lower()
        for alias, chain in CHAIN_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                return chain
        return None

    def _extract_focus_term(self, message: str) -> Optional[str]:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{1,20}", message)
        for token in tokens:
            lowered = token.lower()
            if lowered in CHAIN_ALIASES or lowered in GENERIC_FOCUS_WORDS:
                continue
            return token
        return None

    def _build_grounding_plan(self, message: str) -> List[Dict[str, Any]]:
        lowered = message.lower()
        chain = self._extract_chain(message)
        focus = self._extract_focus_term(message)
        evm_addresses = EVM_ADDRESS_RE.findall(message)
        solana_addresses = SOLANA_ADDRESS_RE.findall(message)
        plan: List[Dict[str, Any]] = []

        if evm_addresses and any(keyword in lowered for keyword in WALLET_KEYWORDS):
            args: Dict[str, Any] = {"wallet": evm_addresses[0]}
            if chain:
                args["chain"] = chain
            plan.append({"tool": "scan_wallet_approvals", "args": args})
            return plan

        if evm_addresses and any(keyword in lowered for keyword in CONTRACT_KEYWORDS):
            plan.append({
                "tool": "scan_contract",
                "args": {"address": evm_addresses[0], "chain": chain or "ethereum"},
            })
            if any(keyword in lowered for keyword in AUDIT_KEYWORDS) and focus:
                plan.append({"tool": "search_audits", "args": {"protocol": focus, "chain": chain, "limit": 5}})
            return self._dedupe_plan(plan)

        if evm_addresses or solana_addresses:
            address = evm_addresses[0] if evm_addresses else solana_addresses[0]
            args = {"address": address}
            if chain:
                args["chain"] = chain
            plan.append({"tool": "analyze_token", "args": args})

        if any(keyword in lowered for keyword in HACK_KEYWORDS):
            args = {"limit": 5}
            if focus:
                args["search"] = focus
            if chain:
                args["chain"] = chain
            if "flash loan" in lowered:
                args["attack_type"] = "Flash Loan"
            plan.append({"tool": "search_rekt_incidents", "args": args})

        if any(keyword in lowered for keyword in AUDIT_KEYWORDS):
            args = {"limit": 5}
            if focus:
                args["protocol"] = focus
            if chain:
                args["chain"] = chain
            plan.append({"tool": "search_audits", "args": args})

        if any(keyword in lowered for keyword in DEFI_KEYWORDS):
            args = {"limit": 6}
            if focus:
                args["query"] = focus
            if chain:
                args["chain"] = chain
            plan.append({"tool": "analyze_defi", "args": args})

        return self._dedupe_plan(plan)

    def _dedupe_plan(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped: List[Dict[str, Any]] = []
        for item in plan:
            signature = self._tool_signature(item["tool"], item.get("args", {}))
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(item)
        return deduped

    def _tool_signature(self, tool_name: str, args: Dict[str, Any]) -> str:
        return f"{tool_name}:{json.dumps(args, sort_keys=True, default=str)}"

    def _tool_failed(self, tool_result: str) -> bool:
        try:
            payload = json.loads(tool_result)
        except json.JSONDecodeError:
            return False
        return isinstance(payload, dict) and bool(payload.get("error"))

    async def _execute_planned_tool(
        self,
        messages: List[Dict[str, Any]],
        tool_calls_made: List[Dict[str, Any]],
        seen_tool_calls: set,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> bool:
        tool_call_id = str(uuid.uuid4())
        signature = self._tool_signature(tool_name, tool_args)
        seen_tool_calls.add(signature)
        tool_result = await dispatch_tool(tool_name, tool_args)

        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_args),
                },
            }],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": tool_result,
        })
        tool_calls_made.append({
            "tool": tool_name,
            "args": tool_args,
            "result_preview": tool_result[:200],
        })
        return not self._tool_failed(tool_result)

    async def chat(
        self,
        session_id: str,
        user_message: str,
    ) -> Dict[str, Any]:
        """
        Process one user message and return the assistant's reply.

        Returns:
        {
            "session_id": str,
            "reply": str,
            "tool_calls_made": [ {"tool": str, "args": dict, "result_summary": str} ],
            "tokens_used": int,
            "latency_ms": int,
        }
        """
        start = time.time()
        sess: Session = self.memory.get_or_create(session_id)

        # Add user message to history
        user_msg = ChatMessage(role="user", content=user_message)
        sess.add(user_msg)

        # Build message list for model: system + history
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *sess.to_openai_messages()[:-1],   # history excluding the just-added user msg
            {"role": "user", "content": user_message},
        ]

        tool_calls_made: List[Dict[str, Any]] = []
        tokens_used = 0
        reply_text = ""
        successful_tool_calls = 0
        seen_tool_calls: set = set()

        grounding_plan = self._build_grounding_plan(user_message)
        grounding_needed = bool(grounding_plan)

        for planned in grounding_plan:
            ok = await self._execute_planned_tool(
                messages=messages,
                tool_calls_made=tool_calls_made,
                seen_tool_calls=seen_tool_calls,
                tool_name=planned["tool"],
                tool_args=planned.get("args", {}),
            )
            if ok:
                successful_tool_calls += 1

        if grounding_needed and successful_tool_calls == 0:
            reply_text = "I couldn't verify that with live data right now, so I don't want to guess. Try again in a moment or give me a specific token, protocol, or chain to check."

        # Agentic loop
        for _round in range(MAX_TOOL_ROUNDS):
            if reply_text:
                break
            try:
                tool_choice: Any = "required" if grounding_needed and successful_tool_calls == 0 else "auto"
                response = await self._call_model(messages, tool_choice=tool_choice)
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                reply_text = "I'm having trouble connecting to the AI backend right now. Please try again in a moment."
                break

            usage = response.get("usage", {})
            tokens_used += usage.get("total_tokens", 0)

            choice = (response.get("choices") or [{}])[0]
            finish_reason = choice.get("finish_reason", "stop")
            msg = choice.get("message", {})
            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                reply_text = content or (
                    "I couldn't produce a grounded answer from the verified data I collected. Try asking about one token, protocol, or chain at a time."
                )
                break

            # Model wants to call tools
            # Add assistant message with tool_calls to the thread
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

            # Execute each tool call
            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                tool_args_raw = tc.get("function", {}).get("arguments", "{}")
                tool_call_id = tc.get("id", str(uuid.uuid4()))

                try:
                    tool_args = json.loads(tool_args_raw)
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(f"[Chat {session_id}] Calling tool: {tool_name}({tool_args})")
                signature = self._tool_signature(tool_name, tool_args)
                if signature in seen_tool_calls:
                    tool_result = json.dumps({
                        "error": "duplicate_tool_call",
                        "message": "This tool with the same arguments was already executed. Use the existing result to answer.",
                    })
                else:
                    seen_tool_calls.add(signature)
                    tool_result = await dispatch_tool(tool_name, tool_args)
                    if not self._tool_failed(tool_result):
                        successful_tool_calls += 1

                # Append tool result to thread
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": tool_result,
                })

                tool_calls_made.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result_preview": tool_result[:200],
                })

            # Continue loop — model will now synthesize tool results
        else:
            # Exceeded max rounds
            if not reply_text:
                reply_text = "I verified some data but couldn't finish a clean grounded answer. Ask me about one token, protocol, or incident at a time."

        # Save assistant reply to memory
        if reply_text:
            sess.add(ChatMessage(role="assistant", content=reply_text))

        latency_ms = int((time.time() - start) * 1000)

        return {
            "session_id": session_id,
            "reply": reply_text,
            "tool_calls_made": tool_calls_made,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
        }

    async def get_history(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return session history, or None if session doesn't exist."""
        sess = self.memory.get(session_id)
        if sess is None:
            return None
        return sess.to_dict()

    def new_session_id(self) -> str:
        return str(uuid.uuid4())

    async def close(self):
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
