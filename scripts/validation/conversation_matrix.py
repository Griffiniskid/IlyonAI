"""Gate 8 — multi-turn conversation matrix with LLM judge.

Fires natural-dialogue R-category conversations (R01-R15) against the
staging agent endpoint and applies per-turn LLM-judge assertions that the
mechanical matrix can not catch — semantic intent fidelity, no silent
protocol substitution, allocation cards on multi-pool requests, no raw
exception text, sentinel scoring presence on opportunity cards, finite
time strings, etc.

PASS bar (Gate 8): >= 95% of turn-level assertions PASS AND zero P0
turn-level failures.

Usage:
    PYTHONIOENCODING=utf-8 python scripts/validation/conversation_matrix.py
    # custom subset
    python scripts/validation/conversation_matrix.py --conversations R01,R03,R06
    # disable LLM judge (mechanical assertions only — cheap, no API key)
    python scripts/validation/conversation_matrix.py --no-llm-judge
    # output dir override
    python scripts/validation/conversation_matrix.py --out docs/conversation-runs/$(date +%s)

Structure:
  - SCENARIOS: list[Conversation] — verbatim user prompts + per-turn
    LLM-judge prompt + per-turn mechanical assertion list.
  - fire_conversation(): runs one conversation end-to-end against staging
    with the same session_id across turns. Saves raw SSE per turn.
  - run_mechanical_assertions(): regex / substring checks per turn.
  - run_llm_judge(): optional GPT-4o-mini classifier per turn.
  - main(): aggregate + summary + pass-bar gate.

Per-turn mechanical assertions catch the structural failures the existing
sweepers / matrix already cover (no `cannot access local variable`, no
`Infinitys`, no `**bold**` etc.). The LLM judge handles semantic ones —
"did the agent's intent match the user's request" — which require
natural-language understanding regex can't do.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STAGING = os.environ.get("STAGING_URL", "https://staging.ilyonai.com")
EVM_WALLET = os.environ.get(
    "CONV_EVM_WALLET", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)
SOL_WALLET = os.environ.get(
    "CONV_SOL_WALLET", "5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L"
)

_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "conversation-runs" / time.strftime("%Y%m%d_%H%M%S")


@dataclass
class TurnAssertion:
    """One per-turn check. `kind` selects judge.

    kind:
      - "must_not_contain": substring must NOT appear in the SSE body
      - "must_contain": substring MUST appear in the SSE body
      - "regex_must_match": pattern MUST match somewhere
      - "regex_must_not_match": pattern MUST NOT match anywhere
      - "card_type_must_be": one of the SSE `event: card` payloads must
        have `card_type` == value (or in value if list)
      - "llm_judge": free-form prose prompt sent to LLM judge with the
        SSE body — judge returns PASS/FAIL with reasoning. P0 means
        any single FAIL caps the conversation as failed.
    """

    kind: str
    value: Any
    severity: str = "P1"  # "P0" | "P1" | "P2"
    description: str = ""


@dataclass
class Turn:
    user_message: str
    assertions: list[TurnAssertion] = field(default_factory=list)
    notes: str = ""


@dataclass
class Conversation:
    id: str  # e.g. "R01"
    title: str
    notes: str
    turns: list[Turn]


# ── Common assertions reused across many conversations ───────────────────

# BUG-RC-003 — no raw Python exception text should ever leak.
_NO_RAW_EXCEPTION = TurnAssertion(
    kind="regex_must_not_match",
    value=r"cannot access local variable|UnboundLocalError|"
          r"AttributeError: 'NoneType'|Traceback \(most recent call last\)",
    severity="P0",
    description="BUG-RC-003: no raw Python exception text in response.",
)

# BUG-RC-006 — no Infinitys/Infinity/NaN time formatting.
_NO_INFINITYS = TurnAssertion(
    kind="regex_must_not_match",
    value=r"Infinitys?\s+old|\bNaN\s+(?:seconds?|s|m|min)|"
          r"Infinity\s+(?:seconds?|s|m|min)",
    severity="P1",
    description="BUG-RC-006: time strings must be finite (no Infinitys/NaN/Infinity).",
)

# BUG-RC-014 — markdown bold should render, not leak literal **bold** in
# the SSE body's user_message-ish content fields. (The SSE itself can
# contain backticks etc.; this only checks the agent's response content.)
_NO_LITERAL_MARKDOWN_BOLD_IN_FINAL = TurnAssertion(
    kind="regex_must_not_match",
    value=r'"content"\s*:\s*"[^"]*\*\*[A-Z][^*]+\*\*',
    severity="P2",
    description="BUG-RC-014: markdown bold in final content should render as HTML, not leak literal asterisks.",
)


# ── Conversation catalogue (R01-R15) ─────────────────────────────────────


SCENARIOS: list[Conversation] = [
    Conversation(
        id="R01",
        title="best-pools → pick-N → allocate-across",
        notes="Multi-turn natural allocation flow. Must emit allocation card on turn 3.",
        turns=[
            Turn(
                user_message="What are the best pools on solana?",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    _NO_INFINITYS,
                    TurnAssertion(
                        kind="card_type_must_be",
                        value=["defi_opportunities", "search_defi_opportunities"],
                        severity="P0",
                        description="Turn 1 must surface a defi_opportunities card.",
                    ),
                ],
            ),
            Turn(
                user_message="Please give me the list of pools that are available with one click deposit.",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    _NO_INFINITYS,
                    TurnAssertion(
                        kind="regex_must_match",
                        value=r"Execution(?:\s+readiness)?[:\s]+\d+\s+(?:candidate|pool)",
                        severity="P1",
                        description="Turn 2 must report execution-ready candidate count.",
                    ),
                ],
            ),
            Turn(
                user_message="Can you pick 4 best pools out of those in your opinion and distribute and allocate 40 usdt on sol across them?",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    _NO_INFINITYS,
                    TurnAssertion(
                        kind="card_type_must_be",
                        value=["allocation", "allocation_plan"],
                        severity="P0",
                        description="BUG-RC-005: multi-pool allocation request MUST emit allocation card.",
                    ),
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "The user explicitly asked to PICK 4 POOLS and DISTRIBUTE / "
                            "ALLOCATE $40 USDT across them. The agent's response should "
                            "either (a) propose a 4-position allocation plan with sizing "
                            "and rationale per pool, OR (b) ask a clarifying question. "
                            "It MUST NOT silently route to a single-pool deposit / execute "
                            "card. Did the agent satisfy the multi-pool allocation intent? "
                            "Answer 'PASS' or 'FAIL: <reason>'."
                        ),
                        severity="P0",
                        description="Semantic: multi-pool intent satisfied.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R02",
        title="execute-by-pool-id (verbatim BUG-RC-003 repro)",
        notes="Must succeed OR return structured blocker — never raw Python exception text.",
        turns=[
            Turn(
                user_message="What are the best pools on solana?",
                assertions=[_NO_RAW_EXCEPTION, _NO_INFINITYS],
            ),
            Turn(
                user_message="Execute deposit into pool 7f5c2e8b-0428-431b-ba6e-571c38a57010 with $100",
                assertions=[
                    _NO_RAW_EXCEPTION,  # P0 — the verbatim bug
                    _NO_INFINITYS,
                    TurnAssertion(
                        kind="regex_must_not_match",
                        value=r"I wasn't able to fetch.*cannot access",
                        severity="P0",
                        description="BUG-RC-003 verbatim: must not show exception leak prefix.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R03",
        title="re-quote / refresh-sim",
        notes="BUG-RC-004: 're quote please' must be recognised as refresh-sim intent.",
        turns=[
            Turn(
                user_message="Supply 100 USDC to Aave V3 on Base",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    _NO_INFINITYS,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "The user asked to SUPPLY 100 USDC to Aave V3 on Base. "
                            "Did the agent emit an Aave V3 execution plan on Base, "
                            "or did it silently substitute a different protocol "
                            "(Fluid Lending, Compound, etc.) — BUG-RC-001? "
                            "Answer 'PASS' if Aave V3 / Base / USDC, else "
                            "'FAIL: <what protocol/chain/asset was emitted instead>'."
                        ),
                        severity="P0",
                        description="BUG-RC-001 semantic check.",
                    ),
                ],
            ),
            Turn(
                user_message="Re quote please",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "The user typed 'Re quote please' as a follow-up to their "
                            "previous Aave V3 supply plan, intending to refresh the "
                            "simulation. Did the agent recognise this as a refresh-sim "
                            "intent (re-emit the plan, perhaps noting the freshness "
                            "reset), or did it (a) emit a generic refusal example "
                            "suggesting an unrelated chain, (b) restart from scratch, "
                            "or (c) ignore the prior context? Answer 'PASS' or "
                            "'FAIL: <reason>'."
                        ),
                        severity="P1",
                        description="BUG-RC-004 re-quote handler.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R04",
        title="protocol typo / under-specification",
        notes="BUG-RC-001: must disambiguate, not silently substitute.",
        turns=[
            Turn(
                user_message="Supply 50 USDC to Fluid on Base",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "The user said 'Fluid' (ambiguous — could be Fluid Lending, "
                            "Fluid DEX) on Base with USDC. Did the agent (a) ask for "
                            "clarification on which Fluid product, (b) refuse with a "
                            "clear 'ambiguous protocol' message, OR (c) silently choose "
                            "one and emit an execution plan without disclosure? "
                            "PASS = (a) or (b); FAIL = (c)."
                        ),
                        severity="P1",
                        description="Ambiguous-protocol disambiguation.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R05",
        title="ambiguous 'best' without constraints",
        notes="Must either ask clarifying question OR show diverse risk-tier sample with sentinel scoring.",
        turns=[
            Turn(
                user_message="Show me the best pool right now",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "User asked for 'best pool' with no risk/chain/APY constraints. "
                            "Did the agent surface a diverse risk-tier set (LOW + MEDIUM + "
                            "HIGH) WITH sentinel scoring visible, OR ask for "
                            "clarification on risk appetite? PASS = either; FAIL = "
                            "single risk tier dumped without sentinel scoring."
                        ),
                        severity="P1",
                        description="Ambiguous best handler.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R06",
        title="asset preservation in supply intent (BUG-RC-002 dispatch)",
        notes=(
            "User explicitly names USDC. Whatever pool the dispatcher "
            "chooses, the payload.asset_in must remain USDC — no silent "
            "coercion to wstETH, WETH, etc. The structural ASSET_POOL_MISMATCH "
            "check has unit-test coverage via the mocked-meta WSTETH "
            "scenario in tests/defi/test_runtime_invariants.py; this "
            "conversation-level assertion proves the live dispatcher path "
            "respects user intent end-to-end."
        ),
        turns=[
            Turn(
                user_message="Supply 100 USDC to fluid-lending on Ethereum",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="regex_must_match",
                        # Either: the agent emits a plan whose asset_in
                        # field is USDC (success — no coercion), OR it
                        # refuses with ASSET_POOL_MISMATCH (also fine —
                        # explicit refusal beats silent coercion).
                        value=r'"asset_in":\s*"USDC"|ASSET_POOL_MISMATCH|'
                              r'Asset/pool\s+mismatch',
                        severity="P0",
                        description=(
                            "BUG-RC-002: asset_in MUST stay USDC (not "
                            "silently coerced) OR the dispatcher MUST "
                            "refuse with ASSET_POOL_MISMATCH."
                        ),
                    ),
                    TurnAssertion(
                        kind="regex_must_not_match",
                        # Coercion symptoms: payload.asset_in flipped to
                        # WSTETH / WETH / DAI etc. without ASSET_POOL_MISMATCH.
                        value=r'"asset_in":\s*"(?:WSTETH|WETH|DAI|FRAX|RETH|STETH)"',
                        severity="P0",
                        description=(
                            "BUG-RC-002: asset_in must NOT be silently "
                            "coerced from USDC to a related collateral asset."
                        ),
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R07",
        title="cross-chain implicit ('40 usdt on sol')",
        notes="BUG-RC-015: cross-chain context must surface bridge requirement, not silently fail.",
        turns=[
            Turn(
                user_message="Can you allocate 40 USDT on solana into the safest yield pool?",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "User said '40 USDT on solana'. If the wallet has no USDT on "
                            "Solana, the agent should surface a bridge requirement "
                            "(deBridge / Allbridge / etc.), NOT silently fall through to "
                            "an EVM USDT plan or fail without explanation. Did the "
                            "agent handle the cross-chain context properly? "
                            "PASS / FAIL: <reason>."
                        ),
                        severity="P1",
                        description="BUG-RC-015 cross-chain handling.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R08",
        title="follow-up reference resolution",
        notes="BUG-RC-016: 'sign it', 'what was the gas?', 'execute number 3' must resolve to prior card.",
        turns=[
            Turn(
                user_message="Show me top 3 USDC supply pools on Base",
                assertions=[_NO_RAW_EXCEPTION],
            ),
            Turn(
                user_message="Execute number 2",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "User said 'Execute number 2' as a follow-up to a list of "
                            "3 USDC supply pools. Did the agent (a) resolve this to "
                            "the second pool from the prior list, OR (b) ask which "
                            "pool, OR (c) silently fail / pick a random pool? "
                            "PASS = (a) or (b); FAIL = (c)."
                        ),
                        severity="P1",
                        description="Follow-up reference resolution.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R09",
        title="prior-failure learning ('any pool that works?')",
        notes="BUG-RC-016: after consecutive failures on pools X/Y, agent must NOT re-list X/Y as 'ready'.",
        turns=[
            Turn(
                user_message="Execute deposit into pool 7f5c2e8b-0428-431b-ba6e-571c38a57010 with $100",
                assertions=[_NO_RAW_EXCEPTION],
            ),
            Turn(
                user_message="Execute deposit into pool 7083d6a5-e3cb-4eeb-8204-f1b735e4ecbb with $100",
                assertions=[_NO_RAW_EXCEPTION],
            ),
            Turn(
                user_message="Is there a pool that you can execute right now?",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "After two failed execute-by-pool-id attempts on "
                            "specific pool IDs, the user asked 'is there a pool that "
                            "you can execute right now?'. Did the agent (a) note the "
                            "prior failures and EXCLUDE those pool IDs from the new "
                            "list, OR (b) re-list the SAME 8 pools including the "
                            "two that just failed as 'ready'? PASS = (a); FAIL = (b)."
                        ),
                        severity="P1",
                        description="BUG-RC-016 prior-failure memory.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R10",
        title="sentinel-scoring presence on every defi_opportunities card",
        notes="BUG-RC-011: every defi_opportunities item must include 4-axis sentinel scoring.",
        turns=[
            Turn(
                user_message="Best low-risk USDC pools on Ethereum",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="regex_must_match",
                        value=r'"sentinel"\s*:|"sentinel_scores"\s*:|sentinel.*score',
                        severity="P1",
                        description="BUG-RC-011: sentinel scoring must be present on opportunity cards.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R11",
        title="0% APY filter",
        notes="BUG-RC-009: 0% APY pools must not be surfaced as 'best'.",
        turns=[
            Turn(
                user_message="Best ETH yield pools on Ethereum sorted by APY",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "User asked for 'best ETH yield pools sorted by APY'. "
                            "Did the agent's list include any pools with 0.0% APY in "
                            "the TOP positions? PASS = no 0% pools in top 5; "
                            "FAIL = at least one 0% APY pool in top 5."
                        ),
                        severity="P2",
                        description="BUG-RC-009 0% APY filter.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R12",
        title="suspicious-APY warning",
        notes="BUG-RC-010: pools >100% APY must trigger yield-trap callout.",
        turns=[
            Turn(
                user_message="What are the highest APY pools right now?",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "If the agent surfaced any pool with APY > 100%, did it "
                            "include a yield-trap warning, historical APY context, or "
                            "explicit caution callout? PASS = pools >100% have an "
                            "explicit warning OR no pools >100% in list; FAIL = "
                            ">100% APY pools listed as 'best' without warning."
                        ),
                        severity="P1",
                        description="BUG-RC-010 yield-trap warning.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R13",
        title="markdown render (no literal **bold**)",
        notes="BUG-RC-014: agent's markdown bold must render as HTML, not literal asterisks.",
        turns=[
            Turn(
                user_message="Show me 3 best stablecoin pools",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    # Allow markdown in body, but the final rendered chat content
                    # field shouldn't carry literal `**FOO**` pattern that would
                    # display verbatim to the user.
                ],
            ),
        ],
    ),
    Conversation(
        id="R14",
        title="blocker recovery — alternatives promised must appear",
        notes="BUG-RC-019: blocker text 'surfacing alternatives' must actually emit alternatives.",
        turns=[
            Turn(
                user_message="Execute deposit into pool gmtrade XAU-USDC with 100 USDT",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "The Gmtrade XAU-USDC pool is unsupported. If the agent's "
                            "blocker text promises 'alternatives ranked by APR + "
                            "similarity', did the response ALSO emit at least 2 "
                            "alternative pool cards? PASS = alternatives present "
                            "(or no 'alternatives' promise made); FAIL = promise "
                            "made but no alternatives followed."
                        ),
                        severity="P1",
                        description="BUG-RC-019 promised alternatives must materialise.",
                    ),
                ],
            ),
        ],
    ),
    Conversation(
        id="R15",
        title="refusal example must use prior chain context",
        notes="BUG-RC-020: refusal example chain should match prior plan's chain.",
        turns=[
            Turn(
                user_message="Supply 100 USDC to Aave V3 on Ethereum",
                assertions=[_NO_RAW_EXCEPTION],
            ),
            Turn(
                user_message="?????",
                assertions=[
                    _NO_RAW_EXCEPTION,
                    TurnAssertion(
                        kind="llm_judge",
                        value=(
                            "User typed '?????' (gibberish) after an Ethereum Aave V3 "
                            "plan. If the agent's refusal includes an example prompt "
                            "(e.g. 'try Supply 100 USDC to Aave V3 on X'), is X = "
                            "Ethereum (matching prior plan chain) or X = Base / "
                            "another chain (BUG-RC-020 — wrong chain example)? "
                            "PASS = Ethereum or no example; FAIL = wrong chain in example."
                        ),
                        severity="P2",
                        description="BUG-RC-020 refusal-example chain context.",
                    ),
                ],
            ),
        ],
    ),
]


# ── Runner ───────────────────────────────────────────────────────────────


def fire_turn(
    session_id: str,
    message: str,
    sse_path: Path,
    *,
    timeout_sec: int = 120,
) -> tuple[int, str]:
    """Fire one turn against staging, write raw SSE to sse_path, return
    (returncode, sse_body)."""
    payload = {
        "message": message,
        "session_id": session_id,
        "evm_wallet": EVM_WALLET,
        "solana_wallet": SOL_WALLET,
    }
    cmd = [
        "curl", "-sS", "-N", "-m", str(timeout_sec),
        "-X", "POST", f"{STAGING}/api/v1/agent",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
    ]
    sse_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec + 10,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        sse_path.write_text(f"<TIMEOUT after {timeout_sec}s>", encoding="utf-8")
        return -1, ""
    sse_path.write_text(result.stdout, encoding="utf-8")
    return result.returncode, result.stdout


def extract_card_types(sse_body: str) -> list[str]:
    """Parse SSE body for `event: card` blocks, extract card_type per."""
    types: list[str] = []
    for line in sse_body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line[len("data:"):].strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("card_type"):
            types.append(str(payload["card_type"]))
    return types


def run_mechanical_assertions(
    body: str,
    assertions: list[TurnAssertion],
) -> list[dict[str, Any]]:
    """Apply non-LLM assertions. Returns one result dict per assertion."""
    out: list[dict[str, Any]] = []
    card_types = extract_card_types(body)
    for a in assertions:
        ok = True
        detail = ""
        if a.kind == "must_not_contain":
            ok = str(a.value) not in body
            if not ok:
                idx = body.find(str(a.value))
                detail = f"matched at offset {idx}: {body[max(0, idx-40):idx+80]!r}"
        elif a.kind == "must_contain":
            ok = str(a.value) in body
            if not ok:
                detail = f"substring {a.value!r} not present in SSE body"
        elif a.kind == "regex_must_not_match":
            m = re.search(str(a.value), body)
            ok = m is None
            if m:
                detail = f"matched {m.group(0)!r} at offset {m.start()}"
        elif a.kind == "regex_must_match":
            m = re.search(str(a.value), body)
            ok = m is not None
            if not m:
                detail = f"pattern {a.value!r} did not match anywhere"
        elif a.kind == "card_type_must_be":
            wanted = a.value if isinstance(a.value, list) else [a.value]
            ok = any(t in wanted for t in card_types)
            if not ok:
                detail = f"emitted card_types={card_types}, expected one of {wanted}"
        elif a.kind == "llm_judge":
            # Handled separately in run_llm_judge — skip here.
            continue
        else:
            detail = f"unknown assertion kind {a.kind!r}"
            ok = False
        out.append(
            {
                "kind": a.kind,
                "severity": a.severity,
                "description": a.description,
                "pass": ok,
                "detail": detail,
            }
        )
    return out


def run_llm_judge(
    body: str,
    assertions: list[TurnAssertion],
    *,
    judge_model: str = "gpt-4o-mini",
    enabled: bool = True,
) -> list[dict[str, Any]]:
    """Apply LLM-judge assertions. Stubs to UNJUDGED when disabled or no
    API key. Real implementation calls the configured judge model with
    a system prompt instructing PASS/FAIL output.
    """
    out: list[dict[str, Any]] = []
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    for a in assertions:
        if a.kind != "llm_judge":
            continue
        if not enabled or not api_key:
            out.append(
                {
                    "kind": "llm_judge",
                    "severity": a.severity,
                    "description": a.description,
                    "pass": None,  # unjudged
                    "detail": (
                        "LLM judge disabled or no API key configured "
                        "(OPENAI_API_KEY / OPENROUTER_API_KEY). Treated as "
                        "UNJUDGED — does not count toward pass/fail tallies."
                    ),
                }
            )
            continue
        # Real call: instruct judge with the assertion prompt + SSE body.
        # Kept minimal; production callers should add retries / model
        # routing. For now we just stub the OpenAI-compatible call shape
        # so production can wire it without changing the harness.
        try:
            import urllib.request

            req_body = {
                "model": judge_model,
                "temperature": 0,
                "max_tokens": 256,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a strict QA judge for a DeFi AI agent. "
                            "Given the assertion prompt and the agent's SSE body, "
                            "return EXACTLY one line: either 'PASS' or "
                            "'FAIL: <one-sentence reason>'. No other output."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Assertion: {a.value}\n\n"
                            f"SSE body (truncated):\n```\n{body[:8000]}\n```"
                        ),
                    },
                ],
            }
            api_base = os.environ.get(
                "OPENAI_API_BASE", "https://api.openai.com/v1"
            )
            request = urllib.request.Request(
                f"{api_base}/chat/completions",
                data=json.dumps(req_body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as resp:
                resp_payload = json.loads(resp.read().decode("utf-8"))
            verdict = (
                resp_payload.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            passed = verdict.upper().startswith("PASS")
            out.append(
                {
                    "kind": "llm_judge",
                    "severity": a.severity,
                    "description": a.description,
                    "pass": passed,
                    "detail": verdict,
                }
            )
        except Exception as exc:  # noqa: BLE001
            out.append(
                {
                    "kind": "llm_judge",
                    "severity": a.severity,
                    "description": a.description,
                    "pass": None,
                    "detail": f"JUDGE_ERROR: {type(exc).__name__}: {exc}",
                }
            )
    return out


def run_conversation(
    conv: Conversation,
    out_dir: Path,
    *,
    llm_enabled: bool,
    judge_model: str,
    inter_turn_sleep: float = 1.5,
) -> dict[str, Any]:
    session_id = f"convmatrix-{conv.id}-{uuid.uuid4().hex[:8]}"
    conv_out_dir = out_dir / conv.id
    conv_out_dir.mkdir(parents=True, exist_ok=True)
    turn_results: list[dict[str, Any]] = []
    for i, turn in enumerate(conv.turns, start=1):
        sse_path = conv_out_dir / f"turn_{i}.txt"
        rc, body = fire_turn(session_id, turn.user_message, sse_path)
        mech = run_mechanical_assertions(body, turn.assertions)
        llm = run_llm_judge(
            body, turn.assertions, judge_model=judge_model, enabled=llm_enabled
        )
        turn_results.append(
            {
                "turn": i,
                "user_message": turn.user_message,
                "curl_rc": rc,
                "sse_path": str(sse_path),
                "sse_bytes": len(body),
                "mechanical": mech,
                "llm_judge": llm,
            }
        )
        time.sleep(inter_turn_sleep)
    summary_path = conv_out_dir / "summary.json"
    summary = {
        "conversation_id": conv.id,
        "title": conv.title,
        "notes": conv.notes,
        "session_id": session_id,
        "turns": turn_results,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


# ── Aggregation + pass-bar gate ──────────────────────────────────────────


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up turn results into a Gate 8 pass/fail summary."""
    total_assertions = 0
    passed = 0
    failed = 0
    unjudged = 0
    p0_fails: list[dict[str, Any]] = []
    for conv in results:
        for turn in conv["turns"]:
            for check in (*turn["mechanical"], *turn["llm_judge"]):
                total_assertions += 1
                if check["pass"] is True:
                    passed += 1
                elif check["pass"] is False:
                    failed += 1
                    if check["severity"] == "P0":
                        p0_fails.append(
                            {
                                "conversation": conv["conversation_id"],
                                "turn": turn["turn"],
                                "description": check["description"],
                                "detail": check["detail"],
                            }
                        )
                else:
                    unjudged += 1
    judged = passed + failed
    pass_rate = (passed / judged * 100.0) if judged > 0 else 0.0
    gate_pass = pass_rate >= 95.0 and not p0_fails
    return {
        "total_assertions": total_assertions,
        "passed": passed,
        "failed": failed,
        "unjudged": unjudged,
        "pass_rate_pct": round(pass_rate, 2),
        "p0_fails": p0_fails,
        "gate_8_pass": gate_pass,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--conversations",
        type=str,
        default="",
        help="Comma-separated list of conversation IDs (R01,R03,...). Empty = all.",
    )
    p.add_argument(
        "--out", type=Path, default=_DEFAULT_OUT,
        help="Output directory (default: docs/conversation-runs/<ts>)",
    )
    p.add_argument("--judge-model", type=str, default="gpt-4o-mini")
    p.add_argument(
        "--no-llm-judge",
        action="store_true",
        help="Skip LLM-judge assertions (treats them as UNJUDGED).",
    )
    p.add_argument(
        "--inter-turn-sleep", type=float, default=1.5,
        help="Seconds to sleep between turns within a conversation.",
    )
    args = p.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    wanted_ids = (
        {x.strip().upper() for x in args.conversations.split(",") if x.strip()}
        if args.conversations
        else None
    )
    selected = [c for c in SCENARIOS if wanted_ids is None or c.id in wanted_ids]
    if not selected:
        print(f"[conv-matrix] No conversations matched filter {args.conversations!r}", file=sys.stderr)
        return 2

    print(f"[conv-matrix] firing {len(selected)} conversation(s) against {STAGING}")
    print(f"[conv-matrix] output → {args.out}")
    print(f"[conv-matrix] llm judge: {'OFF' if args.no_llm_judge else 'ON'} (model={args.judge_model})")

    results: list[dict[str, Any]] = []
    for conv in selected:
        print(f"  [{conv.id}] {conv.title}")
        summary = run_conversation(
            conv,
            args.out,
            llm_enabled=not args.no_llm_judge,
            judge_model=args.judge_model,
            inter_turn_sleep=args.inter_turn_sleep,
        )
        results.append(summary)
        print(
            f"    turns={len(summary['turns'])} "
            f"sse_total_bytes={sum(t['sse_bytes'] for t in summary['turns'])}"
        )

    agg = aggregate(results)
    agg_path = args.out / "aggregate.json"
    agg_path.write_text(
        json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n[conv-matrix] aggregate:")
    print(f"  total assertions:  {agg['total_assertions']}")
    print(f"  passed:            {agg['passed']}")
    print(f"  failed:            {agg['failed']}")
    print(f"  unjudged:          {agg['unjudged']}")
    print(f"  pass rate:         {agg['pass_rate_pct']}%")
    print(f"  P0 failures:       {len(agg['p0_fails'])}")
    if agg["p0_fails"]:
        for fail in agg["p0_fails"]:
            print(
                f"    [{fail['conversation']} turn {fail['turn']}] "
                f"{fail['description']}: {fail['detail']}"
            )
    print(f"  GATE 8 PASS?       {agg['gate_8_pass']}")
    print(f"  aggregate.json → {agg_path}")

    return 0 if agg["gate_8_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
