# findings-I — matrix Pass A wave 1, category I (session-key / AA)

**Scope**: `docs/matrix-runs/passA-wave1/I01..I05/turn_*.txt` — 5 chains, 21 turns.

## Per-chain verdict

| Chain | Turns | SK install card? | Revoke action? | Mirror-drift gate? | Net |
|-------|-------|------------------|----------------|--------------------|-----|
| I01_session_key_aave     | 5 | NO | NO | NO | PARTIAL (freeform + 1 refusal-acked) |
| I02_session_key_compound | 4 | NO (plan emitted but session-keyless) | NO | NO | PARTIAL (state-skip + revoke missing) |
| I03_session_key_LST      | 4 | NO | NO | NO | PARTIAL (off-topic search + freeform on revoke) |
| I04_session_key_marinade | 4 | NO | NO | NO | PARTIAL (off-topic + freeform exec advice) |
| I05_session_key_kernel   | 4 | NO | NO | NO | PARTIAL (100% freeform fallback) |

## P0 findings

### P0-I-01 — REVOKE_SESSION_KEY action missing from plans (V7-074 not routed)
- **Hit**: I02 turn_4, I03 turn_3, I03 turn_4.
- **Evidence**: I02 t4: user asks to revoke → runtime returns "I need a specific action to revoke … please tell me exactly what you'd like to revoke". Yet `src/defi/execution/adapters/nexus_revoke.py` + `REVOKE_SESSION_KEY` StepAction enum exist and are pin-tested.
- **Impact**: V7-074 adapter shipped but agent intent-parser never invokes it. Chat-driven revoke broken end-to-end despite `/api/v1/sessions/{id}/revoke` being LIVE (§11 D.6).
- **Fix path**: route "revoke" + (session-key | approval) context into deterministic REVOKE_* path; do not drop to freeform.

### P0-I-02 — Session-key flow entirely absent across category
- **Hit**: I01–I05 (all 5).
- **Evidence**: Zero `session_key_install`/`session_key_policy`/`aa_install_module` cards across 21 turns. No SESSION_KEY_MIRROR_DRIFT fires. No `EXPECTED_PENDING_AA_DELEGATE` honest stub. I01 t2: user requests autonomous Aave V3 rebalancing w/ $500 daily cap → response treats it as a search-filter problem. I05 all turns: kernel-specific session-key asks → 100% freeform fallback.
- **Impact**: V7-073 calldata builders (`build_install_session_key_module_calldata`, `build_uninstall_*`, selectors `0x9517e29f` / `0xa71763a8`) are shipped + 7 pin tests, but agent never routes user intent to them.
- **Fix path**: intent-parser must recognize "autonomous rebalance" / "daily cap" / "session key" / "auto-compound" / "policy" + AA-kind hints → emit `INSTALL_SESSION_KEY` step.

### P0-I-03 — SESSION_KEY_MIRROR_DRIFT gate untestable end-to-end
- **Hit**: I01–I05 (logical consequence of P0-I-02).
- **Evidence**: Because no install card is ever produced, `src/aa/session_key_mirror.py::compare_policies` cannot be exercised against real on-chain reads in this category. Pin test is unit-only.
- **Impact**: §11 D.5 blocker SESSION_KEY_MIRROR_DRIFT cannot fire from real-request flow. Downstream of P0-I-02.

## P1 findings

### P1-I-01 — BUG-M02 state-skip confirmed (draft → ready, no simulated)
- **Hit**: I02 turn_2.
- **Evidence**: Single response emits `defi_opportunities` + `allocation` + `execution_plan` cards in one SSE frame (step_index:3). Each step has `transaction.serialized: null`, `requires_signature: true`, `blocker: null`. No separate "simulated" card, no `simulated_at`, no `simulated_calldata_hash`. Plan jumps draft → ready without simulated.
- **Status**: BUG-M02 logged in BUG_LEDGER. Fix landed in commit 9ffe441 + projection-jump silent-admit extension; staging needs the next redeploy to pick up.

### P1-I-02 — Off-topic search results when LST / Marinade asked
- **Hit**: I03 t1 (Lido/Rocket Pool expected → got RAVE-USDT, SERV-WETH on uniswap-v4/v3), I04 t1 (Marinade expected → got gmtrade XAU-USDC, GBP-USDC, NZD-USDC forex perps).
- **Evidence**: `search_defi_opportunities` args show `chains=["ethereum"]` (I03) and `chains=["solana"]` (I04) with NO `protocol_filter` or `asset_hint`. Intent-parser dropped LST/Marinade hints silently.
- **Impact**: P1 — cards are technically accurate (DefiLlama-sourced, executable=true) but unrelated to user ask.
- **Fix path**: extract LST class (stETH/wstETH/rETH/cbETH) and protocol-family (marinade-finance, jito, lido) into `protocol_filter`/`asset_hint`.

### P1-I-03 — Freeform fallback gives executable advice without calldata
- **Hit**: I04 turn_3.
- **Evidence**: User asked to stake on Marinade w/ auto-compound. Response: "Open Marinade Finance, connect your Phantom wallet, and stake 0.1 SOL. Enable the auto-compound feature and set the interval to weekly, then confirm the transaction…"
- **Impact**: Inconsistent freeform-fallback gate. I04 t2/t4 + all of I05 correctly emit the refusal line, but I04 t3 leaks step-by-step imperative exec advice.
- **Fix path**: suppress imperative verbs ("open / connect / stake / enable / set / confirm") in freeform-fallback when no deterministic adapter matched.

## P2 observations

- I01 t5: `EXPECTED_REFUSAL_INTENT_ACKED` correctly fired — only runtime gate that engaged in entire category.
- I02 t2 chain-name normalization: same pool labeled "mainnet" (#2) and "eth" (#3) in same allocation card — identical calldata, double-counted.
- AI-unavailable / TOOL_TIMEOUT: NOT observed. `search_defi_opportunities` returned `ok:true` in every call. (Singleton AIRouter fix from BUG-M01 confirmed working.)

## Summary
- Chains reviewed: 5
- Total turns: 21
- P0: 3 (P0-I-01 revoke routing, P0-I-02 session-key intent missing, P0-I-03 mirror-drift untestable)
- P1: 3 (state-skip confirmed, off-topic LST search, freeform exec leak)
- Verdict: **FINDINGS** — P0-I-02 is the root that takes down P0-I-01 and P0-I-03.
