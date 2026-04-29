# Sentinel-Assistant Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fuse the Sentinel scoring agent with the merged wallet assistant so the `/agent/*` chat provides demo-grade Sentinel scoring on every recommendation, safe multi-step execution plans, and an opt-in cross-chain rebalance daemon without modifying the wallet-assistant source tree.

**Architecture:** Use `src/agent/*` as the primary brain. Add scoring and Shield middleware around existing `ToolEnvelope` sidecars, expose wallet-assistant actions through read-only wrapper tools, then add a deterministic planner/executor and optimizer daemon in later phases. Keep `IlyonAi-Wallet-assistant-main/` immutable via a guard script.

**Tech Stack:** Python 3.13, FastAPI/aiohttp agent runtime, Pydantic schemas in `src/api/schemas/agent.py`, LangChain `StructuredTool`, pytest, Next.js/React frontend cards, Bash validation scripts.

---

## File Structure

### Phase 1 — Universal Sentinel Scoring + Routing Guard

- Create `src/scoring/rubric.py`: import and expose the existing demo rubric from `src/allocator/composer.py`; convert a `PoolCandidate` into existing `SentinelBlock` / `ShieldBlock` sidecars.
- Create `src/scoring/normalizer.py`: normalize DefiLlama/DexScreener/wallet-assistant dictionaries into `PoolCandidate`.
- Create `src/scoring/pool_scorer.py`: score pool-like dicts with the rubric.
- Create `src/scoring/route_scorer.py`: lightweight Shield/Sentinel proxy for swap routes.
- Create `src/scoring/bridge_scorer.py`: lightweight Shield/Sentinel proxy for bridge routes.
- Create `src/scoring/cache.py`: deterministic in-memory TTL cache for repeated scoring.
- Create `src/scoring/shield_gate.py`: transaction and plan-level safety verdicts.
- Create `src/agent/tools/sentinel_wrap.py`: decorator that post-processes existing tool envelopes.
- Create `scripts/check_assistant_immutable.sh`: fail if files under `IlyonAi-Wallet-assistant-main/` changed since the checkpoint tag.
- Modify `web/next.config.js`: add `AGENT_BACKEND=sentinel|wallet` routing switch.
- Modify `src/agent/runtime.py`: emit any existing `ToolEnvelope.sentinel` and `ToolEnvelope.shield` as SSE card sidecar events by preserving them on card payloads.
- Add tests under `tests/scoring/` and `tests/agent/test_sentinel_wrap.py`.

### Phase 2 — Multi-Step Planner + Executor

- Create `src/agent/planner.py`: deterministic plan builder for bridge/stake/swap/deposit sequences.
- Create `src/agent/receipt_watcher.py`: EVM/Solana receipt polling helpers.
- Create `src/agent/step_executor.py`: persisted plan state machine.
- Create `src/agent/tools/compose_plan.py`: chat tool that validates and returns an execution plan card.
- Modify `src/api/schemas/agent.py`: add `ExecutionPlanV2Payload` and `PlanStepV2` while preserving existing `PlanStep`.
- Modify `src/agent/streaming.py`: add plan frame helpers only if needed by runtime.
- Add tests under `tests/agent/test_planner.py`, `tests/agent/test_receipt_watcher.py`, and `tests/agent/test_step_executor.py`.

### Phase 3 — Cross-Chain Yield Optimizer

- Create `src/optimizer/snapshot.py`: normalize current holdings into scored positions.
- Create `src/optimizer/target_builder.py`: call existing allocation logic to build target portfolio.
- Create `src/optimizer/delta.py`: apply hysteresis rules to produce rebalance moves.
- Create `src/optimizer/plan_synth.py`: translate moves into planner input.
- Create `src/optimizer/daemon.py`: opt-in scheduler entrypoint.
- Create `src/optimizer/safety.py`: cooldowns, TTL, daily cap.
- Create `scripts/run_optimizer.py` and `scripts/validate_phase_3.sh`.
- Add tests under `tests/optimizer/`.

---

## Phase 1 Tasks

### Task 1: Immutable Assistant Guard

**Files:**
- Create: `scripts/check_assistant_immutable.sh`
- Test: shell command in Step 2

- [ ] **Step 1: Write the guard script**

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_TAG="${ASSISTANT_IMMUTABLE_BASE:-checkpoint/pre-scoring-merge-brainstorm-20260429-133016}"
TARGET_DIR="IlyonAi-Wallet-assistant-main/"

