"""ZeroDev Kernel wrapper — sibling to biconomy_nexus.

Kernel is the second policy-framework option the user can delegate to.
Same EIP-7702 authorization shape; different impl address.

Kernel v3 default impl (per ZeroDev docs as of 2026-05) ships at
0xd6CEDDe84be40893d153Be9d467CD6aD37875b28 across all supported chains.
Frontend opt-in flow picks Nexus or Kernel by user preference; the
backend uses identical digest + tuple-assembly helpers — only the impl
address differs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.auth.smart_account import (
    Eip7702Authorization,
    authorization_digest,
    build_authorization_from_signature,
)


KERNEL_V3_IMPL = "0xd6CEDDe84be40893d153Be9d467CD6aD37875b28"


# Kernel v3 deployed-chain set per ZeroDev docs. Overlaps with Nexus on
# the major EVM chains. The two sets differ at the tail (Kernel is on
# more L2s; Nexus has wider canonical-CL coverage).
KERNEL_CHAIN_IDS: frozenset[int] = frozenset({
    1, 10, 56, 137, 8453, 42161, 43114,
    59144, 81457, 5000, 100, 324, 534352, 42220, 130, 146,
    480,    # World Chain
    1101,   # Polygon zkEVM
    250,    # Fantom (legacy)
})


@dataclass(frozen=True)
class KernelAuthRequest:
    user_wallet: str
    chain_id: int
    nonce: int

    @property
    def implementation(self) -> str:
        return KERNEL_V3_IMPL


def supported_chain(chain_id: int) -> bool:
    return chain_id in KERNEL_CHAIN_IDS


def prepare_kernel_authorization(
    *,
    user_wallet: str,
    chain_id: int,
    nonce: int,
) -> dict[str, Any]:
    if not supported_chain(chain_id):
        raise ValueError(
            f"ZeroDev Kernel not deployed on chain_id {chain_id}. "
            f"Supported: {sorted(KERNEL_CHAIN_IDS)}"
        )
    digest = authorization_digest(
        chain_id=chain_id,
        implementation=KERNEL_V3_IMPL,
        nonce=nonce,
    )
    return {
        "impl": KERNEL_V3_IMPL,
        "chain_id": chain_id,
        "nonce": nonce,
        "digest": "0x" + digest.hex(),
        "wallet": user_wallet,
    }


def assemble_kernel_authorization(
    *,
    chain_id: int,
    nonce: int,
    signature_hex: str,
) -> Eip7702Authorization:
    if not supported_chain(chain_id):
        raise ValueError(
            f"ZeroDev Kernel not deployed on chain_id {chain_id}."
        )
    return build_authorization_from_signature(
        chain_id=chain_id,
        implementation=KERNEL_V3_IMPL,
        nonce=nonce,
        signature_hex=signature_hex,
    )
