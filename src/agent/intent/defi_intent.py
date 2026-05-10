from __future__ import annotations

from dataclasses import dataclass, field
import re


_CHAIN_ALIASES = {
    "solana": (r"\bsolana\b", r"\bsol\b"),
    "ethereum": (r"\bethereum\b", r"\beth\b", r"\bmainnet\b"),
    "arbitrum": (r"\barbitrum\b", r"\barb\b"),
    "base": (r"\bbase\b",),
    "optimism": (r"\boptimism\b", r"\bop\b"),
    "polygon": (r"\bpolygon\b", r"\bmatic\b"),
    "bsc": (r"\bbsc\b", r"\bbnb\b", r"\bbnb chain\b"),
    "avalanche": (r"\bavalanche\b", r"\bavax\b"),
}

_DEFI_TERMS = re.compile(
    r"\b(pool|pools|farm|farms|farming|vault|vaults|yield|yields|yielding|apy|apr|"
    r"staking|stake|stakes|lending|lend|lends|strategy|strategies|"
    r"opportunit(?:y|ies)|liquidit(?:y|ies)|defi|positions?)\b",
    re.IGNORECASE,
)
_SEARCH_TERMS = re.compile(r"\b(show|find|search|research|list|what|which)\b", re.IGNORECASE)
_ALLOCATION_TERMS = re.compile(
    r"\b(allocate|allocation|distribute|diversify|deploy|invest|put|"
    r"build\s+(?:me\s+)?(?:a\s+|an\s+|the\s+)?(?:[\w%/$.,-]+\s+){0,8}(?:strategy|portfolio|allocation\s+plan|yield\s+plan)|"
    r"design\s+(?:a\s+|an\s+|the\s+)?(?:[\w%/$.,-]+\s+){0,8}(?:strategy|portfolio)|"
    r"craft\s+(?:a\s+|an\s+|the\s+)?(?:[\w%/$.,-]+\s+){0,8}(?:strategy|portfolio)|"
    r"create\s+(?:a\s+|an\s+|the\s+)?(?:[\w%/$.,-]+\s+){0,8}(?:strategy|portfolio))\b",
    re.IGNORECASE,
)
_EXECUTION_TERMS = re.compile(r"\b(execute|deposit|through my wallet|automatically|sign|do it)\b", re.IGNORECASE)
_REINVEST_TERMS = re.compile(r"\b(reinvest(?:ment|ments)?|compound|auto-compound|autocompound|rebalance later|weekly\s+rebalanc|daily\s+rebalanc)\b", re.IGNORECASE)
_NEGATION_EXEC_TERMS = re.compile(
    r"\b(?:do\s+not\s+execute|don'?t\s+execute|just\s+research|research\s+only|"
    r"no\s+(?:signing|execution|transactions?|transactions)|"
    r"without\s+(?:signing|executing|wallet)|"
    r"do\s+not\s+(?:sign|deploy|deposit)|"
    r"hypothetical(?:ly)?|simulate\s+only|paper\s+trade)\b",
    re.IGNORECASE,
)
_STABLECOIN_TERMS = re.compile(
    r"\b(stable(?:coin)?(?:s|-only)?|stablecoin\s+only|usdc(?:\s+only)?|usdt(?:\s+only)?|stables?\s+only|"
    r"only\s+stable(?:s|coins?)?|stable\s+yield|stable\s+lending)\b",
    re.IGNORECASE,
)
_AMOUNT_ASSET_RE = re.compile(
    r"\b(?:i have|allocate|deploy|distribute|invest|put|with|of|using|totaling|"
    r"split\s+across\s+\d+\s+pools?,?|across\s+\d+\s+pools?,?)"
    r"\s+(-?)\$([\d,]+(?:\.\d+)?)\s*([kKmM])?\s*([A-Za-z]{2,10})?",
    re.IGNORECASE,
)
# Bare $X amount fallback — "$1500 USDC", "$50 million" — captured when context
# words above didn't match.
_BARE_AMOUNT_USD_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|[kKmM])?\b",
    re.IGNORECASE,
)


@dataclass
class DefiIntent:
    intent: str
    product_types: list[str] = field(default_factory=list)
    chains: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    risk_levels: list[str] = field(default_factory=list)
    target_apy: float | None = None
    apy_mode: str | None = None
    min_apy: float | None = None
    max_apy: float | None = None
    min_tvl: float = 100_000.0
    ranking_objective: str = "constraint_fit_then_risk_adjusted_return"
    execution_requested: bool = False
    reinvestment_requested: bool = False
    amount_usd: float | None = None
    asset_hint: str | None = None
    risk_budget: str = "balanced"
    stablecoin_only: bool = False
    reinvestment_cadence: str | None = None


def _parse_chains(text: str) -> list[str]:
    chains: list[str] = []
    for chain, patterns in _CHAIN_ALIASES.items():
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
            chains.append(chain)
    return chains