if ! git rev-parse --verify "$BASE_TAG" >/dev/null 2>&1; then
  echo "ERROR: immutable base '$BASE_TAG' does not exist" >&2
  exit 1
fi

changed="$(git diff --name-only "$BASE_TAG" -- "$TARGET_DIR")"
if [ -n "$changed" ]; then
  echo "ERROR: wallet assistant files changed since $BASE_TAG" >&2
  printf '%s\n' "$changed" >&2
  exit 1
fi

echo "OK: wallet assistant is unchanged since $BASE_TAG"
```

- [ ] **Step 2: Run guard against current tree**

Run: `bash scripts/check_assistant_immutable.sh`

Expected: `OK: wallet assistant is unchanged since checkpoint/pre-scoring-merge-brainstorm-20260429-133016`

- [ ] **Step 3: Commit**

Run: `git add scripts/check_assistant_immutable.sh docs/superpowers/plans/2026-04-29-sentinel-assistant-fusion-implementation.md && git commit -m "chore: guard wallet assistant immutability"`

### Task 2: Scoring Rubric Package

**Files:**
- Create: `src/scoring/__init__.py`
- Create: `src/scoring/rubric.py`
- Test: `tests/scoring/test_rubric.py`

- [ ] **Step 1: Write failing tests**

```python
from src.allocator.composer import PoolCandidate
from src.scoring.rubric import score_pool_candidate, sentinel_block_from_candidate


def test_score_pool_candidate_matches_demo_weighting():
    pool = PoolCandidate(
        project="aave-v3",
        symbol="USDC",
        chain="Arbitrum",
        tvl_usd=1_200_000_000,
        apy=6.2,
        audits=True,
        days_live=720,
        stable=True,
        il_risk="no",
        exposure="single",
    )

    score = score_pool_candidate(pool)

    assert score.safety == 100
    assert score.durability == 90
    assert score.exit == 92
    assert score.confidence == 85
    assert score.weighted == 94
    assert score.risk_level == "low"
    assert score.strategy_fit == "balanced"


def test_sentinel_block_from_candidate_uses_existing_schema():
    pool = PoolCandidate(
        project="unknown-farm",
        symbol="USDC-ETH",
        chain="Ethereum",
        tvl_usd=250_000_000,
        apy=32.0,
        audits=False,
        days_live=200,
        stable=True,
        il_risk="yes",
        exposure="multi",
    )

    block = sentinel_block_from_candidate(pool)

    assert block.risk_level in {"HIGH", "MEDIUM", "LOW"}
    assert block.sentinel == 58
    assert "Unaudited" in block.flags
    assert "IL risk" in block.flags
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/scoring/test_rubric.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.scoring'`

- [ ] **Step 3: Implement rubric package**

```python
# src/scoring/__init__.py
from .rubric import PoolSentinelScore, score_pool_candidate, sentinel_block_from_candidate

__all__ = ["PoolSentinelScore", "score_pool_candidate", "sentinel_block_from_candidate"]
```

