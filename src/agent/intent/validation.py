"""Semantic validation gate for swap/bridge/buy intents.

Centralizes:
- English stop-words and prepositional noise that must not be parsed as token symbols.
- Token → chain registry (which chain a token natively lives on).
- Cross-chain detection (when a single-chain swap should route to a bridge instead).
- Amount sanity (zero / negative / overflow).
- Aggregator error translation (Jupiter / Enso raw errors → user-actionable messages).

Used by intent detectors (regex shortcuts) and by tool wrappers (LLM tool-call path)
so a malformed intent cannot reach Jupiter/Enso regardless of which path produced it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable


# Words that appear in user phrasings ("from my wallet on solana chain") and must
# never be captured as a token symbol. Superset of the legacy _NOT_A_SYMBOL list.
STOP_WORDS: frozenset[str] = frozenset({
    # English prepositions / determiners
    "A", "AN", "THE", "THIS", "THAT", "IT", "OF", "ON", "IN", "FOR", "TO",
    "FROM", "INTO", "WITH", "USING", "VIA", "AT", "BY", "AS", "AND", "OR",
    "BUT", "MY", "YOUR", "OUR", "HIS", "HER", "ITS", "THEIR",
    # Action verbs
    "SWAP", "EXCHANGE", "CONVERT", "TRADE", "SELL", "DUMP", "BUY",
    "BRIDGE", "TRANSFER", "STAKE", "UNSTAKE", "SEND", "MOVE", "DEPOSIT",
    "WITHDRAW", "SUPPLY", "LEND", "BORROW", "APPROVE",
    # Quantity sentinels
    "ALL", "MAX", "MAXIMUM", "ENTIRE", "EVERYTHING", "WHOLE", "HALF",
    "QUARTER", "PERCENT", "PCT",
    # Wallet / chain noise
    "WALLET", "CHAIN", "ADDRESS", "ACCOUNT", "BALANCE", "FUND", "FUNDS",
    "PORTFOLIO", "HOLDINGS", "POSITION", "POSITIONS", "ASSETS", "TOKENS",
    "BAGS", "STASH",
    # Chain names — never a token symbol
    "ETHEREUM", "MAINNET", "SOLANA", "ARBITRUM", "OPTIMISM", "POLYGON",
    "AVALANCHE", "BASE", "ZKSYNC", "LINEA", "SCROLL",
    # Common bsc aliases — BNB / BSC ARE valid token tickers, so those stay out
    # Misc filler
    "PLEASE", "NOW", "TODAY", "ASAP", "PLS",
})


# Canonical token registry. Maps SYMBOL → set of chain_ids on which the token
# natively exists with the agent-supported aggregator (Enso for EVM, Jupiter
# for Solana). Used to reject swap intents where token_in/token_out is not on
# the resolved chain.
#
# chain_id legend (matches simple_runtime CHAIN_IDS / wallet_swap):
#   1      Ethereum mainnet
#   10     Optimism
#   56     BSC
#   101    Solana (Jupiter)
#   137    Polygon
#   8453   Base
#   42161  Arbitrum
#   43114  Avalanche
TOKEN_CHAINS: dict[str, frozenset[int]] = {
    # Stables — multi-chain
    "USDC":    frozenset({1, 10, 56, 101, 137, 8453, 42161, 43114}),
    "USDT":    frozenset({1, 10, 56, 101, 137, 8453, 42161, 43114}),
    "DAI":     frozenset({1, 10, 137, 8453, 42161}),
    "BUSD":    frozenset({56}),
    "TUSD":    frozenset({1, 56}),
    "FDUSD":   frozenset({1, 56}),
    "FRAX":    frozenset({1, 10, 137, 42161}),
    "LUSD":    frozenset({1, 10, 42161}),
    "USDE":    frozenset({1}),
    # Native + wrapped natives (chain-locked)
    "ETH":     frozenset({1, 10, 8453, 42161}),
    "WETH":    frozenset({1, 10, 8453, 42161}),  # NOT Solana; Wormhole wETH
                                                 # exists but agent doesn't route it
    "BNB":     frozenset({56}),
    "WBNB":    frozenset({56}),
    "SOL":     frozenset({101}),
    "WSOL":    frozenset({101}),
    "MATIC":   frozenset({1, 137}),
    "POL":     frozenset({1, 137}),
    "AVAX":    frozenset({43114}),
    "WAVAX":   frozenset({43114}),
    "ARB":     frozenset({42161}),
    "OP":      frozenset({10}),
    "WBTC":    frozenset({1, 10, 137, 8453, 42161, 43114}),
    "BTC":     frozenset({1, 10, 137, 8453, 42161, 43114}),  # quoted as WBTC
    # Solana-native ecosystem
    "BONK":    frozenset({101}),
    "JUP":     frozenset({101}),
    "PYTH":    frozenset({101}),
    "RAY":     frozenset({101}),
    "ORCA":    frozenset({101}),
    "JITO":    frozenset({101}),
    "JITOSOL": frozenset({101}),
    "MSOL":    frozenset({101}),
    "STSOL":   frozenset({101}),
    "WIF":     frozenset({101}),
    "POPCAT":  frozenset({101}),
    "FATPENGU": frozenset({101}),
    "PENGU":   frozenset({101}),
    # EVM-only top-cap
    "LINK":    frozenset({1, 10, 56, 137, 8453, 42161, 43114}),
    "UNI":     frozenset({1, 10, 137, 8453, 42161}),
    "AAVE":    frozenset({1, 10, 137, 8453, 42161, 43114}),
    "PEPE":    frozenset({1}),
    "SHIB":    frozenset({1}),
    "DOGE":    frozenset({56}),
    "CAKE":    frozenset({56}),
    "STETH":   frozenset({1}),
    "WSTETH":  frozenset({1, 10, 8453, 42161}),
    "RETH":    frozenset({1, 10, 42161}),
    "LDO":     frozenset({1}),
    "MKR":     frozenset({1}),
    "CRV":     frozenset({1, 10, 137, 42161}),
}


# Tokens whose USD price is meaningless or that should never appear as either
# leg of a swap — synonyms of stop-words that the simulate_swap fallback was
# previously misclassifying.
_NEVER_TOKENS: frozenset[str] = STOP_WORDS


# Public chain alias → numeric id table for callers that don't import
# simple_runtime.CHAIN_IDS directly. Mirrors the runtime values; Solana = 101
# here (Jupiter convention) rather than the deBridge id.
_CHAIN_ID_BY_NAME_FALLBACK: dict[str, int] = {
    "ethereum": 1, "eth": 1, "mainnet": 1,
    "arbitrum": 42161, "arb": 42161,
    "base": 8453,
    "optimism": 10, "op": 10,
    "polygon": 137, "matic": 137,
    "bsc": 56, "bnb": 56,
    "avalanche": 43114, "avax": 43114,
    "solana": 101, "sol": 101,
}


# Rough max-amount sanity per supported chain (in human units, decimals applied
# downstream). Anything above is almost certainly a parser error rather than a
# real intent. Set generously so legitimate whales aren't blocked.
_AMOUNT_CEILING_HUMAN = Decimal("1_000_000_000")


@dataclass(frozen=True)
class SwapValidation:
    """Result of validating a swap-shaped intent."""
    ok: bool
    error_code: str | None = None
    user_message: str | None = None
    suggested_action: str | None = None  # "bridge" | "reject" | None


def is_stop_word(token: str | None) -> bool:
    """True if `token` is English / phrasing noise, not a real symbol."""
    if not token:
        return True
    return token.strip().upper() in STOP_WORDS


def is_valid_symbol_shape(token: str | None) -> bool:
    """True if `token` looks like a ticker (2–10 alnum/$./_-, not stop-word)."""
    if not token:
        return False
    t = token.strip()
    if not 2 <= len(t) <= 12:
        return False
    if not re.match(r"^[A-Za-z][A-Za-z0-9$._-]{1,11}$", t):
        return False
    return not is_stop_word(t)


def filter_symbol_candidates(candidates: Iterable[str]) -> list[str]:
    """Drop stop-words and bad-shape entries from a list of candidate tickers."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in candidates:
        if not raw:
            continue
        sym = raw.strip().upper()
        if sym in seen:
            continue
        if not is_valid_symbol_shape(sym):
            continue
        seen.add(sym)
        out.append(sym)
    return out


