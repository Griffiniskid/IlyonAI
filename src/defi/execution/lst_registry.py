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


# ─────────────────────────────────────────────────────────────────────────────
# V7-055 — per-chain receipt-token address registry
# ─────────────────────────────────────────────────────────────────────────────
#
# Many LSTs live on multiple chains as bridged ERC20s with DIFFERENT addresses
# per chain. Direct-mint flows generally only exist on Ethereum mainnet, but
# the *receipt token* the user actually holds (and that adapters/quotes need
# to reference) has chain-specific addresses on L2s.
#
# Shape:
#   LST_REGISTRY[protocol][chain_id] = {
#       "receipt_addr": "0x…",        # ERC20 the user holds after mint/bridge
#       "minter":       "0x…" | None, # direct-mint contract (Ethereum-only for
#                                       most protocols); None on bridged L2s
#       "decimals":     int,
#       "symbol":       str,          # receipt-token symbol on that chain
#   }
#
# Addresses verified against on-chain block explorers + protocol docs where
# noted. Anything marked TODO needs verification before being relied on.
#
# Chains:
#   1     = Ethereum mainnet
#   10    = Optimism
#   8453  = Base
#   42161 = Arbitrum One
#   59144 = Linea
LST_REGISTRY: dict[str, dict[int, dict]] = {
    # ── Lido — wstETH is the bridged/wrapped variant on L2s (stETH is rebasing
    #    and is not bridged natively; L2s use wstETH).
    "lido": {
        1: {
            "receipt_addr": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",  # wstETH
            "minter":       "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",  # stETH (wrap via wstETH contract)
            "decimals":     18,
            "symbol":       "wstETH",
        },
        42161: {
            "receipt_addr": "0x5979D7b546E38E414F7E9822514be443A4800529",  # wstETH on Arbitrum
            "minter":       None,
            "decimals":     18,
            "symbol":       "wstETH",
        },
        10: {
            "receipt_addr": "0x1F32b1c2345538c0c6f582fCB022739c4A194Ebb",  # wstETH on Optimism
            "minter":       None,
            "decimals":     18,
            "symbol":       "wstETH",
        },
        8453: {
            "receipt_addr": "0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452",  # wstETH on Base
            "minter":       None,
            "decimals":     18,
            "symbol":       "wstETH",
        },
        59144: {
            "receipt_addr": "0xB5beDd42000b71FddE22D3eE8a79Bd49A568fC8F",  # wstETH on Linea
            "minter":       None,
            "decimals":     18,
            "symbol":       "wstETH",
        },
    },
    # ── Coinbase — cbETH on Ethereum + Base + Arbitrum + Optimism.
    "coinbase": {
        1: {
            "receipt_addr": "0xBe9895146f7AF43049ca1c1AE358B0541Ea49704",  # cbETH on Ethereum
            "minter":       None,  # cbETH is minted by Coinbase off-chain
            "decimals":     18,
            "symbol":       "cbETH",
        },
        8453: {
            "receipt_addr": "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22",  # cbETH on Base
            "minter":       None,
            "decimals":     18,
            "symbol":       "cbETH",
        },
        42161: {
            "receipt_addr": "0x1DEBd73E752bEaF79865Fd6446b0c970EaE7732f",  # cbETH on Arbitrum
            "minter":       None,
            "decimals":     18,
            "symbol":       "cbETH",
        },
        10: {
            "receipt_addr": "0xaddb6A0412DE1BA0F936DCaeb8Aaa24578dcF3B2",  # cbETH on Optimism
            "minter":       None,
            "decimals":     18,
            "symbol":       "cbETH",
        },
    },
    # ── Rocket Pool — rETH on Ethereum + Arbitrum + Optimism + Base.
    "rocket-pool": {
        1: {
            "receipt_addr": "0xae78736Cd615f374D3085123A210448E74Fc6393",  # rETH on Ethereum
            "minter":       "0xDD3f50F8A6CafbE9b31a427582963f465E745AF8",  # RocketDepositPool
            "decimals":     18,
            "symbol":       "rETH",
        },
        42161: {
            "receipt_addr": "0xEC70Dcb4A1EFa46b8F2D97C310C9c4790ba5ffA8",  # rETH on Arbitrum
            "minter":       None,
            "decimals":     18,
            "symbol":       "rETH",
        },
        10: {
            "receipt_addr": "0x9Bcef72be871e61ED4fBbc7630889beE758eb81D",  # rETH on Optimism
            "minter":       None,
            "decimals":     18,
            "symbol":       "rETH",
        },
        8453: {
            "receipt_addr": "0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624c",  # rETH on Base
            "minter":       None,
            "decimals":     18,
            "symbol":       "rETH",
        },
    },
    # ── ether.fi — weETH (wrapped eETH) is the bridged variant on L2s.
    "ether.fi": {
        1: {
            "receipt_addr": "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee",  # weETH on Ethereum
            "minter":       "0x308861a430be4cce5502d0a12724771fc6daf216",  # LiquidityPool (mints eETH)
            "decimals":     18,
            "symbol":       "weETH",
        },
        42161: {
            "receipt_addr": "0x35751007a407ca6FEFfE80b3cB397736D2cf4dbe",  # weETH on Arbitrum
            "minter":       None,
            "decimals":     18,
            "symbol":       "weETH",
        },
        8453: {
            "receipt_addr": "0x04C0599Ae5A44757c0af6F9eC3b93da8976c150A",  # weETH on Base
            "minter":       None,
            "decimals":     18,
            "symbol":       "weETH",
        },
        10: {
            "receipt_addr": "0x5A7fACB970D094B6C7FF1df0eA68D99E6e73CBFF",  # weETH on Optimism
            "minter":       None,
            "decimals":     18,
            "symbol":       "weETH",
        },
        59144: {
            "receipt_addr": "0x1Bf74C010E6320bab11e2e5A532b5AC15e0b8aA6",  # weETH on Linea
            "minter":       None,
            "decimals":     18,
            "symbol":       "weETH",
        },
    },
    # ── Renzo — ezETH is bridged to L2s.
    "renzo": {
        1: {
            "receipt_addr": "0xbf5495Efe5DB9ce00f80364C8B423567e58d2110",  # ezETH on Ethereum (proxy)
            "minter":       "0x74a09653a083691711cf8215a6ab074bb4e99ef5",  # RestakeManager
            "decimals":     18,
            "symbol":       "ezETH",
        },
        42161: {
            "receipt_addr": "0x2416092f143378750bb29b79eD961ab195CcEea5",  # ezETH on Arbitrum
            "minter":       None,
            "decimals":     18,
            "symbol":       "ezETH",
        },
        8453: {
            "receipt_addr": "0x2416092f143378750bb29b79eD961ab195CcEea5",  # ezETH on Base
            "minter":       None,
            "decimals":     18,
            "symbol":       "ezETH",
        },
        59144: {
            "receipt_addr": "0x2416092f143378750bb29b79eD961ab195CcEea5",  # ezETH on Linea
            "minter":       None,
            "decimals":     18,
            "symbol":       "ezETH",
        },
    },
    # ── Kelp DAO — rsETH bridged to L2s.
    "kelp": {
        1: {
            "receipt_addr": "0xA1290d69c65A6Fe4DF752f95823fae25cB99e5A7",  # rsETH on Ethereum
            "minter":       "0x036676389e48133b63a802f8635ad39e752d375d",  # LRTDepositPool
            "decimals":     18,
            "symbol":       "rsETH",
        },
        42161: {
            "receipt_addr": "0x4186BFC76E2E237523CBC30FD220FE055156b41F",  # rsETH on Arbitrum
            "minter":       None,
            "decimals":     18,
            "symbol":       "rsETH",
        },
        10: {
            "receipt_addr": "0x87eEE96D50Fb761AD85B1c982d28A042169d61b1",  # rsETH on Optimism
            "minter":       None,
            "decimals":     18,
            "symbol":       "rsETH",
        },
        8453: {
            "receipt_addr": "0x1Bc71130A0e39942a7658878169764Bbd8A45993",  # rsETH on Base
            "minter":       None,
            "decimals":     18,
            "symbol":       "rsETH",
        },
        59144: {
            "receipt_addr": "0x4186BFC76E2E237523CBC30FD220FE055156b41F",  # rsETH on Linea (TODO: re-verify on Lineascan)
            "minter":       None,
            "decimals":     18,
            "symbol":       "rsETH",
        },
    },
    # ── Frax — frxETH on Ethereum + Arbitrum + Optimism.
    "frax-ether": {
        1: {
            "receipt_addr": "0x5E8422345238F34275888049021821E8E08CAa1f",  # frxETH on Ethereum
            "minter":       "0xbAFA44EFE7901E04E39Dad13167D089C559c1138",  # frxETHMinter
            "decimals":     18,
            "symbol":       "frxETH",
        },
        42161: {
            "receipt_addr": "0x178412e79c25968a32e89b11f63B33F733770c2A",  # frxETH on Arbitrum
            "minter":       None,
            "decimals":     18,
            "symbol":       "frxETH",
        },
        10: {
            "receipt_addr": "0x6806411765Af15Bddd26f8f544A34cC40cb9838B",  # frxETH on Optimism
            "minter":       None,
            "decimals":     18,
            "symbol":       "frxETH",
        },
    },
    # ── Mantle — mETH on Ethereum (mainnet) + bridged to Mantle L2 (5000).
    "mantle": {
        1: {
            "receipt_addr": "0xd5F7838F5C461fefF7FE49ea5ebaF7728bB0ADfa",  # mETH on Ethereum
            "minter":       "0xe3cbd06d7dadb3f4e6557bab7edd924cd1489e8f",  # Mantle staking
            "decimals":     18,
            "symbol":       "mETH",
        },
    },
    # ── Swell — rswETH / swETH on Ethereum (no L2 bridge presence as of writing).
    "swell": {
        1: {
            "receipt_addr": "0xFAe103DC9cf190eD75350761e95403b7b8aFa6c0",  # rswETH on Ethereum
            "minter":       "0xfae103dc9cf190ed75350761e95403b7b8afa6c0",  # rswETH (self-mint)
            "decimals":     18,
            "symbol":       "rswETH",
        },
    },
    # ── Puffer — pufETH on Ethereum.
    "puffer": {
        1: {
            "receipt_addr": "0xD9A442856C234a39a81a089C06451EBAa4306a72",  # pufETH (ERC-4626 vault)
            "minter":       "0xD9A442856C234a39a81a089C06451EBAa4306a72",  # PufferVault
            "decimals":     18,
            "symbol":       "pufETH",
        },
    },
}


def lst_for_chain(protocol: str, chain_id: int) -> dict | None:
    """Return per-chain receipt-token record, or None if not registered.

    Looks up `LST_REGISTRY[protocol][chain_id]`. Protocol key is matched
    case-insensitively against canonical lowercase keys. Returns a *copy*
    of the entry so callers can mutate without polluting the registry.
    """
    if not isinstance(protocol, str) or not protocol:
        return None
    proto = protocol.lower()
    by_chain = LST_REGISTRY.get(proto)
    if by_chain is None:
        return None
    entry = by_chain.get(int(chain_id))
    if entry is None:
        return None
    return dict(entry)


def supported_chains_for_protocol(protocol: str) -> list[int]:
    """Return sorted list of chain_ids registered for a protocol."""
    by_chain = LST_REGISTRY.get(protocol.lower()) if isinstance(protocol, str) else None
    if not by_chain:
        return []
    return sorted(by_chain.keys())


def all_protocols() -> list[str]:
    return sorted(LST_REGISTRY.keys())
