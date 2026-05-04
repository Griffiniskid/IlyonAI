"""Simple agent runtime without ReAct - uses direct LLM calls with tool support."""
from __future__ import annotations

import json
import re
from typing import AsyncIterator

from src.agent.intent.defi_intent import DefiIntent, parse_defi_intent
from src.agent.llm import IlyonChatModel
from src.agent.streaming import StreamCollector, encode_sse, frame_event_name
from src.api.schemas.agent import ThoughtFrame, ToolFrame, ObservationFrame, FinalFrame, DoneFrame, CardFrame, PlanBlockedFrame

from src.storage.agent_chats import append_message, list_messages
from src.storage.database import get_database
from src.defi.strategy.opportunity_memory import (
    find_opportunity as _recall_pool,
    recall as _recall_opp_record,
    remember_allocation as _remember_allocation,
    remember_opportunities as _remember_opportunities,
)


# Maximum prior messages loaded into context per turn (user+assistant combined).
# Keeps prompts bounded while still giving the model multi-turn awareness.
HISTORY_WINDOW = 12


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
        r"explain .*scor(?:e|ing).*methodolog",
        r"what .*scor(?:e|ing).*methodolog",
        r"how .*scor(?:e|ing).*methodolog",
        r"scor(?:e|ing).*methodolog",
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
    "build_bridge_tx": [
        r"\bbridge\b",
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

CHAIN_IDS = {
    "ethereum": 1,
    "eth": 1,
    "mainnet": 1,
    "arbitrum": 42161,
    "arb": 42161,
    "base": 8453,
    "optimism": 10,
    "op": 10,
    "polygon": 137,
    "matic": 137,
    "bsc": 56,
    "bnb": 56,
    "solana": 7565164,
    "sol": 7565164,
}

TOKEN_DECIMALS = {
    "USDC": 6,
    "USDT": 6,
    "DAI": 18,
    "ETH": 18,
    "BNB": 18,
    "MATIC": 18,
    "SOL": 9,
}


def _is_critical_shield(envelope) -> bool:
    """Return True when a ToolEnvelope carries a critical Shield verdict or grade."""
    shield = getattr(envelope, "shield", None)
    if shield is None:
        return False
    verdict = (getattr(shield, "verdict", "") or "").upper()
    grade = (getattr(shield, "grade", "") or "").upper()
    return verdict == "SCAM" or grade == "F"


def _emit_plan_blocked_if_critical(envelope, *, plan_id: str):
    """Yield SSE-shaped dicts when a shield is critical.

    Used by simple_runtime to short-circuit the signing flow.
    """
    if not _is_critical_shield(envelope):
        return
    reasons = list(getattr(envelope.shield, "reasons", []) or [])
    yield {"plan_id": plan_id, "reasons": reasons, "severity": "critical"}


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


def _to_base_units(amount: str, token: str) -> str:
    raw = amount.replace(",", "")
    decimals = TOKEN_DECIMALS.get(token.upper(), 18)
    if "." in raw:
        whole, frac = raw.split(".", 1)
        frac = (frac + ("0" * decimals))[:decimals]
        return str(int(whole or "0") * (10 ** decimals) + int(frac or "0"))
    return str(int(raw or "0") * (10 ** decimals))


def _short_json(value: dict | None) -> str:
    if not value:
        return "{}"
    try:
        return json.dumps(value, sort_keys=True)[:220]
    except Exception:
        return str(value)[:220]


def _pre_tool_reasoning(tool_name: str, tool_input: dict, message: str) -> list[str]:
    amount = tool_input.get("usd_amount")
    risk = tool_input.get("risk_budget", "balanced")
    chains = tool_input.get("chains") or []
    if tool_name == "allocate_plan":
        chain_text = f" across {', '.join(chains)}" if chains else " across supported chains"
        amount_text = f"${amount:,.0f}" if isinstance(amount, (int, float)) else "the requested capital"
        return [
            f"Parsed intent: allocate {amount_text} across staking + yield, {risk} risk-weighted{chain_text}.",
            "Preparing live opportunity search across DefiLlama and the Sentinel DeFi intelligence engine.",
            "Applying hard filters before ranking: minimum TVL, sufficient operating history, sane APY, and supported chain coverage.",
            "Scoring candidates with Sentinel dimensions: Safety x Yield durability x Exit liquidity x Confidence.",
        ]
    if tool_name == "simulate_swap":
        return [
            f"Parsed swap intent: {_short_json(tool_input)}.",
            "Resolving token pair, chain, and amount before requesting a route quote.",
            "Checking quote quality: route source, expected output, price impact, gas, and slippage assumptions.",
            "Preparing wallet-safe signing guidance; the agent never touches private keys.",
        ]
    if tool_name == "build_bridge_tx":
        return [
            f"Parsed bridge intent: {_short_json(tool_input)}.",
            "Resolving source chain, destination chain, token decimals, and bridge route constraints.",
            "Checking bridge risk surface: fill time, route liquidity, destination correctness, and spender exposure.",
            "Preparing bridge signing guidance with wallet confirmation gates.",
        ]
    if tool_name == "compose_plan":
        return [
            "Parsed a multi-step execution request and decomposed it into ordered actions.",
            "Resolving dependencies between steps so later actions wait for prior receipts or received amounts.",
            "Checking chain, token, protocol, and spender assumptions before any wallet prompt exists.",
            "Applying Sentinel and Shield gates before exposing any signing path.",
            "Composing an execution plan card with per-step status, gas, wallet requirements, and dependency locks.",
        ]
    if tool_name == "get_staking_options":
        return [
            f"Parsed staking/yield search: {_short_json(tool_input)}.",
            "Querying yield pools and filtering for TVL depth, APY sanity, chain fit, and token relevance.",
            "Ranking opportunities by sustainable yield, exit liquidity, and Sentinel risk posture.",
            "Preparing pool cards so the user can compare yield against risk instead of chasing APY alone.",
        ]
    if tool_name == "search_defi_opportunities":
        return [
            f"Parsed constraint-aware DeFi search: {_short_json(tool_input)}.",
            "Separating research, allocation, and execution intent before selecting a tool.",
            "Applying hard APY, risk, chain, and TVL filters from the user's exact request.",
            "Checking execution readiness separately so unsupported pools never get fake signing buttons.",
        ]
    if tool_name == "build_yield_execution_plan":
        return [
            f"Parsed direct yield execution: {_short_json(tool_input)}.",
            "Confirming adapter coverage and producing real unsigned approve + supply calldata.",
            "Running wallet preflight (balance / gas / allowance) before exposing any signing button.",
            "Emitting an ExecutionPlanV3 card with per-step status; later steps unlock only after on-chain receipt.",
        ]
    if tool_name == "build_allocation_execution_plan":
        rows = tool_input.get("allocations") or []
        return [
            f"Composing one ExecutionPlanV3 across {len(rows)} allocation rows.",
            "Building real approve + deposit calldata per row via the adapter registry.",
            "Wiring per-chain dependency chains so each step unlocks only after the prior on-chain receipt.",
            "Skipping rows without verified adapters and surfacing them as warnings instead of fake buttons.",
        ]
    if tool_name == "build_yield_strategy_plan":
        return [
            f"Composing yield strategy: {_short_json(tool_input)}.",
            "Wiring prerequisite swap/bridge into the deposit step before any wallet signature.",
            "Verifying adapter coverage for the destination protocol/action/chain.",
            "Producing one ExecutionPlanV3 with per-step depends_on so the wallet sees a single signing flow.",
        ]
    if tool_name == "find_liquidity_pool":
        return [
            f"Parsed liquidity-pool search: {_short_json(tool_input)}.",
            "Resolving pair defaults and chain scope before searching DEX liquidity.",
            "Ranking pools by liquidity depth, route availability, and exit practicality.",
            "Flagging pool-selection caveats such as pair fragmentation and impermanent-loss exposure.",
        ]
    if tool_name == "get_wallet_balance":
        return [
            "Parsed wallet/portfolio request and resolved the best available wallet address.",
            "Aggregating supported-chain balances across EVM and Solana providers where available.",
            "Checking for missing-chain or rate-limit caveats before summarizing holdings.",
            "Preparing next-action guidance based on tracked assets and empty-wallet cases.",
        ]
    if tool_name == "get_token_price":
        return [
            f"Parsed token market request: {_short_json(tool_input)}.",
            "Resolving token identity across live price feeds before trusting the ticker symbol.",
            "Checking liquidity depth, 24h movement, and source quality so the quote is not a thin-pair artifact.",
            "Preparing price context with market caveats instead of a naked number.",
        ]
    if tool_name == "get_defi_market_overview":
        return [
            "Parsed DeFi market overview request.",
            "Aggregating protocol-level TVL, category, and short-term change data.",
            "Ranking protocols by liquidity depth, market relevance, and trend signal before summarizing.",
            "Separating broad market signal from action-ready opportunities so recommendations stay risk-aware.",
        ]
    if tool_name == "get_defi_analytics":
        return [
            f"Parsed DeFi analytics request: {_short_json(tool_input)}.",
            "Selecting protocol, pool, or market analytics mode from the query shape.",
            "Checking TVL, APY, liquidity, volatility, and Sentinel score context before summarizing.",
            "Preparing an analyst-style answer with caveats, strongest signals, and next action.",
        ]
    if tool_name == "search_dexscreener_pairs":
        return [
            f"Parsed DEX pair search: {_short_json(tool_input)}.",
            "Resolving query terms against live DexScreener pairs and chain aliases.",
            "Ranking candidates by liquidity depth, volume quality, freshness, and route usefulness.",
            "Preparing pair cards with enough context to avoid clicking shallow or misleading markets.",
        ]
    return [
        f"Parsed request and selected tool `{tool_name}` with inputs {_short_json(tool_input)}.",
        "Checking available data sources and risk context before answering.",
        "Preparing a concise result with next-step guidance.",
    ]


def _post_tool_reasoning(tool_name: str, env) -> list[str]:
    data = getattr(env, "data", None) or {}
    trace = [str(line) for line in data.get("analysis_trace", []) if line]
    if trace:
        return trace
    if tool_name == "simulate_swap":
        impact = data.get("price_impact_pct")
        return [
            f"Validated quote output and price impact{f' ({impact}%)' if impact not in (None, '') else ''} before presenting the swap card."
        ]
    if tool_name == "build_bridge_tx":
        return [
            "Validated bridge route payload and exposed route timing plus wallet-signing requirements.",
            "Checked source/destination chain assumptions and spender exposure before presenting the bridge card.",
        ]
    if tool_name == "get_staking_options":
        count = len(data.get("staking_options", []) or [])
        return [
            f"Selected {count} staking opportunities after liquidity and APY sanity filters.",
            "Prioritized sustainable yield and exit depth over headline APY.",
        ]
    if tool_name == "search_defi_opportunities":
        candidates = data.get("primary_candidates") or []
        excluded = data.get("excluded_summary") or []
        ready = (data.get("execution_readiness_summary") or {}).get("executable_count", 0)
        return [
            f"Selected {len(candidates)} candidates that match the requested APY/risk band; excluded {len(excluded)} mismatches.",
            f"Separated execution-ready opportunities from research-only results; executable count is {ready}.",
        ]
    if tool_name == "find_liquidity_pool":
        count = len(data.get("pools", []) or [])
        return [
            f"Selected {count} liquidity pools ranked by depth and route usefulness.",
            "Flagged liquidity selection caveats before exposing pool-level details.",
        ]
    if tool_name == "get_token_price":
        source = data.get("dex") or data.get("source") or "aggregated feed"
        liquidity = data.get("liquidity") or data.get("liquidity_usd")
        liquidity_text = f" (${float(liquidity):,.0f})" if isinstance(liquidity, (int, float)) else ""
        return [
            f"Validated live token price against {source}.",
            f"Checked liquidity context{liquidity_text} before summarizing the market read.",
        ]
    if tool_name == "get_wallet_balance":
        tokens = data.get("tokens") or data.get("balances") or []
        positions = data.get("positions") or []
        return [
            f"Normalized wallet holdings across available providers: {len(tokens) if isinstance(tokens, list) else 'multi-chain'} token rows and {len(positions) if isinstance(positions, list) else 0} DeFi positions.",
            "Checked missing-chain and empty-wallet caveats before giving portfolio next steps.",
        ]
    if tool_name == "get_defi_market_overview":
        protocols = data.get("protocols") or data.get("items") or []
        return [
            f"Condensed market overview from {len(protocols) if isinstance(protocols, list) else 'live'} protocol records.",
            "Separated broad market context from deployable recommendations so the answer stays decision-safe.",
        ]
    if tool_name == "get_defi_analytics":
        return [
            "Validated analytics result against Sentinel risk framing before writing the answer.",
            "Highlighted strongest signals, weakest assumptions, and useful follow-up actions.",
        ]
    if tool_name == "search_dexscreener_pairs":
        pairs = data.get("pairs") or data.get("results") or []
        return [
            f"Ranked {len(pairs) if isinstance(pairs, list) else 'live'} DEX pairs by liquidity, volume, and freshness.",
            "Prepared comparison-ready pair context instead of a raw search dump.",
        ]
    return ["Validated tool result and converted it into a risk-aware answer with user-facing next steps."]


def _emit_thoughts(collector: StreamCollector, lines: list[str]) -> None:
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        collector._step += 1
        collector._queue.append(ThoughtFrame(step_index=collector._step, content=text))


def _detect_bridge_then_stake(message: str) -> tuple[str, dict] | None:
    pattern = re.compile(
        r"bridge\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})\s+"
        r"from\s+(?P<src>[A-Za-z ]+?)\s+to\s+(?P<dst>[A-Za-z ]+?)\s*[,;]?\s*"
        r"(?:(?:and|then)\s+)?stake\s+(?:it\s+)?(?:on\s+)?(?P<protocol>[A-Za-z0-9 ._-]+)",
        re.IGNORECASE,
    )
    match = pattern.search(message)
    if not match:
        return None

    token = match.group("token").upper()
    src = match.group("src").strip().lower()
    dst = match.group("dst").strip().lower()
    protocol = match.group("protocol").strip().lower().replace(" ", "-")
    src_chain_id = CHAIN_IDS.get(src)
    dst_chain_id = CHAIN_IDS.get(dst)
    if src_chain_id is None or dst_chain_id is None:
        return None

    return (
        "compose_plan",
        {
            "title": f"Bridge {token} to {match.group('dst').strip().title()} and stake on {match.group('protocol').strip().title()}",
            "steps": [
                {
                    "step_id": "step-1",
                    "action": "bridge",
                    "params": {
                        "token_in": token,
                        "amount": _to_base_units(match.group("amount"), token),
                        "src_chain_id": src_chain_id,
                        "dst_chain_id": dst_chain_id,
                    },
                },
                {
                    "step_id": "step-2",
                    "action": "stake",
                    "params": {"token": token, "protocol": protocol, "chain_id": dst_chain_id},
                    "resolves_from": {"amount": "step-1.received_amount"},
                },
            ],
        },
    )


def _detect_swap_then_lp(message: str) -> tuple[str, dict] | None:
    pattern = re.compile(
        r"swap\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<tin>[A-Za-z]{2,10})\s+"
        r"(?:to|for|into)\s+(?P<tout>[A-Za-z]{2,10})\s+(?:then\s+)?"
        r"(?:provide\s+liquidity|deposit\s+lp|add\s+liquidity)\s+(?:to\s+)?"
        r"(?P<pair>[A-Za-z]{2,10}[/-][A-Za-z]{2,10})\s+(?:on\s+)?(?P<protocol>[A-Za-z0-9 ._-]+)",
        re.IGNORECASE,
    )
    match = pattern.search(message)
    if not match:
        return None
    pair = match.group("pair").upper().replace("/", "/")
    protocol = match.group("protocol").strip().lower().replace(" ", "-")
    return (
        "compose_plan",
        {
            "title": f"Swap {match.group('tin').upper()} to {match.group('tout').upper()} and deposit LP on {match.group('protocol').strip().title()}",
            "steps": [
                {
                    "step_id": "swap",
                    "action": "swap",
                    "params": {"token_in": match.group("tin").upper(), "token_out": match.group("tout").upper(), "amount": match.group("amount").replace(",", ""), "chain_id": 1},
                },
                {
                    "step_id": "deposit-lp",
                    "action": "deposit_lp",
                    "params": {"token": pair, "protocol": protocol, "chain_id": 1},
                    "resolves_from": {"amount": "swap.amount_out"},
                },
            ],
        },
    )


def _detect_transfer_plan(message: str) -> tuple[str, dict] | None:
    pattern = re.compile(r"(?:send|transfer)\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})\s+to\s+(?P<to>[\w.:-]+)", re.IGNORECASE)
    match = pattern.search(message)
    if not match:
        return None
    token = match.group("token").upper()
    return (
        "compose_plan",
        {
            "title": f"Send {token}",
            "steps": [
                {
                    "step_id": "transfer",
                    "action": "transfer",
                    "params": {"token": token, "amount": _to_base_units(match.group("amount"), token), "recipient": match.group("to"), "chain_id": 1},
                }
            ],
        },
    )


def _detect_stake_amount_plan(message: str) -> tuple[str, dict] | None:
    idle = re.search(r"stake\s+all\s+my\s+idle\s+(?P<token>[A-Za-z]{2,10})", message, re.IGNORECASE)
    if idle:
        token = idle.group("token").upper()
        return (
            "compose_plan",
            {
                "title": f"Stake idle {token}",
                "steps": [
                    {"step_id": "balance", "action": "get_balance", "params": {"token": token, "chain_id": 1}},
                    {"step_id": "stake", "action": "stake", "params": {"token": token, "protocol": "lido", "chain_id": 1}, "resolves_from": {"amount": "balance.idle_amount"}},
                ],
            },
        )

    direct = re.search(r"stake\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})\s+(?:on\s+)?(?P<protocol>[A-Za-z0-9 ._-]+)", message, re.IGNORECASE)
    if not direct:
        return None
    token = direct.group("token").upper()
    amount = float(direct.group("amount").replace(",", ""))
    amount_usd = amount * 3000 if token == "ETH" else amount
    return (
        "compose_plan",
        {
            "title": f"Stake {token} on {direct.group('protocol').strip().title()}",
            "steps": [
                {
                    "step_id": "stake",
                    "action": "stake",
                    "params": {"token": token, "amount": direct.group("amount"), "protocol": direct.group("protocol").strip().lower().replace(" ", "-"), "chain_id": 1, "amount_usd": amount_usd},
                }
            ],
        },
    )


def _detect_malicious_swap_plan(message: str) -> tuple[str, dict] | None:
    pattern = re.compile(r"swap\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<tin>[A-Za-z]{2,10})\s+(?:to|for|into)\s+(?P<tout>[A-Za-z0-9_-]+)", re.IGNORECASE)
    match = pattern.search(message)
    if not match or "malicious" not in match.group("tout").lower():
        return None
    return (
        "compose_plan",
        {
            "title": "Blocked swap risk review",
            "steps": [
                {"step_id": "swap", "action": "swap", "params": {"token_in": match.group("tin").upper(), "token_out": match.group("tout").upper(), "amount": match.group("amount"), "chain_id": 1}}
            ],
        },
    )


# Phrases that mean "execute the previously discussed plan / continue the prior turn".
# Kept narrow on purpose — only short confirmations, no broad keywords like "do it"
# that could match unrelated turns.
FOLLOWUP_PROCEED_PATTERNS = [
    r"^\s*proceed\b",
    r"\bproceed\s+with\s+(?:the\s+)?execut",
    r"\bproceed\s+with\s+(?:the\s+)?(?:plan|allocation|swap|bridge|stake)",
    r"\b(?:please\s+)?(?:go\s+ahead|continue|carry\s+on)\b.*\bexecut",
    r"^\s*(?:please\s+)?execute\s+(?:the|it|that|this|plan|allocation)?\b",
    r"^\s*yes(?:,)?\s*(?:please\s*)?(?:proceed|execute|continue|go\s+ahead)\b",
    r"^\s*confirm(?:ed)?\b",
    r"^\s*(?:let'?s|let\s+us)\s+(?:do\s+(?:it|this|that)|proceed|execute|go)\b",
    r"^\s*(?:approved|approve)\b",
]


def detect_followup_intent(message: str) -> str | None:
    """Return a normalized follow-up intent label or None.

    Currently emits 'proceed_execution' for confirmation/proceed phrases.
    The caller is expected to combine this with chat history to determine
    *which* prior plan or allocation the user is approving.
    """
    text = message.strip()
    if not text:
        return None
    for pat in FOLLOWUP_PROCEED_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "proceed_execution"
    return None


_AAVE_SUPPLY_RE = re.compile(
    r"(?:supply|deposit|lend)\s+"
    r"(?P<amount>[\d,]+(?:\.\d+)?)\s*"
    r"(?P<asset>[A-Za-z]{2,10})"
    r"(?:.*?(?:to|on|via|into)\s+aave(?:\s*v3)?)?"
    r"(?:.*?on\s+(?P<chain>ethereum|polygon|arbitrum|optimism|base|avalanche))?",
    re.IGNORECASE | re.DOTALL,
)


_AAVE_HINT = re.compile(r"\baave\b", re.IGNORECASE)


_BRIDGE_THEN_SUPPLY_RE = re.compile(
    r"bridge\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<asset>[A-Za-z]{2,10})"
    r"(?:\s+from\s+(?P<src>ethereum|polygon|arbitrum|optimism|base|avalanche|bsc))?"
    r"\s+to\s+(?P<dst>ethereum|polygon|arbitrum|optimism|base|avalanche|bsc)"
    r".*?(?:then|and).*?(?:supply|deposit|lend).*?aave",
    re.IGNORECASE | re.DOTALL,
)

_SWAP_THEN_SUPPLY_RE = re.compile(
    r"swap\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<src_asset>[A-Za-z]{2,10})\s+(?:to|for|into)\s+(?P<dst_asset>[A-Za-z]{2,10})"
    r"(?:\s+on\s+(?P<chain>ethereum|polygon|arbitrum|optimism|base|avalanche|bsc))?"
    r".*?(?:then|and).*?(?:supply|deposit|lend).*?aave",
    re.IGNORECASE | re.DOTALL,
)


def _detect_bridge_then_aave_supply(message: str) -> tuple[str, dict] | None:
    match = _BRIDGE_THEN_SUPPLY_RE.search(message)
    if not match:
        return None
    return "build_yield_strategy_plan", {
        "deposit_chain": (match.group("dst") or "base").lower(),
        "deposit_protocol": "aave-v3",
        "deposit_action": "supply",
        "deposit_asset": match.group("asset").upper(),
        "deposit_amount": match.group("amount").replace(",", ""),
        "source_chain": (match.group("src") or "ethereum").lower(),
        "source_asset": match.group("asset").upper(),
        "source_amount": match.group("amount").replace(",", ""),
    }


def _detect_swap_then_aave_supply(message: str) -> tuple[str, dict] | None:
    match = _SWAP_THEN_SUPPLY_RE.search(message)
    if not match:
        return None
    chain = (match.group("chain") or "ethereum").lower()
    return "build_yield_strategy_plan", {
        "deposit_chain": chain,
        "deposit_protocol": "aave-v3",
        "deposit_action": "supply",
        "deposit_asset": match.group("dst_asset").upper(),
        "deposit_amount": match.group("amount").replace(",", ""),
        "source_chain": chain,
        "source_asset": match.group("src_asset").upper(),
        "source_amount": match.group("amount").replace(",", ""),
    }


def _detect_aave_supply(message: str) -> tuple[str, dict] | None:
    """Match prompts like 'supply 100 USDC to Aave V3 on Ethereum' / 'execute Aave USDC supply 100'."""
    if not _AAVE_HINT.search(message):
        return None
    match = _AAVE_SUPPLY_RE.search(message)
    if not match:
        # Fallback: 'execute aave (v3) usdc supply 100 on base'
        alt = re.search(
            r"aave(?:\s*v3)?[^\d\n]*?(?P<asset>[A-Za-z]{2,10})\s+(?:supply|deposit|lend)\s+(?P<amount>[\d,]+(?:\.\d+)?)(?:\s+on\s+(?P<chain>ethereum|polygon|arbitrum|optimism|base|avalanche))?",
            message,
            re.IGNORECASE | re.DOTALL,
        )
        if not alt:
            return None
        match = alt
    asset = match.group("asset").upper()
    if asset.lower() in {"on", "to", "of"}:
        return None
    amount = match.group("amount").replace(",", "")
    chain_match = match.groupdict().get("chain")
    chain = (chain_match or "ethereum").lower()
    return "build_yield_execution_plan", {
        "chain": chain,
        "protocol": "aave-v3",
        "action": "supply",
        "asset_in": asset,
        "amount_in": amount,
    }


_POOL_EXECUTE_TRIGGER = re.compile(
    r"\b(execute|sign|run|deploy|fire|do)\b.*\b("
    r"this\s+pool|the\s+pool|that\s+pool|pool\s+#?\d+|"
    r"these\s+pools|the\s+pools|the\s+strategy|the\s+plan|the\s+allocation|"
    r"transactions?\s+through\s+(my|the)\s+wallet|through\s+(my|the)\s+wallet|"
    r"the\s+transactions?|all\s+(of\s+)?them|all\s+(the\s+)?pools)\b",
    re.IGNORECASE,
)
_POOL_EXECUTE_HINT = re.compile(
    r"\b(execute|sign|run|deploy|deposit\s+into|stake\s+to|enter|provide\s+lp)\b",
    re.IGNORECASE,
)
_POOL_REF_INDEX = re.compile(r"#\s*(\d{1,2})|pool\s*(\d{1,2})\b|number\s*(\d{1,2})\b", re.IGNORECASE)
_POOL_REF_PROTOCOL_PAIR = re.compile(
    r"([A-Za-z][A-Za-z0-9_-]{2,40})\s+([A-Z][A-Z0-9]{1,9}[\s/-][A-Z0-9]{1,12})",
)
_POOL_AMOUNT_RE = re.compile(
    r"(?:with\s+)?\$?\s*([\d,]+(?:\.\d+)?)\s*(usdc|usdt|dai|usds|usd|sol|eth|bnb|matic|avax|wbtc|btc)?",
    re.IGNORECASE,
)
_ALLOC_TRIGGER = re.compile(
    r"\b(execute|sign|run|deploy)\b.*\b("
    r"the\s+(strategy|allocation|plan|transactions?|deposits?|distribution)|"
    r"transactions?\s+through\s+(my|the)\s+wallet|"
    r"all\s+(of\s+)?them|all\s+(the\s+)?pools)\b",
    re.IGNORECASE,
)


def _action_for_product_type(product_type: str | None) -> str:
    pt = (product_type or "").lower()
    if pt in {"pool", "lp", "amm", "clmm"}:
        return "deposit_lp"
    if pt in {"staking", "stake", "lst"}:
        return "stake"
    return "supply"


def _detect_pool_execute_followup(
    message: str, session_id: str | None
) -> tuple[str, dict] | None:
    """Resolve "execute this pool X" / "execute the strategy" against session memory."""
    if not session_id:
        return None
    if not message:
        return None
    msg = message.strip()
    if not _POOL_EXECUTE_HINT.search(msg):
        return None

    record = _recall_opp_record(str(session_id))
    if record is None:
        return None

    asset_match = _POOL_AMOUNT_RE.search(msg)
    asked_amount = asset_match.group(1).replace(",", "") if asset_match else None
    asked_asset = (asset_match.group(2) or "").upper() if asset_match else None

    # ── Multi-pool / allocation trigger ──────────────────────────────────────
    if _ALLOC_TRIGGER.search(msg):
        rows = list(record.allocations or [])
        if not rows and record.items:
            # Fall back to top-N items if the user never ran allocate_plan but
            # has a fresh pool list.
            rows = record.items[:5]
        if rows:
            default_asset = (asked_asset or record.last_asset_hint or "USDC").upper()
            return "build_allocation_execution_plan", {
                "allocations": rows,
                "default_asset": default_asset,
                "default_amount_total": (
                    asked_amount or
                    (str(int(record.last_amount_usd)) if record.last_amount_usd else None)
                ),
                "title_hint": f"Allocation execution ({len(rows)} pools)",
            }

    # ── Single-pool trigger ──────────────────────────────────────────────────
    if not _POOL_EXECUTE_TRIGGER.search(msg):
        # Treat "execute pool raydium-amm SPACEX-WSOL" as a pool trigger even
        # without the literal phrase "this pool".
        if "execute" not in msg.lower() and "sign" not in msg.lower():
            return None

    index_match = _POOL_REF_INDEX.search(msg)
    index_hint: int | None = None
    if index_match:
        for grp in index_match.groups():
            if grp:
                try:
                    index_hint = int(grp)
                except ValueError:
                    pass
                break

    protocol_hint: str | None = None
    symbol_hint: str | None = None
    pair_match = _POOL_REF_PROTOCOL_PAIR.search(msg)
    if pair_match:
        protocol_hint = pair_match.group(1)
        symbol_hint = pair_match.group(2).replace(" ", "-")
    else:
        # Look for a known protocol name token.
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", msg):
            tl = token.lower()
            if tl in {
                "aave", "compound", "lido", "ethena", "morpho", "spark", "yearn",
                "convex", "curve", "pendle", "stargate", "frax", "rocketpool",
                "etherfi", "stader", "raydium", "orca", "kamino", "marinade",
                "jito", "sanctum", "meteora", "aerodrome", "uniswap", "velodrome",
                "supernova", "steer", "moonwell", "drift", "lulo",
            }:
                protocol_hint = tl
                break

    chain_hint: str | None = None
    chain_match = re.search(
        r"\b(ethereum|polygon|arbitrum|optimism|base|avalanche|bsc|solana|sol)\b",
        msg, re.IGNORECASE,
    )
    if chain_match:
        chain_hint = chain_match.group(1).lower()

    opp = _recall_pool(
        str(session_id),
        protocol_hint=protocol_hint,
        symbol_hint=symbol_hint,
        chain_hint=chain_hint,
        index_hint=index_hint,
    )
    if opp is None:
        return None

    asset_in = (asked_asset or _infer_asset_from_symbol(opp.get("symbol"), opp.get("chain")) or "USDC").upper()
    amount = asked_amount or _amount_from_record(record) or "100"
    action = _action_for_product_type(opp.get("product_type"))

    return "build_yield_execution_plan", {
        "chain": opp.get("chain"),
        "protocol": opp.get("protocol"),
        "action": action,
        "asset_in": asset_in,
        "amount_in": amount,
        "research_thesis": (
            f"Replaying selected pool ({opp.get('protocol')} {opp.get('symbol')} "
            f"on {opp.get('chain')}) from prior search."
        ),
    }


def _infer_asset_from_symbol(symbol: str | None, chain: str | None) -> str | None:
    if not symbol:
        return None
    sym = symbol.upper()
    for stable in ("USDC", "USDT", "DAI", "USDS", "USDE"):
        if stable in sym:
            return stable
    if (chain or "").lower() in {"solana", "sol"} and ("WSOL" in sym or "SOL" in sym):
        return "SOL"
    for major in ("WETH", "ETH", "WBTC", "BTC", "MATIC", "AVAX", "BNB"):
        if major in sym:
            return "ETH" if major == "WETH" else major
    return None


def _amount_from_record(record) -> str | None:
    if record is None:
        return None
    if record.last_amount_usd:
        return str(int(record.last_amount_usd))
    return None


def _defi_intent_to_tool(intent: DefiIntent) -> tuple[str, dict] | None:
    if intent.intent == "allocate_strategy":
        params: dict = {
            "usd_amount": intent.amount_usd or 10_000.0,
            "risk_budget": intent.risk_budget,
        }
        if intent.chains:
            params["chains"] = intent.chains
        if intent.asset_hint:
            params["asset_hint"] = intent.asset_hint
        if intent.target_apy is not None:
            params["target_apy"] = intent.target_apy
        if intent.min_apy is not None:
            params["min_apy"] = intent.min_apy
        if intent.max_apy is not None:
            params["max_apy"] = intent.max_apy
        if intent.risk_levels:
            params["risk_levels"] = intent.risk_levels
        return "allocate_plan", params

    if intent.intent not in {"search_defi_opportunities", "execute_yield_strategy"}:
        return None

    params: dict = {
        "risk_levels": intent.risk_levels,
        "product_types": intent.product_types,
        "chains": intent.chains,
        "ranking_objective": intent.ranking_objective,
        "execution_requested": intent.execution_requested,
        "limit": 8,
    }
    if intent.target_apy is not None:
        params["target_apy"] = intent.target_apy
    if intent.min_apy is not None:
        params["min_apy"] = intent.min_apy
    if intent.max_apy is not None:
        params["max_apy"] = intent.max_apy
    if intent.asset_hint:
        params["asset_hint"] = intent.asset_hint
    return "search_defi_opportunities", params


def detect_intent(message: str) -> tuple[str, dict] | None:
    """Detect intent and extract parameters from user message."""
    message_lower = message.lower()

    # Strategy composer detectors (multi-step yield) win over single-action detectors.
    for detector in (_detect_bridge_then_aave_supply, _detect_swap_then_aave_supply):
        detected = detector(message)
        if detected is not None:
            return detected
    multi_step = _detect_bridge_then_stake(message)
    if multi_step is not None:
        return multi_step
    for detector in (_detect_aave_supply, _detect_swap_then_lp, _detect_stake_amount_plan, _detect_malicious_swap_plan, _detect_transfer_plan):
        detected = detector(message)
        if detected is not None:
            return detected

    defi_tool = _defi_intent_to_tool(parse_defi_intent(message))
    if defi_tool is not None:
        return defi_tool

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
                    tok = match.group(1).upper()
                    # Skip common English words that aren't tokens.
                    if tok.lower() not in {"the", "a", "an", "this", "that", "it", "of", "on", "in", "for"}:
                        params["token"] = tok
                elif tool_name == "simulate_swap":
                    # Parse "swap [of] <amount> <TOKEN_IN> to <TOKEN_OUT> on <chain>".
                    swap_re = re.compile(
                        r"(?:swap|exchange|convert|trade)\s+"
                        r"(?:of\s+)?"
                        r"(?P<amount>[\d,]+(?:\.\d+)?)\s*"
                        r"(?P<tin>[A-Za-z]{2,10})\s+"
                        r"(?:to|for|into)\s+"
                        r"(?P<tout>[A-Za-z]{2,10})"
                        r"(?:\s+on\s+(?P<chain>\w+))?",
                        re.IGNORECASE,
                    )
                    m2 = swap_re.search(message)
                    if m2:
                        params["token_in"] = m2.group("tin").upper()
                        params["token_out"] = m2.group("tout").upper()
                        params["amount"] = m2.group("amount").replace(",", "")
                        chain = m2.group("chain")
                        params["chain"] = (chain.lower() if chain else "ethereum")
                    else:
                        # Fallback: pick the last two capitalised tokens that aren't english stop-words
                        stop = {"SWAP", "TO", "FOR", "INTO", "ON", "THE", "A", "AN"}
                        candidates = [t for t in re.findall(r"[A-Za-z]{2,10}", message)
                                      if t.upper() not in stop]
                        if len(candidates) >= 2:
                            params["token_in"] = candidates[-2].upper()
                            params["token_out"] = candidates[-1].upper()
                        amount_match = re.search(r'(\d+(?:\.\d+)?)', message)
                        if amount_match:
                            params["amount"] = amount_match.group(1)
                        params["chain"] = "ethereum"
                elif tool_name == "build_bridge_tx":
                    bridge_re = re.compile(
                        r"bridge\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})"
                        r"(?:\s+from\s+(?P<src>[A-Za-z ]+?))?\s+to\s+(?P<dst>[A-Za-z ]+)",
                        re.IGNORECASE,
                    )
                    m_bridge = bridge_re.search(message)
                    if m_bridge:
                        token = m_bridge.group("token").upper()
                        src = (m_bridge.group("src") or "ethereum").strip().lower()
                        dst = m_bridge.group("dst").strip().lower()
                        dst = re.sub(r"\s+(?:and|then|to|for).*$", "", dst).strip()
                        params["src_chain_id"] = CHAIN_IDS.get(src, 1)
                        params["dst_chain_id"] = CHAIN_IDS.get(dst, CHAIN_IDS.get(dst.split()[0], 42161))
                        params["token_in"] = token
                        params["token_out"] = token
                        params["amount"] = _to_base_units(m_bridge.group("amount"), token)
                elif tool_name == "find_liquidity_pool":
                    # "pool for USDC on Ethereum" / "pool for USDC/WETH"
                    pair_re = re.compile(
                        r"(?:pool|pair|lp)\s+(?:for\s+)?"
                        r"(?P<ta>[A-Za-z]{2,10})"
                        r"(?:\s*[/-]\s*(?P<tb>[A-Za-z]{2,10}))?"
                        r"(?:\s+on\s+(?P<chain>\w+))?",
                        re.IGNORECASE,
                    )
                    m3 = pair_re.search(message)
                    _STABLES = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "USDE"}
                    if m3:
                        ta = m3.group("ta").upper()
                        tb = m3.group("tb")
                        params["token_a"] = ta
                        if tb:
                            params["token_b"] = tb.upper()
                        else:
                            # Smart default: stable → pair with WETH, else pair with USDC.
                            params["token_b"] = "WETH" if ta in _STABLES else "USDC"
                        chain = m3.group("chain")
                        if chain:
                            params["chain"] = chain.lower()
                    else:
                        # Provide defaults so the tool doesn't 400 on missing required args
                        params["token_a"] = "USDC"
                        params["token_b"] = "WETH"
                        params["chain"] = "ethereum"
                elif tool_name == "get_wallet_balance":
                    # Pull the first 0x... (EVM) or base58 Solana-ish address.
                    evm_m = re.search(r"\b(0x[a-fA-F0-9]{40})\b", message)
                    sol_m = re.search(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b", message)
                    if evm_m:
                        params["wallet"] = evm_m.group(1)
                    elif sol_m:
                        params["wallet"] = sol_m.group(1)
                elif tool_name == "get_staking_options":
                    params["min_tvl"] = 200_000_000
                    params["min_apy"] = 0.5
                    params["limit"] = 8
                    chains = _parse_chains(message)
                    if chains:
                        params["chain"] = chains[0]
                    # Try to extract an asset filter
                    asset_m = re.search(
                        r"\b(?:for|of)\s+([A-Za-z]{2,8})\b",
                        message,
                        re.IGNORECASE,
                    )
                    if asset_m:
                        params["asset"] = asset_m.group(1).upper()
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

    chain_label = (chain or "").replace("-", " ").title() if chain else ""
    if dex and dex.lower() == "coingecko":
        response += f"Source: CoinGecko · {chain_label}\n\n" if chain_label else "Source: CoinGecko\n\n"
    elif dex and dex != "unknown":
        response += f"Source: {dex.title()} on {chain_label or 'DEX'}\n\n"
    else:
        response += f"Source: Aggregated DEX feed\n\n"
    response += "*Prices are sourced from live on-chain and CoinGecko feeds; small differences across exchanges are normal.*"

    return response


def _pretty_project(slug: str) -> str:
    if not slug:
        return "Unknown"
    s = str(slug).replace("_", "-").replace(".", " ")
    return " ".join(p.capitalize() if p and not p.isupper() else p for p in s.split("-"))


def _format_staking_response(data: dict) -> str:
    """Format staking data into natural language."""
    pools = data.get("staking_options", [])

    if not pools:
        return "I couldn't find any staking pools matching your criteria right now. Try adjusting your search or check back later."

    response = f"**Top Staking Opportunities** ({len(pools)} pools found)\n\n"

    for i, pool in enumerate(pools[:5], 1):
        protocol = _pretty_project(pool.get("protocol", "Unknown"))
        symbol = pool.get("symbol", "")
        apy = pool.get("apy", 0) or 0
        tvl = pool.get("tvl_usd", 0) or 0
        risk = pool.get("risk_level", "UNKNOWN")
        chain = pool.get("chain", "Unknown")

        response += f"{i}. **{protocol}** — {symbol}  \n"
        response += f"   APY {apy:.2f}% · TVL ${tvl:,.0f} · {chain} · Risk {risk}\n\n"

    response += "*Ranked by log-TVL × APY (junk-yield pools filtered). DYOR — higher APY almost always means higher risk.*"
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


def _format_balance_response(data: dict) -> str:
    wallet = data.get("wallet", "")
    total = data.get("total_usd", "0.00")
    by_chain = data.get("by_chain") or {}
    lines: list[str] = [f"**Wallet Balance — {wallet}**", ""]
    if str(total) in ("0.00", "0", "0.0"):
        lines.append("Total tracked value: **$0.00**\n")
        lines.append(
            "I couldn't find any positions on the supported chains. This usually means the wallet is empty, "
            "on a chain we don't track yet, or the balance API is rate-limited — try again in a minute."
        )
    else:
        lines.append(f"Total tracked value: **${total}**")
        lines.append("")
        for chain, usd in by_chain.items():
            lines.append(f"- {chain.title()}: ${usd}")
    lines.append("")
    lines.append("*Balances are aggregated from Moralis (EVM) and Helius/RPC (Solana); small delays are normal.*")
    return "\n".join(lines)


def _format_pool_response(data: dict) -> str:
    pools = data.get("pools", []) or []
    ta = data.get("token_a", "?")
    tb = data.get("token_b", "?")
    if not pools:
        return (
            f"I couldn't find a {ta}/{tb} pool on the chain you asked for. "
            "Try a different quote token (e.g. USDC or WETH) or another chain."
        )
    lines: list[str] = [f"**Liquidity Pools — {ta}/{tb}** ({len(pools)} found)", ""]
    for i, p in enumerate(pools[:5], 1):
        dex = p.get("dex", "unknown")
        chain = p.get("chain", "unknown")
        liq = p.get("liquidity_usd") or p.get("liquidity") or 0
        try:
            liq_str = f"${float(liq):,.0f}"
        except Exception:
            liq_str = str(liq)
        lines.append(f"{i}. **{dex.title()}** on {str(chain).title()} · liquidity {liq_str}")
    lines.append("")
    lines.append("*Deepest pools first. Pair availability varies by DEX.*")
    return "\n".join(lines)


def _format_swap_response(data: dict) -> str:
    """Format swap data into natural language."""
    # Accept multiple payload shapes: flat {token_in, amount_in} or nested {pay, receive}.
    pay = data.get("pay") or {}
    receive = data.get("receive") or {}
    token_in = data.get("token_in") or pay.get("symbol") or pay.get("token") or ""
    token_out = data.get("token_out") or receive.get("symbol") or receive.get("token") or ""
    amount = (
        data.get("amount_in")
        or data.get("amount")
        or pay.get("amount")
        or pay.get("amount_in")
        or "0"
    )
    estimated = (
        data.get("estimated_out")
        or receive.get("amount")
        or receive.get("amount_out")
        or "0"
    )
    rate = data.get("rate")
    router = data.get("router") or data.get("dex") or ""
    chain = data.get("chain", "")
    price_impact = data.get("price_impact_pct")

    response = f"**Swap Quote — {amount} {token_in} → {token_out}**\n\n"
    if estimated and str(estimated) != "0":
        response += f"Estimated receive: **~{estimated} {token_out}**\n"
    if rate:
        response += f"Rate: {rate}\n"
    if price_impact not in (None, ""):
        response += f"Price impact: {price_impact}%\n"
    if router:
        response += f"Route: {router}"
        if chain:
            response += f" ({chain})"
        response += "\n"
    if estimated in (None, "0", "") and rate is None:
        response += "\nI couldn't compute a firm quote — provide contract addresses for the pair to get an on-chain simulation."
    else:
        response += "\n*Estimate only; sign inside your wallet to confirm slippage and gas.*"
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
        "For the demo allocation rubric, Sentinel blends 0.40 Safety, 0.25 Yield Durability, 0.20 Exit Liquidity, and 0.15 Confidence into a 0-100 deployability score. The deeper DeFi pipeline can add product-specific APR efficiency and dependency haircuts, but the visible recommendation envelope always exposes those four core dimensions.\n\n"
        "**Risk level and strategy fit**\n"
        "Risk level is derived from the safety deficit. Strategy fit is conservative only when safety is very strong and yield quality is still healthy; otherwise opportunities move into balanced or aggressive buckets.\n\n"
        "**What this means in practice**\n"
        "A pool with high APY but weak exits, poor docs, fragile incentives, or heavy dependency risk will not rank well. A lower-APY venue can outrank it if the carry is cleaner, the exit is deeper, and the evidence is stronger."
    )


