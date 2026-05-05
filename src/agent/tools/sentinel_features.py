"""Chat-callable wrappers around the Sentinel feature surface.

Exposes the same engines that power /analyze, /whales, /smart-money,
and /shield through agent tools so a chat user can run the full
Sentinel toolkit via natural language ("analyze this token X",
"who's the latest whale on Solana", "is contract Y safe").
"""
from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

from src.agent.tools._base import err_envelope, ok_envelope


_logger = logging.getLogger(__name__)
_analyzer = None
_API_BASE = os.environ.get("INTERNAL_API_BASE", "http://127.0.0.1:8080")


async def _get_analyzer():
    """Lazy-init shared TokenAnalyzer (heavy to construct)."""
    global _analyzer
    if _analyzer is None:
        from src.core.analyzer import TokenAnalyzer
        _analyzer = TokenAnalyzer()
    return _analyzer


def _format_score(value: Any, suffix: str = "/100") -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.0f}{suffix}"
    except (TypeError, ValueError):
        return "n/a"


def _format_usd(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if v >= 1_000_000_000:
        return f"${v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.2f}"


async def analyze_token_full_sentinel(
    ctx,
    *,
    address: str,
    chain: str | None = None,
    mode: str = "standard",
):
    """Run the full Sentinel token analyzer and return a structured card."""
    if not address or not isinstance(address, str):
        return err_envelope("missing_address", "Pass a token address (mint or 0x...) to analyze.")

    try:
        analyzer = await _get_analyzer()
        result = await analyzer.analyze(address.strip(), mode=mode, chain=chain)
    except Exception as exc:
        _logger.exception("analyze_token_full_sentinel failed")
        return err_envelope("analyzer_error", f"Token analysis failed: {exc}")

    if result is None:
        return err_envelope(
            "analysis_failed",
            "We couldn't gather enough data on this token. The address may be invalid, "
            "the token may be on an unsupported chain, or upstream APIs are temporarily down.",
        )

    token = result.token
    chain_label = (token.chain or "unknown").lower()
    score = float(getattr(result, "overall_score", 0) or 0)
    verdict = "SAFE" if score >= 70 else ("CAUTION" if score >= 50 else ("RISKY" if score >= 30 else "DANGEROUS"))
    grade = getattr(result, "grade", "F")

    payload = {
        "address": token.address,
        "chain": chain_label,
        "name": token.name,
        "symbol": token.symbol,
        "decimals": token.decimals,
        "price_usd": token.price_usd,
        "market_cap": token.market_cap,
        "liquidity_usd": token.liquidity_usd,
        "volume_24h": token.volume_24h,
        "scores": {
            "overall": score,
            "grade": grade,
            "verdict": verdict,
            "safety": getattr(result, "safety_score", None),
            "liquidity": getattr(result, "liquidity_score", None),
            "distribution": getattr(result, "distribution_score", None),
            "social": getattr(result, "social_score", None),
            "activity": getattr(result, "activity_score", None),
            "honeypot": getattr(result, "honeypot_score", None),
            "deployer": getattr(result, "deployer_reputation_score", None),
            "anomaly": getattr(result, "behavioral_anomaly_score", None),
        },
        "security": {
            "mint_authority_enabled": token.mint_authority_enabled,
            "freeze_authority_enabled": token.freeze_authority_enabled,
            "liquidity_locked": token.liquidity_locked,
            "lp_lock_percent": token.lp_lock_percent,
            "honeypot_status": token.honeypot_status,
            "is_honeypot": token.honeypot_is_honeypot,
            "buy_tax": token.goplus_buy_tax,
            "sell_tax": token.goplus_sell_tax,
            "is_renounced": token.is_renounced,
            "is_verified": token.is_verified,
        },
        "holders": {
            "top_holder_pct": token.top_holder_pct,
            "concentration": token.holder_concentration,
            "suspicious_wallets": token.suspicious_wallets,
            "flags": token.holder_flags,
        },
        "ai": {
            "verdict": token.ai_verdict,
            "score": token.ai_score,
            "rug_probability": token.ai_rug_probability,
            "summary": token.ai_summary,
            "red_flags": token.ai_red_flags,
            "green_flags": token.ai_green_flags,
            "recommendation": token.ai_recommendation,
        },
    }
    payload["analysis_trace"] = [
        f"Resolved {token.symbol or token.address[:6]} on {chain_label} via TokenAnalyzer ({mode}).",
        f"Sentinel score {score:.0f}/100 (grade {grade}) — verdict {verdict}.",
        "Aggregated safety, liquidity, distribution, holder, AI, and on-chain signals before summarising.",
    ]
    return ok_envelope(
        data=payload,
        card_type="text",
        card_payload={"text": _render_token_summary(payload), "kind": "sentinel_token_analysis"},
    )


def _render_token_summary(p: dict[str, Any]) -> str:
    scores = p.get("scores") or {}
    sec = p.get("security") or {}
    ai = p.get("ai") or {}
    holders = p.get("holders") or {}
    sym = p.get("symbol") or p.get("address", "")[:8]
    lines = [
        f"**Sentinel Analysis — {sym} on {p.get('chain','?').title()}**",
        f"Address: `{p.get('address')}`",
        "",
        f"**Overall:** {_format_score(scores.get('overall'))} · grade `{scores.get('grade','?')}` · verdict **{scores.get('verdict','?')}**",
        "",
        "**Score breakdown**",
        f"- Safety: {_format_score(scores.get('safety'))}",
        f"- Liquidity: {_format_score(scores.get('liquidity'))}",
        f"- Distribution: {_format_score(scores.get('distribution'))}",
        f"- Activity: {_format_score(scores.get('activity'))}",
        f"- Honeypot: {_format_score(scores.get('honeypot'))}",
        f"- Deployer reputation: {_format_score(scores.get('deployer'))}",
        f"- Behavioral anomaly: {_format_score(scores.get('anomaly'))}",
        "",
        "**Market**",
        f"- Price: ${p.get('price_usd') or 'n/a'}",
        f"- Market cap: {_format_usd(p.get('market_cap'))}",
        f"- Liquidity: {_format_usd(p.get('liquidity_usd'))}",
        f"- 24h volume: {_format_usd(p.get('volume_24h'))}",
        "",
        "**Security**",
        f"- Honeypot: {sec.get('honeypot_status','unknown')} (is_honeypot={sec.get('is_honeypot')})",
        f"- Buy/sell tax: {sec.get('buy_tax')}/{sec.get('sell_tax')}",
        f"- Liquidity locked: {sec.get('liquidity_locked')} ({sec.get('lp_lock_percent') or 0}%)",
        f"- Mint authority: {sec.get('mint_authority_enabled')} · Freeze: {sec.get('freeze_authority_enabled')}",
        f"- Renounced: {sec.get('is_renounced')} · Verified: {sec.get('is_verified')}",
        "",
        "**Holder distribution**",
        f"- Top holder: {holders.get('top_holder_pct') or 'n/a'}%",
        f"- Concentration: {holders.get('concentration') or 'n/a'}",
        f"- Suspicious wallets: {holders.get('suspicious_wallets') or 0}",
    ]
    if ai.get("verdict"):
        lines.extend([
            "",
            "**AI verdict**",
            f"- {ai.get('verdict')} (rug prob {ai.get('rug_probability') or '?'}%)",
        ])
        if ai.get("summary"):
            lines.append(f"  > {ai['summary']}")
        if ai.get("red_flags"):
            lines.append("  Red flags: " + ", ".join(str(x) for x in (ai["red_flags"] or [])[:5]))
        if ai.get("green_flags"):
            lines.append("  Green flags: " + ", ".join(str(x) for x in (ai["green_flags"] or [])[:5]))
        if ai.get("recommendation"):
            lines.append(f"  Recommendation: {ai['recommendation']}")
    return "\n".join(lines)


async def _internal_get(path: str, params: dict | None = None) -> dict | list | None:
    url = f"{_API_BASE}{path}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(url, params=params or {}) as r:
                if r.status >= 400:
                    return None
                return await r.json()
    except Exception:
        return None


async def track_whales(
    ctx,
    *,
    chain: str | None = None,
    hours: int = 24,
    limit: int = 10,
):
    """Surface recent whale transactions across supported chains."""
    params: dict[str, Any] = {"limit": min(int(limit or 10), 25), "hours": int(hours or 24)}
    if chain:
        params["chain"] = chain
    raw = await _internal_get("/api/v1/whales", params=params)
    if raw is None:
        return err_envelope("whale_unavailable", "Whale feed temporarily unavailable; try again in a moment.")
    items = raw.get("whales") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    items = items or []
    payload = {"items": items, "chain": chain, "hours": params["hours"]}
    text = _render_whale_summary(items, chain=chain, hours=params["hours"])
    return ok_envelope(
        data=payload,
        card_type="text",
        card_payload={"text": text, "kind": "sentinel_whale_feed"},
    )


def _render_whale_summary(items: list[dict[str, Any]], *, chain: str | None, hours: int) -> str:
    if not items:
        return f"No whale activity detected in the last {hours}h{f' on {chain}' if chain else ''}."
    lines = [f"**Whale activity — last {hours}h{f' on {chain}' if chain else ' (multi-chain)'}** · {len(items)} events"]
    for it in items[:10]:
        sym = it.get("token_symbol") or it.get("symbol") or it.get("token") or "?"
        usd = it.get("usd_value") or it.get("value_usd") or it.get("amount_usd")
        action = it.get("action") or it.get("type") or "tx"
        wallet = it.get("wallet") or it.get("from_address") or it.get("address") or ""
        chain_lbl = it.get("chain") or chain or ""
        lines.append(f"- {action.upper()} {sym} {_format_usd(usd)} on {chain_lbl} (wallet `{wallet[:8]}…`)")
    return "\n".join(lines)


async def get_smart_money_hub(
    ctx,
    *,
    chain: str = "solana",
    limit: int = 10,
):
    """Solana smart-money hub: top wallets, fresh accumulations, conviction picks."""
    raw = await _internal_get("/api/v1/smart-money/overview", params={"chain": chain, "limit": min(int(limit or 10), 25)})
    if raw is None:
        return err_envelope("hub_unavailable", "Smart-money hub temporarily unavailable; try again in a moment.")
    text = _render_hub_summary(raw, chain=chain)
    return ok_envelope(
        data={"raw": raw, "chain": chain},
        card_type="text",
        card_payload={"text": text, "kind": "sentinel_smart_money_hub"},
    )


def _render_hub_summary(raw: dict[str, Any], *, chain: str) -> str:
    lines = [f"**Smart-money hub — {chain}**"]
    for key, label in (
        ("top_wallets", "Top wallets"),
        ("recent_accumulations", "Recent accumulations"),
        ("trending_tokens", "Trending tokens"),
        ("conviction", "Conviction picks"),
    ):
        items = (raw or {}).get(key) or []
        if items:
            lines.append(f"\n**{label}**")
            for it in items[:5]:
                if isinstance(it, dict):
                    name = it.get("symbol") or it.get("name") or it.get("address") or "?"
                    usd = it.get("usd_value") or it.get("value_usd") or it.get("conviction")
                    lines.append(f"- {name} ({_format_usd(usd)})" if usd else f"- {name}")
    if len(lines) == 1:
        lines.append("(No live signals returned for that chain right now.)")
    return "\n".join(lines)


async def get_shield_check(
    ctx,
    *,
    address: str,
    chain: str | None = None,
):
    """Shield risk assessment for a wallet or contract address."""
    if not address:
        return err_envelope("missing_address", "Pass a wallet/contract address to scan with Shield.")
    path = f"/api/v1/shield/{address}"
    if chain:
        path = f"/api/v1/shield/{address}/{chain}"
    raw = await _internal_get(path)
    if raw is None:
        return err_envelope("shield_unavailable", "Shield scan temporarily unavailable.")
    text = _render_shield_summary(raw, address=address, chain=chain)
    return ok_envelope(
        data={"raw": raw, "address": address, "chain": chain},
        card_type="text",
        card_payload={"text": text, "kind": "sentinel_shield_report"},
    )


def _render_shield_summary(raw: dict[str, Any], *, address: str, chain: str | None) -> str:
    verdict = (raw or {}).get("verdict") or "unknown"
    risk = (raw or {}).get("risk_score")
    findings = (raw or {}).get("findings") or (raw or {}).get("approvals") or []
    lines = [
        f"**Shield report — `{address[:10]}…`{f' on {chain}' if chain else ''}**",
        f"Verdict: **{verdict}**" + (f" · risk {risk}" if risk is not None else ""),
    ]
    if findings:
        lines.append("\n**Findings**")
        for f in findings[:8]:
            if isinstance(f, dict):
                spender = f.get("spender") or f.get("contract") or "?"
                token = f.get("token") or f.get("symbol") or "?"
                lvl = f.get("severity") or f.get("risk") or ""
                lines.append(f"- `{spender[:10]}…` allowed to spend {token} {lvl}")
    else:
        lines.append("\n(No significant approvals or risks detected.)")
    return "\n".join(lines)


async def lookup_entity(
    ctx,
    *,
    query: str,
):
    """Resolve a name, ENS, address, or fund tag to a Sentinel entity profile."""
    if not query:
        return err_envelope("missing_query", "Pass an address, ENS, fund tag, or name to look up.")
    qnorm = str(query).strip()
    raw = await _internal_get(f"/api/v1/entities/{qnorm}")
    if raw is None:
        listing = await _internal_get("/api/v1/entities", params={"q": qnorm})
        if isinstance(listing, dict):
            entries = listing.get("entities") or []
            if entries:
                raw = entries[0]
    if not raw:
        return err_envelope("entity_not_found", f"No Sentinel entity profile matched `{qnorm}`.")
    name = raw.get("name") or raw.get("label") or qnorm
    tags = raw.get("tags") or raw.get("classifications") or []
    addrs = raw.get("addresses") or []
    summary_lines = [f"**Entity — {name}**"]
    if tags:
        summary_lines.append("Tags: " + ", ".join(str(t) for t in tags[:8]))
    if addrs:
        summary_lines.append(f"Linked addresses: {len(addrs)} (first: `{str(addrs[0])[:14]}…`)")
    if raw.get("description"):
        summary_lines.append(str(raw["description"])[:280])
    return ok_envelope(
        data={"entity": raw, "query": qnorm},
        card_type="text",
        card_payload={"text": "\n".join(summary_lines), "kind": "sentinel_entity"},
    )


async def analyze_pool(
    ctx,
    *,
    pool: str,
    chain: str | None = None,
):
    """Sentinel-grade pool analysis. Accepts DefiLlama pool UUID or 'protocol pair'."""
    if not pool:
        return err_envelope("missing_pool", "Pass a DefiLlama pool UUID or 'protocol pair'.")
    from src.agent.tools.execute_pool_position import (
        _fetch_pool_meta,
        _looks_like_pool_id,
        _resolve_protocol_pair,
        _split_protocol_pair,
    )
    pool_arg = str(pool).strip()
    if _looks_like_pool_id(pool_arg):
        meta = await _fetch_pool_meta(pool_arg)
    else:
        protocol_hint, pair_hint = _split_protocol_pair(pool_arg)
        meta = await _resolve_protocol_pair(protocol_hint, pair_hint, chain=chain)
    if not meta:
        return err_envelope("pool_not_found", f"Could not resolve pool `{pool_arg}` against DefiLlama.")
    apy = meta.get("apy") or meta.get("apyBase")
    tvl = meta.get("tvlUsd")
    risk = meta.get("ilRisk") or "medium"
    lines = [
        f"**Pool — {meta.get('project','?')} · {meta.get('symbol','?')} on {meta.get('chain','?')}**",
        f"APY: {apy:.2f}%" if isinstance(apy, (int, float)) else f"APY: {apy or 'n/a'}",
        f"TVL: {_format_usd(tvl)}",
        f"IL risk: {risk}",
    ]
    if meta.get("predictions"):
        pred = meta["predictions"]
        if pred.get("predictedClass"):
            lines.append(f"DefiLlama outlook: {pred['predictedClass']}")
    if meta.get("underlyingTokens"):
        lines.append(f"Underlying tokens: {len(meta['underlyingTokens'])}")
    return ok_envelope(
        data={"pool": meta},
        card_type="text",
        card_payload={"text": "\n".join(lines), "kind": "sentinel_pool_report"},
    )
