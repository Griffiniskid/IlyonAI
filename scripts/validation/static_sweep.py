"""Mechanical static sweep of matrix SSE captures for known anti-patterns.

Runs in <60s vs 5-15 min × 9 reviewers. Replaces ~50% of LLM reviewer time
so reviewers can focus on NEW shapes only.

Surfaces every wave-N capture file matching any of:
  - Sanitizer regex patterns from src/agent/simple_runtime.py
    (_FREEFORM_TX_STATE_HALLUCINATION_RE, _FREEFORM_IMPERATIVE_UI_HALLUCINATION_RE,
     _BODY_SCRATCHPAD_STRONG_RE, _UNBACKED_*_RE)
  - Anti-pattern catalogue extracted from BUG_LEDGER.md CLOSED entries
  - Structural invariants from spec §11 D.1-D.8

Output:
  docs/matrix-runs/<wave>/static-sweep.md
    - per-category markdown table of pattern hits
    - top-10 highest-leverage patterns (most files affected)
    - per-file inventory of which patterns triggered

Usage:
  python scripts/validation/static_sweep.py docs/matrix-runs/passA-wave8
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


# ─── Catalogue of anti-patterns from BUG_LEDGER + sanitizer set ───────────
# Each entry: (id, severity, regex, description)
# Severity: P0 = financial-loss / safety bypass, P1 = wrong answer, P2 = cosmetic.
PATTERNS: list[tuple[str, str, re.Pattern, str]] = [
    # Tx-hash hallucinations
    ("AP-001", "P0",
     re.compile(r"\b0x[0-9a-fA-F]{3,}…[0-9a-fA-F]{2,}\b"),
     "Bare tx-hash-with-ellipsis (H02 t2 form)"),
    ("AP-002", "P0",
     re.compile(r"\b(?:current\s+)?tx\s*[:—–-]\s*`?0x[0-9a-fA-F]{4,}",
                re.IGNORECASE),
     "'Current tx: 0x…' without backticks"),
    ("AP-003", "P0",
     re.compile(r"\btransaction\s+(?:for\s+[\w$.,\s]{1,80}?\s+)?(?:is|are)\s+(?:already\s+)?(?:ready|set|in\s+place)\b",
                re.IGNORECASE),
     "'Transaction is ready' fabrication (A15)"),
    ("AP-004", "P0",
     re.compile(r"(?:has|have)\s+been\s+(?:executed|submitted|broadcast(?:ed)?|confirmed|delivered|sent)\b",
                re.IGNORECASE),
     "'has been executed/submitted/...' tense (F10, E10)"),
    ("AP-005", "P0",
     re.compile(r"track\s+(?:its|the)\s+progress\s+on\s+(?:etherscan|basescan|arbiscan|optimistic\s+etherscan|polygonscan|bscscan|snowtrace|solscan|explorer\.solana)\b",
                re.IGNORECASE),
     "'track its progress on BaseScan' without URL (E10)"),

    # Structured headers (markdown-pretending-to-be-card)
    ("AP-010", "P0",
     re.compile(r"\*\*[A-Z][A-Za-z0-9 ./-]{1,40}\s*·\s*(?:Supply|Stake|Swap|Bridge|Withdraw|Deposit|Borrow|Repay|Mint|Burn|Wrap|Unwrap|Approve|Claim|Compound|Migrate|Refinance|Loop|Exit|Remove|Unstake|Restake|Top[-\s]?up)\s*\*\*",
                re.IGNORECASE),
     "'**Protocol · Verb**' freeform header (G08 T2)"),
    ("AP-011", "P0",
     re.compile(r"\*\*\s*Execution\s+Plan\s*[–—-]\s*(?:Supply|Stake|Swap|Bridge|Withdraw|Deposit|Borrow|Repay|Mint|Claim|Compound|Migrate|Exit|Remove|Unstake|Buy|Sell)\b",
                re.IGNORECASE),
     "'**Execution Plan – Supply USDC**' en-dash header (G04 T4)"),
    ("AP-012", "P0",
     re.compile(r"\bswap\s+leg\*{0,2}\s*[-–—:]\s*\*{0,2}\s*swap\s+[\d.]+\s+[A-Z]{2,8}",
                re.IGNORECASE),
     "'**Swap leg** – Swap X TOKEN' fabrication (H02 t2)"),
    ("AP-013", "P0",
     re.compile(r"\bsplit\s+confirmed\*{0,2}\s*[-–—:]",
                re.IGNORECASE),
     "'**Split confirmed** –' fabrication (H02 t3)"),

    # State-machine narration
    ("AP-020", "P0",
     re.compile(r"(?:execution\s+plan|plan)\s+will\s+(?:move|transition|go|advance|flip)\s+from\s+[`\"']?(?:draft|pending|prompted|building)[`\"']?\s+to\s+[`\"']?(?:executed|signed|complete|ready|broadcast(?:ed)?)[`\"']?",
                re.IGNORECASE),
     "'Execution Plan will move from draft to executed' (E01)"),
    ("AP-021", "P0",
     re.compile(r"\bthe\s+bridge\s+will\s+proceed\b",
                re.IGNORECASE),
     "'the bridge will proceed' state-machine narration (E01)"),

    # I'll generate/create a plan
    ("AP-030", "P0",
     re.compile(r"i'?ll\s+(?:generate|produce|build|create)\s+(?:\w+(?:\.\w+)*\s+){0,5}(?:plan|bridge|transaction|swap)\b",
                re.IGNORECASE),
     "'I'll generate the plan' promise (E03)"),
    ("AP-031", "P0",
     re.compile(r"i\s+can\s+(?:generate|produce|build|create)\s+(?:\w+(?:\.\w+)*\s+){0,5}(?:plan|bridge|transaction|swap)\b",
                re.IGNORECASE),
     "'I can generate a signable plan' (E03)"),
    ("AP-032", "P0",
     re.compile(r"i'?ll\s+create\s+a\s+ready[-\s]?to[-\s]?sign\s+plan",
                re.IGNORECASE),
     "'I'll create a ready-to-sign plan' (E08)"),

    # Bare bridge claim
    ("AP-040", "P0",
     re.compile(r"\b(?:debridge|debridge[-\s]dln|li\.?fi|across|hop|stargate|socket|bungee|squid|wormhole)\s+(?:dln\s+)?is\s+the\s+bridge\s+used\s+to\b",
                re.IGNORECASE),
     "'X is the bridge used to move...' bare route claim (E04)"),
    ("AP-041", "P0",
     re.compile(r"\bbridge\s+route\s*[:—–-]\s*[A-Z]",
                re.IGNORECASE),
     "'Bridge route: X → Y → Z' invented (E13)"),

    # Slippage/fee fabrications — tightened wave-12 to require the
    # specific fabrication phrasing ("slippage band", "bridge fee",
    # "protocol fee") with a leading verb context. The wave-7/8 regex
    # over-fired on legitimate `slippage_cap` card field + "gas
    # estimates and 0.5% slippage cap" descriptive prose.
    ("AP-050", "P0",
     re.compile(r"\b(?:slippage\s+band|bridge\s+fee\s+(?:is|are|of|estimate)|protocol\s+fee\s+(?:is|are|of|≈|~|approximately))\s*[~≈]?\s*\d+(?:\.\d+)?\s*[%]",
                re.IGNORECASE),
     "'slippage band 0.5%' / 'protocol fee is 0.10%' fabrication (E02, E05) — tightened wave-12 to exclude legitimate slippage_cap"),
    ("AP-051", "P0",
     re.compile(r"\bestimated\s+bridge\s+fee\b",
                re.IGNORECASE),
     "'Estimated bridge fee' fabrication (H04 t2)"),
    ("AP-052", "P0",
     re.compile(r"\btypical\s+execution\s+time\s*[:—–-]\s*\d",
                re.IGNORECASE),
     "'Typical execution time: 2-5 minutes' fabrication (H04 t2)"),

    # Wallet-state assertions
    ("AP-060", "P0",
     re.compile(r"\byou\s+(?:already\s+)?hold\s+[\d.]+\s+[A-Z]{2,8}\s*[,]\s*[\d.]+\s+[A-Z]{2,8}",
                re.IGNORECASE),
     "'You already hold N USDC, N USDT' fabricated balance (H07 t2)"),
    ("AP-061", "P0",
     re.compile(r"\bdust\s+mix\s+confirmed\b",
                re.IGNORECASE),
     "'Dust mix confirmed' fabricated state (H07 t3)"),
    ("AP-062", "P0",
     re.compile(r"\bno\s+residual\s+dust(?:\s+remains)?\b",
                re.IGNORECASE),
     "'no residual dust remains' fabricated post-exec state (H07 t3)"),
    ("AP-063", "P0",
     re.compile(r"\btop[-\s]?up\s+(?:confirmed|complete|done|completed|successful)\b",
                re.IGNORECASE),
     "'Top-up confirmed' fabricated state (H09)"),

    # Fabricated quotes
    ("AP-070", "P0",
     re.compile(r"\bswap(?:ping)?\s+[\d.]+\s+[A-Z]{2,8}\s+to\s+[A-Z]{2,8}\s+on\s+[A-Z][a-z]+\s+(?:yields|has\s+been|delivers|will\s+deliver|gives?\s+you\s+(?:about|roughly|approximately|~)|nets|returns|for\s+(?:about|roughly|approximately|~))\b",
                re.IGNORECASE),
     "'Swapping X to Y on Z yields/gives you N ETH' fabricated quote (F10)"),

    # JLP composition
    ("AP-080", "P0",
     re.compile(r"\b(?:SOL|ETH|USDC|USDT|WBTC|DAI|MATIC|AVAX|BNB)\s*[≈~]\s*\d+\s*%(?:[\s,\n-]+(?:SOL|ETH|USDC|USDT|WBTC|DAI|MATIC|AVAX|BNB)\s*[≈~]\s*\d+\s*%){1,}",
                re.IGNORECASE),
     "JLP composition table 'SOL ≈ 45%, ETH ≈ 20%' fabricated (H05 t2)"),

    # Currency-token cap fabrications
    ("AP-090", "P0",
     re.compile(r"\$\d+(?:[.,]\d+)?\s*(?:daily|per\s+day|/day|weekly|per\s+week|/week|monthly|per\s+month|/month)\s+(?:cap|budget|allowance|limit)",
                re.IGNORECASE),
     "'$500 daily cap' invented numeric cap (I01)"),
    ("AP-091", "P0",
     re.compile(r"\$\d+(?:[.,]\d+)?\s+(?:USDC|USDT|DAI|ETH|SOL|WETH|WBTC|MATIC|AVAX|BNB|USD)\s+(?:per\s+day|/day|daily|each\s+day|spend\s+cap|daily\s+cap|spend\s+limit)",
                re.IGNORECASE),
     "'$100 USDC per day' currency-token cap paraphrase (I02 t2)"),
    ("AP-092", "P0",
     re.compile(r"\*\*\s*daily\s+spend\s+cap\s*:?\s*\*\*\s*\$\d+(?:[.,]\d+)?\s+(?:USDC|USDT|DAI|ETH|SOL|WETH|WBTC|MATIC|AVAX|BNB|USD)",
                re.IGNORECASE),
     "'**Daily spend cap:** $100 USDC' markdown bold (I02 t3)"),

    # Policy Signed narrative
    ("AP-100", "P0",
     re.compile(r"\*\*\s*policy\s+signed\b",
                re.IGNORECASE),
     "'**Policy Signed**' fabricated signature state (I02 t3)"),
    ("AP-101", "P0",
     re.compile(r"\bby\s+signing\s+this\s+policy,?\s+you\s+authoriz(?:e|ed)",
                re.IGNORECASE),
     "'By signing this policy, you authorize' pseudo-legal (I02 t3)"),

    # Imperative dApp UI
    ("AP-110", "P0",
     re.compile(r"\bopen\s+(?:the\s+|your\s+)?(?:nexus\s+dapp|phantom\s+wallet|metamask|rabby|backpack|coinbase\s+wallet|trust\s+wallet|solflare|safe\s+wallet|ledger\s+live|argent|zerodev\s+app|biconomy\s+app|kernel\s+app)\b",
                re.IGNORECASE),
     "'Open the Nexus dApp' imperative UI flow (I01)"),
    ("AP-111", "P0",
     re.compile(r"\b(?:gelato|keep3r|chainlink\s+automation|defender|sentinel'?s?\s+autonomous\s+module|keeper[-\s]based\s+trigger|openzeppelin\s+defender|tenderly\s+actions)\b",
                re.IGNORECASE),
     "Named third-party keeper recommendation (I02 t3)"),

    # CoT scratchpad lead-strings
    ("AP-120", "P1",
     re.compile(r"^\s*(?:we\s+(?:need|have|must|should|will|can)|let'?s\s+(?:think|compute|build|produce|consider))",
                re.IGNORECASE | re.MULTILINE),
     "First-person planning lead (We need to / Let's compute)"),
    ("AP-121", "P1",
     re.compile(r"^\s*(?:plug\s+\w+\s*=|compute(?:\s+\w+){0,3}\s*[:.]|sum(?:\s+\w+){0,2}\s*[:=]|default\s+to\s+(?:even|equal|risk))",
                re.IGNORECASE | re.MULTILINE),
     "Strong CoT scratchpad ('Plug w=', 'Compute amounts:', 'Sum:')"),
    ("AP-122", "P1",
     re.compile(r"\d+(?:\.\d+)?\s*[*x×]\s*\d+(?:\.\d+)?\s*=\s*\d+(?:\.\d+)?",
                re.IGNORECASE),
     "Arithmetic equality leak (14.284*6=85.704)"),

    # Empty content
    ("AP-130", "P0",
     re.compile(r'"content":""[\s,]*"card_ids":\s*\[\]',
                re.IGNORECASE),
     "Empty final content with empty card_ids (G03 T4, I03 T3, I05)"),

    # Bare 40-hex address in freeform body
    ("AP-140", "P1",
     re.compile(r"\b0x[0-9a-fA-F]{40}\b"),
     "40-hex address (verify if backed by card or freeform)"),

    # USD overflow
    ("AP-150", "P0",
     re.compile(r'"(?:usd_value|usd_total|total_usd)"\s*:\s*[\d.]+e\+?[2-9]\d',
                re.IGNORECASE),
     "USD value overflow (≥$1e20) — F02 t3 spark token"),

    # Pendle schedule fabrications
    ("AP-160", "P0",
     re.compile(r"\b(?:epochs?|windows?|cooldowns?|unbonding\s+periods?)\s+(?:open|opens?|start|starts?|run|runs?|close|closes?|begin|begins?)\s+(?:every|on|at|next|each)\b",
                re.IGNORECASE),
     "'Epochs open every Thursday' fabricated schedule (F04 t2)"),

    # ExecutionPlanV3 + transaction=null + status=ready
    ("AP-170", "P0",
     re.compile(r'"status"\s*:\s*"ready"[\s\S]{0,200}?"transaction"\s*:\s*null',
                re.IGNORECASE),
     "Card 'status:ready' with 'transaction:null' (composed-plan E07 t4, H06)"),

    # requires_signature:false with non-zero tx_count
    ("AP-180", "P1",
     re.compile(r'"requires_signature"\s*:\s*false[\s\S]{0,200}?"tx_count"\s*:\s*[1-9]',
                re.IGNORECASE),
     "'requires_signature:false' while 'tx_count >=1' (B series, D10/D11 t1)"),

    # backticked Solidity verbs
    ("AP-190", "P0",
     re.compile(r"`(?:removeLiquidity|mint|swap|supply|approve|deposit|withdraw|exitPool)\([^`]*\)`",
                re.IGNORECASE),
     "Backticked Solidity call signatures (H14 t3/t4)"),

    # Confirmation-prompt without card
    ("AP-200", "P0",
     re.compile(r"(?:supply|stake|swap|bridge|deposit|withdraw|claim|borrow|repay)\s+[\d.,]+\s+[A-Z]{2,8}[\s\S]{0,160}?\b(?:confirm\s+(?:if\s+you'?d?\s+like\s+to\s+)?proceed|let\s+me\s+know\s+(?:if\s+)?you'?d?\s+like\s+to\s+proceed|would\s+you\s+like\s+(?:to\s+)?proceed|ready\s+to\s+(?:supply|stake|swap|bridge|deposit|withdraw))\b",
                re.IGNORECASE),
     "'Supply 100 USDC. Confirm if you'd like to proceed' precursor (F02 t4)"),
]


def scan_file(path: Path) -> dict:
    """Return {pattern_id: [hit_snippets]} for any pattern matching the file."""
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return {}
    hits: dict[str, list[str]] = {}
    for pid, _sev, regex, _desc in PATTERNS:
        matches = regex.findall(body)
        if matches:
            # Take first 3 unique matches as evidence
            sample = []
            seen = set()
            for m in matches:
                m_str = m if isinstance(m, str) else " ".join(m)
                m_str = m_str[:140]
                if m_str not in seen:
                    sample.append(m_str)
                    seen.add(m_str)
                if len(sample) >= 3:
                    break
            hits[pid] = sample
    return hits


def scan_wave(wave_dir: Path) -> dict:
    """Walk every turn_*.txt in wave_dir. Return {file_path: {pattern_id: hits}}."""
    results: dict[str, dict[str, list[str]]] = {}
    for turn_file in wave_dir.rglob("turn_*.txt"):
        hits = scan_file(turn_file)
        if hits:
            rel = turn_file.relative_to(wave_dir)
            results[str(rel)] = hits
    return results


def render_markdown(wave_dir: Path, results: dict) -> str:
    """Render results as a single markdown report."""
    pattern_meta = {pid: (sev, desc) for pid, sev, _re, desc in PATTERNS}
    # Tally hits per pattern across all files
    hit_count = Counter()
    file_count_per_pattern: dict[str, set[str]] = defaultdict(set)
    per_cat_pattern_files: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for file_path, file_hits in results.items():
        category = file_path[0] if file_path else "?"
        for pid, hits in file_hits.items():
            hit_count[pid] += len(hits)
            file_count_per_pattern[pid].add(file_path)
            per_cat_pattern_files[category][pid].add(file_path)

    md = [f"# Static sweep — {wave_dir.name}", ""]
    md.append(f"Scanned: {sum(1 for _ in wave_dir.rglob('turn_*.txt'))} turn files")
    md.append(f"Files with ≥1 hit: {len(results)}")
    md.append(f"Total pattern hits: {sum(hit_count.values())}")
    md.append("")

    # Top patterns by file count
    md.append("## Top patterns (by file count)")
    md.append("")
    md.append("| ID | Sev | Files | Hits | Description |")
    md.append("|----|-----|-------|------|-------------|")
    sorted_patterns = sorted(
        file_count_per_pattern.items(),
        key=lambda kv: (-len(kv[1]), -hit_count[kv[0]]),
    )
    for pid, files in sorted_patterns:
        sev, desc = pattern_meta[pid]
        md.append(f"| {pid} | {sev} | {len(files)} | {hit_count[pid]} | {desc} |")
    md.append("")

    # Per-category breakdown
    md.append("## Per-category breakdown")
    md.append("")
    md.append("| Cat | Total files w/ hits | Top pattern (files) |")
    md.append("|-----|---------------------|---------------------|")
    for cat in sorted(per_cat_pattern_files.keys()):
        cat_files = set()
        for files in per_cat_pattern_files[cat].values():
            cat_files |= files
        top_pid = max(per_cat_pattern_files[cat], key=lambda p: len(per_cat_pattern_files[cat][p]))
        top_n = len(per_cat_pattern_files[cat][top_pid])
        md.append(f"| {cat} | {len(cat_files)} | {top_pid} ({top_n} files) |")
    md.append("")

    # Per-file inventory (top 30 most-affected files)
    md.append("## Top-30 most-affected files")
    md.append("")
    file_total_hits = {fp: sum(len(h) for h in fh.values()) for fp, fh in results.items()}
    for fp in sorted(file_total_hits, key=lambda f: -file_total_hits[f])[:30]:
        pids = sorted(results[fp].keys())
        md.append(f"- `{fp}` — {file_total_hits[fp]} hits — {', '.join(pids)}")
    md.append("")

    # Detailed pattern hits for top-5 highest-impact patterns
    md.append("## Sample evidence (top-5 patterns)")
    md.append("")
    for pid, _files in sorted_patterns[:5]:
        sev, desc = pattern_meta[pid]
        md.append(f"### {pid} [{sev}] — {desc}")
        md.append("")
        sample_count = 0
        for fp, fh in results.items():
            if pid not in fh:
                continue
            md.append(f"- `{fp}`: `{fh[pid][0][:120]}`")
            sample_count += 1
            if sample_count >= 5:
                break
        md.append("")

    return "\n".join(md)


def main():
    if len(sys.argv) != 2:
        print("usage: static_sweep.py <wave_dir>", file=sys.stderr)
        sys.exit(2)
    wave_dir = Path(sys.argv[1])
    if not wave_dir.exists():
        print(f"not found: {wave_dir}", file=sys.stderr)
        sys.exit(1)
    results = scan_wave(wave_dir)
    md = render_markdown(wave_dir, results)
    out_path = wave_dir / "static-sweep.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"wrote {out_path}: {len(results)} files with hits, {sum(sum(len(h) for h in fh.values()) for fh in results.values())} total")
    # Also dump raw json for programmatic comparison wave-over-wave
    json_path = wave_dir / "static-sweep.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"wrote {json_path}")


if __name__ == "__main__":
    main()