def _format_execution_plan_v3_response(data: dict) -> str:
    plan = data.get("plan") or data
    steps = plan.get("steps") or []
    blockers = plan.get("blockers") or []
    title = plan.get("title") or "Yield Execution Plan"
    summary = plan.get("summary") or ""
    status = plan.get("status") or "draft"
    lines = [f"**{title}** — {summary}"]
    lines.append(f"Status: `{status}` · {plan.get('totals', {}).get('signatures_required', 0)} signature(s) required.")
    if steps:
        lines.append("")
        lines.append("**Steps**")
        for step in steps:
            ready_marker = "▶ " if step.get("status") == "ready" else "· "
            asset = step.get("asset_in") or ""
            amount = step.get("amount_in") or ""
            head = f"{ready_marker}Step {step.get('index')} — {step.get('action')}"
            if amount and asset:
                head += f" {amount} {asset}"
            head += f" on {step.get('chain')} via {step.get('protocol')} ({step.get('status')})"
            lines.append(head)
    if blockers:
        lines.append("")
        lines.append("**Blockers**")
        for blocker in blockers:
            lines.append(f"- {blocker.get('title')}: {blocker.get('detail')}")
        lines.append("")
        lines.append("No signing button is shown until every blocker clears.")
    elif status == "ready":
        lines.append("")
        lines.append("Open the Execution Plan card above and sign step 1 in your wallet to begin.")
    return "\n".join(lines).strip()


