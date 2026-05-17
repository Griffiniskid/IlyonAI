"""V7-003 — Phase 6 chain expansion pin test.

For each of the 10 newly-added EVM chains (Linea, Scroll, Mantle, Blast,
zkSync Era, Gnosis, Celo, Sonic, Berachain, Unichain), verify that:

1. A ChainConfig entry exists in ``EVM_CHAIN_CONFIGS`` with the schema
   the rest of the codebase expects (explorer_url, primary_dex,
   wrapped_native_address, etc.).
2. ``RPC_FALLBACKS`` has at least one public RPC URL.
3. ``Settings`` exposes a ``<chain>_rpc_url`` Pydantic field so operators
   can override via env var.
4. The native gas token alias resolves through ``lookup_symbol``.
5. ``ChainType.icon_url`` returns a non-empty URL.

A drift here means Aave/Compound supply / Enso route attempts on these
chains will explode with AttributeError instead of returning a typed
NULL_ROUTE / unsupported-chain card.
"""
from __future__ import annotations

import pytest

from src.chains.base import EVM_CHAIN_CONFIGS, ChainType
from src.config import Settings
from src.data.asset_registry import RPC_FALLBACKS, lookup_symbol


# (ChainType, settings field name, native gas symbol)
NEW_CHAINS = [
    (ChainType.LINEA, "linea_rpc_url", "ETH"),
    (ChainType.SCROLL, "scroll_rpc_url", "ETH"),
    (ChainType.MANTLE, "mantle_rpc_url", "MNT"),
    (ChainType.BLAST, "blast_rpc_url", "ETH"),
    (ChainType.ZKSYNC, "zksync_rpc_url", "ETH"),
    (ChainType.GNOSIS, "gnosis_rpc_url", "XDAI"),
    (ChainType.CELO, "celo_rpc_url", "CELO"),
    (ChainType.SONIC, "sonic_rpc_url", "S"),
    (ChainType.BERACHAIN, "berachain_rpc_url", "BERA"),
    (ChainType.UNICHAIN, "unichain_rpc_url", "ETH"),
]


@pytest.mark.parametrize("chain,_field,_sym", NEW_CHAINS)
def test_chain_config_present(chain: ChainType, _field: str, _sym: str) -> None:
    """Every new chain must have a ChainConfig entry."""
    assert chain in EVM_CHAIN_CONFIGS, (
        f"{chain.value} missing from EVM_CHAIN_CONFIGS — "
        f"Aave/Compound adapters will AttributeError"
    )
    cfg = EVM_CHAIN_CONFIGS[chain]
    # Schema check — these keys are read by EVMChainClient/_factory paths.
    for required in (
        "explorer_url",
        "explorer_api_url",
        "primary_dex",
        "dex_router_address",
        "wrapped_native_address",
        "block_time_seconds",
    ):
        assert required in cfg, f"{chain.value} ChainConfig missing key '{required}'"
    # explorer + wrapped-native must be truthy strings.
    assert cfg["explorer_url"].startswith("http"), (
        f"{chain.value} explorer_url must be a URL"
    )
    assert cfg["wrapped_native_address"], (
        f"{chain.value} wrapped_native_address must be set "
        f"(empty breaks ETH↔WETH preflight)"
    )
    assert cfg["wrapped_native_address"].startswith("0x"), (
        f"{chain.value} wrapped_native_address must be a 0x-prefixed EVM address"
    )


@pytest.mark.parametrize("chain,_field,_sym", NEW_CHAINS)
def test_rpc_fallbacks_present(chain: ChainType, _field: str, _sym: str) -> None:
    """Every new chain must have at least one fallback RPC URL."""
    pool = RPC_FALLBACKS.get(chain.value)
    assert pool, f"RPC_FALLBACKS missing entry for {chain.value}"
    assert len(pool) >= 1, f"{chain.value} fallback pool is empty"
    for url in pool:
        assert url.startswith("http"), (
            f"{chain.value} fallback URL '{url}' is not http(s)"
        )


@pytest.mark.parametrize("chain,field,_sym", NEW_CHAINS)
def test_settings_field_present(chain: ChainType, field: str, _sym: str) -> None:
    """Settings must expose a Pydantic field for each new chain RPC."""
    settings = Settings()
    assert hasattr(settings, field), (
        f"Settings missing field '{field}' for {chain.value}"
    )
    # Defaults to None (Optional) so adapters fall back to RPC_FALLBACKS.
    value = getattr(settings, field)
    assert value is None or isinstance(value, str), (
        f"Settings.{field} must be Optional[str], got {type(value).__name__}"
    )


@pytest.mark.parametrize("chain,_field,sym", NEW_CHAINS)
def test_native_token_alias_resolves(chain: ChainType, _field: str, sym: str) -> None:
    """The native gas token must be reachable via lookup_symbol."""
    hit = lookup_symbol(chain.value, sym)
    assert hit is not None, (
        f"lookup_symbol({chain.value!r}, {sym!r}) returned None — "
        f"native-token preflight will fail"
    )
    addr, decimals = hit
    assert decimals == 18, (
        f"{chain.value} native token {sym} should be 18-decimals, got {decimals}"
    )
    assert addr.startswith("0x"), f"{chain.value} native placeholder must be 0x-prefixed"


@pytest.mark.parametrize("chain,_field,_sym", NEW_CHAINS)
def test_icon_url_present(chain: ChainType, _field: str, _sym: str) -> None:
    """UI cards rely on a non-empty icon_url; blank string breaks <img>."""
    icon = chain.icon_url
    assert icon, f"{chain.value}.icon_url is empty"
    assert icon.startswith("http"), f"{chain.value}.icon_url must be a URL"


def test_total_chain_config_count_meets_floor() -> None:
    """V7-003 exit criterion: ≥17 chain configs (was 7 before, now 7+10=17)."""
    assert len(EVM_CHAIN_CONFIGS) >= 17, (
        f"Expected ≥17 EVM_CHAIN_CONFIGS entries, got {len(EVM_CHAIN_CONFIGS)}"
    )
