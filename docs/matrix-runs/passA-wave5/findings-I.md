# Matrix Pass A — Wave 5 — Category I findings

`SUMMARY: CLOSED=0 STILL=7 MUTATED=2 NEW=2 P0_REMAINING=5 P1_REMAINING=5`

## STILL — P0 (3)

### P0-I-01 REVOKE_SESSION_KEY action missing
21/21 I-turns: zero `revoke_session_key` / `nexus_revoke` routing. All revoke prompts hit freeform. Unchanged.

### P0-I-02 Session-key flow entirely absent
21/21 I-turns: zero `session_key_*` card_type emitted. All hit "No deterministic DeFi tool matched". Unchanged.

### P0-I-03 SESSION_KEY_MIRROR_DRIFT untestable — blocked by P0-I-02.

## STILL — P1 (4)

### P1-I-02 off-topic LST/Marinade search
I03 t1 "LST on Ethereum" returns saturn/uniswap/curve/zeebu/morpho — zero Lido/Rocket/EtherFi.
I04 t1 "Marinade on Solana" returns 7 gmtrade FX + 1 orca ZEC — zero Marinade.
Fix: emit `protocol_filter=marinade|lido|rocket|etherfi|swell|frax|mantle|kelp|jito` when text matches `\b(LST|liquid stak|liquid restak|LRT|Marinade|mSOL|stETH)\b`.

### P1-I-03 freeform fallback gives executable advice — STILL (guard MISSED)
- I01 t2: "Open the Nexus dApp, go to Portfolio, select your Aave V3 position, tap Settings, enable Autonomous Rebalancing, set the daily cap to $500" — invented $500 + invented UI navigation.
- I01 t4: same UI invention for revoke.
- I02 t3 allocation `## Next steps`: "Enable a keeper-based trigger (e.g., Gelato or Sentinel's autonomous module)" — leaks DESPITE having a card because `card_ids` is non-empty and guard short-circuits.
- I04 t2: "Open your Phantom wallet, locate the signing request" — invented wallet-flow UI.
- I05 t3: "Sign the ZeroDev Kernel policy for autonomous rebalancing with a $200 daily budget" — invented $200/day budget.

Fix: extend `_FREEFORM_TX_STATE_HALLUCINATION_RE` to refuse (1) `open\s+(?:the\s+)?(?:nexus\s+dapp|phantom\s+wallet|metamask|rabby)`, (2) `(?:gelato|sentinel'?s?\s+autonomous\s+module|keeper-based\s+trigger)`, (3) `\$\d+\s*(?:daily|per\s+day|/day)\s+(?:cap|budget|allowance)`, (4) `sign\s+the\s+(?:zerodev\s+kernel|nexus|biconomy)\s+policy`. AND remove `card_ids` short-circuit for narrative composer suffixes.

### NEW-I-03 cadence-adverb "daily" → asset_hint="DAILY"
I01 t1 parsed `asset_hint:"DAILY"` → "Ranked 234 candidates; 0 matched". Stoplist not added at `defi_intent.py:369`.

### NEW-I-05 allocation card emitted on session-key turn
I02 t3 emits defi_opportunities + allocation cards with placeholder $200/pool × 5 = $1,000; zero session_key_*, zero spend_cap, zero policy field.

## MUTATED (2)

### NEW-I-04 (P0) Hallucinated contract impl-address narrative — MUTATED
I05 t1: "After you sign and submit the ZeroDev Kernel policy, the impl address will be the contract address created in that transaction. You can verify it in your wallet's transaction details or by looking up the tx on a block explorer."

Wave-4 exact wording "impl address you just created" and "wallet will show that contract" CLOSED. Model paraphrased: "impl address will be the contract address created in that transaction" + "verify it in your wallet's transaction details" + "looking up the tx on a block explorer". None hit the regex.

Fix: broaden regex with `\bimpl\s+address\s+will\s+be\b`, `\bcontract\s+address\s+created\s+in\s+that\s+transaction\b`, `\bverify\s+it\s+in\s+your\s+wallet'?s?\s+transaction\s+details\b`, `\blook(?:ing)?\s+up\s+the\s+tx\s+on\s+a\s+block\s+explorer\b`. Better: refuse any freeform mentioning `(?:zerodev\s+kernel\s+policy|kernel\s+policy|session\s+key|aa\s+module|EIP-?7702)` until P0-I-02 lands.

### NEW-I-01 card↔narrative divergence — MUTATED
I02 t3: card `total_usd:"$1,000"`, `blended_apy:"~5.8%"`; narrative "$100 daily allocation", "weighted blended APY ~4.66%". 10× drift on total, 5× drift on per-row.

## NEW wave-5 (2)

### NEW-I-07 (P0) — Sanitizer `card_ids` short-circuit lets keeper recommendation leak
I02 t3 emits two cards → `card_ids:["d019db6f-…","280f8e0f-…"]` non-empty → guard returns text unchanged → "Enable a keeper-based trigger (e.g., Gelato or Sentinel's autonomous module)" reaches user. Research card does NOT back third-party-keeper claims.
Fix: split sanitizer into two passes — (1) tx-state-only patterns gated by `card_ids` (current behavior), (2) imperative-UI + named-keeper patterns ungated. OR scan only `## Next steps` / final paragraph regardless of `card_ids`.

### NEW-I-08 (P1) — Chain-label drift persists and worsens
I02 t3 allocation rows: src row 3 `chain:"scroll"` → alloc `chain:"mainnet"` (different chain); src row 4 `ethereum` → alloc `eth`; src row 5 `optimism` → alloc `op`. Three different chain spellings for same value.

## Verdict
Wave-5 commit is narrow regex-string-match-only. Caught literal wave-4 NEW-I-04 wording but model paraphrased around it on the same prompt. Zero impact on the 3 wave-4 P0s (parser-grammar / composer root causes).

Net P0: 3 STILL + 1 MUTATED + 1 NEW = **5 open P0s** in cat I after wave-5.
Net P1: 5 open P1s.