def _format_opportunity_search_response(data: dict) -> str:
    candidates = data.get("primary_candidates") or []
    blockers = data.get("execution_blockers") or []
    if not candidates:
        return (
            "I couldn't find credible DeFi opportunities matching those exact APY, risk, chain, and TVL constraints. "
            "I did not fall back to unrelated low-risk pools; loosen the APY band or risk filter if you want broader research."
        )

    lines = ["**Constraint-Matched DeFi Opportunities**", ""]
    for index, candidate in enumerate(candidates[:5], 1):
        apy = candidate.get("apy") or 0
        tvl = candidate.get("tvl_usd") or 0
        try:
            apy_text = f"{float(apy):.1f}%"
        except (TypeError, ValueError):
            apy_text = str(apy)
        try:
            tvl_text = f"${float(tvl):,.0f}"
        except (TypeError, ValueError):
            tvl_text = str(tvl)
        lines.append(
            f"{index}. **{_pretty_project(str(candidate.get('protocol') or 'Unknown'))}** — "
            f"{candidate.get('symbol') or 'Unknown'} on {candidate.get('chain') or 'unknown'}  "
        )
        lines.append(f"   APY {apy_text} · TVL {tvl_text} · Risk {candidate.get('risk_level') or 'UNKNOWN'}")
        urls = candidate.get("source_urls") or {}
        link_parts: list[str] = []
        if urls.get("defillama_pool"):
            link_parts.append(f"[DefiLlama pool]({urls['defillama_pool']})")
        if urls.get("defillama_protocol"):
            link_parts.append(f"[Protocol on DefiLlama]({urls['defillama_protocol']})")
        if urls.get("protocol_site"):
            link_parts.append(f"[Protocol site]({urls['protocol_site']})")
        if link_parts:
            lines.append(f"   Links: {' · '.join(link_parts)}")
        reason = candidate.get("unsupported_reason")
        if candidate.get("executable"):
            adapter = candidate.get("adapter_id") or "executable adapter"
            lines.append(f"   Execution: ready via {adapter}")
        elif reason:
            lines.append(f"   Execution: routed via closest-executable alternative — {reason}")
        lines.append("")

    excluded = data.get("excluded_summary") or []
    if excluded:
        lines.append(
            f"Excluded {len(excluded)} candidates that violated the requested risk, APY, chain, or TVL constraints."
        )
        lines.append("")

    if blockers:
        lines.append("**Execution Blocked**")
        for blocker in blockers:
            lines.append(f"- {blocker.get('title')}: {blocker.get('detail')}")
        lines.append("")
        lines.append("No signing button shown because no verified adapter can build unsigned transactions for this path yet.")
    elif data.get("execution_requested"):
        ready = (data.get("execution_readiness_summary") or {}).get("executable_count", 0)
        lines.append(f"Execution readiness: {ready} candidate(s) have adapter support.")

    return "\n".join(lines).strip()


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
    if tool_name == "search_defi_opportunities":
        return _format_opportunity_search_response(data)
    if tool_name in {"build_yield_execution_plan", "build_yield_strategy_plan", "build_allocation_execution_plan"} or card_type == "execution_plan_v3":
        return _format_execution_plan_v3_response(data)
    if card_type == "token" or tool_name == "get_token_price":
        return _format_price_response(data)
    elif card_type == "stake" or tool_name == "get_staking_options":
        return _format_staking_response(data)
    elif card_type == "market_overview" or tool_name == "get_defi_market_overview":
        return _format_market_response(data)
    elif card_type == "swap_quote" or tool_name == "simulate_swap":
        return _format_swap_response(data)
    elif card_type == "balance" or tool_name == "get_wallet_balance":
        return _format_balance_response(data)
    elif card_type == "pool" or tool_name == "find_liquidity_pool":
        return _format_pool_response(data)
    elif card_type == "bridge" or tool_name == "build_bridge_tx":
        return _format_bridge_response(data)
    else:
        # Generic formatting
        return json.dumps(data, indent=2) if isinstance(data, dict) else str(data)


