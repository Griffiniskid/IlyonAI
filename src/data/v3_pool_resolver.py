"""Resolve Uniswap V3 / PancakeSwap V3 / Aerodrome Slipstream pool address
via `factory.getPool(token0, token1, fee)` and read pool state from slot0().

Cached in-process for 5 minutes (state moves with every swap so we keep it
fresh enough for range / APR math).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from src.data.asset_registry import NATIVE_PLACEHOLDER, RPC_FALLBACKS, _RPC_BY_CHAIN

# selector("getPool(address,address,uint24)") = 0x1698ee82
_GET_POOL_SEL = "0x1698ee82"
# selector("slot0()") = 0x3850c7bd
_SLOT0_SEL = "0x3850c7bd"
# selector("tickSpacing()") = 0xd0c93a7c
_TICK_SPACING_SEL = "0xd0c93a7c"
# selector("liquidity()") = 0x1a686502
_LIQUIDITY_SEL = "0x1a686502"
# selector("fee()") = 0xddca3f43
_FEE_SEL = "0xddca3f43"
# selector("token0()") = 0x0dfe1681
_TOKEN0_SEL = "0x0dfe1681"
# selector("token1()") = 0xd21220a7
_TOKEN1_SEL = "0xd21220a7"


# Factory + NonfungiblePositionManager per (chain, protocol).
V3_FACTORIES: dict[tuple[str, str], dict[str, str]] = {
    ("ethereum", "uniswap-v3"): {
        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "nfp_manager": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    },
    ("polygon", "uniswap-v3"): {
        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "nfp_manager": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    },
    ("arbitrum", "uniswap-v3"): {
        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "nfp_manager": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    },
    ("optimism", "uniswap-v3"): {
        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "nfp_manager": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    },
    ("base", "uniswap-v3"): {
        "factory": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
        "nfp_manager": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
    },
    ("bsc", "uniswap-v3"): {
        "factory": "0xdB1d10011AD0Ff90774D0C6Bb92e5C5c8b4461F7",
        "nfp_manager": "0x7b8A01B39D58278b5DE7e48c8449c9f4F5170613",
    },
    ("avalanche", "uniswap-v3"): {
        "factory": "0x740b1c1de25031C31FF4fC9A62f554A55cdC1baD",
        "nfp_manager": "0x655C406EBFa14EE2006250925e54ec43AD184f8B",
    },
    ("bsc", "pancakeswap-v3"): {
        "factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
        "nfp_manager": "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364",
    },
    ("ethereum", "pancakeswap-v3"): {
        "factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
        "nfp_manager": "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364",
    },
    ("base", "aerodrome-slipstream"): {
        "factory": "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A",
        "nfp_manager": "0x827922686190790b37229fd06084350E74485b72",
    },
}

# Default tick spacing by fee tier (Uniswap V3 + PancakeSwap V3).
FEE_TIER_TICK_SPACING: dict[int, int] = {
    100: 1,    # 0.01%
    500: 10,   # 0.05%
    3000: 60,  # 0.30%
    10000: 200,  # 1.00%
}


@dataclass(frozen=True)
class V3PoolState:
    chain: str
    protocol: str
    pool_address: str
    factory: str
    nfp_manager: str
    token0: str
    token1: str
    fee_bps: int
    tick_spacing: int
    sqrt_price_x96: int
    tick: int
    liquidity: int


def _pad32(hex_str: str) -> str:
    s = hex_str.lower()
    if s.startswith("0x"):
        s = s[2:]
    return s.rjust(64, "0")


def _encode_address(addr: str) -> str:
    return _pad32(addr)


def _encode_uint(v: int) -> str:
    return _pad32(format(v, "x"))


def _decode_uint(hex_data: str, offset: int = 0, size: int = 64) -> int:
    h = hex_data[2:] if hex_data.startswith("0x") else hex_data
    return int(h[offset : offset + size], 16) if h[offset : offset + size] else 0


def _decode_int24(hex_data: str, offset: int = 64) -> int:
    """ABI int24 is padded to 32 bytes with sign extension (1...1 for negative).
    The raw 256-bit value can be 2^256 - n for negative ticks. Detect via top
    bit at the 256-bit level and convert back to a signed Python int."""
    h = hex_data[2:] if hex_data.startswith("0x") else hex_data
    raw = int(h[offset : offset + 64], 16)
    if raw >= 2**255:
        return raw - 2**256
    return raw


def _decode_address(hex_data: str, offset: int = 0) -> str:
    h = hex_data[2:] if hex_data.startswith("0x") else hex_data
    return "0x" + h[offset + 24 : offset + 64]


_cache: dict[tuple[str, str, str, str, int], tuple[float, V3PoolState | None]] = {}
_cache_lock = asyncio.Lock()
_TTL_S = 300.0  # 5 min


async def _eth_call_with_fallback(chain: str, to: str, data: str) -> str | None:
    """Try every RPC in the fallback list; return first non-empty result."""
    rpcs = RPC_FALLBACKS.get(chain) or [_RPC_BY_CHAIN.get(chain) or ""]
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }
    last_err: Exception | None = None
    for rpc in rpcs:
        if not rpc:
            continue
        try:
            async with httpx.AsyncClient(timeout=8) as cli:
                r = await cli.post(rpc, json=payload)
                if r.status_code == 429 or r.status_code >= 500:
                    continue
                r.raise_for_status()
                body = r.json()
                if "error" in body:
                    continue
                result = body.get("result")
                if result and result != "0x":
                    return result
                if result == "0x":
                    return result
        except (httpx.HTTPError, ValueError, KeyError) as e:
            last_err = e
            continue
    return None


async def _eth_call(rpc: str, to: str, data: str) -> str | None:
    """Legacy single-RPC path kept for compatibility with asset_registry."""
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


async def resolve_v3_pool(
    *,
    chain: str,
    protocol: str,
    token_a: str,
    token_b: str,
    fee_bps: int,
) -> V3PoolState | None:
    """Resolve V3 pool address + read live state.

    `token_a` / `token_b` are user-supplied (may need to be sorted as token0 <
    token1 lexicographically per V3 spec). Returns None if pool doesn't exist.
    """
    chain_norm = chain.lower()
    proto_norm = protocol.lower()
    cfg = V3_FACTORIES.get((chain_norm, proto_norm))
    if cfg is None:
        return None

    a = token_a.lower()
    b = token_b.lower()
    if a == NATIVE_PLACEHOLDER:
        # V3 needs WETH for ETH
        return None  # caller should wrap to WETH first
    if int(a, 16) > int(b, 16):
        a, b = b, a
    token0_addr, token1_addr = a, b

    cache_key = (chain_norm, proto_norm, token0_addr, token1_addr, fee_bps)
    now = time.monotonic()
    async with _cache_lock:
        hit = _cache.get(cache_key)
        if hit and (now - hit[0]) < _TTL_S:
            return hit[1]

    call_data = (
        _GET_POOL_SEL
        + _encode_address(token0_addr)
        + _encode_address(token1_addr)
        + _encode_uint(fee_bps)
    )
    pool_hex = await _eth_call_with_fallback(chain_norm, cfg["factory"], call_data)
    if not pool_hex or pool_hex == "0x" or int(pool_hex, 16) == 0:
        async with _cache_lock:
            _cache[cache_key] = (now, None)
        return None
    pool_addr = "0x" + pool_hex[-40:]
    if int(pool_addr, 16) == 0:
        async with _cache_lock:
            _cache[cache_key] = (now, None)
        return None

    # Read slot0 + tickSpacing + liquidity in parallel
    slot0_task = _eth_call_with_fallback(chain_norm, pool_addr, _SLOT0_SEL)
    tick_spacing_task = _eth_call_with_fallback(chain_norm, pool_addr, _TICK_SPACING_SEL)
    liquidity_task = _eth_call_with_fallback(chain_norm, pool_addr, _LIQUIDITY_SEL)
    slot0_hex, ts_hex, liq_hex = await asyncio.gather(
        slot0_task, tick_spacing_task, liquidity_task
    )
    if not slot0_hex:
        async with _cache_lock:
            _cache[cache_key] = (now, None)
        return None

    # slot0 layout: sqrtPriceX96 (160-bit), tick (int24), observationIndex (uint16),
    # observationCardinality (uint16), observationCardinalityNext (uint16),
    # feeProtocol (uint8), unlocked (bool). ABI pads each to 32 bytes.
    sqrt_price_x96 = _decode_uint(slot0_hex, offset=0)
    tick = _decode_int24(slot0_hex, offset=64)
    if ts_hex and ts_hex != "0x":
        tick_spacing = _decode_uint(ts_hex, offset=0)
    else:
        tick_spacing = FEE_TIER_TICK_SPACING.get(fee_bps, 60)
    liquidity = _decode_uint(liq_hex, offset=0) if liq_hex else 0

    state = V3PoolState(
        chain=chain_norm,
        protocol=proto_norm,
        pool_address=pool_addr,
        factory=cfg["factory"],
        nfp_manager=cfg["nfp_manager"],
        token0=token0_addr,
        token1=token1_addr,
        fee_bps=fee_bps,
        tick_spacing=tick_spacing,
        sqrt_price_x96=sqrt_price_x96,
        tick=tick,
        liquidity=liquidity,
    )
    async with _cache_lock:
        _cache[cache_key] = (now, state)
    return state


async def list_fee_tiers_with_pools(
    *, chain: str, protocol: str, token_a: str, token_b: str
) -> list[V3PoolState]:
    """For range-card discovery: probe every standard fee tier and return
    states for the tiers that exist."""
    results = []
    for fee in (100, 500, 3000, 10000):
        st = await resolve_v3_pool(
            chain=chain, protocol=protocol, token_a=token_a, token_b=token_b, fee_bps=fee
        )
        if st is not None:
            results.append(st)
    return results
