import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from datetime import timezone
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.schemas.request import AgentRequest
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Chat, ChatMessage, User
from app.api.auth import get_optional_user

router = APIRouter()
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _clean_agent_output(text: str) -> str:
    """
    Strip leaked ReAct scaffolding from the agent's final output.

    LangChain's ZERO_SHOT_REACT agent sometimes leaks its internal trace when
    the LLM doesn't follow the exact ReAct format — e.g. it outputs:
        Question: Hello
        Thought: ...
        Action: None
    instead of a clean Final Answer.  We detect this and extract the useful part.
    """
    if not text:
        return text

    # 1. If the text starts with "Question:" or "Thought:", it's leaked ReAct format.
    if re.match(r"^(Question|Thought|Action|Observation):", text.strip()):
        # First priority: extract a proper Final Answer if one is embedded
        final_match = re.search(r"Final Answer:\s*(.+)", text, re.DOTALL)
        if final_match:
            return final_match.group(1).strip()

        # Second priority: a Thought that reads like a real answer (not meta-commentary)
        thought_match = re.search(
            r"Thought:\s*(.+?)(?=\n(?:Action|Observation|Final Answer|Question):|$)",
            text, re.DOTALL
        )
        if thought_match:
            thought = thought_match.group(1).strip()
            skip_phrases = ("i need to", "i should call", "i must use", "i will use", "let me check")
            if len(thought) > 20 and not any(thought.lower().startswith(p) for p in skip_phrases):
                return thought

        # Last resort: strip all ReAct labels AND the Question line entirely
        cleaned = re.sub(r"^Question:.*$", "", text, flags=re.MULTILINE)
        cleaned = re.sub(
            r"(Thought|Action Input|Action|Observation|Final Answer):\s*",
            "", cleaned
        ).strip()
        cleaned = re.sub(r"\bNone\b\s*", "", cleaned).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if cleaned:
            return cleaned

    return text

# ── Simple per-key rate limiter ───────────────────────────────────────────────
# Stores last request timestamp per user_id (or IP for anonymous users).
# Minimum gap between requests: 0.5 seconds.
_last_request: dict[str, float] = {}
_MIN_GAP = 0.5  # seconds


def _check_rate_limit(key: str) -> None:
    now = time.monotonic()
    last = _last_request.get(key, 0.0)
    if now - last < _MIN_GAP:
        wait = round(_MIN_GAP - (now - last), 1)
        raise HTTPException(status_code=429, detail=f"Too many requests. Please wait {wait}s.")
    _last_request[key] = now


def _auto_title(text: str) -> str:
    """Generate a chat title from the first user message (max 40 chars)."""
    clean = text.strip().replace("\n", " ")
    return clean[:40] + ("…" if len(clean) > 40 else "")


def _normalize_short_swap_query(query: str) -> str:
    """Normalize shorthand swap prompts like '🔄 Swap BNB → USDT'."""
    q = (query or "").strip()
    m = re.match(r"^\s*🔄\s*Swap\s+(?:([0-9]*\.?[0-9]+)\s+)?([A-Za-z0-9]+)\s*[→>-]+\s*([A-Za-z0-9]+)\s*$", q, re.IGNORECASE)
    if m:
        amount = m.group(1) or "0.01"
        src = m.group(2).upper()
        dst = m.group(3).upper()
        return f"Swap {amount} {src} to {dst}"
    return q


def _extract_chain_alias(query: str) -> str:
    lowered = (query or "").lower()
    masked = re.sub(r"\b[a-z0-9]{2,12}\s*/\s*[a-z0-9]{2,12}\b", " ", lowered)
    aliases = {
        "ethereum": "ethereum",
        "eth": "ethereum",
        "mainnet": "ethereum",
        "bsc": "bsc",
        "bnb": "bsc",
        "bnb chain": "bsc",
        "polygon": "polygon",
        "matic": "polygon",
        "arbitrum": "arbitrum",
        "arb": "arbitrum",
        "optimism": "optimism",
        "op": "optimism",
        "base": "base",
        "avalanche": "avalanche",
        "avax": "avalanche",
        "solana": "solana",
        "sol": "solana",
    }
    for key, value in aliases.items():
        if re.search(rf"\b{re.escape(key)}\b", masked):
            return value
    return ""


def _split_wallet_context(user_address: str, solana_address: Optional[str]) -> tuple[str, str]:
    evm_wallet = ""
    sol_wallet = ""
    for raw in (user_address or "", solana_address or ""):
        for part in [p.strip() for p in str(raw).split(",") if p.strip()]:
            if part.startswith("0x") and len(part) == 42 and not evm_wallet:
                evm_wallet = part
            elif not part.startswith("0x") and len(part) >= 32 and not sol_wallet:
                sol_wallet = part
    return evm_wallet, sol_wallet


def _infer_runtime_chain_id(chain_id: int, wallet_type: Optional[str], evm_wallet: str, solana_wallet: str) -> int:
    if chain_id in {0, 101, 7565164}:
        return 101
    if wallet_type == "phantom" and not evm_wallet and solana_wallet:
        return 101
    return chain_id