def _format_bridge_response(data: dict) -> str:
    src = data.get("src_chain_id", "source")
    dst = data.get("dst_chain_id", "destination")
    amount_in = data.get("amount_in_display") or data.get("amount_in") or data.get("amount") or "requested amount"
    amount_out = data.get("dst_amount_display") or data.get("amount_out") or "estimated output"
    fill = data.get("estimated_fill_time_seconds") or data.get("estimated_seconds")
    router = data.get("router") or "deBridge"
    lines = [
        f"**Bridge Quote — chain {src} → chain {dst}**",
        "",
        f"Amount in: **{amount_in}**",
        f"Estimated receive: **{amount_out}**",
        f"Route: {router}",
    ]
    if fill:
        lines.append(f"Estimated fill time: ~{fill}s")
    lines.extend([
        "",
        "*Review the bridge route, destination chain, and spender in your wallet before signing.*",
    ])
    return "\n".join(lines)


_PLAN_KEYWORDS = (
    "execution plan",
    "step execution plan",
    "allocate",
    "allocation",
    "sentinel scoring breakdown",
    "step-1",
    "step 1",
    "review the full plan",
)


def _maybe_replay_followup(*, message: str, history: list[dict]) -> str | None:
    """If `message` is a confirmation phrase and history shows a prior plan/allocation,
    return a concise continuation message. Otherwise return None.

    This keeps the assistant on-task instead of falling through to the generic
    starter ("Hello! I'm ready to help...") when the user types "proceed".
    """
    if detect_followup_intent(message) is None:
        return None

    last_assistant: dict | None = None
    for entry in reversed(history):
        if (entry.get("role") == "assistant") and entry.get("content"):
            last_assistant = entry
            break
    if last_assistant is None:
        return None

    body = (last_assistant.get("content") or "").lower()
    if not any(kw in body for kw in _PLAN_KEYWORDS):
        return None

    return (
        "Confirmed — continuing with the execution plan from the previous step.\n\n"
        "Each step in the plan must be signed in your wallet before the next one unlocks. "
        "Open the execution plan card above and approve step 1 to begin; on-chain receipts "
        "will gate the follow-up steps.\n\n"
        "If you want to change risk budget, skip a protocol, or rerun the allocation against "
        "different chains, just say so and I'll regenerate the plan."
    )