```python
# src/scoring/rubric.py
from __future__ import annotations

from dataclasses import dataclass

from src.api.schemas.agent import SentinelBlock
from src.allocator.composer import (
    PoolCandidate,
    bucket_fit,
    bucket_risk,
    derive_flags,
    score_confidence,
    score_durability,
    score_exit,
    score_safety,
    weighted_sentinel,
)


@dataclass(frozen=True)
class PoolSentinelScore:
    safety: int
    durability: int
    exit: int
    confidence: int
    weighted: int
    risk_level: str
    strategy_fit: str
    flags: list[str]
    breakdown_explainer: str


def score_pool_candidate(pool: PoolCandidate) -> PoolSentinelScore:
    safety = score_safety(pool)
    durability = score_durability(pool)
    exit_score = score_exit(pool)
    confidence = score_confidence(pool)
    weighted = weighted_sentinel(safety, durability, exit_score, confidence)
    risk_level = bucket_risk(weighted)
    strategy_fit = bucket_fit(weighted, pool.apy)
    flags = derive_flags(pool, weighted)
    explainer = (
        f"Safety {safety}, durability {durability}, exit {exit_score}, "
        f"confidence {confidence}; weighted Sentinel {weighted}/100."
    )
    return PoolSentinelScore(
        safety=safety,
        durability=durability,
        exit=exit_score,
        confidence=confidence,
        weighted=weighted,
        risk_level=risk_level,
        strategy_fit=strategy_fit,
        flags=flags,
        breakdown_explainer=explainer,
    )


def sentinel_block_from_candidate(pool: PoolCandidate) -> SentinelBlock:
    score = score_pool_candidate(pool)
    return SentinelBlock(
        sentinel=score.weighted,
        safety=score.safety,
        durability=score.durability,
        exit=score.exit,
        confidence=score.confidence,
        risk_level=score.risk_level.upper(),
        strategy_fit=score.strategy_fit,
        flags=score.flags,
    )
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/scoring/test_rubric.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run: `git add src/scoring tests/scoring/test_rubric.py && git commit -m "feat(scoring): expose Sentinel rubric package"`

### Task 3: Pool Normalizer And Scorer

**Files:**
- Create: `src/scoring/normalizer.py`
- Create: `src/scoring/pool_scorer.py`
- Test: `tests/scoring/test_pool_scorer.py`

- [ ] **Step 1: Write failing tests**

```python
from src.scoring.normalizer import pool_candidate_from_mapping
from src.scoring.pool_scorer import score_pool_mapping


def test_normalizes_defillama_pool_fields():
    pool = pool_candidate_from_mapping({
        "project": "aave-v3",
        "symbol": "USDC",
        "chain": "Arbitrum",
        "tvlUsd": 850_000_000,
        "apy": 4.8,
        "stablecoin": True,
        "ilRisk": "no",
    })

    assert pool.project == "aave-v3"
    assert pool.symbol == "USDC"
    assert pool.chain == "Arbitrum"
    assert pool.tvl_usd == 850_000_000
    assert pool.audits is True
    assert pool.stable is True
    assert pool.exposure == "single"


def test_score_pool_mapping_returns_existing_sentinel_block():
    block = score_pool_mapping({
        "project": "unknown",
        "symbol": "USDC-ETH",
        "chain": "Ethereum",
        "tvlUsd": 300_000_000,
        "apy": 18.0,
        "stablecoin": False,
        "ilRisk": "yes",
    })

    assert block.sentinel < 82
    assert block.risk_level in {"HIGH", "MEDIUM"}
    assert "Unaudited" in block.flags
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/scoring/test_pool_scorer.py -v`

Expected: FAIL with missing modules.

- [ ] **Step 3: Implement normalizer and pool scorer**

```python
# src/scoring/normalizer.py
from __future__ import annotations

from typing import Any

from src.allocator.composer import PoolCandidate


AUDIT_PROJECTS = {
    "lido", "rocket-pool", "rocketpool", "jito", "aave-v3", "aave-v2",
    "compound-v3", "compound-v2", "pendle", "curve-dex", "curve",
    "ether.fi", "ether-fi", "renzo", "etherfi", "spark", "morpho-blue",
    "makerdao", "convex-finance", "yearn-finance", "stargate", "hyperliquid",
}


def infer_audits(project_slug: str) -> bool:
    return project_slug.lower() in AUDIT_PROJECTS


def infer_stable(symbol: str, pool: dict[str, Any]) -> bool:
    if bool(pool.get("stablecoin")):
        return True
    stable_tokens = ("USDC", "USDT", "DAI", "FRAX", "LUSD", "USDE", "SUSDE", "USDY", "PYUSD", "GHO")
    symbol_upper = symbol.upper()
    return any(token in symbol_upper for token in stable_tokens)


def infer_exposure(symbol: str) -> str:
    return "multi" if "-" in symbol and not symbol.upper().startswith("PT-") else "single"


def infer_days_live(pool: dict[str, Any], audited: bool) -> int:
    explicit = pool.get("days_live") or pool.get("daysLive")
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass
    tvl = float(pool.get("tvlUsd") or pool.get("tvl_usd") or pool.get("liquidity_usd") or 0)
    if audited:
        return 720 if tvl >= 1_000_000_000 else 400
    return 200 if tvl >= 100_000_000 else 60


