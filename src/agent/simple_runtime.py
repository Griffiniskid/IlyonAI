"""Simple agent runtime without ReAct - uses direct LLM calls with tool support."""
from __future__ import annotations

import json
import re
from typing import AsyncIterator

from src.agent.llm import IlyonChatModel
from src.agent.streaming import StreamCollector, encode_sse, frame_event_name
from src.api.schemas.agent import ThoughtFrame, ToolFrame, FinalFrame, DoneFrame, CardFrame


# Simple keyword-based intent detection.
# Priority order matters — explanatory intents must outrank allocation/staking keywords.
INTENT_PATTERNS = {
    "explain_sentinel_methodology": [
        r"how does .*sentinel.*work",
        r"how .*sentinel.*scor",
        r"sentinel.*scor.*work",
        r"explain .*sentinel",
        r"what is .*sentinel",
        r"what does .*sentinel",
        r"sentinel.*criterion",
        r"sentinel.*safety.*durability.*exit.*confidence",
    ],
    "allocate_plan": [
        r"allocate",
        r"distribute",
        r"diversif(?:y|ied|ication)",
        r"deploy\s+(?:\$?\d|\w+\s+into)",
        r"risk[- ]?weighted",
        r"portfolio\s+across",
        r"spread\s+.*\s+across",
        r"re[- ]?run\s+the\s+allocation",
        r"rebalance(?:\s+(?:now|this|the))?",
        r"conservative\s+risk\s+budget",
        r"low[- ]?risk\s+only",
        r"only\s+low[- ]?risk",
        r"maximize\s+(?:blended\s+)?apy",
        r"skip\s+pendle",
        r"skip\s+\w+\s+positions",
    ],
    "get_token_price": [
        r"price of (\w+)",
        r"(\w+) price",
        r"how much is (\w+)",
        r"cost of (\w+)",
        r"value of (\w+)",
    ],
    "get_staking_options": [
        r"staking",
        r"stake",
        r"yield",
        r"earning",
        r"pools",
        r"apy",
    ],
    "get_defi_market_overview": [
        r"market overview",
        r"market stats",
        r"trending",
        r"top tokens",
        r"market data",
    ],
    "get_defi_analytics": [
        r"analytics",
        r"analysis",
        r"analyze",
        r"protocol",
        r"compare",
    ],
    "simulate_swap": [
        r"swap",
        r"exchange",
        r"convert",
        r"trade",
    ],
    "get_wallet_balance": [
        r"portfolio",
        r"balance",
        r"holdings",
        r"wallet",
        r"assets",
    ],
    "find_liquidity_pool": [
        r"liquidity pool",
        r"lp pool",
        r"pool for",
        r"pairs",
    ],
    "search_dexscreener_pairs": [
        r"dex",
        r"search pair",
        r"trading pair",
    ],
}


CHAIN_PATTERNS = {
    "solana": [r"\bsolana\b", r"\bsol\b"],
    "ethereum": [r"\bethereum\b", r"\beth\b", r"\bmainnet\b"],
    "arbitrum": [r"\barbitrum\b", r"\barb\b"],
    "base": [r"\bbase\b"],
    "optimism": [r"\boptimism\b", r"\bop\b"],
    "polygon": [r"\bpolygon\b", r"\bmatic\b"],
    "bsc": [r"\bbsc\b", r"\bbnb\b", r"\bbnb chain\b"],
    "avalanche": [r"\bavalanche\b", r"\bavax\b"],
}

ASSET_HINT_PATTERN = re.compile(
    r"(?:i have|deploy|allocate|distribute|invest|put)\s+\$?([\d,]+(?:\.\d+)?)\s*([kKmM])?\s+([A-Za-z]{2,10})",
    re.IGNORECASE,
)


def _parse_amount(text: str) -> float:
    """Extract a USD amount from free text — supports $10k, 10,000, 10000 USDC, etc."""
    # $10k / $10K / $10,000
    m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?", text)
    if not m:
        return 10_000.0
    raw = m.group(1).replace(",", "")
    try:
        n = float(raw)
    except ValueError:
        return 10_000.0
    suffix = (m.group(2) or "").lower()
    if suffix == "k":
        n *= 1_000
    elif suffix == "m":
        n *= 1_000_000
    return n


def _parse_risk_budget(text: str) -> str:
    t = text.lower()
    if "conservative" in t or "low risk" in t or "safe" in t:
        return "conservative"
    if "aggressive" in t or "high yield" in t or "maximize" in t or "high risk" in t:
        return "aggressive"
    return "balanced"


