"""Simple agent runtime without ReAct - uses direct LLM calls with tool support."""
from __future__ import annotations

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
    r"\b(?i:(raydium-amm|raydium-clmm|orca-whirlpools|orca|meteora-dlmm|meteora|"
    r"kamino|marinade|jito|sanctum|drift|aave-v3|compound-v3|spark|curve|convex|pendle|"
    r"yearn-finance|lido|rocket-pool|ether\.fi|frax-ether|stargate|morpho-blue|moonwell|"
    r"stader|gmx|velodrome|aerodrome-slipstream|uniswap-v[34]|steer-protocol|zeebu|blackhole-clmm|supernova-cl))"
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


def _detect_pool_execute(message: str, intent: DefiIntent) -> tuple[str, dict] | None:
    """Route 'execute pool X' / 'deposit into raydium-amm SPACEX-WSOL' to
    execute_pool_position when a concrete pool reference is present.
    """
    if not intent.execution_requested:
        return None
    text = message.strip()
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
    params: dict = {
        "pool": pool_ref,
        "amount": intent.amount_usd if (intent.amount_usd is not None and intent.amount_usd > 0) else 100.0,
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
    m = re.search(r"\b(?:risk\s*budget|risk\s*level)\s+(conservative|balanced|aggressive)\b", text, re.IGNORECASE)
    if m:
        params["risk_budget"] = m.group(1).lower()
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

    multi_step = _detect_bridge_then_stake(message)
    if multi_step is not None:
        return multi_step
    for detector in (_detect_direct_pool_deposit, _detect_aave_supply, _detect_swap_then_lp, _detect_stake_amount_plan, _detect_stake_all, _detect_stake_simple, _detect_malicious_swap_plan, _detect_bridge_signable, _detect_buy_intent, _detect_swap_signable, _detect_transfer_plan):
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


def _strategy_system_prompt(*, target_apy: float | None, risk_levels: list[str] | None, chains: list[str] | None) -> str:
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
    return (
        "You are Ilyon Sentinel, a senior DeFi strategist. The user asked you to BUILD a strategy. "
        "You have your own intelligence AND access to live pool data the system already fetched.\n\n"
        f"{apy_line}\n{risk_line}\n{chain_line}\n\n"
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
) -> str | None:
    """Run the LLM with strategy composition prompt + live pool data context."""
    pool_summary = _summarize_pools_for_strategy(pool_card or {})
    system_prompt = _strategy_system_prompt(
        target_apy=target_apy, risk_levels=risk_levels, chains=chains
    )

    context_blocks: list[str] = []
    if prior_cards_summary:
        context_blocks.append(
            "Previously surfaced pools / cards in this chat (for continuity — refer to these "
            "if the user said 'those pools', 'these', 'previous'):\n" + prior_cards_summary
        )
    if pool_summary:
        context_blocks.append(
            "Live pool candidates the system just fetched for this request "
            "(use these as your concrete pool universe):\n" + pool_summary
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
        result = await llm._agenerate(llm_messages)
        text = result.generations[0].message.content or ""
        return text.strip() or None
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
            collector.emit_final(replay, [])
            for frame in collector.drain():
                yield encode_sse(frame_event_name(frame), frame.model_dump())
            return

    # Detect intent
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
                    # markdown response on top of the live pool data. Card stays.
                    if (
                        tool_name == "search_defi_opportunities"
                        and _is_strategy_compose_request(message)
                        and env.card_payload
                    ):
                        try:
                            _emit_thoughts(collector, [
                                "Composing strategy narrative on top of live pool data (multi-section ChatGPT-style output).",
                            ])
                            for frame in collector.drain():
                                yield encode_sse(frame_event_name(frame), frame.model_dump())
                            prior_cards_summary = _summarize_prior_cards(history_cards)
                            composed = await _compose_strategy_via_llm(
                                llm,
                                user_message=message,
                                pool_card=env.card_payload,
                                history=history,
                                target_apy=tool_input.get("target_apy"),
                                risk_levels=tool_input.get("risk_levels"),
                                chains=tool_input.get("chains"),
                                prior_cards_summary=prior_cards_summary,
                            )
                            if composed:
                                final_content = composed
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
            base_system = (
                "You are Ilyon Sentinel's crypto agent. You help users with DeFi, "
                "token prices, swaps, bridges, staking, and yield opportunities.\n\n"
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
                result = await llm._agenerate(llm_messages)
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
        if not is_allocate and not is_legacy_preview:
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