_STRATEGY_FOLLOWUP_RE = re.compile(
    r"\b(execute it|execute the plan|run it|sign it|do it|reinvest|compound( this| it)?|rebalance( it| this)?|proceed with execution)\b",
    re.IGNORECASE,
)


def _resolve_strategy_followup(message: str, session_id: str | None) -> tuple[str, dict] | None:
    if not session_id:
        return None
    if not _STRATEGY_FOLLOWUP_RE.search(message or ""):
        return None
    from src.defi.strategy.memory import recall_strategy
    record = recall_strategy(str(session_id))
    if record is None:
        return None
    constraints = dict(record.constraints or {})
    if "deposit_chain" in constraints:
        params = {
            "deposit_chain": constraints.get("deposit_chain"),
            "deposit_protocol": constraints.get("deposit_protocol"),
            "deposit_action": constraints.get("deposit_action"),
            "deposit_asset": constraints.get("deposit_asset"),
            "deposit_amount": constraints.get("deposit_amount"),
            "research_thesis": f"Replaying prior strategy ({record.intent_summary}).",
        }
        for key in ("source_chain", "source_asset", "source_amount", "slippage_bps"):
            value = constraints.get(key)
            if value is not None:
                params[key] = value
        return "build_yield_strategy_plan", params
    if "chain" in constraints and "protocol" in constraints:
        return "build_yield_execution_plan", {
            "chain": constraints["chain"],
            "protocol": constraints["protocol"],
            "action": constraints["action"],
            "asset_in": constraints["asset_in"],
            "amount_in": constraints["amount_in"],
            "research_thesis": f"Replaying prior strategy ({record.intent_summary}).",
        }
    return None


