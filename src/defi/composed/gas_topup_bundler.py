"""V7-040 gas-topup bundler with real bridge-quote selection.

Picks the best route across {deBridge DLN, LI.FI, Socket} by scoring each
quote on (cost_usd + (est_time_s / 60) * 0.10). Returns a GasTopupBundle
with the winning route's quote_id/via + dropped-quote costs for
observability. If all 3 clients raise / time out, emits a
GAS_TOPUP_REQUIRED blocker dict (no silent fabrication).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional


logger = logging.getLogger(__name__)


# Chain-name -> EVM chain id (subset; covers all chains in _native_for_chain).
_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "optimism": 10,
    "bsc": 56,
    "gnosis": 100,
    "polygon": 137,
    "sonic": 146,
    "mantle": 5000,
    "base": 8453,
    "celo": 42220,
    "avalanche": 43114,
    "arbitrum": 42161,
    "berachain": 80094,
}

# USDC contract addresses per chain (native USDC, not bridged variants where
# possible). Bridge aggregators accept these as `token_in` / `token_out`.
_USDC_ADDRS: dict[str, str] = {
    "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "optimism": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
    "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "polygon": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "bsc": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    "avalanche": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
    "gnosis": "0xDDAfbb505ad214D7b80b1f830fcCc89B60fb7A83",
    "celo": "0xcebA9300f2b948710d2653dD7B07f33A8B32118C",
    "mantle": "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9",
    "sonic": "0x29219dd400f2Bf60E5a23d13Be72B486D4038894",
    "berachain": "0x549943e04f40284185054145c6E4e9568C1D3241",
}


@dataclass
class GasTopupBundle:
    source_chain: str
    source_token: str
    source_amount_usd: float
    dest_chain: str
    dest_native_token: str
    bridge_route: str  # "debridge" / "lifi" / "socket"
    bundle_steps: list = field(default_factory=list)
    # Observability: cost score + dropped-quote costs.
    selected_cost_usd: Optional[float] = None
    selected_est_time_s: Optional[int] = None
    selected_quote_id: Optional[str] = None
    dropped_quotes: list = field(default_factory=list)


def _native_for_chain(chain: str) -> str:
    return {"ethereum": "ETH", "arbitrum": "ETH", "base": "ETH", "optimism": "ETH",
            "polygon": "MATIC", "bsc": "BNB", "avalanche": "AVAX",
            "sonic": "S", "berachain": "BERA", "celo": "CELO",
            "mantle": "MNT", "gnosis": "XDAI"}.get(chain.lower(), "ETH")


def _pick_source_chain(insufficient_chain: str, wallet_inventory: dict, needed_usd: float) -> Optional[str]:
    """Return the first chain (other than insufficient_chain) with >= needed_usd USDC."""
    for chain, balances in wallet_inventory.items():
        if chain == insufficient_chain:
            continue
        if balances.get("USDC", 0) >= needed_usd:
            return chain
    return None


def build_gas_topup_bundle(
    insufficient_chain: str,
    needed_usd: float,
    wallet_inventory: dict,
    source_preference: str = "ethereum",
) -> Optional[GasTopupBundle]:
    """Synchronous shape preserved for backward compatibility.

    Picks the first viable cross-chain USDC source and returns a 2-step
    bridge+swap bundle. Bridge-route field defaults to "debridge" — for
    real quote-based selection across {deBridge, LI.FI, Socket} use
    `build_gas_topup_bundle_async`.
    """
    source_chain = _pick_source_chain(insufficient_chain, wallet_inventory, needed_usd)
    if source_chain is None:
        return None
    return GasTopupBundle(
        source_chain=source_chain,
        source_token="USDC",
        source_amount_usd=needed_usd,
        dest_chain=insufficient_chain,
        dest_native_token=_native_for_chain(insufficient_chain),
        bridge_route="debridge",
        bundle_steps=[
            {"action": "bridge", "from": source_chain, "to": insufficient_chain, "asset": "USDC", "amount_usd": needed_usd},
            {"action": "swap", "chain": insufficient_chain, "from": "USDC", "to": _native_for_chain(insufficient_chain), "amount_usd": needed_usd},
        ],
    )


def _score_quote(cost_usd: float, est_time_s: float) -> float:
    """Lightly penalize slow routes: score = cost_usd + (minutes * 0.10)."""
    return cost_usd + (est_time_s / 60.0) * 0.10


def _derive_cost_usd(needed_usd: float, quote: dict[str, Any]) -> float:
    """USDC has 6 decimals on every supported chain. expected_dst_amount is
    in token units; cost = source_usd - (expected_dst_amount / 1e6).
    Floor at 0 — some quotes overshoot due to incentives.
    """
    expected = quote.get("expected_dst_amount") or 0
    dst_usd = float(expected) / 1_000_000.0
    return max(0.0, float(needed_usd) - dst_usd)


async def _safe_quote(client_name: str, coro) -> tuple[str, Optional[dict[str, Any]], Optional[str]]:
    """Wrap an awaitable to swallow exceptions and tag with client_name."""
    try:
        result = await coro
        return client_name, result, None
    except Exception as exc:  # noqa: BLE001 — fallback path needs broad catch
        logger.info("gas_topup bridge %s quote failed: %s", client_name, exc)
        return client_name, None, str(exc)


async def _select_bridge_quote(
    *,
    source_chain: str,
    dest_chain: str,
    needed_usd: float,
    recipient: str,
    debridge_client: Any,
    lifi_client: Any,
    socket_client: Any,
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    """Async parallel fan-out to {deBridge, LI.FI, Socket}. Returns a dict:

      {"winner": {...}, "dropped": [...], "all_failed": bool, "errors": [...]}
    """
    src_id = _CHAIN_IDS.get(source_chain.lower())
    dst_id = _CHAIN_IDS.get(dest_chain.lower())
    token_in = _USDC_ADDRS.get(source_chain.lower())
    token_out = _USDC_ADDRS.get(dest_chain.lower())

    # If we can't form a quote (unknown chain), surface as all-failed so the
    # caller emits GAS_TOPUP_REQUIRED rather than fabricating a route.
    if not (src_id and dst_id and token_in and token_out):
        return {
            "winner": None,
            "dropped": [],
            "all_failed": True,
            "errors": [f"unsupported chain pair {source_chain}->{dest_chain}"],
        }

    amount = int(needed_usd * 1_000_000)  # USDC 6 decimals
    kwargs = dict(
        src_chain_id=src_id,
        dst_chain_id=dst_id,
        token_in=token_in,
        token_out=token_out,
        amount=amount,
        recipient=recipient,
    )

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                _safe_quote("debridge", debridge_client.quote(**kwargs)),
                _safe_quote("lifi", lifi_client.quote(**kwargs)),
                _safe_quote("socket", socket_client.quote(**kwargs)),
                return_exceptions=False,
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        return {
            "winner": None,
            "dropped": [],
            "all_failed": True,
            "errors": ["timeout waiting for bridge quotes"],
        }

    scored: list[dict[str, Any]] = []
    errors: list[str] = []
    for name, quote, err in results:
        if quote is None:
            errors.append(f"{name}: {err}")
            continue
        cost = _derive_cost_usd(needed_usd, quote)
        ttl = int(quote.get("ttl_s") or 600)
        scored.append(
            {
                "route": name,
                "cost_usd": cost,
                "est_time_s": ttl,
                "score": _score_quote(cost, ttl),
                "quote_id": quote.get("quote_id"),
                "via": quote.get("via") or name,
            }
        )

    if not scored:
        return {"winner": None, "dropped": [], "all_failed": True, "errors": errors}

    scored.sort(key=lambda q: q["score"])
    winner = scored[0]
    dropped = scored[1:]
    return {"winner": winner, "dropped": dropped, "all_failed": False, "errors": errors}


async def build_gas_topup_bundle_async(
    insufficient_chain: str,
    needed_usd: float,
    wallet_inventory: dict,
    *,
    recipient: str = "0x0000000000000000000000000000000000000000",
    debridge_client: Any = None,
    lifi_client: Any = None,
    socket_client: Any = None,
    source_preference: str = "ethereum",
) -> dict[str, Any]:
    """Real bridge-quote-selection variant of build_gas_topup_bundle.

    Returns either:
      {"bundle": GasTopupBundle}  — on success
      {"blocker": {"code": "GAS_TOPUP_REQUIRED", "reason": "..."}}  — on
        no viable source OR all-bridge-quote-failure (no silent fabrication)
    """
    source_chain = _pick_source_chain(insufficient_chain, wallet_inventory, needed_usd)
    if source_chain is None:
        return {
            "blocker": {
                "code": "GAS_TOPUP_REQUIRED",
                "reason": f"no cross-chain USDC source covers ${needed_usd:.2f} for {insufficient_chain}",
            }
        }

    # Lazy-import client factories so test injection stays simple.
    if debridge_client is None:
        from src.routing.debridge_client import DeBridgeBridge

        debridge_client = DeBridgeBridge()
    if lifi_client is None:
        from src.routing.lifi_client import LifiBridge

        lifi_client = LifiBridge()
    if socket_client is None:
        from src.routing.socket_client import SocketBridge

        socket_client = SocketBridge()

    selection = await _select_bridge_quote(
        source_chain=source_chain,
        dest_chain=insufficient_chain,
        needed_usd=needed_usd,
        recipient=recipient,
        debridge_client=debridge_client,
        lifi_client=lifi_client,
        socket_client=socket_client,
    )

    if selection["all_failed"]:
        return {
            "blocker": {
                "code": "GAS_TOPUP_REQUIRED",
                "reason": (
                    f"all 3 bridge quotes failed for {source_chain}->{insufficient_chain}: "
                    + "; ".join(selection["errors"])
                ),
            }
        }

    winner = selection["winner"]
    native = _native_for_chain(insufficient_chain)
    bundle = GasTopupBundle(
        source_chain=source_chain,
        source_token="USDC",
        source_amount_usd=needed_usd,
        dest_chain=insufficient_chain,
        dest_native_token=native,
        bridge_route=winner["route"],
        bundle_steps=[
            {
                "action": "bridge",
                "from": source_chain,
                "to": insufficient_chain,
                "asset": "USDC",
                "amount_usd": needed_usd,
                "via": winner["via"],
                "quote_id": winner["quote_id"],
            },
            {
                "action": "swap",
                "chain": insufficient_chain,
                "from": "USDC",
                "to": native,
                "amount_usd": needed_usd,
            },
        ],
        selected_cost_usd=winner["cost_usd"],
        selected_est_time_s=winner["est_time_s"],
        selected_quote_id=winner["quote_id"],
        dropped_quotes=selection["dropped"],
    )
    return {"bundle": bundle}