_BRIDGE_CHAIN_ALIASES: list[tuple[str, int]] = [
    ("bnb chain", 56),
    ("binance smart chain", 56),
    ("ethereum mainnet", 1),
    ("eth chain", 1),
    ("solana chain", 101),
    ("sol chain", 101),
    ("ethereum", 1),
    ("mainnet", 1),
    ("arbitrum", 42161),
    ("optimism", 10),
    ("avalanche", 43114),
    ("polygon", 137),
    ("base", 8453),
    ("bsc", 56),
    ("bnb", 56),
    ("eth", 1),
    ("solana", 101),
    ("sol", 101),
    ("matic", 137),
    ("avax", 43114),
    ("arb", 42161),
    ("op", 10),
]

_BRIDGE_NATIVE_TOKEN_TO_CHAIN: dict[str, int] = {
    "SOL": 101,
    "ETH": 1,
    "BNB": 56,
    "MATIC": 137,
    "AVAX": 43114,
}


def _match_bridge_chain_phrase(text: str) -> int:
    lowered = (text or "").lower()
    for phrase, chain_id in _BRIDGE_CHAIN_ALIASES:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return chain_id
    return 0


def _extract_bridge_amount_token(query: str) -> tuple[str, str]:
    m = re.search(r"\bbridge\s+(?:(all|max|[0-9]*\.?[0-9]+)\s+)?([A-Za-z0-9]+)\b", query, re.IGNORECASE)
    if not m:
        return "", ""
    token = m.group(2).upper()
    if token.lower() in {"from", "to", "on", "chain"}:
        return "", ""
    return m.group(1) or "all", token


