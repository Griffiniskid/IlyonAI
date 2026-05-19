"""Cross-chain intent detection + source-chain inference.

Pass A findings rows 10-11 caught two failure modes:

* **E01/E02/E07** — multi-step cross-chain prompts (e.g. "bridge 100 USDC from
  Arbitrum to Base then supply on Aave V3") emitted a `pool_link` no-exec card
  instead of the signable `composed_plan` two-step (bridge + post-action) plan.
  Class: cross-chain post-action drops onto pool_link path.
* **E04/E05/E06/E09/E12/E13/E14** — cross-chain prompts with the source chain
  *implied* by wallet context (e.g. "bridge my USDC to mainnet and supply on
  Aave") silently dropped the source chain. The build_yield_execution_plan
  composed-plan branch only fires when `extra.source_chain` is set, so a
  dest-only prompt routed to the regular single-chain pool_link path and the
  bridge leg never materialised.

This module is the single source of truth for:

1. Detecting whether a user message expresses a cross-chain intent and whether
   it has a post-action (supply / stake / lp / lend).
2. Extracting `(source_chain, dest_chain)` from the message — and returning a
   `CROSS_CHAIN_SOURCE_AMBIGUOUS` sentinel when only the destination is
   detected, so the runtime can emit a blocker rather than silently default to
   a dest-only pool_link.

Wiring note: the dispatch list in `src/agent/simple_runtime.py` is owned by the
sanitizer-fix agent in this hand-off. After both branches land, a follow-up
patch should prepend `_detect_cross_chain_universal` from this module to the
dispatch tuple so the looser forms route to `build_yield_execution_plan` with
`extra.source_chain` populated. Until then, `build_yield_execution_plan`
itself calls `infer_cross_chain_hint` to backstop the routing decision.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Canonical chain slugs the rest of the runtime understands.
_CHAIN_SLUGS: dict[str, str] = {
    # EVM
    "ethereum": "ethereum",
    "eth": "ethereum",
    "mainnet": "ethereum",
    "l1": "ethereum",
    "polygon": "polygon",
    "matic": "polygon",
    "arbitrum": "arbitrum",
    "arb": "arbitrum",
    "optimism": "optimism",
    "op": "optimism",
    "base": "base",
    "avalanche": "avalanche",
    "avax": "avalanche",
    "bsc": "bsc",
    "bnb": "bsc",
    "binance": "bsc",
    "linea": "linea",
    "scroll": "scroll",
    "zksync": "zksync",
    "mantle": "mantle",
    "blast": "blast",
    # Solana
    "solana": "solana",
    "sol": "solana",
}

# Tokens whose home chain we can confidently assume when source is implied.
# Kept tight on purpose — anything ambiguous (USDC, USDT, WBTC, ETH…) MUST
# trigger the CROSS_CHAIN_SOURCE_AMBIGUOUS blocker rather than guess.
_TOKEN_HOME_CHAIN_STRICT: dict[str, str] = {
    "SOL": "solana",
    "WSOL": "solana",
    "BNB": "bsc",
    "WBNB": "bsc",
    "MATIC": "polygon",
    "AVAX": "avalanche",
    "ARB": "arbitrum",
    "OP": "optimism",
}

# Phrases that mark a cross-chain verb.
_BRIDGE_VERBS = (
    r"bridge|move|send|transfer|relay|cross[-\s]?chain|teleport"
)

# Phrases that mark a yield post-action (so the plan needs 2 signable steps).
_POST_ACTION_VERBS = (
    r"supply|deposit|stake|provide|lend|add\s+liquidity|lp|farm|earn|"
    r"borrow|mint|wrap"
)

# Loose cross-chain detector: any cross-chain verb + destination chain.
# Matches "bridge to base", "move my USDC to ethereum", "send 50 USDT to optimism then supply on aave".
_LOOSE_CROSS_CHAIN_RE = re.compile(
    rf"\b(?:{_BRIDGE_VERBS})\b[^.]*?\bto\s+(?P<dst>[A-Za-z][A-Za-z0-9]*)\b",
    re.IGNORECASE,
)

# Strict form with explicit source: "...from <chain> to <chain>".
_FROM_TO_RE = re.compile(
    r"\bfrom\s+(?P<src>[A-Za-z][A-Za-z0-9]*)\s+to\s+(?P<dst>[A-Za-z][A-Za-z0-9]*)\b",
    re.IGNORECASE,
)

# Post-action presence test ("then supply", "and stake", "to deposit into …").
_POST_ACTION_RE = re.compile(
    rf"\b(?:then|and|to|,)\s+(?:{_POST_ACTION_VERBS})\b",
    re.IGNORECASE,
)

# Token mention so we can fall back to _TOKEN_HOME_CHAIN_STRICT when source is
# implied. The shape is intentionally narrow to avoid grabbing English words.
_TOKEN_MENTION_RE = re.compile(
    r"\b(?P<token>[A-Z]{2,8})\b",
)


@dataclass(frozen=True)
class CrossChainIntent:
    """Outcome of inferring cross-chain intent from a user message.

    `is_cross_chain` — message expresses cross-chain motion.
    `has_post_action` — message also wants to supply/stake/lp after bridging,
        which means the runtime MUST emit a composed_plan (signable 2-step)
        rather than a pool_link no-exec card.
    `source_chain` — extracted or inferred from token home chain. None when
        the runtime should emit CROSS_CHAIN_SOURCE_AMBIGUOUS.
    `dest_chain` — extracted from the message ("to <chain>").
    `source_ambiguous` — True when destination was found but source could not
        be unambiguously extracted/inferred.
    """

    is_cross_chain: bool
    has_post_action: bool
    source_chain: str | None
    dest_chain: str | None
    source_ambiguous: bool

    @property
    def needs_composed_plan(self) -> bool:
        """Routing rule: cross-chain + post-action MUST use composed_plan."""
        return self.is_cross_chain and self.has_post_action

    @property
    def needs_source_blocker(self) -> bool:
        """Surface CROSS_CHAIN_SOURCE_AMBIGUOUS when dest is set but source isn't."""
        return self.is_cross_chain and self.source_ambiguous


