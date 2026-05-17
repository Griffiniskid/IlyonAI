"""Solana simulator — V7-010.

Calls the Solana RPC `simulateTransaction` method with
`replaceRecentBlockhash: True, sigVerify: False` so a freshly-built (but
not-yet-signed) serialized transaction can be evaluated against current
state without needing a real signature or a fresh blockhash from the
client. Compute-unit usage + the first program error are surfaced via
`SimulationResult` so the broadcast path can refuse before signing.

Spec ref:
  §4 simulator — "Solana side uses RPC simulateTransaction with
  replaceRecentBlockhash so we can sim the next bundle right up to
  the user's wallet popup."

Notes on RPC shape:
  https://docs.solana.com/api/http#simulatetransaction
  Request:
    {
      "jsonrpc": "2.0", "id": 1, "method": "simulateTransaction",
      "params": [<base64 wire tx>, {
        "encoding": "base64",
        "sigVerify": false,
        "replaceRecentBlockhash": true,
        "commitment": "processed"
      }]
    }
  Response (success):
    {"jsonrpc":"2.0","result":{"value":{"err":null,"logs":[...],"unitsConsumed":N}},...}
  Response (program error):
    {"jsonrpc":"2.0","result":{"value":{"err":{"InstructionError":[0,{"Custom":6000}]},...}}}
  Response (rpc-level error):
    {"jsonrpc":"2.0","error":{"code":-32602,"message":"invalid base64"}}
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from src.defi.execution.state_machine import compute_calldata_hash
from src.defi.simulator.tenderly_client import SimulationResult

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10.0)


async def simulate_transaction(
    rpc_url: str,
    serialized_tx_b64: str,
    *,
    commitment: str = "processed",
    session: aiohttp.ClientSession | None = None,
) -> SimulationResult:
    """Call Solana RPC `simulateTransaction` and unpack the result.

    The `calldata_hash` is computed over the serialized base64 tx itself
    — that's the exact byte sequence the wallet will sign, so V7-001's
    bind invariant compares apples to apples at submit-time.

    Network/RPC errors yield a failed `SimulationResult` rather than
    raising, so the broadcast guard stays total (callers gate on
    `result.success` and refuse the submit when False).
    """
    calldata_hash = compute_calldata_hash(serialized_tx_b64)

    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "simulateTransaction",
        "params": [
            serialized_tx_b64,
            {
                "encoding": "base64",
                "sigVerify": False,
                "replaceRecentBlockhash": True,
                "commitment": commitment,
            },
        ],
    }

    async def _do_post(s: aiohttp.ClientSession) -> SimulationResult:
        try:
            async with s.post(rpc_url, json=body, timeout=_HTTP_TIMEOUT) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    return SimulationResult(
                        success=False,
                        calldata_hash=calldata_hash,
                        error_message=f"HTTP {resp.status}: {text[:400]}",
                    )
                try:
                    data = await resp.json(content_type=None)
                except Exception as exc:  # noqa: BLE001 — malformed body
                    return SimulationResult(
                        success=False,
                        calldata_hash=calldata_hash,
                        error_message=f"invalid JSON: {exc!s}",
                    )
                return _parse_solana_response(data, calldata_hash)
        except aiohttp.ClientError as exc:
            logger.warning("solana sim client error: %s", exc)
            return SimulationResult(
                success=False,
                calldata_hash=calldata_hash,
                error_message=f"network error: {exc!s}",
            )
        except TimeoutError as exc:
            return SimulationResult(
                success=False,
                calldata_hash=calldata_hash,
                error_message=f"timeout: {exc!s}",
            )

    if session is not None:
        return await _do_post(session)
    async with aiohttp.ClientSession() as new_session:
        return await _do_post(new_session)


def _parse_solana_response(
    data: dict[str, Any],
    calldata_hash: str,
) -> SimulationResult:
    """Map a Solana RPC response into the unified `SimulationResult`.

    - RPC-level error (`"error"` key present) → success=False, msg.
    - `result.value.err is None` → success=True with unitsConsumed.
    - `result.value.err is not None` → success=False with the error
      stringified (Solana errors are tagged JSON like
      `{"InstructionError":[0,{"Custom":6000}]}` so we stringify for UI).
    """
    rpc_err = data.get("error")
    if rpc_err is not None:
        msg = (
            f"rpc error {rpc_err.get('code')}: {rpc_err.get('message', 'unknown')}"
            if isinstance(rpc_err, dict)
            else f"rpc error: {rpc_err!s}"
        )
        return SimulationResult(
            success=False,
            calldata_hash=calldata_hash,
            error_message=msg,
            raw_response=data,
        )

    result = data.get("result") or {}
    value = result.get("value") or {}
    err = value.get("err")
    units = int(value.get("unitsConsumed") or 0)

    if err is None:
        return SimulationResult(
            success=True,
            calldata_hash=calldata_hash,
            compute_units=units,
            raw_response=data,
        )

    # Program-level error — stringify the tagged JSON for UI display.
    return SimulationResult(
        success=False,
        calldata_hash=calldata_hash,
        compute_units=units,
        error_message=f"program error: {err!r}",
        raw_response=data,
    )


__all__ = ["simulate_transaction"]
