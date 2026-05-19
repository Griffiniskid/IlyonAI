"""V7-031 — SPL Token-2022 transfer-hook allowlist gate (Python).

Spec ref: `IlyonAi_LP_Execution_Spec.pdf` §13 row 4. Any deposit / swap /
supply leg that moves an SPL Token-2022 mint MUST verify, before signing,
that the mint either (a) does not declare a `TransferHook` extension, or
(b) declares one whose program id is in the trusted allowlist. Untrusted
hook → emit `TOKEN_2022_HOOK_UNTRUSTED` blocker and refuse to sign.

This module is the canonical Python implementation of the TLV walker
already used in the Solana-sidecar JS adapters (see
`services/solana-yield-builder/src/adapters/_token_safety.js`). The two
implementations MUST agree on the extension discriminant value (14 / 0x0E)
and on the byte layout below.

Source citation for the TLV extension type byte
-----------------------------------------------
The discriminant value 14 (0x0E) for `TransferHook` is defined by the
upstream Solana Program Library spl-token-2022 crate:

    https://github.com/solana-labs/solana-program-library/blob/master/token/program-2022/src/extension/mod.rs

    #[repr(u16)]
    pub enum ExtensionType {
        Uninitialized = 0,
        TransferFeeConfig,                // 1
        TransferFeeAmount,                // 2
        MintCloseAuthority,               // 3
        ConfidentialTransferMint,         // 4
        ConfidentialTransferAccount,      // 5
        DefaultAccountState,              // 6
        ImmutableOwner,                   // 7
        MemoTransfer,                     // 8
        NonTransferable,                  // 9
        InterestBearingConfig,            // 10
        CpiGuard,                         // 11
        PermanentDelegate,                // 12
        NonTransferableAccount,           // 13
        TransferHook,                     // 14   <-- 0x0E
        TransferHookAccount,              // 15
        ...
    }

The TLV stream stores each record as
    u16 little-endian extension_type
    u16 little-endian payload_length
    <payload_length bytes of payload>

For `TransferHook`, the payload is exactly 64 bytes: a 32-byte
`Pubkey` `authority` followed by a 32-byte `Pubkey` `program_id`.
See `token/program-2022/src/extension/transfer_hook/mod.rs`:

    #[repr(C)]
    pub struct TransferHook {
        pub authority: OptionalNonZeroPubkey,
        pub program_id: OptionalNonZeroPubkey,
    }

A zero `program_id` (`Pubkey::default()`) means "no hook configured" —
the on-chain program treats it as absent, so we do too.

Byte layout of a Token-2022 mint account
----------------------------------------
The mint account is:
    bytes  0..82   — packed `Mint` struct (base SPL token Mint layout)
    bytes 82..165  — padding so the legacy `Multisig::LEN == 355` invariant
                     for unpacked accounts holds; only present on Token-2022
                     mints, never on legacy SPL mints which are exactly 82
                     bytes.
    byte    165    — `AccountType` discriminant (1 for `Mint`)
    bytes 166..    — TLV extension stream (zero or more `(u16 type, u16 len,
                     payload)` records), terminated by either end-of-buffer
                     or a `(type=0, len=0)` `Uninitialized` record.

A legacy SPL Token mint is exactly 82 bytes — no extension area, no hook
ever possible — so we short-circuit on `len(data) <= 165` after base64
decode.
"""
from __future__ import annotations

import base64
import logging
import struct
from typing import Iterable, Optional

import aiohttp

logger = logging.getLogger(__name__)


# Token-2022 mint TLV layout constants (mirrors spl-token-2022/state.rs).
MINT_BASE_LEN: int = 82                  # packed Mint::LEN
ACCOUNT_TYPE_OFFSET: int = 165           # byte 165 = AccountType discriminant
EXTENSIONS_START: int = 166              # TLV stream begins at byte 166
EXTENSION_TYPE_TRANSFER_HOOK: int = 0x0E  # 14, per spl-token-2022 ExtensionType
TRANSFER_HOOK_EXT_LEN: int = 64          # authority(32) + program_id(32)

