"""
Tool definitions for the AI chat agent.

Each tool is declared in OpenAI function-calling format and has a
corresponding async handler. The engine calls these when the model
decides to use a tool, then feeds results back into the conversation.

IMPORTANT: Tools only retrieve and analyze data. They never execute
any on-chain transaction.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# OpenAI-compatible tool schemas
# -----------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "analyze_token",
            "description": (
                "Analyze a token for security risks, rug pull probability, "
                "market data, and AI verdict. Works for Solana (base58) and "
                "all major EVM chains (0x address). Optionally specify chain."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Token contract address (Solana base58 or EVM 0x hex)",
                    },
                    "chain": {
                        "type": "string",
                        "description": "Chain name: solana, ethereum, base, arbitrum, bsc, polygon, optimism, avalanche. Auto-detected if omitted.",
                    },
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_contract",
            "description": (
                "Scan an EVM smart contract for vulnerabilities: reentrancy, "
                "owner backdoors, honeypot patterns, proxy risks, etc. "
                "Returns static analysis + AI audit verdict."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "EVM contract address (0x...)"},
                    "chain": {"type": "string", "description": "Chain: ethereum, base, arbitrum, bsc, polygon, optimism, avalanche"},
                },
                "required": ["address", "chain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_wallet_approvals",
            "description": (
                "Scan an EVM wallet's token approvals across all chains "
                "and identify risky allowances (unlimited or to unknown contracts). "
                "Returns scored approval list with revoke recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet": {"type": "string", "description": "EVM wallet address (0x...)"},
                    "chain": {"type": "string", "description": "Restrict to one chain (optional). Scans all EVM chains if omitted."},
                },
                "required": ["wallet"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_defi_pools",
            "description": (
                "Fetch top DeFi liquidity pools filtered by chain, protocol, TVL, and APY. "
                "Returns risk-scored pool data from DefiLlama."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chain": {"type": "string", "description": "Chain filter (ethereum, base, arbitrum, etc.)"},
                    "protocol": {"type": "string", "description": "Protocol filter (uniswap-v3, aave-v3, etc.)"},
                    "min_tvl": {"type": "number", "description": "Minimum TVL in USD (default 100000)"},
                    "min_apy": {"type": "number", "description": "Minimum APY %"},
                    "max_apy": {"type": "number", "description": "Maximum APY % (cap extreme farms)"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_yield_opportunities",
            "description": (
                "Fetch yield farming opportunities with sustainability analysis. "
                "Classifies APY as stable/moderate/high/extreme and checks "
                "what fraction comes from real fees vs token emissions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chain": {"type": "string"},
                    "exposure": {
                        "type": "string",
                        "enum": ["stable-stable", "crypto-stable", "crypto-crypto"],
                        "description": "Pool exposure type filter",
                    },
                    "min_apy": {"type": "number"},
                    "max_apy": {"type": "number"},
                    "min_tvl": {"type": "number"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_defi",
            "description": (
                "Run the DeFi analyzer workflow for a protocol, asset, or chain. "
                "Returns grounded pool, yield, lending, and protocol matches with risk highlights."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Protocol or asset to analyze, e.g. curve, aave, usdc, eth"},
                    "chain": {"type": "string", "description": "Optional chain filter"},
                    "min_tvl": {"type": "number", "description": "Minimum TVL in USD"},
                    "min_apy": {"type": "number", "description": "Minimum APY percentage"},
                    "limit": {"type": "integer", "description": "Max result groups to return"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_rekt_incidents",
            "description": (
                "Search the REKT database for DeFi hacks, exploits, and rug pulls. "
                "Filter by chain, attack type, or keyword. Returns incident amount, "
                "attack vector, and post-mortem links."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Keyword search (protocol name, attack type, etc.)"},
                    "chain": {"type": "string"},
                    "attack_type": {"type": "string", "description": "e.g. Flash Loan, Rug Pull, Oracle Manipulation"},
                    "min_amount": {"type": "number", "description": "Minimum amount stolen in USD"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_audits",
            "description": (
                "Search protocol audit history by protocol, auditor, or chain. "
                "Use this for questions about whether a protocol has been audited and by whom."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "protocol": {"type": "string", "description": "Protocol name filter, e.g. Curve, Aave, Compound"},
                    "auditor": {"type": "string", "description": "Audit firm filter"},
                    "chain": {"type": "string", "description": "Chain filter"},
                    "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_protocol_info",
            "description": (
                "Get TVL, chain breakdown, and metadata for a specific DeFi protocol "
                "by its DefiLlama slug (e.g. 'uniswap', 'aave', 'curve-dex')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "DefiLlama protocol slug"},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_intel_stats",
            "description": "Get aggregate DeFi security statistics: total funds stolen, top attack vectors, most-hit chains.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# -----------------------------------------------------------------------
# Tool handlers
# -----------------------------------------------------------------------

async def handle_analyze_token(args: Dict[str, Any]) -> str:
    """Call the token analyzer and return a compact JSON summary."""
    import aiohttp
    address = args.get("address", "")
    chain = args.get("chain", "")

    params: Dict[str, str] = {}
    if chain:
        params["chain"] = chain

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(
                "http://localhost:8080/api/v1/analyze",
                json={"address": address, "chain": chain or None},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    scores = data.get("scores", {})
                    ai = data.get("ai", {})
                    token = data.get("token", {})
                    market = data.get("market", {})
                    security = data.get("security", {})
                    # Return condensed summary for the AI
                    return json.dumps({
                        "address": address,
                        "name": token.get("name"),
                        "symbol": token.get("symbol"),
                        "chain": token.get("chain"),
                        "score": scores.get("overall"),
                        "grade": scores.get("grade"),
                        "verdict": ai.get("verdict"),
                        "rug_probability": ai.get("rug_probability"),
                        "price_usd": market.get("price_usd"),
                        "market_cap": market.get("market_cap"),
                        "liquidity_usd": market.get("liquidity_usd"),
                        "security": {
                            "liquidity_lock_status": security.get("liquidity_lock_status"),
                            "liquidity_locked": security.get("liquidity_locked"),
                            "lp_lock_percent": security.get("lp_lock_percent"),
                            "liquidity_lock_note": security.get("liquidity_lock_note"),
                            "can_mint": security.get("can_mint"),
                            "can_blacklist": security.get("can_blacklist"),
                            "can_pause": security.get("can_pause"),
                            "is_upgradeable": security.get("is_upgradeable"),
                            "is_renounced": security.get("is_renounced"),
                            "honeypot_status": security.get("honeypot_status"),
                            "buy_tax": security.get("buy_tax"),
                            "sell_tax": security.get("sell_tax"),
                        },
                        "ai_summary": ai.get("summary"),
                        "ai_recommendation": ai.get("recommendation"),
                        "red_flags": ai.get("red_flags", [])[:5],
                    }, default=str)
                else:
                    error_text = await resp.text()
                    return json.dumps({"error": f"Analysis failed: HTTP {resp.status}", "details": error_text[:300]})
    except Exception as e:
        return json.dumps({"error": f"Tool error: {str(e)}"})


async def handle_scan_contract(args: Dict[str, Any]) -> str:
    import aiohttp
    address = args.get("address", "")
    chain = args.get("chain", "ethereum")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(
                "http://localhost:8080/api/v1/contract/scan",
                json={"address": address, "chain": chain},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps({
                        "address": address,
                        "chain": chain,
                        "overall_risk": data.get("overall_risk"),
                        "risk_score": data.get("risk_score"),
                        "is_verified": data.get("is_verified"),
                        "ai_verdict": data.get("ai_verdict") or data.get("ai_risk_verdict"),
                        "ai_summary": data.get("ai_audit_summary"),
                        "key_findings": data.get("key_findings", [])[:5],
                        "recommendations": data.get("recommendations", [])[:5],
                        "vulnerabilities": [
                            {
                                "name": v.get("title") or v.get("name"),
                                "severity": v.get("severity"),
                                "line": v.get("line_number"),
                            }
                            for v in data.get("vulnerabilities", [])[:5]
                        ],
                    }, default=str)
                else:
                    error_text = await resp.text()
                    return json.dumps({"error": f"Contract scan failed: HTTP {resp.status}", "details": error_text[:300]})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_scan_wallet_approvals(args: Dict[str, Any]) -> str:
    import aiohttp
    wallet = args.get("wallet", "")
    chain = args.get("chain")
    url = f"http://localhost:8080/api/v1/shield/{wallet}"
    params = {}
    if chain:
        params["chain"] = chain
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    summary = data.get("summary", {})
                    high_risk = [a for a in data.get("approvals", []) if a.get("risk_level") == "HIGH"][:5]
                    return json.dumps({
                        "wallet": wallet,
                        "total_approvals": summary.get("total_approvals"),
                        "high_risk_count": summary.get("high_risk_count"),
                        "recommendation": data.get("recommendation"),
                        "top_high_risk": [
                            {
                                "token": a.get("token_address"),
                                "spender": a.get("spender_name") or a.get("spender_address"),
                                "allowance": a.get("allowance"),
                                "risk_score": a.get("risk_score"),
                            }
                            for a in high_risk
                        ],
                    }, default=str)
                else:
                    return json.dumps({"error": f"Shield scan failed: HTTP {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_get_defi_pools(args: Dict[str, Any]) -> str:
    import aiohttp
    params: Dict[str, str] = {}
    for k in ("chain", "protocol", "min_tvl", "min_apy", "max_apy"):
        if args.get(k) is not None:
            params[k] = str(args[k])
    params["limit"] = str(min(args.get("limit", 10), 15))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get("http://localhost:8080/api/v1/defi/pools", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pools = data.get("pools", [])
                    return json.dumps({
                        "count": data.get("count"),
                        "pools": [
                            {
                                "project": p.get("project"),
                                "symbol": p.get("symbol"),
                                "chain": p.get("chain"),
                                "tvlUsd": p.get("tvlUsd"),
                                "apy": p.get("apy"),
                                "risk_level": p.get("risk_level"),
                                "risk_score": p.get("risk_score"),
                                "risk_flags": p.get("risk_flags", [])[:2],
                            }
                            for p in pools
                        ],
                    }, default=str)
                else:
                    return json.dumps({"error": f"HTTP {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_get_yield_opportunities(args: Dict[str, Any]) -> str:
    import aiohttp
    params: Dict[str, str] = {}
    for k in ("chain", "exposure", "min_apy", "max_apy", "min_tvl"):
        if args.get(k) is not None:
            params[k] = str(args[k])
    params["limit"] = str(min(args.get("limit", 10), 15))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get("http://localhost:8080/api/v1/defi/yields", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    yields = data.get("yields", [])
                    return json.dumps({
                        "count": data.get("count"),
                        "yields": [
                            {
                                "project": y.get("project"),
                                "symbol": y.get("symbol"),
                                "chain": y.get("chain"),
                                "apy": y.get("apy"),
                                "apy_tier": y.get("apy_tier"),
                                "tvlUsd": y.get("tvlUsd") or y.get("tvl_usd"),
                                "exposure_type": y.get("exposure_type"),
                                "sustainability_ratio": y.get("sustainability_ratio"),
                                "risk_level": y.get("risk_level"),
                                "risk_flags": y.get("risk_flags", [])[:2],
                            }
                            for y in yields
                        ],
                    }, default=str)
                else:
                    return json.dumps({"error": f"HTTP {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_analyze_defi(args: Dict[str, Any]) -> str:
    import aiohttp
    params: Dict[str, str] = {}
    for k in ("query", "chain", "min_tvl", "min_apy"):
        if args.get(k) is not None:
            params[k] = str(args[k])
    params["limit"] = str(min(args.get("limit", 8), 12))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get("http://localhost:8080/api/v1/defi/analyze", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps({
                        "query": data.get("query"),
                        "chain": data.get("chain"),
                        "summary": data.get("summary", {}),
                        "highlights": data.get("highlights", {}),
                        "top_pools": [
                            {
                                "project": p.get("project"),
                                "symbol": p.get("symbol"),
                                "chain": p.get("chain"),
                                "apy": p.get("apy"),
                                "tvl_usd": p.get("tvlUsd") or p.get("tvl_usd"),
                                "risk_level": p.get("risk_level"),
                            }
                            for p in data.get("top_pools", [])[:5]
                        ],
                        "top_yields": [
                            {
                                "project": y.get("project"),
                                "symbol": y.get("symbol"),
                                "chain": y.get("chain"),
                                "apy": y.get("apy"),
                                "sustainability_ratio": y.get("sustainability_ratio"),
                                "risk_level": y.get("risk_level"),
                            }
                            for y in data.get("top_yields", [])[:5]
                        ],
                        "top_lending_markets": [
                            {
                                "protocol": m.get("protocol_display") or m.get("protocol"),
                                "symbol": m.get("symbol"),
                                "chain": m.get("chain"),
                                "apy_supply": m.get("apy_supply"),
                                "apy_borrow": m.get("apy_borrow"),
                                "combined_risk_score": m.get("combined_risk_score"),
                            }
                            for m in data.get("top_lending_markets", [])[:5]
                        ],
                        "matching_protocols": [
                            {
                                "name": p.get("name"),
                                "slug": p.get("slug"),
                                "tvl": p.get("tvl"),
                                "chains": p.get("chains", [])[:5],
                            }
                            for p in data.get("matching_protocols", [])[:5]
                        ],
                    }, default=str)
                return json.dumps({"error": f"HTTP {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_search_rekt_incidents(args: Dict[str, Any]) -> str:
    import aiohttp
    params: Dict[str, str] = {}
    for k in ("search", "chain", "attack_type", "min_amount"):
        if args.get(k) is not None:
            params[k] = str(args[k])
    params["limit"] = str(min(args.get("limit", 10), 20))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get("http://localhost:8080/api/v1/intel/rekt", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps({
                        "count": data.get("count"),
                        "total_stolen_usd": data.get("total_stolen_usd"),
                        "incidents": [
                            {
                                "name": i.get("name"),
                                "date": i.get("date"),
                                "amount_usd": i.get("amount_usd"),
                                "attack_type": i.get("attack_type"),
                                "chains": i.get("chains"),
                                "funds_recovered": i.get("funds_recovered"),
                                "description": (i.get("description") or "")[:200],
                            }
                            for i in data.get("incidents", [])
                        ],
                    }, default=str)
                else:
                    return json.dumps({"error": f"HTTP {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_search_audits(args: Dict[str, Any]) -> str:
    import aiohttp
    params: Dict[str, str] = {}
    for k in ("protocol", "auditor", "chain", "verdict"):
        if args.get(k) is not None:
            params[k] = str(args[k])
    params["limit"] = str(min(args.get("limit", 10), 15))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get("http://localhost:8080/api/v1/intel/audits", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps({
                        "count": data.get("count"),
                        "audits": [
                            {
                                "protocol": a.get("protocol"),
                                "auditor": a.get("auditor"),
                                "date": a.get("date"),
                                "verdict": a.get("verdict"),
                                "chains": a.get("chains", []),
                                "severity_findings": a.get("severity_findings", {}),
                            }
                            for a in data.get("audits", [])
                        ],
                    }, default=str)
                return json.dumps({"error": f"HTTP {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_get_protocol_info(args: Dict[str, Any]) -> str:
    import aiohttp
    slug = args.get("slug", "")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(f"http://localhost:8080/api/v1/defi/protocol/{slug}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return json.dumps({
                        "name": data.get("name"),
                        "slug": data.get("slug"),
                        "tvl": data.get("tvl"),
                        "chains": data.get("chains", [])[:10],
                        "category": data.get("category"),
                        "description": (data.get("description") or "")[:300],
                    }, default=str)
                else:
                    return json.dumps({"error": f"Protocol '{slug}' not found"})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_get_intel_stats(args: Dict[str, Any]) -> str:
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get("http://localhost:8080/api/v1/intel/stats") as resp:
                if resp.status == 200:
                    return json.dumps(await resp.json(), default=str)
                else:
                    return json.dumps({"error": f"HTTP {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# Dispatch map
TOOL_HANDLERS = {
    "analyze_token":          handle_analyze_token,
    "scan_contract":          handle_scan_contract,
    "scan_wallet_approvals":  handle_scan_wallet_approvals,
    "get_defi_pools":         handle_get_defi_pools,
    "get_yield_opportunities": handle_get_yield_opportunities,
    "analyze_defi":           handle_analyze_defi,
    "search_rekt_incidents":  handle_search_rekt_incidents,
    "search_audits":          handle_search_audits,
    "get_protocol_info":      handle_get_protocol_info,
    "get_intel_stats":        handle_get_intel_stats,
}


async def dispatch_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """Dispatch a tool call to its handler. Returns JSON string result."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        return await handler(args)
    except Exception as e:
        logger.error(f"Tool {tool_name} error: {e}")
        return json.dumps({"error": str(e)})
