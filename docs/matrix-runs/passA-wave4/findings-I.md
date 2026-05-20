# Matrix Pass A — Wave 4 — Category I findings

`SUMMARY: CLOSED=1 STILL=6 MUTATED=2 NEW=3 P0_REMAINING=2 P1_REMAINING=5`

## STILL — P0 (3)

### P0-I-01 — REVOKE_SESSION_KEY action missing
I02/I03/I05 t4 (`Revoke …`) → freeform fallback ("No deterministic DeFi tool matched"). Zero `revoke_session_key` / `nexus_revoke` routing across all 21 I-turns.
Fix: add `revoke_session_key` + `revoke_approval` verb tokens to `src/agent/intent/defi_intent.py::parse_defi_intent`; wire to existing `src/defi/execution/adapters/nexus_revoke.py`.

### P0-I-02 — Session-key flow entirely absent
All 21 I-turns hit freeform `"No deterministic DeFi tool matched the request"`. Zero `session_key_*` card_type emitted.
Fix: extend `defi_intent.py` with `session_key_install` / `_revoke` / `aa_install_module` / `kernel_policy_create` verbs on tokens: `session key`, `kernel policy`, `ZeroDev`, `Nexus EIP-7702`, `install module`, `autonomous rebalancing`, `spend cap`, `selector allowlist`.

### P0-I-03 — SESSION_KEY_MIRROR_DRIFT untestable
Blocked by P0-I-02.

## MUTATED (2)

### NEW-I-01 — Card↔narrative divergence MUTATED (worse)
I02 t3: narrative says "daily $100 across 8 pools" while `allocation` card shows 5 positions × $200 = $1,000. Plus narrative "blended APY ~4.6%" while card has "~5.8%". Outright numeric divergence on amount, count, APY.
Fix: `src/agent/strategy/allocation_composer.py` — derive narrative numerics from same payload dict that builds the card.

### NEW-I-02 — ERC-20 template misroute MUTATED
I02 CLOSED, I05 STILL (still asks for "Revoke approval for USDC on Uniswap V3" / "Revoke staking position on Lido" / "Revoke bridge allowance for USDC via deBridge" ERC-20-style for a Kernel session-key revoke).

## STILL — P1 (3)

### P1-I-02 — off-topic search for LST/Marinade
I03 t1 "LST on Ethereum" returns Saturn SUSDAT, gmtrade FX-perps; zero Lido/Rocket/EtherFi/stETH. I04 t1 "Marinade on Solana" returns 7 gmtrade pools + 1 orca ZEC-USDC; zero Marinade.
Fix: emit `protocol_filter` for `marinade|lido|rocket|etherfi|swell|frax|mantle|kelp|jito` + `protocol_family="LST"` when text matches `\b(LST|liquid stak|liquid restak|LRT)\b`.

### P1-I-03 — freeform fallback gives executable advice (SCOPE EXPANDED)
I01 t2 invents `$500 daily cap` + Nexus UI path; I02 t3 narrative wedges "Enable a keeper-based trigger (e.g., Gelato or Sentinel's autonomous module)" into emitted card; I04 t3 verbatim Marinade imperative; I05 t1 hallucinated `impl address`.
Fix: refuse imperative UI instructions + named third-party services in freeform composer.

### NEW-I-03 — Cadence-adverb hallucination "daily" → asset_hint="DAILY" (STILL)
I01 t1 `asset_hint:"DAILY"` → "Ranked 234 candidates; 0 matched".
Fix: `defi_intent.py:324` — after `asset = (match.group(4) or "").upper() or None`, add `if asset in {"DAILY","WEEKLY","HOURLY","MONTHLY","YEARLY","ANNUALLY","BIWEEKLY","QUARTERLY"}: asset = None`.

## NEW (3)

### NEW-I-04 (P0) — Hallucinated contract impl-address narrative
I05 t1: "The impl address you're asking about is the address of the ZeroDev Kernel policy you just created … Once you sign and submit the policy, your wallet will show that contract's impl address." Invented contract + promised post-sign behavior.
Fix: same as P0-I-02 (session-key intent grammar) + stricter "no invented contract addresses / no promised post-sign behavior" guard.

### NEW-I-05 (P1) — Allocation card emitted on session-key turn
I02 t3 user asks session-key install with spend cap; agent emits `allocation` card with no spend-cap field, no session-key policy, placeholder $1,000/$200 weights.
Fix: gate allocation card emission on absence of `session_key_*` / `spend_cap` / `policy` tokens.

### NEW-I-06 (P2) — Chain-label drift persists in allocation card
I02 t3 rows: `chain="mainnet"`, `"eth"`, `"op"` while source `defi_opportunities` had `"scroll"`, `"ethereum"`, `"optimism"`. Row 3 scroll USDC pool relabeled mainnet (different chain).
Fix: copy `chain` verbatim from source item.

## Verdict
Commit `231c299` (scratchpad strip + withdraw(0)) has zero observed impact on I-category (parser-grammar root cause). All 3 wave-3 P0s persist. NEW-I-01 worsened. 2 new findings (NEW-I-04 P0, NEW-I-05 P1).

Files of interest:
- `src/agent/intent/defi_intent.py` (cadence stoplist line 324; session-key verb grammar entire file)
- `src/defi/execution/adapters/nexus_revoke.py` (existing adapter, unreachable from parser)
- `src/defi/execution/models.py` (REVOKE_SESSION_KEY / INSTALL_SESSION_KEY constants exist)
- `src/agent/strategy/allocation_composer.py` (chain-label drift + narrative↔card divergence)
