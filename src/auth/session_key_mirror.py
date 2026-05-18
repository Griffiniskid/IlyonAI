"""V7-073 — Session-key mirror on-chain check.

Spec §1 invariant: before the runtime declares a session-key revoke
"complete", we MUST mirror-check the on-chain state by calling
`Nexus.isModuleInstalled(moduleType, module, initData)`. The frontend
"Revoke session key" CTA writes through the deterministic
`Nexus.uninstallModule` adapter (V7-074) and then the state-machine
verifier asks this module whether the on-chain mirror says the module
is gone. Only when both halves agree do we flip the session-key
policy to "revoked" in the unified state store (V7-075).

Why this matters: a freshly-broadcast `uninstallModule` tx can fail
(reverted, out-of-gas, wrong moduleType) and yet the wallet returns
a tx hash. The naive runtime would mark the policy as revoked and
the agent could keep using the (still-installed) session signer to
spend. The mirror check closes that gap by reading the EIP-7579
module-registry state straight from the Nexus account.

Selector reference:
    isModuleInstalled(uint256 moduleTypeId, address module, bytes initData)
        => keccak256("isModuleInstalled(uint256,address,bytes)")[:4]
        => 0x112d3a7d

The function is intentionally adapter-agnostic w.r.t. the EVM client:
any object exposing `async call(to: str, data: str) -> str` (hex-encoded
return) works. Tests inject a mock; production wires the same surface
on top of the existing aiohttp JSON-RPC client.
"""
from __future__ import annotations

from typing import Any, Protocol


# ERC-7579 module type IDs — mirrors the constants in biconomy_nexus.py
# (kept duplicated here to avoid a circular import; the IDs are an
# on-chain ABI invariant and won't drift).
NEXUS_MODULE_TYPE_VALIDATOR = 1
NEXUS_MODULE_TYPE_EXECUTOR = 2
NEXUS_MODULE_TYPE_FALLBACK = 3
NEXUS_MODULE_TYPE_HOOK = 4

# isModuleInstalled(uint256 moduleTypeId, address module, bytes initData)
# selector = keccak256("isModuleInstalled(uint256,address,bytes)")[:4]
NEXUS_IS_MODULE_INSTALLED_SELECTOR = "0x112d3a7d"


class _EvmCallable(Protocol):
    """Minimal surface the mirror check needs from an EVM client.

    Real implementations (web3.py, aiohttp JSON-RPC, etc.) all expose
    some form of `eth_call`; we only require the typed async surface so
    tests can inject a trivial mock without standing up a full provider.
    """

    async def call(self, to: str, data: str) -> str:  # pragma: no cover - Protocol
        ...


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


def _encode_empty_bytes_arg() -> str:
    """ABI-encode an empty bytes value (length 0, no payload)."""
    return _encode_uint256(0)


def build_is_module_installed_calldata(
    *,
    module_type: int,
    module_address: str,
    init_data: bytes = b"",
) -> str:
    """Build the calldata for `Nexus.isModuleInstalled(uint256,address,bytes)`.

    Returns the 0x-prefixed hex string the EVM client passes as `data`
    to `eth_call`. We only support empty `init_data` for now (the
    common revoke-mirror case); callers needing non-empty init data
    can extend by mirroring `_encode_bytes` from biconomy_nexus.py.
    """
    head = (
        _encode_uint256(module_type)
        + _encode_address(module_address)
        + _encode_uint256(0x60)  # offset to bytes
    )
    tail = _encode_uint256(len(init_data)) + init_data.hex()
    return NEXUS_IS_MODULE_INSTALLED_SELECTOR + head + tail


def _decode_bool(hex_return: str) -> bool:
    """Decode a single ABI-encoded bool returned from eth_call.

    The Solidity `bool` is right-padded to 32 bytes, so True is
    `0x000...01` and False is `0x000...00`. We accept either the raw
    return or a prefixed/padded form for robustness against client
    formatting variation.
    """
    if not hex_return:
        return False
    s = hex_return.lower().removeprefix("0x").lstrip("0")
    return s == "1"


async def is_session_key_active_on_chain(
    nexus_addr: str,
    session_module_addr: str,
    evm_client: Any,
    *,
    module_type: int = NEXUS_MODULE_TYPE_VALIDATOR,
    init_data: bytes = b"",
) -> bool:
    """Mirror-check: does Nexus report the session-key module installed?

    Calls `Nexus.isModuleInstalled(moduleType, module, initData)` against
    the user's Nexus account and decodes the bool return. Returns True
    iff the on-chain registry confirms the module is currently active,
    False if the registry confirms it is NOT installed.

    Raises the underlying RPC exception on call failure — callers MUST
    decide how to handle the ambiguity. `assert_session_key_revoked`
    treats a raise as "cannot confirm revocation" (returns False, the
    SAFE direction). The §1 invariant: we never declare a key revoked
    on an RPC blip.
    """
    calldata = build_is_module_installed_calldata(
        module_type=module_type,
        module_address=session_module_addr,
        init_data=init_data,
    )
    raw = await evm_client.call(nexus_addr, calldata)
    return _decode_bool(raw)


async def assert_session_key_revoked(
    nexus_addr: str,
    module_addr: str,
    evm_client: Any,
    *,
    module_type: int = NEXUS_MODULE_TYPE_VALIDATOR,
) -> bool:
    """Returns True ONLY when the on-chain mirror confirms the module
    is NOT installed. Returns False on RPC failure or when the module
    is still installed.

    This is the spec-§1 invariant gate the state-machine consults
    before flipping the session-key policy to "revoked" in the
    unified state store (V7-075). The asymmetry — False on RPC failure
    — matches the safety direction for revoke (a stale "revoked"
    would let an attacker keep using the key, which is the bug we're
    closing). The state-machine MUST re-poll on False to make progress.
    """
    try:
        still_active = await is_session_key_active_on_chain(
            nexus_addr,
            module_addr,
            evm_client,
            module_type=module_type,
        )
    except Exception:
        # RPC failure — cannot confirm revocation. SAFE default: False.
        return False
    return not still_active