def _parse_chains(text: str) -> list[str]:
    chains: list[str] = []
    lowered = text.lower()
    for chain, patterns in CHAIN_PATTERNS.items():
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns):
            chains.append(chain)
    return chains


def _parse_asset_hint(text: str) -> str | None:
    match = ASSET_HINT_PATTERN.search(text)
    if not match:
        return None
    symbol = match.group(3).upper()
    if symbol in CHAIN_PATTERNS:
        return None
    return symbol


def detect_intent(message: str) -> tuple[str, dict] | None:
    """Detect intent and extract parameters from user message."""
    message_lower = message.lower()

    for tool_name, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                # Extract token/asset name if present
                params = {}
                if tool_name == "explain_sentinel_methodology":
                    return tool_name, params
                if tool_name == "allocate_plan":
                    params["usd_amount"] = _parse_amount(message)
                    params["risk_budget"] = _parse_risk_budget(message)
                    chains = _parse_chains(message)
                    if chains:
                        params["chains"] = chains
                    asset_hint = _parse_asset_hint(message)
                    if asset_hint:
                        params["asset_hint"] = asset_hint
                    return tool_name, params
                if tool_name == "get_token_price" and match.groups():
                    params["token"] = match.group(1).upper()
                elif tool_name == "simulate_swap":
                    # Try to extract swap details
                    tokens = re.findall(r'(\w+)', message_lower)
                    if len(tokens) >= 2:
                        params["token_in"] = tokens[-2].upper()
                        params["token_out"] = tokens[-1].upper()
                    # Try to extract amount
                    amount_match = re.search(r'(\d+(?:\.\d+)?)', message)
                    if amount_match:
                        params["amount"] = amount_match.group(1)
                    params["chain"] = "ethereum"
                return tool_name, params
    
    return None


def _format_price_response(data: dict) -> str:
    """Format price data into natural language."""
    symbol = data.get("symbol", "Unknown")
    price = data.get("price_usd", "0")
    change = data.get("change_24h_pct", 0)
    chain = data.get("chain", "unknown")
    dex = data.get("dex", "unknown")
    liquidity = data.get("liquidity", 0)
    
    response = f"**{symbol} Price Update**\n\n"
    response += f"Current price: **${price}**\n"
    
    if change:
        direction = "up" if float(change) > 0 else "down"
        response += f"24h change: {direction} {abs(float(change)):.2f}%\n"
    
    if liquidity:
        response += f"Liquidity: ${float(liquidity):,.0f}\n"
    
    response += f"Source: {dex.title() if dex != 'unknown' else 'Multiple DEXs'} on {chain.title()}\n\n"
    response += "*Note: Prices are sourced from live DEX data and may vary across exchanges.*"
    
    return response


def _format_staking_response(data: dict) -> str:
    """Format staking data into natural language."""
    pools = data.get("staking_options", [])
    
    if not pools:
        return "I couldn't find any staking pools matching your criteria right now. Try adjusting your search or check back later."
    
    response = f"**Top Staking Opportunities** ({len(pools)} pools found)\n\n"
    
    for i, pool in enumerate(pools[:5], 1):
        protocol = pool.get("protocol", "Unknown")
        symbol = pool.get("symbol", "")
        apy = pool.get("apy", 0)
        tvl = pool.get("tvl_usd", 0)
        risk = pool.get("risk_level", "UNKNOWN")
        chain = pool.get("chain", "Unknown")
        
        response += f"{i}. **{protocol}** - {symbol}\n"
        response += f"   APY: {apy:.2f}% | TVL: ${tvl:,.0f} | Chain: {chain}\n"
        response += f"   Risk Level: {risk}\n\n"
    
    response += "*Remember: Higher APY often means higher risk. Always DYOR before investing.*"
    return response


def _format_market_response(data: dict) -> str:
    """Format market overview into natural language."""
    protocols = data.get("protocols", [])
    total_tvl = data.get("total_tvl", 0)
    
    if not protocols:
        return "Market data is temporarily unavailable. Please check back in a few minutes."
    
    response = "**DeFi Market Overview**\n\n"
    
    if total_tvl:
        response += f"Combined TVL of top protocols: **${total_tvl:,.0f}**\n\n"
    
    response += "**Top Protocols by TVL:**\n\n"
    
    for i, p in enumerate(protocols[:5], 1):
        name = p.get("name", "Unknown")
        tvl = p.get("tvl", 0)
        change_1d = p.get("change_1d", 0)
        category = p.get("category", "Unknown")
        
        response += f"{i}. **{name}** ({category})\n"
        response += f"   TVL: ${tvl:,.0f}"
        if change_1d:
            direction = "📈" if change_1d > 0 else "📉"
            response += f" | 24h: {direction} {abs(change_1d):.2f}%"
        response += "\n\n"
    
    return response


