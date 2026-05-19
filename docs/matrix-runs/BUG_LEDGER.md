# BUG_LEDGER — IlyonAi production-readiness pursuit

Single source of truth for every bug surfaced during the V8 close-to-100% pursuit:
12-subagent re-verification audits, anti-pattern grep sweeps, and matrix passes A/B/C.

Initialized 2026-05-19 against HEAD `7b4d1f5` (after prior session's claimed-100%
was independently falsified to 88% by 6-subagent audit run on the same date).

## Schema

Each entry MUST have:
- **ID** — `BUG-NNN` monotonically increasing
- **Surfaced by** — `audit-batch-X` | `pass{A,B,C}-wave{N}/{chain_id}/turn_{N}` | `grep-{pattern}`
- **Severity** — `P0` (financial loss / safety bypass) | `P1` (wrong answer / missing card / bad blocker code) | `P2` (cosmetic / inefficiency)
- **Spec reference** — `§X.Y`, requirement ID, S{1-15}, D.{1-8}, or §13 row label
- **Root cause** — one-line technical explanation
- **Fix** — `path/to/file.py:line_no` (or multiple) + commit SHA
- **Before/after SSE quote** — for matrix-surfaced bugs only; literal substring of SSE that flips from broken → fixed

## Entries

(none yet — first will land when Wave 1 closure surfaces audit findings or Matrix Pass A fires)

---

## Coverage delta tracker

| Snapshot                       | LIVE | PARTIAL | MISSING | SKIP-OK |
|--------------------------------|------|---------|---------|---------|
| Prior session claim (over)     | 75   | 0       | 0       | 0       |
| 2026-05-19 audit (independent) | 58   | 9       | 0       | 8       |
| (next: post-Wave-1)            | ?    | ?       | ?       | ?       |
| (next: post-Wave-2)            | ?    | ?       | ?       | ?       |
| (next: post-Wave-3)            | ?    | ?       | ?       | ?       |
| (next: post-pass-A)            | ?    | ?       | ?       | ?       |
| Final (target)                 | 75   | 0       | 0       | 0       |
