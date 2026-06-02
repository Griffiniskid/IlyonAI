"""pool_deeplink strategy: link to the protocol's OWN app (always reachable),
and let the card's copyable POOL ADDRESS take the user to the exact pool.

This replaced the old per-pool deep-link forms (V3 add with fee/range etc.),
which proved unreliable across the long tail — "Invalid pair" / 404 / wrong
fee tier. So for any protocol we have an app URL for, pool_deeplink returns
that app URL. Protocols with no mapped app URL fall through to the per-chain
exact handling (e.g. Solana Orca pools page) and then the generic fallback
(DexScreener exact pair → DefiLlama exact pool).
"""
from src.agent.pool_deeplinks import pool_deeplink


def test_curve_links_to_curve_app():
    url = pool_deeplink(protocol="curve-dex", chain="ethereum", pool_id="abc",
                        pool_address="0xPOOL", symbol="DAI-USDC-USDT", underlying_tokens=[])
    assert "curve.fi" in url


def test_uniswap_v3_links_to_uniswap_app():
    url = pool_deeplink(protocol="uniswap-v3", chain="base", pool_id="abc",
                        pool_address="0xP", symbol="USDC-WETH", underlying_tokens=[])
    assert "app.uniswap.org" in url


def test_raydium_links_to_raydium_app():
    url = pool_deeplink(protocol="raydium-amm", chain="solana", pool_id="abc",
                        pool_address="POOLADDR", symbol="SOL-USDC", underlying_tokens=["A", "B"])
    assert "raydium.io" in url


def test_raydium_links_to_raydium_app_without_address():
    url = pool_deeplink(protocol="raydium-amm", chain="solana", pool_id="abc",
                        pool_address=None, symbol="SOL-USDC", underlying_tokens=["MintA", "MintB"])
    assert "raydium.io" in url


def test_orca_exact_pool():
    # Orca has no mapped slug here ("orca-dex"), so it falls through to the
    # Solana branch and lands on the exact whirlpool page by address.
    url = pool_deeplink(protocol="orca-dex", chain="solana", pool_id="abc",
                        pool_address="WHIRL", symbol="SOL-USDC", underlying_tokens=[])
    assert "orca.so/pools/WHIRL" in url


def test_aerodrome_links_to_aerodrome_app():
    url = pool_deeplink(protocol="aerodrome-v1", chain="base", pool_id="abc",
                        pool_address="0xAERO", symbol="USDC-AERO", underlying_tokens=[])
    assert "aerodrome.finance" in url


def test_fallback_is_defillama_exact_pool():
    url = pool_deeplink(protocol="unknown-proto", chain="ethereum", pool_id="uuid-123",
                        pool_address=None, symbol="X-Y", underlying_tokens=[])
    assert url == "https://defillama.com/yields/pool/uuid-123"


def test_solana_unknown_falls_back_to_defillama():
    url = pool_deeplink(protocol="mystery", chain="solana", pool_id="uuid-9",
                        pool_address=None, symbol="A-B", underlying_tokens=[])
    assert url == "https://defillama.com/yields/pool/uuid-9"


def test_sushi_links_to_sushi_app():
    url = pool_deeplink(protocol="sushiswap", chain="base", pool_id=None,
                        pool_address="0x" + "a" * 40, symbol="USDC-WETH",
                        underlying_tokens=[])
    assert "sushi.com" in url


def test_never_defillama_yields_landing_and_never_empty():
    # Every exit must be a usable URL — never empty, never the DefiLlama
    # /yields landing page (a bare list with no pool selected).
    cases = [
        dict(protocol="curve-dex", chain="ethereum", pool_id=None, pool_address=None, symbol="3pool", underlying_tokens=[]),
        dict(protocol="uniswap-v3", chain="ethereum", pool_id=None, pool_address=None, symbol="USDC-WETH", underlying_tokens=[]),
        dict(protocol="mystery", chain="ethereum", pool_id=None, pool_address=None, symbol="FOO-BAR", underlying_tokens=[]),
        dict(protocol="raydium-amm", chain="solana", pool_id=None, pool_address=None, symbol="SOL-USDC", underlying_tokens=[]),
    ]
    for kw in cases:
        url = pool_deeplink(**kw)
        assert url, kw
        assert url.rstrip("/") != "https://defillama.com/yields", kw


def test_uniswap_v4_links_to_uniswap_app():
    # A V4 pool links to the Uniswap app (the V4→V3 substitution bug lived in
    # the address RESOLVER, tested separately, not here).
    url = pool_deeplink(protocol="uniswap-v4", chain="base", pool_id=None,
                        pool_address="0x" + "c" * 40, symbol="USDC-WETH",
                        underlying_tokens=[])
    assert "app.uniswap.org" in url
