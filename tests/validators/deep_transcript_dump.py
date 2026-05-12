"""
Deep-inspection harness — runs every scenario from strict_validator_v2.build_corpus()
against staging and writes a per-scenario transcript file containing:

- Prompt
- Wallet kind
- Expected card_types
- Final assistant text
- Every card payload (pretty JSON)
- Every SSE frame summary (event+keys, no value dump)
- Post-sign hint events if any
- URL liveness probe result if scenario has url_keywords

The file is written as Markdown so a human can read each transcript end-to-end
and detect logical/UX/copy/calldata/URL/post-sign issues that mechanical
assertions miss.

Output: /tmp/v2-deep/<idx>_<scenario_name>.md
        /tmp/v2-deep/_index.md (one line per scenario with verdict slot)
"""

from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent))
from strict_validator_v2 import (  # noqa: E402
    BASE,
    TIMEOUT,
    Scenario,
    build_corpus,
    collect_cards,
    final_text,
    stream,
    check_url_live,
)

OUT_DIR = Path("/tmp/v2-deep")


def render(scenario: Scenario, idx: int, frames, cards, text, url_probe: list[str]) -> str:
    lines: list[str] = []
    lines.append(f"# Scenario {idx:03d} — {scenario.name}")
    lines.append("")
    lines.append(f"**Wallet:** {scenario.wallet}")
    lines.append(f"**Prompt:** `{scenario.prompt}`")
    lines.append("")
    lines.append("**Scenario contract:**")
    lines.append(
        "- require_card_types: " + (", ".join(sorted(scenario.require_card_types)) or "—")
    )
    lines.append(
        "- forbid_card_types: " + (", ".join(sorted(scenario.forbid_card_types)) or "—")
    )
    if scenario.require_text:
        lines.append("- require_text: " + " | ".join(scenario.require_text))
    if scenario.forbid_text:
        lines.append("- forbid_text: " + " | ".join(scenario.forbid_text))
    if scenario.expected_protocol:
        lines.append(f"- expected_protocol: {scenario.expected_protocol}")
    if scenario.min_step_count:
        lines.append(f"- min_step_count: {scenario.min_step_count}")
    if scenario.url_keywords:
        lines.append("- url_keywords: " + ", ".join(scenario.url_keywords))
    if scenario.expected_amount:
        lines.append(f"- expected_amount: {scenario.expected_amount}")
    lines.append("")
    lines.append("## Final assistant text")
    lines.append("```")
    lines.append(text.strip()[:4000] or "(no text)")
    lines.append("```")
    lines.append("")
    lines.append(f"## Cards emitted ({len(cards)})")
    for i, c in enumerate(cards):
        lines.append(f"### card[{i}] — `{c.get('card_type', '?')}`")
        lines.append("```json")
        try:
            lines.append(json.dumps(c, indent=2, default=str)[:6000])
        except Exception as exc:
            lines.append(f"(serialize failed: {exc})")
        lines.append("```")
        lines.append("")
    lines.append("## SSE frame summary")
    by_event: dict[str, int] = {}
    for fr in frames:
        ev = fr.event or "?"
        by_event[ev] = by_event.get(ev, 0) + 1
    for ev, n in sorted(by_event.items()):
        lines.append(f"- `{ev}` × {n}")
    lines.append("")
    if url_probe:
        lines.append("## URL liveness")
        for line in url_probe:
            lines.append(f"- {line}")
        lines.append("")
    return "\n".join(lines)


async def run_one(
    session: aiohttp.ClientSession, idx: int, sc: Scenario
) -> tuple[str, list[str]]:
    """Returns (out_path, url_probe_lines) for index entry."""
    convo_id = f"deep-{idx}-{sc.name[:20]}"
    payload = {
        "message": sc.prompt,
        "conversation_id": convo_id,
        "wallet": {"kind": sc.wallet, "address": "0x" + ("a" * 40) if sc.wallet == "evm" else "11111111111111111111111111111111"},
    }
    try:
        frames = await stream(session, payload)
    except Exception as exc:
        frames = []
        text = f"(stream exception: {exc})"
        cards: list[dict] = []
    else:
        cards = collect_cards(frames)
        text = final_text(frames)

    url_probe: list[str] = []
    if sc.url_keywords:
        for c in cards:
            payload_card = c.get("payload") or c
            url = payload_card.get("url") or ""
            if url:
                errs = await check_url_live(url, sc.url_keywords)
                url_probe.append(f"{url} → " + ("OK" if not errs else " ; ".join(errs)))

    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in sc.name)[:60]
    out = OUT_DIR / f"{idx:03d}_{safe}.md"
    out.write_text(render(sc, idx, frames, cards, text, url_probe))
    return str(out), url_probe


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scenarios = build_corpus()
    print(f"Deep dump running {len(scenarios)} scenarios against {BASE} → {OUT_DIR}", flush=True)
    index_lines = ["# Deep transcript index", ""]
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        for i, sc in enumerate(scenarios):
            try:
                path, _ = await run_one(session, i, sc)
                print(f"  {i:03d} {sc.name} → {path}", flush=True)
                index_lines.append(f"- [{i:03d} {sc.name}](./{Path(path).name})")
            except Exception as exc:
                print(f"  {i:03d} {sc.name} → ERROR {exc}", flush=True)
                index_lines.append(f"- {i:03d} {sc.name} → ERROR {exc}")
    (OUT_DIR / "_index.md").write_text("\n".join(index_lines))
    print(f"\nIndex: {OUT_DIR / '_index.md'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