def token_supported_on_chain(token: str | None, chain_id: int | None) -> bool | None:
    """Return True/False if known, None when token isn't in registry.

    Unknown tokens (long-tail memes) are NOT auto-rejected; they fall through
    to aggregator resolution. Only registered tokens carry chain constraints.
    """
    if not token or chain_id is None:
        return None
    sym = token.strip().upper()
    chains = TOKEN_CHAINS.get(sym)
    if chains is None:
        return None
    return int(chain_id) in chains


def is_cross_chain(token_in: str | None, token_out: str | None,
                   chain_id: int | None) -> bool:
    """True if the (token_in, token_out, chain_id) trio implies a bridge.

    A swap is single-chain when both tokens exist on `chain_id`. If either
    token is registered ONLY on a different chain, treat as cross-chain.
    """
    if chain_id is None:
        return False
    in_ok = token_supported_on_chain(token_in, chain_id)
    out_ok = token_supported_on_chain(token_out, chain_id)
    # Both unknown → defer to aggregator.
    if in_ok is None and out_ok is None:
        return False
    # Either known and NOT on this chain → cross-chain mismatch.
    return (in_ok is False) or (out_ok is False)


def _native_chain_for_token(token: str) -> int | None:
    """If a registered token has exactly one home chain, return it; else None."""
    sym = token.strip().upper()
    chains = TOKEN_CHAINS.get(sym)
    if chains is None or len(chains) != 1:
        return None
    return next(iter(chains))


