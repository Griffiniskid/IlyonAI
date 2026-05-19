"""V7-031 pin tests for the SPL Token-2022 transfer-hook allowlist gate.

Spec ref: `IlyonAi_LP_Execution_Spec.pdf` §13 row 4 — any deposit / swap /
supply leg of a Token-2022 mint MUST pass an allowlist check on the
TransferHook extension's program id before signing. The extension type
discriminant is 14 (0x0E) per the upstream spl-token-2022
ExtensionType enum (see module docstring of
`src.shield.spl_transfer_hook` for the source citation).

These tests cover:
  * empty / legacy-shaped data → no extensions surfaced
  * TLV with type=0x0E + 32-byte hook program id → extracted to base58
  * trusted hook (test allowlist) → True
  * untrusted hook (default empty allowlist) → False
  * `check_transfer_hook` end-to-end with mocked RPC: extension present +
    untrusted → returns (False, hook_addr)
"""
from __future__ import annotations

import asyncio
import base64
import struct
from typing import Any

import pytest

from src.shield.spl_transfer_hook import (
    EXTENSION_TYPE_TRANSFER_HOOK,
    EXTENSIONS_START,
    TOKEN_2022_PROGRAM_ID,
    check_transfer_hook,
    extract_transfer_hook_program,
    is_transfer_hook_trusted,
    parse_token_2022_extensions,
    _base58_encode_pubkey,
)


# A fake 32-byte hook program id, used as the canonical "untrusted hook"
# across the test suite.
FAKE_HOOK_BYTES = bytes(range(1, 33))  # 0x01..0x20 — non-zero, deterministic
FAKE_HOOK_B58 = _base58_encode_pubkey(FAKE_HOOK_BYTES)


def _build_mint_account_with_hook(
    hook_program_bytes: bytes | None,
    *,
    hook_authority_bytes: bytes | None = None,
    trailing_padding: int = 0,
) -> bytes:
    """Build a Token-2022 mint account buffer with an optional TransferHook
    TLV record at EXTENSIONS_START.

    Layout:
        [0..82)    Mint base (zeroed — content irrelevant for the parser)
        [82..165)  padding to AccountType offset
        [165]      AccountType=1 (Mint)
        [166..]    TLV stream:
                     u16 LE ext_type   (= 14 = TransferHook)
                     u16 LE ext_len    (= 64)
                     64 bytes payload  (authority || program_id)
                     [optional trailing zero padding]
    """
    buf = bytearray(EXTENSIONS_START - 1)          # bytes 0..164 zeroed (Mint base + pad)
    buf.append(1)                                   # byte 165 = AccountType = Mint
    if hook_program_bytes is not None:
        auth = hook_authority_bytes or (b"\x00" * 32)
        assert len(auth) == 32
        assert len(hook_program_bytes) == 32
        # TLV header: type=14 (0x0E), length=64
        buf.extend(struct.pack("<HH", EXTENSION_TYPE_TRANSFER_HOOK, 64))
        buf.extend(auth)                           # authority (32B)
        buf.extend(hook_program_bytes)             # program_id (32B)
    if trailing_padding > 0:
        buf.extend(b"\x00" * trailing_padding)
    return bytes(buf)


# ---------------------------------------------------------------------------
# Fake aiohttp ClientSession that responds to a single getAccountInfo call.
# Mirrors the pattern used by tests/shield/test_frozen_account.py so the
# transfer-hook gate exercises the exact same RPC surface.
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, payload: Any, status: int = 200):
        self._payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._payload


class FakeRpcSession:
    """Returns a fixed getAccountInfo response. Tracks calls for assertions."""

    def __init__(self, account_data_b64: str | None, owner: str = TOKEN_2022_PROGRAM_ID):
        if account_data_b64 is None:
            self._value = None
        else:
            self._value = {"owner": owner, "data": [account_data_b64, "base64"]}
        self.calls: list[dict] = []
        self.closed = False

    def post(self, url: str, json: dict | None = None, timeout: Any = None, **kw):
        method = (json or {}).get("method", "")
        self.calls.append({"url": url, "method": method, "params": (json or {}).get("params")})
        body = {"jsonrpc": "2.0", "id": 1, "result": {"value": self._value, "context": {"slot": 1}}}
        return _FakeResp(body)

    async def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_parse_empty_data_returns_no_extensions():
    assert parse_token_2022_extensions("") == []
    # Legacy 82-byte mint — short-circuits before TLV walker
    legacy_82 = base64.b64encode(b"\x00" * 82).decode("ascii")
    assert parse_token_2022_extensions(legacy_82) == []
    # A Token-2022 mint with NO extension records (account-type byte only).
    # Bytes 0..164 are Mint+pad, byte 165 is AccountType=1, no TLV after.
    just_account_type = base64.b64encode(bytes(EXTENSIONS_START - 1) + b"\x01").decode("ascii")
    assert parse_token_2022_extensions(just_account_type) == []