def _format_swap_response(data: dict) -> str:
    """Format swap data into natural language."""
    token_in = data.get("token_in", "")
    token_out = data.get("token_out", "")
    amount = data.get("amount_in", data.get("amount", "0"))
    estimated = data.get("estimated_out", "0")
    price = data.get("price_usd", 0)
    
    response = f"**Swap Estimate: {amount} {token_in} → {token_out}**\n\n"
    
    if estimated != "0":
        response += f"Estimated receive: **~{estimated} {token_out}**\n"
        if price:
            response += f"Rate: ~${price:.4f} per {token_in}\n"
    else:
        response += "Unable to calculate exact swap estimate without token addresses.\n\n"
        response += "To get a precise quote, please provide the token contract addresses or connect your wallet.\n"
    
    response += "\n*Note: This is an estimate. Actual amounts may vary due to slippage and market conditions.*"
    return response


def _format_allocate_response(data: dict) -> str:
    """Produce the demo-style intro paragraph for an allocate_plan result."""
    total_usd = data.get("total_usd", "$0")
    blended = data.get("blended_apy", "0%")
    weighted = data.get("weighted_sentinel", 0)
    positions = data.get("positions", []) or []
    chain_scope = data.get("chain_scope")
    market_brief = data.get("market_brief") or {}
    low = sum(1 for p in positions if (p.get("risk") == "low"))
    medium = sum(1 for p in positions if (p.get("risk") == "medium"))
    high = sum(1 for p in positions if (p.get("risk") == "high"))
    parts: list[str] = []
    parts.append(
        f"Here's a risk-weighted allocation across {len(positions)} top-rated positions"
        f"{f' on {chain_scope}' if chain_scope else ''}. "
        f"Weighted Sentinel score lands at **{weighted} / 100** with {low} Low-risk, "
        f"{medium} Medium, {high} High. Blended APY is ≈ **{blended}** net of gas."
    )
    if market_brief.get("summary"):
        parts.append(str(market_brief["summary"]))
    parts.append(
        "Below is the Sentinel scoring breakdown for each pool — this is the Ilyon safety lens "
        "layered on top of the allocation, so you can see *why* each position passed, not just its APY."
    )
    parts.append(
        f"Ready to execute? I'll prepare {len(positions)} transactions — "
        "you'll approve each one in your wallet; I never touch keys."
    )
    return "\n\n".join(parts)


def _format_sentinel_methodology_response() -> str:
    return (
        "**How Ilyon Sentinel actually scores DeFi opportunities**\n\n"
        "Sentinel is not an APY sorter. It scores each opportunity across four decision axes, then blends them into a deployability score.\n\n"
        "**1. Safety**\n"
        "Safety is built from protocol safety, asset quality, structure safety, dependency inheritance, governance/admin posture, and stress history. On the main DeFi pipeline this includes audits, incident history, docs coverage, oracle and bridge dependencies, wrapper risk, depeg drag, and historical drawdown behavior.\n\n"
        "**2. Yield Durability**\n"
        "Yield durability measures whether the carry is likely to persist. Sentinel looks at fee-backed share, APY persistence, reward-token quality, emissions dilution, reserve health, and real activity rather than trusting headline APY.\n\n"
        "**3. Exit Liquidity**\n"
        "Exit liquidity measures whether you can actually leave the position cleanly. Sentinel uses TVL depth, slippage realism, market fragmentation, utilization headroom, and withdrawal constraints.\n\n"
        "**4. Confidence**\n"
        "Confidence drops when coverage is incomplete. Missing docs, thin history, absent volume, or weak dependency evidence all reduce confidence and can cap otherwise attractive opportunities.\n\n"
        "**How scores combine**\n"
        "Sentinel first computes a product-specific quality score from Safety, Yield Durability, Exit Liquidity, and Confidence. For single-asset and lending-like products the quality blend is 46% Safety, 22% Yield Durability, 22% Exit Liquidity, and 10% Confidence. LP variants shift those weights based on product type. Then overall deployability blends quality with APR efficiency, so yield only helps if it survives risk haircuts.\n\n"
        "**Risk level and strategy fit**\n"
        "Risk level is derived from the safety deficit. Strategy fit is conservative only when safety is very strong and yield quality is still healthy; otherwise opportunities move into balanced or aggressive buckets.\n\n"
        "**What this means in practice**\n"
        "A pool with high APY but weak exits, poor docs, fragile incentives, or heavy dependency risk will not rank well. A lower-APY venue can outrank it if the carry is cleaner, the exit is deeper, and the evidence is stronger."
    )