def _parse_product_types(text: str) -> list[str]:
    lowered = text.lower()
    product_types: list[str] = []
    if "pool" in lowered or "liquidity" in lowered:
        product_types.append("pool")
    if "farm" in lowered:
        product_types.append("farm")
    if "vault" in lowered:
        product_types.append("vault")
    if "lend" in lowered or "supply" in lowered:
        product_types.append("lending")
    if "stake" in lowered or "staking" in lowered:
        product_types.append("staking")
    if not product_types and re.search(r"\b(yield|apy|apr|opportunit(?:y|ies))\b", lowered):
        product_types.extend(["pool", "farm", "vault", "lending"])
    return product_types


def _parse_risk_levels(text: str) -> list[str]:
    lowered = text.lower()
    levels: list[str] = []
    if re.search(r"medium\s*(?:and|/|-|to)?\s*high|medium[- ]high", lowered):
        return ["MEDIUM", "HIGH"]
    if any(term in lowered for term in (
        "safe", "safest", "conservative", "low risk", "low-risk",
        "minimum risk", "min risk", "minimal risk", "lowest risk",
        "least risk", "lowest-risk", "minimum-risk",
    )):
        levels.append("LOW")
    if re.search(r"\bmedium(?:\s+risk|-risk)?\b", lowered):
        levels.append("MEDIUM")
    if any(term in lowered for term in (
        "aggressive", "high risk", "high-risk", "highest risk", "max risk", "maximum risk",
    )):
        levels.append("HIGH")
    return [level for level in ("LOW", "MEDIUM", "HIGH") if level in levels]


_WORD_NUMS: dict[str, int] = {
    "five": 5, "ten": 10, "fifteen": 15, "twenty": 20,
    "twenty-five": 25, "twenty five": 25,
    "thirty": 30,
    "thirty-five": 35, "thirty five": 35,
    "forty": 40, "fourty": 40,
    "forty-five": 45, "forty five": 45, "fourty-five": 45, "fourty five": 45,
    "fifty": 50,
    "fifty-five": 55, "fifty five": 55,
    "sixty": 60,
    "sixty-five": 65, "sixty five": 65,
    "seventy": 70,
    "seventy-five": 75, "seventy five": 75,
    "eighty": 80,
    "eighty-five": 85, "eighty five": 85,
    "ninety": 90,
    "ninety-five": 95, "ninety five": 95,
    "one hundred": 100, "hundred": 100,
    "two hundred": 200, "three hundred": 300, "five hundred": 500,
    "one thousand": 1000, "thousand": 1000,
}