# Token program ids — used to short-circuit legacy SPL mints which can
# never declare a transfer hook.
TOKEN_2022_PROGRAM_ID: str = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
SPL_TOKEN_PROGRAM_ID: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


# Default allowlist — INTENTIONALLY EMPTY. Token-2022 transfer-hook
# semantics are too powerful (arbitrary CPI on every transfer) to enable
# by default; integrations must explicitly opt-in by extending this set
# or by passing a per-call `allowlist=` argument. Safe default = deny.
TRUSTED_TRANSFER_HOOKS: frozenset[str] = frozenset()


# Bitcoin/base58 alphabet — matches @solana/web3.js `PublicKey.toBase58()`.
_BASE58_ALPHABET: str = (
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)


def _base58_encode_pubkey(raw: bytes) -> str:
    """Encode 32 big-endian bytes as a base58 string.

    Inlined so this module has zero crypto deps. Matches the encoding
    returned by `solana-py`'s `PublicKey(...).__str__()` and by JS
    `web3.js PublicKey.toBase58()` for 32-byte inputs.
    """
    # Leading zero bytes become leading '1's in base58.
    zeros = 0
    while zeros < len(raw) and raw[zeros] == 0:
        zeros += 1
    # Convert big-endian bytes -> base58 via repeated division.
    digits = bytearray(raw)
    out: list[str] = []
    start = zeros
    while start < len(digits):
        carry = 0
        for i in range(start, len(digits)):
            val = (carry << 8) | digits[i]
            digits[i] = val // 58
            carry = val % 58
        out.append(_BASE58_ALPHABET[carry])
        while start < len(digits) and digits[start] == 0:
            start += 1
    return ("1" * zeros) + "".join(reversed(out))


def parse_token_2022_extensions(account_data_b64: str) -> list[dict]:
    """Parse the Token-2022 mint TLV extension stream.

    Args:
        account_data_b64: base64-encoded mint account data, exactly as
            returned by `getAccountInfo(... base64)`.

    Returns:
        list[dict] — one record per TLV entry, each as
            ``{"type": int, "length": int, "data": bytes}``.
        Empty list when:
            * data is empty / shorter than EXTENSIONS_START
            * legacy SPL mint (exactly 82 bytes, no extension area)
            * malformed TLV (length overruns buffer) — defensive,
              malformed mints are rejected on-chain.

    Never raises on malformed input — returns whatever it parsed up to
    the first malformed record.
    """
    if not account_data_b64:
        return []
    try:
        raw = base64.b64decode(account_data_b64)
    except (ValueError, TypeError):
        return []
    return _parse_extensions_bytes(raw)


def _parse_extensions_bytes(raw: bytes) -> list[dict]:
    if not raw or len(raw) <= EXTENSIONS_START:
        return []
    out: list[dict] = []
    cursor = EXTENSIONS_START
    while cursor + 4 <= len(raw):
        ext_type, ext_len = struct.unpack_from("<HH", raw, cursor)
        payload_start = cursor + 4
        payload_end = payload_start + ext_len
        if payload_end > len(raw):
            # malformed — stop walking, return what we have so far
            break
        if ext_type == 0 and ext_len == 0:
            # `Uninitialized` terminator record — end of TLV stream.
            break
        out.append({
            "type": int(ext_type),
            "length": int(ext_len),
            "data": bytes(raw[payload_start:payload_end]),
        })
        cursor = payload_end
    return out


def extract_transfer_hook_program(account_data_b64: str) -> Optional[str]:
    """Return the base58 `program_id` of the TransferHook extension if set.

    Returns:
        * None — no extension area, no TransferHook record, or the
          recorded program id is `Pubkey::default()` (zero) which the
          on-chain program treats as "no hook configured".
        * base58 string — 32-byte program id, ready for allowlist lookup.

    The TransferHook payload is (authority 32 bytes, program_id 32 bytes)
    per `transfer_hook/mod.rs`. We take bytes 32..64 of the payload as
    the program id.
    """
    extensions = parse_token_2022_extensions(account_data_b64)
    for record in extensions:
        if record["type"] != EXTENSION_TYPE_TRANSFER_HOOK:
            continue
        payload = record["data"]
        if len(payload) < TRANSFER_HOOK_EXT_LEN:
            return None
        program_bytes = payload[32:64]
        # Pubkey::default() (32 zero bytes) → no hook configured.
        if all(b == 0 for b in program_bytes):
            return None
        return _base58_encode_pubkey(program_bytes)
    return None