def _format_tool_result(tool_name: str, result) -> str:
    """Format any tool result into natural language."""
    # Handle ToolEnvelope objects
    if hasattr(result, 'ok'):
        if not result.ok:
            error = result.error
            return f"I wasn't able to fetch that data right now. {error.message if error else 'Please try again later.'}"
        data = result.data if result.data else {}
        card_type = result.card_type if result.card_type else ""
    else:
        # Handle plain dict
        if not result.get("ok", False):
            error = result.get("error", {})
            return f"I wasn't able to fetch that data right now. {error.get('message', 'Please try again later.')}"
        data = result.get("data", {})
        card_type = result.get("card_type", "")
    
    if card_type == "allocation" or tool_name == "allocate_plan":
        return _format_allocate_response(data)
    if card_type == "token" or tool_name == "get_token_price":
        return _format_price_response(data)
    elif card_type == "stake" or tool_name == "get_staking_options":
        return _format_staking_response(data)
    elif card_type == "market_overview" or tool_name == "get_defi_market_overview":
        return _format_market_response(data)
    elif card_type == "swap_quote" or tool_name == "simulate_swap":
        return _format_swap_response(data)
    else:
        # Generic formatting
        return json.dumps(data, indent=2) if isinstance(data, dict) else str(data)


async def run_ephemeral_turn(
    *,
    router,
    tools,
    message: str,
    wallet: str | None = None,
) -> AsyncIterator[bytes]:
    """Execute one agent turn without DB persistence and yield SSE-encoded frames.
    
    Uses keyword-based intent detection for reliable tool calling.
    Formats tool results directly without LLM for consistent, fast responses.
    """
    llm = IlyonChatModel(router=router, model="default")
    collector = StreamCollector()
    started = __import__('time').monotonic()
    
    # Detect intent
    intent = detect_intent(message)

    try:
        final_content = ""
        
        # If we detected an intent, call the tool and format result directly
        if intent:
            tool_name, tool_input = intent

            if tool_name == "explain_sentinel_methodology":
                collector._step += 1
                collector._queue.append(ThoughtFrame(
                    step_index=collector._step,
                    content="Grounding the response in the live Sentinel scoring model..."
                ))
                collector._step += 1
                collector._queue.append(ThoughtFrame(
                    step_index=collector._step,
                    content="Summarizing Safety, Yield Durability, Exit Liquidity, Confidence, and weighting rules..."
                ))
                final_content = _format_sentinel_methodology_response()
                elapsed = int((__import__('time').monotonic() - started) * 1000)
                collector.emit_final(final_content, [])
                for frame in collector.drain():
                    yield encode_sse(frame_event_name(frame), frame.model_dump())
                return
            
            # Emit thought about tool usage
            collector._step += 1
            collector._queue.append(ThoughtFrame(
                step_index=collector._step,
                content=f'Fetching {tool_name.replace("_", " ")}...'
            ))
            
            # Find and execute tool
            tool_result = None
            for tool in tools:
                if tool.name == tool_name:
                    try:
                        tool_result = await tool.ainvoke(tool_input)
                        
                        # Emit tool frame
                        collector._queue.append(ToolFrame(
                            step_index=collector._step,
                            name=tool_name,
                            args=tool_input
                        ))
                    except Exception as e:
                        tool_result = {"ok": False, "error": {"message": str(e)}}
                    break
            
            # Format tool result directly (no LLM call for formatting)
            card_ids_for_final: list[str] = []
            if tool_result:
                from src.api.schemas.agent import ToolEnvelope
                env: ToolEnvelope | None = None
                if isinstance(tool_result, ToolEnvelope):
                    env = tool_result
                elif isinstance(tool_result, str):
                    try:
                        env = ToolEnvelope.model_validate_json(tool_result)
                    except Exception:
                        env = None
                if env is not None and env.ok:
                    for trace in (env.data.get("analysis_trace", []) if env.data else []):
                        collector._step += 1
                        collector._queue.append(ThoughtFrame(
                            step_index=collector._step,
                            content=str(trace),
                        ))
                    # Push primary card
                    if env.card_type and env.card_payload is not None:
                        collector._queue.append(CardFrame(
                            step_index=collector._step,
                            card_id=env.card_id,
                            card_type=env.card_type,
                            payload=env.card_payload,
                        ))
                        card_ids_for_final.append(env.card_id)
                    # Push extra cards (e.g. sentinel_matrix + execution_plan from allocate_plan)
                    for extra in env.extra_cards or []:
                        collector._queue.append(CardFrame(
                            step_index=collector._step,
                            card_id=extra.card_id,
                            card_type=extra.card_type,
                            payload=extra.payload,
                        ))
                        card_ids_for_final.append(extra.card_id)
                    final_content = _format_tool_result(tool_name, env)
                elif isinstance(tool_result, dict):
                    final_content = _format_tool_result(tool_name, tool_result)
                else:
                    final_content = str(tool_result)
            else:
                final_content = "I couldn't find the data you're looking for. Please try again or rephrase your question."
        else:
            # No intent detected, use LLM for general conversation
            system_msg = """You are Ilyon Sentinel's crypto agent. You help users with DeFi, token prices, swaps, and yield opportunities.

Respond directly to the user in a friendly, professional manner. Do NOT include meta-commentary or reasoning.

When discussing crypto assets, mention:
- Risk levels (LOW, MEDIUM, HIGH) based on market cap and volatility
- Strategy fit (conservative, balanced, aggressive)
- General safety tips"""
            
            result = await llm._agenerate([
                type('Msg', (), {'type': 'system', 'content': system_msg})(),
                type('Msg', (), {'type': 'human', 'content': message})()
            ])
            final_content = result.generations[0].message.content
        
        # Clean up response — skip the meta-commentary stripper for allocation
        # responses (the "Below is the Sentinel scoring breakdown…" paragraph
        # would otherwise be eaten by the "Below is/are" pattern).
        is_allocate = intent and intent[0] == "allocate_plan"
        if not is_allocate:
            final_content = _clean_response(final_content)
        
        # Emit final frame
        elapsed = int((__import__('time').monotonic() - started) * 1000)
        final_card_ids = locals().get("card_ids_for_final", []) or []
        collector.emit_final(final_content, final_card_ids)
        
        # Yield all frames
        for frame in collector.drain():
            yield encode_sse(frame_event_name(frame), frame.model_dump())
            
    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
        yield encode_sse("error", {"error": error_msg})


