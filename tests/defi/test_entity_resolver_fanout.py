"""V7-015 fan-out pin test — EntityResolver adoption across DeFi adapters.

Locks the contract that, post-refactor, all six in-scope adapters call the
centralized `EntityResolver` instead of keeping adapter-local
`_resolve_token` / `_CHAIN_IDS` helpers as the ONLY resolution path:

  * balancer.py
  * curve.py
  * uniswap_v2.py
  * uniswap_v3_nft.py
  * aave_v3.py
  * compound_v3.py

Three checks:
  1. Callsite-presence — each adapter module imports EntityResolver.
  2. Identity — patching `EntityResolver.resolve_token` is observed by the
     refactored adapter's build path (proof the resolver call is real).
  3. Behavioural parity — Uniswap V2 + Aave V3 adapters resolve USDC on
     Ethereum to the same canonical address `EntityResolver.resolve_token`
     returns directly.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.resolver.entity_resolver import EntityResolver


_ADAPTER_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "defi"
    / "execution"
    / "adapters"
)

_EXPECTED_ADAPTERS = [
    "balancer.py",
    "curve.py",
    "uniswap_v2.py",
    "uniswap_v3_nft.py",
    "aave_v3.py",
    "compound_v3.py",
]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── 1. Callsite-presence ──────────────────────────────────────────────────

def test_entity_resolver_imported_in_all_six_adapters() -> None:
    """All six target adapters must import EntityResolver at module scope."""
    needle_a = "from src.defi.resolver.entity_resolver import"
    needle_b = "from src.defi.resolver import"  # balancer + curve use re-export
    hits: list[str] = []
    for name in _EXPECTED_ADAPTERS:
        path = _ADAPTER_DIR / name
        assert path.is_file(), f"Missing adapter file: {path}"
        text = path.read_text(encoding="utf-8")
        if needle_a in text or needle_b in text:
            hits.append(name)
    assert len(hits) >= 6, (
        f"EntityResolver fan-out incomplete. Found in {hits} "
        f"(expected ≥ 6 of {_EXPECTED_ADAPTERS})."
    )


def test_uniswap_v2_imports_entity_resolver_directly() -> None:
    text = (_ADAPTER_DIR / "uniswap_v2.py").read_text(encoding="utf-8")
    assert "from src.defi.resolver.entity_resolver import EntityResolver" in text


def test_uniswap_v3_nft_imports_entity_resolver_directly() -> None:
    text = (_ADAPTER_DIR / "uniswap_v3_nft.py").read_text(encoding="utf-8")
    assert "from src.defi.resolver.entity_resolver import EntityResolver" in text


def test_aave_v3_imports_entity_resolver_directly() -> None:
    text = (_ADAPTER_DIR / "aave_v3.py").read_text(encoding="utf-8")
    assert "from src.defi.resolver.entity_resolver import EntityResolver" in text


def test_compound_v3_imports_entity_resolver_directly() -> None:
    text = (_ADAPTER_DIR / "compound_v3.py").read_text(encoding="utf-8")
    assert "from src.defi.resolver.entity_resolver import EntityResolver" in text


# ─── 2. Identity — monkeypatched resolver is observed ──────────────────────

def test_aave_v3_build_invokes_entity_resolver_resolve_token(monkeypatch):
    """Spy on EntityResolver.resolve_token and confirm Aave V3 build calls it."""
    from src.defi.execution.adapters import aave_v3 as adapter_mod

    calls: list[tuple[str, str]] = []
    real = EntityResolver.resolve_token

    def spy(self, symbol_or_addr: str, chain: str):
        calls.append((symbol_or_addr, chain))
        return real(self, symbol_or_addr, chain)

    monkeypatch.setattr(EntityResolver, "resolve_token", spy)

    a = adapter_mod.AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="aave-v3",
        asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    assert steps, "Aave V3 build returned no steps"
    assert any(c[0].upper() == "USDC" and c[1].lower() == "ethereum" for c in calls), (
        f"EntityResolver.resolve_token was not called by Aave V3 build for "
        f"(USDC, ethereum); observed calls: {calls}"
    )


def test_compound_v3_build_invokes_entity_resolver_resolve_token(monkeypatch):
    """Spy on EntityResolver.resolve_token and confirm Compound V3 build calls it."""
    from src.defi.execution.adapters import compound_v3 as adapter_mod

    calls: list[tuple[str, str]] = []
    real = EntityResolver.resolve_token

    def spy(self, symbol_or_addr: str, chain: str):
        calls.append((symbol_or_addr, chain))
        return real(self, symbol_or_addr, chain)

    monkeypatch.setattr(EntityResolver, "resolve_token", spy)

    a = adapter_mod.CompoundV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="compound-v3",
        asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    assert steps, "Compound V3 build returned no steps"
    assert any(c[0].upper() == "USDC" and c[1].lower() == "ethereum" for c in calls), (
        f"EntityResolver.resolve_token was not called by Compound V3 build for "
        f"(USDC, ethereum); observed calls: {calls}"
    )


def test_uniswap_v2_build_invokes_entity_resolver_resolve_token(monkeypatch):
    """Spy on EntityResolver.resolve_token and confirm Uniswap V2 build calls it."""
    from src.defi.execution.adapters import uniswap_v2 as adapter_mod

    calls: list[tuple[str, str]] = []
    real = EntityResolver.resolve_token

    def spy(self, symbol_or_addr: str, chain: str):
        calls.append((symbol_or_addr, chain))
        return real(self, symbol_or_addr, chain)

    monkeypatch.setattr(EntityResolver, "resolve_token", spy)

    a = adapter_mod.UniswapV2DualTokenAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="uniswap-v2",
        asset_in="USDC",
        amount_in=Decimal("1000"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"token_b": "WETH", "amount_a": Decimal("1000"), "amount_b": Decimal("0.5")},
    )
    steps = _run(a.build(req))
    assert steps, "Uniswap V2 build returned no steps"
    assert any(c[0].upper() in {"USDC", "WETH"} for c in calls), (
        f"EntityResolver.resolve_token was not called by Uniswap V2 build; "
        f"observed calls: {calls}"
    )


# ─── 3. Behavioural parity — USDC on Ethereum ──────────────────────────────

_USDC_ETHEREUM = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"


def test_entity_resolver_resolves_usdc_ethereum_to_canonical_address():
    r = EntityResolver()
    info = r.resolve_token("USDC", "ethereum")
    assert info is not None
    assert info.address == _USDC_ETHEREUM
    assert info.decimals == 6


def test_aave_v3_supply_calldata_carries_canonical_usdc_address():
    """Aave V3 supply on Ethereum / USDC encodes the same address that
    EntityResolver returns directly — proof the lookup path is identity-equal.
    """
    from src.defi.execution.adapters import aave_v3 as adapter_mod

    a = adapter_mod.AaveV3SupplyAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="aave-v3",
        asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    steps = _run(a.build(req))
    assert steps, "Aave V3 supply returned no steps"
    # The approve step's `to` field is the token address. Find it.
    approve = next((s for s in steps if s.action == "approve"), None)
    assert approve is not None, f"No approve step in {[s.action for s in steps]}"
    assert approve.transaction.to.lower() == _USDC_ETHEREUM


def test_uniswap_v2_addLiquidity_calldata_carries_canonical_usdc_address():
    """Uniswap V2 dual-token addLiquidity encodes USDC at the canonical
    asset_registry address that EntityResolver resolves to."""
    from src.defi.execution.adapters import uniswap_v2 as adapter_mod

    a = adapter_mod.UniswapV2DualTokenAdapter()
    req = YieldBuildRequest(
        chain="ethereum",
        protocol="uniswap-v2",
        asset_in="USDC",
        amount_in=Decimal("1000"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"token_b": "WETH", "amount_a": Decimal("1000"), "amount_b": Decimal("0.5")},
    )
    steps = _run(a.build(req))
    assert steps, "Uniswap V2 build returned no steps"
    # First approve step's `to` is tokenA = USDC.
    approves = [s for s in steps if s.action == "approve"]
    assert approves, f"No approve step; got {[s.action for s in steps]}"
    first_approve_to = approves[0].transaction.to.lower()
    assert first_approve_to == _USDC_ETHEREUM, (
        f"First V2 approve targets {first_approve_to}; "
        f"expected canonical USDC {_USDC_ETHEREUM}"
    )
