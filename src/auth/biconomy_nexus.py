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


# ─────────────────────────────────────────────────────────────────────
# Phase 7 / §11 D.5 — policy framework integration
# ─────────────────────────────────────────────────────────────────────

# ERC-7579 module type IDs
NEXUS_MODULE_TYPE_VALIDATOR = 1
NEXUS_MODULE_TYPE_EXECUTOR  = 2
NEXUS_MODULE_TYPE_FALLBACK  = 3
NEXUS_MODULE_TYPE_HOOK      = 4

# Nexus installModule(uint256 moduleTypeId, address module, bytes initData)
# selector = keccak256("installModule(uint256,address,bytes)")[:4] = 0x9517e29f
_NEXUS_INSTALL_MODULE_SELECTOR = "0x9517e29f"
# uninstallModule(uint256 moduleTypeId, address module, bytes deinitData)
_NEXUS_UNINSTALL_MODULE_SELECTOR = "0xa71763a8"


def _encode_uint256(value: int) -> str:
    if value < 0:
        raise ValueError("uint256 cannot be negative")
    return format(value, "064x")


def _encode_address(address: str) -> str:
    a = address.lower()
    if a.startswith("0x"):
        a = a[2:]
    if len(a) != 40:
        raise ValueError(f"invalid address: {address}")
    return ("0" * 24) + a


def _encode_bytes(data: bytes) -> str:
    """ABI-encode dynamic bytes: 32-byte length + data padded to 32-byte boundary."""
    length = len(data)
    hex_data = data.hex()
    pad_len = (32 - length % 32) % 32
    return _encode_uint256(length) + hex_data + "00" * pad_len


def build_install_session_key_module_calldata(
    *,
    validator_module_address: str,
    session_signer: str,
    spend_cap_wei: int,
    selector_allowlist: list[str],
    expiry_unix: int,
) -> str:
    """Build calldata for `Nexus.installModule(VALIDATOR, validator_module,
    initData)` where initData encodes the SessionKey policy:
        abi.encode(address signer, uint256 spendCap, bytes4[] selectors, uint256 expiry)

    The signed tx broadcasts an EIP-7702 op that delegates to Nexus +
    immediately installs the session-key policy module. Subsequent agent
    actions broadcast through the session signer; Nexus enforces spend cap
    + selector allowlist + expiry on-chain.
    """
    if not selector_allowlist:
        raise ValueError("selector_allowlist must be non-empty.")
    # initData = abi.encode(address, uint256, bytes4[], uint256)
    # bytes4[] is dynamic — offset = 0x80 (4 head words × 32 bytes)
    head = (
        _encode_address(session_signer)
        + _encode_uint256(spend_cap_wei)
        + _encode_uint256(0x80)  # offset to bytes4[]
        + _encode_uint256(expiry_unix)
    )
    # bytes4[] tail: length + each entry padded right to 32 bytes
    tail = _encode_uint256(len(selector_allowlist))
    for sel in selector_allowlist:
        s = sel.lower().removeprefix("0x")
        if len(s) != 8:
            raise ValueError(f"selector must be 4 bytes (8 hex chars): {sel}")
        tail += s + ("0" * 56)  # pad to 32 bytes (4 byte selector + 28 byte pad)
    init_data_hex = head + tail
    init_data_bytes = bytes.fromhex(init_data_hex)
    # outer: installModule(uint256, address, bytes)
    # bytes parameter is dynamic — offset = 0x60 (3 head words)
    calldata = (
        _NEXUS_INSTALL_MODULE_SELECTOR
        + _encode_uint256(NEXUS_MODULE_TYPE_VALIDATOR)
        + _encode_address(validator_module_address)
        + _encode_uint256(0x60)  # offset to bytes
        + _encode_bytes(init_data_bytes)
    )
    return calldata


def build_uninstall_session_key_module_calldata(
    *,
    validator_module_address: str,
) -> str:
    """Build calldata for Nexus.uninstallModule(VALIDATOR, validator_module, "")
    — revokes the session-key policy installed previously."""
    calldata = (
        _NEXUS_UNINSTALL_MODULE_SELECTOR
        + _encode_uint256(NEXUS_MODULE_TYPE_VALIDATOR)
        + _encode_address(validator_module_address)
        + _encode_uint256(0x60)
        + _encode_uint256(0)  # empty bytes
    )
    return calldata


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
