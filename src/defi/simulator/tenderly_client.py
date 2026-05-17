"""Tenderly bundle simulator (EVM) — V7-010.

Posts the unsigned step calldata to Tenderly's
`/api/v1/account/{account}/project/{project}/simulate-bundle` endpoint
and returns a unified `SimulationResult`. The `calldata_hash` field is
computed via `src.defi.execution.state_machine.compute_calldata_hash` on
the canonicalized request body so it round-trips deterministically (same
input → same hash, independent of dict-key ordering).

Spec ref:
  §4 simulator — "Tenderly forks per chain; bundle simulator for
  multi-tx EVM plans; result includes gas, revert reason, calldata
  hash bound to the plan-step."

Notes on shape:
  - The Tenderly bundle endpoint accepts a list of `simulations` (each
    is a single tx dict). We accept callers' `transactions: List[dict]`
    format directly (`{to, data, value, from, gas?}`), wrap it as
    Tenderly expects, and POST with the project's API key.
  - On non-2xx responses we surface a `success=False` result with the
    HTTP status + body excerpt as `error_message` so the broadcast path
    can log + refuse rather than blow up.
  - Network errors (timeouts, connection refused) likewise return a
    failed `SimulationResult` — never raise out of `simulate_bundle`
    so the broadcast guard stays total.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from src.defi.execution.state_machine import compute_calldata_hash

logger = logging.getLogger(__name__)


_TENDERLY_BASE = "https://api.tenderly.co"
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15.0)


@dataclass
class SimulationResult:
    """Unified shape across EVM (Tenderly) and Solana (RPC) simulators.

    `calldata_hash` is the SHA-256 of the canonicalized request payload
    — same value the broadcast path will stamp on the step so V7-001's
    bind invariant can compare equality at submit-time.
    """

    success: bool
    calldata_hash: str
    gas_used: int = 0
    compute_units: int = 0
    error_message: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


class TenderlyClient:
    """Async client for Tenderly's bundle-simulate REST endpoint.

    Usage:
        client = TenderlyClient(
            api_key=os.environ["TENDERLY_API_KEY"],
            account_slug=os.environ["TENDERLY_ACCOUNT"],
            project_slug=os.environ["TENDERLY_PROJECT"],
        )
        result = await client.simulate_bundle(
            transactions=[{"to": "0x...", "data": "0x...", "value": "0"}],
            network_id=1,
        )
        if result.success:
            step.simulated_calldata_hash = result.calldata_hash
    """

    def __init__(
        self,
        api_key: str,
        account_slug: str,
        project_slug: str,
        *,
        base_url: str = _TENDERLY_BASE,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("TenderlyClient requires a non-empty api_key")
        if not account_slug or not project_slug:
            raise ValueError(
                "TenderlyClient requires non-empty account_slug + project_slug"
            )
        self._api_key = api_key
        self._account = account_slug
        self._project = project_slug
        self._base_url = base_url.rstrip("/")
        self._session = session

    @property
    def _endpoint(self) -> str:
        return (
            f"{self._base_url}/api/v1/account/{self._account}"
            f"/project/{self._project}/simulate-bundle"
        )

    def _build_payload(
        self,
        transactions: list[dict[str, Any]],
        network_id: int,
    ) -> dict[str, Any]:
        """Wrap caller-supplied unsigned txs as Tenderly's bundle shape.

        Tenderly expects each leg to carry `network_id`, `save: True` (so
        the run appears in the dashboard for postmortems), and a
        `simulation_type: "quick"` for fast pre-broadcast checks. We add
        sensible defaults but pass-through any caller-provided fields.
        """
        simulations: list[dict[str, Any]] = []
        for tx in transactions:
            leg = {
                "network_id": str(network_id),
                "save": True,
                "save_if_fails": True,
                "simulation_type": "quick",
                "from": tx.get("from") or tx.get("sender") or "",
                "to": tx.get("to", ""),
                "input": tx.get("data") or tx.get("input") or "0x",
                "value": str(tx.get("value", "0")),
            }
            if tx.get("gas") is not None:
                leg["gas"] = int(str(tx["gas"]), 0) if isinstance(tx["gas"], str) else int(tx["gas"])
            simulations.append(leg)
        return {"simulations": simulations}

    async def simulate_bundle(
        self,
        transactions: list[dict[str, Any]],
        network_id: int,
    ) -> SimulationResult:
        """POST the bundle to Tenderly and unpack the response.

        Returns a `SimulationResult` whose `calldata_hash` is computed
        BEFORE the HTTP call, so even on Tenderly outage the broadcast
        path has a hash to stamp (and the step gets refused at the bind
        check because `success=False` will block any submit-flip).
        """
        payload = self._build_payload(transactions, network_id)
        # Hash the canonicalized payload up-front: deterministic, sorted
        # JSON. Sharing `compute_calldata_hash` with state_machine.py is
        # intentional — same hash function on both sides of the bind.
        calldata_hash = compute_calldata_hash(payload)

        headers = {
            "X-Access-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async def _do_post(session: aiohttp.ClientSession) -> SimulationResult:
            try:
                async with session.post(
                    self._endpoint, json=payload, headers=headers, timeout=_HTTP_TIMEOUT,
                ) as resp:
                    body_text = await resp.text()
                    if resp.status >= 400:
                        excerpt = body_text[:400]
                        logger.warning(
                            "tenderly simulate-bundle %s for network=%s: %s",
                            resp.status, network_id, excerpt,
                        )
                        return SimulationResult(
                            success=False,
                            calldata_hash=calldata_hash,
                            error_message=f"HTTP {resp.status}: {excerpt}",
                        )
                    try:
                        data = await resp.json(content_type=None)
                    except Exception as exc:  # noqa: BLE001 — body may be malformed
                        return SimulationResult(
                            success=False,
                            calldata_hash=calldata_hash,
                            error_message=f"invalid JSON: {exc!s}",
                        )
                    return _parse_tenderly_response(data, calldata_hash)
            except aiohttp.ClientError as exc:
                logger.warning("tenderly client error: %s", exc)
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

        # Reuse caller-supplied session if any (lets tests inject mocks),
        # otherwise spin a one-shot session.
        if self._session is not None:
            return await _do_post(self._session)
        async with aiohttp.ClientSession() as session:
            return await _do_post(session)


def _parse_tenderly_response(
    data: dict[str, Any],
    calldata_hash: str,
) -> SimulationResult:
    """Extract success/gas/revert-reason from a Tenderly bundle response.

    The response shape (per Tenderly docs):
      {"simulation_results": [
          {"transaction": {"gas_used": int, "status": bool, "error_message": str|None},
           "simulation": {...}}, ...
      ]}

    A bundle is considered successful when EVERY leg reports status=True.
    Gas is the sum of all legs (matches what the wallet will price).
    The first failing leg's error message is surfaced for UI display.
    """
    legs = data.get("simulation_results") or []
    if not legs:
        # Tenderly sometimes returns single-leg results under
        # `transaction` directly; tolerate both shapes.
        tx = data.get("transaction")
        if tx:
            legs = [{"transaction": tx, "simulation": data.get("simulation", {})}]
    if not legs:
        return SimulationResult(
            success=False,
            calldata_hash=calldata_hash,
            error_message="empty simulation_results",
            raw_response=data,
        )

    total_gas = 0
    success = True
    error_message: str | None = None
    for leg in legs:
        tx = leg.get("transaction") or {}
        leg_status = tx.get("status", True)
        leg_gas = int(tx.get("gas_used") or 0)
        total_gas += leg_gas
        if not leg_status and error_message is None:
            error_message = (
                tx.get("error_message")
                or leg.get("simulation", {}).get("error_message")
                or "tenderly leg reverted"
            )
            success = False

    return SimulationResult(
        success=success,
        calldata_hash=calldata_hash,
        gas_used=total_gas,
        error_message=error_message,
        raw_response=data,
    )


__all__ = ["SimulationResult", "TenderlyClient"]
