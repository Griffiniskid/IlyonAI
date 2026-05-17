"""Centralized entity resolver — V7-015 (spec §3).

Replaces adapter-local helpers (`_resolve_token`, `_resolve_pool`, `_CHAIN_IDS`,
`_TOKENS`, ad-hoc protocol aliasing) with one service that adapters call into.

Design contract:
  * Token resolution returns a `TokenInfo` dataclass with `symbol`, `address`,
    `decimals`, `is_native`, `wrapped_alias`. Handles the WETH↔ETH / WMATIC↔
    MATIC/POL / WBNB↔BNB / WAVAX↔AVAX / WS↔S / WBERA↔BERA / WSOL↔SOL native
    families AND the USDC.e bridged-vs-native disambiguation (Arbitrum +
    Optimism + Polygon). Addresses come from `src.data.asset_registry._REGISTRY`
    — the single source of truth.
  * Protocol resolution returns a canonical lowercase slug. Aliases collapse
    "uniswap"→"uniswap-v3", "aave"→"aave-v3", "comp"→"compound-v3", etc.
  * Pool resolution composes the existing V3 factory probe in
    `src.data.v3_pool_resolver.resolve_v3_pool` for V3 protocols. V2 uses the
    factory's `getPair(token0, token1)` selector against the V2 factory map
    derived from `_V2_ROUTERS` keys (V2 routers are 1:1 with V2 factories on
    every supported chain — the factory is read via `factory()` on the router
    in production but we hard-code the canonical V2 factories here to avoid
    extra RPC).
  * Chain resolution returns a `ChainInfo` dataclass with `chain_id`,
    `chain_name`, `native_token`. Handles "ethereum"↔1, "base"↔8453, plus
    non-EVM "solana" (chain_id=-1, native_token="SOL").

Native↔wrapped semantics:
  Calling `resolve_token("ETH", "ethereum")` returns a TokenInfo whose
  `address` points to WETH (so the value is immediately usable by adapters
  that need an ERC-20 mint address) and whose `is_native=True` flags that
  the user-typed asset was the gas token. `wrapped_alias` carries the
  wrapped symbol ("WETH"). Calling `resolve_token("WETH", "ethereum")`
  returns the same address with `is_native=False`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from src.data.asset_registry import (
    NATIVE_PLACEHOLDER,
    _REGISTRY as _TOKEN_REGISTRY,
    lookup_symbol,
)


# ─── Native↔Wrapped pairing (gas token symbol → wrapped ERC-20 symbol) ──────
# Spec §3 — these are the gas tokens whose wrapped form is the on-chain
# ERC-20 that adapters actually deposit/borrow against. Anything not in
# this map is assumed to already be an ERC-20.
_NATIVE_TO_WRAPPED: dict[tuple[str, str], str] = {
    ("ethereum", "ETH"): "WETH",
    ("base", "ETH"): "WETH",
    ("arbitrum", "ETH"): "WETH",
    ("optimism", "ETH"): "WETH",
    ("linea", "ETH"): "WETH",
    ("scroll", "ETH"): "WETH",
    ("blast", "ETH"): "WETH",
    ("zksync", "ETH"): "WETH",
    ("unichain", "ETH"): "WETH",
    ("polygon", "MATIC"): "WMATIC",
    ("polygon", "POL"): "WMATIC",  # POL is the rebranded MATIC
    ("avalanche", "AVAX"): "WAVAX",
    ("bsc", "BNB"): "WBNB",
    ("sonic", "S"): "WS",
    ("berachain", "BERA"): "WBERA",
    ("mantle", "MNT"): "WMNT",
    ("gnosis", "XDAI"): "WXDAI",
    ("solana", "SOL"): "WSOL",
}

# Reverse map: wrapped → native (used to compute wrapped_alias when caller
# typed the wrapped symbol directly so they still see the native pairing).
_WRAPPED_TO_NATIVE: dict[tuple[str, str], str] = {
    (chain, wrapped): native for (chain, native), wrapped in _NATIVE_TO_WRAPPED.items()
}


# ─── Protocol slug aliasing ─────────────────────────────────────────────────
# Canonical slug → set of accepted aliases. The reverse lookup is built once
# at import time. Anything not in the alias map passes through lower-cased so
# slugs we don't explicitly alias (e.g. "kamino", "marinade", "raydium-clmm")
# remain identity-resolved.
_PROTOCOL_CANONICAL_ALIASES: dict[str, set[str]] = {
    "uniswap-v3": {"uniswap", "univ3", "uniswap3", "uniswapv3"},
    "uniswap-v2": {"univ2", "uniswapv2"},
    "uniswap-v4": {"univ4", "uniswapv4"},
    "aave-v3": {"aave", "aavev3", "aave3"},
    "aave-v2": {"aavev2", "aave2"},
    "compound-v3": {"comp", "compound", "comet", "compoundv3"},
    "compound-v2": {"compoundv2", "comp2"},
    "pancakeswap-v3": {"pancake-v3", "pancakeswapv3", "pcsv3"},
    "pancakeswap-v2": {"pancake-v2", "pancake", "pancakeswap", "pcs"},
    "sushiswap": {"sushi", "sushiswap-v2"},
    "curve": {"curve-dex", "curve-finance", "curve-stable"},
    "balancer": {"balancer-v2", "bal"},
    "pendle-v2": {"pendle"},
    "morpho": {"morpho-blue", "morpho-aave"},
    "lido": {"lido-st"},
    "rocketpool": {"rocket-pool", "rocket"},
    "kamino": {"kamino-lend", "kamino-lending"},
    "marinade": {"marinade-finance"},
    "jito": {"jito-sol"},
    "orca": {"orca-whirlpools", "whirlpool", "whirlpools"},
    "raydium-clmm": {"raydium-clamm", "raydium-v3"},
    "raydium-v2": {"raydium-amm", "raydium-v2-amm"},
    "aerodrome-slipstream": {"aerodrome-cl", "aero-cl"},
    "velodrome-cl": {"velo-cl", "velodrome-slipstream"},
    "kodiak-v3": {"kodiak"},
    "swapx-v4": {"swapx"},
    "ethena": {"ethena-usde"},
}

# Build reverse alias→canonical map at import time.
_PROTOCOL_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in _PROTOCOL_CANONICAL_ALIASES.items():
    _PROTOCOL_ALIAS_TO_CANONICAL[_canonical] = _canonical
    for _a in _aliases:
        _PROTOCOL_ALIAS_TO_CANONICAL[_a] = _canonical


# ─── Chain ID + native gas token map ────────────────────────────────────────
# Single source of truth for chain_name ↔ chain_id ↔ native gas token symbol.
# Non-EVM chains use chain_id=-1 as a sentinel (Solana, etc.).
_CHAIN_INFO: dict[str, tuple[int, str]] = {
    # EVM L1s
    "ethereum": (1, "ETH"),
    "mainnet": (1, "ETH"),
    "bsc": (56, "BNB"),
    "binance": (56, "BNB"),
    "polygon": (137, "MATIC"),
    "avalanche": (43114, "AVAX"),
    "gnosis": (100, "XDAI"),
    # L2s
    "arbitrum": (42161, "ETH"),
    "optimism": (10, "ETH"),
    "base": (8453, "ETH"),
    "linea": (59144, "ETH"),
    "blast": (81457, "ETH"),
    "scroll": (534352, "ETH"),
    "mantle": (5000, "MNT"),
    "zksync": (324, "ETH"),
    "celo": (42220, "CELO"),
    "sonic": (146, "S"),
    "berachain": (80094, "BERA"),
    "unichain": (130, "ETH"),
    # Non-EVM
    "solana": (-1, "SOL"),
}

# Reverse map: chain_id → chain_name (canonical form, prefer first-listed).
_CHAIN_ID_TO_NAME: dict[int, str] = {}
for _name, (_cid, _native) in _CHAIN_INFO.items():
    if _cid not in _CHAIN_ID_TO_NAME:
        _CHAIN_ID_TO_NAME[_cid] = _name


# ─── V2 factory map (chain, canonical-protocol-slug) → factory address ──────
# Hard-coded canonical V2 factories so `resolve_pool` for V2 doesn't have to
# dispatch through the router's `factory()` selector at runtime. Derived from
# the V2 router map in adapters/uniswap_v2.py — each router has a 1:1 factory.
V2_FACTORIES: dict[tuple[str, str], str] = {
    ("ethereum", "uniswap-v2"): "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
    ("ethereum", "sushiswap"): "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac",
    ("bsc", "pancakeswap-v2"): "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73",
    ("polygon", "quickswap"): "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
    ("polygon", "sushiswap"): "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
    ("arbitrum", "sushiswap"): "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
    ("arbitrum", "camelot"): "0x6EcCab422D763aC031210895C81787E87B43A652",
    ("optimism", "sushiswap"): "0xFbc12984689e5f15626Bad03Ad60160Fe98B303C",
    ("base", "sushiswap"): "0x71524B4f93c58fcbF659783284E38825f0622859",
    ("avalanche", "trader-joe-v1"): "0x9Ad6C38BE94206cA50bb0d90783181662f0Cfa10",
    ("avalanche", "sushiswap"): "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
}


@dataclass(frozen=True)
class TokenInfo:
    """Canonical token descriptor returned by `EntityResolver.resolve_token`.

    Fields:
      symbol: canonical UPPER-CASE symbol (e.g. "WETH", "USDC.E")
      address: lower-case checksummed-less hex address (or Solana base58 mint)
      decimals: token decimals
      is_native: True if the user-typed symbol was the gas-token alias (ETH,
        MATIC, POL, BNB, AVAX, S, BERA, MNT, XDAI, SOL). False if they typed
        the wrapped ERC-20 directly.
      wrapped_alias: the wrapped ERC-20 symbol when applicable (always
        populated for the EVM gas-token family — both directions). Empty
        string when the asset has no native↔wrapped pair (e.g. USDC).
    """

    symbol: str
    address: str
    decimals: int
    is_native: bool
    wrapped_alias: str


@dataclass(frozen=True)
class ChainInfo:
    """Canonical chain descriptor returned by `EntityResolver.resolve_chain`."""

    chain_id: int
    chain_name: str
    native_token: str


class EntityResolver:
    """Centralized resolution for tokens, protocols, chains, and pools.

    Stateless except for an internal `_pool_resolver_override` hook used by
    tests to inject a mock for `resolve_pool` without hitting live RPC. Call
    `set_pool_resolver` in test setup to swap.

    Adapters should construct one of these once at module import time (the
    object is cheap — no I/O in __init__) and call its methods instead of
    keeping their own `_TOKENS` / `_resolve_token` helpers.
    """

    def __init__(self) -> None:
        # Override hook for tests — when set, `resolve_pool` calls this
        # callable instead of `src.data.v3_pool_resolver.resolve_v3_pool`
        # and the on-chain V2 `getPair` RPC. Signature must match
        # `resolve_pool` itself (token0, token1, fee_tier, chain, protocol)
        # and return Optional[str].
        self._pool_resolver_override: Optional[
            callable  # type: ignore[type-arg]
        ] = None

    # ─── Token ──────────────────────────────────────────────────────────────

    def resolve_token(self, symbol_or_addr: str, chain: str) -> Optional[TokenInfo]:
        """Resolve `symbol_or_addr` on `chain` to a TokenInfo.

        Accepts either a symbol ("ETH", "WETH", "USDC.E") or a 0x-prefixed
        address. For natives, returns the WRAPPED address (so callers can
        immediately use it in ERC-20 calls) and flags `is_native=True`.
        """
        if not symbol_or_addr or not chain:
            return None
        chain_norm = chain.lower().strip()
        s = symbol_or_addr.strip()

        # ─── Address path (EVM only — Solana addresses are base58, length
        # varies, no 0x prefix). Look up in the per-chain registry.
        if s.lower().startswith("0x") and len(s) == 42:
            addr_l = s.lower()
            for (c, sym), (a, dec) in _TOKEN_REGISTRY.items():
                if c == chain_norm and a == addr_l:
                    # Detect native: registry entries with NATIVE_PLACEHOLDER
                    # represent the gas token. For an address-typed query we
                    # also catch the wrapped form here.
                    is_native = a == NATIVE_PLACEHOLDER
                    wrapped_alias = _NATIVE_TO_WRAPPED.get(
                        (chain_norm, sym), ""
                    ) or _WRAPPED_TO_NATIVE.get((chain_norm, sym), "")
                    return TokenInfo(
                        symbol=sym,
                        address=a,
                        decimals=dec,
                        is_native=is_native,
                        wrapped_alias=wrapped_alias,
                    )
            return None

        sym_upper = s.upper()

        # ─── Solana native (no wrapped ERC-20 family in our registry) ───────
        if chain_norm == "solana":
            if sym_upper in ("SOL", "WSOL"):
                # WSOL mint is the canonical wrapped SOL on Solana.
                return TokenInfo(
                    symbol="WSOL",
                    address="So11111111111111111111111111111111111111112",
                    decimals=9,
                    is_native=(sym_upper == "SOL"),
                    wrapped_alias="WSOL" if sym_upper == "SOL" else "SOL",
                )
            # Common Solana SPLs — keep a minimal table here for now; full
            # SPL list lives in `src.data.solana`.
            _SOLANA_SPLS = {
                "USDC": ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),
                "USDT": ("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", 6),
            }
            if sym_upper in _SOLANA_SPLS:
                addr, dec = _SOLANA_SPLS[sym_upper]
                return TokenInfo(
                    symbol=sym_upper,
                    address=addr,
                    decimals=dec,
                    is_native=False,
                    wrapped_alias="",
                )
            return None

        # ─── EVM native gas-token alias → return wrapped ERC-20 address ────
        if (chain_norm, sym_upper) in _NATIVE_TO_WRAPPED:
            wrapped = _NATIVE_TO_WRAPPED[(chain_norm, sym_upper)]
            wrapped_entry = lookup_symbol(chain_norm, wrapped)
            if wrapped_entry is None:
                # Registry should always have the wrapped form — defensive.
                return None
            wrapped_addr, wrapped_dec = wrapped_entry
            return TokenInfo(
                symbol=wrapped,
                address=wrapped_addr,
                decimals=wrapped_dec,
                is_native=True,
                wrapped_alias=wrapped,
            )

        # ─── EVM wrapped ERC-20 directly (WETH, WBNB, ...) — flag the
        # reverse so callers know there's a native pair. ─────────────────────
        if (chain_norm, sym_upper) in _WRAPPED_TO_NATIVE:
            entry = lookup_symbol(chain_norm, sym_upper)
            if entry is None:
                return None
            addr, dec = entry
            return TokenInfo(
                symbol=sym_upper,
                address=addr,
                decimals=dec,
                is_native=False,
                wrapped_alias=sym_upper,
            )

        # ─── Plain ERC-20 (USDC, USDT, DAI, USDC.e, …). USDC.e on
        # Arbitrum/Optimism/Polygon is distinct from native USDC and the
        # registry already separates the two — just hit it. ─────────────────
        entry = lookup_symbol(chain_norm, sym_upper)
        if entry is not None:
            addr, dec = entry
            return TokenInfo(
                symbol=sym_upper,
                address=addr,
                decimals=dec,
                is_native=False,
                wrapped_alias="",
            )
        return None

    # ─── Protocol ───────────────────────────────────────────────────────────

    def resolve_protocol(self, slug_or_name: str) -> Optional[str]:
        """Resolve a user-typed protocol slug to its canonical form.

        Returns the canonical lowercase slug (e.g. "uniswap-v3", "aave-v3",
        "kamino"). Returns the lower-cased input verbatim if it's not in
        the alias map — that lets adapters resolve protocols we haven't
        explicitly aliased without forcing a registry edit per new protocol.
        """
        if not slug_or_name:
            return None
        s = slug_or_name.strip().lower()
        if not s:
            return None
        return _PROTOCOL_ALIAS_TO_CANONICAL.get(s, s)

    # ─── Chain ──────────────────────────────────────────────────────────────

    def resolve_chain(self, name_or_id: str | int) -> Optional[ChainInfo]:
        """Resolve "ethereum"/"base"/"1"/"8453"/etc. to a ChainInfo.

        Accepts the canonical chain name, a chain-id integer (or its string
        form), and common aliases ("mainnet", "binance"). Returns None for
        unknown chains.
        """
        if name_or_id is None:
            return None
        # Numeric → reverse lookup by chain id.
        if isinstance(name_or_id, int):
            cid = name_or_id
            name = _CHAIN_ID_TO_NAME.get(cid)
            if name is None:
                return None
            _, native = _CHAIN_INFO[name]
            return ChainInfo(chain_id=cid, chain_name=name, native_token=native)

        s = str(name_or_id).strip().lower()
        if not s:
            return None
        # Numeric-string path ("1", "8453").
        if s.isdigit():
            cid = int(s)
            name = _CHAIN_ID_TO_NAME.get(cid)
            if name is None:
                return None
            _, native = _CHAIN_INFO[name]
            return ChainInfo(chain_id=cid, chain_name=name, native_token=native)
        # Name path.
        entry = _CHAIN_INFO.get(s)
        if entry is None:
            return None
        cid, native = entry
        # Use the input form unless it's an alias → prefer the canonical.
        canonical = _CHAIN_ID_TO_NAME.get(cid, s)
        return ChainInfo(chain_id=cid, chain_name=canonical, native_token=native)

    # ─── Pool ───────────────────────────────────────────────────────────────

    def set_pool_resolver(
        self, override: Optional[callable]  # type: ignore[type-arg]
    ) -> None:
        """Test hook: inject a mock pool resolver so unit tests can avoid RPC.

        The override is called with the same kwargs as `resolve_pool`:
        `(token0=..., token1=..., fee_tier=..., chain=..., protocol=...)`
        and must return Optional[str] (the pool address).
        """
        self._pool_resolver_override = override

    def resolve_pool(
        self,
        token0: str,
        token1: str,
        fee_tier: int,
        chain: str,
        protocol: str,
    ) -> Optional[str]:
        """Resolve a pool address by (token0, token1, fee_tier, chain, protocol).

        For V3-family protocols this calls
        `src.data.v3_pool_resolver.resolve_v3_pool` (async) under an event
        loop. For V2 it consults the V2 factory map + on-chain `getPair`.
        For tests, install a mock via `set_pool_resolver`.

        Returns the lower-case 0x address of the pool, or None if no pool
        exists for the requested tuple.
        """
        if self._pool_resolver_override is not None:
            return self._pool_resolver_override(
                token0=token0,
                token1=token1,
                fee_tier=fee_tier,
                chain=chain,
                protocol=protocol,
            )

        canonical_proto = self.resolve_protocol(protocol) or protocol.lower()
        chain_l = chain.lower()

        # V3 family — dispatch into the async V3 pool resolver.
        v3_family = {
            "uniswap-v3",
            "pancakeswap-v3",
            "aerodrome-slipstream",
            "velodrome-cl",
            "velodrome-slipstream",
            "kodiak-v3",
            "swapx-v4",
        }
        if canonical_proto in v3_family:
            from src.data.v3_pool_resolver import resolve_v3_pool

            async def _run() -> Optional[str]:
                state = await resolve_v3_pool(
                    chain=chain_l,
                    protocol=canonical_proto,
                    token_a=token0,
                    token_b=token1,
                    fee_bps=fee_tier,
                )
                return state.pool_address if state is not None else None

            try:
                # If there's already a running loop the caller must use the
                # async path directly — return None instead of crashing.
                asyncio.get_running_loop()
                return None
            except RuntimeError:
                return asyncio.run(_run())

        # V2 family — look up factory and synthesize the pair via on-chain
        # getPair. For tests this path is always mocked.
        v2_family = {
            "uniswap-v2",
            "sushiswap",
            "pancakeswap-v2",
            "quickswap",
            "camelot",
            "trader-joe-v1",
            "baseswap",
            "velodrome-v1",
        }
        if canonical_proto in v2_family:
            factory = V2_FACTORIES.get((chain_l, canonical_proto))
            if factory is None:
                return None
            # Build getPair calldata: selector 0xe6a43905 + token0 + token1
            # (padded). Issue eth_call via the shared RPC pool. Tests should
            # mock — production wiring can be added when first adapter wants
            # it.
            from src.data.asset_registry import RPC_FALLBACKS

            rpcs = RPC_FALLBACKS.get(chain_l) or []
            if not rpcs:
                return None
            # Lazy import to keep startup light.
            import httpx

            t0 = token0.lower().removeprefix("0x").rjust(64, "0")
            t1 = token1.lower().removeprefix("0x").rjust(64, "0")
            data = "0xe6a43905" + t0 + t1
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_call",
                "params": [{"to": factory, "data": data}, "latest"],
            }
            for rpc in rpcs:
                try:
                    with httpx.Client(timeout=8) as cli:
                        r = cli.post(rpc, json=payload)
                        if r.status_code != 200:
                            continue
                        result = r.json().get("result")
                        if not result or result == "0x":
                            continue
                        addr = "0x" + result[-40:]
                        if int(addr, 16) == 0:
                            return None
                        return addr
                except (httpx.HTTPError, ValueError, KeyError):
                    continue
            return None

        return None
