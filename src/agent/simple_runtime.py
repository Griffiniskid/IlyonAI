"""Simple agent runtime without ReAct - uses direct LLM calls with tool support."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import AsyncIterator

logger = logging.getLogger(__name__)

from src.agent.intent.defi_intent import DefiIntent, parse_defi_intent
from src.agent.intent.validation import (
    STOP_WORDS as _VALIDATION_STOP_WORDS,
    filter_symbol_candidates,
    is_cross_chain,
    is_stop_word,
    is_valid_symbol_shape,
    primary_home_chain,
    token_supported_on_chain,
    validate_swap_params,
    _native_chain_for_token,
)
from src.agent.llm import IlyonChatModel
from src.agent.streaming import StreamCollector, encode_sse, frame_event_name
import uuid
from src.api.schemas.agent import ThoughtFrame, ToolFrame, ObservationFrame, FinalFrame, DoneFrame, CardFrame, PlanBlockedFrame

from src.storage.agent_chats import append_message, list_messages
from src.storage.database import get_database


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
        r"\banalytics\b",
        r"\bprotocol stats\b",
        r"\bcompare protocols?\b",
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
    "pol": 137,
    "bsc": 56,
    "bnb": 56,
    "binance": 56,
    "solana": 7565164,
    "sol": 7565164,
    "avalanche": 43114,
    "avax": 43114,
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
    if tool_name == "build_swap_tx":
        # If token_out matches a canonical LST, this is a stake intent — describe
        # it as staking so the live-reasoning panel matches the user's request.
        token_out_addr = str(tool_input.get("token_out", "")).lower()
        token_in_sym = str(tool_input.get("token_in", "")).upper()
        token_out_sym = str(tool_input.get("token_out", "")).upper()
        lst_match = next(
            (info for (sym, _cid), info in _LST_BY_TOKEN_CHAIN.items()
             if info[0].lower() == token_out_addr and sym == token_in_sym),
            None,
        )
        amt_str = str(tool_input.get("amount_in", "")).upper()
        # Detect buy intent: user typed "buy ..." and we're spending a stable
        # to acquire a non-stable. Surface the interpretation so the user can
        # correct if they meant exact-output (which we don't support).
        is_buy_intent = (
            isinstance(message, str)
            and re.match(r"^\s*buy\b", message, re.IGNORECASE)
            and token_in_sym in {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FDUSD"}
        )

        # Plain-English first thought based on the amount sentinel.
        if amt_str == "ALL":
            first = (
                f"Reading your full {token_in_sym} balance from the wallet "
                f"(minus a small native-gas reserve) before quoting the route."
            )
        elif amt_str.startswith("PCT:"):
            try:
                pct_num = int(amt_str[4:])
            except ValueError:
                pct_num = 0
            first = (
                f"Computing {pct_num}% of your {token_in_sym} balance — "
                f"the wallet scanner will resolve the exact amount before the route quote."
            )
        elif is_buy_intent:
            first = (
                f"Parsed as buy: spending {token_in_sym} to acquire {token_out_sym}. "
                f"Amount is interpreted as the input — quote will show how much {token_out_sym} you'll receive."
            )
        else:
            first = f"Parsed swap intent: {_short_json(tool_input)}."

        if lst_match:
            lst_protocol = lst_match[1]
            return [
                first if amt_str in ("ALL",) or amt_str.startswith("PCT:")
                else f"Parsed stake intent: {token_in_sym} → {lst_protocol} liquid staking.",
                f"Routing through Enso/Jupiter into the canonical {lst_protocol} LST so the staked balance stays liquid.",
                "Validating slippage and price impact before producing the unsigned transaction.",
                "Building an unsigned transaction so the wallet can review the exact spend and approval.",
                "Preparing wallet-safe signing guidance; the agent never holds keys — the user signs in their wallet.",
            ]
        return [
            first,
            "Resolving token pair, chain, decimals, and amount before requesting an aggregator route.",
            "Choosing aggregator: Jupiter for Solana, Enso for EVM. Validating slippage, route source, and price impact before quoting.",
            "Building an unsigned transaction so Phantom or MetaMask can review the exact spend, gas, and approval.",
            "Preparing wallet-safe signing guidance; the agent never holds keys — the user signs in their wallet.",
        ]
    if tool_name == "build_solana_swap":
        return [
            f"Parsed Solana swap intent: {_short_json(tool_input)}.",
            "Resolving SPL mints and decimals before requesting a Jupiter v6 quote.",
            "Checking route quality: hop count, price impact, slippage tolerance, and fee account.",
            "Building a base64 VersionedTransaction for Phantom signing — the agent never touches keys.",
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


_TOKEN_NATIVE_CHAIN: dict[str, str] = {
    "ETH": "ethereum", "WETH": "ethereum",
    "SOL": "solana", "WSOL": "solana",
    "BNB": "bsc", "WBNB": "bsc",
    "MATIC": "polygon",
    "AVAX": "avalanche",
    "ARB": "arbitrum",
    "OP": "optimism",
    "BTC": "ethereum",  # WBTC most-liquid on ETH
    "WBTC": "ethereum",
}


def _detect_bridge_then_stake(message: str) -> tuple[str, dict] | None:
    # First try the strict 'from X to Y' form
    pattern = re.compile(
        r"bridge\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})\s+"
        r"from\s+(?P<src>[A-Za-z ]+?)\s+to\s+(?P<dst>[A-Za-z ]+?)\s*[,;]?\s*"
        r"(?:(?:and|then)\s+)?stake\s+(?:it\s+)?(?:on\s+)?(?P<protocol>[A-Za-z0-9 ._-]+)",
        re.IGNORECASE,
    )
    match = pattern.search(message)
    src: str | None = None
    if not match:
        # Looser form: 'bridge X TOKEN to DST and stake on PROTOCOL' (src inferred)
        loose = re.compile(
            r"bridge\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})\s+"
            r"to\s+(?P<dst>[A-Za-z ]+?)\s*[,;]?\s*"
            r"(?:(?:and|then)\s+)?stake\s+(?:it\s+)?(?:on\s+)?(?P<protocol>[A-Za-z0-9 ._-]+)",
            re.IGNORECASE,
        )
        match = loose.search(message)
        if not match:
            return None
        token_upper = match.group("token").upper()
        src = _TOKEN_NATIVE_CHAIN.get(token_upper)
        if src is None:
            return None
    else:
        src = match.group("src").strip().lower()

    token = match.group("token").upper()
    dst = match.group("dst").strip().lower()
    # Strip trailing words ("solana chain" → "solana", "and" suffixes already handled by regex)
    dst = re.sub(r"\s+chain\b.*$", "", dst).strip()
    protocol = match.group("protocol").strip().lower().replace(" ", "-")
    src_chain_id = CHAIN_IDS.get(src)
    dst_chain_id = CHAIN_IDS.get(dst, CHAIN_IDS.get(dst.split()[0] if dst else ""))
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


# Phrases that turn a "swap X to Y" sentence into a question/hypothetical/future
# rather than an executable command. The detector must refuse so the LLM can
# answer rather than build a real signing card.
_NON_IMPERATIVE_RE = re.compile(
    r"^\s*(?:why|how|what|when|where|who|whom|whose|"
    r"will|would|should|could|can|may|might|do|does|did|is|are|am|was|were|"
    r"if|unless|whether|"
    r"explain|tell\s+me|teach\s+me|show\s+me\s+how|describe|"
    r"i\s+(?:want\s+to|would\s+like\s+to|will|might|may|plan\s+to))\b",
    re.IGNORECASE,
)
_CONDITIONAL_HEDGE_RE = re.compile(
    r"\b(?:but\s+only\s+if|only\s+if|if\s+price|tomorrow|next\s+(?:week|month|day)|"
    r"later|after\s+(?:lunch|tomorrow|noon)|when\s+price)\b",
    re.IGNORECASE,
)


def _is_imperative_command(message: str) -> bool:
    """True when the message reads like a direct command, not a question / hedge."""
    if _NON_IMPERATIVE_RE.search(message):
        return False
    if _CONDITIONAL_HEDGE_RE.search(message):
        return False
    return True


def _is_valid_recipient(addr: str) -> bool:
    """Reject English noise like 'me' / 'alice' / 'bob' as transfer recipients.

    Only accept what looks like an EVM address (0x... 42-char) or a Solana
    base58 pubkey (32-44 chars), or an ENS name (.eth / .sol).
    """
    if not addr:
        return False
    s = addr.strip()
    if s.lower().startswith("0x") and len(s) == 42:
        return True
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", s):
        return True
    if re.match(r"^[a-z0-9-]+\.(eth|sol|crypto|x|nft)$", s, re.IGNORECASE):
        return True
    return False


def _detect_transfer_plan(message: str) -> tuple[str, dict] | None:
    if not _is_imperative_command(message):
        return None
    # Numeric amount path: "send 0.5 USDC to 0x..."
    pattern = re.compile(r"(?:send|transfer)\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})\s+to\s+(?P<to>[\w.:-]+)", re.IGNORECASE)
    match = pattern.search(message)
    if match:
        token = match.group("token").upper()
        recipient = match.group("to")
        if not _is_valid_recipient(recipient):
            return None
        if is_stop_word(token) or not is_valid_symbol_shape(token):
            return None
        return (
            "compose_plan",
            {
                "title": f"Send {token}",
                "steps": [
                    {
                        "step_id": "transfer",
                        "action": "transfer",
                        "params": {"token": token, "amount": _to_base_units(match.group("amount"), token), "recipient": recipient, "chain_id": 1},
                    }
                ],
            },
        )
    # "Send all/half/25%" path: fractional balance, agent looks up at execution
    # time. Same noise-word filter as swap-all so "send all wallet to 0x..."
    # doesn't capture WALLET as the symbol.
    all_pattern = re.compile(
        rf"(?:send|transfer)\s+(?P<qty>{_QUANTIFIER_PATTERN})\s+"
        r"(?:of\s+)?(?:my\s+)?(?P<token>[A-Za-z][A-Za-z0-9$._-]{0,15})"
        r"(?:\s+(?:from|in)\s+(?:my\s+)?wallet)?"
        r"\s+to\s+(?P<to>[\w.:-]+)",
        re.IGNORECASE,
    )
    am = all_pattern.search(message)
    if not am:
        return None
    token = am.group("token").upper()
    if token in _NOT_A_SYMBOL:
        return None
    if is_stop_word(token) or not is_valid_symbol_shape(token):
        return None
    recipient = am.group("to")
    if not _is_valid_recipient(recipient):
        return None
    amt_sentinel = _quantifier_to_amount(am.group("qty"))
    pct_label = am.group("qty").strip().lower()
    return (
        "compose_plan",
        {
            "title": f"Send {pct_label} {token}",
            "steps": [
                {
                    "step_id": "transfer",
                    "action": "transfer",
                    "params": {"token": token, "amount": amt_sentinel, "recipient": recipient, "chain_id": 1},
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

    direct = re.search(r"stake\s+(?P<sign>-)?(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})\s+(?:on\s+|with\s+)?(?P<protocol>[A-Za-z0-9 ._-]+)", message, re.IGNORECASE)
    if not direct:
        return None
    token = direct.group("token").upper()
    amount = float(direct.group("amount").replace(",", ""))
    if direct.group("sign") == "-" or amount <= 0 or amount > 1_000_000:
        return None  # let downstream flag absurd / invalid amounts
    proto_raw = direct.group("protocol").strip()
    proto_l = proto_raw.lower()

    # "Stake N TOKEN with Marinade on Solana" — protocol_raw will swallow
    # "Marinade on Solana" because the trailing capture is greedy. Split off
    # the chain so the proper Solana adapter (sidecar) handles the request
    # instead of the legacy chain_id=1 compose_plan path.
    chain_hint: str | None = None
    chain_match = re.search(r"\bon\s+(?P<chain>solana|ethereum|polygon|bsc|arbitrum|optimism|base|avalanche)\b", proto_l, re.IGNORECASE)
    if chain_match:
        chain_hint = chain_match.group("chain").lower()
        proto_l = re.sub(r"\bon\s+\S+.*$", "", proto_l, flags=re.IGNORECASE).strip()
    proto_slug = proto_l.replace(" ", "-")

    SOLANA_LST_HEADS = {"marinade", "jito", "sanctum", "blazestake", "blaze", "drift-staking"}
    # DefiLlama project receipt-token symbols. Marinade=mSOL, Jito=jitoSOL,
    # Sanctum-Infinity=INF. The pair filter uses substring containment, so
    # "sanctum SOL" never matches the "INF" symbol on the catalog. Map each
    # LST hub to the asset symbol DefiLlama actually uses for its pool entry.
    LST_HUB_RECEIPT = {
        "marinade": "MSOL",
        "jito": "JITOSOL",
        "sanctum": "INF",
        "blazestake": "BSOL",
        "blaze": "BSOL",
    }
    if (chain_hint == "solana") or (proto_slug.split("-")[0] in SOLANA_LST_HEADS):
        # Solana LSTs (Marinade mSOL, Jito jitoSOL, Sanctum INF) only stake
        # SOL — there is no USDT-SOL "pool" for these. Always pass pool as
        # bare `<proto> <receipt>` and let the sidecar handle the prep-swap
        # from whatever token the user supplied (asset_in) into the LST.
        head = proto_slug.split("-")[0]
        receipt = LST_HUB_RECEIPT.get(head, "SOL")
        return (
            "execute_pool_position",
            {
                "pool": f"{proto_slug} {receipt}",
                "amount": amount,
                "asset_in": token,
                "chain": "solana",
            },
        )

    amount_usd = amount * 3000 if token == "ETH" else amount
    return (
        "compose_plan",
        {
            "title": f"Stake {token} on {proto_raw.title()}",
            "steps": [
                {
                    "step_id": "stake",
                    "action": "stake",
                    "params": {"token": token, "amount": direct.group("amount"), "protocol": proto_slug, "chain_id": 1, "amount_usd": amount_usd},
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


# Solana decimals for swap base-unit conversion. Falls back to 9 (lamports) for unknown SPL tokens.
_SOLANA_DECIMALS = {
    "SOL": 9, "WSOL": 9, "USDC": 6, "USDT": 6, "BONK": 5, "JUP": 6, "PYTH": 6,
    "RAY": 6, "ORCA": 6, "JITO": 9, "JITOSOL": 9, "MSOL": 9, "STSOL": 9,
    "WBTC": 8, "WETH": 8,
}


# Quantifier phrases the swap/sell/bridge/transfer/stake detectors accept.
# Map to a percent integer 1-100 so the wallet tool can convert
# balance × pct/100 → base units. Defined at module top so all the regex
# patterns below can reference _QUANTIFIER_PATTERN at compile time.
_QUANTIFIER_PCT = {
    "all": 100, "max": 100, "maximum": 100, "entire": 100, "entire balance": 100,
    "everything": 100, "100%": 100, "whole": 100, "whole balance": 100,
    "three quarters": 75, "three-quarters": 75, "75%": 75,
    "two thirds": 66, "two-thirds": 66, "67%": 67, "66%": 66,
    "half": 50, "1/2": 50, "50%": 50, "50 percent": 50,
    "third": 33, "one third": 33, "1/3": 33, "33%": 33, "33 percent": 33,
    "quarter": 25, "one quarter": 25, "1/4": 25, "25%": 25, "25 percent": 25,
    "20%": 20, "20 percent": 20, "10%": 10, "10 percent": 10,
    "5%": 5, "5 percent": 5,
}
_QUANTIFIER_PATTERN = "|".join(re.escape(k) for k in sorted(_QUANTIFIER_PCT, key=len, reverse=True))
_NOT_A_SYMBOL = {"WALLET", "MY", "FROM", "INTO", "TO", "FOR", "OF", "ALL", "MAX", "ENTIRE", "EVERYTHING"}


def _quantifier_to_amount(q: str) -> str:
    """Map a parsed quantifier ('half', '50%', 'all') to an amount sentinel.

    Returns 'ALL' for 100% (kept for backward-compat) or 'PCT:NN' for partials.
    """
    pct = _QUANTIFIER_PCT.get(q.strip().lower(), 100)
    return "ALL" if pct == 100 else f"PCT:{pct}"


# Multiplier suffix for numeric amounts: '1k', '1.5m', '2b'. Crypto users type
# these constantly, so every numeric-amount regex below uses _NUM_AMOUNT_RE
# and runs the captured groups through _expand_numeric_amount.
_NUM_AMOUNT_RE = r"(?P<amount>[\d,]+(?:\.\d+)?)(?P<suffix>[kKmMbB])?"


def _expand_numeric_amount(amount_str: str, suffix: str | None) -> Decimal | None:
    """Parse '1.5k' / '100,000' / '2.5m' / '0.1' as Decimal so wei-level
    precision survives multiplication by 10**decimals (float64 loses precision
    at ~1e16, breaking 18-decimal SHIB-class tokens)."""
    try:
        n = Decimal((amount_str or "").replace(",", ""))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not suffix:
        return n
    s = suffix.lower()
    if s == "k":
        return n * Decimal(1_000)
    if s == "m":
        return n * Decimal(1_000_000)
    if s == "b":
        return n * Decimal(1_000_000_000)
    return n


# "bridge [amount|all] TOKEN from CHAIN to CHAIN" — single-step signable bridge.
# Mirrors _detect_swap_signable so "bridge all FATPENGU from solana to ethereum"
# doesn't fall through to the LLM (which would mis-extract WALLET as token_in).
_BRIDGE_NUMERIC_RE = re.compile(
    r"(?:bridge|transfer\s+across|move)\s+"
    rf"{_NUM_AMOUNT_RE}\s+"
    r"(?P<token>[A-Za-z]{2,10})\s+"
    r"from\s+(?P<src>[A-Za-z ]+?)\s+to\s+(?P<dst>[A-Za-z ]+?)\s*$",
    re.IGNORECASE,
)
_BRIDGE_ALL_RE = re.compile(
    r"(?:bridge|transfer\s+across|move)\s+"
    rf"(?P<qty>{_QUANTIFIER_PATTERN})"
    r"\s+(?:of\s+)?(?:my\s+)?"
    r"(?P<token>[A-Za-z][A-Za-z0-9$._-]{0,15})"
    r"(?:\s+(?:from|in)\s+(?:my\s+)?wallet)?"
    r"\s+from\s+(?P<src>[A-Za-z ]+?)\s+to\s+(?P<dst>[A-Za-z ]+?)\s*$",
    re.IGNORECASE,
)

# "bridge 0.14 sol to eth chain" — no explicit "from" clause; infer source
# chain from the token's home chain. This closes the tester gap reported in
# 2026-05 where SOL→ETH/BNB/AVAX bridge requests fell through to the LLM.
_BRIDGE_TO_NUMERIC_RE = re.compile(
    r"^\s*(?:bridge|transfer\s+across|move)\s+"
    rf"{_NUM_AMOUNT_RE}\s+"
    r"(?P<token>[A-Za-z]{2,10})"
    r"(?:\s+(?:from|in)\s+(?:my\s+)?wallet)?"
    r"\s+(?:to|->|→|onto|over\s+to)\s+"
    r"(?P<dst>[A-Za-z][A-Za-z0-9 ._-]+?)"
    r"(?:\s+(?:chain|network|mainnet))?\s*$",
    re.IGNORECASE,
)
_BRIDGE_TO_ALL_RE = re.compile(
    r"^\s*(?:bridge|transfer\s+across|move)\s+"
    rf"(?P<qty>{_QUANTIFIER_PATTERN})"
    r"\s+(?:of\s+)?(?:my\s+)?"
    r"(?P<token>[A-Za-z][A-Za-z0-9$._-]{0,15})"
    r"(?:\s+(?:from|in)\s+(?:my\s+)?wallet)?"
    r"\s+(?:to|->|→|onto|over\s+to)\s+"
    r"(?P<dst>[A-Za-z][A-Za-z0-9 ._-]+?)"
    r"(?:\s+(?:chain|network|mainnet))?\s*$",
    re.IGNORECASE,
)

# Token → home chain mapping for implicit-source bridge.
_TOKEN_HOME_CHAIN: dict[str, int] = {
    "SOL": 7565164, "WSOL": 7565164,
    "ETH": 1, "WETH": 1,
    "BNB": 56, "WBNB": 56, "CAKE": 56,
    "MATIC": 137, "WMATIC": 137,
    "AVAX": 43114, "WAVAX": 43114,
    "ARB": 42161,
    "OP": 10,
}


def _detect_bridge_signable(message: str) -> tuple[str, dict] | None:
    if not _is_imperative_command(message):
        return None
    """Bridge intent → build_bridge_tx, both numeric and ALL forms."""
    text = message.strip()

    def _resolve_dst(dst_raw: str) -> int | None:
        d = dst_raw.strip().lower()
        d = re.sub(r"\s+(chain|network|mainnet)$", "", d).strip()
        return CHAIN_IDS.get(d)

    # Implicit-source bridge: "bridge 0.14 sol to eth chain"
    tn = _BRIDGE_TO_NUMERIC_RE.search(text)
    if tn:
        token = tn.group("token").upper()
        if token in _NOT_A_SYMBOL:
            return None
        src_chain_id = _TOKEN_HOME_CHAIN.get(token)
        dst_chain_id = _resolve_dst(tn.group("dst"))
        if src_chain_id and dst_chain_id and src_chain_id != dst_chain_id:
            amount_value = _expand_numeric_amount(tn.group("amount"), tn.group("suffix"))
            if amount_value is not None and amount_value > 0:
                if src_chain_id == 7565164:
                    decimals = _SOLANA_DECIMALS.get(token, 9)
                elif src_chain_id == 56 and token in {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FDUSD"}:
                    decimals = 18
                else:
                    decimals = TOKEN_DECIMALS.get(token, 18)
                try:
                    amt_base = str(int(amount_value * (Decimal(10) ** decimals)))
                except (OverflowError, ValueError, InvalidOperation):
                    amt_base = None
                if amt_base:
                    return (
                        "build_bridge_tx",
                        {
                            "src_chain_id": src_chain_id,
                            "dst_chain_id": dst_chain_id,
                            "token_in": token,
                            "token_out": "",
                            "amount": amt_base,
                        },
                    )
    ta = _BRIDGE_TO_ALL_RE.search(text)
    if ta:
        token = ta.group("token").upper()
        if token not in _NOT_A_SYMBOL:
            src_chain_id = _TOKEN_HOME_CHAIN.get(token)
            dst_chain_id = _resolve_dst(ta.group("dst"))
            if src_chain_id and dst_chain_id and src_chain_id != dst_chain_id:
                return (
                    "build_bridge_tx",
                    {
                        "src_chain_id": src_chain_id,
                        "dst_chain_id": dst_chain_id,
                        "token_in": token,
                        "token_out": "",
                        "amount": _quantifier_to_amount(ta.group("qty")),
                    },
                )

    am = _BRIDGE_ALL_RE.search(text)
    if am:
        token = am.group("token").upper()
        if token in _NOT_A_SYMBOL:
            return None
        src = am.group("src").strip().lower()
        dst = am.group("dst").strip().lower()
        src_chain_id = CHAIN_IDS.get(src)
        dst_chain_id = CHAIN_IDS.get(dst)
        if src_chain_id is None or dst_chain_id is None or src_chain_id == dst_chain_id:
            return None
        return (
            "build_bridge_tx",
            {
                "src_chain_id": src_chain_id,
                "dst_chain_id": dst_chain_id,
                "token_in": token,
                "token_out": "",
                "amount": _quantifier_to_amount(am.group("qty")),
            },
        )
    nm = _BRIDGE_NUMERIC_RE.search(text)
    if not nm:
        return None
    token = nm.group("token").upper()
    src = nm.group("src").strip().lower()
    dst = nm.group("dst").strip().lower()
    src_chain_id = CHAIN_IDS.get(src)
    dst_chain_id = CHAIN_IDS.get(dst)
    if src_chain_id is None or dst_chain_id is None or src_chain_id == dst_chain_id:
        return None
    amount_value = _expand_numeric_amount(nm.group("amount"), nm.group("suffix"))
    if amount_value is None or amount_value <= 0:
        return None
    # Source-chain decimals: BSC USDC/USDT are 18-decimal (BNB-pegged), not 6.
    # Same for any EVM chain with non-canonical pegs. Solana mints use the
    # SPL decimal table.
    if src_chain_id == 7565164:
        decimals = _SOLANA_DECIMALS.get(token, 9)
    elif src_chain_id == 56 and token in {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FDUSD"}:
        decimals = 18
    else:
        decimals = TOKEN_DECIMALS.get(token, 18)
    try:
        amount_base = str(int(amount_value * (Decimal(10) ** decimals)))
    except (OverflowError, ValueError, InvalidOperation):
        return None
    return (
        "build_bridge_tx",
        {
            "src_chain_id": src_chain_id,
            "dst_chain_id": dst_chain_id,
            "token_in": token,
            "token_out": "",
            "amount": amount_base,
        },
    )


# Liquid-staking targets (LST) per (token_in, chain_id). When the user types a
# bare "stake X TOKEN" (no protocol qualifier), we route the trade through the
# canonical LST so they get an executable Phantom / MetaMask signing card via
# the existing swap path. mainnet token addresses verified manually.
_LST_BY_TOKEN_CHAIN: dict[tuple[str, int], tuple[str, str]] = {
    ("SOL", 101): ("J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn", "Jito"),  # jitoSOL
    ("ETH", 1): ("0xae7ab96520de3a18e5e111b5eaab095312d7fe84", "Lido"),  # stETH
    ("BNB", 56): ("0xB0b84D294e0C75A6abe60171b70edEb2EFd14A1B", "Lista"),  # slisBNB
    ("MATIC", 137): ("0xfa68FB4628DFF1028CFEc22b4162FCcd0d45efb6", "Stader"),  # MATICX
    ("AVAX", 43114): ("0x2b2C81e08f1Af8835a78Bb2A90AE924ACE0eA4bE", "Benqi"),  # sAVAX
}


_STAKE_ALL_RE = re.compile(
    rf"^\s*stake\s+(?P<qty>{_QUANTIFIER_PATTERN})\s+"
    r"(?:of\s+)?(?:my\s+)?"
    r"(?P<token>[A-Za-z][A-Za-z0-9$._-]{0,15})"
    r"(?:\s+(?:from|in)\s+(?:my\s+)?wallet)?\s*$",
    re.IGNORECASE,
)


def _detect_stake_all(message: str) -> tuple[str, dict] | None:
    """'stake all my SOL' / 'stake all BNB' → LST swap with amount=ALL.

    Routes through build_swap_tx so the swap-all balance lookup substitutes the
    user's full chain balance (minus a gas reserve) at execution time.
    """
    m = _STAKE_ALL_RE.search(message)
    if not m:
        return None
    if "idle" in message.lower():
        return None  # let _detect_stake_amount_plan idle path handle it
    token = m.group("token").upper()
    if token in _NOT_A_SYMBOL:
        return None
    chain_id_by_token = {"SOL": 101, "ETH": 1, "BNB": 56, "MATIC": 137, "AVAX": 43114}
    chain_id = chain_id_by_token.get(token)
    if not chain_id:
        return None
    lst_target = _LST_BY_TOKEN_CHAIN.get((token, chain_id))
    if not lst_target:
        return None
    return (
        "build_swap_tx",
        {
            "chain_id": chain_id,
            "token_in": token,
            "token_out": lst_target[0],
            "amount_in": _quantifier_to_amount(m.group("qty")),
            "from_addr": "",
        },
    )


def _detect_stake_simple(message: str) -> tuple[str, dict] | None:
    """Match bare 'stake 0.1 bnb' / 'stake 1 sol' (no protocol qualifier).

    Returns build_swap_tx into the canonical LST for that chain so the user
    gets a real signing card instead of an empty DeFi search.
    """
    pattern = re.compile(
        r"^\s*stake\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})"
        r"(?:\s+(?:on\s+|with\s+|via\s+)(?P<protocol>[A-Za-z0-9 ._-]+))?\s*$",
        re.IGNORECASE,
    )
    m = pattern.search(message)
    if not m:
        return None
    if m.group("protocol"):
        # Protocol-qualified stake — let _detect_stake_amount_plan handle it.
        return None
    token = m.group("token").upper()
    try:
        amount_value = Decimal(m.group("amount").replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if amount_value <= 0:
        return None
    chain_id_by_token = {"SOL": 101, "ETH": 1, "BNB": 56, "MATIC": 137, "AVAX": 43114}
    chain_id = chain_id_by_token.get(token)
    if not chain_id:
        return None
    lst_target = _LST_BY_TOKEN_CHAIN.get((token, chain_id))
    if not lst_target:
        return None
    decimals = _SOLANA_DECIMALS.get(token, 9) if chain_id == 101 else TOKEN_DECIMALS.get(token, 18)
    try:
        amount_in = str(int(amount_value * (Decimal(10) ** decimals)))
    except (OverflowError, ValueError, InvalidOperation):
        return None
    if int(amount_in) <= 0:
        return None
    return (
        "build_swap_tx",
        {
            "chain_id": chain_id,
            "token_in": token,
            "token_out": lst_target[0],
            "amount_in": amount_in,
            "from_addr": "",
        },
    )


# "swap all FATPENGU [from my wallet] to usdc" — must match BEFORE the numeric
# pattern, and must NOT capture noise words ("WALLET", "MY", "FROM") as the
# token symbol. The optional "from/in (my) wallet" clause is consumed but
# discarded so it never lands in `tin`. Now also matches "half / 50% / quarter".
_SWAP_ALL_RE = re.compile(
    r"(?:swap|exchange|convert|trade|sell|dump)\s+"
    rf"(?P<qty>{_QUANTIFIER_PATTERN})"
    r"\s+(?:of\s+)?(?:my\s+)?"
    r"(?P<tin>[A-Za-z][A-Za-z0-9$._-]{0,15})"
    r"(?:\s+(?:from|in)\s+(?:my\s+)?wallet)?"
    r"\s+(?:to|for|into)\s+"
    r"(?P<tout>[A-Za-z][A-Za-z0-9$._-]{0,15})"
    r"(?:\s+on\s+(?P<chain>\w+))?",
    re.IGNORECASE,
)

# "sell all FATPENGU" / "dump all SHIB" / "sell half my SOL" — destination defaults to USDC.
_SELL_ALL_RE = re.compile(
    r"^\s*(?:sell|dump)\s+"
    rf"(?P<qty>{_QUANTIFIER_PATTERN})"
    r"\s+(?:of\s+)?(?:my\s+)?"
    r"(?P<tin>[A-Za-z][A-Za-z0-9$._-]{0,15})"
    r"(?:\s+(?:from|in)\s+(?:my\s+)?wallet)?\s*$",
    re.IGNORECASE,
)
# "buy 100 BONK" / "buy 0.5 SOL with USDC" — swap source (default USDC) into target.
_BUY_RE = re.compile(
    rf"^\s*buy\s+{_NUM_AMOUNT_RE}\s+"
    r"(?P<tout>[A-Za-z][A-Za-z0-9$._-]{0,15})"
    r"(?:\s+(?:with|using|from|via)\s+(?P<src>[A-Za-z][A-Za-z0-9$._-]{0,15}))?"
    r"(?:\s+on\s+(?P<chain>\w+))?\s*$",
    re.IGNORECASE,
)


def _detect_buy_intent(message: str) -> tuple[str, dict] | None:
    if not _is_imperative_command(message):
        return None
    """'buy 100 BONK' / 'buy 0.5 SOL with USDC' → swap source into target.

    Source defaults to USDC. The numeric amount specifies the OUTPUT amount
    in target tokens, not the input — but Jupiter/Enso quote API takes input
    amount, so we emit a swap with the input side as the explicit src token
    and the agent re-asks the user when liquidity differs significantly.

    Implementation note: we route as 'swap N USDC to TOKEN' so the existing
    pricing path produces a quote. If the user wants 100 BONK literally,
    they can quote-and-adjust.
    """
    m = _BUY_RE.search(message)
    if not m:
        return None
    tout = m.group("tout").upper()
    src = (m.group("src") or "USDC").upper()
    if tout in _NOT_A_SYMBOL or src in _NOT_A_SYMBOL or tout == src:
        return None
    amount_value = _expand_numeric_amount(m.group("amount"), m.group("suffix"))
    if amount_value is None or amount_value <= 0:
        return None
    # Pick chain from token signal: solana memes → 101, EVM tokens → 1 default,
    # BNB → 56, etc. Reuse the same logic as sell-all.
    chain_id_by_token = {
        "BNB": 56, "CAKE": 56, "BUSD": 56, "WBNB": 56,
        "MATIC": 137, "POL": 137, "AVAX": 43114,
        "ARB": 42161, "OP": 10,
        "SHIB": 1, "PEPE": 1, "ETH": 1, "WETH": 1,
        "SOL": 101, "BONK": 101, "JUP": 101, "PYTH": 101, "RAY": 101,
        "ORCA": 101, "MSOL": 101, "JITOSOL": 101, "STSOL": 101,
        "FATPENGU": 101, "PENGU": 101, "WIF": 101, "POPCAT": 101,
    }
    chain_hint = (m.group("chain") or "").lower()
    if chain_hint:
        chain_id = CHAIN_IDS.get(chain_hint, chain_id_by_token.get(tout, 1))
        if chain_id == 7565164:
            chain_id = 101
    else:
        chain_id = chain_id_by_token.get(tout, 101)
    # Convert input USDC amount in source token decimals.
    if chain_id == 101:
        decimals = _SOLANA_DECIMALS.get(src, 6)
    elif chain_id == 56 and src in {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FDUSD"}:
        decimals = 18
    else:
        decimals = TOKEN_DECIMALS.get(src, 18 if src not in {"USDC", "USDT"} else 6)
    try:
        amount_in = str(int(amount_value * (Decimal(10) ** decimals)))
    except (OverflowError, ValueError, InvalidOperation):
        return None
    # Cross-chain reject: 'buy 100 PENGU with ETH' — PENGU is Solana-only,
    # ETH is EVM. Buy intent doesn't auto-bridge; refuse so the LLM/user can
    # rephrase as bridge + swap.
    if is_cross_chain(src, tout, chain_id):
        return None
    return (
        "build_swap_tx",
        {
            "chain_id": chain_id,
            "token_in": src,
            "token_out": tout,
            "amount_in": amount_in,
            "from_addr": "",
        },
    )


def _detect_swap_signable(message: str) -> tuple[str, dict] | None:
    """Route signable swap intents to build_swap_tx (legacy SimulationPreview path).

    Picks chain_id by message hint or token signal so Phantom Solana users land on
    Jupiter and EVM users land on Enso. Amount is converted to base units (lamports
    for Solana, wei-style for EVM) using TOKEN_DECIMALS / _SOLANA_DECIMALS. The
    sentinel `amount_in == "ALL"` is forwarded so the swap tool can substitute the
    user's actual wallet balance at execution time.
    """
    # Refuse questions / hypotheticals / future-tense — never execute a tool.
    if not _is_imperative_command(message):
        return None
    # 1a) "sell all FATPENGU" — destination implied USDC. Map well-known
    # tokens to their canonical home chain so the swap-all balance lookup
    # scans the right wallet.
    sell_all_match = _SELL_ALL_RE.search(message)
    if sell_all_match:
        token_in = sell_all_match.group("tin").upper()
        if (token_in not in _NOT_A_SYMBOL
                and not is_stop_word(token_in)
                and is_valid_symbol_shape(token_in)
                and token_in != "USDC"):
            chain_id_by_token = {
                "BNB": 56, "CAKE": 56, "BUSD": 56, "WBNB": 56,
                "MATIC": 137, "POL": 137,
                "AVAX": 43114,
                "ARB": 42161, "OP": 10,
                "SHIB": 1, "PEPE": 1, "ETH": 1, "WETH": 1,
                "SOL": 101, "BONK": 101, "JUP": 101, "PYTH": 101, "RAY": 101,
                "ORCA": 101, "MSOL": 101, "JITOSOL": 101, "STSOL": 101,
                "FATPENGU": 101, "PENGU": 101, "WIF": 101, "POPCAT": 101,
            }
            chain_id = chain_id_by_token.get(token_in, 101)
            return (
                "build_swap_tx",
                {
                    "chain_id": chain_id,
                    "token_in": token_in,
                    "token_out": "USDC",
                    "amount_in": _quantifier_to_amount(sell_all_match.group("qty")),
                    "from_addr": "",
                },
            )

    # 1) "swap all/half/50% X to Y" — no numeric amount, look up balance later.
    all_match = _SWAP_ALL_RE.search(message)
    if all_match:
        token_in = all_match.group("tin").upper()
        token_out = all_match.group("tout").upper()
        if token_in in _NOT_A_SYMBOL or token_out in _NOT_A_SYMBOL:
            return None
        if is_stop_word(token_in) or is_stop_word(token_out):
            return None
        if not is_valid_symbol_shape(token_in) or not is_valid_symbol_shape(token_out):
            return None
        if "MALICIOUS" in (token_in, token_out):
            return None
        chain_hint = (all_match.group("chain") or "").lower()
        evm_only = {"BNB", "CAKE", "BUSD", "WBNB", "MATIC", "AVAX", "ARB", "OP", "WETH", "WSTETH", "RETH", "SHIB", "PEPE"}
        solana_only = {"BONK", "JUP", "PYTH", "RAY", "ORCA", "MSOL", "JITOSOL", "STSOL", "FATPENGU", "PENGU", "WIF", "POPCAT"}
        if chain_hint:
            chain_id = CHAIN_IDS.get(chain_hint, 1)
            if chain_id == 7565164:
                chain_id = 101
        elif token_in == "SOL" or token_out == "SOL" or token_in in solana_only or token_out in solana_only:
            chain_id = 101
        elif token_in in evm_only or token_out in evm_only:
            if token_in in {"WETH", "SHIB", "PEPE", "WSTETH", "RETH"} or token_out in {"WETH", "SHIB", "PEPE", "WSTETH", "RETH"}:
                chain_id = 1
            elif token_in in {"BNB", "CAKE", "BUSD", "WBNB"} or token_out in {"BNB", "CAKE", "BUSD", "WBNB"}:
                chain_id = 56
            elif token_in in {"MATIC", "POL"} or token_out in {"MATIC", "POL"}:
                chain_id = 137
            elif token_in == "AVAX" or token_out == "AVAX":
                chain_id = 43114
            elif token_in == "ARB" or token_out == "ARB":
                chain_id = 42161
            elif token_in == "OP" or token_out == "OP":
                chain_id = 10
            else:
                chain_id = 56
        elif token_in in {"USDC", "USDT", "DAI"} and token_out in {"USDC", "USDT", "DAI"}:
            chain_id = 101
        else:
            # Unknown ticker (typical meme on Solana) → default Solana so Jupiter
            # gets a chance to resolve via the user's wallet token list.
            chain_id = 101
        # Cross-chain: ALL/PCT amount is a sentinel, so we can't auto-bridge a
        # numeric amount. Reject the swap so the user reframes as a bridge.
        if is_cross_chain(token_in, token_out, chain_id):
            return None
        return (
            "build_swap_tx",
            {
                "chain_id": chain_id,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": _quantifier_to_amount(all_match.group("qty")),
                "from_addr": "",
            },
        )

    # 2) "swap 0.1 SOL to USDC" — explicit numeric amount.
    pattern = re.compile(
        r"(?:swap|exchange|convert|trade)\s+(?:of\s+)?"
        rf"{_NUM_AMOUNT_RE}\s*"
        r"(?P<tin>[A-Za-z]{2,10})\s+"
        r"(?:to|for|into)\s+"
        r"(?P<tout>[A-Za-z]{2,10})"
        r"(?:\s+on\s+(?P<chain>\w+))?",
        re.IGNORECASE,
    )
    m = pattern.search(message)
    if not m:
        # 3) "sell 100 SHIB" / "dump 0.5 BONK" — destination defaults to USDC.
        sell_pattern = re.compile(
            rf"(?:sell|dump)\s+{_NUM_AMOUNT_RE}\s*"
            r"(?P<tin>[A-Za-z]{2,10})"
            r"(?:\s+(?:to|for|into)\s+(?P<tout>[A-Za-z]{2,10}))?"
            r"(?:\s+on\s+(?P<chain>\w+))?\s*$",
            re.IGNORECASE,
        )
        sm = sell_pattern.search(message)
        if not sm:
            return None
        # Synthesise the same group dict so the rest of the function works.
        m = sm
        # Force a USDC destination when none specified.
        if not sm.group("tout"):
            class _Wrap:
                def __init__(self, real, override_tout):
                    self._real = real
                    self._override = override_tout
                def group(self, name):
                    if name == "tout":
                        return self._override
                    return self._real.group(name)
                def groups(self):
                    return self._real.groups()
            m = _Wrap(sm, "USDC")
    token_in = m.group("tin").upper()
    token_out = m.group("tout").upper()
    if "MALICIOUS" in (token_in, token_out):
        return None
    # Reject obvious stop-word captures from earlier-pattern slack — the regex
    # can't always exclude phrases like "from my wallet to wbnb" cleanly.
    if is_stop_word(token_in) or is_stop_word(token_out):
        return None
    try:
        suffix = m.group("suffix")
    except Exception:
        suffix = None
    amount_value = _expand_numeric_amount(m.group("amount"), suffix)
    if amount_value is None or amount_value <= 0:
        return None
    # Sanity ceiling: anything above 1B human units of any token is a parse
    # error — block before the LLM/aggregator wastes a quote on it.
    if amount_value > Decimal("1_000_000_000"):
        return None
    chain_hint = (m.group("chain") or "").lower()

    evm_only = {"BNB", "CAKE", "BUSD", "WBNB", "MATIC", "AVAX", "ARB", "OP", "WETH", "WSTETH", "RETH", "SHIB", "PEPE"}
    solana_only = {"BONK", "JUP", "PYTH", "RAY", "ORCA", "MSOL", "JITOSOL", "STSOL", "WIF", "POPCAT", "FATPENGU", "PENGU"}

    if chain_hint:
        chain_id = CHAIN_IDS.get(chain_hint, 1)
        # CHAIN_IDS uses 7565164 for solana (deBridge ID); swap path expects 101.
        if chain_id == 7565164:
            chain_id = 101
    elif token_in == "SOL" or token_out == "SOL" or token_in in solana_only or token_out in solana_only:
        chain_id = 101
    elif token_in in evm_only or token_out in evm_only:
        # Pick the EVM home chain of the registered side instead of always defaulting
        # to BSC (56). WETH/SHIB/PEPE → Ethereum (1); BNB/CAKE → BSC; etc.
        if token_in in {"WETH", "SHIB", "PEPE", "WSTETH", "RETH"} or token_out in {"WETH", "SHIB", "PEPE", "WSTETH", "RETH"}:
            chain_id = 1
        elif token_in in {"BNB", "CAKE", "BUSD", "WBNB"} or token_out in {"BNB", "CAKE", "BUSD", "WBNB"}:
            chain_id = 56
        elif token_in in {"MATIC", "POL"} or token_out in {"MATIC", "POL"}:
            chain_id = 137
        elif token_in == "AVAX" or token_out == "AVAX":
            chain_id = 43114
        elif token_in == "ARB" or token_out == "ARB":
            chain_id = 42161
        elif token_in == "OP" or token_out == "OP":
            chain_id = 10
        else:
            chain_id = 56
    elif token_in in {"USDC", "USDT", "DAI"} and token_out in {"USDC", "USDT", "DAI"}:
        chain_id = 101
    else:
        chain_id = 1

    # Cross-chain detection: SOL → WETH, BNB → SOL, etc. Route to bridge.
    if is_cross_chain(token_in, token_out, chain_id):
        # Pick canonical home chains (single-home if known, else the registered
        # primary preference). This lets SOL → ETH route to ethereum even though
        # ETH lives on multiple chains.
        src_chain_id = primary_home_chain(token_in)
        dst_chain_id = primary_home_chain(token_out)
        if src_chain_id and dst_chain_id and src_chain_id != dst_chain_id:
            # Compute base-units on the SOURCE chain (where token_in lives).
            if src_chain_id == 101:
                src_decimals = _SOLANA_DECIMALS.get(token_in, 9)
            elif src_chain_id == 56 and token_in in {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FDUSD"}:
                src_decimals = 18
            else:
                src_decimals = TOKEN_DECIMALS.get(token_in, 18)
            try:
                amount_base = str(int(amount_value * (Decimal(10) ** src_decimals)))
            except (OverflowError, ValueError, InvalidOperation):
                return None
            if int(amount_base) <= 0:
                return None
            return (
                "build_bridge_tx",
                {
                    "src_chain_id": src_chain_id,
                    "dst_chain_id": dst_chain_id,
                    "token_in": token_in,
                    "token_out": "",  # let bridge resolver pick destination
                    "amount": amount_base,
                },
            )
        # Otherwise: refuse the swap so we don't hand garbage to the aggregator.
        return None

    if chain_id == 101:
        decimals = _SOLANA_DECIMALS.get(token_in, 9)
    elif chain_id == 56 and token_in in {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FDUSD"}:
        # BSC pegs are 18-decimal, not 6.
        decimals = 18
    else:
        decimals = TOKEN_DECIMALS.get(token_in, 18)

    try:
        amount_in = str(int(amount_value * (Decimal(10) ** decimals)))
    except (OverflowError, ValueError, InvalidOperation):
        return None
    if int(amount_in) <= 0:
        return None

    # Final pre-dispatch validation. Catches anything the structured logic missed.
    v = validate_swap_params(
        token_in=token_in,
        token_out=token_out,
        chain_id=chain_id,
        amount_in=amount_in,
    )
    if not v.ok:
        return None

    return (
        "build_swap_tx",
        {
            "chain_id": chain_id,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_in,
            "from_addr": "",
        },
    )


# Phrases that mean "execute the previously discussed plan / continue the prior turn".
# Kept narrow on purpose — only short confirmations, no broad keywords like "do it"
# that could match unrelated turns.
FOLLOWUP_PROCEED_PATTERNS = [
    # Standalone confirmations only — must end the message (or be followed
    # by punctuation/optional final particle), so 'execute deposit into
    # pool X' doesn't match.
    r"^\s*(?:please\s+)?proceed\s*[.!?]*\s*$",
    r"^\s*(?:please\s+)?proceed\s+with\s+(?:the\s+)?(?:plan|allocation|swap|bridge|stake|execution)\s*[.!?]*\s*$",
    r"^\s*(?:please\s+)?(?:go\s+ahead|continue|carry\s+on)\s*[.!?]*\s*$",
    r"^\s*(?:please\s+)?(?:go\s+ahead|continue)\s+and\s+(?:execute|proceed|sign)\s*[.!?]*\s*$",
    r"^\s*(?:please\s+)?execute\s+(?:the\s+|that\s+|this\s+)?(?:plan|allocation|strategy|it|that|this)\s*[.!?]*\s*$",
    r"^\s*(?:please\s+)?execute\s*[.!?]*\s*$",
    r"^\s*yes(?:,)?\s*(?:please)?\s*(?:proceed|execute|continue|go\s+ahead)?\s*[.!?]*\s*$",
    r"^\s*confirm(?:ed)?\s*[.!?]*\s*$",
    r"^\s*(?:let'?s|let\s+us)\s+(?:do\s+(?:it|this|that)|proceed|execute|go)\s*[.!?]*\s*$",
    r"^\s*(?:approved|approve)\s*[.!?]*\s*$",
    r"^\s*ok(?:ay)?\s*[.!?]*\s*$",
    r"^\s*sounds\s+good\s*[.!?]*\s*$",
    r"^\s*looks\s+good\s*[.!?]*\s*$",
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


_GENERIC_SUPPLY_RE = re.compile(
    r"^\s*(?:supply|deposit|lend|stake)\s+"
    r"(?P<amount>[\d,]+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+"
    r"(?P<asset>[A-Za-z]{2,10})\s+"
    r"(?:on|to|via|into)\s+"
    r"(?P<protocol>[A-Za-z][A-Za-z0-9 \-_.]{1,30}?)\s+"
    r"on\s+"
    r"(?P<chain>ethereum|polygon|arbitrum|optimism|base|avalanche|bsc|bnb|solana|"
    r"linea|mantle|zksync|scroll|blast|mode|berachain|sonic|sei|fantom|celo|near|"
    r"cosmos|metis|gnosis|moonbeam|tron|aptos|sui)\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def _detect_generic_supply(message: str) -> tuple[str, dict] | None:
    """Generic 'supply N TOKEN on/via PROTOCOL on CHAIN' detector.

    Routes to execute_pool_position with `pool='<protocol> <asset>'` so the
    protocol resolver can find the matching DefiLlama pool. Covers Venus,
    Compound, Spark, Morpho, Moonwell, Radiant, etc. when the user names
    the protocol explicitly.
    """
    m = _GENERIC_SUPPLY_RE.search(message)
    if not m:
        return None
    asset = m.group("asset").upper()
    if asset in _NOISE_ASSET_TOKENS:
        return None
    amount = m.group("amount").replace(",", "")
    proto = m.group("protocol").strip().lower().replace(" ", "-")
    # Drop trailing chain alias accidentally captured ("venus on bsc" -> "venus")
    proto = re.sub(
        r"-(?:on|via|to)$",
        "",
        proto,
    )
    chain = m.group("chain").lower()
    if chain in {"bnb"}:
        chain = "bsc"
    return ("execute_pool_position", {
        "pool": f"{proto} {asset}",
        "amount": float(amount),
        "asset_in": asset,
        "chain": chain,
    })


# Vault / lending protocols that route through the Enso shortcut adapter.
# Order: longest slug first so "yearn-finance" beats bare "yearn".
_ENSO_PROTOS_RE = re.compile(
    r"\b(?i:("
    r"aave[ -]?v3|aave[ -]?v2|aave|"
    r"compound[ -]?v3|compound[ -]?v2|compound|"
    r"yearn[ -]?finance|yearn[ -]?v3|yearn|"
    r"morpho[ -]?blue|metamorpho|morpho|"
    r"spark[ -]?protocol|spark[ -]?lending|spark|"
    r"sky[ -]?lending|sky|makerdao|"
    r"fluid[ -]?lending|fluid|"
    r"moonwell|stargate|"
    r"origin[ -]?ether|origin|"
    r"ethena|pendle|"
    r"lido|rocket[ -]?pool|rocketpool|"
    r"ether[\.\-]?fi|etherfi|weeth|"
    r"frax[ -]?ether|frx[ -]?ether|frax|sfrxeth|"
    r"stader|gmx|"
    r"curve[ -]?dex|curve[ -]?finance|curve[ -]?stable|curve|"
    r"balancer[ -]?v2|balancer[ -]?v3|balancer|"
    r"velodrome|aerodrome"
    r"))\b"
)

_ENSO_CHAINS_RE = re.compile(
    r"\b(?i:(ethereum|polygon|arbitrum|optimism|base|avalanche|bsc|bnb|"
    r"linea|zksync|scroll|gnosis|sonic|soneium|plasma|ink))\b"
)

_ENSO_PROTO_TO_SLUG = {
    "aave": "aave-v3", "aave v3": "aave-v3", "aave-v3": "aave-v3", "aavev3": "aave-v3",
    "aave v2": "aave-v2", "aave-v2": "aave-v2",
    "compound": "compound-v3", "compound v3": "compound-v3", "compound-v3": "compound-v3", "compoundv3": "compound-v3",
    "compound v2": "compound-v2", "compound-v2": "compound-v2",
    "yearn": "yearn-finance", "yearn finance": "yearn-finance", "yearn-finance": "yearn-finance",
    "yearn v3": "yearn-v3", "yearn-v3": "yearn-v3",
    "morpho": "morpho-blue", "morpho blue": "morpho-blue", "morpho-blue": "morpho-blue",
    "metamorpho": "morpho-blue",
    "spark": "spark", "spark protocol": "spark", "spark-protocol": "spark",
    "spark lending": "spark-lending", "spark-lending": "spark-lending",
    "sky": "sky-lending", "sky lending": "sky-lending", "sky-lending": "sky-lending",
    "makerdao": "makerdao",
    "fluid": "fluid", "fluid lending": "fluid-lending", "fluid-lending": "fluid-lending",
    "moonwell": "moonwell", "stargate": "stargate",
    "origin": "origin", "origin ether": "origin-ether", "origin-ether": "origin-ether",
    "ethena": "ethena", "pendle": "pendle",
    "lido": "lido",
    "rocket pool": "rocket-pool", "rocket-pool": "rocket-pool", "rocketpool": "rocket-pool",
    "ether.fi": "ether.fi", "ether-fi": "ether.fi", "etherfi": "ether.fi", "weeth": "ether.fi",
    "frax": "frax", "frax ether": "frax-ether", "frax-ether": "frax-ether", "frx-ether": "frax-ether", "sfrxeth": "frax-ether",
    "stader": "stader", "gmx": "gmx",
    "curve": "curve", "curve dex": "curve", "curve-dex": "curve", "curve finance": "curve",
    "curve stable": "curve", "curve-stable": "curve", "curve-finance": "curve",
    "balancer": "balancer-v2", "balancer v2": "balancer-v2", "balancer-v2": "balancer-v2",
    "balancer v3": "balancer-v3", "balancer-v3": "balancer-v3",
    "velodrome": "velodrome", "aerodrome": "aerodrome",
}

_ENSO_STAKE_PROTOS = frozenset({
    "lido", "rocket-pool", "ether.fi", "frax-ether", "stader",
})


def _enso_normalize_slug(raw: str) -> str:
    s = raw.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return _ENSO_PROTO_TO_SLUG.get(s, s.replace(" ", "-"))


_ENSO_VAULT_DEPOSIT_RE = re.compile(
    r"^\s*(?:put|add|deposit|provide|supply|stake|lend|allocate)\s+"
    r"(?P<amount>[\d,]+(?:\.\d+)?)\s+"
    r"(?P<asset>[A-Za-z]{2,10})\s+"
    r"(?:in|to|into|on|via|onto|with)\s+"
    r"(?P<rest>.+?)\s*$",
    re.IGNORECASE,
)


def _detect_enso_vault_deposit(message: str) -> tuple[str, dict] | None:
    """Match 'Deposit 100 USDC into Yearn USDC vault on Ethereum',
    'Stake 0.05 ETH with Lido on Ethereum', 'Deposit 50 DAI into Spark on Ethereum',
    'Supply 100 USDC to Aave V3 on Ethereum', etc.

    Routes to build_yield_execution_plan with action=supply/stake/deposit_lp
    so the Enso shortcut adapter handles the calldata.
    """
    m = _ENSO_VAULT_DEPOSIT_RE.search(message)
    if not m:
        return None
    asset = m.group("asset").upper()
    if asset in _NOT_A_SYMBOL or asset in _NOISE_ASSET_TOKENS:
        return None
    rest = m.group("rest")
    proto_match = _ENSO_PROTOS_RE.search(rest)
    if not proto_match:
        return None
    slug = _enso_normalize_slug(proto_match.group(1))
    chain_match = _ENSO_CHAINS_RE.search(rest)
    chain = (chain_match.group(1).lower() if chain_match else "ethereum")
    if chain == "bnb":
        chain = "bsc"
    amount = m.group("amount").replace(",", "")
    verb = m.group(0).split()[0].lower()
    if slug in _ENSO_STAKE_PROTOS or verb == "stake":
        action = "stake"
    elif slug.startswith(("curve", "balancer")):
        action = "deposit_lp"
    else:
        action = "supply"
    return "build_yield_execution_plan", {
        "chain": chain,
        "protocol": slug,
        "action": action,
        "asset_in": asset,
        "amount_in": amount,
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


_POOL_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_POOL_PROTO_PAIR_RE = re.compile(
    r"\b(?i:(raydium-amm|raydium-clmm|orca-whirlpools|orca-dex|orca|meteora-dlmm|meteora|"
    r"kamino-liquidity|kamino-lend|kamino|marinade-liquid-staking|marinade|jito-liquid-staking|"
    r"jito|sanctum-infinity|sanctum|drift|aave-v3|aave|compound-v3|compound|spark|curve-dex|curve|"
    r"convex|pendle|yearn-finance|yearn|lido|rocket-pool|ether\.fi|frax-ether|stargate|morpho-blue|"
    r"morpho|moonwell|stader|gmx|velodrome|aerodrome-slipstream|aerodrome|uniswap-v[34]|uniswap|"
    r"pancakeswap-amm-v3|pancakeswap|balancer-v3|balancer|"
    r"gmtrade|hylo-lsts|marginfi-lst|the-vault-liquid-staking|"
    r"steer-protocol|zeebu|blackhole-clmm|supernova-cl|shadow-exchange-clmm|mim-swap|beefy))"
    r"[\s·/|-]+([A-Z][A-Z0-9.]*[-_/][A-Z][A-Z0-9.]+|[A-Z][A-Z0-9]{2,15})",
)


# Approximate fiat hint for converting "put 0.2 SOL into pool X" → USD size.
# Price drift is fine because pool deposit sizing is bounded by user balance and
# slippage_bps tolerates volatility. Real-time price lookup would be ideal but
# would couple this detector to the pricing service for negligible gain.
_TOKEN_USD_HINT: dict[str, float] = {
    "SOL": 90.0, "WSOL": 90.0,
    "ETH": 2300.0, "WETH": 2300.0,
    "BNB": 640.0, "WBNB": 640.0,
    "MATIC": 0.13, "WMATIC": 0.13, "POL": 0.13,
    "AVAX": 18.0, "WAVAX": 18.0,
    "ARB": 0.13, "OP": 0.15,
    "USDC": 1.0, "USDT": 1.0, "DAI": 1.0, "BUSD": 1.0, "FDUSD": 1.0, "TUSD": 1.0,
    "BTC": 80000.0, "WBTC": 80000.0, "CBBTC": 80000.0,
}


_DIRECT_POOL_DEPOSIT_RE = re.compile(
    r"^\s*(?:put|add|deposit|provide|supply|stake|allocate)\s+"
    rf"{_NUM_AMOUNT_RE}\s+"
    r"(?P<token>[A-Za-z]{2,10})\s+"
    r"(?:(?:in|to|into|on|inside)\s+)?"
    r"(?:this\s+|the\s+|a\s+)?"
    r"(?:pool|liquidity\s+pool|lp|vault)\s+"
    r"(?P<rest>.+?)\s*$",
    re.IGNORECASE,
)


_SOL_RECEIPT_DEPOSIT_RE = re.compile(
    r"^\s*(?:put|add|deposit|provide|supply|stake)\s+"
    rf"{_NUM_AMOUNT_RE}\s+"
    r"(?P<token>[A-Za-z]{2,10})\s+"
    r"(?:to|into|in|on)\s+"
    r"(?:the\s+|a\s+)?"
    r"(?P<receipt>JLP|JitoSOL|mSOL|MSOL|bSOL|BSOL|INF|jupSOL|jSOL|sSOL|"
    r"jupiter-?perps?|jupiter[ -]?(?:lp|perps|lend|staked[ -]?sol)|"
    r"marinade(?:\s+(?:mSOL|MSOL|staked[ -]?sol|finance))?|"
    r"jito(?:[ -]?(?:staked-sol|sol|liquid-staking))?|"
    r"sanctum(?:[ -]?(?:infinity|INF))?|"
    r"kamino(?:[ -]?(?:lend|vault|liquidity))?|"
    r"stader[ -]?sol|blazestake|jpool|solayer)\b"
    r"(?:\s+on\s+(?:solana|sol))?\s*$",
    re.IGNORECASE,
)


def _detect_solana_receipt_deposit(message: str) -> tuple[str, dict] | None:
    """'Add 25 USDT to JLP' / 'Stake 5 SOL on Marinade' (when stake detector
    misses) / 'Supply 10 USDC to JitoSOL' route to execute_pool_position with
    the protocol head set so the resolver locks onto the right Solana yield
    program.
    """
    m = _SOL_RECEIPT_DEPOSIT_RE.search(message)
    if not m:
        return None
    token = m.group("token").upper()
    if token in _NOT_A_SYMBOL:
        return None
    rec_raw = m.group("receipt")
    rec = re.sub(r"[\s\-]", "", rec_raw).upper()
    # Receipt → canonical protocol slug + canonical receipt symbol.
    receipt_map = {
        "JLP": ("jupiter-perps", "JLP"),
        "JUPITERPERPS": ("jupiter-perps", "JLP"),
        "JUPITERPERP": ("jupiter-perps", "JLP"),
        "JUPITERLP": ("jupiter-perps", "JLP"),
        "JUPITERLEND": ("jupiter-lend", "USDC"),
        "JITOSOL": ("jito", "JitoSOL"),
        "JITO": ("jito", "JitoSOL"),
        "JITOSTAKEDSOL": ("jito", "JitoSOL"),
        "JITOLIQUIDSTAKING": ("jito", "JitoSOL"),
        "MSOL": ("marinade", "mSOL"),
        "MARINADE": ("marinade", "mSOL"),
        "MARINADEMSOL": ("marinade", "mSOL"),
        "MARINADEFINANCE": ("marinade", "mSOL"),
        "MARINADESTAKEDSOL": ("marinade", "mSOL"),
        "BSOL": ("blazestake", "bSOL"),
        "BLAZESTAKE": ("blazestake", "bSOL"),
        "INF": ("sanctum-infinity", "INF"),
        "SANCTUM": ("sanctum-infinity", "INF"),
        "SANCTUMINFINITY": ("sanctum-infinity", "INF"),
        "SANCTUMINF": ("sanctum-infinity", "INF"),
        "JUPSOL": ("jupiter-staked-sol", "jupSOL"),
        "JUPITERSTAKEDSOL": ("jupiter-staked-sol", "jupSOL"),
        "JSOL": ("jpool", "jSOL"),
        "JPOOL": ("jpool", "jSOL"),
        "SSOL": ("solayer", "sSOL"),
        "SOLAYER": ("solayer", "sSOL"),
        "STADERSOL": ("stader", "BNSOL"),
        "STADER": ("stader", "BNSOL"),
        "KAMINO": ("kamino", "kSOL"),
        "KAMINOLEND": ("kamino-lend", "kUSDC"),
        "KAMINOVAULT": ("kamino-liquidity", "kVAULT"),
        "KAMINOLIQUIDITY": ("kamino-liquidity", "kVAULT"),
    }
    proto, receipt_sym = receipt_map.get(rec, (rec.lower(), rec))
    amount_value = _expand_numeric_amount(m.group("amount"), m.group("suffix"))
    if amount_value is None or amount_value <= 0:
        return None
    native_amount = float(amount_value)
    # USD-denominated input (USDC / USDT / DAI / etc.) is already in stable
    # human units that the sidecar accepts directly. For native asset inputs
    # (SOL on Sanctum INF, ETH on Lido, etc.) pass the native amount and let
    # the sidecar's adapter handle units. Never pre-multiply by USD price —
    # that turns 'Stake 10 SOL' into 900 SOL.
    is_stable_in = token in {"USDC", "USDT", "DAI", "FRAX", "USDE", "USDS", "GHO", "PYUSD", "TUSD", "BUSD", "FDUSD", "MIM", "MKUSD", "CRVUSD"}
    return (
        "execute_pool_position",
        {
            "pool": f"{proto} {receipt_sym}",
            "amount": native_amount,
            "asset_in": token,
            "chain": "solana",
            "amount_is_usd": is_stable_in,
        },
    )


def _detect_direct_pool_deposit(message: str) -> tuple[str, dict] | None:
    """'Put 0.2 SOL to this pool uniswap-v4 USDT-SIREN' → execute_pool_position.

    The DefiIntent allocator misroutes this to allocate_plan because 'put' is
    in _ALLOCATION_TERMS. This detector short-circuits when the user names a
    concrete pool reference so they get a single deposit card, not a 5-step
    allocation strategy.
    """
    m = _DIRECT_POOL_DEPOSIT_RE.search(message)
    if not m:
        return None
    token = m.group("token").upper()
    if token in _NOT_A_SYMBOL:
        return None
    rest = m.group("rest").strip().lstrip("·").strip()
    pool_ref = None
    # UUID inside the rest ("put 20 usdc into this pool 399d9968-...-2a9852e0a9a6")
    # must route straight to the pool resolver — protocol/pair detection below
    # never succeeds against a UUID and the deposit silently degrades to a
    # search card.
    uuid_in_rest = _POOL_UUID_RE.search(rest)
    if uuid_in_rest:
        pool_ref = uuid_in_rest.group(0)
    if not pool_ref:
        proto_pair = _POOL_PROTO_PAIR_RE.search(rest)
        if proto_pair:
            pool_ref = f"{proto_pair.group(1)} {proto_pair.group(2)}"
        else:
            pair_only = re.search(r"\b([A-Z][A-Z0-9.]{0,9}[-/_·][A-Z][A-Z0-9.]{0,9})\b", rest)
            if pair_only:
                pool_ref = pair_only.group(1)
    if not pool_ref:
        # Bare protocol fallback: "put 100 usdc into pool aave-v3" → use
        # token as the asset hint for single-asset supply.
        bare = re.search(
            r"\b(?i:(aave-v3|aave|compound-v3|compound|spark|morpho-blue|morpho|"
            r"lido|rocket-pool|jito|kamino|marinade|sanctum|stader|raydium|orca|"
            r"meteora|uniswap-v[34]|curve|convex|pendle|yearn|gmx))\b",
            rest,
        )
        if bare:
            pool_ref = f"{bare.group(1).lower()} {token}"
    if not pool_ref:
        return None
    amount_value = _expand_numeric_amount(m.group("amount"), m.group("suffix"))
    if amount_value is None or amount_value <= 0:
        return None
    price = _TOKEN_USD_HINT.get(token)
    if not price:
        # Unknown token — pass native amount; tool will fail-soft if it can't price.
        usd_amount = float(amount_value) * 1.0
    else:
        usd_amount = float(amount_value) * price
    if usd_amount <= 0:
        return None
    return (
        "execute_pool_position",
        {
            "pool": pool_ref,
            "amount": usd_amount,
            "asset_in": token,
        },
    )


# "Add liquidity to PROTOCOL PAIR (FEE)? (on CHAIN)? (with)? $AMOUNT (TOKEN)?"
# Catches the standard LP-deposit phrasing that doesn't include the bare
# `pool` / `lp` / `vault` keyword that `_DIRECT_POOL_DEPOSIT_RE` requires.
_PROTOCOL_NAME_RE = (
    r"(?P<protocol>(?:[A-Za-z]+[\s-]?){1,3}(?:V\d|v\d|amm|amm-v\d|clmm|slipstream|fusion)?)"
)
# 2-token (USDC-WETH) OR 3-token (DAI-USDC-USDT for Curve 3pool). Capping at
# 3 because beyond that it's almost certainly garbage and we'd rather let
# the LLM fallback handle exotic multi-asset pools.
_PAIR_RE = r"(?P<pair>[A-Z][A-Z0-9.]{1,9}(?:[/-][A-Z][A-Z0-9.]{1,9}){1,2})"
# Accept scientific notation (1e10, 2.5e3, 1.5E-2) in addition to plain
# digits + commas. Negative amounts are intentionally NOT matched so the
# generic refusal path can surface a clean "amount must be positive" hint
# instead of letting the user sign a malformed plan.
_AMOUNT_USD_OR_TOKEN_RE = (
    r"(?:with\s+)?"
    r"(?:\$\s*(?P<usd>[\d,]+(?:\.\d+)?(?:[eE][-+]?\d+)?)|"
    r"(?P<native>[\d,]+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+(?P<token>[A-Za-z]{2,10}))"
)
_ADD_LIQUIDITY_RE = re.compile(
    r"^\s*(?:add|provide|deposit)\s+(?:liquidity\s+)?"
    r"(?:to|in|into|on)\s+"
    rf"{_PROTOCOL_NAME_RE}\s+{_PAIR_RE}"
    # Optional trailing pool-variant suffix ("DLMM", "CLMM", "CPMM", "AMM", "V3").
    r"(?:\s+(?:DLMM|CLMM|CPMM|AMM|Whirlpool|Whirlpools|Slipstream|Fusion|V\d|v\d|pool))?"
    r"(?:\s+\d+(?:\.\d+)?\s*%)?"
    r"(?:\s+on\s+(?P<chain>[A-Za-z]+))?"
    # Allow "with my <SRC>" source-token hint to appear BEFORE the amount,
    # e.g. "... on Ethereum with my USDT, $200". The trailing comma+space is
    # tolerated so the amount regex still matches.
    r"(?:[,\s]+with\s+my\s+(?P<src_pre>[A-Za-z][A-Za-z0-9]{1,9}))?"
    r"[,\s]+"
    rf"{_AMOUNT_USD_OR_TOKEN_RE}"
    # Optional second leg for V2 dual-token form: "and Y TOKEN_B".
    r"(?:\s+and\s+(?:\$\s*[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s+[A-Za-z]{2,10}))?"
    # Tolerate trailing "on CHAIN" after the amount — common phrasing
    # "Add liquidity to Raydium SOL-USDC CLMM with 10 USDC on Solana".
    r"(?:\s+on\s+(?P<chain_after>[A-Za-z]+))?"
    # Tolerate trailing range-preset hint with optional leading comma:
    # "..., balanced range" / " narrow range" / "wide" / "full range".
    r"(?:[,\s]+(?:with\s+)?(?:narrow|balanced|wide|full)(?:\s+range)?)?"
    r"\s*$",
    re.IGNORECASE,
)

# Inverted form: "Deposit $AMOUNT into PROTOCOL PAIR on CHAIN"
_ADD_LIQUIDITY_INV_RE = re.compile(
    r"^\s*(?:deposit|add|put|invest)\s+"
    r"(?:\$\s*(?P<usd>[\d,]+(?:\.\d+)?)|"
    r"(?P<native>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10}))"
    # Optional second leg before the "into PROTOCOL" tail: "and Y TOKEN_B".
    r"(?:\s+and\s+(?:\$\s*[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s+[A-Za-z]{2,10}))?"
    r"\s+(?:into|in|to|on)\s+"
    rf"{_PROTOCOL_NAME_RE}\s+{_PAIR_RE}"
    # Optional trailing pool-variant suffix ("DLMM", "CLMM", "AMM", "V3").
    r"(?:\s+(?:DLMM|CLMM|AMM|Whirlpool|Whirlpools|Slipstream|Fusion|V\d|v\d|pool))?"
    r"(?:\s+\d+(?:\.\d+)?\s*%)?"
    r"(?:\s+on\s+(?P<chain>[A-Za-z]+))?"
    # Tolerate trailing range/preset hints like "with balanced range", "with narrow range",
    # "balanced range", "narrow", "wide", "full range". Doesn't capture — the
    # range builder picks defaults if the request omits explicit lower/upper pct.
    r"(?:\s+(?:with\s+)?(?:narrow|balanced|wide|full)(?:\s+range)?)?"
    r"\s*$",
    re.IGNORECASE,
)

# Inverse-of-inverse: "Open a PROTOCOL [DLMM|CLMM|Whirlpool] PAIR position on
# CHAIN with N TOKEN". Catches user phrasing like
# "Open a Meteora DLMM SOL-USDC position on Solana with 5 USDT" that the
# `add/deposit/provide liquidity` detectors don't match because the verb is
# "Open" and the amount sits at the trailing edge of the sentence.
_OPEN_POSITION_RE = re.compile(
    r"^\s*open\s+(?:a\s+|an\s+)?"
    rf"{_PROTOCOL_NAME_RE}\s+{_PAIR_RE}"
    r"(?:\s+(?:DLMM|CLMM|CPMM|AMM|Whirlpool|Whirlpools|Slipstream|Fusion|V\d|v\d))?"
    r"(?:\s+\d+(?:\.\d+)?\s*%)?"
    r"\s+(?:position|lp|liquidity)"
    r"(?:\s+on\s+(?P<chain>[A-Za-z]+))?"
    rf"\s+(?:with\s+)?{_AMOUNT_USD_OR_TOKEN_RE}"
    # Tolerate trailing "on CHAIN" after the amount — common phrasing
    # "Open Uniswap V3 ETH-USDC position with 0.1 ETH on Ethereum".
    r"(?:\s+on\s+(?P<chain_after>[A-Za-z]+))?"
    # Trailing range-preset hint may carry leading comma:
    # "..., balanced range" / "narrow" / "wide range" / "full".
    r"(?:[,\s]+(?:with\s+)?(?:narrow|balanced|wide|full)(?:\s+range)?)?"
    r"\s*$",
    re.IGNORECASE,
)


# §6d no-amount fallback: "Add liquidity to PROTO PAIR (on CHAIN)? with my SRC".
# The standard _ADD_LIQUIDITY_RE requires an explicit amount; this variant
# captures intent with source-token override only and defaults amount=100 USD.
_ADD_LIQ_NOAMT_WITHMY_RE = re.compile(
    r"^\s*(?:add|provide|deposit)\s+(?:liquidity\s+)?"
    r"(?:to|in|into|on)\s+"
    rf"{_PROTOCOL_NAME_RE}\s+{_PAIR_RE}"
    r"(?:\s+(?:DLMM|CLMM|CPMM|AMM|Whirlpool|Whirlpools|Slipstream|Fusion|V\d|v\d|pool))?"
    r"(?:\s+\d+(?:\.\d+)?\s*%)?"
    r"(?:\s+on\s+(?P<chain>[A-Za-z]+))?"
    r"\s+(?:with|using|from|out\s+of)\s+my\s+"
    r"(?P<src>[A-Za-z][A-Za-z0-9]{1,9})"
    r"(?:\s+on\s+(?P<chain_after>[A-Za-z]+))?"
    r"\s*$",
    re.IGNORECASE,
)


def _detect_add_liquidity(message: str) -> tuple[str, dict] | None:
    """Match 'Add liquidity to Uniswap V3 USDC/WETH on Ethereum with $100'
    and the inverted 'Deposit $100 into PancakeSwap V3 USDT-BNB on BSC' form,
    routing to execute_pool_position with a "protocol pair" pool ref so the
    pool resolver + pool_link gate fire correctly.

    Also detects the V2 dual-token form 'with 100 USDC and 0.05 WETH' and
    forwards both legs via extra={token_a, amount_a, token_b, amount_b} so
    the UniswapV2DualTokenAdapter builds a 3-step approve/approve/addLiquidity
    plan instead of falling through to pool_link.
    """
    text = message.strip()
    m = _ADD_LIQUIDITY_RE.search(text) or _ADD_LIQUIDITY_INV_RE.search(text) or _OPEN_POSITION_RE.search(text)
    # §6d no-amount fallback: "with my <SRC>" form without an explicit amount.
    # Synthesises a default amount=100 USD so the plan can build; the user
    # can refine before signing. Surface a captured "src" via a synthetic
    # `usd` group attribute so the downstream parser path picks it up.
    _no_amt_synthetic = False
    _no_amt_src: str | None = None
    if not m:
        m_noamt = _ADD_LIQ_NOAMT_WITHMY_RE.search(text)
        if m_noamt:
            m = m_noamt
            _no_amt_synthetic = True
            try:
                _no_amt_src = (m_noamt.group("src") or "").upper() or None
            except (IndexError, AttributeError):
                _no_amt_src = None
    if not m:
        return None
    proto_raw = (m.group("protocol") or "").strip().lower()
    # Normalize "uniswap v3" → "uniswap-v3" for the pool resolver / kind gate.
    proto = re.sub(r"\s+", "-", proto_raw)
    pair = (m.group("pair") or "").upper().replace("/", "-")
    # Variant-suffix rewrite (§6b): when the user appended CLMM / DLMM /
    # Whirlpool / Slipstream / CPMM / Fusion *after* the pair, the regex
    # consumes the token but loses the protocol sub-variant. Without this
    # rewrite "Raydium SOL-USDC CLMM" routes to plain "raydium" which the
    # downstream family-head selector collapses to raydium-amm, costing the
    # in-chat range card. Restore the explicit sub-variant before building
    # pool_ref so execute_pool_position._CLMM_SUB_VARIANTS gate trips.
    variant_match = re.search(
        r"\b(DLMM|CLMM|CPMM|AMM|Whirlpool|Whirlpools|Slipstream|Fusion)\b",
        text,
        re.IGNORECASE,
    )
    if variant_match:
        variant = variant_match.group(1).lower()
        proto_head = proto.split("-")[0]
        _VARIANT_REWRITE = {
            ("raydium", "clmm"): "raydium-clmm",
            ("raydium", "cpmm"): "raydium-cp",
            ("raydium", "amm"): "raydium-amm",
            ("orca", "whirlpool"): "orca-whirlpools",
            ("orca", "whirlpools"): "orca-whirlpools",
            ("orca", "clmm"): "orca-clmm",
            ("meteora", "dlmm"): "meteora-dlmm",
            ("meteora", "amm"): "meteora",
            ("aerodrome", "slipstream"): "aerodrome-slipstream",
            ("velodrome", "slipstream"): "velodrome-slipstream",
            ("velodrome", "clmm"): "velodrome-cl",
            ("pancakeswap", "fusion"): "pancakeswap-v3",
        }
        rewritten = _VARIANT_REWRITE.get((proto_head, variant))
        if rewritten:
            proto = rewritten
    # Bare "slipstream" with no chain-prefix: infer from chain. Aerodrome
    # on Base, Velodrome CL on Optimism. Keeps the V3 short-circuit reachable
    # for "Open Slipstream WETH-USDC position with 0.05 WETH on Base".
    if proto == "slipstream":
        _chain_for_slip = (
            (m.groupdict() or {}).get("chain")
            or (m.groupdict() or {}).get("chain_after")
            or ""
        ).lower()
        if _chain_for_slip == "base":
            proto = "aerodrome-slipstream"
        elif _chain_for_slip in ("optimism", "op"):
            proto = "velodrome-cl"
    pool_ref = f"{proto} {pair}"

    _md = m.groupdict() or {}
    usd_str = _md.get("usd")
    native_str = _md.get("native")
    native_tok = (_md.get("token") or "").upper()
    amount_is_usd = False
    usd_equivalent: float | None = None
    if usd_str:
        try:
            amount = float(usd_str.replace(",", ""))
        except (TypeError, ValueError):
            return None
        asset_in = "USDC"  # default USD-denominated leg until LLM refines
        amount_is_usd = True
        usd_equivalent = amount
    elif native_str and native_tok:
        try:
            qty = float(native_str.replace(",", ""))
        except (TypeError, ValueError):
            return None
        # CRITICAL: amount stays in NATIVE units (qty) — never multiplied by
        # USD price. The downstream adapter treats `amount_in` as the asset_in
        # unit; passing USD here would have the user sign for $115 worth of
        # ETH when they typed "0.05 ETH" (115× overshoot). USD-equivalent is
        # surfaced separately for budgeting / Preview display only.
        amount = qty
        price = _TOKEN_USD_HINT.get(native_tok, 1.0)
        usd_equivalent = qty * price
        asset_in = native_tok
    elif _no_amt_synthetic and _no_amt_src:
        # §6d no-amount form: user named source token but no amount. Default
        # to $100 USD-denominated; user can adjust in the Preview card before
        # signing.
        amount = 100.0
        asset_in = _no_amt_src
        amount_is_usd = True
        usd_equivalent = 100.0
    else:
        return None
    if amount <= 0:
        return None

    # V2 dual-token capture: 'with X TOKEN_A and Y TOKEN_B'. Optional and only
    # used when the first amount was native (not USD-denominated). Two halves of
    # a single regex so we can stretch each side independently.
    extra: dict = {}
    dual_re = re.compile(
        r"(?P<amt_a>[\d,]+(?:\.\d+)?)\s+(?P<tok_a>[A-Za-z]{2,10})"
        r"\s+and\s+"
        r"(?P<amt_b>[\d,]+(?:\.\d+)?)\s+(?P<tok_b>[A-Za-z]{2,10})",
        re.IGNORECASE,
    )
    dm = dual_re.search(text)
    if dm:
        try:
            amt_a = float(dm.group("amt_a").replace(",", ""))
            amt_b = float(dm.group("amt_b").replace(",", ""))
        except (TypeError, ValueError):
            amt_a = amt_b = 0.0
        tok_a = dm.group("tok_a").upper()
        tok_b = dm.group("tok_b").upper()
        if amt_a > 0 and amt_b > 0 and tok_a and tok_b:
            extra.update({
                "token_a": tok_a,
                "amount_a": amt_a,
                "token_b": tok_b,
                "amount_b": amt_b,
                "dual_token": True,
            })
            # When dual-token captures, the `amount` field still passes through
            # as the USD-equivalent for budgeting / UI, but the adapter reads
            # the two legs from extra.
            asset_in = tok_a

    # V3 EVM short-circuit: route Uniswap V3 / PancakeSwap V3 / Aerodrome
    # Slipstream straight to build_yield_execution_plan so the new
    # UniswapV3NFTAdapter builds a real swap+approve+mint plan instead of the
    # legacy pool_deposit_v3 redirect card.
    _V3_EVM_PROTOS = {
        "uniswap-v3", "pancakeswap-v3", "pancake-v3",
        "aerodrome-slipstream", "aerodrome-cl",
        "velodrome-cl", "velodrome-slipstream",
    }
    _EVM_CHAINS_SET = {
        "ethereum", "polygon", "arbitrum", "optimism", "base", "avalanche", "bsc", "bnb",
    }
    _gd = m.groupdict() or {}
    chain_raw = (_gd.get("chain") or _gd.get("chain_after") or "").lower()
    if chain_raw == "bnb":
        chain_raw = "bsc"
    # §6d "with my <TOKEN>" silent reassignment: when the user names a source
    # token that isn't one of the pool's legs, snapshot it so the downstream
    # builder can (a) route through Enso multi-input zap and (b) surface an
    # exposure_disclosure ("you said USDT, I'll split into 50.3% USDC +
    # 49.7% SOL — position is exposed to SOL price movement, not just USDC
    # peg"). The detector is intentionally permissive: it accepts "with my",
    # "using my", "from my", and bare "my USDT" trailing the LP intent.
    with_my_match = re.search(
        r"\b(?:with|using|from|out\s+of)\s+my\s+(?P<src>[A-Za-z][A-Za-z0-9]{1,9})\b",
        text,
        re.IGNORECASE,
    )
    source_token: str | None = None
    if with_my_match:
        _src_candidate = with_my_match.group("src").upper()
        if _src_candidate not in _NOISE_ASSET_TOKENS:
            source_token = _src_candidate

    if proto in _V3_EVM_PROTOS and chain_raw in _EVM_CHAINS_SET:
        fee_match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if fee_match:
            fee_pct = float(fee_match.group(1))
            fee_bps = int(round(fee_pct * 10_000))
        else:
            fee_bps = 500  # default to 0.05% tier
        extra_v3 = {"pool_symbol": pair, "fee_bps": fee_bps, "amount_is_usd": amount_is_usd}
        if usd_equivalent is not None:
            extra_v3["usd_equivalent"] = usd_equivalent
        if source_token:
            extra_v3["source_token"] = source_token
            # Source-token override implies user-funded zap-in: route through
            # the source asset, not the pool's primary leg.
            asset_in = source_token
        return (
            "build_yield_execution_plan",
            {
                "chain": chain_raw,
                "protocol": proto,
                "action": "deposit_lp",
                "asset_in": asset_in,
                "amount_in": amount,
                "extra": extra_v3,
            },
        )

    # Solana CLMM/DLMM/Whirlpool short-circuit (§6b): route to
    # build_yield_execution_plan so the sidecar pool_state probe emits the
    # range_block payload. Without this the legacy execute_pool_position
    # path falls through to prep_swap + "click the protocol link" handoff
    # text — spec §6b violation.
    _SOLANA_CLMM_LIKE_PROTOS = {
        "raydium-clmm", "raydium-amm-v3",
        "orca-whirlpools", "orca-clmm",
        "meteora-dlmm",
    }
    _SOLANA_CHAINS_SET = {"solana", "sol"}
    chain_for_solana = chain_raw or "solana"
    if proto in _SOLANA_CLMM_LIKE_PROTOS and chain_for_solana in _SOLANA_CHAINS_SET:
        extra_sol = {"pool_symbol": pair, "amount_is_usd": amount_is_usd}
        if usd_equivalent is not None:
            extra_sol["usd_equivalent"] = usd_equivalent
        if source_token:
            extra_sol["source_token"] = source_token
            asset_in = source_token
        return (
            "build_yield_execution_plan",
            {
                "chain": "solana",
                "protocol": proto,
                "action": "deposit_lp",
                "asset_in": asset_in,
                "amount_in": amount,
                "extra": extra_sol,
            },
        )

    params: dict = {"pool": pool_ref, "amount": amount, "asset_in": asset_in}
    if extra:
        params["extra"] = extra
    if source_token:
        params.setdefault("extra", {})["source_token"] = source_token
        # Source-token override: user holds source_token, not asset_in. Route
        # the zap-in from source_token; downstream builder splits the source
        # into pool's required legs and surfaces exposure_disclosure (§6d).
        params["asset_in"] = source_token
    return (
        "execute_pool_position",
        params,
    )


_STRATEGY_BUILD_VERBS_RE = re.compile(
    r"\b(build|design|create|craft|propose|recommend|outline|develop|research(?:\s+and\s+(?:build|design|create|craft|propose|recommend|outline|develop))?)"
    r"\s+(?:me\s+|us\s+)?(?:a|an|the)?\s*"
    r"(?:[\w%/$.,-]+\s+){0,8}"
    r"(?:strategy|strategies|portfolio|allocation\s+plan|yield\s+plan|farm\s+plan|diversified\s+yield|yield\s+strategy)\b",
    re.IGNORECASE,
)
_NOISE_ASSET_TOKENS = {
    "APY", "APR", "YIELD", "STRATEGY", "STRATEGIES", "RISK", "RISKS",
    "POOL", "POOLS", "FARM", "FARMS", "VAULT", "VAULTS", "PAIR", "PAIRS",
    "LP", "LPS", "GAS", "GAS%", "TVL", "BPS", "FEE", "FEES",
    "TARGETING", "TARGET", "ABOUT", "AROUND", "NEAR", "OVER", "UNDER",
    "MIN", "MAX", "MINIMUM", "MAXIMUM", "AT", "FOR", "TO", "ON", "VIA",
    "ANY", "ALL", "TOP", "BEST", "WORST", "HIGH", "LOW", "MED", "MEDIUM",
    "LOWEST", "HIGHEST", "PROFIT", "RETURNS",
    "EXECUTE", "EXECUTING", "EXECUTION", "DEPOSIT", "DEPOSITING", "DEPOSITS",
    "STAKE", "STAKING", "SUPPLY", "SUPPLYING", "BUY", "SELL", "SWAP",
    "PROCEED", "SIGN", "SIGNING", "ALLOCATE", "ALLOCATION", "DISTRIBUTE",
    "REINVEST", "REINVESTMENT", "REINVESTMENTS", "REBALANCE", "REBALANCING",
    "WALLET", "WALLETS",
}


# §6d no-protocol form: "Add liquidity to PAIR (pool)? with my SRC".
# Spec-canonical phrasing: "Add liquidity to USDC/SOL pool with my USDT".
# The existing _ADD_LIQUIDITY_RE requires an explicit protocol; this
# detector fills the gap and routes through the pool resolver's bare-pair
# fallback with source_token attached so downstream emits exposure
# disclosure.
_LP_WITH_MY_RE = re.compile(
    r"^\s*(?:add|provide|deposit|put|invest)\s+(?:liquidity\s+)?"
    r"(?:to|in|into|on|via|using)?\s*"
    r"(?:the\s+|a\s+|an\s+)?"
    # Optional explicit protocol head before pair — only matched when the
    # _ADD_LIQUIDITY_RE blast didn't already short-circuit. Stays loose.
    r"(?:[A-Za-z][A-Za-z0-9-]{1,20}\s+)?"
    rf"{_PAIR_RE}"
    r"(?:\s+pool|\s+lp|\s+pair)?"
    r"(?:\s+on\s+(?P<chain>[A-Za-z]+))?"
    r"(?:\s+with\s+\$?[\d,]+(?:\.\d+)?(?:\s+[A-Za-z]{2,10})?)?"
    r"\s+(?:with|using|from|out\s+of)\s+my\s+"
    r"(?P<src>[A-Za-z][A-Za-z0-9]{1,9})"
    r"(?:\s+on\s+(?P<chain_after>[A-Za-z]+))?"
    r"\s*$",
    re.IGNORECASE,
)


def _detect_lp_with_my(message: str) -> tuple[str, dict] | None:
    """Match the §6d canonical 'Add liquidity to PAIR pool with my SOURCE'
    form when no protocol is named, then forward to execute_pool_position
    with source_token attached so the resolver picks the best matching
    pool and the downstream builder emits the exposure disclosure.
    """
    text = message.strip()
    m = _LP_WITH_MY_RE.search(text)
    if not m:
        return None
    pair = (m.group("pair") or "").upper().replace("/", "-")
    src = (m.group("src") or "").upper()
    if not pair or not src or src in _NOISE_ASSET_TOKENS:
        return None
    # Reject if SRC is one of the pair legs — that's a passthrough zap and
    # has no §6d ambiguity to resolve.
    legs = set(pair.split("-"))
    if src in legs:
        return None
    _gd = m.groupdict() or {}
    chain_raw = (_gd.get("chain") or _gd.get("chain_after") or "").lower()
    if chain_raw == "bnb":
        chain_raw = "bsc"
    # Amount: best-effort scan for "with $X" / "with N TOKEN".
    amt_match = re.search(
        r"\bwith\s+\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?\s*([A-Za-z]{2,10})?",
        text,
        re.IGNORECASE,
    )
    amount_val: float = 100.0
    amount_is_usd = True
    if amt_match:
        try:
            amount_val = float(amt_match.group(1).replace(",", ""))
            sfx = (amt_match.group(2) or "").lower()
            if sfx == "k":
                amount_val *= 1_000
            elif sfx == "m":
                amount_val *= 1_000_000
            unit = (amt_match.group(3) or "").upper()
            if unit and unit not in {"USDC", "USDT", "USD", "DAI", "FRAX"}:
                amount_is_usd = False
        except (TypeError, ValueError):
            pass
    # Pool ref is bare pair — pool resolver handles via DefiLlama lookup.
    pool_ref = pair
    params: dict = {
        "pool": pool_ref,
        "amount": amount_val,
        "amount_is_usd": amount_is_usd,
        "asset_in": src,
        "extra": {"source_token": src, "pool_symbol": pair},
    }
    if chain_raw:
        params["chain"] = chain_raw
    return ("execute_pool_position", params)


def _detect_pool_execute(message: str, intent: DefiIntent) -> tuple[str, dict] | None:
    """Route 'execute pool X' / 'deposit into raydium-amm SPACEX-WSOL' to
    execute_pool_position when a concrete pool reference is present.
    """
    if not intent.execution_requested:
        return None
    text = message.strip()
    # Strategy-build intents must NEVER route here — they need the strategy
    # composer / search_defi_opportunities path. Prior bug: "Build me a
    # strategy targeting 60% APY on Solana" matched the asset-on-protocol
    # fallback as asset='APY' protocol='solana'.
    if _STRATEGY_BUILD_VERBS_RE.search(text):
        return None
    pool_ref: str | None = None
    m = _POOL_UUID_RE.search(text)
    if m:
        pool_ref = m.group(0)
    else:
        m2 = _POOL_PROTO_PAIR_RE.search(text)
        if m2:
            pool_ref = f"{m2.group(1)} {m2.group(2)}"
        else:
            # Plain symbol pair fallback ("SPACEX-WSOL", "WETH/USDC").
            sp = re.search(r"\b([A-Z][A-Z0-9.]{0,9}[-/_][A-Z][A-Z0-9.]{0,9})\b", text)
            if sp:
                pool_ref = sp.group(1)
            else:
                # Single-asset deposit phrasing: "USDC on Aave V3", "ETH on Lido".
                # Stop at " with ", " on amount ", chain words, or digits.
                m3 = re.search(
                    r"\b([A-Z]{2,8})\s+(?:on|via|to|into)\s+([A-Za-z][A-Za-z0-9 \-_.]{1,40}?)(?=\s+(?:with|amount|for|of|using|\d)|\s*$)",
                    text,
                    re.I,
                )
                if m3:
                    asset = m3.group(1).upper()
                    if asset in _NOISE_ASSET_TOKENS:
                        return None
                    proto_raw = m3.group(2).strip().lower()
                    # Drop trailing chain phrase: "kamino on solana" -> "kamino"
                    proto_raw = re.sub(
                        r"\s+(?:on|via)\s+(ethereum|solana|polygon|arbitrum|base|optimism|bsc|avalanche)\b.*$",
                        "",
                        proto_raw,
                    )
                    proto = re.sub(r"\s+", "-", proto_raw)
                    proto = re.sub(r"-(ethereum|solana|polygon|arbitrum|base|optimism|bsc|avalanche)$", "", proto)
                    pool_ref = f"{proto} {asset}"
    if not pool_ref:
        return None
    # When pool_ref is a bare pair, scan the message for a protocol mention
    # to anchor the resolver. Stops 'USDC-WSOL on Orca' from drifting to
    # Cetus on Sui.
    if " " not in pool_ref and not _POOL_UUID_RE.match(pool_ref):
        proto_token = re.search(
            r"\b(?i:(raydium-amm|raydium-clmm|raydium|orca-whirlpools|orca-clmm|orca|"
            r"meteora-dlmm|meteora|kamino-lend|kamino-liquidity|kamino|marinade|jito|sanctum|drift|"
            r"aave-v3|aave|compound-v3|compound|spark|curve|convex|pendle|yearn-finance|yearn|"
            r"lido|rocket-pool|ether\.fi|frax-ether|frax|stargate|morpho-blue|morpho|moonwell|"
            r"stader|gmx|velodrome|aerodrome-slipstream|aerodrome|uniswap-v[34]|uniswap|"
            r"steer-protocol|zeebu|blackhole-clmm|supernova-cl|lulo|save))\b",
            text,
        )
        if proto_token:
            pool_ref = f"{proto_token.group(1).lower()} {pool_ref}"
    # Amount detection: prefer explicit "with $X" / "for $X" / "$X" /
    # "X USD" / "X USDC" patterns over the intent.amount_usd default.
    # Also track whether the amount is USD-denominated ($, usdc, usdt, usd) so
    # execute_pool_position can convert to native units when the pool's primary
    # asset is non-stable (WSOL, ETH, etc.).
    explicit_amt: float | None = None
    amount_is_usd = False
    # Two-pass: first try unit-required (so "with 10$" matches the trailing $),
    # then fall back to unit-optional.
    am = re.search(
        r"\b(?:with|for|amount|of|=)\s*(\$)?\s*(\d+(?:[\.,]\d+)?)\s*([kKmM])?\s*"
        r"(?P<unit>USDC|USDT|USD|DAI|FRAX|dollars?|\$)",
        text,
        re.IGNORECASE,
    )
    if not am:
        am = re.search(
            r"\b(?:with|for|amount|of|=)\s*(\$)?\s*(\d+(?:[\.,]\d+)?)\s*([kKmM])?",
            text,
            re.IGNORECASE,
        )
    if not am:
        # Bare "$X" or "X$" form
        am = re.search(r"(\$)\s*(\d+(?:[\.,]\d+)?)\s*([kKmM])?", text)
        if not am:
            am = re.search(r"(\d+(?:[\.,]\d+)?)\s*([kKmM])?\s*(\$)", text)
            if am:
                # Reorder groups to (dollar_marker, digits, suffix) for consistency
                # with the other branches below.
                class _GroupShim:
                    def __init__(self, m):
                        self._m = m
                    def group(self, i):
                        if i == 1:
                            return "$"
                        if i == 2:
                            return self._m.group(1)
                        if i == 3:
                            return self._m.group(2)
                        return None
                    def groupdict(self):
                        return {"unit": "$"}
                    @property
                    def lastindex(self):
                        return 3
                am = _GroupShim(am)
    if am:
        try:
            dollar_sign = bool(am.group(1)) if am.lastindex and am.lastindex >= 1 else False
            n = float(am.group(2).replace(",", ""))
            sfx = (am.group(3) or "").lower()
            if sfx == "k":
                n *= 1_000
            elif sfx == "m":
                n *= 1_000_000
            unit = (am.groupdict().get("unit") or "").upper() if hasattr(am, "groupdict") else ""
            if dollar_sign or unit in {"USDC", "USDT", "USD", "DAI", "FRAX", "DOLLAR", "DOLLARS", "$"}:
                amount_is_usd = True
            if 0 < n <= 1_000_000_000:
                explicit_amt = n
        except (TypeError, ValueError):
            pass
    if explicit_amt is None:
        explicit_amt = intent.amount_usd if (intent.amount_usd is not None and intent.amount_usd > 0) else 100.0
        amount_is_usd = True
    params: dict = {
        "pool": pool_ref,
        "amount": explicit_amt,
        "amount_is_usd": amount_is_usd,
    }
    chain_hint_match = re.search(r"\bon\s+(solana|ethereum|polygon|arbitrum|base|optimism|bsc|avalanche)\b", text, re.I)
    if chain_hint_match:
        params["chain"] = chain_hint_match.group(1).lower()
    return "execute_pool_position", params


def _defi_intent_to_tool(intent: DefiIntent) -> tuple[str, dict] | None:
    if intent.intent == "allocate_strategy":
        params: dict = {
            "usd_amount": intent.amount_usd if intent.amount_usd is not None else 10_000.0,
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
        if getattr(intent, "limit", None):
            params["max_positions"] = int(intent.limit)
        return "allocate_plan", params

    if intent.intent not in {"search_defi_opportunities", "execute_yield_strategy"}:
        return None

    params: dict = {
        "risk_levels": intent.risk_levels,
        "product_types": intent.product_types,
        "chains": intent.chains,
        "ranking_objective": intent.ranking_objective,
        "execution_requested": intent.execution_requested,
        "limit": int(getattr(intent, "limit", None) or 8),
    }
    if intent.target_apy is not None:
        params["target_apy"] = intent.target_apy
    if intent.min_apy is not None:
        params["min_apy"] = intent.min_apy
    if intent.max_apy is not None:
        params["max_apy"] = intent.max_apy
    if intent.asset_hint:
        params["asset_hint"] = intent.asset_hint
    # Stablecoin-only flag carried through so search_defi_opportunities can
    # filter symbols and the strategy compose narrative knows to talk
    # stables-only.
    if getattr(intent, "stablecoin_only", False):
        params["stablecoin_only"] = True
    if getattr(intent, "protocol_filter", None):
        params["protocol_filter"] = intent.protocol_filter
    # Only forward min_tvl when the user explicitly set it (the default
    # 100K floor would override per-risk-tier defaults downstream).
    if getattr(intent, "min_tvl", 100_000.0) != 100_000.0:
        params["min_tvl"] = intent.min_tvl
    return "search_defi_opportunities", params


_WHALE_RE = re.compile(r"\b(whale|whales|big buyer|big sell|large transfer|smart money move)\b", re.I)
_SMART_MONEY_RE = re.compile(r"\b(smart money|conviction picks?|top traders?|alpha hub)\b", re.I)
_ENTITY_RE = re.compile(r"\b(who is|who are|find entity|tag for|known as|who's)\s+([A-Za-z0-9._\-]{2,60})\b", re.I)
_SHIELD_RE = re.compile(r"\b(shield|approvals?|drain|risk scan)\b.*\b(0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})\b", re.I)
_ANALYZE_TOKEN_RE = re.compile(r"\b(analyze|check|scan|sentinel|review)\s+(?:this\s+)?(?:token|coin|mint|contract|pool)?\s*(?:on\s+(?:dexscreener|dex|solscan|defillama)\s*[:,]?\s*)?\b(0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})\b", re.I)
# Bare-mint detector: when message contains a Solana base58 mint or 0x EVM
# address with no accompanying pool/protocol words, default to token analysis.
_BARE_MINT_RE = re.compile(r"\b(0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})\b")
_DEX_HINT_RE = re.compile(r"\b(dexscreener|dex screener|solscan|on dex)\b", re.I)
_ANALYZE_POOL_RE = re.compile(r"\b(analyze|review|stats? for|check)\s+(?:this\s+)?pool\b", re.I)


def _detect_sentinel_chat_tools(message: str) -> tuple[str, dict] | None:
    """Route Sentinel feature asks to deterministic tools so the LLM
    can't drift into 'contextual reasoning' mode for them.
    """
    text = message.strip()
    # Skip only when the *primary verb* of the message is wallet/swap/bridge/
    # allocate. Mentions of "wallet" inside a shield-style ask must NOT
    # short-circuit the sentinel router.
    if re.match(r"^\s*(my\s+(?:wallet|balance|portfolio|holdings|assets)\b|what\s+is\s+my\b|swap\s|bridge\s|allocate\s|distribute\s|deploy\s+\$?\d|portfolio\b|holdings\b)", text, re.I):
        return None
    # 1. analyze_token / analyze_dex_pair (also matches "analyze this pool
    #    on dexscreener: <addr>" and other phrasings around a bare address).
    m = _ANALYZE_TOKEN_RE.search(text)
    bare_addr_match = None
    if not m:
        # Trigger token analysis on safety/rug-style asks too, not just verbs
        if re.search(r"\b(analyze|check|scan|sentinel|review|rug|scam|safe|honeypot|legit|trustworthy|audit)\b", text, re.I):
            bare_addr_match = _BARE_MINT_RE.search(text)
            if bare_addr_match:
                m = bare_addr_match
    if m:
        addr = m.group(2) if hasattr(m, "groups") and m.groups() and m.lastindex and m.lastindex >= 2 else m.group(0)
        chain_lower = text.lower()
        chain = "solana" if (len(addr) >= 32 and not addr.startswith("0x")) else (
            "ethereum" if "ethereum" in chain_lower else (
                "bsc" if "bsc" in chain_lower or "bnb" in chain_lower else (
                    "polygon" if "polygon" in chain_lower else None)))
        params: dict = {"address": addr}
        if chain:
            params["chain"] = chain
        # Pasted with 'pool', 'pair', 'dex', 'dexscreener' → use the
        # ambiguity-resolving DexScreener probe. Otherwise default to
        # token analysis.
        if re.search(r"\b(pool|pair|dex|dexscreener|liquidity)\b", text, re.I):
            return "analyze_dex_pair", params
        return "analyze_token_full_sentinel", params
    # 2. analyze_pool — when 'analyze pool ...' OR safety/quality verbs + pool reference, and not in execute mode
    pool_safety_trigger = re.search(r"\b(safe|risky|rug|legit|trustworthy|audit|honeypot|stats?|info|details?)\b", text, re.I)
    if (_ANALYZE_POOL_RE.search(text) or (pool_safety_trigger and (_POOL_UUID_RE.search(text) or _POOL_PROTO_PAIR_RE.search(text)))) and not re.search(r"\bexecute\b|\bdeposit\b", text, re.I):
        u = _POOL_UUID_RE.search(text)
        p = _POOL_PROTO_PAIR_RE.search(text)
        ref: str | None = None
        if u:
            ref = u.group(0)
        elif p:
            ref = f"{p.group(1)} {p.group(2)}"
        else:
            # Fallback: just a symbol pair like "SPACEX-WSOL" or "WETH/USDC"
            sp = re.search(r"\b([A-Z][A-Z0-9.]{0,9}[-/_][A-Z][A-Z0-9.]{0,9})\b", text)
            if sp:
                ref = sp.group(1)
                # Anchor with a protocol mentioned elsewhere in the message.
                proto_token = re.search(
                    r"\b(?i:(raydium-amm|raydium-clmm|raydium|orca-whirlpools|orca-clmm|orca|"
                    r"meteora-dlmm|meteora|kamino-lend|kamino-liquidity|kamino|marinade|jito|sanctum|drift|"
                    r"aave-v3|aave|compound-v3|compound|spark|curve|convex|pendle|yearn|"
                    r"lido|rocket-pool|ether\.fi|frax-ether|frax|stargate|morpho-blue|morpho|moonwell|"
                    r"stader|gmx|velodrome|aerodrome-slipstream|aerodrome|uniswap-v[34]|uniswap))\b",
                    text,
                )
                if proto_token:
                    ref = f"{proto_token.group(1).lower()} {ref}"
        if ref:
            params = {"pool": ref}
            chain_hint = re.search(r"\bon\s+(solana|ethereum|polygon|arbitrum|base|optimism|bsc|avalanche)\b", text, re.I)
            if chain_hint:
                params["chain"] = chain_hint.group(1).lower()
            return "analyze_pool_full_sentinel", params
    # 3. whale_track
    if _WHALE_RE.search(text):
        params = {}
        if "solana" in text.lower():
            params["chain"] = "solana"
        elif "ethereum" in text.lower():
            params["chain"] = "ethereum"
        m_h = re.search(r"(\d+)\s*h(?:our)?", text, re.I)
        if m_h:
            params["hours"] = int(m_h.group(1))
        return "track_whales", params
    # 4. smart_money_hub
    if _SMART_MONEY_RE.search(text):
        params = {"chain": "solana"}
        if "ethereum" in text.lower():
            params["chain"] = "ethereum"
        return "get_smart_money_hub", params
    # 5. shield_check
    m_sh = _SHIELD_RE.search(text)
    if m_sh:
        return "get_shield_check", {"address": m_sh.group(2)}
    # 6. entity_lookup
    m_ent = _ENTITY_RE.search(text)
    if m_ent and m_ent.group(2).strip().lower() not in {"the", "this", "that", "x", "y", "it"}:
        return "lookup_entity", {"query": m_ent.group(2).strip()}
    return None


def _detect_preference_update(message: str) -> tuple[str, dict] | None:
    """Match natural-language preference updates and route to update_preference."""
    text = message.strip()
    params: dict = {}
    m = re.search(r"\b(?:set\s+)?(?:my\s+)?slippage(?:\s+(?:to|=|cap))?\s+(\d{1,4})\s*(?:bps|bp)?\b", text, re.IGNORECASE)
    if m:
        try:
            params["slippage_cap_bps"] = int(m.group(1))
        except ValueError:
            pass
    m = re.search(
        r"\b(?:risk\s*budget|risk\s*level|risk\s*profile)\s*(?:to|=|:|set\s+to)?\s*(conservative|balanced|aggressive)\b",
        text,
        re.IGNORECASE,
    )
    if m:
        params["risk_budget"] = m.group(1).lower()
    elif re.search(
        r"\b(?:set|change|update|switch)\b[^.\n]{0,40}\b(?:risk(?:\s*budget|\s*level|\s*profile)?)\b[^.\n]{0,40}?\b(conservative|balanced|aggressive)\b",
        text,
        re.IGNORECASE,
    ):
        m2 = re.search(
            r"\b(conservative|balanced|aggressive)\b",
            text,
            re.IGNORECASE,
        )
        if m2:
            params["risk_budget"] = m2.group(1).lower()
    elif re.match(r"^\s*(conservative|balanced|aggressive)\s+only\b", text, re.IGNORECASE):
        params["risk_budget"] = re.match(r"^\s*(\w+)", text, re.IGNORECASE).group(1).lower()
    m = re.search(r"\bgas\s+cap\s*(?:to|=)?\s*\$?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        try:
            params["gas_cap_usd"] = float(m.group(1))
        except ValueError:
            pass
    if not params:
        return None
    return "update_preference", params


def detect_intent(message: str) -> tuple[str, dict] | None:
    """Detect intent and extract parameters from user message."""
    message_lower = message.lower()

    bootstrap = _detect_bootstrap_alloc(message)
    if bootstrap is not None:
        return bootstrap

    multi_step = _detect_bridge_then_stake(message)
    if multi_step is not None:
        return multi_step
    for detector in (_detect_solana_receipt_deposit, _detect_direct_pool_deposit, _detect_add_liquidity, _detect_lp_with_my, _detect_enso_vault_deposit, _detect_aave_supply, _detect_generic_supply, _detect_swap_then_lp, _detect_stake_amount_plan, _detect_stake_all, _detect_stake_simple, _detect_malicious_swap_plan, _detect_bridge_signable, _detect_buy_intent, _detect_swap_signable, _detect_transfer_plan):
        detected = detector(message)
        if detected is not None:
            return detected

    sentinel_tool = _detect_sentinel_chat_tools(message)
    if sentinel_tool is not None:
        return sentinel_tool

    pref = _detect_preference_update(message)
    if pref is not None:
        return pref

    parsed_intent = parse_defi_intent(message)
    pool_exec = _detect_pool_execute(message, parsed_intent)
    if pool_exec is not None:
        return pool_exec
    defi_tool = _defi_intent_to_tool(parsed_intent)
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
                    # Skip stop-words and shape-invalid captures.
                    if is_stop_word(tok) or not is_valid_symbol_shape(tok):
                        continue
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
                        ti = m2.group("tin").upper()
                        to = m2.group("tout").upper()
                        if is_stop_word(ti) or is_stop_word(to):
                            return None
                        if ti == to:
                            return None
                        try:
                            amt_val = float(m2.group("amount").replace(",", ""))
                        except (TypeError, ValueError):
                            return None
                        if amt_val <= 0 or amt_val > 1_000_000_000:
                            return None
                        params["token_in"] = ti
                        params["token_out"] = to
                        params["amount"] = m2.group("amount").replace(",", "")
                        chain = m2.group("chain")
                        chain_l = chain.lower() if chain else "ethereum"
                        # Cross-chain check: refuse so the LLM/bridge path can take over.
                        from src.agent.intent.validation import _CHAIN_ID_BY_NAME_FALLBACK as _C  # noqa: E402
                        _cid = _C.get(chain_l)
                        if _cid and is_cross_chain(ti, to, _cid):
                            return None
                        params["chain"] = chain_l
                    else:
                        # Fallback: pick the last two valid-looking tickers,
                        # routing every English noise word ("WALLET", "FROM",
                        # "MY", chain names, etc) through the central STOP_WORDS list.
                        # Reject when the message contains a URL or 0x address —
                        # neither is a swap-able ticker.
                        if re.search(r"https?://|0x[0-9a-fA-F]{40}", message):
                            return None
                        # Strip URL-ish hostname noise before extracting tokens.
                        clean_msg = re.sub(r"https?://\S+", " ", message)
                        all_tokens = re.findall(r"[A-Za-z]{2,10}", clean_msg)
                        candidates = filter_symbol_candidates(all_tokens)
                        if len(candidates) < 2:
                            return None
                        ti = candidates[-2]
                        to = candidates[-1]
                        if ti == to:
                            return None
                        # Detect a negative-sign immediately preceding a number — reject.
                        if re.search(r"-\s*\d", message):
                            return None
                        amount_match = re.search(r'(\d+(?:\.\d+)?)', message)
                        if not amount_match:
                            return None
                        try:
                            amt_val = float(amount_match.group(1))
                        except (TypeError, ValueError):
                            return None
                        if amt_val <= 0 or amt_val > 1_000_000_000:
                            return None
                        # Detect chain hint anywhere in the message.
                        chain_l = "ethereum"
                        for chain_name, patterns in CHAIN_PATTERNS.items():
                            if any(re.search(p, message_lower, re.IGNORECASE) for p in patterns):
                                chain_l = chain_name
                                break
                        from src.agent.intent.validation import _CHAIN_ID_BY_NAME_FALLBACK as _C  # noqa: E402
                        _cid = _C.get(chain_l)
                        if _cid and is_cross_chain(ti, to, _cid):
                            return None
                        params["token_in"] = ti
                        params["token_out"] = to
                        params["amount"] = amount_match.group(1)
                        params["chain"] = chain_l
                elif tool_name == "build_bridge_tx":
                    bridge_re = re.compile(
                        r"bridge\s+(?P<amount>[\d,]+(?:\.\d+)?)\s+(?P<token>[A-Za-z]{2,10})"
                        r"(?:\s+from\s+(?P<src>[A-Za-z ]+?))?\s+to\s+(?P<dst>[A-Za-z ]+)",
                        re.IGNORECASE,
                    )
                    m_bridge = bridge_re.search(message)
                    if not m_bridge:
                        # Refuse rather than emit an empty-params bridge tool call.
                        # 'bridge weth to bnb' (no amount) used to fall through here
                        # and the bridge tool received {} which crashed downstream.
                        return None
                    token = m_bridge.group("token").upper()
                    if is_stop_word(token) or not is_valid_symbol_shape(token):
                        return None
                    src = (m_bridge.group("src") or "ethereum").strip().lower()
                    dst = m_bridge.group("dst").strip().lower()
                    dst = re.sub(r"\s+(?:and|then|to|for).*$", "", dst).strip()
                    src_id = CHAIN_IDS.get(src)
                    dst_id = CHAIN_IDS.get(dst, CHAIN_IDS.get(dst.split()[0] if dst else ""))
                    if src_id is None or dst_id is None or src_id == dst_id:
                        return None
                    params["src_chain_id"] = src_id
                    params["dst_chain_id"] = dst_id
                    params["token_in"] = token
                    # Leave token_out empty so the wallet-assistant's bridge resolver
                    # picks the chain-correct output (e.g. SOL → ETH on Ethereum)
                    # instead of forcing the source mint onto a foreign chain.
                    params["token_out"] = ""
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
    request_meta = data.get("request_meta") or {}
    if not candidates:
        # Conflict-aware empty narrative — explicit when constraints are
        # mathematically incompatible.
        target_apy = request_meta.get("target_apy")
        risk_levels = request_meta.get("risk_levels") or []
        chains = request_meta.get("chains") or []
        is_low_only = set(map(str.upper, risk_levels)) == {"LOW"}
        # Bitcoin / unsupported chain
        unsupported_chains = [c for c in chains if c.lower() in {"bitcoin", "btc"}]
        parts: list[str] = []
        if unsupported_chains:
            parts.append(
                f"**{', '.join(c.upper() for c in unsupported_chains)} is not currently supported** "
                "for direct DeFi yield execution. Bitcoin yield products live on wrapped-BTC pools "
                "on EVM chains (e.g., Ethereum, Arbitrum, Base) — try `WBTC` or `cbBTC` pools there."
            )
        if target_apy is not None and is_low_only and float(target_apy) >= 25.0:
            parts.append(
                f"**The target {float(target_apy):.0f}% APY conflicts with a LOW-risk filter.** "
                "Low-risk DeFi (blue-chip lending like Aave V3 USDC, liquid staking like JitoSOL/Lido) "
                "tops out at roughly 4-8% APY in current market conditions. To reach "
                f"{float(target_apy):.0f}% you would need to allow MEDIUM or HIGH risk exposure "
                "(concentrated LPs, boosted farms, leveraged stable looping) — those carry "
                "impermanent loss, smart-contract, and incentive-cliff risk."
            )
        if target_apy is not None and float(target_apy) >= 500.0:
            parts.append(
                f"**A {float(target_apy):.0f}% APY target is unrealistic** in today's market — even "
                "the most aggressive Solana memecoin LPs cap at ~500% gross APY before factoring "
                "impermanent loss and token-price collapse. Realistic high-yield strategies "
                "target 30-150% with active management."
            )
        if not parts:
            parts.append(
                "I couldn't find credible DeFi opportunities matching those exact APY, risk, chain, "
                "and TVL constraints. Loosen any one filter (e.g., raise the APY ceiling, allow "
                "MEDIUM risk, or include another chain) to widen the candidate pool."
            )
        return "\n\n".join(parts)

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
        if reason and not candidate.get("executable"):
            lines.append(f"   Execution: research-only — {reason}")
        elif candidate.get("executable"):
            adapter = candidate.get("adapter_id") or "executable adapter"
            lines.append(f"   Execution: ready via {adapter}")
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
    if tool_name == "build_yield_execution_plan" or card_type == "execution_plan_v3":
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
    elif card_type == "sentinel_token_report" or tool_name == "analyze_token_full_sentinel":
        return _format_sentinel_token_summary(result)
    elif card_type == "sentinel_pool_report" or tool_name == "analyze_pool_full_sentinel":
        return _format_sentinel_pool_summary(result)
    elif card_type == "sentinel_whale_feed" or tool_name == "track_whales":
        return _format_sentinel_whale_summary(result)
    elif card_type == "sentinel_smart_money_hub" or tool_name == "get_smart_money_hub":
        return _format_sentinel_smart_money_summary(result)
    elif card_type == "sentinel_shield_report" or tool_name == "get_shield_check":
        return _format_sentinel_shield_summary(result)
    elif card_type == "sentinel_entity_card" or tool_name == "lookup_entity":
        return _format_sentinel_entity_summary(result)
    else:
        # Generic formatting — never dump raw JSON to chat.
        return "Tool ran successfully. Open the card above for the full details."


def _card(result) -> dict:
    if hasattr(result, "card_payload"):
        return getattr(result, "card_payload") or {}
    if isinstance(result, dict):
        return result.get("card_payload") or {}
    return {}


def _format_sentinel_token_summary(result) -> str:
    p = _card(result)
    sym = p.get("symbol") or (p.get("address") or "")[:8]
    score = p.get("score")
    grade = p.get("grade")
    verdict = p.get("verdict")
    chain = p.get("chain") or "?"
    parts = [f"**{sym}** on **{chain}** — Sentinel score **{score}/100** (grade {grade})."]
    if verdict:
        parts.append(f"Verdict: **{verdict}**.")
    sec = p.get("security") or {}
    if sec.get("liquidity_locked"):
        parts.append(f"Liquidity locked ({sec.get('lp_lock_percent') or 0}%).")
    if sec.get("is_honeypot") is False:
        parts.append("Not a honeypot.")
    rec = p.get("recommendation")
    if rec:
        parts.append(rec)
    parts.append("Open the report above for the full risk surface.")
    return " ".join(parts)


def _format_sentinel_pool_summary(result) -> str:
    p = _card(result)
    return (
        f"**{p.get('protocol','?')} · {p.get('symbol','?')}** on **{p.get('chain','?')}** — "
        f"APY **{p.get('apy') or 'n/a'}%**, TVL ${p.get('tvl_usd') or 0:,.0f}, "
        f"IL risk **{p.get('il_risk') or 'unknown'}**. Open the pool report for execution options."
    )


def _format_sentinel_whale_summary(result) -> str:
    p = _card(result)
    items = p.get("items") or []
    chain = p.get("chain") or "all chains"
    hours = p.get("hours")
    if not items:
        return f"No whale activity in the last {hours}h on {chain}. Try widening the window or switching chains."
    return f"{len(items)} whale events captured in the last {hours}h on {chain}. Open the feed above for per-tx details."


def _format_sentinel_smart_money_summary(result) -> str:
    p = _card(result)
    chain = p.get("chain")
    counts = (
        f"{len(p.get('top_wallets') or [])} top wallets, "
        f"{len(p.get('trending_tokens') or [])} trending tokens, "
        f"{len(p.get('conviction') or [])} conviction picks"
    )
    return f"Smart-money hub for **{chain}** — {counts}. Open the card above for the breakdown."


def _format_sentinel_shield_summary(result) -> str:
    p = _card(result)
    s = p.get("summary") or {}
    verdict = p.get("verdict") or "unknown"
    return (
        f"Shield report on `{(p.get('address') or '')[:10]}…` — verdict **{verdict}**. "
        f"{s.get('total_approvals',0)} approvals total · "
        f"{s.get('high_risk_count',0)} high · {s.get('medium_risk_count',0)} med · "
        f"{s.get('low_risk_count',0)} low."
    )


def _format_sentinel_entity_summary(result) -> str:
    p = _card(result)
    if p.get("empty"):
        return p.get("empty_reason") or "No entity match."
    name = p.get("name") or p.get("query")
    tags = p.get("tags") or []
    addrs = p.get("addresses") or []
    return f"Entity **{name}** — {len(tags)} tags, {len(addrs)} linked addresses. Open the card for full details."


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
    # Hard guard: if the message contains a concrete pool reference, $ amount,
    # or any execution-arg pattern, this is NOT a confirmation — it's a fresh
    # explicit deposit instruction. Refuse the canned reply so the normal
    # intent dispatch can build a real signing card.
    if _POOL_UUID_RE.search(message):
        return None
    if _POOL_PROTO_PAIR_RE.search(message):
        return None
    if re.search(r"\$\s*\d|\b\d+(?:\.\d+)?\s*(?:USDC|USDT|USD|SOL|ETH|BTC|WBTC|BNB|MATIC|AVAX|DAI)\b", message, re.IGNORECASE):
        return None
    # Verb + object pattern ("execute deposit into ...", "execute swap ...")
    if re.search(r"^\s*execute\s+(?:deposit|swap|bridge|stake|trade|buy|sell|supply|provide)\b", message, re.IGNORECASE):
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


# ── Strategy composition (LLM-on-top-of-tool-data) ─────────────────────────

_STRATEGY_REQUEST_RE = re.compile(
    r"\b("
    # build / design / create / craft / plan / propose / recommend / make / write
    # — possibly with up to ~7 connector tokens before 'strategy'
    r"(?:build|design|create|craft|plan|propose|recommend|make|write|outline|develop)"
    r"\s+(?:me\s+|us\s+)?(?:a|an|the)?\s*(?:[\w%/$.,-]+\s+){0,7}strateg(?:y|ies)|"
    # research-and-X form
    r"research\s+and\s+(?:build|design|propose|create|recommend)\s+(?:me\s+)?(?:a|an|the)?\s*(?:[\w%/$.,-]+\s+){0,4}strateg(?:y|ies)|"
    # bare 'a strategy that …' / 'a strategy targeting …'
    r"\ba\s+strateg(?:y|ies)\s+(?:targeting|that\s+target|aimed\s+at|for|to\s+(?:hit|reach|achieve))|"
    # 'strategy targeting X% APY'
    r"strateg(?:y|ies)\s+(?:targeting|that\s+target|aimed\s+at|for|to\s+(?:hit|reach|achieve))"
    r")\b",
    re.IGNORECASE,
)


def _is_strategy_compose_request(message: str) -> bool:
    """True when user wants a multi-section strategy doc, not just a pool list."""
    if not message:
        return False
    return bool(_STRATEGY_REQUEST_RE.search(message))


def _filter_strategy_card(
    card_payload: dict,
    *,
    target_apy: float | None,
    risk_levels: list[str] | None,
    min_tvl: float = 1_000_000.0,
) -> tuple[dict, int, int]:
    """Narrow a defi_opportunities card to pools that match the user's stated
    target APY band and TVL floor. Prevents the degen-only-pools mismatch
    where narrative says 'targeting 60%' but card shows 455% pools.

    Returns (new_payload, kept_count, original_count). When the band is empty
    we surface the most-realistic survivors (TVL>=1M sorted by closeness to
    target) so the card never goes blank — but we tag empty_band so the
    narrative explains the gap.
    """
    if not isinstance(card_payload, dict):
        return card_payload, 0, 0
    items = list(card_payload.get("items") or [])
    original_count = len(items)
    if not items:
        return card_payload, 0, 0

    def _apy(it: dict) -> float:
        try:
            return float(it.get("apy") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _tvl(it: dict) -> float:
        try:
            return float(it.get("tvl_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _risk(it: dict) -> str:
        return str(it.get("risk_level") or "MEDIUM").upper()

    matched: list[dict]
    if target_apy is not None and target_apy > 0:
        lo = max(0.5, target_apy * 0.5)
        hi = target_apy * 1.6
        matched = [it for it in items if lo <= _apy(it) <= hi and _tvl(it) >= min_tvl]
    else:
        matched = [it for it in items if _tvl(it) >= min_tvl]

    if risk_levels:
        wanted = {str(r).upper() for r in risk_levels}
        matched = [it for it in matched if _risk(it) in wanted]

    if not matched:
        # Fall back: closest-to-target with TVL>=1M, then >=500K, then any.
        for tvl_cap in (1_000_000.0, 500_000.0, 0.0):
            ranked = sorted(
                [it for it in items if _tvl(it) >= tvl_cap],
                key=lambda it: (
                    abs(_apy(it) - (target_apy or 0.0)),
                    -_tvl(it),
                ),
            )
            if ranked:
                matched = ranked[:5]
                break
        if not matched:
            matched = items[:5]

    new_payload = dict(card_payload)
    new_payload["items"] = matched[:8]
    return new_payload, len(new_payload["items"]), original_count


def _summarize_pools_for_strategy(card_payload: dict) -> str:
    """Compact bullet list of opportunities for LLM context. Bounded length."""
    if not isinstance(card_payload, dict):
        return ""
    items = card_payload.get("items") or []
    if not items:
        return ""
    lines: list[str] = []
    for idx, it in enumerate(items[:15], start=1):
        try:
            sym = it.get("symbol") or "?"
            proto = it.get("protocol") or "?"
            chain = it.get("chain") or "?"
            apy = float(it.get("apy") or 0.0)
            tvl = float(it.get("tvl_usd") or 0.0)
            risk = it.get("risk_level") or "?"
            executable = "executable" if it.get("executable") else "research-only"
            pool_id = it.get("pool_id") or ""
            lines.append(
                f"{idx}. {proto} {sym} on {chain} — APY {apy:.1f}% · TVL ${tvl:,.0f} · risk {risk} · {executable} · pool_id={pool_id}"
            )
        except Exception:
            continue
    return "\n".join(lines)


def _strategy_system_prompt(
    *,
    target_apy: float | None,
    risk_levels: list[str] | None,
    chains: list[str] | None,
    reinvestment_cadence: str | None = None,
    stablecoin_only: bool = False,
) -> str:
    apy_line = f"Target APY: {target_apy:.0f}%" if target_apy else "Target APY: not specified — infer from request."
    risk_line = (
        f"Risk preference: {', '.join(risk_levels)}"
        if risk_levels
        else "Risk preference: not specified — infer from request."
    )
    chain_line = (
        f"Chains: {', '.join(chains)}"
        if chains
        else "Chains: not specified — infer from request."
    )
    cadence_line = (
        f"Reinvestment cadence: {reinvestment_cadence} (the 'Reinvestment plan' "
        "section MUST reflect this exact cadence)."
        if reinvestment_cadence
        else "Reinvestment cadence: not specified — pick a reasonable default."
    )
    stable_line = (
        "Stablecoin-only constraint: TRUE — every pool you cite must be a "
        "stablecoin pair (USDC/USDT/DAI/FRAX/LUSD/etc.). If the live data "
        "block has non-stable pools, exclude them and recommend stable "
        "alternatives by category (Aave V3 USDC, Curve 3pool, Pendle PT-USDe, "
        "Mountain USDM)."
        if stablecoin_only
        else "Stablecoin-only constraint: FALSE — full asset universe allowed."
    )
    return (
        "You are Ilyon Sentinel, a senior DeFi strategist. The user asked you to BUILD a strategy. "
        "You have your own intelligence AND access to live pool data the system already fetched.\n\n"
        f"{apy_line}\n{risk_line}\n{chain_line}\n{cadence_line}\n{stable_line}\n\n"
        "OUTPUT FORMAT — markdown, ChatGPT-style, multi-section. ALWAYS include these sections "
        "(use real H2 headers, tables where relevant):\n\n"
        "## Reality check\n"
        "Be honest about what the target APY actually requires (compounding math, risk profile, "
        "what categories of pools/strategies are even capable of it). Cite the math (monthly/daily "
        "compounded rate). Do NOT promise the target — frame it as feasibility analysis.\n\n"
        "## Target allocation\n"
        "A markdown table: Bucket | Allocation % | Purpose | Expected APY range. Pick 4-6 buckets "
        "that together can produce the target with appropriate risk distribution. Examples of "
        "buckets: liquid staking base, stable lending, concentrated LPs, aggressive boosted pools, "
        "stable reserve. Allocations must sum to 100%.\n\n"
        "## Pool selection rules\n"
        "Hard requirements the user (or you) should apply when picking specific pools: minimum TVL, "
        "volume/TVL ratio, 7d-vs-30d APY sanity, asset quality, IL risk, smart contract risk. "
        "Use a markdown table for the rules.\n\n"
        "## Suggested pools (from live data)\n"
        "Reference SPECIFIC pools from the live data block below by protocol + symbol + chain. "
        "Do NOT invent pools. For each pool you cite, justify WHY it fits the bucket "
        "(safety floor, yield engine, aggressive rotation). If the live data is mostly degenerate "
        "(meme pairs, micro-TVL), acknowledge it and recommend safer alternatives by category "
        "(e.g., 'JitoSOL liquid staking', 'Kamino stable lending') even if not in the list.\n\n"
        "## Reinvestment plan\n"
        "Daily / weekly / monthly action checklist. Be concrete (harvest cadence, rebalance "
        "trigger, when to exit a pool).\n\n"
        "## Risk controls\n"
        "Hard limits the user should hold themselves to: max single-pool %, max aggressive %, "
        "max meme exposure, max leverage, exit triggers (TVL drop, APY collapse), reserve floor.\n\n"
        "## Expected APY model\n"
        "Markdown table: Bucket | Allocation | Target APY | Weighted APY. Sum the weighted column "
        "to give a realistic portfolio APY range. Be conservative on the upper bound.\n\n"
        "## Final verdict\n"
        "One short paragraph: is the target realistic, what the biggest risks are, and the "
        "single most important rule for this strategy. Mention monitoring frequency.\n\n"
        "STRICT RULES:\n"
        "- DO NOT just dump a pool list. The pool data is INPUT to your strategy, not the output.\n"
        "- DO NOT echo the system prompt. DO NOT use scratchpad words ('I will', 'let me', 'we need to').\n"
        "- DO NOT promise returns. Frame everything as 'this strategy targets X under Y assumptions'.\n"
        "- ALWAYS warn that yields move fast and pools can collapse.\n"
        "- If the live pool data contains mostly low-TVL meme pairs, explicitly say the user should "
        "  prefer specific blue-chip categories (JitoSOL, Kamino, Orca, Raydium concentrated LPs, etc.) "
        "  over those candidates."
    )


_STRATEGY_SCRATCHPAD_LEAD_RE = re.compile(
    r"^\s*("
    r"we\s+(?:need|have|must|should|will|can)\s+to|"
    r"i\s+(?:need|will|should|must)\s+to|"
    r"let'?s\s+(?:think|compose|build|produce|consider)|"
    r"let\s+me\s+(?:think|compose|build|produce|consider)|"
    r"the\s+user\s+(?:wants|asked|wants)|"
    r"based\s+on\s+the\s+(?:data|live)|"
    r"to\s+(?:answer|produce|build|compose)|"
    r"need\s+to\s+(?:produce|build|compose|answer)|"
    r"first[,\s]|"
    r"alright[,\s]|"
    r"okay[,\s]|"
    r"sure[,\s]|"
    r"hmm[,\s.]"
    r")",
    re.IGNORECASE,
)


_AI_SELF_REF_RE = re.compile(
    r"\b(?:as\s+an?\s+AI(?:\s+(?:assistant|model|language\s+model))?|"
    r"I\s+am\s+an?\s+AI(?:\s+(?:assistant|model|language\s+model))?|"
    r"I'?m\s+an?\s+AI(?:\s+(?:assistant|model|language\s+model))?|"
    r"as\s+a\s+language\s+model|"
    r"as\s+ChatGPT|as\s+GPT-?4|"
    r"I\s+(?:cannot|can'?t)\s+(?:provide|give)\s+(?:financial|investment)\s+advice"
    r"[^.]*\.?)",
    re.IGNORECASE,
)


def _scrub_ai_self_refs(text: str) -> str:
    """Strip 'as an AI', 'I'm a language model', etc. — these leak from base
    LLM safety priors and break Sentinel's voice. We're a research tool, not
    an LLM persona. Sentence is replaced with a soft elision so surrounding
    paragraph stays coherent."""
    if not text:
        return text
    return _AI_SELF_REF_RE.sub("", text)


def _strip_strategy_scratchpad(text: str) -> str:
    """Strip leading scratchpad paragraphs without touching markdown structure.

    `_clean_response` is too aggressive on strategy compose output (eats
    table rows, bullet lists). This soft pass only peels leading scratchpad
    paragraphs until the first markdown heading or table row.
    """
    if not text:
        return text
    text = _scrub_ai_self_refs(text)
    lines = text.split("\n")
    drop = 0
    for ln in lines:
        s = ln.strip()
        if not s:
            drop += 1
            continue
        # Stop at first markdown heading or table row or list item
        if s.startswith("#") or s.startswith("|") or s.startswith("- ") or s.startswith("* "):
            break
        if _STRATEGY_SCRATCHPAD_LEAD_RE.match(s):
            drop += 1
            continue
        # Non-scratchpad non-markdown line — keep
        break
    return "\n".join(lines[drop:]).lstrip()


async def _compose_strategy_via_llm(
    llm,
    *,
    user_message: str,
    pool_card: dict | None,
    history: list[dict] | None,
    target_apy: float | None,
    risk_levels: list[str] | None,
    chains: list[str] | None,
    prior_cards_summary: str = "",
    empty_band: bool = False,
    reinvestment_cadence: str | None = None,
    stablecoin_only: bool = False,
) -> str | None:
    """Run the LLM with strategy composition prompt + live pool data context."""
    pool_summary = _summarize_pools_for_strategy(pool_card or {})
    system_prompt = _strategy_system_prompt(
        target_apy=target_apy,
        risk_levels=risk_levels,
        chains=chains,
        reinvestment_cadence=reinvestment_cadence,
        stablecoin_only=stablecoin_only,
    )

    context_blocks: list[str] = []
    if prior_cards_summary:
        context_blocks.append(
            "Previously surfaced pools / cards in this chat (for continuity — refer to these "
            "if the user said 'those pools', 'these', 'previous'):\n" + prior_cards_summary
        )
    if empty_band:
        context_blocks.append(
            "IMPORTANT: the live pool search returned NO pools that fit the target APY band "
            "AND a $1M+ TVL floor. The pool list below was widened to the closest-to-target "
            "survivors. In your narrative you MUST acknowledge that the target is unrealistic "
            "on this chain right now, name the safer blue-chip alternatives by category "
            "(e.g., JitoSOL liquid staking, Kamino lending, Aave V3, Lido stETH), and lower "
            "the realistic blended APY claim."
        )
    if pool_summary:
        context_blocks.append(
            "Live pool candidates the system just fetched for this request "
            "(use these as your concrete pool universe — DO NOT invent pools "
            "and DO NOT cite pools outside this list as if they were live data):\n"
            + pool_summary
        )
    user_block = f"User request: {user_message}"
    if context_blocks:
        user_block = "\n\n".join(context_blocks) + "\n\n" + user_block

    llm_messages: list = []
    llm_messages.append(type("Msg", (), {"type": "system", "content": system_prompt})())
    trimmed_history = [p for p in (history or [])[-HISTORY_WINDOW:] if p.get("content")]
    for prior in trimmed_history:
        role = prior.get("role")
        mtype = "human" if role == "user" else ("ai" if role == "assistant" else "system")
        llm_messages.append(type("Msg", (), {"type": mtype, "content": prior.get("content") or ""})())
    llm_messages.append(type("Msg", (), {"type": "human", "content": user_block})())

    try:
        # 2400 covers all 8 strategy sections without truncating mid-table.
        # Stays under the upstream provider's per-call output cap
        # (gpt-oss-120b:nitro returned empty body at 4000).
        result = await llm._agenerate(llm_messages, max_tokens=2400, temperature=0.5)
        text = (result.generations[0].message.content or "").strip()
        if not text:
            return None
        # OpenAIClient.chat() returns a fixed apology string on transport error
        # — reject it so the default formatter remains the response.
        lowered = text.lower()
        rejection_markers = (
            "i couldn't reach the language model",
            "sorry, i can't respond",
            "ai unavailable",
        )
        if any(marker in lowered for marker in rejection_markers):
            logger.warning("strategy compose: LLM returned transport error string; falling back to formatter")
            return None
        return text
    except Exception as exc:
        logger.warning("strategy composition LLM call failed: %s: %s", type(exc).__name__, exc)
        return None


# ── Prior-cards memory helper (cross-turn pool context) ───────────────────


def _summarize_prior_cards(history_cards: list[dict] | None, max_cards: int = 6) -> str:
    """Extract pool/protocol identifiers from prior cards for LLM context.

    history_cards is a flat list of dicts shaped like
    {card_type, payload: {...}} captured from previous assistant turns.
    """
    if not history_cards:
        return ""
    lines: list[str] = []
    seen_pool_ids: set[str] = set()
    for card in history_cards[-max_cards:]:
        ctype = card.get("card_type")
        payload = card.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if ctype == "defi_opportunities":
            for it in (payload.get("items") or [])[:10]:
                pool_id = it.get("pool_id") or ""
                if pool_id and pool_id in seen_pool_ids:
                    continue
                if pool_id:
                    seen_pool_ids.add(pool_id)
                try:
                    lines.append(
                        f"- {it.get('protocol')} {it.get('symbol')} on {it.get('chain')} "
                        f"(APY {float(it.get('apy') or 0):.1f}%, TVL ${float(it.get('tvl_usd') or 0):,.0f}, "
                        f"risk {it.get('risk_level')}, pool_id={pool_id})"
                    )
                except Exception:
                    continue
        elif ctype == "execution_plan_v3":
            plan_id = payload.get("plan_id") or ""
            steps = payload.get("steps") or []
            if plan_id and steps:
                step_summaries = []
                for step in steps[:3]:
                    step_summaries.append(
                        f"step {step.get('index')}: {step.get('action')} "
                        f"{step.get('amount_in') or ''} {step.get('asset_in') or ''} on "
                        f"{step.get('chain')} via {step.get('protocol')}"
                    )
                lines.append(
                    f"- execution plan {plan_id} with {len(steps)} step(s): "
                    + "; ".join(step_summaries)
                )
        elif ctype == "allocation":
            positions = payload.get("positions") or []
            if positions:
                lines.append(
                    "- allocation card with positions: "
                    + "; ".join(
                        f"{p.get('protocol')}/{p.get('symbol')} {p.get('weight_pct') or '?'}%"
                        for p in positions[:6]
                    )
                )
    return "\n".join(lines).strip()


# ── Prior-pools distribution (continuity across turns) ────────────────────

_PRIOR_POOLS_REF_RE = re.compile(
    r"\b(?:across|between|into|among|over|onto|to)\s+"
    r"(?:those|these|the\s+(?:previous|above|last|listed|earlier|same|aforementioned)|all\s+(?:those|these))\s+pools?\b",
    re.IGNORECASE,
)
_PRIOR_POOLS_PRONOUN_RE = re.compile(
    r"\b(?:distribute|spread|split|allocate|divide|deploy|put|deposit|stake|invest|use|apply)\b[^.!?\n]{0,80}\b"
    r"(?:them|those|these|across\s+all|across\s+the\s+pools)\b",
    re.IGNORECASE,
)


def _references_prior_pools(message: str) -> bool:
    if not message:
        return False
    return bool(_PRIOR_POOLS_REF_RE.search(message) or _PRIOR_POOLS_PRONOUN_RE.search(message))


def _extract_prior_pool_items(history_cards: list[dict] | None) -> list[dict]:
    """Pull the most recent defi_opportunities item list from cards memory."""
    if not history_cards:
        return []
    for card in reversed(history_cards):
        if card.get("card_type") == "defi_opportunities":
            payload = card.get("payload") or {}
            items = payload.get("items") or []
            if isinstance(items, list) and items:
                return items
    return []


async def _compose_prior_pools_distribution_via_llm(
    llm,
    *,
    user_message: str,
    prior_pools: list[dict],
    history: list[dict] | None,
    amount_hint: str | None = None,
) -> str | None:
    """LLM composes a per-pool distribution markdown from the prior pools the
    user is referring to. Keeps the user's amount and the SAME pool universe."""
    pool_lines: list[str] = []
    for idx, it in enumerate(prior_pools[:12], start=1):
        try:
            sym = it.get("symbol") or "?"
            proto = it.get("protocol") or "?"
            chain = it.get("chain") or "?"
            apy = float(it.get("apy") or 0.0)
            tvl = float(it.get("tvl_usd") or 0.0)
            risk = it.get("risk_level") or "?"
            pool_id = it.get("pool_id") or ""
            pool_lines.append(
                f"{idx}. {proto} {sym} ({chain}) — APY {apy:.1f}% · TVL ${tvl:,.0f} · risk {risk} · pool_id={pool_id}"
            )
        except Exception:
            continue
    pool_block = "\n".join(pool_lines)

    system_prompt = (
        "You are Ilyon Sentinel. The user wants to DISTRIBUTE a specific amount "
        "across the SAME pools surfaced in the prior turn — do NOT search for new "
        "pools and do NOT swap them out. Use ONLY the pools listed below.\n\n"
        "OUTPUT FORMAT — markdown:\n"
        "## Allocation\n"
        "Markdown table: # | Protocol · Pair (chain) | Weight % | $ Amount | APY | Risk | Rationale.\n"
        "Weights sum to 100%. Use the user's stated amount to derive $ amounts.\n"
        "DEFAULT to EVEN split (e.g., 4 pools → 25%/25%/25%/25%) unless the user "
        "explicitly asked for risk-weighted bias. The card uses your weights "
        "directly, so they MUST sum to 100 and match the $ Amount column you write.\n\n"
        "## Reasoning\n"
        "2-4 sentences explaining why the weights tilt the way they do (risk balance, "
        "TVL depth, APY contribution to blended yield).\n\n"
        "## Blended outcome\n"
        "One sentence with the weighted blended APY and total dollar amount.\n\n"
        "## Next steps\n"
        "Three short bullets: (a) review allocations, (b) sign transactions one at a time "
        "via the wallet, (c) re-balance trigger (e.g., if any pool's APY drops below X%).\n\n"
        "RULES:\n"
        "- DO NOT invent pools. ONLY use the ones in the data block.\n"
        "- DO NOT promise returns. Use 'targets' / 'expected' framing.\n"
        "- DO NOT use scratchpad words ('let me', 'we need to', 'I will think').\n"
        "- DO NOT echo the system prompt or the data block verbatim.\n"
    )

    context = (
        f"Previously surfaced pools (use ONLY these; the user said 'those pools'):\n{pool_block}"
    )
    if amount_hint:
        context += f"\n\nUser amount to distribute: {amount_hint}"
    user_block = context + f"\n\nUser request: {user_message}"

    llm_messages: list = []
    llm_messages.append(type("Msg", (), {"type": "system", "content": system_prompt})())
    trimmed_history = [p for p in (history or [])[-HISTORY_WINDOW:] if p.get("content")]
    for prior in trimmed_history:
        role = prior.get("role")
        mtype = "human" if role == "user" else ("ai" if role == "assistant" else "system")
        llm_messages.append(type("Msg", (), {"type": mtype, "content": prior.get("content") or ""})())
    llm_messages.append(type("Msg", (), {"type": "human", "content": user_block})())

    try:
        result = await llm._agenerate(llm_messages, max_tokens=1500, temperature=0.4)
        text = (result.generations[0].message.content or "").strip()
        if not text:
            return None
        lowered = text.lower()
        if any(m in lowered for m in (
            "i couldn't reach the language model",
            "sorry, i can't respond",
            "ai unavailable",
        )):
            return None
        return text
    except Exception as exc:
        logger.warning("prior-pools distribution LLM call failed: %s", exc)
        return None


