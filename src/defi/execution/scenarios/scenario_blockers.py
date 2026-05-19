"""§13 spec-scenario blocker emitters (H07/H08/H09/H10/H11/H12/H14/H15 + E15).

Pass C 58517bf hand-read aggregate (file: passC_H_findings_58517bf.md) caught
nine §13 scenarios where the existing detector or inventory hint was present,
but the build path silently fell through to a signable plan / pool_link card
without emitting the structured blocker that the spec demands. Each function
here returns a list[ExecutionBlocker]; an empty list means "no blocker needed".

Wire site: src/agent/tools/build_yield_execution_plan.py — call
`scan_scenario_blockers(...)` once after `steps` are built but before
`assert_signable_composed_plan(plan)` runs.

Hard rule: every blocker code emitted here MUST already be registered in
`src/defi/execution/models.py::KNOWN_BLOCKER_CODES`. If you add a new code,
register it there first or the runtime drops the blocker silently.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from src.defi.execution.models import ExecutionBlocker, ExecutionStepV3

# E15 — Spec §13 row 15 price-impact gate threshold. Anything ≥500 bps is
# refused-to-sign per spec §13 "PRICE_IMPACT_TOO_HIGH". The detector reads
# step.snapshot["price_impact_bps"] OR step.snapshot["priceImpactBps"] OR
# step.transaction-side fields the adapters stash.
PRICE_IMPACT_REFUSE_BPS: int = 500


def _step_snapshot(step: Any) -> dict[str, Any]:
    snap = getattr(step, "snapshot", None) or {}
    if not isinstance(snap, dict):
        return {}
    return snap


def _step_price_impact_bps(step: Any) -> int | None:
    """Pull the price-impact field out of a step's snapshot / metadata.

    Adapters stamp the field under one of several keys depending on which
    quoter produced the route (Enso uses `price_impact_bps`, LI.FI uses
    `priceImpactBps`, internal V3 quoter uses `priceImpactPct` as a 0..1
    fraction). We accept whichever lands first.
    """
    snap = _step_snapshot(step)
    for key in ("price_impact_bps", "priceImpactBps", "price_impact"):
        v = snap.get(key)
        if v is None:
            continue
        try:
            return int(float(v))
        except (TypeError, ValueError):
            continue
    # Fractional fallback (Uniswap V3 quoter)
    for key in ("price_impact_pct", "priceImpactPct"):
        v = snap.get(key)
        if v is None:
            continue
        try:
            return int(round(float(v) * 10000))
        except (TypeError, ValueError):
            continue
    return None


# ──────────────────────────────────────────────────────────────────────────
# H07 — DUST_BELOW_THRESHOLD
# ──────────────────────────────────────────────────────────────────────────
def detect_dust_below_threshold_blocker(
    *,
    steps: Iterable[Any],
    amount_in_usd_resolver: Any = None,
    threshold_usd: float = 1.0,
) -> list[ExecutionBlocker]:
    """Emit DUST_BELOW_THRESHOLD when any leg's USD value < $1.00.

    `amount_in_usd_resolver`: optional callable `(symbol, amount, chain) -> usd`.
    When None we fall back to a heuristic: stablecoins ≈ 1 USD, others fall
    back to step.snapshot.amount_usd if present. Sub-USD legs always emit
    the blocker — the runtime can let the user choose SWEEP / LEAVE /
    INCREASE_TO_THRESHOLD via the dust_accumulator hooks.
    """
    from src.defi.recovery.dust_accumulator import (
        DustPosition,
        build_dust_blocker,
    )

    _STABLES = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "USDS", "BUSD",
                "TUSD", "FDUSD", "USDBC", "USDE", "SDAI", "SUSDE"}
    positions: list[DustPosition] = []
    for step in steps or []:
        token = (getattr(step, "asset_in", None) or "").upper()
        if not token:
            continue
        amt_raw = getattr(step, "amount_in", None)
        try:
            amt = float(amt_raw) if amt_raw is not None else 0.0
        except (TypeError, ValueError):
            continue
        if amt <= 0:
            continue
        chain = (getattr(step, "chain", "") or "ethereum").lower()
        usd: float | None = None
        snap = _step_snapshot(step)
        if "amount_usd" in snap:
            try:
                usd = float(snap["amount_usd"])
            except (TypeError, ValueError):
                usd = None
        if usd is None and callable(amount_in_usd_resolver):
            try:
                usd = amount_in_usd_resolver(token, amt, chain)
            except Exception:  # noqa: BLE001
                usd = None
        if usd is None:
            if token in _STABLES:
                usd = amt
            else:
                continue
        if usd < float(threshold_usd):
            positions.append(DustPosition(
                token=token,
                amount_token=amt,
                amount_usd=usd,
                chain=chain,
                step_id=getattr(step, "step_id", None),
            ))
    if not positions:
        return []
    return [build_dust_blocker(positions, threshold_usd=threshold_usd)]


# ──────────────────────────────────────────────────────────────────────────
# H08 — PARTIAL_ALLOWANCE_REMAINING
# ──────────────────────────────────────────────────────────────────────────
def detect_partial_allowance_blocker(
    *,
    steps: Iterable[Any],
    inventory: Any | None,
) -> list[ExecutionBlocker]:
    """Emit PARTIAL_ALLOWANCE_REMAINING when allowance > 0 but < amount.

    `evaluate_preflight` already emits a `missing_allowance` blocker for
    allowance == 0. This detector covers the strictly-positive partial
    case (user previously approved 25 USDC, now wants to supply 50): the
    plan still needs an approve step but the message must call out the
    residual amount so the user understands why a fresh approval is
    required (some ERC20s, notably USDT, refuse non-zero→non-zero
    allowance updates and need a 0-reset hop first).
    """
    if inventory is None:
        return []
    out: list[ExecutionBlocker] = []
    seen: set[tuple[str, str, str]] = set()
    for step in steps or []:
        action = getattr(step, "action", None)
        if action not in {"swap", "supply", "stake", "deposit_lp", "bridge"}:
            continue
        asset_in = getattr(step, "asset_in", None)
        amount_in_raw = getattr(step, "amount_in", None)
        if not asset_in or amount_in_raw is None:
            continue
        tx = getattr(step, "transaction", None)
        spender = getattr(tx, "spender", None) if tx is not None else None
        if not spender:
            continue
        chain = (getattr(step, "chain", "") or "").lower()
        key = (chain, asset_in.upper(), spender.lower())
        if key in seen:
            continue
        try:
            amount = Decimal(str(amount_in_raw))
        except Exception:  # noqa: BLE001
            continue
        try:
            current = inventory.allowance_for(chain, asset_in, spender)
        except Exception:  # noqa: BLE001
            continue
        if current is None:
            continue
        try:
            current_dec = Decimal(str(current))
        except Exception:  # noqa: BLE001
            continue
        if current_dec <= 0 or current_dec >= amount:
            continue
        # Partial allowance — emit blocker.
        seen.add(key)
        usdt_quirk = asset_in.upper() == "USDT"
        cta = (
            f"Reset allowance to 0 first (USDT non-zero update quirk), then "
            f"approve {amount} {asset_in}."
            if usdt_quirk else
            f"Re-approve spender {spender[:10]}... for {amount} {asset_in} "
            f"(current allowance: {current_dec})."
        )
        out.append(ExecutionBlocker(
            code="PARTIAL_ALLOWANCE_REMAINING",
            severity="blocker",
            title=f"Partial {asset_in} allowance — top-up required",
            detail=(
                f"Step {getattr(step, 'index', '?')} needs allowance "
                f">= {amount} {asset_in} for spender {spender}; current "
                f"allowance is {current_dec} (>0 but insufficient). "
                f"USDT (and a few other ERC20s) require a 0-reset before "
                f"raising allowance; failing to reset reverts the new "
                f"approve tx silently."
            ),
            affected_step_ids=[getattr(step, "step_id", "")],
            cta=cta,
        ))
    return out


# ──────────────────────────────────────────────────────────────────────────
# H09 — GAS_MISSING_DST (GAS_TOPUP_REQUIRED)
# ──────────────────────────────────────────────────────────────────────────
def detect_gas_missing_dst_blocker(
    *,
    steps: Iterable[Any],
    inventory: Any | None,
    dst_chain: str | None = None,
    min_native_gas: dict[str, float] | None = None,
) -> list[ExecutionBlocker]:
    """Emit GAS_TOPUP_REQUIRED for cross-chain plans where the destination
    chain wallet has < min_required native gas.

    Distinct from preflight's generic `insufficient_gas`: that fires per-step
    on the step's chain. This one fires once per plan against the EXPLICIT
    destination chain (the post-bridge leg) so the message tells the user
    which chain to top up. The runtime can also pass `min_native_gas`
    overrides for non-default per-chain floors.
    """
    if inventory is None or not dst_chain:
        return []
    min_native_gas = min_native_gas or {
        "ethereum": 0.005, "base": 0.001, "arbitrum": 0.001,
        "optimism": 0.001, "polygon": 1.0, "bsc": 0.005,
        "avalanche": 0.01, "solana": 0.01,
    }
    dst_l = dst_chain.lower()
    need = Decimal(str(min_native_gas.get(dst_l, 0.001)))
    try:
        have = inventory.gas_balance(dst_l)
    except Exception:  # noqa: BLE001
        return []
    if have is None:
        return []
    try:
        have_dec = Decimal(str(have))
    except Exception:  # noqa: BLE001
        return []
    if have_dec >= need:
        return []
    # Identify affected steps: post-bridge legs on the dst_chain.
    affected: list[str] = []
    for step in steps or []:
        if (getattr(step, "chain", "") or "").lower() == dst_l:
            sid = getattr(step, "step_id", None)
            if sid:
                affected.append(sid)
    native_sym = {
        "ethereum": "ETH", "arbitrum": "ETH", "optimism": "ETH",
        "base": "ETH", "polygon": "MATIC", "bsc": "BNB",
        "avalanche": "AVAX", "solana": "SOL", "linea": "ETH",
        "scroll": "ETH", "zksync": "ETH",
    }.get(dst_l, "native")
    return [ExecutionBlocker(
        code="GAS_TOPUP_REQUIRED",
        severity="blocker",
        title=f"Top up {native_sym} on {dst_chain}",
        detail=(
            f"Cross-chain plan settles on {dst_chain}. Destination wallet "
            f"holds {have_dec} {native_sym}, plan needs ≥{need} {native_sym} "
            f"to broadcast the post-bridge leg. Bridge a small amount of "
            f"native gas to {dst_chain} before retrying — without it the "
            f"post-bridge supply/stake step will sit blocked indefinitely."
        ),
        affected_step_ids=affected,
        cta=(
            f"Send ≥{need} {native_sym} to your wallet on {dst_chain} "
            f"(any small bridge or CEX withdrawal works)."
        ),
    )]


# ──────────────────────────────────────────────────────────────────────────
# H10 — LST_ALREADY_DEPOSITED
# ──────────────────────────────────────────────────────────────────────────
# Map of LST staking protocols → wrapped-LST symbol whose presence in the
# wallet means the wrap+swap legs can be skipped (route direct supply).
_LST_SYMBOL_BY_PROTOCOL: dict[str, str] = {
    "lido":                  "STETH",
    "rocket-pool":           "RETH",
    "ether.fi":              "EETH",
    "etherfi":               "EETH",
    "renzo":                 "EZETH",
    "swell":                 "SWETH",
    "frax-ether":            "SFRXETH",
    "frax":                  "SFRXETH",
    "kelp":                  "RSETH",
    "mantle-staked-ether":   "METH",
    "marinade":              "MSOL",
    "marinade-liquid-staking": "MSOL",
    "marinade-native":       "MSOL",
    "jito":                  "JITOSOL",
    "jito-liquid-staking":   "JITOSOL",
}


def detect_lst_already_deposited_blocker(
    *,
    protocol: str,
    action: str,
    asset_in: str,
    inventory: Any | None,
    chain: str | None = None,
) -> list[ExecutionBlocker]:
    """Emit LST_ALREADY_DEPOSITED when wallet already holds the wrapped LST.

    Spec §13: a "stake X ETH on Lido" intent with stETH already in wallet
    should NOT re-wrap. The runtime should either supply the existing
    stETH directly (saving the wrap leg's gas + slippage) OR confirm with
    the user that they really want to stake fresh ETH on top.

    Severity = warning so the user can override; the blocker carries the
    LST balance + symbol so the runtime can construct a SKIP_WRAP +
    DIRECT_SUPPLY recovery path.
    """
    if inventory is None:
        return []
    act = (action or "").lower()
    if act not in {"stake", "supply", "deposit"}:
        return []
    proto_l = (protocol or "").lower()
    lst_sym = _LST_SYMBOL_BY_PROTOCOL.get(proto_l)
    if not lst_sym:
        return []
    # Wallet already holds the wrapped form?
    chain_l = (chain or "").lower() or (
        "solana" if lst_sym in {"MSOL", "JITOSOL"} else "ethereum"
    )
    try:
        bal = inventory.balance_of(chain_l, lst_sym)
    except Exception:  # noqa: BLE001
        return []
    if bal is None:
        return []
    try:
        bal_dec = Decimal(str(bal))
    except Exception:  # noqa: BLE001
        return []
    if bal_dec <= 0:
        return []
    return [ExecutionBlocker(
        code="LST_ALREADY_DEPOSITED",
        severity="warning",
        title=f"{lst_sym} already in wallet — skip the wrap?",
        detail=(
            f"Wallet holds {bal_dec} {lst_sym} on {chain_l}. The requested "
            f"`{action}` on {protocol} would mint MORE {lst_sym} from "
            f"{asset_in} (paying wrap fees + slippage). If you intended "
            f"to deploy your EXISTING {lst_sym}, switch to a direct "
            f"supply route instead of a wrap-then-deposit composed plan."
        ),
        affected_step_ids=[],
        cta=(
            f"SKIP_WRAP | DIRECT_SUPPLY ({bal_dec} {lst_sym}) | "
            f"WRAP_FRESH ({asset_in})"
        ),
        recoverable=True,
    )]


# ──────────────────────────────────────────────────────────────────────────
# H11 — NFT_LP_REFINANCE
# ──────────────────────────────────────────────────────────────────────────
def detect_nft_lp_refinance_blocker(
    *,
    extra: dict[str, Any] | None,
    steps: Iterable[Any] | None,
) -> list[ExecutionBlocker]:
    """Refinance intent (`_detect_v3_nft_refinance`) sets extra.refinance=True.

    The expected emission is a multi-step composed plan:
       1. collect_fees (collect)
       2. close_position (decrease_liquidity + collect remainder)
       3. open_new_position (mint with new range)

    If the build path only emits a single supply step (legacy adapter
    fallthrough), surface NFT_LP_REFINANCE_INCOMPLETE so the runtime
    blocks the sign rather than silently degrading "refinance" to
    "supply".
    """
    if not extra or not extra.get("refinance"):
        return []
    step_list = list(steps or [])
    actions = [(getattr(s, "action", None) or "") for s in step_list]
    has_collect = any(a in {"collect_fees", "collect", "claim"} for a in actions)
    has_close = any(a in {"close_position", "decrease_liquidity", "withdraw"} for a in actions)
    has_open = any(a in {"open_position", "deposit_lp", "add_liquidity",
                          "mint", "lp_mint", "provide_liquidity"} for a in actions)
    if has_collect and has_close and has_open:
        return []
    token_id = extra.get("token_id") or "?"
    pool_sym = extra.get("pool_symbol") or "?"
    return [ExecutionBlocker(
        code="NFT_LP_REFINANCE_INCOMPLETE",
        severity="blocker",
        title=f"V3 LP refinance #{token_id} — multi-step plan missing",
        detail=(
            f"Refinance of {pool_sym} position #{token_id} requires a "
            f"3-step composed plan (collect → close → open). Build path "
            f"emitted {len(step_list)} step(s) "
            f"({', '.join(actions) or 'none'}); refusing to surface a "
            f"partial plan that would either leave fees stranded or "
            f"silently downgrade refinance → supply (financial-loss bug)."
        ),
        affected_step_ids=[getattr(s, "step_id", "") for s in step_list],
        cta=(
            f"Retry with explicit `refinance` verb so the V3 NFT adapter "
            f"emits the full collect+close+open composed plan."
        ),
    )]


# ──────────────────────────────────────────────────────────────────────────
# H12 — CLAIM_COMPOUND
# ──────────────────────────────────────────────────────────────────────────
def detect_claim_compound_blocker(
    *,
    extra: dict[str, Any] | None,
    steps: Iterable[Any] | None,
) -> list[ExecutionBlocker]:
    """Emit CLAIM_COMPOUND_INCOMPLETE when the claim+compound intent
    (`_detect_claim_compound` sets extra.claim_compound=True) didn't
    produce both a claim step AND a reinvest step.

    Pass C H12 leaked raw selectors (0x095ea7b3 / 0xa0712d68) in the
    AI prose because the build path returned a single signable supply
    step instead of the 2-step claim_rewards + reinvest_into_position
    composed plan.
    """
    if not extra or not extra.get("claim_compound"):
        return []
    step_list = list(steps or [])
    actions = [(getattr(s, "action", None) or "") for s in step_list]
    has_claim = any(a in {"claim", "claim_rewards", "harvest"} for a in actions)
    has_reinvest = any(a in {"stake", "supply", "deposit", "lock", "compound"}
                       for a in actions)
    if has_claim and has_reinvest:
        return []
    reward_token = extra.get("reward_token") or "?"
    stake_target = extra.get("stake_target") or "?"
    return [ExecutionBlocker(
        code="CLAIM_COMPOUND_INCOMPLETE",
        severity="blocker",
        title=f"Claim+compound {reward_token} — multi-step plan missing",
        detail=(
            f"Claim+compound intent expects a 2-step composed plan "
            f"(claim {reward_token} → reinvest into {stake_target}). "
            f"Build path emitted {len(step_list)} step(s) "
            f"({', '.join(actions) or 'none'}); refusing to silently "
            f"degrade to a single supply step that ignores the "
            f"unclaimed rewards balance."
        ),
        affected_step_ids=[getattr(s, "step_id", "") for s in step_list],
        cta=(
            f"Retry with `claim+compound` verb so the composer emits "
            f"claim_rewards followed by stake_back/reinvest."
        ),
    )]


# ──────────────────────────────────────────────────────────────────────────
# H14 — V2_TO_V3_MIGRATE
# ──────────────────────────────────────────────────────────────────────────
def detect_v2_to_v3_migrate_blocker(
    *,
    extra: dict[str, Any] | None,
    steps: Iterable[Any] | None,
) -> list[ExecutionBlocker]:
    """Emit V2_TO_V3_MIGRATE_INCOMPLETE when migrate intent
    (`_detect_v2_to_v3_migrate` sets extra.migrate_v2_to_v3=True) didn't
    produce both a V2_remove step and a V3_add step.

    Pass C H14 leaked because the build path silently emitted a single
    supply step with asset_in="LP" — user signs LP-as-ERC20 to V3 mint,
    funds locked.
    """
    if not extra or not extra.get("migrate_v2_to_v3"):
        return []
    step_list = list(steps or [])
    actions = [(getattr(s, "action", None) or "") for s in step_list]
    has_remove = any(a in {"remove_liquidity", "withdraw", "close_position",
                            "decrease_liquidity", "burn"} for a in actions)
    has_add = any(a in {"add_liquidity", "deposit_lp", "lp_mint", "mint",
                         "open_position", "provide_liquidity"} for a in actions)
    if has_remove and has_add:
        return []
    v2_pool = extra.get("v2_pool") or "?"
    v3_proto = extra.get("v3_protocol") or "?"
    return [ExecutionBlocker(
        code="V2_TO_V3_MIGRATE_INCOMPLETE",
        severity="blocker",
        title=f"Migrate V2 {v2_pool} → V3 — multi-step plan missing",
        detail=(
            f"V2→V3 migrate expects a 2-step composed plan "
            f"(V2 remove_liquidity → V3 add_liquidity). Build path "
            f"emitted {len(step_list)} step(s) "
            f"({', '.join(actions) or 'none'}); refusing to surface a "
            f"single-step plan that would either lock the V2 LP or "
            f"deposit LP-token as ERC20 to the V3 router."
        ),
        affected_step_ids=[getattr(s, "step_id", "") for s in step_list],
        cta=(
            f"Retry with `migrate` verb so the V2→{v3_proto} composer "
            f"emits remove + add as separate signable steps."
        ),
    )]


# ──────────────────────────────────────────────────────────────────────────
# H15 — WALLET_MISMATCH
# ──────────────────────────────────────────────────────────────────────────
def detect_wallet_mismatch_blocker(
    *,
    user_address: str | None,
    chain: str | None,
    wallet_chain_kind: str | None = None,
) -> list[ExecutionBlocker]:
    """Spec §13 row H15 — when wallet.chain_kind != plan.chain_kind, refuse.

    Pass C H15 leaked a real signable Aave V3 plan to a guest 0xaaaa…aaaa
    address despite the user signaling "I want to use my Solana wallet".
    The build_yield_execution_plan top-of-function `_is_evm_addr` /
    `_is_sol_addr` checks already cover the address-shape mismatch
    case; THIS detector covers the explicit chain_kind override (e.g.
    runtime passes `extra.wallet_chain_kind="solana"` when the user's
    selected wallet is Phantom-Solana but the planner derived chain=
    "ethereum").
    """
    if not user_address:
        return []
    chain_l = (chain or "").lower()
    if not chain_l:
        return []
    plan_kind = "solana" if chain_l in {"solana", "sol"} else "evm"
    # Derive wallet kind from explicit hint OR from address shape.
    import re as _re
    if wallet_chain_kind:
        wallet_kind = wallet_chain_kind.lower()
    else:
        if user_address.startswith("0x") and len(user_address) == 42:
            wallet_kind = "evm"
        elif _re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", user_address):
            wallet_kind = "solana"
        else:
            wallet_kind = "unknown"
    if wallet_kind == "unknown" or wallet_kind == plan_kind:
        return []
    return [ExecutionBlocker(
        code="WALLET_CHAIN_MISMATCH",
        severity="blocker",
        title=f"Wallet/plan chain-kind mismatch — refusing to sign",
        detail=(
            f"Plan targets {chain_l} (chain_kind={plan_kind}) but the "
            f"connected wallet is chain_kind={wallet_kind} "
            f"(address={user_address[:10]}…). Signing this plan would "
            f"either fail at the wallet layer or, worse, surface a "
            f"completely different address as the recipient. Refusing "
            f"to emit a signable plan."
        ),
        affected_step_ids=[],
        cta=(
            f"Switch to a {plan_kind.upper()} wallet "
            f"({'MetaMask' if plan_kind == 'evm' else 'Phantom (Solana mode)'}) "
            f"and retry, or switch the plan to a {wallet_kind}-supported chain."
        ),
    )]


# ──────────────────────────────────────────────────────────────────────────
# E15 — PRICE_IMPACT_TOO_HIGH gate
# ──────────────────────────────────────────────────────────────────────────
def detect_price_impact_too_high_blocker(
    *,
    steps: Iterable[Any],
    refuse_bps: int = PRICE_IMPACT_REFUSE_BPS,
) -> list[ExecutionBlocker]:
    """Spec §13 E15 — refuse status:ready when any step's price_impact >= 500 bps.

    Reads `step.snapshot["price_impact_bps"]` (or `priceImpactBps`,
    `price_impact_pct`). Pass C E15 logged `Price impact: 10000 bps`
    with status:ready — that's a 100% impact route, almost certainly a
    thin-liquidity gotcha where the user signs and loses ~100% of the
    inflow.
    """
    out: list[ExecutionBlocker] = []
    seen_ids: set[str] = set()
    for step in steps or []:
        pi_bps = _step_price_impact_bps(step)
        if pi_bps is None:
            continue
        if pi_bps < refuse_bps:
            continue
        sid = getattr(step, "step_id", "") or ""
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        out.append(ExecutionBlocker(
            code="PRICE_IMPACT_TOO_HIGH",
            severity="blocker",
            title=f"Price impact too high — {pi_bps} bps",
            detail=(
                f"Step {getattr(step, 'index', '?')} quotes a price impact "
                f"of {pi_bps} bps ({pi_bps / 100.0:.2f}%). Spec §13 refuses "
                f"to surface status:ready for routes ≥{refuse_bps} bps — "
                f"the thin-liquidity loss would consume most of the inflow. "
                f"Try a smaller amount, split across hops, or pick a deeper "
                f"liquidity pool."
            ),
            affected_step_ids=[sid] if sid else [],
            cta=(
                f"Reduce trade size (impact scales super-linearly) OR "
                f"switch to a deeper-liquidity pool. Refusing to sign at "
                f"≥{refuse_bps} bps price impact."
            ),
        ))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Aggregator — single entry-point called by build_yield_execution_plan
# ──────────────────────────────────────────────────────────────────────────
def scan_scenario_blockers(
    *,
    steps: Iterable[Any],
    inventory: Any | None = None,
    extra: dict[str, Any] | None = None,
    protocol: str | None = None,
    action: str | None = None,
    asset_in: str | None = None,
    chain: str | None = None,
    user_address: str | None = None,
    dst_chain: str | None = None,
    refuse_price_impact_bps: int = PRICE_IMPACT_REFUSE_BPS,
    enable_dust: bool = True,
) -> list[ExecutionBlocker]:
    """Run every §13 scenario detector, return the union of emitted blockers.

    Each individual detector is fail-soft (returns []) when its trigger
    inputs are missing, so callers can pass the full kwarg set even if
    most are None — only the detectors with enough signal to fire will
    add to the output list.
    """
    out: list[ExecutionBlocker] = []
    step_list = list(steps or [])
    # H07
    if enable_dust:
        try:
            out.extend(detect_dust_below_threshold_blocker(steps=step_list))
        except Exception:  # noqa: BLE001
            pass
    # H08
    try:
        out.extend(detect_partial_allowance_blocker(
            steps=step_list, inventory=inventory,
        ))
    except Exception:  # noqa: BLE001
        pass
    # H09
    try:
        out.extend(detect_gas_missing_dst_blocker(
            steps=step_list, inventory=inventory, dst_chain=dst_chain,
        ))
    except Exception:  # noqa: BLE001
        pass
    # H10
    if protocol and action and asset_in:
        try:
            out.extend(detect_lst_already_deposited_blocker(
                protocol=protocol, action=action, asset_in=asset_in,
                inventory=inventory, chain=chain,
            ))
        except Exception:  # noqa: BLE001
            pass
    # H11
    try:
        out.extend(detect_nft_lp_refinance_blocker(
            extra=extra, steps=step_list,
        ))
    except Exception:  # noqa: BLE001
        pass
    # H12
    try:
        out.extend(detect_claim_compound_blocker(
            extra=extra, steps=step_list,
        ))
    except Exception:  # noqa: BLE001
        pass
    # H14
    try:
        out.extend(detect_v2_to_v3_migrate_blocker(
            extra=extra, steps=step_list,
        ))
    except Exception:  # noqa: BLE001
        pass
    # H15
    if user_address and chain:
        wck = None
        if extra:
            wck = extra.get("wallet_chain_kind") or extra.get("wallet_kind")
        try:
            out.extend(detect_wallet_mismatch_blocker(
                user_address=user_address, chain=chain,
                wallet_chain_kind=wck,
            ))
        except Exception:  # noqa: BLE001
            pass
    # E15
    try:
        out.extend(detect_price_impact_too_high_blocker(
            steps=step_list, refuse_bps=refuse_price_impact_bps,
        ))
    except Exception:  # noqa: BLE001
        pass
    return out