def pool_candidate_from_mapping(pool: dict[str, Any]) -> PoolCandidate:
    project = str(pool.get("project") or pool.get("protocol") or pool.get("protocol_name") or "Unknown")
    symbol = str(pool.get("symbol") or pool.get("asset") or pool.get("pair") or "?")
    audited = bool(pool.get("audits")) if "audits" in pool else infer_audits(project)
    tvl = float(pool.get("tvlUsd") or pool.get("tvl_usd") or pool.get("liquidity_usd") or 0)
    return PoolCandidate(
        project=project,
        symbol=symbol,
        chain=str(pool.get("chain") or pool.get("chain_name") or "Ethereum"),
        tvl_usd=tvl,
        apy=float(pool.get("apy") or pool.get("apr") or pool.get("yield") or 0),
        audits=audited,
        days_live=infer_days_live(pool, audited),
        stable=infer_stable(symbol, pool),
        il_risk=str(pool.get("ilRisk") or pool.get("il_risk") or "no"),
        exposure=str(pool.get("exposure") or infer_exposure(symbol)),
        raw_flags=tuple(str(flag) for flag in pool.get("flags", []) if str(flag).strip()),
    )
```

```python
# src/scoring/pool_scorer.py
from __future__ import annotations

from typing import Any

from src.api.schemas.agent import SentinelBlock
from src.scoring.normalizer import pool_candidate_from_mapping
from src.scoring.rubric import sentinel_block_from_candidate


def score_pool_mapping(pool: dict[str, Any]) -> SentinelBlock:
    return sentinel_block_from_candidate(pool_candidate_from_mapping(pool))
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/scoring/test_pool_scorer.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run: `git add src/scoring/normalizer.py src/scoring/pool_scorer.py tests/scoring/test_pool_scorer.py && git commit -m "feat(scoring): normalize and score pool mappings"`

### Task 4: Shield Gate

**Files:**
- Create: `src/scoring/shield_gate.py`
- Test: `tests/scoring/test_shield_gate.py`

- [ ] **Step 1: Write failing tests**

```python
from src.scoring.shield_gate import shield_for_transaction


def test_shield_warns_for_high_slippage():
    verdict = shield_for_transaction({"slippage_bps": 800, "spender": "Enso"})

    assert verdict.verdict == "RISKY"
    assert verdict.grade == "D"
    assert "High slippage" in verdict.reasons


def test_shield_blocks_known_malicious_destination():
    verdict = shield_for_transaction({"to": "0x000000000000000000000000000000000000dEaD"})

    assert verdict.verdict == "SCAM"
    assert verdict.grade == "F"
    assert "Known malicious destination" in verdict.reasons
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/scoring/test_shield_gate.py -v`

Expected: FAIL with missing module.

- [ ] **Step 3: Implement shield gate**

```python
# src/scoring/shield_gate.py
from __future__ import annotations

from typing import Any

from src.api.schemas.agent import ShieldBlock

MALICIOUS_ADDRESSES = {"0x000000000000000000000000000000000000dead"}
ALLOWED_SPENDERS = {"enso", "jupiter", "uniswap", "pancakeswap", "debridge", "stargate", "layerzero"}


def shield_for_transaction(tx: dict[str, Any]) -> ShieldBlock:
    reasons: list[str] = []
    severity = 0

    to_address = str(tx.get("to") or tx.get("recipient") or "").lower()
    if to_address in MALICIOUS_ADDRESSES:
        reasons.append("Known malicious destination")
        severity = max(severity, 4)

    slippage_bps = int(tx.get("slippage_bps") or tx.get("slippageBps") or 0)
    if slippage_bps > 1500:
        reasons.append("Critical slippage")
        severity = max(severity, 4)
    elif slippage_bps > 500:
        reasons.append("High slippage")
        severity = max(severity, 3)
    elif slippage_bps > 100:
        reasons.append("Elevated slippage")
        severity = max(severity, 1)

    spender = str(tx.get("spender") or tx.get("router") or "").lower()
    if spender and not any(allowed in spender for allowed in ALLOWED_SPENDERS):
        reasons.append("Unrecognized spender")
        severity = max(severity, 2)

    if tx.get("approval_amount") in {"max", "MAX_UINT256"}:
        reasons.append("Infinite approval")
        severity = max(severity, 1)

    verdicts = {
        0: ("SAFE", "A"),
        1: ("CAUTION", "B"),
        2: ("RISKY", "C"),
        3: ("RISKY", "D"),
        4: ("SCAM", "F"),
    }
    verdict, grade = verdicts[severity]
    return ShieldBlock(verdict=verdict, grade=grade, reasons=reasons)
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/scoring/test_shield_gate.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run: `git add src/scoring/shield_gate.py tests/scoring/test_shield_gate.py && git commit -m "feat(scoring): add Shield transaction gate"`

### Task 5: Sentinel Tool Wrapper

**Files:**
- Create: `src/agent/tools/sentinel_wrap.py`
- Test: `tests/agent/test_sentinel_wrap.py`

- [ ] **Step 1: Write failing tests**

```python
from src.agent.tools._base import ok_envelope
from src.agent.tools.sentinel_wrap import attach_pool_score, attach_transaction_shield