def _clean_response(content: str) -> str:
    """Clean up any JSON blocks, meta-commentary, or technical formatting from response."""
    # Remove JSON code blocks
    content = re.sub(r'```json\s*.*?\s*```', '', content, flags=re.DOTALL)
    content = re.sub(r'```\s*.*?\s*```', '', content, flags=re.DOTALL)
    
    # Remove standalone JSON objects
    content = re.sub(r'\{\s*"[^"]+":\s*"[^"]+"[^}]*\}', '', content)
    
    # Remove meta-commentary patterns
    meta_patterns = [
        r'^(Okay|OK|Alright|Sure|Well|So|Now|Let me|I\'ll|I will|I should|I need to|I think|I believe|I suppose|I guess)\b[^.]*\.\s*',
        r'^(The user is|User is|They are|This user)\b[^.]*\.\s*',
        r'^(Here is|Here are|Below is|Below are)\b[^.]*\.\s*',
        r'^(I\'m|I am)\s+(going to|about to|trying to|attempting to|working on)\b[^.]*\.\s*',
        r'^(First|Next|Then|Finally|Lastly)\b[^.]*\.\s*',
        r'^(Let me think|Let me analyze|Let me check|Let me look|Let me search)\b[^.]*\.\s*',
        r'^(I don\'t have|I do not have|I cannot|I can\'t)\b[^.]*\.\s*',
        r'^(In this case|In that case|For this|For that)\b[^.]*\.\s*',
    ]
    
    for pattern in meta_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.MULTILINE)
    
    # Remove "I" statements that are meta-commentary (not facts about data)
    content = re.sub(r'^I\s+(?:think|believe|suppose|guess|feel|would|could|might|should)\s+[^.]*\.\s*$', '', content, flags=re.MULTILINE | re.IGNORECASE)
    
    # Clean up multiple newlines and spaces
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r' {2,}', ' ', content)
    
    # Remove empty lines at start/end
    content = content.strip()
    
    return content
