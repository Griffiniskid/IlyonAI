"""Spec §13 Row 1 pin tests — Pyth/Chainlink 60s feed-age preflight.

These tests are HTTP/RPC-free: every external call is mocked behind
duck-typed async stubs so the suite stays fast and deterministic. The
goal is to lock the staleness-threshold contract so downstream callers
(preflight, sidecar, UI) can rely on the ``STALE_PRICE_FEED`` blocker
code without reading the internals.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest

from src.shield.feed_age import (
    STALE_PRICE_FEED_BLOCKER_CODE,
    STALE_PRICE_FEED_THRESHOLD_SEC,
    check_chainlink_age,
    check_feed_age,
    check_pyth_age,
    evaluate_feed_age_preflight,
)


# ----- Stubs -----------------------------------------------------------------


class _FakeResp:
    def __init__(self, payload: Any, status: int = 200):
        self._payload = payload
        self.status = status

    async def json(self) -> Any:
        return self._payload


class _FakeHttpSession:
    """Minimal aiohttp.ClientSession lookalike — only needs .get() to
    return an async context manager wrapping a JSON-returning response.
    Captures the last URL/params pair so tests can assert call shape."""

    def __init__(self, payload: Any, status: int = 200):
        self._payload = payload
        self._status = status
        self.last_url: str | None = None
        self.last_params: dict[str, Any] | None = None

    def get(self, url: str, params: dict[str, Any] | None = None):
        self.last_url = url
        self.last_params = params

        @asynccontextmanager
        async def _cm():
            yield _FakeResp(self._payload, self._status)

        return _cm()


class _FailingHttpSession:
    def get(self, url: str, params: dict[str, Any] | None = None):
        @asynccontextmanager
        async def _cm():
            raise RuntimeError("network down")
            yield  # pragma: no cover — make this a generator
        return _cm()


class _FakeRpc:
    """call_function(address, chain_id, abi, fn_name) → 5-tuple."""

    def __init__(self, tuple_result: tuple | dict | None, raise_exc: Exception | None = None):
        self._result = tuple_result
        self._raise = raise_exc

    async def call_function(self, *, address: str, chain_id: int, abi: Any, fn_name: str) -> Any:
        if self._raise is not None:
            raise self._raise
        return self._result


# ----- check_feed_age (pure) -------------------------------------------------


def test_check_feed_age_fresh_returns_none():
    assert check_feed_age(30) is None


def test_check_feed_age_stale_returns_blocker_code():
    assert check_feed_age(70) == STALE_PRICE_FEED_BLOCKER_CODE
    assert check_feed_age(70) == "STALE_PRICE_FEED"


def test_check_feed_age_at_threshold_is_fresh():
    # Threshold is `>` not `>=` — exactly 60s old is still acceptable.
    assert check_feed_age(STALE_PRICE_FEED_THRESHOLD_SEC) is None
    assert check_feed_age(STALE_PRICE_FEED_THRESHOLD_SEC + 1) == STALE_PRICE_FEED_BLOCKER_CODE


def test_check_feed_age_handles_garbage_input():
    assert check_feed_age(None) is None  # type: ignore[arg-type]
    assert check_feed_age("not-a-number") is None  # type: ignore[arg-type]


def test_check_feed_age_custom_threshold():
    assert check_feed_age(45, threshold_sec=30) == STALE_PRICE_FEED_BLOCKER_CODE
    assert check_feed_age(45, threshold_sec=60) is None


# ----- check_pyth_age --------------------------------------------------------


def test_pyth_age_stale_returns_age_over_threshold():
    now_t = 2_000_000_000
    payload = [{"id": "abc", "price": {"publish_time": now_t - 80, "price": "1"}}]
    sess = _FakeHttpSession(payload)
    age = asyncio.run(check_pyth_age("abc", sess, now_fn=lambda: now_t))
    assert age == 80
    assert check_feed_age(age) == STALE_PRICE_FEED_BLOCKER_CODE
    assert sess.last_url.endswith("/api/latest_price_feeds")
    assert sess.last_params == {"ids[]": "abc"}


def test_pyth_age_fresh_no_blocker():
    now_t = 2_000_000_000
    payload = [{"id": "abc", "price": {"publish_time": now_t - 5}}]
    sess = _FakeHttpSession(payload)
    age = asyncio.run(check_pyth_age("abc", sess, now_fn=lambda: now_t))
    assert age == 5
    assert check_feed_age(age) is None


def test_pyth_age_v2_parsed_shape():
    now_t = 1_700_000_000
    payload = {"parsed": [{"price": {"publish_time": now_t - 70}}]}
    sess = _FakeHttpSession(payload)
    age = asyncio.run(check_pyth_age("xyz", sess, now_fn=lambda: now_t))
    assert age == 70
    assert check_feed_age(age) == "STALE_PRICE_FEED"


def test_pyth_age_network_failure_returns_none():
    age = asyncio.run(check_pyth_age("abc", _FailingHttpSession(), now_fn=lambda: 0))
    assert age is None


def test_pyth_age_empty_price_id_returns_none():
    sess = _FakeHttpSession([])
    age = asyncio.run(check_pyth_age("", sess))
    assert age is None


def test_pyth_age_clock_skew_clamped_to_zero():
    # Publish time slightly in the future (clock skew on the wire) — we
    # treat the feed as fresh rather than emitting a negative age.
    payload = [{"price": {"publish_time": 1000}}]
    sess = _FakeHttpSession(payload)
    age = asyncio.run(check_pyth_age("abc", sess, now_fn=lambda: 990))
    assert age == 0


# ----- check_chainlink_age ---------------------------------------------------


def test_chainlink_age_stale_tuple_response():
    now_t = 2_000_000_000
    updated_at = now_t - 90
    # latestRoundData returns (roundId, answer, startedAt, updatedAt, answeredInRound)
    rpc = _FakeRpc(tuple_result=(1, 100_000_000, updated_at - 1, updated_at, 1))
    age = asyncio.run(check_chainlink_age("0xfeed", 1, rpc, now_fn=lambda: now_t))
    assert age == 90
    assert check_feed_age(age) == STALE_PRICE_FEED_BLOCKER_CODE


def test_chainlink_age_fresh_dict_response():
    now_t = 2_000_000_000
    rpc = _FakeRpc(tuple_result={"updatedAt": now_t - 10})
    age = asyncio.run(check_chainlink_age("0xfeed", 1, rpc, now_fn=lambda: now_t))
    assert age == 10
    assert check_feed_age(age) is None


def test_chainlink_age_rpc_failure_returns_none():
    rpc = _FakeRpc(tuple_result=None, raise_exc=RuntimeError("rpc gone"))
    age = asyncio.run(check_chainlink_age("0xfeed", 1, rpc, now_fn=lambda: 0))
    assert age is None


def test_chainlink_age_empty_addr_returns_none():
    rpc = _FakeRpc(tuple_result=(0, 0, 0, 0, 0))
    age = asyncio.run(check_chainlink_age("", 1, rpc, now_fn=lambda: 0))
    assert age is None


# ----- evaluate_feed_age_preflight (fan-out) ---------------------------------


def test_evaluate_emits_pyth_blocker_only_when_stale():
    now_t = 2_000_000_000
    payload = [{"price": {"publish_time": now_t - 75}}]
    sess = _FakeHttpSession(payload)
    blockers = asyncio.run(evaluate_feed_age_preflight(
        ["pyth-id-1"], sess, now_fn=lambda: now_t,
    ))
    assert len(blockers) == 1
    assert blockers[0]["code"] == STALE_PRICE_FEED_BLOCKER_CODE
    assert blockers[0]["source"] == "pyth"
    assert blockers[0]["age_seconds"] == 75


def test_evaluate_fresh_pyth_emits_no_blocker():
    now_t = 2_000_000_000
    payload = [{"price": {"publish_time": now_t - 5}}]
    sess = _FakeHttpSession(payload)
    blockers = asyncio.run(evaluate_feed_age_preflight(
        ["pyth-id-1"], sess, now_fn=lambda: now_t,
    ))
    assert blockers == []


def test_evaluate_combines_pyth_and_chainlink():
    now_t = 2_000_000_000
    payload = [{"price": {"publish_time": now_t - 90}}]
    sess = _FakeHttpSession(payload)
    rpc = _FakeRpc(tuple_result=(1, 0, 0, now_t - 120, 1))
    blockers = asyncio.run(evaluate_feed_age_preflight(
        ["pyth-id-1"], sess,
        chainlink_feeds=[("0xfeed", 1)],
        rpc_client=rpc,
        now_fn=lambda: now_t,
    ))
    codes = {(b["source"], b["code"]) for b in blockers}
    assert ("pyth", STALE_PRICE_FEED_BLOCKER_CODE) in codes
    assert ("chainlink", STALE_PRICE_FEED_BLOCKER_CODE) in codes


def test_evaluate_skips_chainlink_when_no_rpc():
    now_t = 2_000_000_000
    payload = [{"price": {"publish_time": now_t - 5}}]
    sess = _FakeHttpSession(payload)
    blockers = asyncio.run(evaluate_feed_age_preflight(
        ["pyth-id-1"], sess,
        chainlink_feeds=[("0xfeed", 1)],
        rpc_client=None,
        now_fn=lambda: now_t,
    ))
    assert blockers == []
