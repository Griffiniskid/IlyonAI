"""LST + LRT direct-mint registry — R8 / Phase 6.

Per-protocol, per-chain mapping of (LST/LRT symbol → mint flow). Two
strategies per entry:
  - direct_mint: native mint contract + selector + min-deposit constraint.
  - secondary_market: Curve / Balancer / Uniswap V3 stable pool the
    runtime falls back to when direct mint is paused, capped, or rate-
    capped (e.g. Lido's stake-rate-limit kicks in on big deposits).

Selectors are the function the deposit call lands on. min_deposit / cap
fields gate the secondary fallback. Adapters consume this registry to
choose between native and pool-route per current state.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DirectMintPath:
    contract: str                    # mint contract address
    selector: str                    # 4-byte calldata prefix
    native_eth: bool = False         # True when deposit is plain ETH (msg.value)
    min_deposit_native: float = 0.0  # protocol-imposed min, in native units
    note: str = ""


@dataclass(frozen=True)
class SecondaryMarketPath:
    venue: str                       # "curve" | "balancer" | "uniswap-v3"
    pool_address: str                # pool contract address
    paired_with: str                 # the other side of the swap, e.g. "WETH"
    note: str = ""


@dataclass(frozen=True)
class LstEntry:
    chain: str
    symbol: str                      # e.g. "stETH", "ezETH"
    direct_mint: DirectMintPath | None
    secondary_market: SecondaryMarketPath | None
    protocol: str
    receipt_token: str               # the ERC20 the user holds after mint
    audit_url: str | None = None


# Ethereum mainnet first; non-Eth chains share the same symbol via the LRT
# registry. Adapters resolve secondary-market fallback when direct_mint
# returns "paused" / "capped" / "rate_limited".
_REGISTRY: dict[tuple[str, str], LstEntry] = {
    # ── Lido stETH ──
    ("ethereum", "stETH"): LstEntry(
        chain="ethereum", symbol="stETH",
        direct_mint=DirectMintPath(
            contract="0xae7ab96520de3a18e5e111b5eaab095312d7fe84",  # Lido stETH
            selector="0xa1903eab",  # submit(address referral)
            native_eth=True,
            min_deposit_native=0.0001,
            note="Lido staking rate-limit caps ~150_000 ETH per day; secondary kicks in past cap.",
        ),
        secondary_market=SecondaryMarketPath(
            venue="curve",
            pool_address="0xdc24316b9ae028f1497c275eb9192a3ea0f67022",  # ETH/stETH
            paired_with="ETH",
        ),
        protocol="lido", receipt_token="stETH",
    ),
    # ── Rocket Pool rETH ──
    ("ethereum", "rETH"): LstEntry(
        chain="ethereum", symbol="rETH",
        direct_mint=DirectMintPath(
            contract="0xae78736cd615f374d3085123a210448e74fc6393",  # RETH Token (deposit via DepositPool)
            selector="0xa3e0464d",  # deposit() via Rocket Deposit Pool
            native_eth=True,
            min_deposit_native=0.01,
            note="Rocket Pool deposit pool cap may force secondary route.",
        ),
        secondary_market=SecondaryMarketPath(
            venue="balancer",
            pool_address="0x1e19cf2d73a72ef1332c882f20534b6519be0276",  # rETH/wstETH
            paired_with="wstETH",
        ),
        protocol="rocket-pool", receipt_token="rETH",
    ),
    # ── ether.fi eETH / weETH ──
    ("ethereum", "eETH"): LstEntry(
        chain="ethereum", symbol="eETH",
        direct_mint=DirectMintPath(
            contract="0x308861a430be4cce5502d0a12724771fc6daf216",  # ether.fi Liquidity Pool
            selector="0xd5c08a72",  # deposit()
            native_eth=True,
            min_deposit_native=0.001,
        ),
        secondary_market=SecondaryMarketPath(
            venue="curve", pool_address="0x13947303f63b363876868d070f14dc865c36463b",
            paired_with="WETH",
        ),
        protocol="ether.fi", receipt_token="eETH",
    ),
    # ── Frax frxETH ──
    ("ethereum", "frxETH"): LstEntry(
        chain="ethereum", symbol="frxETH",
        direct_mint=DirectMintPath(
            contract="0xbafa44efe7901e04e39dad13167d089c559c1138",  # frxETHMinter
            selector="0x4dcd4547",  # submit()
            native_eth=True,
            min_deposit_native=0.01,
        ),
        secondary_market=SecondaryMarketPath(
            venue="curve", pool_address="0xa1f8a6807c402e4a15ef4eba36528a3fed24e577",
            paired_with="ETH",
        ),
        protocol="frax-ether", receipt_token="frxETH",
    ),
    # ── Mantle mETH ──
    ("ethereum", "mETH"): LstEntry(
        chain="ethereum", symbol="mETH",
        direct_mint=DirectMintPath(
            contract="0xe3cbd06d7dadb3f4e6557bab7edd924cd1489e8f",  # mantle staking
            selector="0xf6326fb3",  # stake()
            native_eth=True,
            min_deposit_native=0.01,
        ),
        secondary_market=None,
        protocol="mantle", receipt_token="mETH",
    ),
    # ── LRT registry (EigenLayer-restaked basket tokens) ──
    # Renzo ezETH
    ("ethereum", "ezETH"): LstEntry(
        chain="ethereum", symbol="ezETH",
        direct_mint=DirectMintPath(
            contract="0x74a09653a083691711cf8215a6ab074bb4e99ef5",  # RestakeManager
            selector="0xfdaf83a3",  # depositETH(referral)
            native_eth=True,
            min_deposit_native=0.01,
        ),
        secondary_market=SecondaryMarketPath(
            venue="balancer",
            pool_address="0x596192bb6e41802428ac943d2f1476c1af25cc0e",  # ezETH/WETH
            paired_with="WETH",
        ),
        protocol="renzo", receipt_token="ezETH",
    ),
    # Kelp rsETH
    ("ethereum", "rsETH"): LstEntry(
        chain="ethereum", symbol="rsETH",
        direct_mint=DirectMintPath(
            contract="0x036676389e48133b63a802f8635ad39e752d375d",  # Kelp depositPool
            selector="0x47e7ef24",  # depositAsset(address asset, uint256 amount)
            native_eth=False,
            min_deposit_native=0,
        ),
        secondary_market=SecondaryMarketPath(
            venue="balancer",
            pool_address="0x58aadfb1afac0ad7fca1148f3cde6aedf5236b6d",
            paired_with="ETHx",
        ),
        protocol="kelp", receipt_token="rsETH",
    ),
    # Swell rswETH / swETH
    ("ethereum", "rswETH"): LstEntry(
        chain="ethereum", symbol="rswETH",
        direct_mint=DirectMintPath(
            contract="0xfae103dc9cf190ed75350761e95403b7b8afa6c0",  # Swell rswETH
            selector="0xf340fa01",  # deposit()
            native_eth=True,
            min_deposit_native=0.01,
        ),
        secondary_market=None,
        protocol="swell", receipt_token="rswETH",
    ),
    # Puffer pufETH
    ("ethereum", "pufETH"): LstEntry(
        chain="ethereum", symbol="pufETH",
        direct_mint=DirectMintPath(
            contract="0xd9a442856c234a39a81a089c06451ebaa4306a72",  # PufferVault
            selector="0xb6b55f25",  # deposit(uint256) — ERC-4626
            native_eth=False,
        ),
        secondary_market=None,
        protocol="puffer", receipt_token="pufETH",
    ),
}


def lookup_lst(chain: str, symbol: str) -> LstEntry | None:
    return _REGISTRY.get((chain.lower(), symbol))


def all_entries() -> list[LstEntry]:
    return list(_REGISTRY.values())


def chains_for_symbol(symbol: str) -> list[str]:
    return [k[0] for k in _REGISTRY if k[1] == symbol]
