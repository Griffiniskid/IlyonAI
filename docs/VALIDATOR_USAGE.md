# Validation Protocol — Self-Analysis Only

> **HARD RULE.** Mechanical pass/fail validation is **forbidden** from this
> point forward. The agent (Claude / human reviewer) **must read every
> conversation transcript end-to-end** and detect logical, copy, UX,
> calldata, URL, and post-sign behavior issues by inspection — never by
> assert-only scripts that emit a single PASS/FAIL.
>
> The validator scripts in this repo are **transcript-producers**, not
> verdict-producers. They send the real requests, dump the full SSE
> output per scenario, and let a thinking reviewer read every transcript
> and form a judgment.

## Why

Every prior incident — Raydium AMM 1-step prep-swap, `?ammId=` redirect
to `/swap`, post-sign `search_defi_opportunities` fire, `unhashable
type: 'slice'` exception, finalize-on-protocol copy that misled the
tester — was missed by mechanical assertions but obvious in a 15-second
human read of the transcript. The gap is judgment, not coverage. Adding
more assertions has diminishing returns; adding a reviewer who reads
every transcript has none.

## Required workflow

1. **Run the dump harness** against the target environment:

   ```bash
   ILYON_BASE=https://staging.ilyonai.com \
       python3 -uB tests/validators/deep_transcript_dump.py
   ```

   Output: `/tmp/v2-deep/<idx>_<scenario>.md` per scenario, plus
   `_index.md`. Each file contains the **prompt, every SSE frame
   summary, every card payload, the final assistant text, and a URL
   liveness probe**. No verdict line.

2. **Read every transcript.** Not a sample. Not a regex pre-scan. The
   reviewer opens each file and asks:

   - Does the final text contain a leaked exception, a redirect phrase,
     a wrong protocol name, a placeholder, or `undefined` / `NaN`?
   - Does the card payload have non-null `tx.data` / `tx.serialized` if
     it claims to be ready to sign?
   - Do the amounts in the summary match what the user asked for?
   - Does the URL in the card actually open the right pool when
     clicked (the dump probes liveness — read the probe result)?
   - Is the step count appropriate for the protocol (Raydium AMM zap =
     ≥3 steps, Aave supply = 2 steps, etc.)?
   - Is the post-sign behavior sane (no `search_defi_opportunities`
     re-fire, no `confirm the receipt` user-message injection)?
   - Does the wallet/chain match (Solana request on EVM wallet must
     emit `wallet_chain_mismatch` blocker)?
   - Is the copy honest about what the chat can sign vs what the user
     must finalize on the protocol app?

3. **Catalog findings.** Each bug → an entry in
   `/tmp/v2-deep/_findings.md` with: scenario file, problem in 1–2
   sentences, severity, owning module.

4. **Fix every finding.** Push to `main`. If staging branch lags,
   `git push origin main:staging` to ship.

5. **Re-deploy + re-run the dump.** Repeat the read-every-transcript
   loop. Stop only when the reviewer reads all transcripts and finds
   nothing actionable.

6. **Update this doc** when new bug classes surface in production that
   the dump didn't already expose. Add an item under "Patterns the
   reviewer should specifically look for" below.

## Patterns the reviewer should specifically look for

| Pattern | What it looks like in the transcript |
|---|---|
| Leaked exception | "I wasn't able to fetch that data right now. \<python error\>" in final text |
| Redirect-phrase copy | "finalise the LP add inside the …", "currently finalizes on …", "currently unavailable" |
| Old Raydium URL | `raydium.io/liquidity/?ammId=` (must be `/liquidity/increase/?pool_id=`) |
| Zap underfilled | Raydium AMM / Orca Whirlpool with `steps` count == 1 (should be ≥3 for a real zap) |
| Empty cards | `Cards emitted (0)` block — tool failed silently |
| Missing `range_block` | V3 EVM card with no `range_block` payload — slider can't render |
| Wrong protocol | Card title says `uniswap-v3` when the user asked for `pancakeswap-v3` |
| Float drift | `0.111111` / `0.0999999` / `1.23e-08` in any user-visible string |
| Atomic-unit leak | `100000000000000000` instead of `0.1 ETH` |
| Post-sign fire | SSE stream contains `confirm the receipt` injected as a `user` message after step_signed |
| Wallet/chain mismatch | Solana prompt + EVM wallet → no `wallet_chain_mismatch` blocker visible |
| Stale deadline | `tx.deadline` ≤ current time or > 24h ahead |
| Zero address `tx.to` | `tx.to: "0x0000…0000"` on any EVM step |
| Solana tx oversize | `tx.serialized` decodes to >1232 bytes without ALT hint |

## Transcript producer scripts

| Path | What it produces |
|---|---|
| `tests/validators/deep_transcript_dump.py` | Per-scenario Markdown transcript files at `/tmp/v2-deep/`. **Primary.** |
| `scripts/anvil_fork_sim.py` | Funded Anvil fork — broadcasts a V3 mint plan + dumps receipts. Use to verify a calldata path actually lands on chain. |
| `scripts/playwright_browser_smoke.py` | Headless Chromium navigates the chat, dumps DOM + console errors per scenario. Use to verify the wallet popup actually shows when the card asserts "ready". |
| `tests/calldata_decoder.py` | Library helper — decode EVM calldata to human selector + args for inspection. |

These scripts **emit data, not verdicts**. The reviewer reads the
output. No script in this repo may print "PASS" or "FAIL" as its
primary signal again.

## Updating after each browser bug

When the human tester finds a bug in the browser that the dump didn't
expose:

1. Reproduce the bug by running the dump on the same scenario.
2. If the transcript already shows the bug → the reviewer missed it.
   Add the failure pattern to the **Patterns** table above so the next
   reviewer scans for it.
3. If the transcript does **not** show the bug → the dump is missing a
   signal. Extend `deep_transcript_dump.py` to capture whatever frame /
   payload field the bug lives in (e.g. a post-sign re-fire that's
   only visible if the dump replays the SSE stream after a signed
   step).
4. Re-run, re-read, fix the underlying bug, commit dump-improvement +
   fix in the same PR.

This is the "tester reality bridge". Every browser-found bug becomes a
permanent capture in the dump and a permanent line in the Patterns
table — never a one-off mechanical assert.
