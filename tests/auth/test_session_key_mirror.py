"""V7-073 — Pin test for the on-chain session-key mirror check.

Verifies that `src/auth/session_key_mirror.py`:

  1. Builds the canonical `isModuleInstalled(uint256,address,bytes)`
     calldata with the right selector (0x112d3a7d) and arg encoding.
  2. `is_session_key_active_on_chain` returns True when the mocked
     Nexus call returns the boolean-true ABI encoding (0x000...01).
  3. Returns False when the mocked call returns false (0x000...00).
  4. Returns False on RPC failure (the SAFE default — revoke verifier
     must not declare a still-active key revoked).
  5. `assert_session_key_revoked` is the inverse — True iff the
     mirror reports NOT installed.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.auth.session_key_mirror import (
    NEXUS_IS_MODULE_INSTALLED_SELECTOR,
    NEXUS_MODULE_TYPE_VALIDATOR,
    assert_session_key_revoked,
    build_is_module_installed_calldata,
    is_session_key_active_on_chain,
)


_NEXUS_ADDR = "0x" + "ab" * 20
_MODULE_ADDR = "0x" + "cd" * 20


class _MockEvmClient:
    """Records every call(to, data) tuple and returns a fixed hex string."""

    def __init__(self, return_value: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self.return_value = return_value

    async def call(self, to: str, data: str) -> str:
        self.calls.append((to, data))
        return self.return_value


class _ExplodingEvmClient:
    """Mock that raises on every call — for the RPC-failure path."""

    async def call(self, to: str, data: str) -> str:  # pragma: no cover - raises
        raise RuntimeError("rpc dead")


def test_calldata_uses_canonical_selector():
    """Built calldata starts with the 0x112d3a7d isModuleInstalled selector."""
    cd = build_is_module_installed_calldata(
        module_type=NEXUS_MODULE_TYPE_VALIDATOR,
        module_address=_MODULE_ADDR,
    )
    assert cd.lower().startswith(NEXUS_IS_MODULE_INSTALLED_SELECTOR)


def test_calldata_embeds_module_address():
    """The module address (lowercased, zero-padded) appears in the calldata."""
    cd = build_is_module_installed_calldata(
        module_type=NEXUS_MODULE_TYPE_VALIDATOR,
        module_address=_MODULE_ADDR,
    )
    # cd lower → contains 40-char address without the 0x prefix.
    assert "cd" * 20 in cd.lower()


def test_is_session_key_active_returns_true_when_mock_returns_true():
    """Mocked Nexus.isModuleInstalled returns 1 → helper returns True."""
    mock = _MockEvmClient(return_value="0x" + "0" * 63 + "1")
    result = asyncio.run(
        is_session_key_active_on_chain(_NEXUS_ADDR, _MODULE_ADDR, mock)
    )
    assert result is True
    # And the EVM client was actually called with the Nexus account
    # as the `to` and a 0x112d3a7d-prefixed payload.
    assert len(mock.calls) == 1
    to, data = mock.calls[0]
    assert to == _NEXUS_ADDR
    assert data.lower().startswith(NEXUS_IS_MODULE_INSTALLED_SELECTOR)


def test_is_session_key_active_returns_false_when_mock_returns_false():
    """Mocked return = 0x000...00 → not installed."""
    mock = _MockEvmClient(return_value="0x" + "0" * 64)
    result = asyncio.run(
        is_session_key_active_on_chain(_NEXUS_ADDR, _MODULE_ADDR, mock)
    )
    assert result is False


def test_is_session_key_active_propagates_rpc_failure():
    """RPC raise propagates through is_session_key_active_on_chain —
    callers (assert_session_key_revoked) decide the safety direction."""
    with pytest.raises(RuntimeError, match="rpc dead"):
        asyncio.run(
            is_session_key_active_on_chain(
                _NEXUS_ADDR, _MODULE_ADDR, _ExplodingEvmClient()
            )
        )


def test_assert_session_key_revoked_true_when_mirror_says_not_installed():
    """Mirror returns false → revoked=True."""
    mock = _MockEvmClient(return_value="0x" + "0" * 64)
    result = asyncio.run(assert_session_key_revoked(_NEXUS_ADDR, _MODULE_ADDR, mock))
    assert result is True


def test_assert_session_key_revoked_false_when_still_installed():
    """Mirror returns true → revoked=False (do NOT declare it gone)."""
    mock = _MockEvmClient(return_value="0x" + "0" * 63 + "1")
    result = asyncio.run(assert_session_key_revoked(_NEXUS_ADDR, _MODULE_ADDR, mock))
    assert result is False


def test_assert_session_key_revoked_false_on_rpc_failure():
    """RPC raise → revoked=False (safety direction: don't flip on
    failure; the next poll will retry the mirror check)."""
    result = asyncio.run(
        assert_session_key_revoked(_NEXUS_ADDR, _MODULE_ADDR, _ExplodingEvmClient())
    )
    assert result is False
