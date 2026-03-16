"""Canonical product taxonomy for DeFi opportunity classification."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


STABLE_SYMBOLS = {
    "USDC", "USDT", "DAI", "FRAX", "BUSD", "LUSD", "SUSD", "TUSD", "USDP", "USDS", "USDE", "FDUSD", "GHO", "USDBC"
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pool_value(pool: Dict[str, Any], snake_key: str, legacy_key: Optional[str] = None, default: Any = None) -> Any:
    if snake_key in pool and pool.get(snake_key) is not None:
        return pool.get(snake_key)
    if legacy_key and legacy_key in pool and pool.get(legacy_key) is not None:
        return pool.get(legacy_key)
    return default


def _symbol_parts(symbol: str) -> List[str]:
    return [part.strip().upper() for part in str(symbol or "").replace("-", "/").split("/") if part.strip()]


def _category_haystack(pool: Dict[str, Any]) -> str:
    return " ".join(
        str(pool.get(key) or "")
        for key in ("category", "project", "pool_meta", "symbol", "url")
    ).lower()


def _normalized_exposure(pool: Dict[str, Any], asset_count: int, symbol_parts: Iterable[str]) -> str:
    raw = str(_pool_value(pool, "exposure_type", "exposure", "") or "").strip().lower()
    if raw in {"stable-stable", "crypto-stable", "crypto-crypto", "single"}:
        return raw
    if asset_count <= 1:
        return "single"

    parts = list(symbol_parts)
    stable_count = sum(1 for part in parts if part in STABLE_SYMBOLS)
    if stable_count == asset_count and asset_count > 0:
        return "stable-stable"
    if stable_count > 0:
        return "crypto-stable"
    return "crypto-crypto"


def classify_defi_record(pool: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a DefiLlama record into a canonical product taxonomy."""
    underlying = list(_pool_value(pool, "underlying_tokens", "underlyingTokens", []) or [])
    reward_tokens = list(_pool_value(pool, "reward_tokens", "rewardTokens", []) or [])
    symbol_parts = _symbol_parts(pool.get("symbol") or "")
    asset_count = max(len(underlying), len(symbol_parts), 1)
    category_text = _category_haystack(pool)
    apy_reward = _safe_float(_pool_value(pool, "apy_reward", "apyReward", 0))
    has_rewards = bool(reward_tokens or apy_reward > 0)
    total_supply = _safe_float(_pool_value(pool, "total_supply_usd", "totalSupplyUsd", 0))
    total_borrow = _safe_float(_pool_value(pool, "total_borrow_usd", "totalBorrowUsd", 0))
    utilization = _safe_float(pool.get("utilization"))
    normalized_exposure = _normalized_exposure(pool, asset_count, symbol_parts)
    stablecoin = bool(pool.get("stablecoin"))
    il_risk = str(_pool_value(pool, "il_risk", "ilRisk", "") or "").strip().lower() == "yes"

    lending_markers = (
        total_supply > 0
        or total_borrow > 0
        or utilization > 0
        or any(marker in category_text for marker in ("lending", "borrow", "money market", "cdp", "loan", "supply"))
    )
    staking_markers = any(marker in category_text for marker in ("staking", "staked", "restaking", "validator", "liquid staking"))
    vault_markers = any(marker in category_text for marker in ("vault", "strategy", "yield aggregator"))
    lp_like = asset_count >= 2 or il_risk or normalized_exposure in {"stable-stable", "crypto-stable", "crypto-crypto"}

    if lending_markers and not lp_like:
        product_type = "lending_supply_like"
        score_family = "single_asset"
        search_group = "lending"
    elif staking_markers and not lp_like:
        product_type = "single_asset_staking"
        score_family = "single_asset"
        search_group = "staking"
    elif vault_markers and not lp_like:
        product_type = "single_asset_vault"
        score_family = "single_asset"
        search_group = "vault"
    elif lp_like:
        if normalized_exposure == "stable-stable" or (stablecoin and asset_count >= 2):
            product_type = "incentivized_stable_lp" if has_rewards else "stable_lp"
        elif normalized_exposure == "crypto-stable":
            product_type = "incentivized_crypto_stable_lp" if has_rewards else "crypto_stable_lp"
        else:
            product_type = "incentivized_crypto_crypto_lp" if has_rewards else "crypto_crypto_lp"
        score_family = "lp"
        search_group = "pool"
    else:
        product_type = "single_asset_yield"
        score_family = "single_asset"
        search_group = "yield"

    display_kind = "yield" if has_rewards and score_family == "lp" else "pool" if score_family == "lp" else "lending" if product_type == "lending_supply_like" else "yield"
    return {
        "product_type": product_type,
        "score_family": score_family,
        "search_group": search_group,
        "asset_count": asset_count,
        "has_rewards": has_rewards,
        "is_incentivized": has_rewards,
        "is_lp_like": score_family == "lp",
        "is_single_asset": asset_count <= 1,
        "normalized_exposure": normalized_exposure,
        "stablecoin": stablecoin,
        "default_kind": display_kind,
        "supports_pool_route": score_family == "lp",
    }
