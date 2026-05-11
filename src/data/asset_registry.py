"""Canonical (chain, symbol) → (address, decimals) registry for EVM tokens.

Used by adapters that need to translate a user-typed symbol like "USDC" or
"WETH" into the on-chain contract. Falls back to ERC20 on-chain decimals() +
Coingecko contract lookup for unknowns (`resolve_any_evm_token`).

Native gas tokens use the canonical 0xEee...EEeE placeholder so Enso and other
routers accept them.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

NATIVE_PLACEHOLDER = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

# Verified mainnet contract addresses + decimals.
# Format: (chain, symbol) -> (address_lower, decimals)
_REGISTRY: dict[tuple[str, str], tuple[str, int]] = {
    # --- Ethereum ---
    ("ethereum", "ETH"): (NATIVE_PLACEHOLDER, 18),
    ("ethereum", "WETH"): ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
    ("ethereum", "USDC"): ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    ("ethereum", "USDT"): ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    ("ethereum", "DAI"): ("0x6b175474e89094c44da98b954eedeac495271d0f", 18),
    ("ethereum", "WBTC"): ("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 8),
    ("ethereum", "STETH"): ("0xae7ab96520de3a18e5e111b5eaab095312d7fe84", 18),
    ("ethereum", "WSTETH"): ("0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0", 18),
    ("ethereum", "RETH"): ("0xae78736cd615f374d3085123a210448e74fc6393", 18),
    ("ethereum", "FRXETH"): ("0x5e8422345238f34275888049021821e8e08caa1f", 18),
    ("ethereum", "SFRXETH"): ("0xac3e018457b222d93114458476f3e3416abbe38f", 18),
    ("ethereum", "CBETH"): ("0xbe9895146f7af43049ca1c1ae358b0541ea49704", 18),
    ("ethereum", "OETH"): ("0x856c4efb76c1d1ae02e20ceb03a2a6a08b0b8dc3", 18),
    ("ethereum", "EETH"): ("0x35fa164735182de50811e8e2e824cfb9b6118ac2", 18),
    ("ethereum", "WEETH"): ("0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee", 18),
    ("ethereum", "USDE"): ("0x4c9edd5852cd905f086c759e8383e09bff1e68b3", 18),
    ("ethereum", "SUSDE"): ("0x9d39a5de30e57443bff2a8307a4256c8797a3497", 18),
    ("ethereum", "SUSDS"): ("0xa3931d71877c0e7a3148cb7eb4463524fec27fbd", 18),
    ("ethereum", "USDS"): ("0xdc035d45d973e3ec169d2276ddab16f1e407384f", 18),
    ("ethereum", "FRAX"): ("0x853d955acef822db058eb8505911ed77f175b99e", 18),
    ("ethereum", "CRV"): ("0xd533a949740bb3306d119cc777fa900ba034cd52", 18),
    ("ethereum", "CVX"): ("0x4e3fbd56cd56c3e72c1403e103b45db9da5b9d2b", 18),
    ("ethereum", "LINK"): ("0x514910771af9ca656af840dff83e8264ecf986ca", 18),
    ("ethereum", "MKR"): ("0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2", 18),
    ("ethereum", "AAVE"): ("0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9", 18),
    ("ethereum", "SDAI"): ("0x83f20f44975d03b1b09e64809b757c47f942beea", 18),
    # --- Base ---
    ("base", "ETH"): (NATIVE_PLACEHOLDER, 18),
    ("base", "WETH"): ("0x4200000000000000000000000000000000000006", 18),
    ("base", "USDC"): ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
    ("base", "USDBC"): ("0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca", 6),
    ("base", "DAI"): ("0x50c5725949a6f0c72e6c4a641f24049a917db0cb", 18),
    ("base", "CBETH"): ("0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22", 18),
    ("base", "WSTETH"): ("0xc1cba3fcea344f92d9239c08c0568f6f2f0ee452", 18),
    ("base", "AERO"): ("0x940181a94a35a4569e4529a3cdfb74e38fd98631", 18),
    ("base", "MORPHO"): ("0xbaa5cc21fd487b8fcc2f632f3f4e8d37262a0842", 18),
    ("base", "EZETH"): ("0x2416092f143378750bb29b79ed961ab195cceea5", 18),
    # --- Arbitrum ---
    ("arbitrum", "ETH"): (NATIVE_PLACEHOLDER, 18),
    ("arbitrum", "WETH"): ("0x82af49447d8a07e3bd95bd0d56f35241523fbab1", 18),
    ("arbitrum", "USDC"): ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", 6),
    ("arbitrum", "USDC.E"): ("0xff970a61a04b1ca14834a43f5de4533ebddb5cc8", 6),
    ("arbitrum", "USDT"): ("0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", 6),
    ("arbitrum", "DAI"): ("0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", 18),
    ("arbitrum", "WBTC"): ("0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f", 8),
    ("arbitrum", "ARB"): ("0x912ce59144191c1204e64559fe8253a0e49e6548", 18),
    ("arbitrum", "WSTETH"): ("0x5979d7b546e38e414f7e9822514be443a4800529", 18),
    ("arbitrum", "GMX"): ("0xfc5a1a6eb076a2c7ad06ed22c90d7e710e35ad0a", 18),
    # --- Optimism ---
    ("optimism", "ETH"): (NATIVE_PLACEHOLDER, 18),
    ("optimism", "WETH"): ("0x4200000000000000000000000000000000000006", 18),
    ("optimism", "USDC"): ("0x0b2c639c533813f4aa9d7837caf62653d097ff85", 6),
    ("optimism", "USDC.E"): ("0x7f5c764cbc14f9669b88837ca1490cca17c31607", 6),
    ("optimism", "USDT"): ("0x94b008aa00579c1307b0ef2c499ad98a8ce58e58", 6),
    ("optimism", "DAI"): ("0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", 18),
    ("optimism", "OP"): ("0x4200000000000000000000000000000000000042", 18),
    ("optimism", "WSTETH"): ("0x1f32b1c2345538c0c6f582fcb022739c4a194ebb", 18),
    ("optimism", "RETH"): ("0x9bcef72be871e61ed4fbbc7630889bee758eb81d", 18),
    # --- Polygon ---
    ("polygon", "MATIC"): (NATIVE_PLACEHOLDER, 18),
    ("polygon", "POL"): (NATIVE_PLACEHOLDER, 18),
    ("polygon", "WMATIC"): ("0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270", 18),
    ("polygon", "WETH"): ("0x7ceb23fd6bc0add59e62ac25578270cff1b9f619", 18),
    ("polygon", "USDC"): ("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", 6),
    ("polygon", "USDC.E"): ("0x2791bca1f2de4661ed88a30c99a7a9449aa84174", 6),
    ("polygon", "USDT"): ("0xc2132d05d31c914a87c6611c10748aeb04b58e8f", 6),
    ("polygon", "DAI"): ("0x8f3cf7ad23cd3cadbd9735aff958023239c6a063", 18),
    ("polygon", "WBTC"): ("0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6", 8),
    ("polygon", "MATICX"): ("0xfa68fb4628dff1028cfec22b4162fccd0d45efb6", 18),
    # --- Avalanche ---
    ("avalanche", "AVAX"): (NATIVE_PLACEHOLDER, 18),
    ("avalanche", "WAVAX"): ("0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7", 18),
    ("avalanche", "USDC"): ("0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e", 6),
    ("avalanche", "USDT"): ("0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7", 6),
    ("avalanche", "DAI.E"): ("0xd586e7f844cea2f87f50152665bcbc2c279d8d70", 18),
    ("avalanche", "WETH.E"): ("0x49d5c2bdffac6ce2bfdb6640f4f80f226bc10bab", 18),
    ("avalanche", "SAVAX"): ("0x2b2c81e08f1af8835a78bb2a90ae924ace0ea4be", 18),
    # --- BSC ---
    ("bsc", "BNB"): (NATIVE_PLACEHOLDER, 18),
    ("bsc", "WBNB"): ("0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", 18),
    ("bsc", "USDC"): ("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", 18),
    ("bsc", "USDT"): ("0x55d398326f99059ff775485246999027b3197955", 18),
    ("bsc", "BUSD"): ("0xe9e7cea3dedca5984780bafc599bd69add087d56", 18),
    ("bsc", "BTCB"): ("0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c", 18),
    ("bsc", "ETH"): ("0x2170ed0880ac9a755fd29b2688956bd959f933f8", 18),
}


def lookup_symbol(chain: str, symbol: str) -> tuple[str, int] | None:
    """Direct registry lookup. Returns (address, decimals) or None."""
    return _REGISTRY.get((chain.lower(), symbol.upper()))


# --- On-chain ERC20 metadata fallback ---

_RPC_BY_CHAIN: dict[str, str] = {
    "ethereum": "https://eth.llamarpc.com",
    "polygon": "https://polygon-rpc.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io",
    "base": "https://mainnet.base.org",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
    "bsc": "https://bsc-dataseed.binance.org",
}

# Backup RPC pool — tried in order when the primary returns rate-limit /
# 5xx / empty. Each entry is a public, no-auth endpoint that supports
# eth_call. Order matters: the most stable ones first.
RPC_FALLBACKS: dict[str, list[str]] = {
    "ethereum": [
        "https://eth.llamarpc.com",
        "https://ethereum-rpc.publicnode.com",
        "https://cloudflare-eth.com",
        "https://rpc.ankr.com/eth",
        "https://1rpc.io/eth",
    ],
    "base": [
        "https://mainnet.base.org",
        "https://base.publicnode.com",
        "https://1rpc.io/base",
        "https://base-rpc.publicnode.com",
    ],
    "arbitrum": [
        "https://arb1.arbitrum.io/rpc",
        "https://arbitrum.llamarpc.com",
        "https://arbitrum-one-rpc.publicnode.com",
        "https://1rpc.io/arb",
    ],
    "optimism": [
        "https://mainnet.optimism.io",
        "https://optimism-rpc.publicnode.com",
        "https://1rpc.io/op",
        "https://op-pokt.nodies.app",
    ],
    "polygon": [
        "https://polygon-rpc.com",
        "https://polygon-bor-rpc.publicnode.com",
        "https://1rpc.io/matic",
        "https://rpc.ankr.com/polygon",
    ],
    "bsc": [
        "https://bsc-dataseed.binance.org",
        "https://bsc-rpc.publicnode.com",
        "https://1rpc.io/bnb",
        "https://bsc-dataseed1.defibit.io",
    ],
    "avalanche": [
        "https://api.avax.network/ext/bc/C/rpc",
        "https://avalanche-c-chain-rpc.publicnode.com",
        "https://1rpc.io/avax/c",
    ],
}

# selector for decimals() = 0x313ce567, symbol() = 0x95d89b41
_DECIMALS_SELECTOR = "0x313ce567"
_SYMBOL_SELECTOR = "0x95d89b41"


async def _eth_call(rpc: str, to: str, data: str) -> str | None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.post(rpc, json=payload)
            r.raise_for_status()
            return r.json().get("result")
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def _decode_string(hex_data: str) -> str | None:
    if not hex_data or hex_data == "0x":
        return None
    h = hex_data[2:] if hex_data.startswith("0x") else hex_data
    # Standard ABI string: offset(32) + length(32) + bytes
    if len(h) >= 128:
        try:
            length = int(h[64:128], 16)
            raw = h[128 : 128 + length * 2]
            return bytes.fromhex(raw).decode("utf-8", errors="replace").strip("\x00")
        except (ValueError, UnicodeDecodeError):
            pass
    # bytes32 fallback (older tokens)
    try:
        return bytes.fromhex(h[:64]).decode("utf-8", errors="replace").rstrip("\x00").strip()
    except (ValueError, UnicodeDecodeError):
        return None


_onchain_cache: dict[tuple[str, str], tuple[float, tuple[str, int] | None]] = {}
_onchain_lock = asyncio.Lock()
_ONCHAIN_TTL_S = 86400.0


async def resolve_any_evm_token(chain: str, addr_or_symbol: str) -> tuple[str, int] | None:
    """Resolve symbol or address to (address_lower, decimals).

    Order: registry → on-chain decimals() if address-like.
    """
    s = addr_or_symbol.strip()
    chain_norm = chain.lower()
    if s.upper() in {sym for c, sym in _REGISTRY.keys() if c == chain_norm}:
        return _REGISTRY[(chain_norm, s.upper())]
    if s.lower().startswith("0x") and len(s) == 42:
        addr = s.lower()
        key = (chain_norm, addr)
        now = time.monotonic()
        async with _onchain_lock:
            hit = _onchain_cache.get(key)
            if hit and (now - hit[0]) < _ONCHAIN_TTL_S:
                return hit[1]
        rpc = _RPC_BY_CHAIN.get(chain_norm)
        if not rpc:
            return None
        dec_hex = await _eth_call(rpc, addr, _DECIMALS_SELECTOR)
        if not dec_hex or dec_hex == "0x":
            async with _onchain_lock:
                _onchain_cache[key] = (now, None)
            return None
        try:
            decimals = int(dec_hex, 16)
        except ValueError:
            async with _onchain_lock:
                _onchain_cache[key] = (now, None)
            return None
        result = (addr, decimals)
        async with _onchain_lock:
            _onchain_cache[key] = (now, result)
        return result
    return None