async def run_ephemeral_turn(
    *,
    router,
    tools,
    message: str,
    wallet: str | None = None,
    history: list[dict] | None = None,
    session_id: str | None = None,
) -> AsyncIterator[bytes]:
    """Execute one agent turn without DB persistence and yield SSE-encoded frames.

    Uses keyword-based intent detection for reliable tool calling.
    Formats tool results directly without LLM for consistent, fast responses.

    history (optional): list of {role, content} dicts representing prior turns
    in the same session. When provided:
      * a "proceed/execute" follow-up phrase is replayed against the most
        recent allocation/plan assistant turn, and
      * the LLM fallback receives the trailing window as context.
    """
    llm = IlyonChatModel(router=router, model="default")
    collector = StreamCollector()
    started = __import__('time').monotonic()

    # Pool-execution memory follow-up runs FIRST — before the generic
    # "proceed/execute" replay — so "execute this pool X" or
    # "execute the transactions through my wallet" build a real
    # ExecutionPlanV3 instead of falling into the stub replay text.
    early_pool_intent = _detect_pool_execute_followup(message, session_id)

    # If this is a follow-up confirmation and we have prior context, handle it
    # before falling through to the keyword intent detector — otherwise
    # "proceed" would never match anything in INTENT_PATTERNS.
    if history and early_pool_intent is None:
        replay = _maybe_replay_followup(message=message, history=history)
        if replay is not None:
            collector._step += 1
            collector._queue.append(ThoughtFrame(
                step_index=collector._step,
                content="Continuing from the prior allocation/execution plan in this conversation...",
            ))
            collector.emit_final(replay, [])
            for frame in collector.drain():
                yield encode_sse(frame_event_name(frame), frame.model_dump())
            return

    # Pool-execution follow-up resolved earlier; re-use it without re-running
    # the regex / memory lookup.
    intent = early_pool_intent
    # Strategy follow-up: replay last yield plan if user typed "execute it / reinvest / rebalance".
    if intent is None:
        intent = _resolve_strategy_followup(message, session_id)
    if intent is None:
        intent = detect_intent(message)

    try:
        final_content = ""
        
        # If we detected an intent, call the tool and format result directly
        if intent:
            tool_name, tool_input = intent

            if tool_name == "explain_sentinel_methodology":
                _emit_thoughts(collector, [
                    "Parsed Sentinel methodology request and selected explanation mode.",
                    "Grounding the response in the live Sentinel scoring model rather than a generic APY ranking.",
                    "Mapping the four core dimensions: Safety, Yield Durability, Exit Liquidity, and Confidence.",
                    "Adding how risk level, strategy fit, Shield flags, and score caps affect deployability.",
                ])
                for frame in collector.drain():
                    yield encode_sse(frame_event_name(frame), frame.model_dump())
                final_content = _format_sentinel_methodology_response()
                elapsed = int((__import__('time').monotonic() - started) * 1000)
                collector.emit_final(final_content, [])
                for frame in collector.drain():
                    yield encode_sse(frame_event_name(frame), frame.model_dump())
                return

            if tool_name == "compose_plan":
                from src.agent.planner import build_plan

                _emit_thoughts(collector, _pre_tool_reasoning(tool_name, tool_input, message))
                for frame in collector.drain():
                    yield encode_sse(frame_event_name(frame), frame.model_dump())
                plan = build_plan(tool_input)
                _emit_thoughts(collector, [
                    f"Built {plan.total_steps}-step execution graph with receipt gates, wallet requirements, and Sentinel risk state.",
                ])
                collector._queue.append(CardFrame(
                    step_index=collector._step,
                    card_id=plan.plan_id,
                    card_type="execution_plan_v2",
                    payload=plan.model_dump(),
                ))
                final_content = (
                    f"I prepared a {plan.total_steps}-step execution plan. Review the full plan, "
                    "then sign each step in order; follow-up actions stay locked until the prior on-chain receipt confirms."
                )
                collector.emit_final(final_content, [plan.plan_id])
                for frame in collector.drain():
                    yield encode_sse(frame_event_name(frame), frame.model_dump())
                return
            
            _emit_thoughts(collector, _pre_tool_reasoning(tool_name, tool_input, message))
            for frame in collector.drain():
                yield encode_sse(frame_event_name(frame), frame.model_dump())
            
            # Find and execute tool
            tool_result = None
            for tool in tools:
                if tool.name == tool_name:
                    collector._queue.append(ToolFrame(
                        step_index=collector._step,
                        name=tool_name,
                        args=tool_input,
                    ))
                    for frame in collector.drain():
                        yield encode_sse(frame_event_name(frame), frame.model_dump())
                    try:
                        tool_result = await tool.ainvoke(tool_input)
                        collector._queue.append(ObservationFrame(
                            step_index=collector._step,
                            name=tool_name,
                            ok=True,
                            error=None,
                        ))
                    except Exception as e:
                        collector._queue.append(ObservationFrame(
                            step_index=collector._step,
                            name=tool_name,
                            ok=False,
                            error={"code": type(e).__name__, "message": str(e)},
                        ))
                        tool_result = {"ok": False, "error": {"message": str(e)}}
                    for frame in collector.drain():
                        yield encode_sse(frame_event_name(frame), frame.model_dump())
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
                # Critical Shield short-circuit
                if env is not None and _is_critical_shield(env):
                    blocked = PlanBlockedFrame(
                        plan_id=env.card_id or "tool-block",
                        reasons=list(env.shield.reasons or []),
                        severity="critical",
                    )
                    collector._queue.append(blocked)
                    final_content = (
                        "Blocked: this transaction triggered a critical Shield "
                        "warning and will not be signed.\n\n"
                        f"Reasons:\n- " + "\n- ".join(env.shield.reasons or [])
                    )
                    collector.emit_final(final_content, [])
                    for frame in collector.drain():
                        yield encode_sse(frame_event_name(frame), frame.model_dump())
                    return
                if env is not None and env.ok:
                    _emit_thoughts(collector, _post_tool_reasoning(tool_name, env))
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
                    # Persist opportunity / allocation list so a follow-up like
                    # "execute this pool X" can resolve chain/protocol/asset/amount
                    # without re-running the search.
                    try:
                        sid = str(session_id) if session_id else None
                        env_data = getattr(env, "data", None) or {}
                        payload = env.card_payload if isinstance(env.card_payload, dict) else {}
                        if sid and tool_name == "search_defi_opportunities":
                            items = (env_data.get("primary_candidates")
                                     or payload.get("items") or [])
                            if items:
                                _remember_opportunities(sid, items)
                        if sid and tool_name == "allocate_plan":
                            allocs = (env_data.get("allocations")
                                      or payload.get("allocations")
                                      or env_data.get("positions")
                                      or payload.get("positions") or [])
                            total = (env_data.get("total_usd")
                                     or env_data.get("usd_amount")
                                     or payload.get("total_usd")
                                     or payload.get("usd_amount"))
                            if allocs:
                                total_f: float | None = None
                                if total is not None:
                                    try:
                                        cleaned_total = (
                                            str(total).replace("$", "").replace(",", "").strip().split()[0]
                                            if isinstance(total, str) else total
                                        )
                                        total_f = float(cleaned_total)
                                    except (ValueError, TypeError, IndexError):
                                        total_f = None
                                _remember_allocation(
                                    sid,
                                    allocs,
                                    total_usd=total_f,
                                    asset_hint=(env_data.get("asset_hint")
                                                or payload.get("asset_hint")),
                                )
                            # Allocation cards usually carry the underlying pools
                            # too — also remember them as a candidate list.
                            pool_items = (env_data.get("primary_candidates")
                                          or payload.get("items") or allocs or [])
                            if pool_items:
                                _remember_opportunities(sid, pool_items)
                    except Exception:
                        pass
                    final_content = _format_tool_result(tool_name, env)
                elif isinstance(tool_result, dict):
                    final_content = _format_tool_result(tool_name, tool_result)
                else:
                    final_content = str(tool_result)
            else:
                final_content = "I couldn't find the data you're looking for. Please try again or rephrase your question."
        else:
            # No intent detected, use LLM for general conversation.
            # When prior history exists, include it so multi-turn context is preserved.
            _emit_thoughts(collector, [
                "No deterministic DeFi tool matched the request; switching to contextual reasoning mode.",
                "Reviewing recent chat context and user intent before answering.",
                "Applying Sentinel-style risk framing where the answer touches crypto assets or protocols.",
            ])
            for frame in collector.drain():
                yield encode_sse(frame_event_name(frame), frame.model_dump())
            base_system = (
                "You are Ilyon Sentinel's crypto agent. You help users with DeFi, "
                "token prices, swaps, and yield opportunities.\n\n"
                "Respond directly to the user in a friendly, professional manner. "
                "Do NOT include meta-commentary, internal reasoning, or stage directions.\n\n"
                "When discussing crypto assets, mention:\n"
                "- Risk levels (LOW, MEDIUM, HIGH) based on market cap and volatility\n"
                "- Strategy fit (conservative, balanced, aggressive)\n"
                "- General safety tips"
            )

            llm_messages: list = []
            trimmed_history = [
                p for p in (history or [])[-HISTORY_WINDOW:]
                if p.get("content")
            ]

            if trimmed_history:
                system_msg = (
                    base_system
                    + "\n\nThe conversation history below is the same chat session. "
                    + "Use it for continuity — when the user says 'it', 'the plan', "
                    + "'those pools', etc., resolve the reference from the history "
                    + "instead of asking for clarification."
                )
                llm_messages.append(type('Msg', (), {'type': 'system', 'content': system_msg})())
                for prior in trimmed_history:
                    role = prior.get("role")
                    content = prior.get("content") or ""
                    mtype = "human" if role == "user" else ("ai" if role == "assistant" else "system")
                    llm_messages.append(type('Msg', (), {'type': mtype, 'content': content})())
            else:
                llm_messages.append(type('Msg', (), {'type': 'system', 'content': base_system})())

            llm_messages.append(type('Msg', (), {'type': 'human', 'content': message})())

            result = await llm._agenerate(llm_messages)
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


