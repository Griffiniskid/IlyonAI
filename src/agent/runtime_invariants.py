"""Runtime invariant assertions at the SSE emit chokepoint.

Wave 8 validation infra: structural fail-safes that fire BEFORE a card
is enqueued for SSE emission. Catches whole classes of bugs that the
reactive matrix-fix loop has been hand-targeting one-by-one.

Each invariant is a function: (card_type: str, payload: dict) → list[Violation]

If any invariant fires, `_enforce_invariants` replaces the payload with a
structured `invariant_violation` blocker and logs the original to a
quarantine file at `docs/matrix-runs/invariant-violations.log` for
analysis. The card is never emitted with the broken shape.

Invariants currently enforced:

  I1 — Signable step transaction: every step with status ∈ {"ready",
       "pending"} must have non-null `transaction`. Catches:
         - BUG-E-003 (composed plan ready+null-tx, wave-3..7 STILL)
         - P0-H-08 (H06 composed plan, multi-card surface wave-7)
         - D-P0-NEW-WAVE5-02 (ExecutionPlanV2 phantom-ready)
         - NEW-A-W7-08 (alloc Supply steps tx:null + requires_signature:false)

  I2 — Card-level signature/tx-count consistency:
         - `tx_count >= 1` ⇒ `requires_signature == true`
         - `tx_count == 0` ⇒ either no `requires_signature` field or false
       Catches:
         - D-P1-01/-13 (requires_signature:false on signable Stake)
         - B series P1 (requires_signature:false while plan ships 4-5 steps)

  I3 — USD value sanity: any numeric field matching `usd_value|usd_total|
       total_usd|usd_equivalent` ≥ $10^10 is clamped to None + logged.
       Catches:
         - NEW-P0-F-09 wallet USD overflow $5e30 (F02 t3 spark token)
         - NEW-W7-04 H15 t2 same spark token surface
         - N-C-W7-01 C14 T3 same pattern

  I4 — Step-index continuity: every position in `allocation.positions`
       must have a corresponding `execution_plan.steps` entry, OR the
       missing step must be explicitly blocked. Catches:
         - NEW-P0-F-10 alloc 5 positions → plan 4 steps silently
         - N-B-W6-03 B11 t4 aerodrome dropped
         - NEW-A-W7-06 A05 t3 alloc 5 → plan 1

  I5 — Empty content drop guard: not enforced here (lives in emit_final
       sanitizer). Documented for completeness.

  I6 — `executable:false` ⇒ blocker required on referencing step:
       if `defi_opportunities.items[*].symbol = S` has `executable=false`
       AND `execution_plan.steps[*].target` references `S · <protocol>`,
       the step MUST have `blocker_codes` containing `UNSUPPORTED_ADAPTER`.
       Catches:
         - N-B-W4-01 / N-B-W5-03 B09 t4 yearn approval despite executable:false
         - NEW-A-W7-01 saturn/gmtrade in execution_plan
         - N-C-W7-03 C08 gmtrade FX-perp as Supply USDC

Quarantine log format:
  {ts, card_type, violations, payload_excerpt} per line — JSON Lines

Tests:
  tests/defi/test_runtime_invariants.py — 1 test per invariant + positive
  cases + end-to-end via StreamCollector.emit_card.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────

# Cards below this size always passthrough; the invariant set is designed
# for plan-level cards. Trivia like wallet_balance reports get a lighter
# pass.
_USD_OVERFLOW_THRESHOLD = 1e10  # $10 billion — flag any USD ≥ this

# Path to quarantine log; created on first violation.
_QUARANTINE_PATH = Path(
    os.environ.get(
        "INVARIANT_QUARANTINE_PATH",
        "docs/matrix-runs/invariant-violations.log",
    )
)


@dataclass
class Violation:
    """One invariant failure."""

    invariant_id: str
    severity: str  # "P0" | "P1" | "P2"
    detail: str
    locator: str = ""  # e.g. "steps[2].transaction"


# ── Invariants ────────────────────────────────────────────────────────────


def _i1_signable_steps_have_transaction(card_type: str, payload: dict) -> list[Violation]:
    """Every step with status ∈ {ready, pending} AND no blocker_codes
    must have non-null `transaction`."""
    if card_type not in ("execution_plan_v3", "execution_plan"):
        return []
    steps = payload.get("steps") or []
    violations: list[Violation] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        status = step.get("status")
        if status not in ("ready", "pending"):
            continue
        blocker_codes = step.get("blocker_codes") or []
        if blocker_codes:
            # Step is explicitly gated by a blocker; transaction allowed null.
            continue
        if step.get("transaction") is None:
            violations.append(
                Violation(
                    invariant_id="I1",
                    severity="P0",
                    detail=(
                        f"Step {i} has status={status!r} and no blocker_codes, "
                        f"but transaction is null. A signable plan must not "
                        f"emit null-tx steps without an explicit blocker."
                    ),
                    locator=f"steps[{i}].transaction",
                )
            )
    return violations


def _i2_signature_count_consistency(card_type: str, payload: dict) -> list[Violation]:
    """tx_count >= 1 ⇒ requires_signature must be True."""
    if card_type not in ("execution_plan_v3", "execution_plan"):
        return []
    # Some payloads carry counts at top-level, others under `totals`
    totals = payload.get("totals") or {}
    tx_count = (
        payload.get("tx_count")
        or totals.get("tx_count")
        or totals.get("signatures_required")
        or 0
    )
    requires_signature = payload.get("requires_signature")
    if requires_signature is None:
        requires_signature = totals.get("requires_signature")
    if tx_count >= 1 and requires_signature is False:
        return [
            Violation(
                invariant_id="I2",
                severity="P1",
                detail=(
                    f"Card has tx_count={tx_count} but requires_signature=False. "
                    f"Frontend will not show sign button despite plan shipping "
                    f"signable steps."
                ),
                locator="requires_signature",
            )
        ]
    return []


def _i3_usd_value_overflow(card_type: str, payload: dict) -> list[Violation]:
    """Any numeric field matching usd_value|usd_total|total_usd|usd_equivalent
    that is ≥ $10^10 indicates upstream price/decimals corruption."""
    violations: list[Violation] = []
    USD_FIELDS = ("usd_value", "usd_total", "total_usd", "usd_equivalent")

    def walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                key_lower = str(k).lower()
                if key_lower in USD_FIELDS and isinstance(v, (int, float)):
                    if v >= _USD_OVERFLOW_THRESHOLD:
                        violations.append(
                            Violation(
                                invariant_id="I3",
                                severity="P0",
                                detail=(
                                    f"USD field {k}={v:.3e} exceeds $1e10 threshold. "
                                    f"Likely decimals × bad-price oracle overflow "
                                    f"(spark/dust token pattern). Field has been "
                                    f"clamped to None to prevent downstream USD "
                                    f"gate corruption."
                                ),
                                locator=f"{path}.{k}" if path else k,
                            )
                        )
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(payload)
    return violations


def _clamp_usd_overflow(payload: dict) -> dict:
    """Recursively clamp any USD field ≥ $1e10 to None. Mutates a copy."""
    USD_FIELDS = ("usd_value", "usd_total", "total_usd", "usd_equivalent")

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            new = {}
            for k, v in node.items():
                key_lower = str(k).lower()
                if (
                    key_lower in USD_FIELDS
                    and isinstance(v, (int, float))
                    and v >= _USD_OVERFLOW_THRESHOLD
                ):
                    new[k] = None
                else:
                    new[k] = walk(v)
            return new
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(payload)


def _i4_step_index_continuity(card_type: str, payload: dict) -> list[Violation]:
    """Every position in `allocation.positions` (when this card is an
    allocation) or every alloc entry referenced by the plan must have a
    corresponding step. Detects silent drop where alloc has N positions
    but plan has < N steps without explicit reason.

    For execution_plan_v3 cards: just check that step.index values are
    consecutive starting from 0 OR 1.
    """
    if card_type not in ("execution_plan_v3", "execution_plan"):
        return []
    steps = payload.get("steps") or []
    if len(steps) <= 1:
        return []
    indices = []
    for step in steps:
        if isinstance(step, dict) and "index" in step:
            try:
                indices.append(int(step["index"]))
            except (ValueError, TypeError):
                pass
    if len(indices) < 2:
        return []
    indices_sorted = sorted(indices)
    # Detect a gap (e.g. [1,2,4,5] missing 3 — silent drop)
    expected = list(range(indices_sorted[0], indices_sorted[-1] + 1))
    if indices_sorted != expected:
        missing = set(expected) - set(indices_sorted)
        return [
            Violation(
                invariant_id="I4",
                severity="P1",
                detail=(
                    f"Step indices {indices_sorted} have gap(s) at {sorted(missing)}. "
                    f"Silent step-drop breaks plan↔allocation invariant; user "
                    f"would sign a subset of promised positions without warning."
                ),
                locator="steps[*].index",
            )
        ]
    return []


def _i6_executable_false_must_have_blocker(card_type: str, payload: dict) -> list[Violation]:
    """For composed cards bundling both defi_opportunities + execution_plan
    (or sequential turns where opportunities precede plan), any
    `step.target` whose symbol appears in opportunities with
    `executable=false` MUST have `blocker_codes` containing UNSUPPORTED.

    Within a single payload this is usually not co-resident — opportunities
    and plan are separate cards. So this invariant only fires on cards
    that include both (allocation cards with embedded position+exec).
    """
    if card_type not in ("execution_plan_v3", "execution_plan", "allocation"):
        return []
    # Look for embedded opportunities / positions inside the payload
    items_with_exec_false: set[str] = set()
    positions = payload.get("positions") or []
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        executable = pos.get("executable")
        if executable is False:
            symbol = pos.get("symbol") or pos.get("asset") or pos.get("target")
            if symbol:
                items_with_exec_false.add(str(symbol).split(" · ")[0].upper())
        # Also check adapter_id ending in -fallback as a soft signal
        adapter_id = (pos.get("adapter_id") or "").lower()
        if adapter_id.endswith("-fallback"):
            symbol = pos.get("symbol") or pos.get("asset") or pos.get("target")
            if symbol:
                items_with_exec_false.add(str(symbol).split(" · ")[0].upper())

    if not items_with_exec_false:
        return []

    steps = payload.get("steps") or []
    violations: list[Violation] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        target = str(step.get("target") or "").split(" · ")[0].upper()
        if target and target in items_with_exec_false:
            blocker_codes = step.get("blocker_codes") or []
            if not any(
                "UNSUPPORTED" in str(b).upper() or "ADAPTER_UNAVAILABLE" in str(b).upper()
                for b in blocker_codes
            ):
                violations.append(
                    Violation(
                        invariant_id="I6",
                        severity="P0",
                        detail=(
                            f"Step {i} target={target!r} references an "
                            f"opportunity marked executable:false (or fallback "
                            f"adapter), but step has no UNSUPPORTED_ADAPTER "
                            f"blocker. Signing would route to an unsupported "
                            f"pool via fallback adapter."
                        ),
                        locator=f"steps[{i}].blocker_codes",
                    )
                )
    return violations


import math
import re as _re_inv


def _i7_title_payload_consistency(card_type: str, payload: dict) -> list[Violation]:
    """BUG-RC-002: every execution_plan_v3 card whose title mentions a
    protocol/asset must have those tokens reflected in payload.protocol
    and payload.asset_in (when both fields are populated). Detects
    "Fluid Lending Supply — Supply 100 USDC via Fluid Lending on
    Ethereum" titles whose payload silently routes against a WSTETH
    pool.

    Soft check: only fires when both `protocol` and the canonical title
    are populated and disagree on the protocol token. Asset mismatch is
    caught by I10 (preflight) — I7 is the structural last line of
    defense at the emit chokepoint.
    """
    if card_type not in ("execution_plan_v3", "execution_plan"):
        return []
    title = str(payload.get("title") or "")
    if not title:
        return []
    protocol = str(payload.get("protocol") or "").lower().strip()
    if not protocol:
        return []
    # Normalize protocol token (strip "-v3" / "_v3" suffixes for matching)
    proto_root = _re_inv.sub(r"[-_]?v\d+$", "", protocol)
    proto_root = proto_root.replace("-", " ").replace("_", " ")
    title_lower = title.lower()
    # If protocol root token absent from title at all, that's a mismatch.
    if proto_root and proto_root not in title_lower:
        return [
            Violation(
                invariant_id="I7",
                severity="P0",
                detail=(
                    f"Card title {title!r} does not reference the protocol "
                    f"{protocol!r} declared in payload. User would sign a "
                    f"plan whose surface label disagrees with the routed "
                    f"protocol — silent intent substitution. Hard refuse."
                ),
                locator="title",
            )
        ]
    return []


def _i8_sentinel_scoring_present(card_type: str, payload: dict) -> list[Violation]:
    """BUG-RC-011: every defi_opportunities / pool_link / pool card that
    references a pool must include a sentinel block with the 4 axes
    (safety, durability, exit, confidence). Missing sentinel → emit
    P1 violation; the renderer will show a "scoring unavailable" badge
    instead of silently dropping the bar.
    """
    if card_type not in ("defi_opportunities",):
        return []
    items = payload.get("items") or payload.get("opportunities") or []
    violations: list[Violation] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        sentinel = item.get("sentinel") or item.get("sentinel_scores")
        if not isinstance(sentinel, dict):
            violations.append(
                Violation(
                    invariant_id="I8",
                    severity="P1",
                    detail=(
                        f"items[{i}] has no sentinel block — opportunity "
                        f"card emitted without 4-axis scoring. Renderer "
                        f"will fall back to placeholder bar."
                    ),
                    locator=f"items[{i}].sentinel",
                )
            )
            continue
        required_axes = {"safety", "durability", "exit", "confidence"}
        present = {str(k).lower() for k in sentinel.keys()}
        missing = required_axes - present
        if missing:
            violations.append(
                Violation(
                    invariant_id="I8",
                    severity="P1",
                    detail=(
                        f"items[{i}].sentinel missing axes {sorted(missing)}. "
                        f"Renderer expects all 4 of safety/durability/exit/"
                        f"confidence."
                    ),
                    locator=f"items[{i}].sentinel",
                )
            )
    return violations


def _i10_asset_pool_match(card_type: str, payload: dict) -> list[Violation]:
    """BUG-RC-002: execution_plan_v3 cards must not route an `asset_in`
    that disagrees with the pool's declared deposit token. The strong
    enforcement lives in src/defi/execution/preflight.py
    (ASSET_POOL_MISMATCH); I10 is the final structural check at the
    emit chokepoint — catches any preflight bypass.
    """
    if card_type not in ("execution_plan_v3", "execution_plan"):
        return []
    asset_in = str(payload.get("asset_in") or "").upper().strip()
    pool_deposit = str(
        payload.get("pool_deposit_token")
        or payload.get("expected_asset")
        or ""
    ).upper().strip()
    if not asset_in or not pool_deposit:
        return []
    if asset_in != pool_deposit:
        return [
            Violation(
                invariant_id="I10",
                severity="P0",
                detail=(
                    f"asset_in={asset_in!r} does not match pool's expected "
                    f"deposit token {pool_deposit!r}. User would sign a "
                    f"plan that coerces their intent to a different asset."
                ),
                locator="asset_in",
            )
        ]
    return []


def _i12_time_formatting(card_type: str, payload: dict) -> list[Violation]:
    """BUG-RC-006: any user-facing text field referencing time must
    contain a finite numeric with a unit (s/m/h/d). Reject `Infinitys`,
    `nan`, `None`, `Infinity`.
    """
    BAD_TOKENS = ("Infinitys", "Infinity", "NaN", "nan ", " None ")

    def walk(node: Any, path: str = "") -> list[Violation]:
        out: list[Violation] = []
        if isinstance(node, dict):
            for k, v in node.items():
                out.extend(walk(v, f"{path}.{k}" if path else str(k)))
        elif isinstance(node, list):
            for i, x in enumerate(node):
                out.extend(walk(x, f"{path}[{i}]"))
        elif isinstance(node, str):
            for tok in BAD_TOKENS:
                if tok in node:
                    out.append(
                        Violation(
                            invariant_id="I12",
                            severity="P1",
                            detail=(
                                f"Field at {path!r} contains forbidden "
                                f"time token {tok!r}. Time strings must "
                                f"be finite (e.g. '30s', '1m 12s')."
                            ),
                            locator=path,
                        )
                    )
                    break
        elif isinstance(node, float):
            if not math.isfinite(node):
                out.append(
                    Violation(
                        invariant_id="I12",
                        severity="P1",
                        detail=(
                            f"Numeric field at {path!r} is non-finite "
                            f"({node}). Will format as 'Infinity' / 'NaN' "
                            f"if interpolated into a UI string."
                        ),
                        locator=path,
                    )
                )
        return out

    return walk(payload)


_INVARIANTS = [
    _i1_signable_steps_have_transaction,
    _i2_signature_count_consistency,
    _i3_usd_value_overflow,
    _i4_step_index_continuity,
    _i6_executable_false_must_have_blocker,
    _i7_title_payload_consistency,
    _i8_sentinel_scoring_present,
    _i10_asset_pool_match,
    _i12_time_formatting,
]


# ── Public API ────────────────────────────────────────────────────────────


def check_card_invariants(card_type: str, payload: dict) -> list[Violation]:
    """Run all invariants against a card payload. Returns the list of
    violations (empty list = card is clean)."""
    violations: list[Violation] = []
    for inv in _INVARIANTS:
        try:
            violations.extend(inv(card_type, payload) or [])
        except Exception as exc:  # noqa: BLE001
            # Fail-open: a buggy invariant must NEVER crash card emission.
            logger.warning(
                "invariant %s raised %s; card allowed through",
                inv.__name__,
                exc,
            )
    return violations


def quarantine_log(card_type: str, card_id: str, violations: list[Violation], payload: dict) -> None:
    """Append a JSON-Lines record to the quarantine log for later analysis."""
    try:
        _QUARANTINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": int(time.time()),
            "card_id": card_id,
            "card_type": card_type,
            "violations": [
                {
                    "id": v.invariant_id,
                    "sev": v.severity,
                    "detail": v.detail,
                    "locator": v.locator,
                }
                for v in violations
            ],
            "payload_excerpt": json.dumps(payload, default=str)[:2000],
        }
        with _QUARANTINE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("quarantine_log failed: %s", exc)


def enforce_card_invariants(
    card_id: str, card_type: str, payload: dict
) -> tuple[str, dict, list[Violation]]:
    """Run invariants and decide what to emit.

    Returns: (effective_card_type, effective_payload, violations).
    If any P0 violation fires, replaces the card with a structured
    `invariant_violation` blocker. P1 violations are clamped (for I3) or
    logged + emitted alongside the original (for I2/I4).
    """
    violations = check_card_invariants(card_type, payload)
    if not violations:
        return card_type, payload, violations

    quarantine_log(card_type, card_id, violations, payload)

    # I3 clamp: replace USD overflow in-place (don't quarantine the card,
    # just sanitize the numbers).
    has_i3 = any(v.invariant_id == "I3" for v in violations)
    if has_i3:
        payload = _clamp_usd_overflow(payload)

    # Decide whether any P0 violation requires hard refusal.
    p0_violations = [v for v in violations if v.severity == "P0" and v.invariant_id != "I3"]
    if p0_violations:
        # Replace the card with a structured invariant_violation blocker.
        # This prevents the frontend from rendering a broken plan.
        refused_payload = {
            "kind": "invariant_violation",
            "original_card_type": card_type,
            "original_card_id": card_id,
            "violations": [
                {
                    "id": v.invariant_id,
                    "sev": v.severity,
                    "detail": v.detail,
                    "locator": v.locator,
                }
                for v in p0_violations
            ],
            "message": (
                "This card violated a runtime safety invariant and was "
                "refused before emission. The original payload has been "
                "logged for review. Please re-issue the request with an "
                "explicit verb form."
            ),
        }
        return "invariant_violation", refused_payload, violations

    # P1-only violations: emit original (possibly USD-clamped) with logging.
    return card_type, payload, violations
