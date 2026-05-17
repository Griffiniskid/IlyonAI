"""V7-007 pin tests for SPL frozen-account preflight.

Spec ref: `IlyonAi_LP_Execution_Spec.pdf` §13 row 5 — FROZEN_ACCOUNT blocker
must fire when getTokenAccountsByOwner + getAccountInfo say the user's SPL
token account for the planned mint is in state=Frozen (2).

These tests use a fake aiohttp.ClientSession that returns hard-coded RPC
responses, so no live Solana RPC traffic happens.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any

import pytest

from src.data.solana import check_account_frozen
from src.shield.preflight_solana import evaluate_solana_frozen_preflight


MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
OWNER = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"
TOKEN_ACCT = "DRpbCBMxVnDK7maPM5tGv6MvB3v1sRMC86PZ8okm21hy"


# ---------------------------------------------------------------------------
# Fake aiohttp.ClientSession that responds to specific JSON-RPC methods.
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


class FakeSession:
    """aiohttp-shaped fake — supports `async with .post(...)` and
    `await .close()`. Maps (method) → response payload via `responses`."""

    def __init__(self, responses: dict[str, Any], programs_in_token_lookup: set[str] | None = None):
        # responses keys: "getTokenAccountsByOwner", "getAccountInfo"
        self.responses = responses
        self.programs_in_token_lookup = programs_in_token_lookup or {
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        }
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def post(self, url: str, json: dict | None = None, timeout: Any = None, **kw):
        method = (json or {}).get("method", "")
        self.calls.append({"url": url, "method": method, "params": (json or {}).get("params")})

        if method == "getTokenAccountsByOwner":
            params = (json or {}).get("params") or []
            program_id = ""
            if len(params) >= 2 and isinstance(params[1], dict):
                program_id = params[1].get("programId", "")
            # Only the legacy Token program returns an account; Token-2022
            # returns an empty list. This mirrors the real RPC behaviour
            # for USDC (issued under legacy SPL Token).
            if program_id in self.programs_in_token_lookup:
                return _FakeResp(self.responses.get("getTokenAccountsByOwner", {}))
            return _FakeResp({"jsonrpc": "2.0", "id": 1, "result": {"value": []}})

        if method == "getAccountInfo":
            return _FakeResp(self.responses.get("getAccountInfo", {}))

        return _FakeResp({"jsonrpc": "2.0", "id": 1, "result": None})

    async def close(self):
        self.closed = True


def _by_owner_response(state_str: str | None) -> dict:
    """Build a getTokenAccountsByOwner jsonParsed response.

    state_str: "frozen", "initialized", "uninitialized" — or None for
    base64-only encoding (forces the byte-decode fallback path).
    """
    if state_str is None:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "value": [
                    {
                        "pubkey": TOKEN_ACCT,
                        "account": {
                            "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                            "data": "base64-fallback-marker",
                        },
                    }
                ]
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "value": [
                {
                    "pubkey": TOKEN_ACCT,
                    "account": {
                        "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                        "data": {
                            "program": "spl-token",
                            "parsed": {
                                "type": "account",
                                "info": {
                                    "mint": MINT,
                                    "owner": OWNER,
                                    "state": state_str,
                                    "tokenAmount": {
                                        "amount": "1000000",
                                        "decimals": 6,
                                        "uiAmount": 1.0,
                                        "uiAmountString": "1",
                                    },
                                },
                            },
                            "space": 165,
                        },
                    },
                }
            ]
        },
    }


def _account_info_for_state(state_byte: int) -> dict:
    """Synthesise a 165-byte SPL Account blob with the given state at offset 108."""
    raw = bytearray(165)
    raw[108] = state_byte
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "value": {
                "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                "data": [base64.b64encode(bytes(raw)).decode("ascii"), "base64"],
            }
        },
    }


# ---------------------------------------------------------------------------
# check_account_frozen — direct unit pins
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_frozen_state_returns_true():
    """state=2 (Frozen) via jsonParsed → check_account_frozen returns True."""
    session = FakeSession(responses={
        "getTokenAccountsByOwner": _by_owner_response("frozen"),
    })
    result = await check_account_frozen(
        mint=MINT,
        owner=OWNER,
        rpc_url="https://fake.solana.rpc",
        session=session,
    )
    assert result is True
    # Verify we asked the RPC for token accounts (parallel Token + Token-2022).
    methods = [c["method"] for c in session.calls]
    assert methods.count("getTokenAccountsByOwner") == 2


@pytest.mark.asyncio
async def test_initialized_state_returns_false():
    """state=1 (Initialized) via jsonParsed → check_account_frozen returns False."""
    session = FakeSession(responses={
        "getTokenAccountsByOwner": _by_owner_response("initialized"),
    })
    result = await check_account_frozen(
        mint=MINT,
        owner=OWNER,
        rpc_url="https://fake.solana.rpc",
        session=session,
    )
    assert result is False


@pytest.mark.asyncio
async def test_uninitialized_state_returns_false():
    """state=0 (Uninitialized) via jsonParsed → check_account_frozen returns False."""
    session = FakeSession(responses={
        "getTokenAccountsByOwner": _by_owner_response("uninitialized"),
    })
    result = await check_account_frozen(
        mint=MINT,
        owner=OWNER,
        rpc_url="https://fake.solana.rpc",
        session=session,
    )
    assert result is False


@pytest.mark.asyncio
async def test_no_token_account_returns_false():
    """Owner has no SPL account for this mint → False (no blocker)."""
    session = FakeSession(responses={
        "getTokenAccountsByOwner": {
            "jsonrpc": "2.0", "id": 1, "result": {"value": []},
        },
    })
    result = await check_account_frozen(
        mint=MINT,
        owner=OWNER,
        rpc_url="https://fake.solana.rpc",
        session=session,
    )
    assert result is False


@pytest.mark.asyncio
async def test_base64_fallback_path_frozen():
    """When jsonParsed isn't returned, fall back to base64 byte-decode.
    State byte 2 at offset 108 → Frozen → True."""
    session = FakeSession(responses={
        "getTokenAccountsByOwner": _by_owner_response(None),
        "getAccountInfo": _account_info_for_state(2),
    })
    result = await check_account_frozen(
        mint=MINT,
        owner=OWNER,
        rpc_url="https://fake.solana.rpc",
        session=session,
    )
    assert result is True


@pytest.mark.asyncio
async def test_base64_fallback_path_initialized():
    """base64 fallback, state byte 1 (Initialized) → False."""
    session = FakeSession(responses={
        "getTokenAccountsByOwner": _by_owner_response(None),
        "getAccountInfo": _account_info_for_state(1),
    })
    result = await check_account_frozen(
        mint=MINT,
        owner=OWNER,
        rpc_url="https://fake.solana.rpc",
        session=session,
    )
    assert result is False


@pytest.mark.asyncio
async def test_rpc_error_fail_soft():
    """Malformed/error RPC payload must NOT synthesise a frozen=True."""
    session = FakeSession(responses={
        "getTokenAccountsByOwner": {
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32603, "message": "internal RPC overload"},
        },
    })
    result = await check_account_frozen(
        mint=MINT,
        owner=OWNER,
        rpc_url="https://fake.solana.rpc",
        session=session,
    )
    assert result is False


# ---------------------------------------------------------------------------
# evaluate_solana_frozen_preflight — pipeline-level pins
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pipeline_emits_blocker_when_frozen(monkeypatch):
    """Pipeline returns one FROZEN_ACCOUNT blocker per frozen (mint, owner)."""

    async def _fake_check(mint, owner, rpc_url, *, session=None, timeout_s=8.0):
        # USDC mint pretends to be frozen, USDT does not.
        return mint == MINT

    monkeypatch.setattr(
        "src.shield.preflight_solana.check_account_frozen",
        _fake_check,
    )
    pairs = [
        (MINT, OWNER),                                                  # frozen
        ("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", OWNER),         # not frozen
    ]
    blockers = await evaluate_solana_frozen_preflight(
        pairs=pairs,
        rpc_url="https://fake.solana.rpc",
        affected_step_ids=["step_001", "step_002"],
    )
    assert len(blockers) == 1
    blk = blockers[0]
    assert blk.code == "FROZEN_ACCOUNT"
    assert blk.severity == "blocker"
    assert blk.recoverable is True
    assert "step_001" in blk.affected_step_ids
    assert MINT in blk.detail


@pytest.mark.asyncio
async def test_pipeline_no_blocker_when_all_initialized(monkeypatch):
    """No blocker emitted when every pair is initialized/uninitialized."""

    async def _fake_check(mint, owner, rpc_url, *, session=None, timeout_s=8.0):
        return False  # nothing frozen

    monkeypatch.setattr(
        "src.shield.preflight_solana.check_account_frozen",
        _fake_check,
    )
    pairs = [(MINT, OWNER)]
    blockers = await evaluate_solana_frozen_preflight(
        pairs=pairs,
        rpc_url="https://fake.solana.rpc",
    )
    assert blockers == []


@pytest.mark.asyncio
async def test_pipeline_dedupes_pairs(monkeypatch):
    """Duplicate (mint, owner) pairs must only result in a single check."""
    call_log: list[tuple[str, str]] = []

    async def _fake_check(mint, owner, rpc_url, *, session=None, timeout_s=8.0):
        call_log.append((mint, owner))
        return True

    monkeypatch.setattr(
        "src.shield.preflight_solana.check_account_frozen",
        _fake_check,
    )
    pairs = [(MINT, OWNER), (MINT, OWNER), (MINT, OWNER)]
    blockers = await evaluate_solana_frozen_preflight(
        pairs=pairs,
        rpc_url="https://fake.solana.rpc",
    )
    assert len(call_log) == 1
    assert len(blockers) == 1


@pytest.mark.asyncio
async def test_pipeline_empty_pairs_returns_empty():
    """Empty input → empty blocker list. No RPC traffic."""
    blockers = await evaluate_solana_frozen_preflight(
        pairs=[],
        rpc_url="https://fake.solana.rpc",
    )
    assert blockers == []


@pytest.mark.asyncio
async def test_pipeline_swallows_check_exception(monkeypatch):
    """A raising check_account_frozen → treated as 'not frozen' (fail-soft)."""

    async def _boom(mint, owner, rpc_url, *, session=None, timeout_s=8.0):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "src.shield.preflight_solana.check_account_frozen",
        _boom,
    )
    blockers = await evaluate_solana_frozen_preflight(
        pairs=[(MINT, OWNER)],
        rpc_url="https://fake.solana.rpc",
    )
    assert blockers == []