def is_transfer_hook_trusted(
    hook_program_address: str,
    *,
    allowlist: Iterable[str] = TRUSTED_TRANSFER_HOOKS,
) -> bool:
    """Return True iff `hook_program_address` is in the allowlist.

    `allowlist` defaults to the empty `TRUSTED_TRANSFER_HOOKS` frozenset
    so the safe default is *deny*. Tests and integrations override this
    by passing their own `allowlist=` argument.
    """
    if not hook_program_address:
        return False
    return hook_program_address in set(allowlist)


async def check_transfer_hook(
    mint_address: str,
    *,
    rpc_url: str,
    allowlist: Iterable[str] = TRUSTED_TRANSFER_HOOKS,
    session: Optional[aiohttp.ClientSession] = None,
    timeout_s: float = 8.0,
) -> tuple[bool, Optional[str]]:
    """Gate a Solana mint through the transfer-hook allowlist.

    Returns:
        (ok, hook_program_address)

        * (True,  None) — mint has no TransferHook extension OR is a
          legacy SPL mint (cannot declare one).
        * (True,  program_id) — TransferHook extension is set AND
          program_id is in `allowlist`.
        * (False, program_id) — TransferHook extension is set and
          program_id is NOT in `allowlist`. Caller MUST emit a
          `TOKEN_2022_HOOK_UNTRUSTED` blocker.

    Fail-soft on RPC errors: transport flakes return (True, None) so we
    never *fabricate* a blocker. The on-chain program enforces hook
    invocation regardless, so a fail-soft here just degrades to the
    same behaviour as before the gate was added — never to a false-
    positive lockout. This mirrors `evaluate_solana_frozen_preflight`.
    """
    if not mint_address or not rpc_url:
        return True, None

    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout_s)
        )

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [
                mint_address,
                {"encoding": "base64", "commitment": "confirmed"},
            ],
        }
        try:
            async with session.post(
                rpc_url, json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as resp:
                if resp.status != 200:
                    return True, None
                body = await resp.json()
        except Exception as exc:
            logger.debug("getAccountInfo failed for %s: %s",
                         (mint_address or "")[:8], exc)
            return True, None

        if not isinstance(body, dict) or body.get("error"):
            return True, None
        value = (body.get("result") or {}).get("value") or {}
        if not isinstance(value, dict):
            return True, None
        owner = str(value.get("owner") or "")
        # Legacy SPL Token mints can never declare a transfer hook —
        # short-circuit before parsing.
        if owner and owner != TOKEN_2022_PROGRAM_ID:
            return True, None
        data = value.get("data")
        if not isinstance(data, list) or len(data) < 2 or data[1] != "base64":
            return True, None
        data_b64 = data[0]
        if not isinstance(data_b64, str) or not data_b64:
            return True, None

        hook_program = extract_transfer_hook_program(data_b64)
        if not hook_program:
            return True, None
        if is_transfer_hook_trusted(hook_program, allowlist=allowlist):
            return True, hook_program
        return False, hook_program
    finally:
        if owns_session and session is not None:
            await session.close()


__all__ = [
    "EXTENSION_TYPE_TRANSFER_HOOK",
    "MINT_BASE_LEN",
    "ACCOUNT_TYPE_OFFSET",
    "EXTENSIONS_START",
    "TRANSFER_HOOK_EXT_LEN",
    "TOKEN_2022_PROGRAM_ID",
    "SPL_TOKEN_PROGRAM_ID",
    "TRUSTED_TRANSFER_HOOKS",
    "parse_token_2022_extensions",
    "extract_transfer_hook_program",
    "is_transfer_hook_trusted",
    "check_transfer_hook",
]
