from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GasTopupBundle:
    source_chain: str
    source_token: str
    source_amount_usd: float
    dest_chain: str
    dest_native_token: str
    bridge_route: str  # "debridge" / "lifi" / "socket"
    bundle_steps: list = field(default_factory=list)


def build_gas_topup_bundle(
    insufficient_chain: str,
    needed_usd: float,
    wallet_inventory: dict,
    source_preference: str = "ethereum",
) -> Optional[GasTopupBundle]:
    """If user has source funds on another chain, suggest bridge+swap+supply bundle.
    wallet_inventory shape: {"ethereum": {"USDC": 100}, "arbitrum": {"USDC": 5}, ...}
    Returns None if no source can cover needed_usd.
    """
    for chain, balances in wallet_inventory.items():
        if chain == insufficient_chain:
            continue
        usdc = balances.get("USDC", 0)
        if usdc >= needed_usd:
            return GasTopupBundle(
                source_chain=chain,
                source_token="USDC",
                source_amount_usd=needed_usd,
                dest_chain=insufficient_chain,
                dest_native_token=_native_for_chain(insufficient_chain),
                bridge_route="debridge",
                bundle_steps=[
                    {"action": "bridge", "from": chain, "to": insufficient_chain, "asset": "USDC", "amount_usd": needed_usd},
                    {"action": "swap", "chain": insufficient_chain, "from": "USDC", "to": _native_for_chain(insufficient_chain), "amount_usd": needed_usd},
                ],
            )
    return None


def _native_for_chain(chain: str) -> str:
    return {"ethereum": "ETH", "arbitrum": "ETH", "base": "ETH", "optimism": "ETH",
            "polygon": "MATIC", "bsc": "BNB", "avalanche": "AVAX",
            "sonic": "S", "berachain": "BERA", "celo": "CELO",
            "mantle": "MNT", "gnosis": "XDAI"}.get(chain.lower(), "ETH")