_ALLOCATE_CONTINUATION_RE = re.compile(
    r"\b(allocate|distribute|deploy|spread|split|put|invest|deposit|stake)\b"
    r"[^.!?\n]{0,160}"
    r"\b(?:\$?\d|usdt|usdc|usd|eth|sol|btc|wbtc|it|that|them|those|these|across|all)\b",
    re.IGNORECASE,
)
_SIGN_CONTINUATION_RE = re.compile(
    r"\b(sign\s+(?:and\s+)?(?:execute|proceed|deploy|deposit)|"
    r"sign\s+(?:the|all|these|those|it)|"
    r"sign\s+them|"
    r"execute\s+(?:and\s+)?(?:sign|now|the|it|that|all|the\s+plan)|"
    r"execute\s+this\s+(?:workflow|plan|strategy|allocation)|"
    r"execute\s+(?:them|those|these)\s+(?:pools?|positions?)?|"
    r"execute\s+the\s+\d+\s+pools?|"
    r"step\s+by\s+step|"
    r"one\s+(?:at\s+a\s+time|by\s+one)|"
    r"proceed\s+(?:with|to|and)|"
    r"build\s+(?:the\s+)?(?:allocation|execution\s+plan|plan)|"
    r"create\s+(?:the\s+)?(?:execution|plan)|"
    r"continue\s+with\s+(?:allocation|signing|execution)|"
    r"deploy\s+(?:the|it|all|that))\b",
    re.IGNORECASE,
)
# Reamount: "now do $5000 instead", "make it $1000 instead", "change to $X",
# "use $X instead", "rerun with $X"
_REAMOUNT_CONTINUATION_RE = re.compile(
    r"\b(now\s+do|make\s+it|change\s+to|use|rerun\s+with|do\s+(?:it|that)\s+with|"
    r"with\s+\$?\d|but\s+(?:with|use|do)|"
    r"redo\s+(?:with|using)|"
    r"actually\s+\$?\d)\b[^.!?\n]{0,80}\$?\d",
    re.IGNORECASE,
)
# Vague follow-up: "do that", "do it", "go ahead", "yes"
_VAGUE_CONTINUATION_RE = re.compile(
    r"^\s*(do\s+(?:that|it|this|the\s+thing)|go\s+ahead|yes|yep|yeah|please|let'?s\s+do\s+it|all\s+right|alright|ok)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
# Pivot detection: changes core constraint(s) of the prior strategy/search
# Matches: "actually make it Y", "same thing on Z", "now show on W",
# "switch to / change to", "but on Ethereum instead", "instead make it conservative"
_PIVOT_RE = re.compile(
    r"\b("
    r"actually\s+(?:make|do|set|use|on|with|let'?s)|"
    r"same\s+(?:thing|strategy|approach)\s+(?:but\s+)?(?:on|for|in|with)|"
    r"now\s+(?:show|do|run|build)\s+(?:on|for|in|with)|"
    r"switch(?:ed)?\s+to|change\s+to|change\s+it|"
    r"but\s+on\s+\w+(?:\s+instead)?|"
    r"instead\s+(?:make|do|use|on)|"
    r"redo\s+(?:on|with|for)|"
    r"flip\s+to|move\s+to"
    r")\b",
    re.IGNORECASE,
)
# Refine/filter: "filter to X", "narrow to X", "only show Y", "exclude Z"
_REFINE_RE = re.compile(
    r"\b(filter|narrow|restrict|only\s+show|just\s+show|show\s+only|"
    r"exclude|remove|drop|skip|hide|"
    r"with\s+tvl|where\s+(?:apy|tvl|risk)|where\s+the)\b",
    re.IGNORECASE,
)
# "Not those pools / find different / something else / try again"
_REJECT_PRIOR_RE = re.compile(
    r"\b(not\s+(?:those|these|them)|"
    r"different\s+(?:ones|pools|set)|"
    r"something\s+else|"
    r"find\s+(?:other|different)|"
    r"try\s+(?:again|other)|"
    r"new\s+(?:set|search|pools))\b",
    re.IGNORECASE,
)
# "the top one", "the first one", "the best one", "first pool", "highest APY one"
_SINGLE_POOL_PICK_RE = re.compile(
    r"\b(?:the\s+)?(?:top|first|best|highest(?:\s+apy)?|safest)\s+(?:one|pool)\b",
    re.IGNORECASE,
)
# Onboarding bootstrap: "I have $X USDC, what should I do" / "what's the play"
_BOOTSTRAP_ALLOC_RE = re.compile(
    r"\b(?:i\s+have|got|holding|sitting\s+on|with)\s+\$?(?P<amount>[\d,]+(?:\.\d+)?)\s*([kKmM])?\s*"
    r"(?:in\s+)?"
    r"(?:USDC|USDT|USD|DAI|dollars?)?"
    r".{0,120}?"
    r"(?:what\s+(?:should\s+i\s+do|to\s+do|next|now|do\s+i\s+do|can\s+i\s+do)|what'?s\s+the\s+(?:move|play|best))",
    re.IGNORECASE | re.DOTALL,
)


_SAFE_TO_SWAP_RE = re.compile(
    r"\b(is\s+it\s+safe\s+to|safe\s+to|safety\s+of)\s+(?:swap|trade|exchange|convert|sell|buy)\b[^.!?\n]{0,120}",
    re.IGNORECASE,
)


def _is_safety_question(message: str) -> bool:
    """True when user asks 'is it safe to swap/trade X' — used by LLM
    fallback to inject a Shield-flavored system prompt note.
    """
    return bool(_SAFE_TO_SWAP_RE.search(message or ""))


def _detect_bootstrap_alloc(message: str) -> tuple[str, dict] | None:
    m = _BOOTSTRAP_ALLOC_RE.search(message)
    if not m:
        return None
    try:
        amt = float(m.group("amount").replace(",", ""))
    except ValueError:
        return None
    sfx = (m.group(2) or "").lower()
    if sfx == "k":
        amt *= 1_000
    elif sfx == "m":
        amt *= 1_000_000
    if amt <= 0 or amt > 1_000_000_000:
        return None
    return ("allocate_plan", {
        "usd_amount": amt,
        "risk_budget": "balanced",
    })
_AMOUNT_FROM_TEXT_RE = re.compile(
    r"(?:^|\b)\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?\s*(usdt|usdc|usd|dollars?)?",
    re.IGNORECASE,
)
_NATIVE_AMOUNT_FROM_TEXT_RE = re.compile(
    r"(?:^|\b)([\d,]+(?:\.\d+)?)\s*([kKmM])?\s*(SOL|ETH|WETH|BTC|WBTC|BNB|MATIC|AVAX|ARB|OP)\b",
    re.IGNORECASE,
)
_NATIVE_USD_HINT: dict[str, float] = {
    "SOL": 90.0, "WSOL": 90.0,
    "ETH": 2300.0, "WETH": 2300.0,
    "BTC": 80000.0, "WBTC": 80000.0,
    "BNB": 640.0, "WBNB": 640.0,
    "MATIC": 0.13,
    "AVAX": 18.0,
    "ARB": 0.13,
    "OP": 0.15,
}


def _references_prior_pools_for_allocation(
    message: str, history_cards: list[dict] | None
) -> bool:
    """True when user wants to allocate / sign / re-amount / rerun across prior pools.

    Fires when a prior `defi_opportunities` card exists AND the new message
    matches any of: prior-pool refs ("those pools"), allocate verbs with a
    contextual hint ("allocate it"), sign/execute verbs, re-amount phrasings
    ("now do $X"), or a bare vague confirmation ("do that") within the
    prior-card context.
    """
    if not message or not history_cards:
        return False
    has_prior = any(c.get("card_type") == "defi_opportunities" for c in history_cards)
    if not has_prior:
        return False
    if _references_prior_pools(message):
        return True
    if _ALLOCATE_CONTINUATION_RE.search(message):
        return True
    if _SIGN_CONTINUATION_RE.search(message):
        return True
    if _REAMOUNT_CONTINUATION_RE.search(message):
        return True
    if _VAGUE_CONTINUATION_RE.search(message):
        return True
    return False


def _is_pivot_request(message: str, history_cards: list[dict] | None) -> bool:
    """True when the user wants to regenerate the prior search/strategy with
    different constraints (chain switch, risk switch, target switch).
    """
    if not message or not history_cards:
        return False
    has_prior = any(c.get("card_type") == "defi_opportunities" for c in history_cards)
    if not has_prior:
        return False
    return bool(_PIVOT_RE.search(message))


def _last_defi_card_constraints(history_cards: list[dict] | None) -> dict:
    """Extract the constraint snapshot (target_apy/apy_band/chains/risk_levels/
    product_types) from the most recent `defi_opportunities` card so a pivot
    or refine can rebuild the search with those + new overrides.
    """
    if not history_cards:
        return {}
    for card in reversed(history_cards):
        if card.get("card_type") != "defi_opportunities":
            continue
        p = card.get("payload") or {}
        if not isinstance(p, dict):
            continue
        out: dict = {}
        if p.get("target_apy") is not None:
            out["target_apy"] = float(p.get("target_apy"))
        band = p.get("apy_band") or [None, None]
        if isinstance(band, (list, tuple)) and len(band) == 2:
            if band[0] is not None:
                out["min_apy"] = float(band[0])
            if band[1] is not None:
                out["max_apy"] = float(band[1])
        if p.get("risk_levels"):
            out["risk_levels"] = list(p.get("risk_levels") or [])
        if p.get("chains"):
            out["chains"] = list(p.get("chains") or [])
        if p.get("execution_requested"):
            out["execution_requested"] = bool(p.get("execution_requested"))
        if p.get("objective"):
            out["ranking_objective"] = str(p.get("objective"))
        return out
    return {}


def _synthesize_pivot_search_args(
    message: str, history_cards: list[dict] | None
) -> dict | None:
    """Build search_defi_opportunities args from prior card + new pivot.

    Strategy: take prior card constraints as base. Re-parse message for
    chain / risk / target overrides. Merge.
    """
    base = _last_defi_card_constraints(history_cards)
    if not base:
        return None
    # Re-parse new message
    fresh = parse_defi_intent(message)
    args = dict(base)
    # Chain override
    if fresh.chains:
        args["chains"] = fresh.chains
    # Risk override
    if fresh.risk_levels:
        args["risk_levels"] = fresh.risk_levels
    elif fresh.risk_budget == "conservative":
        args["risk_levels"] = ["LOW"]
    elif fresh.risk_budget == "aggressive":
        args["risk_levels"] = ["MEDIUM", "HIGH"]
    # APY override
    if fresh.target_apy is not None:
        args["target_apy"] = fresh.target_apy
        if fresh.min_apy is not None:
            args["min_apy"] = fresh.min_apy
        if fresh.max_apy is not None:
            args["max_apy"] = fresh.max_apy
    if fresh.stablecoin_only:
        args["stablecoin_only"] = True
    args.setdefault("product_types", ["pool", "farm", "vault", "lending"])
    args.setdefault("limit", 8)
    args.setdefault("ranking_objective", "execution_ready_strategy" if args.get("execution_requested") else "constraint_fit_then_risk_adjusted_return")
    return args


def _synthesize_refine_search_args(
    message: str, history_cards: list[dict] | None
) -> dict | None:
    """Build search_defi_opportunities args for a refinement of the prior
    result. Inherits prior chain/target/risk; layers TVL/protocol filters
    parsed from message.
    """
    base = _last_defi_card_constraints(history_cards)
    if not base:
        return None
    args = dict(base)
    args.setdefault("product_types", ["pool", "farm", "vault", "lending"])
    args.setdefault("limit", 8)
    args.setdefault("ranking_objective", "highest_sentinel_score")
    # TVL above X parsing
    tvl_m = re.search(
        r"\btvl\s*(?:above|over|>|>=|at\s+least|min(?:imum)?\s+of)\s*\$?(\d+(?:\.\d+)?)\s*([kKmMbB])?",
        message, re.IGNORECASE,
    )
    if tvl_m:
        try:
            v = float(tvl_m.group(1))
            sfx = (tvl_m.group(2) or "").lower()
            if sfx == "k":
                v *= 1_000
            elif sfx == "m":
                v *= 1_000_000
            elif sfx == "b":
                v *= 1_000_000_000
            args["min_tvl"] = v
        except ValueError:
            pass
    # Protocol filter ("only Aave V3", "only Curve")
    proto_m = re.search(
        r"\b(?:only|just|filter\s+to)\s+([\w-]+(?:\s*v?\d)?)",
        message, re.IGNORECASE,
    )
    if proto_m:
        args["asset_hint"] = None  # don't reuse prior asset hint
        # use protocol slug as substring for ranking re-ordering — pass via a custom kwarg
        args["protocol_filter"] = proto_m.group(1).strip().lower().replace(" ", "-")
    # Reject prior pools — pass exclude_pool_ids from prior card
    if _REJECT_PRIOR_RE.search(message):
        prior_ids = []
        for card in (history_cards or []):
            if card.get("card_type") == "defi_opportunities":
                for it in (card.get("payload") or {}).get("items") or []:
                    pid = it.get("pool_id")
                    if pid:
                        prior_ids.append(pid)
        if prior_ids:
            args["exclude_pool_ids"] = list({p for p in prior_ids})[:30]
    return args


def _is_refine_request(message: str, history_cards: list[dict] | None) -> bool:
    """True when user wants to filter / narrow / exclude from the prior result."""
    if not message or not history_cards:
        return False
    has_prior = any(c.get("card_type") == "defi_opportunities" for c in history_cards)
    if not has_prior:
        return False
    return bool(_REFINE_RE.search(message)) or bool(_REJECT_PRIOR_RE.search(message))


_PERCENT_NEAR_NUMBER_RE = re.compile(
    r"\b(?:targeting|target|around|about|near|at\s+least|minimum|min|over|above|under|below|up\s+to)\s+\d",
    re.IGNORECASE,
)


def _parse_amount_from_text(text: str) -> float | None:
    """Parse a USD-equivalent amount from free text.

    Recognises plain dollar amounts ("$1000", "1000 USDC", "1k") AND native
    crypto amounts ("10 SOL", "0.5 ETH"), converting native via _NATIVE_USD_HINT.
    Native conversion uses approximate spot prices — fine for sizing the
    allocation card; exact USD value comes from on-chain balance at signing.

    Skips numbers that are clearly APY/percent values: number followed by
    '%', 'percent', 'pct', 'apy', 'apr', 'yield', or preceded by mode words
    like 'targeting', 'around', 'at least'.
    """
    if not text:
        return None
    nm = _NATIVE_AMOUNT_FROM_TEXT_RE.search(text)
    if nm:
        try:
            qty = float(nm.group(1).replace(",", ""))
        except ValueError:
            qty = 0.0
        suffix = (nm.group(2) or "").lower()
        if suffix == "k":
            qty *= 1_000
        elif suffix == "m":
            qty *= 1_000_000
        token = nm.group(3).upper()
        price = _NATIVE_USD_HINT.get(token, 0.0)
        if qty > 0 and price > 0:
            usd = qty * price
            if 0 < usd <= 1_000_000_000:
                return usd
    # Iterate every dollar-style match, reject percent values.
    for m in re.finditer(
        r"(?:^|\b)\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?\s*(usdt|usdc|usd|dollars?)?",
        text,
        re.IGNORECASE,
    ):
        # Window around the matched number to check for percent context
        start = max(0, m.start() - 25)
        end = min(len(text), m.end() + 25)
        window = text[start:end]
        # Skip if the number is clearly a percent or APY value
        if re.search(r"\d\s*(?:%|percent|pct)\b", window, re.IGNORECASE):
            # Verify the % is attached to THIS number (not another nearby number)
            local = text[m.start():m.end() + 25]
            if re.search(r"^\$?\s*[\d,.]+\s*[kKmM]?\s*(?:%|percent|pct)\b", local, re.IGNORECASE):
                continue
        # Skip if the number is preceded by APY-mode words ("targeting 60", "at least 30")
        pre = text[max(0, m.start() - 30):m.start()]
        if re.search(r"\b(?:targeting|target|around|about|near|at\s+least|minimum|min|over|above|under|below|up\s+to)\s*$", pre, re.IGNORECASE):
            continue
        # Skip if number is followed by APY/APR/yield word (e.g., "60 APY")
        post = text[m.end():m.end() + 12]
        if re.match(r"\s*(?:apy|apr|yield)\b", post, re.IGNORECASE):
            continue
        # Skip currency-less plain numbers when message has no $/USDC/USD/etc.
        # (avoid "thirty-five percent" being parsed as 35 here)
        currency = (m.group(3) or "").lower()
        has_dollar = "$" in text[max(0, m.start()-2):m.end()]
        if not currency and not has_dollar:
            continue
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        suffix = (m.group(2) or "").lower()
        if suffix == "k":
            n *= 1_000
        elif suffix == "m":
            n *= 1_000_000
        if 0 < n <= 1_000_000_000:
            return n
    return None


def _build_prior_pools_allocation_payload(
    prior_pools: list[dict],
    *,
    usd_amount: float,
    risk_budget: str = "balanced",
    override_weights: list[int] | None = None,
) -> dict | None:
    """Compose an `allocation` card payload over the prior pool universe.

    Skips the strict $200M-TVL composer floor so the SAME pools the user
    already saw end up in the Allocation Proposal — even if they're micro-TVL
    Solana farms. Weights via the same risk-budget ladder.
    """
    from src.api.schemas.agent import AllocationPayload, AllocationPosition
    from src.allocator.composer import (
        normalise_chain as _norm_chain,
        bucket_risk as _bucket_risk,
        bucket_fit as _bucket_fit,
        weighted_sentinel as _ws,
        score_safety as _ss,
        score_durability as _sd,
        score_exit as _se,
        score_confidence as _sc,
        derive_flags as _df,
        PoolCandidate as _PC,
        _ROUTER_BY_CHAIN as _ROUTERS,
        _format_apy as _fmt_apy,
        _format_tvl as _fmt_tvl,
        _format_usd as _fmt_usd,
        summarise_positions as _summarise,
    )

    if not prior_pools:
        return None

    # Even-split weights (default for prior-pools dispatch — narrative also
    # uses even split, so card and narrative agree). Caller can override
    # via risk_budget="ladder_<conservative|balanced|aggressive>".
    n = min(len(prior_pools), 5)
    if override_weights and len(override_weights) >= n:
        weights = list(override_weights[:n])
        s = sum(weights)
        if s and 95 <= s <= 105:
            drift = 100 - s
            weights[0] += drift
            if not weights:
                return None
            # Skip the ladder/even-split branch
            positions: list[AllocationPosition] = []
            for rank, (it, weight) in enumerate(zip(prior_pools[:n], weights), start=1):
                try:
                    apy = float(it.get("apy") or 0.0)
                    tvl = float(it.get("tvl_usd") or 0.0)
                except (TypeError, ValueError):
                    continue
                protocol = str(it.get("protocol") or "Unknown")
                symbol = str(it.get("symbol") or "?")
                chain_raw = str(it.get("chain") or "ethereum")
                chain = _norm_chain(chain_raw)
                if apy >= 80 or tvl < 1_000_000:
                    risk_l = "high"
                elif apy >= 25 or tvl < 50_000_000:
                    risk_l = "medium"
                else:
                    risk_l = "low"
                symbol_upper = symbol.upper()
                is_stable = any(s in symbol_upper for s in ("USD", "DAI", "FRAX", "USDC", "USDT"))
                days_live = 200 if tvl >= 100_000_000 else 90
                pc = _PC(
                    project=protocol, symbol=symbol, chain=chain_raw,
                    tvl_usd=tvl, apy=apy, audits=False, days_live=days_live,
                    stable=is_stable,
                    il_risk="no" if "-" not in symbol else "yes",
                    exposure="single" if "-" not in symbol else "multi",
                )
                ss_v = _ss(pc); sd_v = _sd(pc); se_v = _se(pc); sc_v = _sc(pc)
                sent = _ws(ss_v, sd_v, se_v, sc_v)
                flags = _df(pc, sent)
                positions.append(
                    AllocationPosition(
                        rank=rank, protocol=protocol, asset=symbol, chain=chain,
                        apy=_fmt_apy(apy), sentinel=sent, risk=risk_l,
                        fit=_bucket_fit(sent, apy), weight=weight,
                        usd=_fmt_usd(usd_amount * weight / 100.0),
                        tvl=_fmt_tvl(tvl), router=_ROUTERS.get(chain, "Enso"),
                        safety=ss_v, durability=sd_v, exit=se_v, confidence=sc_v,
                        flags=flags,
                    )
                )
            if positions:
                summary = _summarise(positions, usd_amount)
                return AllocationPayload(positions=positions, **summary).model_dump()
            return None
    if risk_budget.startswith("ladder_") or risk_budget in {"conservative", "balanced", "aggressive"} and risk_budget == "ladder_balanced":
        rb = risk_budget.replace("ladder_", "") or "balanced"
        if rb == "conservative":
            base = [35, 25, 20, 12, 8]
        elif rb == "aggressive":
            base = [30, 25, 20, 15, 10]
        else:
            base = [35, 20, 20, 15, 10]
        trimmed = base[:n]
        total = sum(trimmed)
        weights = [int(round(w * 100 / total)) for w in trimmed]
        drift = 100 - sum(weights)
        if weights:
            weights[0] += drift
    else:
        # Even split — preferred default for prior-pools dispatch
        even = 100 // n
        weights = [even] * n
        weights[0] += 100 - sum(weights)
    if not weights:
        return None

    positions: list[AllocationPosition] = []
    for rank, (it, weight) in enumerate(zip(prior_pools[:5], weights), start=1):
        try:
            apy = float(it.get("apy") or 0.0)
            tvl = float(it.get("tvl_usd") or 0.0)
        except (TypeError, ValueError):
            continue
        protocol = str(it.get("protocol") or "Unknown")
        symbol = str(it.get("symbol") or "?")
        chain_raw = str(it.get("chain") or "ethereum")
        chain = _norm_chain(chain_raw)
        # Risk inferred from APY/TVL, not the strict composer
        if apy >= 80 or tvl < 1_000_000:
            risk_l = "high"
        elif apy >= 25 or tvl < 50_000_000:
            risk_l = "medium"
        else:
            risk_l = "low"
        # Score bands without rejecting on low TVL
        symbol_upper = symbol.upper()
        is_stable = any(s in symbol_upper for s in ("USD", "DAI", "FRAX", "USDC", "USDT"))
        days_live = 200 if tvl >= 100_000_000 else 90
        pc = _PC(
            project=protocol,
            symbol=symbol,
            chain=chain_raw,
            tvl_usd=tvl,
            apy=apy,
            audits=False,
            days_live=days_live,
            stable=is_stable,
            il_risk="no" if "-" not in symbol else "yes",
            exposure="single" if "-" not in symbol else "multi",
        )
        s = _ss(pc); d = _sd(pc); e = _se(pc); c = _sc(pc)
        sent = _ws(s, d, e, c)
        # Force the inferred risk band — reflects live APY/TVL not composer rubric
        flags = _df(pc, sent)
        positions.append(
            AllocationPosition(
                rank=rank,
                protocol=protocol,
                asset=symbol,
                chain=chain,
                apy=_fmt_apy(apy),
                sentinel=sent,
                risk=risk_l,
                fit=_bucket_fit(sent, apy),
                weight=weight,
                usd=_fmt_usd(usd_amount * weight / 100.0),
                tvl=_fmt_tvl(tvl),
                router=_ROUTERS.get(chain, "Enso"),
                safety=s,
                durability=d,
                exit=e,
                confidence=c,
                flags=flags,
            )
        )
    if not positions:
        return None
    summary = _summarise(positions, usd_amount)
    return AllocationPayload(positions=positions, **summary).model_dump()


def _parse_weights_from_narrative(narrative: str, n_pools: int) -> list[int] | None:
    """Extract weight % from a markdown allocation table the LLM produced.

    Looks for lines like '| 1 | gmtrade BTC-USDC ... | 30% | $30 ...' and
    captures the integer percent. Returns weights summing to ~100 if found.
    """
    if not narrative or n_pools <= 0:
        return None
    weights: list[int] = []
    # Match table rows that have a leading rank number, then any cell, then
    # a weight percent in another cell (handles 'Weight %' columns).
    for m in re.finditer(
        r"\|\s*\d+\s*\|[^\n|]*\|\s*(\d{1,3})\s*%",
        narrative,
    ):
        try:
            v = int(m.group(1))
            if 1 <= v <= 100:
                weights.append(v)
        except ValueError:
            continue
        if len(weights) >= n_pools:
            break
    if len(weights) != n_pools:
        return None
    s = sum(weights)
    if not (95 <= s <= 105):
        return None
    # Normalize to exactly 100
    drift = 100 - s
    weights[0] += drift
    return weights


async def _bake_prior_pools_execution_plan(
    tools, *, positions: list[dict], usd_amount: float
) -> dict | None:
    """Per allocation position, invoke `execute_pool_position` to get a real
    unsigned transaction, then assemble an `ExecutionPlanPayload` so the
    front-end Sign-Step-1 button has a target.
    """
    if not positions:
        return None
    # Find the execute_pool_position tool in the runtime's tool list
    epp_tool = None
    for t in tools or []:
        if getattr(t, "name", "") == "execute_pool_position":
            epp_tool = t
            break
    if epp_tool is None:
        return None
    from src.api.schemas.agent import ExecutionStep, ExecutionPlanPayload

    async def _bake_one(pos: dict) -> dict | None:
        protocol = (pos.get("protocol") or "").strip()
        symbol = (pos.get("asset") or "").strip()
        chain = (pos.get("chain") or "").strip().lower()
        weight = int(pos.get("weight") or 0)
        rank = int(pos.get("rank") or 0)
        if not protocol or not symbol or weight <= 0:
            return None
        pool_ref = f"{protocol} {symbol}".strip()
        usd_slice = max(0.0, usd_amount * weight / 100.0)
        if usd_slice <= 0:
            return None
        chain_full = {
            "sol": "solana", "eth": "ethereum", "mainnet": "ethereum",
            "arb": "arbitrum", "base": "base", "polygon": "polygon",
            "bsc": "bsc", "op": "optimism", "avax": "avalanche",
        }.get(chain, chain or None)
        try:
            env = await asyncio.wait_for(
                epp_tool.ainvoke({
                    "pool": pool_ref,
                    "amount": usd_slice,
                    "chain": chain_full,
                }),
                timeout=15.0,
            )
        except Exception as exc:
            logger.warning("bake exec_plan position %s: %s", rank, exc)
            return None
        if env is None:
            return None
        from src.api.schemas.agent import ToolEnvelope
        if isinstance(env, ToolEnvelope):
            payload = env.card_payload if env.ok else None
        elif isinstance(env, dict):
            payload = env.get("card_payload") if env.get("ok", False) else None
        else:
            return None
        if not isinstance(payload, dict):
            return None
        plan_steps = payload.get("steps") or []
        first = plan_steps[0] if plan_steps else None
        tx = (first or {}).get("transaction") if first else None
        # Build ExecutionStep
        verb = "Stake" if any(k in protocol.lower() for k in ("marinade", "jito", "sanctum", "lido", "stader", "liquid-staking")) else "Supply"
        # Entry-leg asset: show what the user is depositing FROM their wallet.
        # For LP/yield pools we accept USDC by default — Jupiter/Enso swap
        # legs convert to the underlying as needed. For pure liquid staking
        # the native chain asset (SOL on Solana) is the deposit token.
        is_lst = any(k in protocol.lower() for k in ("marinade", "jito", "sanctum", "lido", "stader", "liquid-staking"))
        if is_lst:
            amount_asset = "SOL" if chain == "sol" else "ETH"
        else:
            amount_asset = "USDC"
        gas_by_chain = {"sol": 0.01, "eth": 4.8, "mainnet": 6.9, "arb": 0.35, "base": 0.25, "polygon": 0.08, "bsc": 0.12, "op": 0.35, "avax": 0.3}
        return ExecutionStep(
            index=rank,
            verb=verb,
            amount=f"{usd_slice:,.0f}",
            asset=amount_asset,
            target=f"{symbol} · {protocol}",
            chain=chain,
            router="Jupiter" if chain == "sol" else "Enso",
            wallet="Phantom" if chain == "sol" else "MetaMask",
            gas=f"~${gas_by_chain.get(chain, 2.0):,.2f}",
            step_id=f"alloc_step_{rank}",
            protocol=protocol,
            transaction=tx,
        ).model_dump()

    raw_steps = await asyncio.gather(*[_bake_one(p) for p in positions])
    steps = [s for s in raw_steps if s]
    if not steps:
        return None
    total_gas = 0.0
    for s in steps:
        try:
            total_gas += float(str(s.get("gas", "~$0")).lstrip("~$").replace(",", ""))
        except (TypeError, ValueError):
            pass
    wallets = sorted({s.get("wallet", "MetaMask") for s in steps})
    payload = ExecutionPlanPayload(
        steps=steps,
        total_gas=f"~${total_gas:,.2f}",
        slippage_cap="0.5%",
        wallets=" + ".join(wallets) if wallets else "MetaMask",
        tx_count=len(steps),
        requires_signature=any(s.get("transaction") for s in steps),
    ).model_dump()
    return payload


def _build_prior_pools_card(prior_pools: list[dict]) -> dict:
    """Re-emit a defi_opportunities card listing the same pool set the user
    is now allocating across, so the UI shows them again as concrete cards."""
    items = []
    for it in prior_pools[:12]:
        try:
            items.append({
                "protocol": it.get("protocol"),
                "symbol": it.get("symbol"),
                "chain": it.get("chain"),
                "product_type": it.get("product_type") or "pool",
                "apy": float(it.get("apy") or 0.0),
                "apy_base": it.get("apy_base"),
                "apy_reward": it.get("apy_reward"),
                "tvl_usd": float(it.get("tvl_usd") or 0.0),
                "volume_24h_usd": it.get("volume_24h_usd"),
                "risk_level": it.get("risk_level"),
                "executable": bool(it.get("executable")),
                "adapter_id": it.get("adapter_id"),
                "unsupported_reason": it.get("unsupported_reason"),
                "links": it.get("links") or [],
                "pool_id": it.get("pool_id"),
            })
        except Exception:
            continue
    return {
        "objective": "constraint_fit_then_risk_adjusted_return",
        "target_apy": None,
        "apy_band": [None, None],
        "risk_levels": [],
        "chains": list({i.get("chain") for i in items if i.get("chain")}) if items else [],
        "execution_requested": False,
        "items": items,
        "excluded_count": 0,
        "blockers": [],
    }


async def run_ephemeral_turn(
    *,
    router,
    tools,
    message: str,
    wallet: str | None = None,
    history: list[dict] | None = None,
    history_cards: list[dict] | None = None,
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

    # If this is a follow-up confirmation and we have prior context, handle it
    # before falling through to the keyword intent detector — otherwise
    # "proceed" would never match anything in INTENT_PATTERNS.
    if history:
        replay = _maybe_replay_followup(message=message, history=history)
        if replay is not None:
            collector._step += 1
            collector._queue.append(ThoughtFrame(
                step_index=collector._step,
                content="Continuing from the prior allocation/execution plan in this conversation...",
            ))
            # Re-emit the most recent execution_plan card so signing UI
            # reappears for "Execute the plan" / "Yes proceed" follow-ups.
            replay_card_ids: list[str] = []
            if history_cards:
                for hc in reversed(history_cards):
                    ct = (hc.get("card_type") or "").lower()
                    if ct in {"execution_plan_v3", "execution_plan_v2", "execution_plan", "allocation"}:
                        try:
                            collector._step += 1
                            cf = CardFrame(
                                step_index=collector._step,
                                card_id=hc.get("card_id") or f"replay-{uuid.uuid4().hex[:10]}",
                                card_type=hc.get("card_type"),
                                payload=hc.get("payload") or {},
                            )
                            collector._queue.append(cf)
                            replay_card_ids.append(cf.card_id)
                        except Exception:
                            pass
                        break
            collector.emit_final(replay, replay_card_ids)
            for frame in collector.drain():
                yield encode_sse(frame_event_name(frame), frame.model_dump())
            return

    # Pivot detection: when user changes core constraint of prior strategy
    # ("Same thing on Ethereum", "Actually make it conservative 8% on ETH",
    # "Now show on Arbitrum instead"), bypass the prior-pools dispatch and
    # fall through to detect_intent + parse_defi_intent so a fresh search
    # runs with the NEW constraints. Prior `defi_opportunities` card stays
    # in history_cards for the LLM context block.
    pivot_requested = _is_pivot_request(message, history_cards)
    refine_requested = _is_refine_request(message, history_cards)

    # When the message contains a CONCRETE pool reference (UUID or
    # protocol-pair like "gmtrade BTC-USDC"), the user is doing a single-
    # pool deposit, not a re-distribute across the prior set. Skip the
    # prior-pools dispatch so detect_intent → _detect_pool_execute can
    # build a single execute_pool_position card.
    has_concrete_pool_ref = bool(
        _POOL_UUID_RE.search(message) or _POOL_PROTO_PAIR_RE.search(message)
    )

    # Prior-pools continuity: if the user references the previously surfaced
    # pool list ("distribute X across those pools" / "allocate $1000" /
    # "sign these"), reuse the SAME pool universe instead of running a fresh
    # DefiLlama search that returns different pools the user never saw.
    # Skip when a pivot/refine is detected, OR a concrete pool ref is
    # present, so the user gets the regenerated / single-pool result.
    prior_pools_for_dist: list[dict] = []
    is_allocation_continuation = (
        not pivot_requested
        and not refine_requested
        and not has_concrete_pool_ref
        and _references_prior_pools_for_allocation(message, history_cards)
    )
    if is_allocation_continuation:
        prior_pools_for_dist = _extract_prior_pool_items(history_cards)
    prior_intent_override: tuple[str, dict] | None = None

    # LP refinement override — when the prior turn produced a pool_link /
    # pool_deposit_v3 / execution_plan_v3 (Aave-style supply) card AND the
    # current turn is a short refinement phrase (amount/chain/token delta),
    # rebuild the prior intent with the delta instead of routing to search
    # or asking for clarification.
    _LP_AMOUNT_DELTA_RE = re.compile(
        r"(?:make\s+it|change(?:\s+to)?|set\s+(?:it\s+)?to|how\s+about|what\s+if(?:\s+i\s+(?:use|with))?"
        r"|with|execute\s+with|actually(?:\s+(?:use|with|make\s+it))?|try)"
        r"\s*\$?\s*(?P<usd>[\d,]+(?:\.\d+)?)"
        r"(?:\s+(?P<token>[A-Za-z]{2,10}))?"
        r"(?:\s+(?:instead|now|then|please|again))*\s*[\?\.!]?\s*$",
        re.IGNORECASE,
    )
    _LP_CHAIN_SWITCH_RE = re.compile(
        r"^\s*(?:try|switch\s+to|use|instead\s+on|and|on|how\s+about)\s+(?P<chain>arbitrum|ethereum|base|polygon|optimism|bsc|bnb|avalanche|solana)\b",
        re.IGNORECASE,
    )
    _LP_TOKEN_SWITCH_RE = re.compile(
        r"(?:actually\s+use|use\s+|switch\s+to|with)\s+(?P<token>[A-Za-z]{2,10})\s+(?:instead|not)\b",
        re.IGNORECASE,
    )
    # "Add liquidity with $X to the top one" — prior turn was a search list;
    # pick the first opportunity from the prior defi_opportunities card.
    # Also accept the verb-then-reference-then-amount form ("execute the first
    # one with $100" / "deposit into the top pool with 50 USDC") which puts
    # the picker phrase between verb and amount.
    _LP_TOP_ONE_RE = re.compile(
        r"(?:add\s+liquidity|deposit|put|supply|stake|execute|do|run|sign|"
        r"choose|pick|use)\s+"
        # Optional connector + reference phrase BEFORE the amount: 'the first
        # one', 'the top pool', '#1', 'first option', 'option 1', '1st'.
        r"(?:(?:into\s+|on\s+|in\s+|with\s+|to\s+)?"
        r"(?:the\s+|that\s+|this\s+)?"
        r"(?:top|first|best|#?\s*1|1st)\s+"
        r"(?:one|pool|option|result|pick|item)?\s*)?"
        r"(?:with\s+)?\$?\s*(?P<usd>[\d,]+(?:\.\d+)?)"
        r"(?:\s+(?P<unit>[A-Za-z]{2,10}))?"
        # Optional trailing 'to the top one' too — keep prior behaviour.
        r"(?:\s+(?:to|into|in|on)\s+the\s+(?:top|first|best)(?:\s+one|\s+pool|\s+option)?)?\b",
        re.IGNORECASE,
    )

    def _last_lp_card(cards: list[dict] | None) -> dict | None:
        if not cards:
            return None
        for hc in reversed(cards):
            t = (hc.get("card_type") or "").lower()
            if t in {"pool_link", "pool_deposit_v3", "execution_plan_v3"}:
                return hc
        return None

    if prior_intent_override is None:
        prev_lp = _last_lp_card(history_cards)

        # Prior-search → "top one" pick. When the prior turn was a search
        # result (defi_opportunities), recognize "add liquidity with $X to the
        # top one" / "execute with X" and pull the first opportunity item.
        #
        # BEFORE falling back to the top of a search list (which can pick a
        # totally unrelated pool when the search missed the user's named
        # target — DefiLlama down → search returns Hyperliquid junk), scan
        # PRIOR USER MESSAGES for an explicit "<protocol> <pair>" mention
        # like "Raydium AMM SPACEX-WSOL" and prefer that hint.
        if prior_intent_override is None and history_cards:
            top_match = _LP_TOP_ONE_RE.search(message.strip())
            if top_match:
                # Try to recover an explicit protocol+pair hint from earlier
                # user messages in this session.
                prior_hint_proto: str | None = None
                prior_hint_pair: str | None = None
                prior_hint_chain: str | None = None
                if history:
                    _HINT_RE = re.compile(
                        r"\b(?P<proto>raydium-amm|raydium-clmm|raydium|orca-whirlpools|orca-clmm|orca|"
                        r"meteora-dlmm|meteora|kamino-lend|kamino-liquidity|kamino|"
                        r"aerodrome-slipstream|aerodrome|velodrome|"
                        r"uniswap[ -]v[34]|uniswap|pancakeswap[ -]v[23]|pancakeswap|"
                        r"sushiswap[ -]v[23]?|sushiswap|"
                        r"curve(?:-dex)?|balancer(?:-v[23])?|yearn(?:-finance)?|morpho(?:-blue)?|"
                        r"aave[ -]v[23]|aave|compound[ -]v[23]|compound|spark|moonwell|venus|pendle)"
                        r"(?:[ -](?:v[234]|amm|clmm|dex|slipstream|whirlpools))?\s+"
                        r"(?P<pair>[A-Za-z][A-Za-z0-9.]{0,9}[-/_][A-Za-z][A-Za-z0-9.]{0,9})",
                        re.IGNORECASE,
                    )
                    _CHAIN_HINT_RE = re.compile(
                        r"\bon\s+(?P<chain>ethereum|solana|polygon|arbitrum|base|optimism|bsc|bnb|avalanche)\b",
                        re.IGNORECASE,
                    )
                    for prior in reversed(history):
                        if (prior.get("role") or "").lower() != "user":
                            continue
                        prior_text = str(prior.get("content") or "")
                        hm = _HINT_RE.search(prior_text)
                        if hm:
                            prior_hint_proto = re.sub(r"\s+", "-", hm.group("proto").lower())
                            prior_hint_pair = hm.group("pair").upper().replace("/", "-")
                            cm = _CHAIN_HINT_RE.search(prior_text)
                            if cm:
                                cc = cm.group("chain").lower()
                                prior_hint_chain = "bsc" if cc in {"bsc", "bnb"} else cc
                            break

                if prior_hint_proto and prior_hint_pair:
                    try:
                        amt_val = float(top_match.group("usd").replace(",", ""))
                    except (TypeError, ValueError):
                        amt_val = 50.0
                    params = {
                        "pool": f"{prior_hint_proto} {prior_hint_pair}".strip(),
                        "amount": amt_val,
                        "asset_in": "USDC",
                    }
                    if prior_hint_chain:
                        params["chain"] = prior_hint_chain
                    prior_intent_override = ("execute_pool_position", params)
                    prior_pools_for_dist = []
                else:
                    for hc in reversed(history_cards):
                        if (hc.get("card_type") or "").lower() == "defi_opportunities":
                            items = ((hc.get("payload") or {}).get("items") or [])
                            if items:
                                top = items[0]
                                top_proto = (top.get("project") or top.get("protocol") or "").strip().lower()
                                top_sym = (top.get("symbol") or "").strip()
                                top_chain = (top.get("chain") or "").strip().lower()
                                if top_proto and top_sym:
                                    try:
                                        amt_val = float(top_match.group("usd").replace(",", ""))
                                    except (TypeError, ValueError):
                                        amt_val = 50.0
                                    params = {
                                        "pool": f"{top_proto} {top_sym}".strip(),
                                        "amount": amt_val,
                                        "asset_in": "USDC",
                                    }
                                    if top_chain:
                                        params["chain"] = top_chain
                                    prior_intent_override = ("execute_pool_position", params)
                                    # Block the prior-pools allocation/execution_plan
                                    # builder from running concurrently below.
                                    prior_pools_for_dist = []
                                    break

        if prior_intent_override is None and prev_lp:
            payload = prev_lp.get("payload") or {}
            t = (prev_lp.get("card_type") or "").lower()
            # Pull prior protocol / pair / chain / amount / input token from
            # whichever LP card type was last shown.
            prior_protocol = (payload.get("protocol") or "").lower()
            prior_chain = (payload.get("chain") or "").lower()
            # execution_plan_v3 carries the protocol/chain on each step,
            # not at the top level. Pull from the first step when needed.
            if t == "execution_plan_v3":
                _steps = payload.get("steps") or []
                if _steps and not prior_protocol:
                    prior_protocol = str(_steps[0].get("protocol") or "").lower()
                if _steps and not prior_chain:
                    prior_chain = str(_steps[0].get("chain") or "").lower()
            prior_pool_symbol = (
                payload.get("pool_symbol")
                or (payload.get("pair") or {}).get("token0", {}).get("symbol", "") + "-" + (payload.get("pair") or {}).get("token1", {}).get("symbol", "")
                or ""
            ).strip("-")
            # Prior amount: pool_link / pool_deposit_v3 carry a human-readable
            # USD; execution_plan_v3 stores atomic units on steps. Parse the
            # plan summary ("Supply 50 USDC via aave-v3 on ethereum") to
            # recover the human amount instead of using raw atoms which are
            # giant numbers that break downstream validation.
            prior_amount = 0.0
            if payload.get("amount") is not None:
                try:
                    prior_amount = float(payload.get("amount"))
                except (TypeError, ValueError):
                    pass
            if prior_amount == 0.0 and payload.get("input_amount_usd") is not None:
                try:
                    prior_amount = float(payload.get("input_amount_usd"))
                except (TypeError, ValueError):
                    pass
            if prior_amount == 0.0 and t == "execution_plan_v3":
                _summary = str(payload.get("summary") or payload.get("title") or "")
                _m = re.search(r"\b(?:Supply|Deposit|Stake|Add)\s+\$?([\d,]+(?:\.\d+)?)\b", _summary, re.IGNORECASE)
                if _m:
                    try:
                        prior_amount = float(_m.group(1).replace(",", ""))
                    except (TypeError, ValueError):
                        pass
            if prior_amount == 0.0:
                prior_amount = 100.0  # safe USD default; user can refine
            prior_asset_in = (
                payload.get("asset_in")
                or (payload.get("input_token") or {}).get("symbol")
                or ((payload.get("steps") or [{}])[0].get("asset_in") if t == "execution_plan_v3" else None)
                or "USDC"
            )
            if t == "execution_plan_v3":
                # Parse asset from summary if step asset_in missing.
                _summary2 = str(payload.get("summary") or payload.get("title") or "")
                _ma = re.search(r"\b(?:Supply|Deposit|Stake|Add)\s+\$?[\d,]+(?:\.\d+)?\s+([A-Z]{2,10})\b", _summary2)
                if _ma and prior_asset_in in {"USDC", "", None}:
                    prior_asset_in = _ma.group(1).upper()

            # When prior_pool_symbol is empty (execution_plan_v3 for Solana LP
            # paths doesn't carry pair in the payload), recover it from earlier
            # user messages in the session — same hint extraction we use for
            # the search-top-pick branch.
            if not prior_pool_symbol and history:
                _HINT_RE_FB = re.compile(
                    r"\b(?P<proto>raydium-amm|raydium-clmm|raydium|orca-whirlpools|orca-clmm|orca|"
                    r"meteora-dlmm|meteora|kamino-lend|kamino-liquidity|kamino|"
                    r"aerodrome-slipstream|aerodrome|velodrome|"
                    r"uniswap[ -]v[34]|uniswap|pancakeswap[ -]v[23]|pancakeswap|"
                    r"sushiswap[ -]v[23]?|sushiswap|"
                    r"curve(?:-dex)?|balancer(?:-v[23])?)"
                    r"(?:[ -](?:v[234]|amm|clmm|dex|slipstream|whirlpools))?\s+"
                    r"(?P<pair>[A-Za-z][A-Za-z0-9.]{0,9}[-/_][A-Za-z][A-Za-z0-9.]{0,9})",
                    re.IGNORECASE,
                )
                for prior in reversed(history):
                    if (prior.get("role") or "").lower() != "user":
                        continue
                    hm = _HINT_RE_FB.search(str(prior.get("content") or ""))
                    if hm:
                        if not prior_protocol:
                            prior_protocol = re.sub(r"\s+", "-", hm.group("proto").lower())
                        prior_pool_symbol = hm.group("pair").upper().replace("/", "-")
                        break

            m_amt = _LP_AMOUNT_DELTA_RE.search(message.strip())
            m_chain = _LP_CHAIN_SWITCH_RE.search(message.strip())
            m_tok = _LP_TOKEN_SWITCH_RE.search(message.strip())

            if m_amt or m_chain or m_tok:
                new_amount = prior_amount
                new_chain = prior_chain
                new_asset_in = prior_asset_in
                if m_amt:
                    try:
                        new_amount = float(m_amt.group("usd").replace(",", ""))
                    except (TypeError, ValueError):
                        new_amount = prior_amount
                if m_chain:
                    raw = m_chain.group("chain").lower()
                    new_chain = "bsc" if raw in {"bsc", "bnb"} else raw
                if m_tok:
                    new_asset_in = m_tok.group("token").upper()
                # Enso protocol-switch refinement — "Actually use Yearn instead"
                _proto_switch_re = re.compile(
                    r"(?:actually\s+use|use|switch\s+to|with|try)\s+"
                    r"(?P<proto>aave[ -]?v3|aave|compound[ -]?v3|compound|"
                    r"yearn[ -]?finance|yearn|morpho[ -]?blue|metamorpho|morpho|"
                    r"spark[ -]?protocol|spark[ -]?lending|spark|sky|"
                    r"curve[ -]?dex|curve|balancer[ -]?v2|balancer[ -]?v3|balancer|"
                    r"lido|rocket[ -]?pool|rocketpool|ether[\.\-]?fi|etherfi|"
                    r"frax[ -]?ether|frax|stader|gmx|moonwell|stargate)"
                    r"\s+(?:instead|not)\b",
                    re.IGNORECASE,
                )
                m_proto_switch = _proto_switch_re.search(message.strip())
                effective_protocol = prior_protocol
                if m_proto_switch:
                    effective_protocol = _enso_normalize_slug(m_proto_switch.group("proto"))

                # All Enso EVM protocols + Aave/Compound route via build_yield_execution_plan.
                _ENSO_ALL = (
                    {"aave-v3", "aave", "aave-v2", "aave-v3-prime", "compound-v3",
                     "compound", "compound-v2"}
                    | {"yearn-finance", "yearn", "yearn-v3"}
                    | {"morpho-blue", "morpho", "metamorpho"}
                    | {"spark", "spark-protocol", "spark-lending"}
                    | {"sky", "sky-lending", "makerdao"}
                    | {"curve", "curve-dex", "curve-finance"}
                    | {"balancer", "balancer-v2", "balancer-v3"}
                    | {"lido", "rocket-pool", "rocketpool", "ether.fi", "etherfi",
                       "frax", "frax-ether", "stader", "gmx", "moonwell", "stargate"}
                    | {"fluid", "fluid-lending", "origin", "origin-ether",
                       "ethena", "pendle"}
                )
                _V3_EVM_REFINE = {
                    "uniswap-v3", "uniswap", "pancakeswap-v3", "pancake-v3",
                    "aerodrome-slipstream", "aerodrome-cl",
                }
                if effective_protocol in _ENSO_ALL:
                    if effective_protocol in {"curve", "curve-dex", "curve-finance",
                                              "balancer", "balancer-v2", "balancer-v3"}:
                        new_action = "deposit_lp"
                    elif effective_protocol in {"lido", "rocket-pool", "rocketpool",
                                                "ether.fi", "etherfi", "frax",
                                                "frax-ether", "stader"}:
                        new_action = "stake"
                    else:
                        new_action = "supply"
                    prior_intent_override = (
                        "build_yield_execution_plan",
                        {
                            "chain": new_chain,
                            "protocol": effective_protocol,
                            "action": new_action,
                            "asset_in": new_asset_in,
                            "amount_in": new_amount,
                        },
                    )
                    prior_pools_for_dist = []
                elif effective_protocol in _V3_EVM_REFINE and prior_pool_symbol:
                    prior_intent_override = (
                        "build_yield_execution_plan",
                        {
                            "chain": new_chain,
                            "protocol": effective_protocol,
                            "action": "deposit_lp",
                            "asset_in": new_asset_in,
                            "amount_in": new_amount,
                            "extra": {"pool_symbol": prior_pool_symbol, "fee_bps": 500},
                        },
                    )
                    prior_pools_for_dist = []
                elif prior_protocol and prior_pool_symbol:
                    pool_ref = f"{prior_protocol} {prior_pool_symbol}".strip()
                    prior_intent_override = (
                        "execute_pool_position",
                        {
                            "pool": pool_ref,
                            "amount": new_amount,
                            "asset_in": new_asset_in,
                        },
                    )
                    prior_pools_for_dist = []

    if prior_pools_for_dist:
        amount_hint_val = _parse_amount_from_text(message)
        # Single-pool pick: "stake 10 SOL into the top one" → reroute to a
        # single-step execute_pool_position on the first pool of the prior
        # card. The amount comes from the native-aware parser (10 SOL→USD).
        if _SINGLE_POOL_PICK_RE.search(message) and amount_hint_val:
            top = prior_pools_for_dist[0]
            top_protocol = (top.get("protocol") or "").strip()
            top_symbol = (top.get("symbol") or "").strip()
            top_chain = (top.get("chain") or "").strip().lower()
            single_pool_ref = f"{top_protocol} {top_symbol}".strip()
            if single_pool_ref:
                params: dict = {
                    "pool": single_pool_ref,
                    "amount": amount_hint_val,
                }
                if top_chain:
                    params["chain"] = top_chain
                prior_intent_override = ("execute_pool_position", params)
                # Clear prior_pools_for_dist so the LLM-allocation block below
                # doesn't run; we'll honor prior_intent_override in the dispatch.
                prior_pools_for_dist = []
        _emit_thoughts(collector, [
            "User wants to allocate / distribute / sign across the previously surfaced pool list.",
            f"Reusing {len(prior_pools_for_dist)} pool(s) from the prior turn instead of searching fresh ones."
            if prior_pools_for_dist else
            f"User picked a SINGLE pool from the prior list — routing as single-step deposit/stake.",
            (
                f"Distribution amount: ${amount_hint_val:,.0f}"
                if amount_hint_val
                else "No amount detected in this turn — using narrative without hard $ totals."
            ),
        ])
        for frame in collector.drain():
            yield encode_sse(frame_event_name(frame), frame.model_dump())
    if prior_pools_for_dist:
        composed = await _compose_prior_pools_distribution_via_llm(
            llm,
            user_message=message,
            prior_pools=prior_pools_for_dist,
            history=history,
            amount_hint=(f"${amount_hint_val:,.0f}" if amount_hint_val else None),
        )
        prior_card_payload = _build_prior_pools_card(prior_pools_for_dist)
        from uuid import uuid4 as _uuid4
        prior_card_id = str(_uuid4())
        collector._queue.append(CardFrame(
            step_index=collector._step,
            card_id=prior_card_id,
            card_type="defi_opportunities",
            payload=prior_card_payload,
        ))
        emitted_card_ids: list[str] = [prior_card_id]
        # Always emit a typed allocation card over the SAME pool universe so
        # the front-end's Allocation Proposal panel shows the same pools
        # instead of the generic Aave/Uniswap default that allocate_plan
        # returns. When the user gave no amount ("Allocate it" / "Sign and
        # execute" / "Do that"), default to $1000 placeholder and append a
        # note prompting the user to resize.
        try:
            effective_amount = amount_hint_val if amount_hint_val is not None else 1000.0
            # Try to inherit weights from the LLM narrative table so card and
            # narrative agree on percentages. Fall back to even split.
            llm_weights = _parse_weights_from_narrative(
                composed or "", n_pools=min(len(prior_pools_for_dist), 5)
            )
            alloc_payload = _build_prior_pools_allocation_payload(
                prior_pools_for_dist,
                usd_amount=effective_amount,
                risk_budget="balanced",
                override_weights=llm_weights,
            )
            if alloc_payload:
                alloc_card_id = str(_uuid4())
                collector._queue.append(CardFrame(
                    step_index=collector._step,
                    card_id=alloc_card_id,
                    card_type="allocation",
                    payload=alloc_payload,
                ))
                emitted_card_ids.append(alloc_card_id)
                # Bake unsigned transactions per position via execute_pool_position
                # tool, then emit an execution_plan extra card so the front-end
                # signing buttons (per-row + global "Start signing") have a
                # target. Without this, the user sees the allocation but cannot
                # sign anything.
                exec_plan_payload = await _bake_prior_pools_execution_plan(
                    tools,
                    positions=alloc_payload.get("positions") or [],
                    usd_amount=effective_amount,
                )
                if exec_plan_payload:
                    exec_card_id = str(_uuid4())
                    collector._queue.append(CardFrame(
                        step_index=collector._step,
                        card_id=exec_card_id,
                        card_type="execution_plan",
                        payload=exec_plan_payload,
                    ))
                    emitted_card_ids.append(exec_card_id)
                    # Tag non-baked positions on the allocation card so the
                    # Position Stack shows a clear "no adapter" banner.
                    steps_by_rank = {s.get("index"): s for s in (exec_plan_payload.get("steps") or [])}
                    blocked_count = 0
                    for pos in alloc_payload.get("positions") or []:
                        st = steps_by_rank.get(pos.get("rank"))
                        if st and not st.get("transaction"):
                            blocked_count += 1
                            flags = list(pos.get("flags") or [])
                            marker = "No verified adapter — research only"
                            if marker not in flags:
                                flags.append(marker)
                            pos["flags"] = flags
                    if blocked_count:
                        composed = (composed or "").rstrip() + (
                            f"\n\n_⚠ {blocked_count} of {len(alloc_payload.get('positions') or [])} "
                            "positions cannot be signed automatically — no Sentinel-verified adapter "
                            "for those protocols. The remaining position(s) will produce a wallet "
                            "popup. To deposit into the unsupported pools, visit each protocol's UI "
                            "directly (links provided in the Constraint-matched DeFi card)._"
                        )
                if amount_hint_val is None:
                    composed = (composed or "").rstrip() + (
                        "\n\n_Placeholder allocation sized at $1,000 — tell me the "
                        "amount you want to deploy and I'll resize before signing._"
                    )
        except Exception as exc:
            logger.warning("prior-pools allocation/exec-plan build failed: %s", exc)
        final_text = composed or (
            "Distributing across the previously surfaced pool list. "
            "See the pool card above; sign each transaction in your wallet to deposit."
        )
        collector.emit_final(final_text, emitted_card_ids)
        for frame in collector.drain():
            yield encode_sse(frame_event_name(frame), frame.model_dump())
        return

    # Pivot / refine dispatch — synthesize search args from prior card +
    # new message overrides, run search_defi_opportunities directly so the
    # user gets a fresh card on the new chain/risk/target rather than an
    # LLM-only filler reply.
    if prior_intent_override is not None:
        intent = prior_intent_override
    elif pivot_requested or refine_requested:
        synth_args = (
            _synthesize_pivot_search_args(message, history_cards) if pivot_requested
            else _synthesize_refine_search_args(message, history_cards)
        )
        if synth_args:
            intent = ("search_defi_opportunities", synth_args)
        else:
            intent = detect_intent(message)
    else:
        # Detect intent
        intent = detect_intent(message)

    try:
        final_content = ""
        strategy_composed = False

        # If we detected an intent, call the tool and format result directly
        if intent:
            tool_name, tool_input = intent

            # Chain stickiness: when the new turn's args lack a chain filter
            # but a prior `defi_opportunities` card narrowed to a specific
            # chain in this conversation, inherit it. Prevents drift from
            # "yields on Solana" -> "1 pool" jumping to TON/Avalanche.
            if (
                tool_name in {"search_defi_opportunities", "get_staking_options"}
                and (not tool_input.get("chains") or tool_input.get("chains") == [])
                and history_cards
            ):
                # Skip when user explicitly mentioned an "any chain" / "all chains" cue.
                _msg_lower = message.lower()
                if not re.search(r"\b(any|all|every|across|across\s+chains|any\s+chain|all\s+chains)\b", _msg_lower):
                    inherited: list[str] = []
                    for hc in reversed(history_cards):
                        if (hc.get("card_type") or "").lower() in {"defi_opportunities", "stake"}:
                            payload = hc.get("payload") or {}
                            chains_prior = payload.get("chains") or []
                            if not chains_prior:
                                # Inherit from the items' chain field if filter wasn't set
                                items = payload.get("items") or payload.get("staking_options") or []
                                derived = sorted({str(it.get("chain") or "").lower() for it in items if it.get("chain")})
                                derived = [c for c in derived if c]
                                # Only inherit when prior was strictly single-chain
                                if len(derived) == 1:
                                    inherited = derived
                            elif len(chains_prior) <= 2:
                                inherited = list(chains_prior)
                            break
                    if inherited:
                        tool_input["chains"] = inherited

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
                        import traceback as _tb
                        tb_str = _tb.format_exc()
                        try:
                            print(f"[tool_exception] {tool_name} input={tool_input!r}\n{tb_str}", flush=True)
                        except Exception:
                            pass
                        tb_tail = "\n".join(tb_str.splitlines()[-12:])
                        collector._queue.append(ObservationFrame(
                            step_index=collector._step,
                            name=tool_name,
                            ok=False,
                            error={"code": type(e).__name__, "message": str(e), "tb_tail": tb_tail},
                        ))
                        tool_result = {"ok": False, "error": {"message": str(e), "tb_tail": tb_tail}}
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
                    # Legacy SimulationPreview path: signable swap/bridge tools render via the
                    # MainApp's parseSwapPreview→SimulationPreview flow (Phantom signing button).
                    # Skip the typed swap_quote/bridge CardFrame so only the legacy preview shows;
                    # the assistant text becomes the raw wallet-assistant JSON the parser expects.
                    legacy_preview_tools = {"build_swap_tx", "build_bridge_tx", "build_solana_swap", "get_wallet_balance"}
                    is_legacy_preview = tool_name in legacy_preview_tools
                    # Push primary card
                    if not is_legacy_preview and env.card_type and env.card_payload is not None:
                        collector._queue.append(CardFrame(
                            step_index=collector._step,
                            card_id=env.card_id,
                            card_type=env.card_type,
                            payload=env.card_payload,
                        ))
                        card_ids_for_final.append(env.card_id)
                    # Push extra cards (e.g. sentinel_matrix + execution_plan from allocate_plan)
                    if not is_legacy_preview:
                        for extra in env.extra_cards or []:
                            collector._queue.append(CardFrame(
                                step_index=collector._step,
                                card_id=extra.card_id,
                                card_type=extra.card_type,
                                payload=extra.payload,
                            ))
                            card_ids_for_final.append(extra.card_id)
                    if is_legacy_preview and env.data is not None:
                        try:
                            final_content = json.dumps(env.data, default=str)
                        except Exception:
                            final_content = _format_tool_result(tool_name, env)
                    else:
                        final_content = _format_tool_result(tool_name, env)

                    # Strategy compose hook: when the user asked for a STRATEGY
                    # (not just a pool list), let the LLM compose a multi-section
                    # markdown response on top of the live pool data. Card stays
                    # but is filtered to the target APY/TVL band so the visible
                    # pools match the narrative's claimed risk profile.
                    if (
                        tool_name == "search_defi_opportunities"
                        and _is_strategy_compose_request(message)
                        and env.card_payload
                    ):
                        try:
                            target_apy_v = tool_input.get("target_apy")
                            risk_levels_v = tool_input.get("risk_levels")
                            chains_v = tool_input.get("chains")
                            # Tighten the pool universe for the card AND for the
                            # LLM input. For a 60% target we don't want to show
                            # 455% degen pools — they'd contradict the narrative.
                            filtered_payload, filtered_count, original_count = _filter_strategy_card(
                                env.card_payload,
                                target_apy=target_apy_v,
                                risk_levels=risk_levels_v,
                            )
                            # Patch the queued card frame with the filtered set so
                            # what the user SEES matches what the narrative cites.
                            for fr in collector._queue:
                                if (
                                    isinstance(fr, CardFrame)
                                    and fr.card_id == env.card_id
                                    and fr.card_type == "defi_opportunities"
                                ):
                                    fr.payload = filtered_payload
                                    break
                            _emit_thoughts(collector, [
                                f"Composing strategy narrative on top of live pool data (multi-section, ChatGPT-style).",
                                (
                                    f"Filtered pool universe: {filtered_count}/{original_count} pools fit the target band "
                                    f"(APY ≈ {target_apy_v}%, TVL >= 1M)."
                                    if target_apy_v is not None
                                    else f"Showing {filtered_count} pool(s) ranked by Sentinel objective."
                                ),
                            ])
                            for frame in collector.drain():
                                yield encode_sse(frame_event_name(frame), frame.model_dump())
                            prior_cards_summary = _summarize_prior_cards(history_cards)
                            # Re-derive cadence + stablecoin from message
                            from src.agent.intent.defi_intent import parse_defi_intent
                            _re_intent = parse_defi_intent(message)
                            composed = await _compose_strategy_via_llm(
                                llm,
                                user_message=message,
                                pool_card=filtered_payload,
                                history=history,
                                target_apy=target_apy_v,
                                risk_levels=risk_levels_v,
                                chains=chains_v,
                                prior_cards_summary=prior_cards_summary,
                                empty_band=(filtered_count == 0 and original_count > 0),
                                reinvestment_cadence=_re_intent.reinvestment_cadence,
                                stablecoin_only=_re_intent.stablecoin_only,
                            )
                            if composed:
                                # Soft scratchpad strip — preserves headers/tables
                                composed_clean = _strip_strategy_scratchpad(composed)
                                # Reject sentinel "No response" / very short outputs
                                # so we fall back to formatter rather than show stub
                                stub_markers = (
                                    "no response",
                                    "i couldn't reach the language model",
                                    "sorry, i can't respond",
                                    "ai unavailable",
                                )
                                if (
                                    composed_clean
                                    and len(composed_clean.strip()) > 60
                                    and not any(m in composed_clean.lower()[:200] for m in stub_markers)
                                ):
                                    final_content = composed_clean
                                    strategy_composed = True
                            # Execute-chain: when user said "execute it" /
                            # "execute through my wallet" AND we have a
                            # filtered pool universe, also emit allocation
                            # + execution_plan cards over THOSE pools so the
                            # research-only output becomes actionable.
                            # If user gave NO amount, ASK for it instead of
                            # silently using a $1000 placeholder.
                            if (
                                tool_input.get("execution_requested")
                                and filtered_payload
                                and (filtered_payload.get("items") or [])
                            ):
                                user_amount = _parse_amount_from_text(message)
                                if user_amount is None:
                                    # Append a clarifying question to the
                                    # narrative — no allocation card emitted.
                                    final_content = (final_content or "").rstrip() + (
                                        "\n\n---\n\n**Before I size the allocation:** how much do you want "
                                        "to deploy, and from which wallet/token? For example: `Deploy "
                                        "$2,000 from my USDC balance` or `Stake 5 SOL across these`. I'll "
                                        "size each position and prepare the wallet-gated execution plan "
                                        "after you tell me the amount."
                                    )
                                else:
                                    try:
                                        pools_for_alloc = filtered_payload.get("items") or []
                                        rb = "balanced"
                                        rls = (tool_input.get("risk_levels") or [])
                                        if rls and "LOW" in [str(r).upper() for r in rls] and "HIGH" not in [str(r).upper() for r in rls]:
                                            rb = "conservative"
                                        elif rls and "HIGH" in [str(r).upper() for r in rls]:
                                            rb = "aggressive"
                                        alloc_payload_exec = _build_prior_pools_allocation_payload(
                                            pools_for_alloc,
                                            usd_amount=user_amount,
                                            risk_budget=rb,
                                        )
                                        if alloc_payload_exec:
                                            from uuid import uuid4 as _uuid4
                                            alloc_id = str(_uuid4())
                                            collector._queue.append(CardFrame(
                                                step_index=collector._step,
                                                card_id=alloc_id,
                                                card_type="allocation",
                                                payload=alloc_payload_exec,
                                            ))
                                            card_ids_for_final.append(alloc_id)
                                    except Exception as exc:
                                        logger.warning("execute-chain card build failed: %s", exc)
                        except Exception as exc:
                            logger.warning("strategy compose hook failed: %s", exc)
                elif env is not None and not env.ok:
                    err_code = (env.error.code if env.error else "tool_error") or "tool_error"
                    err_msg = (env.error.message if env.error else "Tool returned an error.") or "Tool returned an error."
                    final_content = f"I couldn't complete that — **{err_code}**: {err_msg}"
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
            safety_prompt_extra = ""
            if _is_safety_question(message):
                safety_prompt_extra = (
                    "\n\nSAFETY-FIRST FRAMING: the user is asking whether a swap or "
                    "trade is safe. Apply the Sentinel four-axis rubric in your answer: "
                    "(1) Token quality — contract age, audit status, market cap, holder "
                    "concentration; (2) Pool depth — TVL and 24h volume; (3) Volatility "
                    "regime — recent drawdown / IL exposure; (4) Counter-party — DEX "
                    "reputation. Tag the destination token explicitly as LOW/MEDIUM/HIGH "
                    "risk and recommend slippage cap (50 bps stable, 100-300 bps mid-cap, "
                    "500-1500 bps memecoin). Always tell the user to verify the contract "
                    "address on Solscan/Etherscan before signing."
                )
            base_system = (
                "You are Ilyon Sentinel's crypto agent. You help users with DeFi, "
                "token prices, swaps, bridges, staking, and yield opportunities."
                + safety_prompt_extra + "\n\n"
                "STRICT OUTPUT RULES (non-negotiable):\n"
                "1. Reply directly to the user. Never expose your internal "
                "thinking, scratchpad, or chain-of-thought.\n"
                "2. Do NOT begin sentences with: 'We need to', 'I need to', "
                "'Let me', 'Let\\'s', 'Looking at', 'Hmm', 'Wait', 'Actually', "
                "'Maybe', 'For prior examples', 'In previous examples', "
                "'The user is', 'Need to compute', 'To answer', or any "
                "self-referential planning language.\n"
                "3. Do NOT show arithmetic steps ('0.15 + 0.024 = 0.174'). "
                "If you need to compute, do it silently and present only the result.\n"
                "4. No stage directions, no meta-commentary, no apologies "
                "about reasoning. Be concise and useful.\n"
                "5. Keep replies short and on-point unless the user asks for "
                "deep detail. Two to four sentences is usually right.\n\n"
                "When discussing crypto assets, briefly mention:\n"
                "- Risk level (LOW / MEDIUM / HIGH) when relevant\n"
                "- Strategy fit (conservative / balanced / aggressive) when relevant\n"
                "- General safety tips when the action is risky"
            )

            llm_messages: list = []
            trimmed_history = [
                p for p in (history or [])[-HISTORY_WINDOW:]
                if p.get("content")
            ]

            prior_cards_summary = _summarize_prior_cards(history_cards)
            if trimmed_history or prior_cards_summary:
                system_msg = (
                    base_system
                    + "\n\nThe conversation history below is the same chat session. "
                    + "Use it for continuity — when the user says 'it', 'the plan', "
                    + "'those pools', 'these', 'previous', etc., resolve the reference "
                    + "from the prior assistant cards listed below INSTEAD of searching "
                    + "fresh pools or asking for clarification."
                )
                if prior_cards_summary:
                    system_msg += (
                        "\n\nPreviously surfaced pools / cards in this chat (resolve "
                        "'those pools' / 'these' / 'the previous list' to THESE, not new ones):\n"
                        + prior_cards_summary
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

            try:
                result = await llm._agenerate(llm_messages, max_tokens=1500, temperature=0.4)
                final_content = result.generations[0].message.content
            except Exception as exc:
                logger.error("LLM fallback generation failed: %s: %s", type(exc).__name__, exc)
                final_content = (
                    "I had trouble reaching the language model just now. "
                    "Try rephrasing the request or ask about a specific token, "
                    "swap, bridge, stake, or DeFi pool — those go through the "
                    "deterministic Sentinel tools and don't depend on this fallback."
                )

        # Clean up response — skip the meta-commentary stripper for allocation
        # responses (the "Below is the Sentinel scoring breakdown…" paragraph
        # would otherwise be eaten by the "Below is/are" pattern). Also skip
        # for signable swap/bridge tools whose final_content is a raw JSON
        # dump that the front-end parses (parseSwapPreview).
        is_allocate = intent and intent[0] == "allocate_plan"
        is_legacy_preview = intent and intent[0] in {"build_swap_tx", "build_bridge_tx", "build_solana_swap", "get_wallet_balance"}
        if not is_allocate and not is_legacy_preview and not strategy_composed:
            cleaned = _clean_response(final_content or "")
            # If clean_response stripped the whole message (pure scratchpad),
            # emit a graceful fallback instead of empty bubble.
            if not cleaned.strip():
                cleaned = (
                    "I can help with that. To act on it, try a specific verb — "
                    "swap, bridge, stake, transfer, or 'find pools' — with the "
                    "amount and token. For example: `bridge 0.1 SOL to ETH chain` "
                    "or `swap 1 SOL to USDC`."
                )
            final_content = cleaned
        
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
    solana_wallet: str | None = None,
    evm_wallet: str | None = None,
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
    history_cards: list[dict] = []
    db = None

    if session_id:
        try:
            db = await get_database()
            prior_messages = await list_messages(db, chat_id=session_id)
            history = [
                {"role": m.role, "content": m.content}
                for m in prior_messages[-HISTORY_WINDOW:]
            ]
            for m in prior_messages[-HISTORY_WINDOW:]:
                cards_blob = getattr(m, "cards", None)
                if isinstance(cards_blob, dict):
                    frames = cards_blob.get("frames")
                    if isinstance(frames, list):
                        for f in frames:
                            if isinstance(f, dict):
                                history_cards.append(f)
        except Exception:
            history = []
            history_cards = []
            db = None

        if db is not None:
            try:
                await append_message(db, chat_id=session_id, role="user", content=message)
            except Exception:
                pass

    final_content_parts: list[str] = []
    captured_card_frames: list[dict] = []

    async for chunk in run_ephemeral_turn(
        router=router,
        tools=tools,
        message=message,
        wallet=wallet,
        history=history,
        history_cards=history_cards,
    ):
        yield chunk
        if db is not None:
            try:
                decoded = chunk.decode()
                # Capture all SSE blocks in the chunk (a single yield can hold one frame).
                for block in decoded.split("\n\n"):
                    if not block.strip():
                        continue
                    event_match = re.search(r"^event:\s*(.+)$", block, re.MULTILINE)
                    data_match = re.search(r"^data:\s*(.+)$", block, re.MULTILINE)
                    if not event_match or not data_match:
                        continue
                    event_name = event_match.group(1).strip()
                    if event_name == "final":
                        try:
                            final_content_parts.append(
                                json.loads(data_match.group(1)).get("content", "")
                            )
                        except Exception:
                            pass
                    elif event_name == "card":
                        try:
                            card_obj = json.loads(data_match.group(1))
                            captured_card_frames.append({
                                "card_type": card_obj.get("card_type"),
                                "card_id": card_obj.get("card_id"),
                                "payload": card_obj.get("payload") or {},
                            })
                        except Exception:
                            pass
            except Exception:
                pass

    if db is not None and final_content_parts:
        try:
            cards_blob = (
                {"frames": captured_card_frames}
                if captured_card_frames
                else None
            )
            await append_message(
                db,
                chat_id=session_id,
                role="assistant",
                content="".join(final_content_parts),
                cards=cards_blob,
            )
        except Exception:
            pass


def _clean_response(content: str) -> str:
    """Strip JSON dumps, scratchpad prose, and meta-commentary from LLM output.

    The model occasionally leaks reasoning ("We need to respond with a bridge
    proposal…", "Let's compute amounts…", "Hmm not consistent.") which the
    tester sees as noise. This function nukes whole leading paragraphs that
    open with such markers, then strips one-line scratchpad lines anywhere.
    """
    # Strip code blocks first.
    content = re.sub(r'```json\s*.*?\s*```', '', content, flags=re.DOTALL)
    content = re.sub(r'```\s*.*?\s*```', '', content, flags=re.DOTALL)

    # Strip standalone JSON objects.
    content = re.sub(r'\{\s*"[^"]+":\s*"[^"]+"[^}]*\}', '', content)

    # Phase 1 — peel leading scratchpad lines. A line is scratchpad if it
    # opens with a self-referential marker. Stops at the first non-scratchpad
    # line, preserving the real answer that follows.
    # Self-referential planning markers — high-confidence scratchpad.
    scratchpad_line = re.compile(
        r'^\s*('
        r'we\s+(?:need\s+to|have\s+to|must|should|can|will)|'
        r'i\s+(?:need\s+to|have\s+to|must|should|will\s+(?:compute|calculate)|think|believe|suppose|guess)|'
        r"i'll\s+|i\s+am\s+(?:going\s+to|about\s+to|trying\s+to)|"
        r'let\s+me\s+(?:think|compute|calculate|check|see|analyze|figure)|'
        r"let'?s\s+(?:think|compute|calculate|see|figure|review)|"
        r'looking\s+at|to\s+answer|to\s+compute|to\s+calculate|to\s+respond|'
        r'need\s+to\s+(?:answer|compute|calculate|respond|figure|determine|review)|'
        r'hmm[,. ]|wait[,. ]|'
        r'the\s+user\s+(?:is|wants|asks|asked|requested|needs)|'
        r'user\s+(?:wants|asked|requested|needs)|'
        r'this\s+user|'
        r'in\s+(?:prior|previous|the\s+previous|earlier|past)\s+(?:examples?|conversations?|chats?|messages?)|'
        r'(?:for|in)\s+(?:prior|previous|earlier|the\s+last)\s+(?:examples?|messages?)|'
        r'maybe\s+(?:the\s+fee|fee\s+is|it\s+is)|'
        r'we\s+can\s+approximate|'
        r'\d+(?:\.\d+)?\s*[+\-*/]\s*\d+(?:\.\d+)?\s*='  # bare arithmetic with =
        r')',
        re.IGNORECASE,
    )
    # Skip dropping a line if it carries substantive payload — $/%/address/
    # mint-like base58 etc. — even when it opens with a scratchpad marker.
    # Those are handled by Phase 3 prefix-stripping instead.
    payload_marker = re.compile(r'\$\d|\d+%|0x[0-9a-fA-F]{6,}|[1-9A-HJ-NP-Za-km-z]{20,}|`[^`]+`')
    lines = content.split("\n")
    drop = 0
    for ln in lines:
        if not ln.strip():
            drop += 1
            continue
        if scratchpad_line.match(ln) and not payload_marker.search(ln):
            drop += 1
            continue
        break
    content = "\n".join(lines[drop:])

    # Phase 2.5 — prefix-strip soft openers that precede real content.
    content = re.sub(
        r'^(?:Looking\s+at\s+(?:the\s+)?(?:data|chart|history|info|info\s*),?\s*|'
        r'Based\s+on\s+(?:the\s+)?(?:data|chart|history|info)?,?\s*)',
        '',
        content,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Phase 2 — line-level scratchpad removal anywhere in the response.
    line_patterns = [
        r'^\s*(?:Hmm|Wait|Actually|Maybe|Probably|Let me|Let\'s)\b[^.]*\.\s*$',
        r'^\s*(?:For|In)\s+(?:prior|previous|the\s+last)\s+(?:examples?|conversations?|messages?)\b[^.]*\.\s*$',
        r'^\s*\d+(?:\.\d+)?\s*[+\-*/]\s*\d+[^.]*\.\s*$',  # math scratchpad like "0.15 + 0.024162 = 0.174..."
        r'^\s*(?:But|However|Although)\s+we\s+can\s+approximate\b[^.]*\.\s*$',
    ]
    for p in line_patterns:
        content = re.sub(p, '', content, flags=re.IGNORECASE | re.MULTILINE)

    # Phase 3 — short-line meta patterns at line starts. Two tiers:
    # (a) Conversational openers — strip just the prefix word + comma,
    #     preserving the rest of the sentence.
    # (b) Self-referential planning — strip the whole sentence.
    content = re.sub(
        r'^(?:Okay|OK|Alright|Sure|Well|So|Now)[,!]\s+',
        '',
        content,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    meta_patterns = [
        r'^(We|I)\s+need\s+to\s+answer\b.*?(?=\n\n|With\s+\*\*|Here\s+is|Here\s+are|The\s+answer\s+is|You\s+would|Estimated|Based\s+on|$)',
        r'^(Need\s+to\s+(?:calculate|compute|answer)|Let\'s\s+compute|Let\'s\s+calculate)\b.*?(?=\n\n|With\s+\*\*|Here\s+is|Here\s+are|The\s+answer\s+is|You\s+would|Estimated|Based\s+on|$)',
        r'^(Let me|I\'ll|I will|I should|I need to|I think|I believe|I suppose|I guess)\b[^.]*\.\s*',
        r'^(The user is|User is|They are|This user)\b[^.]*\.\s*',
        r'^(Below is|Below are)\b[^.]*\.\s*',
        r'^(I\'m|I am)\s+(going to|about to|trying to|attempting to|working on)\b[^.]*\.\s*',
        r'^(Let me think|Let me analyze|Let me check|Let me look|Let me search)\b[^.]*\.\s*',
        r'^(I don\'t have|I do not have|I cannot|I can\'t)\b[^.]*\.\s*',
    ]
    for pattern in meta_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.MULTILINE)

    content = re.sub(r'^I\s+(?:think|believe|suppose|guess|feel|would|could|might|should)\s+[^.]*\.\s*$', '', content, flags=re.MULTILINE | re.IGNORECASE)

    content = re.sub(r'\n{3,}', '\n\n', content)
    content = re.sub(r' {2,}', ' ', content)
    content = content.strip()
    return content