# Preferred bridge-destination chain when a token is multi-home. Lowest chain_id
# wins (Ethereum mainnet=1 for ETH/WETH/etc.) — biases bridges to canonical home.
_BRIDGE_DEST_PREFERENCE = (1, 8453, 10, 42161, 137, 56, 43114, 101)


def primary_home_chain(token: str) -> int | None:
    """Pick the canonical home chain for a token.

    For single-home tokens (SOL, BNB, MATIC) returns that chain. For multi-home
    (ETH, WETH, USDC) returns the most-canonical chain in `_BRIDGE_DEST_PREFERENCE`
    that the token actually lives on. Returns None for unknown tokens.
    """
    sym = (token or "").strip().upper()
    chains = TOKEN_CHAINS.get(sym)
    if not chains:
        return None
    if len(chains) == 1:
        return next(iter(chains))
    for cid in _BRIDGE_DEST_PREFERENCE:
        if cid in chains:
            return cid
    return next(iter(chains))


def parse_amount_human(raw: str | None) -> Decimal | None:
    """Parse a human numeric amount string. Returns None on garbage / ≤ 0."""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if not s:
        return None
    try:
        n = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if n <= 0 or n > _AMOUNT_CEILING_HUMAN:
        return None
    return n


def parse_amount_base_units(raw: str | None) -> int | None:
    """Parse a base-units integer string (wei / lamports). Returns None on bad."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Sentinels handled by callers; only positive integer here.
    if not s.isdigit():
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    if n <= 0:
        return None
    return n


def validate_swap_params(
    *,
    token_in: str | None,
    token_out: str | None,
    chain_id: int | None,
    amount_in: str | None,
    amount_is_sentinel: bool = False,
) -> SwapValidation:
    """Validate a swap before dispatching to Jupiter/Enso.

    `amount_is_sentinel=True` means amount_in is "ALL" / "PCT:NN" — skip the
    base-units numeric check (resolved later via balance lookup).
    """
    # Token shape
    if not is_valid_symbol_shape(token_in):
        return SwapValidation(
            ok=False,
            error_code="invalid_token_in",
            user_message=(
                f"I couldn't read the source token from your message. "
                f"Try the canonical symbol — for example: SOL, USDC, ETH."
            ),
            suggested_action="reject",
        )
    if not is_valid_symbol_shape(token_out):
        return SwapValidation(
            ok=False,
            error_code="invalid_token_out",
            user_message=(
                f"I couldn't read the destination token from your message. "
                f"Try the canonical symbol — for example: WBNB, USDC, ETH."
            ),
            suggested_action="reject",
        )
    sym_in = token_in.strip().upper()
    sym_out = token_out.strip().upper()
    if sym_in == sym_out:
        return SwapValidation(
            ok=False,
            error_code="same_token",
            user_message=f"Source and destination are both {sym_in} — nothing to swap.",
            suggested_action="reject",
        )

    # Amount
    if not amount_is_sentinel:
        if parse_amount_base_units(amount_in) is None:
            return SwapValidation(
                ok=False,
                error_code="invalid_amount",
                user_message=(
                    "Amount must be a positive number. "
                    "Try: 'swap 0.1 SOL to USDC'."
                ),
                suggested_action="reject",
            )

    # Chain consistency — if we know the chain a registered token lives on
    # and that doesn't match, route to bridge instead of running a swap.
    if chain_id is not None:
        if is_cross_chain(sym_in, sym_out, int(chain_id)):
            in_native = _native_chain_for_token(sym_in)
            out_native = _native_chain_for_token(sym_out)
            details = []
            if in_native and in_native != int(chain_id):
                details.append(f"{sym_in} lives on chain {in_native}")
            if out_native and out_native != int(chain_id):
                details.append(f"{sym_out} lives on chain {out_native}")
            detail = " — ".join(details) if details else "tokens are on different chains"
            return SwapValidation(
                ok=False,
                error_code="cross_chain",
                user_message=(
                    f"{sym_in} → {sym_out} crosses chains ({detail}). "
                    f"Use 'bridge {sym_in} from <src> to <dst>' to move "
                    f"between chains, then swap on the destination."
                ),
                suggested_action="bridge",
            )
        # Token on chain check (only when both registered)
        in_supported = token_supported_on_chain(sym_in, int(chain_id))
        out_supported = token_supported_on_chain(sym_out, int(chain_id))
        if in_supported is False:
            return SwapValidation(
                ok=False,
                error_code="token_not_on_chain",
                user_message=(
                    f"{sym_in} isn't supported on chain {chain_id}. "
                    f"Pick a chain where {sym_in} exists, or bridge first."
                ),
                suggested_action="reject",
            )
        if out_supported is False:
            return SwapValidation(
                ok=False,
                error_code="token_not_on_chain",
                user_message=(
                    f"{sym_out} isn't supported on chain {chain_id}. "
                    f"Try a chain where {sym_out} exists, or bridge first."
                ),
                suggested_action="reject",
            )

    return SwapValidation(ok=True)


def translate_aggregator_error(raw: str | None) -> str:
    """Map raw aggregator errors to user-actionable messages.

    Falls back to the raw message when no rule matches, so we never swallow
    information silently.
    """
    if not raw:
        return "Swap failed for an unknown reason. Try again in a moment."
    text = str(raw)
    low = text.lower()

    # Jupiter quote: outputMint shape error → cross-chain mismatch slipped through
    if "outputmint" in low and ("wrongsize" in low or "cannot be parsed" in low):
        return (
            "I can't quote that route — the destination token isn't a valid Solana "
            "mint. If you're trying to move between chains, use 'bridge' instead "
            "of 'swap'."
        )
    if "inputmint" in low and ("wrongsize" in low or "cannot be parsed" in low):
        return (
            "I can't quote that route — the source token isn't a valid Solana "
            "mint. Use the canonical symbol (e.g. SOL, USDC) or bridge first."
        )

    # Jupiter quote: no route
    if "could not find any route" in low or "no routes" in low or "routenot" in low:
        return (
            "No swap route exists for that pair right now. Try a more liquid "
            "pair (e.g. against USDC) or check the destination token symbol."
        )

    # Enso rate limit
    if "enso" in low and "429" in low:
        return (
            "Aggregator is briefly rate-limited (1 req/s on this key). "
            "Retry in a few seconds — the request didn't reach the chain."
        )
    if "exceeded the request limit" in low or "rate limit" in low:
        return (
            "Aggregator is rate-limited. Retry in a few seconds — your wallet "
            "wasn't charged."
        )

    # Wallet identity errors (Enso "fromAddress is not a valid address" /
    # Jupiter userPublicKey errors) — almost always a guest with no wallet.
    if ("fromaddress is not a valid address" in low
            or "fromaddress invalid" in low
            or ("userpublickey" in low and ("invalid" in low or "format" in low))
            or "is not a valid address" in low):
        return "Connect a wallet (MetaMask for EVM, Phantom for Solana) and retry the swap."

    # Slippage
    if "slippage" in low and ("exceed" in low or "tolerance" in low):
        return (
            "Quote moved outside slippage tolerance. Increase slippage in "
            "settings or retry — markets are volatile right now."
        )

    # Insufficient liquidity
    if "insufficient liquidity" in low or "not enough liquidity" in low:
        return "Not enough on-chain liquidity for that size. Try a smaller amount."

    # Generic 4xx — keep the trace but explain
    m = re.search(r"\b(4\d\d|5\d\d)\b", text)
    if m:
        return f"Aggregator returned HTTP {m.group(1)}. Retry, or rephrase the swap."

    return text


def validate_quote_output(
    *,
    amount_in_human: float | int | str | None,
    amount_out_human: float | int | str | None,
) -> SwapValidation:
    """After we have a quote, refuse to render zero/negative outputs."""
    def _to_dec(x):
        try:
            return Decimal(str(x).replace(",", "").replace("~", "").strip())
        except (InvalidOperation, ValueError, TypeError):
            return None

    a_in = _to_dec(amount_in_human)
    a_out = _to_dec(amount_out_human)
    if a_in is None or a_in <= 0:
        return SwapValidation(
            ok=False,
            error_code="zero_amount_in",
            user_message="Input amount resolved to zero — recheck your balance and amount.",
            suggested_action="reject",
        )
    if a_out is None or a_out <= 0:
        return SwapValidation(
            ok=False,
            error_code="zero_amount_out",
            user_message=(
                "The aggregator returned a non-positive output amount, so we won't "
                "show a swap card. The quote is unreliable — try again or use a "
                "different pair."
            ),
            suggested_action="reject",
        )
    return SwapValidation(ok=True)