def test_parse_transfer_hook_extension_extracts_program_id():
    raw = _build_mint_account_with_hook(FAKE_HOOK_BYTES)
    data_b64 = base64.b64encode(raw).decode("ascii")

    exts = parse_token_2022_extensions(data_b64)
    assert len(exts) == 1
    assert exts[0]["type"] == EXTENSION_TYPE_TRANSFER_HOOK
    assert exts[0]["type"] == 14  # spec-pinned discriminant
    assert exts[0]["length"] == 64
    # Payload is authority(32) || program_id(32)
    assert exts[0]["data"][32:64] == FAKE_HOOK_BYTES

    hook = extract_transfer_hook_program(data_b64)
    assert hook == FAKE_HOOK_B58


def test_zero_program_id_is_treated_as_no_hook():
    # All-zero program_id == Pubkey::default() — on-chain meaning is
    # "no hook configured", so extract should return None.
    raw = _build_mint_account_with_hook(b"\x00" * 32)
    data_b64 = base64.b64encode(raw).decode("ascii")
    assert extract_transfer_hook_program(data_b64) is None


def test_is_transfer_hook_trusted_explicit_allowlist():
    allowlist = frozenset({FAKE_HOOK_B58})
    assert is_transfer_hook_trusted(FAKE_HOOK_B58, allowlist=allowlist) is True
    assert is_transfer_hook_trusted("SomeOtherProgram1111111111111111111111111111",
                                    allowlist=allowlist) is False


def test_untrusted_hook_default_allowlist_denies():
    # Default TRUSTED_TRANSFER_HOOKS is empty → every hook denied.
    assert is_transfer_hook_trusted(FAKE_HOOK_B58) is False
    # Empty / None inputs are always untrusted.
    assert is_transfer_hook_trusted("") is False


def test_check_transfer_hook_extension_present_untrusted():
    raw = _build_mint_account_with_hook(FAKE_HOOK_BYTES)
    data_b64 = base64.b64encode(raw).decode("ascii")
    session = FakeRpcSession(data_b64, owner=TOKEN_2022_PROGRAM_ID)

    ok, hook_addr = asyncio.run(check_transfer_hook(
        "MintAddressPlaceholder111111111111111111111",
        rpc_url="https://api.example.com",
        session=session,
    ))
    assert ok is False
    assert hook_addr == FAKE_HOOK_B58
    assert session.calls and session.calls[0]["method"] == "getAccountInfo"


def test_check_transfer_hook_trusted_passes():
    raw = _build_mint_account_with_hook(FAKE_HOOK_BYTES)
    data_b64 = base64.b64encode(raw).decode("ascii")
    session = FakeRpcSession(data_b64, owner=TOKEN_2022_PROGRAM_ID)

    ok, hook_addr = asyncio.run(check_transfer_hook(
        "MintAddressPlaceholder111111111111111111111",
        rpc_url="https://api.example.com",
        session=session,
        allowlist=frozenset({FAKE_HOOK_B58}),
    ))
    assert ok is True
    assert hook_addr == FAKE_HOOK_B58


def test_check_transfer_hook_legacy_spl_short_circuits():
    # Legacy SPL Token program — gate must return (True, None) without
    # parsing the extension area (a legacy mint can never declare a hook).
    raw = _build_mint_account_with_hook(FAKE_HOOK_BYTES)  # even if data is hook-shaped
    data_b64 = base64.b64encode(raw).decode("ascii")
    LEGACY_TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    session = FakeRpcSession(data_b64, owner=LEGACY_TOKEN)

    ok, hook_addr = asyncio.run(check_transfer_hook(
        "MintAddressPlaceholder111111111111111111111",
        rpc_url="https://api.example.com",
        session=session,
    ))
    assert ok is True
    assert hook_addr is None


def test_check_transfer_hook_no_extension_passes():
    # Token-2022 mint with no TLV record (only account-type byte at 165).
    raw = bytes(EXTENSIONS_START - 1) + b"\x01"
    data_b64 = base64.b64encode(raw).decode("ascii")
    session = FakeRpcSession(data_b64, owner=TOKEN_2022_PROGRAM_ID)

    ok, hook_addr = asyncio.run(check_transfer_hook(
        "MintAddressPlaceholder111111111111111111111",
        rpc_url="https://api.example.com",
        session=session,
    ))
    assert ok is True
    assert hook_addr is None


def test_malformed_tlv_short_circuits_to_none():
    # TLV header claims length 999, way past end-of-buffer.
    buf = bytearray(EXTENSIONS_START - 1)
    buf.append(1)                                  # byte 165 = AccountType
    buf.extend(struct.pack("<HH", EXTENSION_TYPE_TRANSFER_HOOK, 999))
    buf.extend(b"\x00" * 8)                        # only 8 bytes of "payload"
    data_b64 = base64.b64encode(bytes(buf)).decode("ascii")
    # Parser must not raise, and must not surface a phantom hook.
    assert extract_transfer_hook_program(data_b64) is None
