"""Closed-bug regression sweep.

Reads the canonical-leak probes from `post_deploy_smoke.py` (which already
encodes the "must NOT contain" patterns per bug) and scans every SSE
capture in a wave directory for any pattern reappearing.

Prevents silent regression — wave-6 marked JLP composition CLOSED, wave-7
re-emitted; wave-3 drain-guard CLOSED for ERC4626/WTG3 but wave-5
discovered Aave V3 ERC20 path unguarded. Without this sweep we discover
each regression manually, costing 60-90 min per wave.

Usage:
  python scripts/validation/regression_sweep.py docs/matrix-runs/passA-wave8
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from scripts.validation.post_deploy_smoke import PROBES


def scan_wave(wave_dir: Path) -> dict[str, list[tuple[str, str]]]:
    """For each probe, return the list of (file, matched_pattern) for any
    capture where a `must_not_contain` pattern appears.

    Wave 12 — strip `user_message`/`cross_chain_message` segments before
    scanning so we don't false-match on the literal matrix prompt that
    the harness sent. The sweep only sees the MODEL's output (thoughts +
    cards + final.content).
    """
    import re
    user_msg_re = re.compile(r'"user_message":"(?:[^"\\]|\\.)*"')
    cross_msg_re = re.compile(r'"cross_chain_message":"(?:[^"\\]|\\.)*"')
    results: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for turn_file in wave_dir.rglob("turn_*.txt"):
        try:
            body = turn_file.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):
            continue
        body = user_msg_re.sub('"user_message":""', body)
        body = cross_msg_re.sub('"cross_chain_message":""', body)
        body_lower = body.lower()
        rel_path = str(turn_file.relative_to(wave_dir))
        for probe in PROBES:
            # Skip turns outside the probe's scope (default: any turn).
            if probe.regression_turn_scope:
                if not any(rel_path.endswith(suffix) for suffix in probe.regression_turn_scope):
                    continue
            for forbidden in probe.must_not_contain:
                if forbidden.lower() in body_lower:
                    results[probe.id].append((rel_path, forbidden))
    return results


def render_markdown(wave_dir: Path, results: dict) -> str:
    md = [f"# Closed-bug regression sweep — {wave_dir.name}", ""]
    if not results:
        md.append("**ALL CLEAR.** No closed-bug pattern reappeared in any capture.")
        md.append("")
        return "\n".join(md)

    md.append(f"**{len(results)} closed bugs reappeared.** Details below.")
    md.append("")
    md.append("## Reappearing patterns")
    md.append("")
    md.append("| Probe ID | Bug ref | Files affected | Sample file:pattern |")
    md.append("|----------|---------|----------------|---------------------|")
    probe_lookup = {p.id: p for p in PROBES}
    for probe_id, hits in sorted(results.items(), key=lambda kv: -len(kv[1])):
        probe = probe_lookup[probe_id]
        files = {f for f, _p in hits}
        sample_file, sample_pat = hits[0]
        md.append(
            f"| {probe_id} | {probe.bug_ref} | {len(files)} | "
            f"`{sample_file}`: `{sample_pat[:60]}` |"
        )
    md.append("")
    md.append("## Per-probe inventory")
    md.append("")
    for probe_id, hits in sorted(results.items(), key=lambda kv: -len(kv[1])):
        probe = probe_lookup[probe_id]
        md.append(f"### {probe_id} — {probe.bug_ref}")
        md.append(f"Prompt: `{probe.message}`")
        md.append(f"Hits: {len(hits)} across {len({f for f, _ in hits})} files")
        for f, p in hits[:10]:
            md.append(f"- `{f}` → `{p[:80]}`")
        if len(hits) > 10:
            md.append(f"- ... and {len(hits) - 10} more")
        md.append("")
    return "\n".join(md)


def main():
    if len(sys.argv) != 2:
        print("usage: regression_sweep.py <wave_dir>", file=sys.stderr)
        sys.exit(2)
    wave_dir = Path(sys.argv[1])
    if not wave_dir.exists():
        print(f"not found: {wave_dir}", file=sys.stderr)
        sys.exit(1)
    results = scan_wave(wave_dir)
    md = render_markdown(wave_dir, results)
    out_path = wave_dir / "regression-sweep.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"wrote {out_path}")
    if results:
        print(f"  REGRESSIONS: {len(results)} closed bugs reappeared")
        sys.exit(1)
    else:
        print("  ALL CLEAR — no closed-bug pattern reappeared")


if __name__ == "__main__":
    main()
