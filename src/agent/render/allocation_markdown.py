"""allocation_markdown — single-source-of-truth markdown renderer for the
allocation card payload.

Pass A F-category hand-read (F04/t4, F05/t3, enso-12/t2) surfaced a dual-
reducer disagreement: the LLM-generated narrative rendered an allocation
table with N=items_in_search rows (e.g. 8 × $12.50), while the emitted
`allocation` card payload carried N=positions (e.g. 5 × $20). Two different
reducers operating on the same data → the user cannot reconcile what they
are signing.

This module renders the markdown allocation table directly from the
emitted `AllocationPayload` (the card payload IS the source of truth). It
must be used to REPLACE any allocation table the LLM produced — never to
augment it.

Contract
--------
- `render_allocation_table(payload)`:
    Returns a markdown allocation table (header + N rows) where N exactly
    equals `len(payload["positions"])`. Each row's $ amount, weight, APY
    and protocol come directly from the payload — never re-derived from
    raw candidates.

- `render_allocation_section(payload)`:
    Returns a full `## Allocation` markdown section: header line, table,
    then a 1-sentence blended-outcome summary. Drop-in replacement for
    the LLM's `## Allocation` block.

- `replace_allocation_table_in_narrative(narrative, payload)`:
    Surgical replacement helper. Finds any markdown table in `narrative`
    whose rows look like allocation rows (`| <int> | <protocol> ... | <int>%`
    or `| <int> | <protocol> ... | <int> |`) and substitutes the
    payload-derived table. If no such table is found, appends a fresh
    `## Allocation` section at the top so the card and prose still agree.

No dependency on `simple_runtime.py`. Helper is pure / synchronous.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


_HEADER = "| # | Protocol · Pair (chain) | Weight % | $ Amount | APY | Risk |"
_DIVIDER = "|---|---|---|---|---|---|"


# Friendly chain tone → display name (matches existing UI conventions).
_CHAIN_DISPLAY = {
    "eth": "Ethereum",
    "mainnet": "Ethereum",
    "ethereum": "Ethereum",
    "arb": "Arbitrum",
    "arbitrum": "Arbitrum",
    "op": "Optimism",
    "optimism": "Optimism",
    "polygon": "Polygon",
    "base": "Base",
    "bsc": "BSC",
    "avax": "Avalanche",
    "avalanche": "Avalanche",
    "sol": "Solana",
    "solana": "Solana",
}


def _chain_display(chain: str | None) -> str:
    if not chain:
        return "?"
    return _CHAIN_DISPLAY.get(str(chain).lower(), str(chain).capitalize())


def _coerce_positions(payload: Any) -> list[dict[str, Any]]:
    """Accept either an `AllocationPayload` model, its dict dump, or a bare
    positions list and return a list of dict-shaped positions.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, Mapping):
        candidates = payload.get("positions") or []
    else:
        # pydantic v2 model
        dump = getattr(payload, "model_dump", None)
        if callable(dump):
            data = dump()
            candidates = data.get("positions") or []
        else:
            return []
    out: list[dict[str, Any]] = []
    for p in candidates:
        if isinstance(p, Mapping):
            out.append(dict(p))
        else:
            dump = getattr(p, "model_dump", None)
            if callable(dump):
                out.append(dump())
    return out


def render_allocation_table(payload: Any) -> str:
    """Render the markdown allocation table from the card payload.

    Returns a header + divider + N rows where N == len(payload.positions).
    Returns empty string if there are no positions.
    """
    positions = _coerce_positions(payload)
    if not positions:
        return ""
    lines: list[str] = [_HEADER, _DIVIDER]
    for pos in positions:
        rank = pos.get("rank", "?")
        protocol = str(pos.get("protocol") or "?")
        asset = str(pos.get("asset") or "?")
        chain = _chain_display(pos.get("chain"))
        weight = pos.get("weight", "?")
        usd = str(pos.get("usd") or "?")
        apy = str(pos.get("apy") or "?")
        risk = str(pos.get("risk") or "?").upper()
        lines.append(
            f"| {rank} | {protocol} · {asset} ({chain}) | {weight}% | {usd} | {apy} | {risk} |"
        )
    return "\n".join(lines)


def _payload_summary_line(payload: Any) -> str:
    """One-sentence blended outcome line from payload fields (never recomputed)."""
    if isinstance(payload, Mapping):
        data = dict(payload)
    else:
        dump = getattr(payload, "model_dump", None)
        data = dump() if callable(dump) else {}
    total = data.get("total_usd") or "?"
    blended = data.get("blended_apy") or "?"
    n = len(_coerce_positions(payload))
    return (
        f"Total {total} across {n} position{'s' if n != 1 else ''} — "
        f"blended APY {blended}."
    )


def render_allocation_section(payload: Any) -> str:
    """Full `## Allocation` markdown block sourced from the card payload."""
    table = render_allocation_table(payload)
    if not table:
        return ""
    summary = _payload_summary_line(payload)
    return f"## Allocation\n{table}\n\n{summary}"


# --- Surgical narrative rewriter ------------------------------------------


# Matches contiguous markdown tables. Rows start with `|` and end with `|`.
_TABLE_BLOCK_RE = re.compile(
    r"(?:^|\n)(\|[^\n]*\|\n(?:\|[^\n]*\|\n?)+)",
    re.MULTILINE,
)

# A row is "allocation-like" when its first non-divider cell is an integer
# rank AND it has at least 4 cells AND one cell holds a percent (e.g. `25%`
# or `25` with `%` somewhere on the row) OR a `$` amount.
_ALLOC_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|[^\n]*(?:\d+\s*%|\$[\d,]+)[^\n]*\|",
    re.MULTILINE,
)


def _table_looks_like_allocation(block: str) -> bool:
    rows = [ln for ln in block.splitlines() if ln.strip().startswith("|")]
    # Skip the header + divider; need at least one data row that smells like an alloc row.
    data_rows = [r for r in rows if not re.match(r"^\|\s*-+\s*\|", r) and not re.match(r"^\|\s*#\s*\|", r)]
    return any(_ALLOC_ROW_RE.match(r) for r in data_rows)


def replace_allocation_table_in_narrative(narrative: str, payload: Any) -> str:
    """Replace any allocation-shaped markdown table in `narrative` with one
    rendered from `payload`. Idempotent — if no allocation-like table is
    found, the function appends a fresh `## Allocation` section.

    The card payload is the SINGLE SOURCE OF TRUTH. After this call, the
    markdown table and the emitted card payload agree on N, weights, and
    $ amounts.
    """
    positions = _coerce_positions(payload)
    if not positions:
        return narrative or ""

    rendered_table = render_allocation_table(payload)
    summary = _payload_summary_line(payload)

    if not narrative:
        return render_allocation_section(payload)

    replaced = False

    def _sub(m: re.Match) -> str:
        nonlocal replaced
        block = m.group(1)
        if not _table_looks_like_allocation(block):
            return m.group(0)
        if replaced:
            # Only replace the FIRST allocation-like table — never duplicate.
            return ""
        replaced = True
        prefix = "\n" if m.group(0).startswith("\n") else ""
        return f"{prefix}{rendered_table}\n"

    new = _TABLE_BLOCK_RE.sub(_sub, narrative)
    if replaced:
        return new

    # No allocation-like table found — prepend a clean section so the card
    # and the prose still agree.
    return f"{render_allocation_section(payload)}\n\n{narrative.lstrip()}"


__all__ = [
    "render_allocation_table",
    "render_allocation_section",
    "replace_allocation_table_in_narrative",
]
