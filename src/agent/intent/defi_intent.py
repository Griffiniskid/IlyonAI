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
    r"\b(pool|pools|farm|farms|vault|vaults|yield|apy|apr|staking|stake|lending|strategy|opportunit(?:y|ies))\b",
    re.IGNORECASE,
)
_SEARCH_TERMS = re.compile(r"\b(show|find|search|research|list|what|which)\b", re.IGNORECASE)
_ALLOCATION_TERMS = re.compile(r"\b(allocate|allocation|distribute|diversify|deploy|invest|put)\b", re.IGNORECASE)
_EXECUTION_TERMS = re.compile(r"\b(execute|deposit|through my wallet|automatically|build .*strategy|sign|do it)\b", re.IGNORECASE)
_REINVEST_TERMS = re.compile(r"\b(reinvest|compound|auto-compound|autocompound|rebalance later)\b", re.IGNORECASE)
_AMOUNT_ASSET_RE = re.compile(
    r"\b(?:i have|allocate|deploy|distribute|invest|put)\s+\$?([\d,]+(?:\.\d+)?)\s*([kKmM])?\s*([A-Za-z]{2,10})?",
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
    if any(term in lowered for term in ("safe", "conservative", "low risk", "low-risk")):
        levels.append("LOW")
    if re.search(r"\bmedium(?:\s+risk|-risk)?\b", lowered):
        levels.append("MEDIUM")
    if any(term in lowered for term in ("aggressive", "high risk", "high-risk")):
        levels.append("HIGH")
    return [level for level in ("LOW", "MEDIUM", "HIGH") if level in levels]


def _parse_apy(text: str) -> tuple[float | None, str | None, float | None, float | None]:
    pattern = re.compile(
        r"(?:(?P<mode>around|about|near|target(?:ing)?|at\s+least|minimum|min|over|above|under|below|up\s+to)\s+)?"
        r"(?P<num>\d+(?:\.\d+)?)\s*%?\s*(?:apy|apr|yield)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None, None, None, None
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
    if not match:
        return None, None
    raw = match.group(1).replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        return None, None
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        amount *= 1_000
    elif suffix == "m":
        amount *= 1_000_000
    asset = (match.group(3) or "").upper() or None
    if asset and asset.lower() in _CHAIN_ALIASES:
        asset = None
    return amount, asset


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
    execution_requested = bool(_EXECUTION_TERMS.search(text))
    reinvestment_requested = bool(_REINVEST_TERMS.search(text))
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
    )
