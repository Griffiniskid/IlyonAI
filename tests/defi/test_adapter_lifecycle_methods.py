"""Pin test for V6 §3.2 / Phase 3-5: YieldAdapter Protocol exposes 8 lifecycle methods.

The base Protocol must expose 8 optional lifecycle hooks
(build_increase, build_decrease, build_collect, build_close, build_rebalance,
build_withdraw, build_unstake, build_claim). Each default implementation must
raise NotImplementedError with the adapter name in the message, so unsupported
operations fail loudly. Adapters opt in by overriding.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from src.defi.execution.adapters.base import YieldAdapter


LIFECYCLE_METHODS = (
    "build_increase",
    "build_decrease",
    "build_collect",
    "build_close",
    "build_rebalance",
    "build_withdraw",
    "build_unstake",
    "build_claim",
)


def test_protocol_exposes_all_eight_lifecycle_methods() -> None:
    """YieldAdapter Protocol must declare all 8 lifecycle methods."""
    for name in LIFECYCLE_METHODS:
        assert hasattr(YieldAdapter, name), f"YieldAdapter missing lifecycle method {name!r}"
        attr = getattr(YieldAdapter, name)
        assert callable(attr), f"YieldAdapter.{name} must be callable"
        assert inspect.iscoroutinefunction(attr), (
            f"YieldAdapter.{name} must be an async coroutine function"
        )


def test_default_raises_notimplementederror_with_adapter_name() -> None:
    """Default implementations must raise NotImplementedError including the adapter id."""

    class _BareAdapter(YieldAdapter):  # type: ignore[misc]
        adapter_id = "bare_test_adapter"
        chains: set[str] = set()
        protocols: set[str] = set()
        actions: set[str] = set()

        def supports(self, *, chain, protocol, action):  # type: ignore[override]
            raise NotImplementedError

        async def quote(self, request):  # type: ignore[override]
            raise NotImplementedError

        async def build(self, request):  # type: ignore[override]
            raise NotImplementedError

        async def verify(self, request):  # type: ignore[override]
            raise NotImplementedError

    inst = _BareAdapter()
    for name in LIFECYCLE_METHODS:
        method = getattr(inst, name)
        with pytest.raises(NotImplementedError) as exc_info:
            asyncio.run(method(intent=None))
        msg = str(exc_info.value)
        assert "bare_test_adapter" in msg, (
            f"NotImplementedError for {name} must include adapter id; got: {msg!r}"
        )
        assert name in msg, (
            f"NotImplementedError for {name} must include method name; got: {msg!r}"
        )


def test_subclass_override_is_invoked() -> None:
    """When a subclass overrides a lifecycle method, the override (not the default) runs."""
    sentinel = [{"step": "withdraw_step"}]

    class _OverrideAdapter(YieldAdapter):  # type: ignore[misc]
        adapter_id = "override_test_adapter"
        chains: set[str] = set()
        protocols: set[str] = set()
        actions: set[str] = set()

        def supports(self, *, chain, protocol, action):  # type: ignore[override]
            raise NotImplementedError

        async def quote(self, request):  # type: ignore[override]
            raise NotImplementedError

        async def build(self, request):  # type: ignore[override]
            raise NotImplementedError

        async def verify(self, request):  # type: ignore[override]
            raise NotImplementedError

        async def build_withdraw(self, intent):  # type: ignore[override]
            return sentinel

    inst = _OverrideAdapter()
    result = asyncio.run(inst.build_withdraw(intent={"foo": "bar"}))
    assert result is sentinel, "Subclass override must take precedence over default"

    # Sanity: an un-overridden lifecycle method still raises with this adapter's id.
    with pytest.raises(NotImplementedError) as exc_info:
        asyncio.run(inst.build_claim(intent=None))
    assert "override_test_adapter" in str(exc_info.value)