def _extract_bridge_src_chain(query: str) -> int:
    lowered = (query or "").lower()
    patterns = [
        r"\bfrom\s+([a-z0-9 ]+?)\s+to\b",
        r"\bfrom\s+([a-z0-9 ]+?)\s+chain\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, lowered, re.IGNORECASE)
        if not m:
            continue
        chain_id = _match_bridge_chain_phrase(m.group(1))
        if chain_id:
            return chain_id
    return 0


def _extract_bridge_dst_chain(query: str) -> int:
    lowered = (query or "").lower()
    patterns = [
        r"\bto\s+([a-z0-9 ]+?)\s+chain\b",
        r"\bto\s+([a-z0-9 ]+?)\s*$",
    ]
    for pattern in patterns:
        m = re.search(pattern, lowered, re.IGNORECASE)
        if not m:
            continue
        chain_id = _match_bridge_chain_phrase(m.group(1))
        if chain_id:
            return chain_id
    return 0


def _infer_bridge_src_chain(token_in: str, active_chain_id: int, solana_wallet: str) -> int:
    token_chain = _BRIDGE_NATIVE_TOKEN_TO_CHAIN.get((token_in or "").upper(), 0)
    if token_chain == 101 and solana_wallet:
        return 101
    if token_chain:
        return token_chain
    return active_chain_id


def _try_direct_bridge(query: str, user_address: str, solana_address: str, chain_id: int) -> Optional[str]:
    from app.agents.crypto_agent import _build_bridge_tx

    q = (query or "").strip()
    lowered = q.lower()
    if "bridge" not in lowered:
        return None

    amount, token_in = _extract_bridge_amount_token(q)
    if not amount or not token_in:
        return None

    src_chain = _extract_bridge_src_chain(q)
    dst_chain = _extract_bridge_dst_chain(q)
    if not dst_chain:
        return None
    if not src_chain:
        src_chain = _infer_bridge_src_chain(token_in, chain_id, solana_address)

    payload = json.dumps({
        "token_in": token_in,
        "amount": amount,
        "src_chain_id": src_chain,
        "dst_chain_id": dst_chain,
    })
    return _build_bridge_tx(payload, user_address, chain_id, solana_address)


def _try_direct_yield_search(query: str) -> Optional[str]:
    """Deterministically handle APR/APY pool discovery for common pair queries."""
    from app.agents.crypto_agent import get_defi_analytics

    q = (query or "").strip()
    lowered = q.lower()
    if not any(keyword in lowered for keyword in ("apr", "apy", "yield", "best pool", "highest", "liquidity pool")):
        return None

    token_a = ""
    token_b = ""
    slash_pairs = re.findall(r"\b([A-Za-z0-9]{2,12})\s*/\s*([A-Za-z0-9]{2,12})\b", q, re.IGNORECASE)
    stopwords = {"find", "show", "give", "best", "highest", "pool", "liquidity", "apr", "apy", "yield"}
    for raw_a, raw_b in slash_pairs:
        if raw_a.lower() in stopwords or raw_b.lower() in stopwords:
            continue
        token_a = raw_a.upper()
        token_b = raw_b.upper()
        break

    if not token_a or not token_b:
        pair_match = re.search(
            r"(?:for|of|on)\s+([A-Za-z0-9]{2,12})\s+([A-Za-z0-9]{2,12})\b",
            q,
            re.IGNORECASE,
        )
        if not pair_match:
            return None
        token_a = pair_match.group(1).upper()
        token_b = pair_match.group(2).upper()

    chain_alias = _extract_chain_alias(q)
    search_all_chains = bool(re.search(r"\b(all chains|across all chains|cross-chain|cross chain)\b", lowered))
    metric = "apr" if "apr" in lowered and "apy" not in lowered else "apy"

    analytics_parts = [f"{token_a}/{token_b}"]
    if chain_alias:
        analytics_parts.append(chain_alias)
    analytics_parts.append(f"sort:{metric}")

    return get_defi_analytics(
        " ".join(analytics_parts),
        supported_only=not search_all_chains and not chain_alias,
        verified_only=True,
    )


def _try_direct_staking_info(query: str) -> Optional[str]:
    """Handle informational staking/link queries deterministically."""
    from app.agents.crypto_agent import get_staking_options

    lowered = (query or "").strip().lower()
    if "stake" not in lowered and "staking" not in lowered:
        return None

    patterns = [
        r"\bwhere\b.*\bstake\b",
        r"\blink\b.*\bstake\b",
        r"\bprotocol\b.*\bstake\b",
        r"\bstaking\s+protocol",
        r"\bwhat\s+tokens?.*\bstak",
        r"\bsupported\b.*\bstak",
    ]
    if not any(re.search(pattern, lowered) for pattern in patterns):
        return None

    return get_staking_options(query)


def _try_direct_balance(query: str, user_address: str, solana_address: str) -> Optional[str]:
    """Handle common balance queries deterministically."""
    from app.agents.crypto_agent import get_smart_wallet_balance

    lowered = (query or "").strip().lower()
    normalized = re.sub(r"^[^a-z0-9]+", "", lowered)

    balance_patterns = [
        r"\bmy\s+balance\b",
        r"\bwallet\s+balance\b",
        r"\bcheck\s+balance\b",
        r"\ball\s+chains\b",
        r"\bportfolio\b",
    ]
    if not any(re.search(pattern, normalized) for pattern in balance_patterns):
        return None

    wallet_input = f"{solana_address},{user_address}" if user_address and solana_address else (user_address or solana_address)
    return get_smart_wallet_balance(wallet_input, user_address, solana_address)


def _try_direct_swap(query: str, user_address: str, solana_address: str, chain_id: int) -> Optional[str]:
    """
    Detect 'swap all/my X to Y' patterns and handle directly without the agent.
    Returns JSON string if handled, None if the agent should handle it.
    """
    import json
    from app.agents.crypto_agent import _build_swap_tx, _resolve_token_metadata, build_solana_swap

    q = query.strip()
    # Normalize: insert space before common words glued to token name
    # e.g. "MARCOfrom" → "MARCO from", "BNBto" → "BNB to"
    q = re.sub(r'([A-Za-z0-9])(from|to|for|into|that|on)\b', r'\1 \2', q, flags=re.IGNORECASE)
    # Match: "swap all/my X to/for Y", "swap X that i have to Y", etc.
    patterns = [
        # "swap all BNB to USDT", "swap my BNB to USDT"
        r"swap\s+(?:all|my|entire|full)\s+([A-Za-z0-9]+)\s+(?:to|for|into)\s+([A-Za-z0-9]+)",
        # "swap all BNB that I have to USDT", "swap all BNB from my wallet to USDT"
        r"swap\s+(?:all|my|entire|full)\s+([A-Za-z0-9]+)\s+.*?(?:to|for|into)\s+([A-Za-z0-9]+)",
        # "swap BNB that i have on my wallet for USDT"
        r"swap\s+([A-Za-z0-9]+)\s+that\s+i\s+have\s+.*?(?:to|for|into)\s+([A-Za-z0-9]+)",
    ]
    # Map native token symbols to their chain IDs
    _NATIVE_CHAIN = {
        "BNB": 56, "WBNB": 56, "ETH": 1, "WETH": 1, "MATIC": 137,
        "AVAX": 43114, "FTM": 250, "CRO": 25, "MNT": 5000,
    }
    solana_wallet = (solana_address or "").split(",")[0].strip()
    chain_alias = _extract_chain_alias(q)
    solana_symbols = {"SOL", "BONK", "JUP", "MSOL", "JITOSOL", "PYTH", "RAY", "ORCA"}

    def _should_use_solana(token_in_symbol: str, token_out_symbol: str) -> bool:
        if not solana_wallet:
            return False
        if chain_alias == "solana":
            return True
        if token_in_symbol.upper() in solana_symbols or token_out_symbol.upper() in solana_symbols:
            return True
        return False

    for pat in patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            token_in = m.group(1).upper()
            token_out = m.group(2).upper()
            if _should_use_solana(token_in, token_out):
                swap_input = json.dumps({
                    "sell_token": token_in,
                    "buy_token": token_out,
                    "sell_amount": "all",
                    "user_pubkey": solana_wallet,
                })
                return build_solana_swap(swap_input)
            # Auto-detect chain from token (e.g. BNB → chain 56)
            effective_chain = _NATIVE_CHAIN.get(token_in, chain_id)
            swap_input = json.dumps({
                "chain": "evm",
                "token_in": token_in,
                "token_out": token_out,
                "amount": "all",
                "chain_id": effective_chain,
            })
            return _build_swap_tx(swap_input, user_address, effective_chain)

    amount_patterns = [
        r"swap\s+([0-9]*\.?[0-9]+)\s+([A-Za-z0-9]+)\s+(?:to|for|into)\s+([A-Za-z0-9]+)",
        r"swap\s+([0-9]*\.?[0-9]+)\s+([A-Za-z0-9]+)\s+.*?(?:to|for|into)\s+([A-Za-z0-9]+)",
    ]
    for pat in amount_patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if not m:
            continue
        amount_human = m.group(1)
        token_in = m.group(2).upper()
        token_out = m.group(3).upper()
        if _should_use_solana(token_in, token_out):
            swap_input = json.dumps({
                "sell_token": token_in,
                "buy_token": token_out,
                "sell_amount": amount_human,
                "user_pubkey": solana_wallet,
            })
            return build_solana_swap(swap_input)
        effective_chain = _NATIVE_CHAIN.get(token_in, chain_id)
        _, decimals, resolved_chain = _resolve_token_metadata(token_in, effective_chain, user_address, search_wallet_all_chains=True)
        effective_chain = resolved_chain
        try:
            amount_smallest = str(int(Decimal(amount_human) * (Decimal(10) ** int(decimals or 18))))
        except (InvalidOperation, ValueError):
            return None
        swap_input = json.dumps({
            "chain": "evm",
            "token_in": token_in,
            "token_out": token_out,
            "amount": amount_smallest,
            "chain_id": effective_chain,
        })
        return _build_swap_tx(swap_input, user_address, effective_chain)
    return None


def _try_direct_lp_deposit(query: str, user_address: str, chain_id: int) -> Optional[str]:
    """
    Detect simple LP deposit intents and deterministically resolve the best pool first.
    Returns a JSON string or explanatory text if handled, None if the agent should handle it.
    """
    from app.agents.crypto_agent import (
        _CHAIN_META,
        _build_deposit_lp_tx,
        _resolve_token_metadata,
        find_liquidity_pool,
        get_defi_analytics,
    )

    q = query.strip()
    patterns = [
        r"(?:add|deposit|put)\s+([0-9]*\.?[0-9]+|all)\s+([A-Za-z0-9]+)\s+(?:into|in|to)\s+(?:the\s+)?(?:best|highest\s+apr|highest\s+apy)\s+([A-Za-z0-9/\- ]+?)\s+pool",
        r"(?:add|deposit|put)\s+([0-9]*\.?[0-9]+|all)\s+([A-Za-z0-9]+)\s+(?:into|in|to)\s+(?:the\s+)?best\s+([A-Za-z0-9/\- ]+?)\s+liquidity\s+pool",
    ]

    chain_alias = {
        1: "ethereum",
        10: "optimism",
        56: "bsc",
        137: "polygon",
        8453: "base",
        42161: "arbitrum",
        43114: "avalanche",
        101: "solana",
        7565164: "solana",
    }.get(chain_id, "")

    for pat in patterns:
        m = re.search(pat, q, re.IGNORECASE)
        if not m:
            continue

        amount_raw = m.group(1).strip().lower()
        token_in = m.group(2).upper()
        pair_query = m.group(3).replace("/", " ").strip().upper()

        analytics_query = f"{pair_query} {chain_alias} sort:apy".strip()
        analytics_raw = get_defi_analytics(analytics_query, verified_only=True)
        try:
            analytics = json.loads(analytics_raw)
        except json.JSONDecodeError:
            return None
        cards = analytics.get("cards") or []
        if not cards:
            return None

        top_card = cards[0]
        subtitle = str(top_card.get("subtitle", ""))
        protocol_name = subtitle.split("·")[0].strip() if "·" in subtitle else subtitle.strip() or "Liquidity Pool"

        pool_lookup_raw = find_liquidity_pool(json.dumps({"query": pair_query, "chain_id": chain_alias or chain_id}))
        try:
            pool_lookup = json.loads(pool_lookup_raw)
        except json.JSONDecodeError:
            return None

        pair_address = str(pool_lookup.get("pairAddress", "") or "")
        if not (pair_address.startswith("0x") and len(pair_address) == 42):
            protocol_url = str(pool_lookup.get("protocol_url") or top_card.get("url") or "")
            chain_name = _CHAIN_META.get(chain_id, {}).get("name", f"Chain {chain_id}")
            return (
                f"I found the best {pair_query.replace(' ', '/')} pool on {chain_name}: {protocol_name}. "
                f"I can't build a direct LP deposit transaction for this pool because it does not expose a standard EVM pool address that Enso can route to. "
                f"You can open it directly here: {protocol_url}"
            )

        _, decimals, resolved_chain = _resolve_token_metadata(token_in, chain_id, user_address, search_wallet_all_chains=True)
        if amount_raw == "all":
            amount_smallest = "all"
        else:
            try:
                amount_smallest = str(int(Decimal(amount_raw) * (Decimal(10) ** int(decimals or 18))))
            except (InvalidOperation, ValueError):
                return None

        deposit_input = json.dumps({
            "token_in": token_in,
            "pool_address": pair_address,
            "amount": amount_smallest,
            "protocol": protocol_name,
            "chain_id": resolved_chain,
        })
        deposit_result = _build_deposit_lp_tx(deposit_input, user_address, resolved_chain)
        try:
            parsed = json.loads(deposit_result)
            if parsed.get("status") == "error":
                protocol_url = str(pool_lookup.get("protocol_url") or top_card.get("url") or "")
                return (
                    f"I found the best {pair_query.replace(' ', '/')} pool on {protocol_name}, but I couldn't build a direct LP deposit transaction: {parsed.get('message', 'unknown error')}. "
                    f"You can still open the pool here: {protocol_url}"
                )
        except json.JSONDecodeError:
            pass
        return deposit_result

    return None


def _try_direct_stake(query: str, user_address: str, chain_id: int, solana_address: str = "") -> Optional[str]:
    """
    Detect simple staking intents and build the stake transaction directly.
    Returns JSON on success or a helpful English explanation on failure.
    """
    from app.agents.crypto_agent import _build_stake_tx

    q = query.strip()
    if q.lower().startswith("where to stake"):
        return None

    m = re.search(r"^stake\s+(?:(all|max|[0-9]*\.?[0-9]+)\s+)?(?:my\s+)?([A-Za-z0-9]+)(?:\s+on\s+([A-Za-z0-9]+))?\s*$", q, re.IGNORECASE)
    if not m:
        return None

    _STAKING_NATIVE_CHAIN = {"ETH": 1, "BNB": 56, "MATIC": 137, "SOL": 101}
    amount = m.group(1) or "all"
    token = m.group(2).upper()
    protocol = (m.group(3) or "").lower()
    effective_chain = _STAKING_NATIVE_CHAIN.get(token, chain_id)
    raw = json.dumps({
        "token": token,
        "protocol": protocol,
        "amount": amount,
        "chain_id": effective_chain,
    })
    if solana_address:
        result = _build_stake_tx(raw, user_address, effective_chain, solana_address)
    else:
        result = _build_stake_tx(raw, user_address, effective_chain)
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return result

    if parsed.get("status") == "ok":
        return result

    message = parsed.get("message", "Staking is not available right now.")
    if "No ETH balance" in message:
        return "You do not have any ETH balance on Ethereum available to stake on Lido right now."
    if "No staking protocols available" in message or "not found" in message:
        return message
    return f"I could not build the staking transaction: {message}"


def _try_direct_pool_lookup(query: str, chain_id: int) -> Optional[str]:
    """Detect simple pool lookup requests and route them directly to find_liquidity_pool."""
    from app.agents.crypto_agent import find_liquidity_pool, get_defi_analytics

    q = query.strip()
    m = re.search(r"(?:find|show|give|what\s+is)\s+(?:a\s+)?(?:liquidity\s+)?pool\s+(?:for|of)\s+([A-Za-z0-9]+)\s*[/ ]\s*([A-Za-z0-9]+)", q, re.IGNORECASE)
    if not m:
        return None

    token_a = m.group(1).upper()
    token_b = m.group(2).upper()
    chain_alias = {
        1: "ethereum",
        10: "optimism",
        56: "bsc",
        137: "polygon",
        8453: "base",
        42161: "arbitrum",
        43114: "avalanche",
        101: "solana",
        7565164: "solana",
    }.get(chain_id, chain_id)
    result = find_liquidity_pool(json.dumps({"query": f"{token_a} {token_b}", "chain_id": chain_alias}))
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return result
    if parsed.get("type") == "liquidity_pool_report":
        return result

    analytics_raw = get_defi_analytics(f"{token_a} {token_b} {chain_alias}", verified_only=True)
    try:
        analytics = json.loads(analytics_raw)
    except json.JSONDecodeError:
        return result
    cards = analytics.get("cards") or []
    if not cards:
        return result

    top_card = cards[0]
    subtitle = str(top_card.get("subtitle", ""))
    protocol_name, chain_name = [part.strip() for part in subtitle.split("·", 1)] if "·" in subtitle else (subtitle.strip(), str(chain_alias))
    details = top_card.get("details") or {}
    apy_value = str(details.get("APY", "0")).replace("%", "").replace(",", "")
    tvl_value = str(details.get("TVL", "0")).replace("$", "").replace(",", "")
    try:
        apr = float(apy_value)
    except ValueError:
        apr = 0.0
    try:
        liquidity = float(tvl_value)
    except ValueError:
        liquidity = 0.0
    fallback = {
        "type": "liquidity_pool_report",
        "dexId": protocol_name.lower().replace(" ", "-"),
        "pairAddress": "—",
        "poolSymbol": f"{token_a}-{token_b}",
        "baseToken": token_a,
        "quoteToken": token_b,
        "chainId": str(chain_name).lower(),
        "liquidity_usd": round(liquidity, 2),
        "volume_24h_usd": 0.0,
        "apr": round(apr, 2),
        "url": top_card.get("url", ""),
        "explorer_url": "",
        "protocol_url": top_card.get("url", ""),
        "defillama_url": top_card.get("defillama_url", ""),
    }
    return json.dumps(fallback)


@router.post("/agent")
async def run_agent(
    request: Request,
    body: AgentRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    # Rate limit: 1 request per 0.5 seconds per user (or per IP for anonymous)
    rate_key = str(current_user.id) if current_user else (request.client.host if request.client else "anon")
    _check_rate_limit(rate_key)

    from app.agents.crypto_agent import build_agent  # imported lazily to avoid import-time errors

    direct_query = _normalize_short_swap_query(body.query)
    evm_wallet, solana_wallet = _split_wallet_context(body.user_address, body.solana_address)
    effective_chain_id = _infer_runtime_chain_id(body.chain_id, getattr(body, "wallet_type", None), evm_wallet, solana_wallet)

    # ── Try direct balance handling for common wallet balance prompts ────────
    direct_balance_result = _try_direct_balance(direct_query, evm_wallet, solana_wallet)
    if direct_balance_result:
        provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
        if current_user:
            if provided_chat_id_early:
                chat = db.query(Chat).filter(
                    Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                ).first()
            else:
                chat = None
            if not chat:
                chat_id = str(uuid.uuid4())
                chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                db.add(chat)
                db.flush()
            db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
            db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_balance_result))
            chat.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"session_id": chat.id, "chat_id": chat.id, "response": direct_balance_result}
        return {"session_id": body.session_id, "chat_id": None, "response": direct_balance_result}

    # ── Try direct swap-all handling (bypasses agent for "swap all X to Y") ──
    # Only use the direct result if the swap SUCCEEDED — errors fall through to the agent
    # so the AI can reason about the failure and suggest alternatives.
    direct_swap_result = _try_direct_swap(
        direct_query, evm_wallet, solana_wallet, effective_chain_id
    )
    if direct_swap_result:
        try:
            _parsed_direct = json.loads(direct_swap_result)
            _direct_ok = _parsed_direct.get("status") == "ok"
        except (json.JSONDecodeError, AttributeError):
            _direct_ok = False

        if _direct_ok:
            # Success — save to chat history and return directly (fast path)
            provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
            if current_user:
                if provided_chat_id_early:
                    chat = db.query(Chat).filter(
                        Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                    ).first()
                else:
                    chat = None
                if not chat:
                    chat_id = str(uuid.uuid4())
                    chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                    db.add(chat)
                    db.flush()
                db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
                db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_swap_result))
                chat.updated_at = datetime.now(timezone.utc)
                db.commit()
                return {"session_id": chat.id, "chat_id": chat.id, "response": direct_swap_result}
            return {"session_id": body.session_id, "chat_id": None, "response": direct_swap_result}
        # Error from direct swap — fall through to let the agent handle it with reasoning

    # ── Try direct bridge flow for common bridge requests ────────────────────
    direct_bridge_result = _try_direct_bridge(
        direct_query, evm_wallet, solana_wallet, effective_chain_id
    )
    if direct_bridge_result:
        provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
        if current_user:
            if provided_chat_id_early:
                chat = db.query(Chat).filter(
                    Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                ).first()
            else:
                chat = None
            if not chat:
                chat_id = str(uuid.uuid4())
                chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                db.add(chat)
                db.flush()
            db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
            db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_bridge_result))
            chat.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"session_id": chat.id, "chat_id": chat.id, "response": direct_bridge_result}
        return {"session_id": body.session_id, "chat_id": None, "response": direct_bridge_result}

    # ── Try direct yield search for common APR/APY questions ─────────────────
    direct_staking_info_result = _try_direct_staking_info(direct_query)
    if direct_staking_info_result:
        provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
        if current_user:
            if provided_chat_id_early:
                chat = db.query(Chat).filter(
                    Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                ).first()
            else:
                chat = None
            if not chat:
                chat_id = str(uuid.uuid4())
                chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                db.add(chat)
                db.flush()
            db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
            db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_staking_info_result))
            chat.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"session_id": chat.id, "chat_id": chat.id, "response": direct_staking_info_result}
        return {"session_id": body.session_id, "chat_id": None, "response": direct_staking_info_result}

    # ── Try direct yield search for common APR/APY questions ─────────────────
    direct_yield_result = _try_direct_yield_search(direct_query)
    if direct_yield_result:
        provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
        if current_user:
            if provided_chat_id_early:
                chat = db.query(Chat).filter(
                    Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                ).first()
            else:
                chat = None
            if not chat:
                chat_id = str(uuid.uuid4())
                chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                db.add(chat)
                db.flush()
            db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
            db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_yield_result))
            chat.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"session_id": chat.id, "chat_id": chat.id, "response": direct_yield_result}
        return {"session_id": body.session_id, "chat_id": None, "response": direct_yield_result}

    # ── Try direct LP deposit flow for simple "add/deposit to best pool" requests ──
    direct_lp_result = _try_direct_lp_deposit(
        direct_query, evm_wallet, effective_chain_id
    )
    if direct_lp_result:
        provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
        if current_user:
            if provided_chat_id_early:
                chat = db.query(Chat).filter(
                    Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                ).first()
            else:
                chat = None
            if not chat:
                chat_id = str(uuid.uuid4())
                chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                db.add(chat)
                db.flush()
            db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
            db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_lp_result))
            chat.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"session_id": chat.id, "chat_id": chat.id, "response": direct_lp_result}
        return {"session_id": body.session_id, "chat_id": None, "response": direct_lp_result}

    # ── Try direct staking flow for simple staking requests ──────────────────
    direct_stake_result = _try_direct_stake(
        direct_query, evm_wallet, effective_chain_id, solana_wallet
    )
    if direct_stake_result:
        provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
        if current_user:
            if provided_chat_id_early:
                chat = db.query(Chat).filter(
                    Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                ).first()
            else:
                chat = None
            if not chat:
                chat_id = str(uuid.uuid4())
                chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                db.add(chat)
                db.flush()
            db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
            db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_stake_result))
            chat.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"session_id": chat.id, "chat_id": chat.id, "response": direct_stake_result}
        return {"session_id": body.session_id, "chat_id": None, "response": direct_stake_result}

    # ── Try direct pool lookup flow for simple pair-address requests ─────────
    direct_pool_result = _try_direct_pool_lookup(direct_query, effective_chain_id)
    if direct_pool_result:
        provided_chat_id_early: Optional[str] = getattr(body, "chat_id", None)
        if current_user:
            if provided_chat_id_early:
                chat = db.query(Chat).filter(
                    Chat.id == provided_chat_id_early, Chat.user_id == current_user.id
                ).first()
            else:
                chat = None
            if not chat:
                chat_id = str(uuid.uuid4())
                chat = Chat(id=chat_id, user_id=current_user.id, title=_auto_title(body.query))
                db.add(chat)
                db.flush()
            db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
            db.add(ChatMessage(chat_id=chat.id, role="assistant", content=direct_pool_result))
            chat.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"session_id": chat.id, "chat_id": chat.id, "response": direct_pool_result}
        return {"session_id": body.session_id, "chat_id": None, "response": direct_pool_result}

    # ── Determine session identity (no DB write yet — avoids orphan chats on error) ──
    provided_chat_id: Optional[str] = getattr(body, "chat_id", None)

    if current_user and provided_chat_id:
        existing = db.query(Chat).filter(Chat.id == provided_chat_id, Chat.user_id == current_user.id).first()
        effective_session_id = provided_chat_id if existing else str(uuid.uuid4())
    elif current_user:
        effective_session_id = str(uuid.uuid4())
    else:
        effective_session_id = body.session_id

    effective_query = direct_query

    # ── Build ordered list of models/providers to try ────────────────────────
    from app.agents.crypto_agent import _OPENROUTER_MODELS

    models_to_try: list[Optional[str]] = []
    if settings.api_keys.get("openai"):
        models_to_try.append("__openai__")
    if settings.api_keys.get("openrouter"):
        models_to_try.extend(_OPENROUTER_MODELS)
    if settings.api_keys.get("groq"):
        models_to_try.append("__groq__")
    if not models_to_try:
        raise HTTPException(status_code=503, detail="No LLM API key configured. Add openrouter, groq, or openai to API_KEYS in server/.env.")

    # ── Run the agent with provider fallback ─────────────────────────────────
    last_exc: Optional[Exception] = None

    for model in models_to_try:
        try:
            agent = build_agent(
                session_id=effective_session_id,
                user_address=evm_wallet,
                solana_address=solana_wallet,
                chain_id=effective_chain_id,
                openrouter_model=model,
            )
            result = await asyncio.wait_for(
                agent.ainvoke({"input": effective_query}),
                timeout=90.0,
            )
            response_text = _clean_agent_output(result.get("output", ""))

            # Safety net: if agent hit iteration limit, replace with user-friendly message
            if "agent stopped" in response_text.lower() and "iteration limit" in response_text.lower():
                response_text = (
                    "I wasn't able to fully process your request. "
                    "This can happen with complex multi-step operations. "
                    "Could you try rephrasing or breaking it into smaller steps? "
                    "For example, I can find the best pool for you, or help with a swap."
                )

            chat: Optional[Chat] = None
            if current_user:
                if provided_chat_id:
                    chat = db.query(Chat).filter(Chat.id == provided_chat_id, Chat.user_id == current_user.id).first()
                if not chat:
                    chat = Chat(
                        id=effective_session_id,
                        user_id=current_user.id,
                        title=_auto_title(body.query),
                    )
                    db.add(chat)
                    db.flush()
                db.add(ChatMessage(chat_id=chat.id, role="user", content=body.query))
                db.add(ChatMessage(chat_id=chat.id, role="assistant", content=response_text))
                chat.updated_at = datetime.now(timezone.utc)
                if chat.title == "New Chat":
                    chat.title = _auto_title(body.query)
                db.commit()

            return {
                "session_id": effective_session_id,
                "chat_id": chat.id if chat else None,
                "response": response_text,
            }
        except (asyncio.TimeoutError, TimeoutError) as exc:
            last_exc = exc
            continue
        except Exception as exc:
            err_str = str(exc)

            # Retry on transient provider failures and quota/rate failures
            if (
                "429" in err_str
                or "rate" in err_str.lower()
                or "timed out" in err_str.lower()
                or "402" in err_str
                or "insufficient_quota" in err_str.lower()
                or "billing" in err_str.lower()
                or "credit" in err_str.lower()
                or "service unavailable" in err_str.lower()
                or "temporarily unavailable" in err_str.lower()
            ):
                last_exc = exc
                continue

            # Retry on auth errors too (next provider may work)
            if "401" in err_str or "user not found" in err_str.lower() or "unauthorized" in err_str.lower():
                last_exc = exc
                continue

            # Retry on provider package/config issues (e.g. optional provider not installed)
            if (
                isinstance(exc, ImportError)
                or "module not found" in err_str.lower()
                or "no module named" in err_str.lower()
                or "api key" in err_str.lower()
                or "configuration" in err_str.lower()
            ):
                last_exc = exc
                continue

            # Retry with next provider when a tool receives structured args unexpectedly
            if (
                "too many arguments to single-input tool" in err_str.lower()
                or "consider using structuredtool" in err_str.lower()
            ):
                last_exc = exc
                continue

            # LLM responded in plain text instead of ReAct format — extract and return
            if (
                "could not parse llm output" in err_str.lower()
                or "invalid format" in err_str.lower()
                or "output parsing" in err_str.lower()
                or "missing 'action'" in err_str.lower()
            ):
                import re as _re
                match = _re.search(r"Could not parse LLM output:\s*`(.*)`", err_str, _re.S)
                llm_text = _clean_agent_output(match.group(1).strip() if match else err_str)
                recovered_chat: Optional[Chat] = None
                if current_user:
                    try:
                        if provided_chat_id:
                            recovered_chat = db.query(Chat).filter(Chat.id == provided_chat_id, Chat.user_id == current_user.id).first()
                        if not recovered_chat:
                            recovered_chat = Chat(
                                id=effective_session_id,
                                user_id=current_user.id,
                                title=_auto_title(body.query),
                            )
                            db.add(recovered_chat)
                            db.flush()
                        db.add(ChatMessage(chat_id=recovered_chat.id, role="user", content=body.query))
                        db.add(ChatMessage(chat_id=recovered_chat.id, role="assistant", content=llm_text))
                        recovered_chat.updated_at = datetime.now(timezone.utc)
                        db.commit()
                    except Exception:
                        db.rollback()
                return {
                    "session_id": effective_session_id,
                    "chat_id": recovered_chat.id if recovered_chat else None,
                    "response": llm_text,
                }

            last_exc = exc

    if last_exc is not None:
        err_str = str(last_exc)
        if isinstance(last_exc, (asyncio.TimeoutError, TimeoutError)):
            raise HTTPException(status_code=504, detail="The AI agent took too long to respond. Please try again in a moment.")
        if (
            "context length" in err_str.lower()
            or "too many tokens" in err_str.lower()
            or "maximum context" in err_str.lower()
            or "max_tokens" in err_str.lower()
        ):
            raise HTTPException(status_code=400, detail="The current chat context is too large. Start a new chat and retry the request.")
        if "402" in err_str or "insufficient_quota" in err_str.lower() or "billing" in err_str.lower() or "credit" in err_str.lower():
            raise HTTPException(status_code=402, detail="AI provider credits are insufficient right now. Please top up credits or use another provider key.")
        if "429" in err_str or "rate" in err_str.lower():
            raise HTTPException(status_code=429, detail="All AI providers are currently rate-limited. Please wait a moment and try again.")
        if "401" in err_str or "user not found" in err_str.lower() or "unauthorized" in err_str.lower():
            raise HTTPException(status_code=401, detail="All configured AI provider keys failed authentication. Please update API_KEYS in server/.env and restart.")
        if isinstance(last_exc, ImportError) or "no module named" in err_str.lower():
            raise HTTPException(status_code=503, detail="An optional AI provider dependency is missing on the server. Please install required provider packages.")

    raise HTTPException(status_code=500, detail="The AI backend failed unexpectedly. Please try again.")


class RpcRequest(BaseModel):
    rpc_url: str
    method: str
    params: List[Any]


class BridgeStatusResponse(BaseModel):
    order_id: str
    status: str


@router.post("/rpc-proxy")
async def rpc_proxy(req: RpcRequest):
    """Proxy for cross-chain RPC calls to bypass browser CORS."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                req.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": req.method, "params": req.params},
                timeout=10.0,
            )
            return {"result": resp.json().get("result", "0x0")}
    except Exception as e:
        return {"result": "0x0", "error": str(e)}


@router.get("/bridge-status/{order_id}", response_model=BridgeStatusResponse)
async def bridge_status(order_id: str):
    from app.agents.crypto_agent import _requests

    try:
        resp = _requests.get(f"https://api.dln.trade/v1.0/dln/order/{order_id}/status", timeout=15)
        data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"deBridge status request failed: {exc}") from exc

    if resp.status_code != 200:
        detail = data.get("errorMessage") if isinstance(data, dict) else None
        raise HTTPException(status_code=resp.status_code, detail=detail or "Failed to fetch bridge status")

    status = str((data or {}).get("status") or "Unknown")
    return {"order_id": order_id, "status": status}
