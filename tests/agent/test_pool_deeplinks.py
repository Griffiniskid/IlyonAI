from src.agent.pool_deeplinks import pool_deeplink


def test_curve_exact_pool():
    url = pool_deeplink(protocol="curve-dex", chain="ethereum", pool_id="abc",
                        pool_address="0xPOOL", symbol="DAI-USDC-USDT", underlying_tokens=[])
    assert "curve.fi" in url and "0xPOOL" in url and "deposit" in url


def test_uniswap_v3_exact_pool():
    url = pool_deeplink(protocol="uniswap-v3", chain="base", pool_id="abc",
                        pool_address="0xP", symbol="USDC-WETH", underlying_tokens=[])
    assert "app.uniswap.org" in url and "0xP" in url


def test_raydium_by_pool_address():
    url = pool_deeplink(protocol="raydium-amm", chain="solana", pool_id="abc",
                        pool_address="POOLADDR", symbol="SOL-USDC", underlying_tokens=["A", "B"])
    assert "raydium.io" in url and "POOLADDR" in url


def test_raydium_by_mints_when_no_address():
    url = pool_deeplink(protocol="raydium-amm", chain="solana", pool_id="abc",
                        pool_address=None, symbol="SOL-USDC", underlying_tokens=["MintA", "MintB"])
    assert "raydium.io" in url and "MintA" in url and "MintB" in url


def test_orca_exact_pool():
    url = pool_deeplink(protocol="orca-dex", chain="solana", pool_id="abc",
                        pool_address="WHIRL", symbol="SOL-USDC", underlying_tokens=[])
    assert "orca.so/pools/WHIRL" in url


def test_aerodrome_exact_pool():
    url = pool_deeplink(protocol="aerodrome-v1", chain="base", pool_id="abc",
                        pool_address="0xAERO", symbol="USDC-AERO", underlying_tokens=[])
    assert "aerodrome.finance" in url and "0xAERO" in url


def test_fallback_is_defillama_exact_pool():
    url = pool_deeplink(protocol="unknown-proto", chain="ethereum", pool_id="uuid-123",
                        pool_address=None, symbol="X-Y", underlying_tokens=[])
    assert url == "https://defillama.com/yields/pool/uuid-123"


def test_solana_unknown_falls_back_to_defillama():
    url = pool_deeplink(protocol="mystery", chain="solana", pool_id="uuid-9",
                        pool_address=None, symbol="A-B", underlying_tokens=[])
    assert url == "https://defillama.com/yields/pool/uuid-9"
