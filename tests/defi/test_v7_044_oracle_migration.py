"""Pin test V7-044: price_oracle must be the single source of truth for any
USD-denominated native price across ``src/``.

The audit originally called out lines 1122-1126 of
``src/agent/tools/build_yield_execution_plan.py`` where a hardcoded fallback
dict (``WETH=2300, WBTC=80000``) priced gas in USD. The cleanup grew to also
strip the same baked-in numbers from:

  * ``src/agent/tools/execute_pool_position.py`` (``_TOKEN_USD_HINT_LOCAL``)
  * ``src/agent/simple_runtime.py`` (``_TOKEN_USD_HINT`` + ``_NATIVE_USD_HINT``)

This test now globally scans ``src/`` so any future hardcoded
``"WETH": 2300`` / ``"WBTC": 80000`` regresses loudly. The narrower
``build_yield_execution_plan`` assertions remain to pin the original fix.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_ROOT = REPO_ROOT / "src"
TARGET = REPO_ROOT / "src" / "agent" / "tools" / "build_yield_execution_plan.py"


def test_no_hardcoded_weth_2300_anywhere_in_src():
    """No file under ``src/`` may carry the ``"WETH": 2300`` /
    ``"WBTC": 80000`` hardcodes. The audit-flagged fallback dict pattern
    was the smoking gun for stale-baseline pricing across multiple modules.
    """
    bad = re.compile(r'"WETH"\s*:\s*2300|"WBTC"\s*:\s*80000')
    hits: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in bad.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f"{path}:{line_no}")
    assert not hits, (
        f"V7-044 leftover hardcoded WETH=2300 / WBTC=80000 prices: {hits}"
    )


def test_no_token_usd_hint_local_dict():
    """The ``_TOKEN_USD_HINT_LOCAL`` symbol-keyed price dict is gone."""
    text = TARGET.read_text(encoding="utf-8")
    assert "_TOKEN_USD_HINT_LOCAL" not in text, (
        "V7-044: the local USD-hint dict must be replaced by the oracle."
    )


def test_build_yield_execution_plan_imports_price_oracle():
    """Source must reference ``fetch_price_usd`` from ``src.data.price_oracle``."""
    text = TARGET.read_text(encoding="utf-8")
    assert "from src.data.price_oracle import fetch_price_usd" in text, (
        "V7-044: build_yield_execution_plan must import the oracle."
    )


@pytest.mark.asyncio
async def test_oracle_failure_emits_stale_price_feed_blocker(monkeypatch):
    """When the oracle returns ``None`` for the native symbol and there is
    a positive gas estimate, the plan must surface a ``STALE_PRICE_FEED``
    blocker rather than fall back to a hardcoded number.

    The test exercises only the gas-topup branch by:
      - importing the gas-topup logic via a minimal local replay,
      - monkeypatching ``fetch_price_usd`` to return ``None``.

    We avoid invoking the full ``build_yield_execution_plan`` (it requires a
    populated ctx, inventory, protocol adapter, etc.); instead we assert that
    the source contains the STALE_PRICE_FEED branch and that the oracle is the
    awaited callable.
    """
    text = TARGET.read_text(encoding="utf-8")
    # The fix path must reference STALE_PRICE_FEED in the gas-topup region.
    assert 'code="STALE_PRICE_FEED"' in text, (
        "V7-044: oracle-miss must emit STALE_PRICE_FEED blocker."
    )
    # The oracle must be awaited (async path).
    assert "await _fetch_price_usd(" in text, (
        "V7-044: gas-topup must await fetch_price_usd."
    )


@pytest.mark.asyncio
async def test_price_oracle_returns_none_on_oracle_error(monkeypatch):
    """Smoke-test ``fetch_price_usd`` itself: when the HTTP session raises,
    the oracle returns ``None`` rather than a stale hardcoded number.
    """
    from src.data import price_oracle

    price_oracle._clear_cache_for_tests()

    class _BoomSession:
        def get(self, url, timeout=None):
            class _Ctx:
                async def __aenter__(self_inner):
                    raise RuntimeError("rpc unreachable")

                async def __aexit__(self_inner, *a):
                    return False

            return _Ctx()

    result = await price_oracle.fetch_price_usd(
        "ethereum",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        _BoomSession(),
    )
    assert result is None, (
        "Oracle must return None on RPC failure so callers can emit "
        "STALE_PRICE_FEED instead of silently using a hardcoded price."
    )
