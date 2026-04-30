from src.scoring.bridge_scorer import score_bridge_mapping
from src.scoring.cache import TTLScoreCache
from src.scoring.route_scorer import score_route_mapping


def test_route_scorer_adds_shield_for_known_router():
    sentinel, shield = score_route_mapping(
        {
            "router": "Enso",
            "token_in": "ETH",
            "token_out": "USDC",
            "slippage_bps": 75,
            "price_impact_pct": 0.2,
        }
    )

    assert sentinel.sentinel >= 65
    assert shield.verdict in {"SAFE", "CAUTION"}


def test_route_scorer_warns_for_scam_like_token():
    sentinel, shield = score_route_mapping(
        {
            "router": "UnknownRouter",
            "token_in": "ETH",
            "token_out": "RANDOMSCAMTOKEN",
            "slippage_bps": 900,
        }
    )

    assert sentinel.sentinel < 65
    assert shield.verdict in {"RISKY", "SCAM"}
    assert any(reason in shield.reasons for reason in ["Honeypot pattern", "Unaudited route token"])


def test_bridge_scorer_scores_destination_and_cross_chain_shield():
    sentinel, shield = score_bridge_mapping(
        {
            "token_in": "USDC",
            "dst_chain_id": 42161,
            "amount_usd": 1_000,
            "spender": "deBridge",
        }
    )

    assert sentinel.sentinel >= 65
    assert shield.verdict in {"SAFE", "CAUTION"}
    assert "Cross-chain route" in shield.reasons


def test_ttl_score_cache_is_deterministic_with_clock():
    now = [100.0]
    cache = TTLScoreCache(ttl_seconds=60, clock=lambda: now[0])
    calls = {"count": 0}

    def factory():
        calls["count"] += 1
        return {"value": calls["count"]}

    assert cache.get_or_set("route:1", factory) == {"value": 1}
    assert cache.get_or_set("route:1", factory) == {"value": 1}
    now[0] += 61
    assert cache.get_or_set("route:1", factory) == {"value": 2}
