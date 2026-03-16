from src.defi.risk_engine import DefiRiskEngine


def _docs(real: bool = True):
    return {
        "available": real,
        "placeholder": not real,
        "governance_score": 62,
        "has_timelock_mentions": True,
        "has_multisig_mentions": True,
        "has_admin_mentions": False,
        "freshness_hours": 1 if real else None,
    }


def _history(available: bool = True):
    if not available:
        return {"available": False, "placeholder": True}
    return {
        "available": True,
        "apy_persistence_score": 68,
        "apy_trend_score": 60,
        "tvl_trend_score": 72,
        "tvl_drawdown_pct": 12,
        "recent_apy_drop_pct": 8,
        "recent_tvl_drop_pct": 3,
    }


def _deps():
    return [
        {"dependency_type": "protocol", "risk_score": 28},
        {"dependency_type": "underlying", "risk_score": 12},
    ]


def test_stable_lp_quality_is_separate_from_return_potential():
    engine = DefiRiskEngine()
    item = {
        "product_type": "stable_lp",
        "score_family": "lp",
        "normalized_exposure": "stable-stable",
        "chain": "ethereum",
        "project": "curve-dex",
        "symbol": "USDC-USDT",
        "tvl_usd": 8_000_000,
        "apy": 1.8,
        "apy_base": 1.8,
        "apy_reward": 0.0,
        "volume_usd_1d": 5_000_000,
        "il_risk": "no",
    }
    assets = [
        {"symbol": "USDC", "role": "underlying", "quality_score": 95, "is_stable": True, "is_major": False, "depeg_risk": 5, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
        {"symbol": "USDT", "role": "underlying", "quality_score": 88, "is_stable": True, "is_major": False, "depeg_risk": 12, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
    ]

    result = engine.score_opportunity("pool", item, assets, _deps(), 74, _docs(True), _history(True), [], ranking_profile="balanced")
    summary = result["summary"]

    assert summary["quality_score"] >= 60
    assert summary["return_potential_score"] < summary["quality_score"]
    assert summary["risk_level"] == "LOW"


def test_crypto_stable_lp_structure_is_not_treated_as_generic_multi():
    engine = DefiRiskEngine()
    item = {
        "product_type": "crypto_stable_lp",
        "score_family": "lp",
        "normalized_exposure": "crypto-stable",
        "chain": "base",
        "project": "uniswap-v4",
        "symbol": "ETH-USDC",
        "tvl_usd": 2_000_000,
        "apy": 24.0,
        "apy_base": 24.0,
        "apy_reward": 0.0,
        "volume_usd_1d": 1_500_000,
        "il_risk": "yes",
    }
    assets = [
        {"symbol": "ETH", "role": "underlying", "quality_score": 92, "is_stable": False, "is_major": True, "depeg_risk": 0, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
        {"symbol": "USDC", "role": "underlying", "quality_score": 95, "is_stable": True, "is_major": False, "depeg_risk": 5, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
    ]

    result = engine.score_opportunity("pool", item, assets, _deps(), 72, _docs(True), _history(True), [], ranking_profile="balanced")
    structure = next(d for d in result["dimensions"] if d["key"] == "structure_safety")
    assert structure["score"] >= 60


def test_placeholder_docs_and_missing_history_cap_confidence():
    engine = DefiRiskEngine()
    item = {
        "product_type": "stable_lp",
        "score_family": "lp",
        "normalized_exposure": "stable-stable",
        "chain": "ethereum",
        "project": "curve-dex",
        "symbol": "USDC-USDT",
        "tvl_usd": 8_000_000,
        "apy": 2.0,
        "apy_base": 2.0,
        "apy_reward": 0.0,
        "volume_usd_1d": 0.0,
        "il_risk": "no",
    }
    assets = [
        {"symbol": "USDC", "role": "underlying", "quality_score": 95, "is_stable": True, "is_major": False, "depeg_risk": 5, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
        {"symbol": "USDT", "role": "underlying", "quality_score": 88, "is_stable": True, "is_major": False, "depeg_risk": 12, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
    ]

    result = engine.score_opportunity("pool", item, assets, _deps(), 72, _docs(False), _history(False), [], ranking_profile="balanced")
    assert result["confidence"]["score"] <= 55
    assert result["confidence"]["partial_analysis"] is True


def test_overall_score_rewards_better_apr_efficiency_for_similar_risk():
    engine = DefiRiskEngine()
    base_item = {
        "product_type": "crypto_stable_lp",
        "score_family": "lp",
        "normalized_exposure": "crypto-stable",
        "chain": "ethereum",
        "project": "uniswap-v3",
        "symbol": "ETH-USDC",
        "tvl_usd": 20_000_000,
        "apy_reward": 0.0,
        "volume_usd_1d": 25_000_000,
        "il_risk": "yes",
        "pool_meta": "0.05%",
    }
    assets = [
        {"symbol": "ETH", "role": "underlying", "quality_score": 92, "is_stable": False, "is_major": True, "depeg_risk": 0, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
        {"symbol": "USDC", "role": "underlying", "quality_score": 95, "is_stable": True, "is_major": False, "depeg_risk": 5, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
    ]

    low_apr = {**base_item, "apy": 2.0, "apy_base": 2.0}
    high_apr = {**base_item, "apy": 12.0, "apy_base": 12.0}

    low_result = engine.score_opportunity("pool", low_apr, assets, _deps(), 74, _docs(True), _history(True), [], ranking_profile="balanced")
    high_result = engine.score_opportunity("pool", high_apr, assets, _deps(), 74, _docs(True), _history(True), [], ranking_profile="balanced")

    assert high_result["summary"]["apr_efficiency_score"] > low_result["summary"]["apr_efficiency_score"]
    assert high_result["summary"]["overall_score"] > low_result["summary"]["overall_score"]


def test_bad_reward_heavy_farm_scores_poorly_overall():
    engine = DefiRiskEngine()
    item = {
        "product_type": "incentivized_crypto_crypto_lp",
        "score_family": "lp",
        "normalized_exposure": "crypto-crypto",
        "chain": "base",
        "project": "shadow-exchange",
        "symbol": "FOO-WETH",
        "tvl_usd": 180_000,
        "apy": 220.0,
        "apy_base": 8.0,
        "apy_reward": 212.0,
        "volume_usd_1d": 70_000,
        "il_risk": "yes",
        "pool_meta": "0.01%",
    }
    assets = [
        {"symbol": "FOO", "role": "underlying", "quality_score": 32, "is_stable": False, "is_major": False, "depeg_risk": 0, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
        {"symbol": "WETH", "role": "underlying", "quality_score": 91, "is_stable": False, "is_major": True, "depeg_risk": 0, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
        {"symbol": "RWD", "role": "reward", "quality_score": 25, "is_stable": False, "is_major": False, "depeg_risk": 0, "wrapper_risk": 0, "liquidity_usd": 0, "market_cap_usd": 0, "volatility_24h": 0},
    ]
    history = {
        "available": True,
        "apy_persistence_score": 24,
        "apy_trend_score": 15,
        "tvl_trend_score": 22,
        "tvl_drawdown_pct": 55,
        "recent_apy_drop_pct": 72,
        "recent_tvl_drop_pct": 31,
    }

    result = engine.score_opportunity("yield", item, assets, _deps(), 50, _docs(False), history, [], ranking_profile="balanced")
    assert result["summary"]["overall_score"] < 35
    assert result["summary"]["apr_efficiency_score"] < 40