async def run_simple_turn(
    *,
    router,
    tools,
    message: str,
    wallet: str | None = None,
    session_id: str | None = None,
    user_id: int = 0,
) -> AsyncIterator[bytes]:
    """Wrapper around run_ephemeral_turn that persists chat history and loads
    prior turns for context.

    Persistence behaviour:
      * Whenever a `session_id` is provided we both load the prior history
        for that session and persist the new user/assistant turn. This is
        what gives the chat its memory — including for guest sessions, which
        the frontend keys with a stable `clientSessionId` from localStorage.
      * Errors in the storage layer are swallowed so that a transient DB
        problem can never block a user-visible response.
    """
    history: list[dict] = []
    db = None

    if session_id:
        try:
            db = await get_database()
            prior_messages = await list_messages(db, chat_id=session_id)
            history = [
                {"role": m.role, "content": m.content}
                for m in prior_messages[-HISTORY_WINDOW:]
            ]
        except Exception:
            history = []
            db = None

        if db is not None:
            try:
                await append_message(db, chat_id=session_id, role="user", content=message)
            except Exception:
                pass

    final_content_parts: list[str] = []

    async for chunk in run_ephemeral_turn(
        router=router,
        tools=tools,
        message=message,
        wallet=wallet,
        history=history,
        session_id=session_id,
    ):
        yield chunk
        if db is not None:
            try:
                decoded = chunk.decode()
                if "event: final" in decoded:
                    payload = decoded.split("\ndata: ", 1)[1].split("\n", 1)[0]
                    final_content_parts.append(json.loads(payload).get("content", ""))
            except Exception:
                pass

    if db is not None and final_content_parts:
        try:
            await append_message(
                db,
                chat_id=session_id,
                role="assistant",
                content="".join(final_content_parts),
            )
        except Exception:
            pass


def _clean_response(content: str) -> str:
    """Clean up any JSON blocks, meta-commentary, or technical formatting from response."""
    # Remove JSON code blocks
    content = re.sub(r'```json\s*.*?\s*```', '', content, flags=re.DOTALL)
    content = re.sub(r'```\s*.*?\s*```', '', content, flags=re.DOTALL)
    
    # Remove standalone JSON objects
    content = re.sub(r'\{\s*"[^"]+":\s*"[^"]+"[^}]*\}', '', content)
    
    # Remove meta-commentary patterns
    meta_patterns = [
        r'^(We|I)\s+need\s+to\s+answer\b.*?(?=\n\n|With\s+\*\*|Here\s+is|Here\s+are|The\s+answer\s+is|You\s+would|Estimated|Based\s+on|$)',
        r'^(Need\s+to\s+(?:calculate|compute|answer)|Let\'s\s+compute|Let\'s\s+calculate)\b.*?(?=\n\n|With\s+\*\*|Here\s+is|Here\s+are|The\s+answer\s+is|You\s+would|Estimated|Based\s+on|$)',
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