def _parse_apy(text: str) -> tuple[float | None, str | None, float | None, float | None]:
    # Pass 1: digit-form (with optional APY/APR/yield/% suffix and optional mode word)
    pattern = re.compile(
        r"(?:(?P<mode>around|about|near|target(?:ing)?|at\s+least|minimum|min|over|above|under|below|up\s+to)\s+)?"
        r"(?P<num>\d+(?:\.\d+)?)\s*(?:%|percent|pct)?\s*(?:apy|apr|yield)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        # Pass 2: digit-form with bare "%" or "percent" (no APY/APR/yield suffix)
        pattern2 = re.compile(
            r"(?:(?P<mode>around|about|near|target(?:ing)?|at\s+least|minimum|min|over|above|under|below|up\s+to)\s+)?"
            r"(?P<num>\d+(?:\.\d+)?)\s*(?:%|percent|pct)(?=\s|[^a-zA-Z0-9]|$)",
            re.IGNORECASE,
        )
        match = pattern2.search(text)
    if not match:
        # Pass 3: word numbers ("sixty percent APY", "thirty-five percent")
        word_pattern = re.compile(
            r"(?:(?P<mode>around|about|near|target(?:ing)?|at\s+least|minimum|min|over|above|under|below|up\s+to)\s+)?"
            r"(?P<word>"
            + "|".join(re.escape(w) for w in sorted(_WORD_NUMS.keys(), key=len, reverse=True))
            + r")\s+(?:%|percent|pct)(?=\s|[^a-zA-Z0-9]|$)(?:\s*(?:apy|apr|yield))?",
            re.IGNORECASE,
        )
        wm = word_pattern.search(text)
        if not wm:
            return None, None, None, None
        word = wm.group("word").lower().replace("-", " ")
        word = re.sub(r"\s+", " ", word).strip()
        target = float(_WORD_NUMS.get(word, 0))
        if target <= 0:
            return None, None, None, None
        mode_text = (wm.group("mode") or "around").lower().replace(" ", "_")
        if mode_text in {"at_least", "minimum", "min", "over", "above"}:
            return target, "at_least", target, 500.0
        if mode_text in {"under", "below", "up_to"}:
            return target, "at_most", 0.5, target
        return target, "around", max(0.5, target * 0.7), target * 1.6
    target = float(match.group("num"))
    mode_text = (match.group("mode") or "around").lower().replace(" ", "_")
    if mode_text in {"around", "about", "near", "target", "targeting"}:
        return target, "around", max(0.5, target * 0.7), target * 1.6
    if mode_text in {"at_least", "minimum", "min", "over", "above"}:
        return target, "at_least", target, 500.0
    if mode_text in {"under", "below", "up_to"}:
        return target, "at_most", 0.5, target
    return target, "around", max(0.5, target * 0.7), target * 1.6


def _parse_amount_and_asset(text: str) -> tuple[float | None, str | None]:
    match = _AMOUNT_ASSET_RE.search(text)
    if match:
        sign = match.group(1) or ""
        raw = match.group(2).replace(",", "")
        try:
            amount = float(raw)
        except ValueError:
            return None, None
        if sign == "-":
            amount = -amount
        suffix = (match.group(3) or "").lower()
        if suffix == "k":
            amount *= 1_000
        elif suffix == "m":
            amount *= 1_000_000
        asset = (match.group(4) or "").upper() or None
        if asset and asset.lower() in _CHAIN_ALIASES:
            asset = None
        return amount, asset
    # Bare "$X" / "$50 million" fallback — only fires when no anchored verb was
    # found. Lets "Build me a strategy with $1500 USDC" / "I have $50 million
    # USDC" surface an amount even when the verb pattern misses.
    bare = _BARE_AMOUNT_USD_RE.search(text)
    if not bare:
        return None, None
    try:
        amount = float(bare.group(1).replace(",", ""))
    except ValueError:
        return None, None
    suffix = (bare.group(2) or "").lower()
    if suffix == "k":
        amount *= 1_000
    elif suffix in {"m", "million"}:
        amount *= 1_000_000
    elif suffix == "billion":
        amount *= 1_000_000_000
    return amount, None


def _risk_budget_for(risk_levels: list[str], text: str) -> str:
    lowered = text.lower()
    if "conservative" in lowered or risk_levels == ["LOW"]:
        return "conservative"
    if "aggressive" in lowered or ("HIGH" in risk_levels and "LOW" not in risk_levels):
        return "aggressive"
    return "balanced"


def parse_defi_intent(message: str) -> DefiIntent:
    text = message.strip()
    has_defi_terms = bool(_DEFI_TERMS.search(text))
    chains = _parse_chains(text)
    product_types = _parse_product_types(text)
    risk_levels = _parse_risk_levels(text)
    target_apy, apy_mode, min_apy, max_apy = _parse_apy(text)
    amount_usd, asset_hint = _parse_amount_and_asset(text)
    negated_execution = bool(_NEGATION_EXEC_TERMS.search(text))
    execution_requested = bool(_EXECUTION_TERMS.search(text)) and not negated_execution
    reinvestment_requested = bool(_REINVEST_TERMS.search(text))
    stablecoin_only = bool(_STABLECOIN_TERMS.search(text))
    cadence: str | None = None
    if re.search(r"\bweekly\b", text, re.I):
        cadence = "weekly"
    elif re.search(r"\bdaily\b", text, re.I):
        cadence = "daily"
    elif re.search(r"\bmonthly\b", text, re.I):
        cadence = "monthly"
    allocation_requested = bool(_ALLOCATION_TERMS.search(text)) and amount_usd is not None
    search_requested = bool(_SEARCH_TERMS.search(text)) or has_defi_terms

    if execution_requested and has_defi_terms:
        intent = "execute_yield_strategy"
        ranking_objective = "execution_ready_strategy"
    elif allocation_requested:
        intent = "allocate_strategy"
        ranking_objective = "highest_sentinel_score"
    elif search_requested and has_defi_terms:
        intent = "search_defi_opportunities"
        if re.search(r"highest\s+(?:scoring|sentinel)", text, re.IGNORECASE):
            ranking_objective = "highest_sentinel_score"
        elif re.search(r"highest\s+(?:apy|yield)", text, re.IGNORECASE):
            ranking_objective = "highest_apy_after_sanity_filters"
        elif target_apy is not None:
            ranking_objective = "constraint_fit_then_risk_adjusted_return"
        else:
            ranking_objective = "highest_sentinel_score"
    else:
        intent = "explain_or_compare"
        ranking_objective = "highest_sentinel_score"

    return DefiIntent(
        intent=intent,
        product_types=product_types,
        chains=chains,
        risk_levels=risk_levels,
        target_apy=target_apy,
        apy_mode=apy_mode,
        min_apy=min_apy,
        max_apy=max_apy,
        ranking_objective=ranking_objective,
        execution_requested=execution_requested,
        reinvestment_requested=reinvestment_requested,
        amount_usd=amount_usd,
        asset_hint=asset_hint,
        risk_budget=_risk_budget_for(risk_levels, text),
        stablecoin_only=stablecoin_only,
        reinvestment_cadence=cadence,
    )
