from src.defi.opportunity_taxonomy import classify_defi_record


def test_classifies_incentivized_stable_lp():
    record = {
        "project": "curve-dex",
        "symbol": "USDC-USDT",
        "stablecoin": True,
        "underlying_tokens": ["0xusdc", "0xusdt"],
        "reward_tokens": ["0xcrv"],
        "apy_reward": 1.2,
        "il_risk": "no",
    }

    classification = classify_defi_record(record)
    assert classification["product_type"] == "incentivized_stable_lp"
    assert classification["normalized_exposure"] == "stable-stable"
    assert classification["supports_pool_route"] is True
    assert classification["default_kind"] == "yield"


def test_classifies_crypto_stable_lp_even_when_raw_exposure_is_multi():
    record = {
        "project": "uniswap-v4",
        "symbol": "ETH-USDC",
        "exposure": "multi",
        "stablecoin": False,
        "underlying_tokens": ["0xeth", "0xusdc"],
        "reward_tokens": [],
        "apy_reward": 0,
        "il_risk": "yes",
    }

    classification = classify_defi_record(record)
    assert classification["product_type"] == "crypto_stable_lp"
    assert classification["normalized_exposure"] == "crypto-stable"
    assert classification["supports_pool_route"] is True
    assert classification["default_kind"] == "pool"


def test_excludes_single_asset_lending_from_pool_route():
    record = {
        "project": "aave-v3",
        "symbol": "USDC",
        "exposure": "single",
        "underlying_tokens": ["0xusdc"],
        "reward_tokens": [],
        "total_supply_usd": 1_000_000,
        "total_borrow_usd": 500_000,
        "utilization": 0.5,
        "apy_reward": 0,
        "il_risk": "no",
    }

    classification = classify_defi_record(record)
    assert classification["product_type"] == "lending_supply_like"
    assert classification["score_family"] == "single_asset"
    assert classification["supports_pool_route"] is False
    assert classification["default_kind"] == "lending_supply"
