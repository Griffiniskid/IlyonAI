"""EIP-7702 smart-account helpers — Phase 7 foundation.

EIP-7702 lets an EOA temporarily upgrade to a smart-contract account by
including an authorization tuple in a tx. After the auth lands, the EOA
behaves like the implementation contract for that block range, so a
single UserOp can batch approve+supply+claim flows that would otherwise
need 3 popups.

Anatomy of a 7702 authorization:
    [chain_id, address, nonce, y_parity, r, s]
where (address) is the implementation the EOA delegates to and (r,s,y)
is the EOA's signature over keccak256(MAGIC || rlp([chain_id, address, nonce])).

This module ships the EIP-7702 digest computation + signature unpacking
needed by the runtime to construct a valid auth tuple. Biconomy Nexus
implementation address is the default delegation target; ZeroDev's
Kernel and Safe-7579 can drop in by overriding `implementation_address`.

Frontend sends the tx via eth_sendTransaction with the auth list, and
the orchestrator records the authorization so subsequent UserOps reuse it.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    from eth_utils import keccak as _keccak
except ImportError:  # pragma: no cover
    _keccak = None


# EIP-7702 magic byte (per EIP-7702 spec). Prepended to the RLP before keccak.
MAGIC_BYTE = b"\x05"

# Biconomy Nexus default implementation across all chains where it's deployed
# (per Biconomy docs). ZeroDev Kernel / Safe-7579 can drop in by override.
BICONOMY_NEXUS_IMPL = "0x000000aC74357BFEa72BBD0781833631F732cf19"


@dataclass(frozen=True)
class Eip7702Authorization:
    chain_id: int
    implementation: str
    nonce: int
    y_parity: int
    r: bytes
    s: bytes

    def to_tuple(self) -> tuple[int, str, int, int, bytes, bytes]:
        return (self.chain_id, self.implementation, self.nonce, self.y_parity, self.r, self.s)


def _rlp_encode_authorization(chain_id: int, implementation: str, nonce: int) -> bytes:
    """Minimal RLP encoder for the 3-element authorization tuple.

    Avoids pulling in `rlp` dependency for the single-shape case we need —
    EIP-7702 auth is always (uint, address, uint).
    """
    def _rlp_int(v: int) -> bytes:
        if v == 0:
            return b"\x80"
        b = v.to_bytes((v.bit_length() + 7) // 8, "big")
        return _rlp_bytes(b)

    def _rlp_bytes(b: bytes) -> bytes:
        if len(b) == 1 and b[0] < 0x80:
            return b
        if len(b) < 56:
            return bytes([0x80 + len(b)]) + b
        ll = len(b).to_bytes((len(b).bit_length() + 7) // 8, "big")
        return bytes([0xb7 + len(ll)]) + ll + b

    def _rlp_list(items: list[bytes]) -> bytes:
        payload = b"".join(items)
        if len(payload) < 56:
            return bytes([0xc0 + len(payload)]) + payload
        ll = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
        return bytes([0xf7 + len(ll)]) + ll + payload

    impl_bytes = bytes.fromhex(implementation.removeprefix("0x").lower())
    if len(impl_bytes) != 20:
        raise ValueError(f"implementation address must be 20 bytes, got {len(impl_bytes)}")
    items = [_rlp_int(chain_id), _rlp_bytes(impl_bytes), _rlp_int(nonce)]
    return _rlp_list(items)


def authorization_digest(
    *, chain_id: int, implementation: str, nonce: int,
) -> bytes:
    """Returns the 32-byte digest the EOA must sign for the authorization
    tuple to be valid. Caller passes the digest to MetaMask's
    `personal_sign` (with `\x19\x01` prefix handled by Permit2-style typed
    signing) or constructs the signature server-side from a known key.
    """
    if _keccak is None:
        raise RuntimeError("eth_utils.keccak required for EIP-7702 digest")
    payload = MAGIC_BYTE + _rlp_encode_authorization(chain_id, implementation, nonce)
    return _keccak(payload)


def build_authorization_from_signature(
    *, chain_id: int, implementation: str, nonce: int,
    signature_hex: str,
) -> Eip7702Authorization:
    """Wrap the EOA signature into the authorization tuple shape expected
    by the tx encoder. `signature_hex` is the 65-byte (r || s || v) blob.
    """
    sig = bytes.fromhex(signature_hex.removeprefix("0x"))
    if len(sig) != 65:
        raise ValueError(f"signature must be 65 bytes, got {len(sig)}")
    r, s, v = sig[:32], sig[32:64], sig[64]
    # y_parity for EIP-7702 is 0 or 1 (v - 27 normalisation).
    if v >= 27:
        y_parity = v - 27
    else:
        y_parity = v
    if y_parity not in (0, 1):
        raise ValueError(f"y_parity must be 0 or 1, got {y_parity}")
    return Eip7702Authorization(
        chain_id=chain_id,
        implementation=implementation.lower(),
        nonce=nonce,
        y_parity=y_parity,
        r=r,
        s=s,
    )
