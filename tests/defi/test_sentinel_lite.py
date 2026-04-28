from src.defi.sentinel_lite import sentinel_lite


def test_high_score_gets_safe_badge():
    r = sentinel_lite(shield_verdict={"grade": "A"}, pool_sentinel=90)
    assert r["badge"] == "safe"
    assert r["score"] == 85  # min(85, 90)


def test_no_pool_uses_shield_only():
    r = sentinel_lite(shield_verdict={"grade": "B"})
    assert r["badge"] == "caution"
    assert r["score"] == 70


def test_low_score_gets_risky():
    r = sentinel_lite(shield_verdict={"grade": "F"}, pool_sentinel=30)
    assert r["badge"] == "risky"
    assert r["score"] == 10


def test_no_data_returns_neutral():
    r = sentinel_lite()
    assert r["score"] == 50
    assert r["badge"] == "caution"