def test_attach_pool_score_adds_sentinel_sidecar():
    env = ok_envelope(
        data={"project": "aave-v3", "symbol": "USDC", "chain": "Arbitrum", "tvlUsd": 900_000_000, "apy": 4.2},
        card_type="pool",
        card_payload={"protocol": "aave-v3", "asset": "USDC", "chain": "Arbitrum", "apy": "4.2%", "tvl": "$900M"},
    )

    wrapped = attach_pool_score(env)

    assert wrapped.sentinel is not None
    assert wrapped.sentinel.sentinel >= 82
    assert wrapped.card_payload["sentinel"]["sentinel"] == wrapped.sentinel.sentinel


def test_attach_transaction_shield_adds_shield_sidecar():
    env = ok_envelope(data={"slippage_bps": 800, "spender": "UnknownRouter"}, card_type=None, card_payload=None)

    wrapped = attach_transaction_shield(env)

    assert wrapped.shield is not None
    assert wrapped.shield.verdict == "RISKY"
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/agent/test_sentinel_wrap.py -v`

Expected: FAIL with missing module.

- [ ] **Step 3: Implement sentinel wrapper helpers**

```python
# src/agent/tools/sentinel_wrap.py
from __future__ import annotations

from typing import Any

from src.api.schemas.agent import ToolEnvelope
from src.scoring.pool_scorer import score_pool_mapping
from src.scoring.shield_gate import shield_for_transaction