def _normalize_chain(raw: str | None) -> str | None:
    if not raw:
        return None
    tok = raw.strip().lower()
    tok = re.sub(r"\s+(chain|network|mainnet)$", "", tok)
    return _CHAIN_SLUGS.get(tok)


def infer_cross_chain_hint(message: str) -> CrossChainIntent:
    """Parse `message` for cross-chain motion + (source, dest) chains.

    Resolution order for source:
    1. Explicit "from <chain>" capture.
    2. Token home-chain when the message names a chain-native token (SOL/BNB/
       AVAX/MATIC/ARB/OP) and no "from" was given.
    3. Otherwise mark `source_ambiguous=True` so the caller emits the
       CROSS_CHAIN_SOURCE_AMBIGUOUS blocker instead of routing to the
       destination-only pool_link branch (the E04-E14 bug class).
    """
    text = (message or "").strip()
    if not text:
        return CrossChainIntent(False, False, None, None, False)

    loose = _LOOSE_CROSS_CHAIN_RE.search(text)
    if not loose:
        return CrossChainIntent(False, False, None, None, False)

    dst = _normalize_chain(loose.group("dst"))
    if dst is None:
        # The cross-chain verb fired but the destination isn't a known chain
        # slug — treat as not-cross-chain so existing detectors handle it.
        return CrossChainIntent(False, False, None, None, False)

    # Source extraction.
    src: str | None = None
    src_ambiguous = False
    from_to = _FROM_TO_RE.search(text)
    if from_to:
        src_candidate = _normalize_chain(from_to.group("src"))
        # Re-resolve dst from the explicit form too — the loose regex may have
        # picked a later "to <X>" further into the sentence.
        dst_candidate = _normalize_chain(from_to.group("dst"))
        if src_candidate and dst_candidate and src_candidate != dst_candidate:
            src = src_candidate
            dst = dst_candidate
    if src is None:
        # Try token-home-chain inference.
        for token_match in _TOKEN_MENTION_RE.finditer(text):
            token = token_match.group("token").upper()
            home = _TOKEN_HOME_CHAIN_STRICT.get(token)
            if home and home != dst:
                src = home
                break
        if src is None:
            src_ambiguous = True

    has_post = bool(_POST_ACTION_RE.search(text))

    return CrossChainIntent(
        is_cross_chain=True,
        has_post_action=has_post,
        source_chain=src,
        dest_chain=dst,
        source_ambiguous=src_ambiguous,
    )


def cross_chain_source_blocker_payload(
    *, dest_chain: str | None, message: str
) -> dict:
    """Shape the CROSS_CHAIN_SOURCE_AMBIGUOUS blocker payload.

    Returned as a plain dict so the caller can fold it into an
    ExecutionBlocker (build_yield_execution_plan) or surface it directly via
    an err_envelope (simple dispatch path). Keeping the shape stable here
    means every emission site uses identical copy.
    """
    return {
        "code": "CROSS_CHAIN_SOURCE_AMBIGUOUS",
        "severity": "blocker",
        "title": "Source chain missing",
        "detail": (
            "Cross-chain intent detected — destination chain "
            f"{dest_chain or '(unknown)'} parsed but the source chain was "
            "not specified. Re-prompt with the source chain explicitly "
            "(e.g. 'from Arbitrum') so the deBridge DLN bridge leg can "
            "be quoted without guessing."
        ),
        "cta": "Specify source chain (e.g. 'from Arbitrum').",
        "message": message,
    }


__all__ = [
    "CrossChainIntent",
    "infer_cross_chain_hint",
    "cross_chain_source_blocker_payload",
]
