"""Biconomy Nexus wrapper around the generic EIP-7702 helpers.

Nexus is one of three impl contracts the user can delegate to (the
other two are ZeroDev Kernel + Safe-7579). This module pins the Nexus
defaults so the runtime can preflight an authorization without the
caller threading the impl address through every layer.

The actual policy-framework integration (per-policy attachPolicy +
validation-config encoding) needs the live Nexus ABI; this layer ships
the deterministic pieces (digest + authorization tuple) so the user
flow can begin signing today.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.auth.smart_account import (
    BICONOMY_NEXUS_IMPL,
    Eip7702Authorization,
    authorization_digest,
    build_authorization_from_signature,
)


# Chain-ID set where Biconomy has deployed the Nexus impl. Per Biconomy
# docs, the impl address is identical across every supported chain —
# the auth tuple just carries the chain_id.
NEXUS_CHAIN_IDS: frozenset[int] = frozenset({
    1,        # Ethereum
    10,       # Optimism
    56,       # BSC
    137,      # Polygon
    8453,     # Base
    42161,    # Arbitrum
    43114,    # Avalanche
    80094,    # Berachain
    59144,    # Linea
    81457,    # Blast
    5000,     # Mantle
    100,      # Gnosis
    324,      # zkSync Era
    534352,   # Scroll
    42220,    # Celo
    130,      # Unichain
    146,      # Sonic
})


@dataclass(frozen=True)
class NexusAuthRequest:
    """Inputs to start a Nexus delegation flow."""

    user_wallet: str
    chain_id: int
    nonce: int

    @property
    def implementation(self) -> str:
        return BICONOMY_NEXUS_IMPL


def supported_chain(chain_id: int) -> bool:
    return chain_id in NEXUS_CHAIN_IDS


def prepare_nexus_authorization(
    *,
    user_wallet: str,
    chain_id: int,
    nonce: int,
) -> dict[str, Any]:
    """Return the data the frontend needs to prompt the user to sign.

    Output shape:
      {
        impl: 0x000000aC74357BFEa72BBD0781833631F732cf19,
        chain_id: 1,
        nonce: <u64>,
        digest: 0x<32-byte hex>,
        wallet: 0x<user>,
      }

    Frontend prompts MetaMask with the digest; server combines the
    returned 65-byte signature with these three params via
    `build_authorization_from_signature` to produce the tuple.
    """
    if not supported_chain(chain_id):
        raise ValueError(
            f"Biconomy Nexus impl not deployed on chain_id {chain_id}. "
            f"Supported: {sorted(NEXUS_CHAIN_IDS)}"
        )
    digest = authorization_digest(
        chain_id=chain_id,
        implementation=BICONOMY_NEXUS_IMPL,
        nonce=nonce,
    )
    return {
        "impl": BICONOMY_NEXUS_IMPL,
        "chain_id": chain_id,
        "nonce": nonce,
        "digest": "0x" + digest.hex(),
        "wallet": user_wallet,
    }


def assemble_nexus_authorization(
    *,
    chain_id: int,
    nonce: int,
    signature_hex: str,
) -> Eip7702Authorization:
    """Convenience wrapper — fills in the Nexus impl automatically so
    callers only pass chain_id + nonce + the signed digest."""
    if not supported_chain(chain_id):
        raise ValueError(
            f"Biconomy Nexus impl not deployed on chain_id {chain_id}."
        )
    return build_authorization_from_signature(
        chain_id=chain_id,
        implementation=BICONOMY_NEXUS_IMPL,
        nonce=nonce,
        signature_hex=signature_hex,
    )