def _model_dump(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(obj)


def attach_pool_score(envelope: ToolEnvelope, source: dict[str, Any] | None = None) -> ToolEnvelope:
    if not envelope.ok:
        return envelope
    raw = source or envelope.data or envelope.card_payload or {}
    sentinel = score_pool_mapping(raw)
    envelope.sentinel = sentinel
    if envelope.card_payload is not None:
        envelope.card_payload = {**envelope.card_payload, "sentinel": _model_dump(sentinel)}
    return envelope


def attach_transaction_shield(envelope: ToolEnvelope, source: dict[str, Any] | None = None) -> ToolEnvelope:
    if not envelope.ok:
        return envelope
    raw = source or envelope.data or envelope.card_payload or {}
    shield = shield_for_transaction(raw)
    envelope.shield = shield
    if envelope.card_payload is not None:
        envelope.card_payload = {**envelope.card_payload, "shield": _model_dump(shield)}
    return envelope
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/agent/test_sentinel_wrap.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run: `git add src/agent/tools/sentinel_wrap.py tests/agent/test_sentinel_wrap.py && git commit -m "feat(agent): attach Sentinel and Shield sidecars to tool envelopes"`

### Task 6: Routing Kill Switch

**Files:**
- Modify: `web/next.config.js`
- Test: `web/tests/next-config-agent-backend.test.cjs`

- [ ] **Step 1: Write failing test**

```javascript
const assert = require("assert");

async function loadRewrites(agentBackend) {
  delete require.cache[require.resolve("../next.config.js")];
  process.env.AGENT_BACKEND = agentBackend;
  process.env.API_REWRITE_TARGET = "http://sentinel:8080";
  process.env.ASSISTANT_API_TARGET = "http://wallet:8000";
  const config = require("../next.config.js");
  return config.rewrites();
}

(async () => {
  const sentinel = await loadRewrites("sentinel");
  const sentinelAgent = sentinel.find((r) => r.source === "/api/v1/agent");
  assert.strictEqual(sentinelAgent.destination, "http://sentinel:8080/api/v1/agent");

  const wallet = await loadRewrites("wallet");
  const walletAgent = wallet.find((r) => r.source === "/api/v1/agent");
  assert.strictEqual(walletAgent.destination, "http://wallet:8000/api/v1/agent");
})();
```

- [ ] **Step 2: Verify test fails**

Run: `node web/tests/next-config-agent-backend.test.cjs`

Expected: FAIL because `AGENT_BACKEND=sentinel` still points to wallet.

- [ ] **Step 3: Implement routing switch**

In `web/next.config.js` inside `rewrites()` replace the assistant target lines with:

```js
    const apiTarget = process.env.API_REWRITE_TARGET || "http://localhost:8080";
    const walletAssistantTarget = process.env.ASSISTANT_API_TARGET || "http://localhost:8000";
    const agentBackend = process.env.AGENT_BACKEND || "wallet";
    const assistantTarget = agentBackend === "sentinel" ? apiTarget : walletAssistantTarget;
```

- [ ] **Step 4: Verify test passes**

Run: `node web/tests/next-config-agent-backend.test.cjs`

Expected: no output and exit 0.

- [ ] **Step 5: Commit**

Run: `git add web/next.config.js web/tests/next-config-agent-backend.test.cjs && git commit -m "feat(web): add agent backend routing switch"`

---

## Phase 2 Tasks

### Task 7: Plan Schemas

**Files:**
- Modify: `src/api/schemas/agent.py`
- Test: `tests/agent/test_plan_schemas.py`

- [ ] **Step 1: Write failing tests**

```python
from src.api.schemas.agent import ExecutionPlanV2Payload, PlanStepV2


def test_execution_plan_v2_payload_validates_steps():
    step = PlanStepV2(
        step_id="step-1",
        order=1,
        action="bridge",
        params={"token_in": "USDC", "src_chain_id": 1, "dst_chain_id": 42161},
        status="ready",
    )
    plan = ExecutionPlanV2Payload(
        plan_id="plan-1",
        title="Bridge USDC to Arbitrum",
        steps=[step],
        total_steps=1,
        total_gas_usd=8.0,
        total_duration_estimate_s=90,
        blended_sentinel=None,
        requires_signature_count=1,
        risk_warnings=[],
    )

    assert plan.steps[0].action == "bridge"
    assert plan.risk_gate == "clear"
```

- [ ] **Step 2: Verify test fails**

Run: `pytest tests/agent/test_plan_schemas.py -v`

Expected: FAIL because `ExecutionPlanV2Payload` is missing.

- [ ] **Step 3: Implement schemas**

Add below existing `PlanPayload` in `src/api/schemas/agent.py`:

```python
class PlanStepV2(_Strict):
    step_id: str
    order: int
    action: Literal[
        "swap", "bridge", "stake", "unstake", "deposit_lp", "withdraw_lp",
        "transfer", "approve", "wait_receipt", "get_balance",
    ]
    params: dict[str, Any]
    depends_on: list[str] = Field(default_factory=list)
    resolves_from: dict[str, str] = Field(default_factory=dict)
    sentinel: Optional[SentinelBlock] = None
    shield_flags: list[str] = Field(default_factory=list)
    estimated_gas_usd: Optional[float] = None
    estimated_duration_s: Optional[int] = None
    status: Literal["pending", "ready", "signing", "broadcast", "confirmed", "failed", "skipped"] = "pending"
    tx_hash: Optional[str] = None
    receipt: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ExecutionPlanV2Payload(_CardPayloadBase):
    plan_id: str
    title: str
    steps: list[PlanStepV2]
    total_steps: int
    total_gas_usd: float
    total_duration_estimate_s: int
    blended_sentinel: Optional[int] = Field(default=None, ge=0, le=100)
    requires_signature_count: int
    risk_warnings: list[str] = Field(default_factory=list)
    risk_gate: Literal["clear", "soft_warn", "hard_block"] = "clear"
    requires_double_confirm: bool = False
    chains_touched: list[str] = Field(default_factory=list)
    user_assets_required: dict[str, str] = Field(default_factory=dict)
```

Then add an `ExecutionPlanV2Card` to `_CardUnion` and `CardType` with card type `execution_plan_v2`.

- [ ] **Step 4: Verify test passes**

Run: `pytest tests/agent/test_plan_schemas.py -v`

Expected: 1 passed.

- [ ] **Step 5: Commit**

Run: `git add src/api/schemas/agent.py tests/agent/test_plan_schemas.py && git commit -m "feat(agent): add execution plan v2 schemas"`

### Task 8: Planner

**Files:**
- Create: `src/agent/planner.py`
- Test: `tests/agent/test_planner.py`

- [ ] **Step 1: Write failing tests**

```python
from src.agent.planner import build_plan


def test_bridge_then_stake_injects_wait_receipt_and_soft_warns():
    plan = build_plan({
        "title": "Bridge USDC to Arbitrum and stake on Aave",
        "steps": [
            {"action": "bridge", "params": {"token_in": "USDC", "amount": "1000000000", "src_chain_id": 1, "dst_chain_id": 42161}},
            {"action": "stake", "params": {"token": "USDC", "protocol": "aave-v3", "chain_id": 42161}, "resolves_from": {"amount": "step-1.received_amount"}},
        ],
    })

    assert [step.action for step in plan.steps] == ["approve", "bridge", "wait_receipt", "stake"]
    assert plan.risk_gate == "soft_warn"
    assert plan.requires_double_confirm is True
```

- [ ] **Step 2: Verify test fails**

Run: `pytest tests/agent/test_planner.py -v`

Expected: FAIL with missing planner module.

- [ ] **Step 3: Implement planner**

```python
# src/agent/planner.py
from __future__ import annotations

from uuid import uuid4

from src.api.schemas.agent import ExecutionPlanV2Payload, PlanStepV2


EVM_ERC20_ACTIONS = {"bridge", "stake", "deposit_lp", "transfer", "swap"}


def _needs_approval(action: str, params: dict) -> bool:
    token = str(params.get("token_in") or params.get("token") or params.get("token_symbol") or "").upper()
    chain_id = int(params.get("src_chain_id") or params.get("chain_id") or 0)
    return action in EVM_ERC20_ACTIONS and chain_id not in {0, 101, 7565164} and token not in {"", "ETH", "BNB", "MATIC", "AVAX", "SOL", "NATIVE"}


def _chain_touch(params: dict) -> list[str]:
    chains = []
    for key in ("src_chain_id", "dst_chain_id", "chain_id"):
        if key in params:
            chains.append(str(params[key]))
    return chains


def build_plan(intent: dict) -> ExecutionPlanV2Payload:
    plan_id = str(uuid4())
    raw_steps = intent.get("steps") or []
    steps: list[PlanStepV2] = []
    risk_warnings: list[str] = []
    chains_touched: list[str] = []
    previous_step_id: str | None = None

    for raw in raw_steps:
        action = str(raw["action"])
        params = dict(raw.get("params") or {})
        chains_touched.extend(_chain_touch(params))
        if _needs_approval(action, params):
            approve_id = str(uuid4())
            steps.append(PlanStepV2(
                step_id=approve_id,
                order=len(steps) + 1,
                action="approve",
                params={"token": params.get("token_in") or params.get("token"), "amount": params.get("amount", "all"), "chain_id": params.get("src_chain_id") or params.get("chain_id")},
                depends_on=[] if previous_step_id is None else [previous_step_id],
                status="ready" if previous_step_id is None else "pending",
            ))
            previous_step_id = approve_id

        step_id = raw.get("step_id") or str(uuid4())
        steps.append(PlanStepV2(
            step_id=step_id,
            order=len(steps) + 1,
            action=action,
            params=params,
            depends_on=[] if previous_step_id is None else [previous_step_id],
            resolves_from=dict(raw.get("resolves_from") or {}),
            status="ready" if previous_step_id is None else "pending",
            estimated_gas_usd=8.0 if action in {"bridge", "swap", "stake", "deposit_lp"} else 2.0,
            estimated_duration_s=90 if action == "bridge" else 30,
        ))
        if action == "bridge":
            risk_warnings.append("Cross-chain execution requires receipt confirmation before follow-up steps.")
        previous_step_id = step_id

        if action == "bridge" and raw is not raw_steps[-1]:
            wait_id = str(uuid4())
            steps.append(PlanStepV2(
                step_id=wait_id,
                order=len(steps) + 1,
                action="wait_receipt",
                params={"source_step_id": step_id},
                depends_on=[step_id],
                status="pending",
                estimated_duration_s=90,
            ))
            previous_step_id = wait_id

    total_gas = sum(step.estimated_gas_usd or 0 for step in steps)
    risk_gate = "soft_warn" if risk_warnings else "clear"
    for index, step in enumerate(steps, start=1):
        step.order = index
    return ExecutionPlanV2Payload(
        plan_id=plan_id,
        title=str(intent.get("title") or "Execution plan"),
        steps=steps,
        total_steps=len(steps),
        total_gas_usd=total_gas,
        total_duration_estimate_s=sum(step.estimated_duration_s or 0 for step in steps),
        blended_sentinel=None,
        requires_signature_count=sum(1 for step in steps if step.action not in {"wait_receipt", "get_balance"}),
        risk_warnings=risk_warnings,
        risk_gate=risk_gate,
        requires_double_confirm=risk_gate == "soft_warn",
        chains_touched=sorted(set(chains_touched)),
        user_assets_required={},
    )
```

- [ ] **Step 4: Verify test passes**

Run: `pytest tests/agent/test_planner.py -v`

Expected: 1 passed.

- [ ] **Step 5: Commit**

Run: `git add src/agent/planner.py tests/agent/test_planner.py && git commit -m "feat(agent): build deterministic multi-step plans"`

---

## Phase 3 Tasks

### Task 9: Rebalance Delta Hysteresis

**Files:**
- Create: `src/optimizer/__init__.py`
- Create: `src/optimizer/delta.py`
- Test: `tests/optimizer/test_delta_hysteresis.py`

- [ ] **Step 1: Write failing tests**

```python
from src.optimizer.delta import MoveCandidate, should_move


def test_should_move_requires_apy_sentinel_and_gas_thresholds():
    candidate = MoveCandidate(usd_value=10_000, apy_delta=2.5, sentinel_delta=3, estimated_gas_usd=20)

    assert should_move(candidate) is True


def test_should_not_move_when_safety_drops():
    candidate = MoveCandidate(usd_value=10_000, apy_delta=5.0, sentinel_delta=-1, estimated_gas_usd=20)

    assert should_move(candidate) is False
```

- [ ] **Step 2: Verify test fails**

Run: `pytest tests/optimizer/test_delta_hysteresis.py -v`

Expected: FAIL with missing optimizer module.

- [ ] **Step 3: Implement delta hysteresis**

```python
# src/optimizer/__init__.py
```

```python
# src/optimizer/delta.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MoveCandidate:
    usd_value: float
    apy_delta: float
    sentinel_delta: int
    estimated_gas_usd: float


def should_move(candidate: MoveCandidate) -> bool:
    annual_benefit = candidate.usd_value * (candidate.apy_delta / 100.0)
    return (
        candidate.apy_delta >= 2.0
        and candidate.sentinel_delta >= 0
        and annual_benefit > 4 * candidate.estimated_gas_usd
    )
```

- [ ] **Step 4: Verify test passes**

Run: `pytest tests/optimizer/test_delta_hysteresis.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run: `git add src/optimizer tests/optimizer/test_delta_hysteresis.py && git commit -m "feat(optimizer): add rebalance hysteresis rules"`

---

## Final Verification

- [ ] Run immutable guard: `bash scripts/check_assistant_immutable.sh`
- [ ] Run focused tests: `pytest tests/scoring tests/agent/test_sentinel_wrap.py tests/agent/test_plan_schemas.py tests/agent/test_planner.py tests/optimizer/test_delta_hysteresis.py -v`
- [ ] Run existing demo parity if server dependencies are available: `bash scripts/validate_demo_parity.sh`
- [ ] Run `gitnexus_detect_changes({scope: "all"})` and confirm affected flows are limited to scoring/agent/optimizer/docs/web-config.
- [ ] Run `git status --short` and report uncommitted generated artifacts separately.

## Self-Review

- Spec coverage: Phase 1 scoring/routing guard, Phase 2 planner schemas/execution foundation, Phase 3 optimizer hysteresis foundation are covered.
- Scope note: This implementation plan intentionally implements a working vertical slice of each phase first. Full receipt watching, daemon scheduling, UI cards, and live request scripts remain follow-up tasks inside the same spec after the slice is green.
- Placeholder scan: no `TBD`/`TODO` placeholders.
- Type consistency: tests use existing `SentinelBlock`, `ShieldBlock`, `ToolEnvelope`, and new `PlanStepV2`/`ExecutionPlanV2Payload` consistently.
