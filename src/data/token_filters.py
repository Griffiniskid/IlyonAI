"""
Whale-feed alpha filter.

The smart-money feed is only useful when the tokens being traded are ones where
our analysis actually produces alpha — i.e., new/low-cap Solana tokens whose
price moves on flow. Bridged majors (BTC, ETH, XRP, XMR, TRX, DOGE, …),
stablecoins (USDC, USDT, USDH, PYUSD, DAI, …) and SOL liquid-staking tokens
(mSOL, jitoSOL, jupSOL, INF, …) add noise without signal, so we reject them
before they reach the DB.

Two layers of filter:

1. **Mint-level** — exact match against a curated set of Solana mint addresses.
   Catches known majors/LSTs/stables even before DexScreener metadata resolves.
2. **Symbol-level** — regex match against the resolved DexScreener symbol.
   Catches wrapped variants from any bridge (sollet/portal/wormhole/allbridge)
   and any new stablecoin that appears on mainnet. Applied post-metadata.

Keep this list tight — over-matching drops genuine memecoins.
"""

from __future__ import annotations

import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Mint-level exclusions (Solana SPL mint addresses)
# ─────────────────────────────────────────────────────────────────────────────

# Stablecoins (USDC/USDT already live as STABLECOIN_MINTS in solana_log_parser)
_STABLECOIN_MINTS = {
    # Core
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    # Others in common circulation on Solana
    "USDH1SM1ojwWUga67PGrgFWUHibbjqMvuMaDkRJTgkX",   # USDH (Hubble)
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo",  # PYUSD (PayPal)
    "9zNQRsGLjNKwCUU5Gq5LR8beUCPzQMVMqKAi3SSZh7TY",  # FDUSD
    "USDSwr9ApdHk5bvJKMjzff41FfuX8bSxdKcR81vTwcA",   # USDS
    "EjmyN6qEC1Tf1JxiG1ae7UTJhUxSwk1TCWNWqxWV4J6o",  # DAI (Portal)
    "7kbnvuGBxxj8AG9qp8Scn56muWGaRaFqxg1FsRp3PaFT",  # UXD
    "A9mUU4qviSctJVPJdBJWkb28deg915LYJKrzQ19ji3FM",  # USDCet (Wormhole)
}

# Wrapped BTC / ETH / XRP / other bridged majors on Solana.
_WRAPPED_MAJOR_MINTS = {
    # BTC variants
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # Wrapped BTC (Portal/Wormhole)
    "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E",  # soBTC (legacy Sollet)
    # ETH variants
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",  # Wrapped ETH (Portal)
    "2FPyTwcZLUg1MDrwsyoP4D6s1tM7hAkHYRjkNb5w6Pxk",  # soETH (Sollet)
    "AJ1W9A9N9dEMdVyoDiam2rV44gnBm2csrPDP7xqcapgX",  # bETH (Portal)
    # Others
    "HZRCwxP2Vq9PCpPXooayhJ2bxTpo5xfpQrwB1svh332p",  # LDO (Lido)
}

# SOL liquid-staking tokens — trading these is treasury/yield activity, not alpha.
_LST_MINTS = {
    "So11111111111111111111111111111111111111112",   # WSOL
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",   # mSOL (Marinade)
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",  # stSOL (Lido)
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",   # bSOL (BlazeStake)
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",  # jitoSOL (Jito)
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",   # jupSOL (Jupiter)
    "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm",  # INF (Sanctum)
    "he1iusmfkpAdwvxLNGV8Y1iSbj4rUy6yMhEA3fotn9A",   # hSOL
    "LSTxxxnJzKDFSLr4dUkPcmCf5VyryEqzPLz5j4bpxFp",   # LST (Sanctum wrapped)
    "CgnTSoL3DgY9SFHxcLj6CgCgKKoTBr6tp4CPAEWy25DE",  # cgntSOL
    "5Mh5XuGcT7rWRHhX8BjJUcDkgb6Fw8ofvPWkFHzwevBf",  # laineSOL (approx)
}

EXCLUDED_MINTS: frozenset[str] = frozenset(_STABLECOIN_MINTS | _WRAPPED_MAJOR_MINTS | _LST_MINTS)


# ─────────────────────────────────────────────────────────────────────────────
# Symbol-level exclusion regex
# ─────────────────────────────────────────────────────────────────────────────

# Major ticker symbols — bridged/wrapped variants of these are not alpha.
_MAJOR_TICKERS = (
    r"BTC|ETH|XRP|XMR|DOGE|SHIB|TRX|ADA|LINK|LTC|DOT|AVAX|MATIC|"
    r"UNI|BNB|BCH|ATOM|NEAR|APT|SUI|FIL|ICP|XLM|ALGO|ETC|VET|"
    r"HBAR|ARB|OP|IMX|INJ|TIA|KAS|RUNE|FTM|FTT|LUNA|LUNC|UST"
)

# Common wrapper prefixes across Solana bridges (Wormhole "w"/"portal",
# Sollet "so", Allbridge "ab", Coinbase "cb", plus LST namespace prefixes
# for SOL-denominated staking tokens).
_WRAPPER_PREFIXES = r"w|so|portal|ab|cb|ms|st|b|jito|jup|hL?|lst|scn|laine|cgnt"

# Stablecoin patterns: anything that starts or ends with USD, plus DAI & EUR/GBP/JPY proxies.
_STABLE_PATTERN = (
    r"^(USDC|USDT|USDH|USDR|USDS|USDY|UXD|PYUSD|FDUSD|TUSD|DAI|"
    r"EURC|EURS|GBPC|JPYC|XSGD|USDCet|sUSD|crvUSD|AUSD)$"
    r"|^USD[A-Z0-9]{0,4}$"
    r"|[A-Z0-9]{0,4}USD$"
)

# LSTs by symbol (covers new SOL-staking issuers we might not have mint addresses for).
_LST_PATTERN = (
    r"^(SOL|WSOL|mSOL|stSOL|bSOL|jitoSOL|jupSOL|INF|hSOL|lstSOL|"
    r"scnSOL|laineSOL|cgntSOL|pSOL|eSOL|aeroSOL)$"
)

# Wrapped major: optional wrapper prefix + major ticker, anchored.
_WRAPPED_MAJOR_PATTERN = rf"^({_WRAPPER_PREFIXES})?({_MAJOR_TICKERS})$"

EXCLUDED_SYMBOL_RE = re.compile(
    rf"(?:{_STABLE_PATTERN})|(?:{_LST_PATTERN})|(?:{_WRAPPED_MAJOR_PATTERN})",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def is_excluded_mint(mint: Optional[str]) -> bool:
    """True iff the mint address is on the curated block list."""
    if not mint:
        return False
    return mint in EXCLUDED_MINTS


def is_excluded_symbol(symbol: Optional[str]) -> bool:
    """True iff the resolved token symbol matches a boring-major pattern.

    Returns False for `None`, empty string, and '???' (the placeholder) —
    those get a pass through this layer; mint-level filtering handles them.
    """
    if not symbol or symbol == "???":
        return False
    return bool(EXCLUDED_SYMBOL_RE.match(symbol.strip()))


def is_alpha_token(mint: Optional[str], symbol: Optional[str]) -> bool:
    """Convenience: False if either filter blocks the token, True otherwise."""
    return not is_excluded_mint(mint) and not is_excluded_symbol(symbol)
