import asyncio

from src.agent import pool_address_authoritative as paa


def test_fee_bps_from_meta_valid_tiers():
    assert paa.fee_bps_from_meta("0.05%") == 500
    assert paa.fee_bps_from_meta("0.3%") == 3000
    assert paa.fee_bps_from_meta("1%") == 10000
    assert paa.fee_bps_from_meta("0.01%") == 100


def test_fee_bps_from_meta_rejects_non_tiers():
    assert paa.fee_bps_from_meta(None) is None
    assert paa.fee_bps_from_meta("stable") is None
    assert paa.fee_bps_from_meta("0.07%") is None  # not a real tier


def test_factory_key_v4_not_remapped_to_v3():
    # V4 has no per-pool factory contract; mapping it to v3 mislinks to an
    # unrelated V3 pool. It must stay 'uniswap-v4' so _FACTORY misses and the
    # caller defers to DexScreener.
    assert paa._factory_key("uniswap-v4") == "uniswap-v4"
    assert ("uniswap-v4", "ethereum") not in paa._FACTORY
    # Bare 'uniswap' still resolves as v3 (the common case).
    assert paa._factory_key("uniswap") == "uniswap-v3"


def test_v3_factory_returns_none_without_fee_tier():
    # Unknown tier → return None (defer to DexScreener), never guess a tier.
    out = asyncio.run(
        paa._evm_factory_pool(None, "ethereum", "uniswap-v3",
                              ["0x" + "a" * 40, "0x" + "b" * 40], fee_bps=None)
    )
    assert out is None


def test_400_not_a_valid_tier():
    assert 400 not in paa._V3_FEES
    assert {100, 500, 2500, 3000, 10000} == set(paa._V3_FEES)
