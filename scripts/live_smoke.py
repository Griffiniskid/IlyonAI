#!/usr/bin/env python3
"""Live API smoke harness.

Hits the /api/v1/agent SSE endpoint with a battery of canonical and
adversarial inputs and classifies the outcome of each one. Outputs a
pass/fail table so we can spot bug-class regressions before testers do.

Usage: python scripts/live_smoke.py [--base https://ilyonai.com] [--print]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field

import aiohttp


@dataclass
class Case:
    id: str
    input: str
    expect: str  # 'card' | 'refuse' | 'bridge_card' | 'reasoning_only' | 'either_card_or_refuse'
    note: str = ""


@dataclass
class Outcome:
    case_id: str
    saw_card: bool = False
    card_type: str | None = None
    saw_error: bool = False
    error_msg: str | None = None
    saw_bridge_card: bool = False
    saw_reasoning: bool = False
    final_text: str = ""
    raw_events: list[str] = field(default_factory=list)


def cases() -> list[Case]:
    return [
        # ── Screenshot regressions ─────────────────────────────────────────
        Case("scr1_swap_usdt_wbnb",
             "swap 100 usdt to wbnb",
             "either_card_or_refuse",
             "screenshot 1; must NOT show raw 'Enso 429'"),
        Case("scr1_swap_sol_eth",
             "swap 0.04 sol to eth",
             "either_card_or_refuse",
             "screenshot 1 cross-chain; must bridge or refuse"),
        Case("scr2_swap_sol_weth",
             "swap 0.1 sol for weth",
             "either_card_or_refuse",
             "screenshot 2 cross-chain; no Jupiter WrongSize"),
        Case("scr3_swap_usdc_wbnb_solana",
             "swap 100 usdc on solana chain to wbnb",
             "refuse",
             "screenshot 3 zero-amount preview; must refuse"),
        Case("scr4_wallet_phrase",
             "swap 100 usdc on solana chain from my wallet to wbnb",
             "refuse",
             "screenshot 4 WALLET token; must refuse"),

        # ── Canonical paths (must succeed → card OR refuse with clean
        # message; burner wallets can't sign so aggregator may reject). ────
        Case("canon_sol_usdc",
             "swap 0.1 SOL to USDC",
             "either_card_or_refuse",
             "Solana canonical"),
        Case("canon_usdc_eth",
             "swap 100 USDC to ETH on ethereum",
             "either_card_or_refuse",
             "EVM canonical"),
        Case("canon_bnb_cake",
             "swap 0.5 BNB to CAKE on bsc",
             "either_card_or_refuse",
             "BSC canonical"),
        Case("canon_buy_bonk",
             "buy 100 BONK",
             "either_card_or_refuse",
             "buy intent"),
        Case("canon_sell_all",
             "sell all my SOL",
             "either_card_or_refuse",
             "ALL sentinel; needs wallet → refuse for guest"),
        Case("canon_bridge_explicit",
             "bridge 100 USDC from ethereum to arbitrum",
             "either_card_or_refuse",
             "explicit bridge"),

        # ── Adversarial NLU ───────────────────────────────────────────────
        Case("adv_typo_swp",
             "swp 0.1 sol to usdc",
             "either_card_or_refuse",
             "typo on action"),
        Case("adv_caps",
             "SWAP 0.1 SOL TO USDC",
             "either_card_or_refuse",
             "all caps"),
        Case("adv_emoji",
             "swap 0.1 sol to usdc 🚀",
             "either_card_or_refuse",
             "emoji"),
        Case("adv_extra_punct",
             "swap, 0.1 sol, to usdc.",
             "either_card_or_refuse",
             "punct"),
        Case("adv_missing_amount",
             "swap sol to usdc",
             "refuse",
             "no amount"),
        Case("adv_amount_only",
             "swap 0.1 to usdc",
             "refuse",
             "no source"),
        Case("adv_chain_only",
             "swap on solana",
             "refuse",
             "no tokens"),
        Case("adv_long_meme",
             "swap 0.1 sol to FATPENGU",
             "either_card_or_refuse",
             "Solana meme"),
        Case("adv_unknown_token",
             "swap 100 usdc to ZZZTOTALLYFAKE",
             "either_card_or_refuse",
             "unknown ticker"),
        Case("adv_zero_amount",
             "swap 0 sol to usdc",
             "refuse",
             "zero amount"),
        Case("adv_negative_amount",
             "swap -1 sol to usdc",
             "refuse",
             "negative amount"),
        Case("adv_huge_amount",
             "swap 999999999999999 eth to usdc",
             "refuse",
             "absurd amount"),

        # ── Cross-chain that must NOT swap ────────────────────────────────
        Case("xchain_pepe_bonk",
             "swap 1000 pepe to bonk",
             "either_card_or_refuse",
             "PEPE on ETH, BONK on Sol; bridge or refuse"),
        Case("xchain_cake_bonk",
             "swap 10 cake to bonk",
             "either_card_or_refuse",
             "CAKE on BSC, BONK on Sol"),
        Case("xchain_eth_sol",
             "swap 1 eth to sol",
             "either_card_or_refuse",
             "ETH→SOL cross-chain"),

        # ── Other tools ───────────────────────────────────────────────────
        Case("price_sol",
             "what is the price of SOL",
             "either_card_or_refuse",
             "price intent"),
        Case("balance",
             "show my portfolio",
             "either_card_or_refuse",
             "balance intent (no wallet)"),
        Case("staking",
             "best staking options for SOL",
             "either_card_or_refuse",
             "staking search"),

        # ── Stake / transfer NLU not in screenshot set ────────────────────
        Case("stake_simple",
             "stake 1 sol",
             "either_card_or_refuse",
             "stake → LST"),
        Case("transfer",
             "send 0.1 sol to 11111111111111111111111111111111",
             "either_card_or_refuse",
             "transfer to base58"),

        # ── Pure conversational ───────────────────────────────────────────
        Case("conversational_hi",
             "hi",
             "reasoning_only",
             "no tool fire"),
        Case("conversational_help",
             "what can you do",
             "reasoning_only",
             "general help"),

        # ── Other intent surfaces ─────────────────────────────────────────
        Case("dex_search",
             "find me USDC pools on solana",
             "either_card_or_refuse",
             "pool search"),
        Case("liquidity_pool",
             "best USDC/WETH pools",
             "either_card_or_refuse",
             "LP search"),
        Case("trending",
             "what is trending today",
             "either_card_or_refuse",
             "trending"),
        Case("allocate",
             "allocate 1000 USDC across solana DeFi",
             "either_card_or_refuse",
             "allocation"),
        Case("compare_protocols",
             "compare aave and compound",
             "either_card_or_refuse",
             "protocol compare"),

        # ── More chain coverage ───────────────────────────────────────────
        Case("chain_arbitrum",
             "swap 100 usdc to weth on arbitrum",
             "either_card_or_refuse",
             "arbitrum chain"),
        Case("chain_base",
             "swap 100 usdc to weth on base",
             "either_card_or_refuse",
             "base chain"),
        Case("chain_polygon",
             "swap 100 usdc to matic on polygon",
             "either_card_or_refuse",
             "polygon chain"),
        Case("chain_optimism",
             "swap 100 usdc to op on optimism",
             "either_card_or_refuse",
             "optimism chain"),

        # ── Adversarial: address-shaped tokens, prepositional noise ───────
        Case("adv_address_in_swap",
             "swap 100 0x0000000000000000000000000000000000000000 to usdc",
             "refuse",
             "raw address as ticker"),
        Case("adv_double_amount",
             "swap 100 200 sol to usdc",
             "either_card_or_refuse",
             "two numbers — must not pick wrong one"),
        Case("adv_multi_to",
             "swap 100 usdc to eth to btc",
             "either_card_or_refuse",
             "two destinations — pick one"),
        Case("adv_question",
             "can I swap sol to usdc?",
             "reasoning_only",
             "question form should not fire tool"),
        Case("adv_url",
             "swap 100 https://example.com to usdc",
             "refuse",
             "URL injection"),

        # ── Stake adversarials ────────────────────────────────────────────
        Case("stake_unknown_token",
             "stake 100 ZZZZ",
             "refuse",
             "unknown stake target"),
        Case("stake_with_protocol",
             "stake 1 sol with jito",
             "either_card_or_refuse",
             "explicit stake protocol"),

        # ── Bridge adversarials ───────────────────────────────────────────
        Case("bridge_same_chain",
             "bridge 100 usdc from ethereum to ethereum",
             "refuse",
             "same chain — not bridge"),
        Case("bridge_unknown_chain",
             "bridge 100 usdc from mars to earth",
             "refuse",
             "unknown chain"),

        # ── Multi-step / compose_plan ─────────────────────────────────────
        Case("multi_swap_then_lp",
             "swap 100 usdc to weth then add liquidity",
             "either_card_or_refuse",
             "multi-step compose"),
        Case("multi_bridge_then_stake",
             "bridge 100 usdc from ethereum to solana then stake",
             "either_card_or_refuse",
             "compose plan"),

        # ── Numeric edge / formatting ─────────────────────────────────────
        Case("amt_comma",
             "swap 1,000 usdc to eth",
             "either_card_or_refuse",
             "comma-formatted amount"),
        Case("amt_dust",
             "swap 0.000000001 sol to usdc",
             "either_card_or_refuse",
             "dust amount — 1e-9"),
        Case("amt_k_suffix",
             "swap 10k usdc to eth",
             "either_card_or_refuse",
             "k suffix"),
        Case("amt_m_suffix",
             "swap 0.1m usdc to eth",
             "either_card_or_refuse",
             "m suffix"),

        # ── Synonyms ──────────────────────────────────────────────────────
        Case("syn_exchange",
             "exchange 0.1 sol for usdc",
             "either_card_or_refuse",
             "exchange synonym"),
        Case("syn_convert",
             "convert 0.1 sol into usdc",
             "either_card_or_refuse",
             "convert synonym"),
        Case("syn_trade",
             "trade 0.1 sol for usdc",
             "either_card_or_refuse",
             "trade synonym"),

        # ── Token name conflicts ──────────────────────────────────────────
        Case("token_named_max",
             "swap max usdc to eth",
             "either_card_or_refuse",
             "MAX is a quantifier, not a ticker"),
        Case("token_named_all",
             "swap all to eth",
             "refuse",
             "no source token, just ALL"),
        Case("token_jp",
             "swap 1 jp to usdc",
             "either_card_or_refuse",
             "JP — too short, must reject or unknown"),

        # ── Portfolio-context phrasings ───────────────────────────────────
        Case("portfolio_sell_pct",
             "sell 10% of my portfolio",
             "either_card_or_refuse",
             "PORTFOLIO must not become token; show balance instead"),
        Case("holdings_swap_to_usdc",
             "swap all my holdings to USDC",
             "either_card_or_refuse",
             "HOLDINGS must not become token"),
        Case("bags_sell",
             "sell my bags",
             "either_card_or_refuse",
             "BAGS slang"),

        # ── Sentence-style phrasings ──────────────────────────────────────
        Case("sentence_swap",
             "I want to swap my SOL for ETH",
             "either_card_or_refuse",
             "sentence-style intent"),
        Case("sentence_help",
             "help me move 100 USDC from polygon to base",
             "either_card_or_refuse",
             "verbose bridge"),
        Case("sentence_fast",
             "fast bridge ETH to BNB chain",
             "either_card_or_refuse",
             "missing amount"),

        # ── Address scan / contract intent ────────────────────────────────
        Case("scan_pepe_addr",
             "is this token safe: 0x6982508145454ce325ddbe47a25d4ec3d2311933",
             "either_card_or_refuse",
             "contract scan"),

        # ── Empty / weird inputs ──────────────────────────────────────────
        Case("empty_input",
             "",
             "reasoning_only",
             "blank message"),
        Case("only_punct",
             "?!?",
             "reasoning_only",
             "punctuation only"),
        Case("only_emoji",
             "🚀🚀🚀",
             "reasoning_only",
             "emoji only"),
        Case("very_long",
             "swap " + ("very " * 200) + "0.1 sol to usdc",
             "either_card_or_refuse",
             "noisy long prompt"),

        # ── Questions / hypotheticals — must NOT execute ──────────────────
        Case("q_why_cant",
             "why cant I swap 0.1 sol to usdc",
             "either_card_or_refuse",
             "question must not execute"),
        Case("q_how_do_i",
             "how do I swap sol to usdc",
             "either_card_or_refuse",
             "how-to question"),
        Case("q_can_you",
             "can you swap 0.1 sol to usdc",
             "either_card_or_refuse",
             "polite question"),
        Case("hyp_future",
             "I will swap 0.1 SOL to USDC tomorrow",
             "either_card_or_refuse",
             "future tense"),
        Case("hyp_conditional",
             "swap 0.1 sol to USDC, but only if price is good",
             "either_card_or_refuse",
             "conditional"),
        Case("hyp_explain",
             "explain how to swap sol to usdc",
             "either_card_or_refuse",
             "explanation request"),
    ]


async def run_case(session: aiohttp.ClientSession, base: str, c: Case,
                   evm_wallet: str = "", solana_wallet: str = "") -> Outcome:
    import uuid as _uuid
    out = Outcome(case_id=c.id)
    payload = {
        "message": c.input,
        "session_id": f"smoke-{c.id}-{_uuid.uuid4().hex[:8]}",
    }
    if evm_wallet:
        payload["evm_wallet"] = evm_wallet
        payload["wallet"] = evm_wallet
    if solana_wallet:
        payload["solana_wallet"] = solana_wallet
        if not evm_wallet:
            payload["wallet"] = solana_wallet
    try:
        async with session.post(
            f"{base}/api/v1/agent",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                out.saw_error = True
                out.error_msg = f"HTTP {resp.status}"
                return out
            buf = b""
            async for chunk in resp.content.iter_any():
                buf += chunk
            text = buf.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        out.saw_error = True
        out.error_msg = "timeout"
        return out
    except Exception as exc:
        out.saw_error = True
        out.error_msg = f"{type(exc).__name__}: {exc}"
        return out

    # Crude SSE parser: split by double-newline and look at event/data lines
    for evt in text.split("\n\n"):
        if not evt.strip():
            continue
        out.raw_events.append(evt)
        if "event: card" in evt or '"card_type"' in evt:
            out.saw_card = True
            m = re.search(r'"card_type":\s*"([^"]+)"', evt)
            if m:
                ct = m.group(1)
                out.card_type = ct
                if ct in ("bridge_quote", "bridge_card"):
                    out.saw_bridge_card = True
        if "event: error" in evt or '"code":"swap_failed"' in evt or '"code": "swap_failed"' in evt:
            out.saw_error = True
            m = re.search(r'"message":\s*"([^"]+)"', evt)
            if m:
                out.error_msg = m.group(1)
        if "event: thought" in evt or "event: tool" in evt or "event: observation" in evt:
            out.saw_reasoning = True
        if "event: final" in evt:
            m = re.search(r'"text":\s*"([^"]*)"', evt) or re.search(r'"content":\s*"([^"]*)"', evt)
            if m:
                out.final_text = m.group(1)
            # Final-text refuse signal: agent prepended "swap_failed" /
            # "couldn't complete" / "rejected" — surface as error so the harness
            # classifies the case as a refuse, not "saw card".
            if ("swap_failed" in evt or "rejected" in evt
                    or "couldn't complete" in evt or "couldn\\u2014" in evt):
                out.saw_error = True
                if not out.error_msg:
                    em = re.search(r'\\\*\\\*([a-z_]+)\\\*\\\*[^"]*"', evt)
                    out.error_msg = em.group(1) if em else "refused"
    return out


def classify(case: Case, out: Outcome) -> tuple[bool, str]:
    """Return (passed, reason)."""
    if out.error_msg and ("HTTP" in out.error_msg or out.error_msg == "timeout"):
        return False, f"transport: {out.error_msg}"

    if case.expect == "card":
        if out.saw_card:
            return True, f"card={out.card_type}"
        return False, f"expected card, got error={out.error_msg!r} reasoning={out.saw_reasoning}"

    if case.expect == "refuse":
        if out.saw_card and not out.saw_error:
            return False, f"expected refuse, got card={out.card_type}"
        return True, "refused"

    if case.expect == "bridge_card":
        if out.saw_bridge_card:
            return True, "bridge"
        return False, f"expected bridge card, got card={out.card_type} error={out.error_msg!r}"

    if case.expect == "either_card_or_refuse":
        if out.saw_card or out.saw_error or out.saw_reasoning:
            return True, ("card=" + str(out.card_type)) if out.saw_card else (
                f"refused ({out.error_msg or 'no card'})")
        return False, "no card, no refuse, no reasoning"

    if case.expect == "reasoning_only":
        if out.saw_reasoning and not out.saw_card:
            return True, "reasoning"
        return False, f"saw card={out.saw_card} reasoning={out.saw_reasoning}"

    return False, "unknown expect"


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="https://ilyonai.com",
                   help="API base URL (default: production)")
    p.add_argument("--print", action="store_true",
                   help="print raw SSE events for each case")
    p.add_argument("--filter", default="",
                   help="only run cases whose id contains this substring")
    p.add_argument("--evm-wallet", default="",
                   help="attach an EVM wallet to every request (e.g. burner)")
    p.add_argument("--solana-wallet", default="",
                   help="attach a Solana wallet to every request")
    args = p.parse_args()

    rows = cases()
    if args.filter:
        rows = [c for c in rows if args.filter in c.id]

    results = []
    async with aiohttp.ClientSession() as session:
        # Sequential with throttle to avoid agent_gap rate limit on production.
        for c in rows:
            out = await run_case(session, args.base, c,
                                 evm_wallet=args.evm_wallet,
                                 solana_wallet=args.solana_wallet)
            ok, reason = classify(c, out)
            results.append((c, out, ok, reason))
            tag = "PASS" if ok else "FAIL"
            print(f"[{tag}] {c.id:30s} {reason}", flush=True)
            if args.print and out.raw_events:
                for e in out.raw_events:
                    print("    ", e[:300])
            # Throttle: agent_gap is roughly per-IP. Sleep enough that we don't
            # 429 ourselves into uselessness.
            await asyncio.sleep(5)

    failures = [(c, out, reason) for c, out, ok, reason in results if not ok]
    print()
    print(f"summary: {len(results) - len(failures)}/{len(results)} passed")
    if failures:
        print("failures:")
        for c, out, reason in failures:
            print(f"  - {c.id}: {reason}")
            print(f"    input: {c.input!r}")
            print(f"    note:  {c.note}")
            if out.error_msg:
                print(f"    err:   {out.error_msg}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
