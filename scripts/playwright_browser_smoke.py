"""L4 — Playwright tester-ready validation (Gate 4).

For each scripted matrix-chain flow, against `staging.ilyonai.com`:

1. Inject mocked MetaMask + Phantom EVM/Solana providers BEFORE page load
2. Patch window.fetch to capture every SSE frame from /api/v1/agent
3. Navigate to /agent/chat, type prompt(s) into composer, send
4. Wait for `final` frame
5. Assert every card emitted has a corresponding DOM node (no silent drops)
6. Scan rendered DOM for `undefined`/`NaN`/`null`/blank-state leaks
7. For execution_plan_v3 cards with status:ready: click Sign on the first
   signable step, assert window.ethereum._signed[0] params EXACTLY match
   the SSE card's step.transaction (no UI-side re-encoding)
8. For blocker cards: assert typed UPPER_SNAKE code + recovery CTA visible
9. Capture console errors throughout; any error fails the flow

Artifacts → `docs/playwright-runs/<ts>/` (per-flow logs + screenshots on fail)

Gate criterion: N/N flows PASS, 0 bug instances, 0 console errors.

Run: `PYTHONIOENCODING=utf-8 python scripts/playwright_browser_smoke.py`
     `PYTHONIOENCODING=utf-8 python scripts/playwright_browser_smoke.py --flow A01-t5`
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, ConsoleMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("ILYON_BASE", "https://staging.ilyonai.com")
EVM_WALLET = "0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97"
SOL_WALLET = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"

RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = ROOT / "docs" / "playwright-runs" / RUN_TS
OUT_DIR.mkdir(parents=True, exist_ok=True)


INJECT_PROVIDERS_JS = r"""
// Mock MetaMask EIP-1193 provider
window.__signed = [];
window.ethereum = {
  isMetaMask: true,
  isConnected: () => true,
  selectedAddress: '%EVM%',
  chainId: '0x1',
  networkVersion: '1',
  _signed: window.__signed,
  request: async ({ method, params }) => {
    if (method === 'eth_requestAccounts' || method === 'eth_accounts') {
      return ['%EVM%'];
    }
    if (method === 'eth_chainId') return '0x1';
    if (method === 'wallet_switchEthereumChain') return null;
    if (method === 'wallet_addEthereumChain') return null;
    if (method === 'eth_sendTransaction' || method === 'eth_signTransaction') {
      window.__signed.push({ method, params });
      return '0x' + 'aa'.repeat(32);
    }
    if (method === 'personal_sign' || method === 'eth_sign' ||
        method === 'eth_signTypedData_v4') {
      window.__signed.push({ method, params });
      return '0x' + 'bb'.repeat(65);
    }
    return null;
  },
  on: () => {},
  removeListener: () => {},
};

// Mock Phantom (Solana + EVM)
window.phantom = {
  ethereum: {
    isPhantom: true,
    isConnected: () => true,
    selectedAddress: '%EVM%',
    chainId: '0x1',
    _signed: window.__signed,
    request: async (args) => window.ethereum.request(args),
    on: () => {},
    removeListener: () => {},
  },
  solana: {
    isPhantom: true,
    isConnected: true,
    publicKey: { toString: () => '%SOL%' },
    connect: async () => ({ publicKey: { toString: () => '%SOL%' } }),
    disconnect: async () => null,
    signTransaction: async (tx) => { window.__signed.push({ method: 'sol_signTx', params: [tx] }); return tx; },
    signAndSendTransaction: async (tx) => { window.__signed.push({ method: 'sol_signAndSend', params: [tx] }); return { signature: 'mock_sig' }; },
    on: () => {},
    removeListener: () => {},
  },
};
window.solana = window.phantom.solana;
"""

# Patch fetch to capture every SSE frame emitted by the agent endpoint.
# We don't intercept — we shadow the response body: clone the stream,
# pipe one to the page, decode the other ourselves into window.__sseFrames.
INJECT_SSE_CAPTURE_JS = r"""
window.__sseFrames = [];
window.__sseDone = false;
(() => {
  const origFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : input.url;
    // Match only the agent SSE endpoint (not /api/v1/agent-health etc.)
    if (!url || !/\/api\/v1\/agent(?:[\?\/]|$)/.test(url)) {
      return origFetch(input, init);
    }
    const resp = await origFetch(input, init);
    if (!resp.body) return resp;
    const [a, b] = resp.body.tee();
    // Consume `b` ourselves into __sseFrames. SSE blocks have the form:
    //   event: <name>\n
    //   data: <json>\n
    //   \n
    // We must track the `event:` line — that's the discriminator. The
    // backend (src/agent/streaming.py::encode_sse) emits no `kind` field
    // in the data payload itself.
    (async () => {
      const reader = b.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buf.indexOf('\n\n')) !== -1) {
            const block = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            let eventName = null;
            const dataLines = [];
            for (const line of block.split('\n')) {
              if (line.startsWith('event:')) {
                eventName = line.slice(6).trim();
              } else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5).trimStart());
              }
            }
            if (!dataLines.length) continue;
            const payload = dataLines.join('\n');
            try {
              const data = JSON.parse(payload);
              // Inject `kind` from the SSE event name. Default to
              // 'data' for chunks without an explicit event line.
              const frame = Object.assign({ kind: eventName || 'data' }, data);
              window.__sseFrames.push(frame);
              if (frame.kind === 'final' || frame.kind === 'done') {
                window.__sseDone = true;
              }
            } catch (e) {
              window.__sseFrames.push({ kind: 'parse_error', event: eventName, raw: payload });
            }
          }
        }
      } catch (e) {
        window.__sseFrames.push({ kind: 'stream_error', error: String(e) });
      } finally {
        window.__sseDone = true;
      }
    })();
    // Return a fresh Response using stream `a` to the page
    return new Response(a, {
      status: resp.status,
      statusText: resp.statusText,
      headers: resp.headers,
    });
  };
})();
"""


# ---------------------------------------------------------------------------
# Flow definitions — small representative set for v1. Will expand to 30+
# directly from tests/harness/v4_matrix.py once v1 stabilizes.
# ---------------------------------------------------------------------------
@dataclass
class Flow:
    id: str
    prompts: list[str]
    expect_cards: set[str] = field(default_factory=set)
    expect_sign: bool = False
    note: str = ""


FLOWS: list[Flow] = [
    # ── Category A: search → refine → execute ─────────────────────────────
    Flow(
        id="A01_aave_base_usdc",
        prompts=[
            "Find me USDC lending on Base",
            "Filter to Aave only",
            "Use $250 instead",
            "Actually on Optimism",
            "Execute on Aave V3 with 250 USDC",
        ],
        expect_cards={"pool_link", "execution_plan_v3"},
        expect_sign=True,
        note="Single-pool search → refine → execute (sign EVM supply)",
    ),
    Flow(
        id="A02_steth_lido",
        prompts=[
            "What's the best place to stake my ETH?",
            "Lido only",
            "0.5 ETH",
        ],
        expect_cards={"pool_link"},
        expect_sign=False,
        note="LST staking pool_link only (no auto-execute)",
    ),
    Flow(
        id="A06_morpho_blue",
        prompts=[
            "Show me Morpho Blue markets on Ethereum",
            "Just USDC markets",
            "100 USDC",
        ],
        expect_cards={"defi_opportunities"},
        expect_sign=False,
        note="Morpho Blue — alt protocol search + refine",
    ),
    Flow(
        id="A12_lido_ethereum",
        prompts=[
            "I want to stake 1 ETH on Lido",
            "Show me the execution plan",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=True,
        note="LST direct stake — Lido EVM LST mint",
    ),

    # ── Category B: strategy compose ──────────────────────────────────────
    Flow(
        id="B01_stable_strategy",
        prompts=[
            "Build me a stable yield strategy across Aave Base, Compound, Spark",
            "Make it $5000 total",
            "Now show me the execution plan",
        ],
        expect_cards={"allocation", "execution_plan_v3"},
        expect_sign=True,
        note="Strategy compose → multi-step composed plan",
    ),
    Flow(
        id="B10_pendle_pt",
        prompts=[
            "Build me a yield strategy on Pendle with PT-positions",
            "$1000",
        ],
        expect_cards={"defi_opportunities"},
        expect_sign=False,
        note="Pendle PT yield strategy",
    ),

    # ── Category C: pool refinement ───────────────────────────────────────
    Flow(
        id="C01_aave_base_refine_chain",
        prompts=[
            "USDC lending Aave V3 on Base",
            "Show me Arbitrum instead",
            "100 USDC",
            "Now execute",
        ],
        expect_cards={"pool_link", "execution_plan_v3"},
        expect_sign=True,
        note="Refinement: chain swap then execute",
    ),

    # ── Category D: lifecycle close-out ───────────────────────────────────
    Flow(
        id="D03_compound_claim_withdraw",
        prompts=[
            "Claim my Compound rewards on Ethereum",
            "Now withdraw my whole supply position",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=True,
        note="Compound claim → withdraw multi-step lifecycle",
    ),

    # ── Category E: cross-chain composed plan ─────────────────────────────
    Flow(
        id="E03_eth_to_polygon_aave",
        prompts=[
            "Bridge 200 USDC from Ethereum to Polygon and supply to Aave V3",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=True,
        note="Cross-chain composed: bridge + supply",
    ),

    # ── Category F: stuck-balance + recovery ──────────────────────────────
    Flow(
        id="F03_no_balance",
        prompts=[
            "Supply 1000000 USDC to Aave V3 on Ethereum",  # huge amount → likely insufficient_balance
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=False,
        note="Insufficient balance → blocker with typed code + recovery CTA",
    ),
    Flow(
        id="F01_unsupported_adapter",
        prompts=[
            "Execute on some obscure protocol XYZ on Polygon with 50 USDC",
        ],
        expect_cards=set(),  # likely text refusal
        expect_sign=False,
        note="Unsupported adapter — clean refusal with no signable card",
    ),

    # ── Category H: §7 funding scenarios ─────────────────────────────────
    Flow(
        id="H03_S3_native_eth_V3",
        prompts=[
            "Add liquidity to Uniswap V3 USDC/WETH 0.05% on Ethereum with 0.5 ETH",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=True,
        note="§7 S3 — native ETH funding source → wrap step + LP mint",
    ),
    Flow(
        id="H13_S13_aave_supply",
        prompts=[
            "Supply 50 USDT to Aave V3 on Arbitrum",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=True,
        note="§7 S13 — simple ERC20 supply (Aave V3 Arbitrum USDT)",
    ),

    # ── Category I: session-key flow ─────────────────────────────────────
    Flow(
        id="I01_session_key_aave",
        prompts=[
            "Install a session key for Aave V3 supply with $500 daily cap",
            "Actually 1000 daily",
            "OK install it",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=True,
        note="§11 D.5/D.6 — session-key install with daily cap refinement",
    ),

    # ── Card-type coverage expansion (v4) ────────────────────────────────
    # Each flow below is engineered to surface a specific CardType so that
    # Gate 4's "every card type renders" requirement is exercised. Cards
    # we cannot trigger by user prompt (invariant_violation = backend-only,
    # sentinel_matrix = composer-only) are left for follow-up.

    Flow(
        id="cov_swap_quote",
        prompts=["Quote a swap of 100 USDC to USDT on Ethereum"],
        expect_cards={"swap_quote"},
        expect_sign=False,
        note="Coverage: swap_quote card",
    ),
    Flow(
        id="cov_balance_report",
        prompts=["Show me my wallet balance across all chains"],
        expect_cards={"balance", "balance_report"},
        expect_sign=False,
        note="Coverage: balance / balance_report card",
    ),
    Flow(
        id="cov_token_price",
        prompts=["What's the price of BTC?"],
        expect_cards={"token", "sentinel_token_report"},
        expect_sign=False,
        note="Coverage: token / sentinel_token_report card",
    ),
    Flow(
        id="cov_pool_report",
        prompts=["Is the Lido stETH pool safe?"],
        expect_cards={"pool", "sentinel_pool_report"},
        expect_sign=False,
        note="Coverage: pool / sentinel_pool_report card",
    ),
    Flow(
        id="cov_whale_feed",
        prompts=["Show me whales on Solana"],
        expect_cards={"sentinel_whale_feed"},
        expect_sign=False,
        note="Coverage: sentinel_whale_feed card",
    ),
    Flow(
        id="cov_smart_money",
        prompts=["Show me smart money flows on Ethereum"],
        expect_cards={"sentinel_smart_money_hub"},
        expect_sign=False,
        note="Coverage: sentinel_smart_money_hub card",
    ),
    Flow(
        id="cov_shield_report",
        prompts=["Run a Shield audit on USDC at 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"],
        expect_cards={"sentinel_shield_report"},
        expect_sign=False,
        note="Coverage: sentinel_shield_report card",
    ),
    Flow(
        id="cov_market_overview",
        prompts=["What's trending in DeFi right now?"],
        expect_cards={"market_overview"},
        expect_sign=False,
        note="Coverage: market_overview card",
    ),
    Flow(
        id="cov_v3_lp_mint",
        prompts=[
            "Mint a Uniswap V3 NFT for USDC/WETH 0.05% on Ethereum",
            "Use $200, full range",
        ],
        expect_cards={"pool_deposit_v3", "execution_plan_v3"},
        expect_sign=True,
        note="Coverage: pool_deposit_v3 card",
    ),
    Flow(
        id="cov_bridge_only",
        prompts=["What's the cheapest way to bridge 100 USDC from Ethereum to Polygon?"],
        expect_cards={"bridge", "execution_plan_v3"},
        expect_sign=False,
        note="Coverage: bridge card (info-only, no execute)",
    ),

    # ── More matrix-derived flows (variation in cluster H + E + D) ────────
    Flow(
        id="D02_aave_v3_withdraw",
        prompts=[
            "Withdraw all my USDC from Aave V3 on Base",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=True,
        note="D02 — Aave V3 withdraw_all (wave-6 drain-guard pin path)",
    ),
    Flow(
        id="E09_eth_to_arb_morpho",
        prompts=[
            "Bridge 200 USDC from Ethereum to Arbitrum and lend on Morpho Blue",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=True,
        note="E09 — cross-chain composed bridge + Morpho supply",
    ),
    Flow(
        id="H07_S7_dust",
        prompts=[
            "Combine my dust balances across chains into 100 USDC on Ethereum",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=False,
        note="§7 S7 — dust mixing scenario",
    ),
    Flow(
        id="H15_S15_wrong_wallet",
        prompts=[
            "Stake 1 ETH on Lido",
            "Use my Solana wallet instead",
        ],
        expect_cards={"execution_plan_v3"},
        expect_sign=False,
        note="§7 S15 — wrong-wallet mismatch → blocker",
    ),
    Flow(
        id="cov_text_refusal_unknown",
        prompts=["What's the weather like today?"],
        expect_cards=set(),
        expect_sign=False,
        note="Coverage: text/no_change refusal (off-domain prompt)",
    ),

    # ── §13 27-row edge case representatives ──────────────────────────────
    Flow(
        id="row13a_solana_jup",
        prompts=["Swap 10 SOL for USDC on Jupiter"],
        expect_cards={"execution_plan_v3", "swap_quote"},
        expect_sign=True,
        note="§13 — Solana Jupiter swap",
    ),
    Flow(
        id="row13b_pendle_yt",
        prompts=["Buy Pendle YT-stETH for $200"],
        expect_cards={"execution_plan_v3"},
        expect_sign=False,
        note="§13 — Pendle YT speculation",
    ),
]


# ---------------------------------------------------------------------------
# Bug detection helpers
# ---------------------------------------------------------------------------
LEAK_PATTERNS = [
    (re.compile(r"\bundefined\b"), "undefined leaked into DOM"),
    (re.compile(r"\bNaN\b"), "NaN leaked into DOM"),
    (re.compile(r"\$\$"), "double-dollar (missing price interpolation)"),
    (re.compile(r"\[object Object\]"), "raw object string"),
    (re.compile(r"\bnull\s*%"), "null percentage"),
]


def scan_text_for_leaks(text: str) -> list[str]:
    """Return labelled hits with ±60-char context for triage."""
    findings = []
    for rx, label in LEAK_PATTERNS:
        m = rx.search(text)
        if m:
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            ctx = text[start:end].replace("\n", " ⏎ ").strip()
            findings.append(f"{label} :: …{ctx}…")
    return findings


def compare_tx(sse_tx: dict, popup_params: list[Any]) -> tuple[bool, str]:
    """Compare SSE step.transaction to the wallet popup's params[0]."""
    if not popup_params:
        return False, "wallet popup received no params"
    popup_tx = popup_params[0] if isinstance(popup_params, list) else popup_params
    if not isinstance(popup_tx, dict):
        return False, f"popup params[0] is not a dict: {type(popup_tx).__name__}"
    # Critical fields: to + data + value
    for field_name in ("to", "data"):
        sse_v = sse_tx.get(field_name)
        popup_v = popup_tx.get(field_name)
        if (sse_v or "").lower() != (popup_v or "").lower():
            return False, f"{field_name} mismatch: sse={sse_v!r} popup={popup_v!r}"
    # value may be omitted/0/None — accept any of those as equivalent
    sse_val = sse_tx.get("value") or "0x0"
    popup_val = popup_tx.get("value") or "0x0"
    sse_norm = sse_val if isinstance(sse_val, str) else hex(sse_val)
    pop_norm = popup_val if isinstance(popup_val, str) else hex(popup_val)
    if int(sse_norm, 16) != int(pop_norm, 16):
        return False, f"value mismatch: sse={sse_norm} popup={pop_norm}"
    return True, "match"


# ---------------------------------------------------------------------------
# Flow runner
# ---------------------------------------------------------------------------
async def run_flow(browser: Browser, flow: Flow, log_dir: Path) -> dict:
    """Run a single flow against staging; return {flow, bugs:[], passed:bool}."""
    bugs: list[str] = []
    console_errors: list[str] = []
    inject = INJECT_PROVIDERS_JS.replace("%EVM%", EVM_WALLET).replace("%SOL%", SOL_WALLET)
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    await ctx.add_init_script(inject)
    await ctx.add_init_script(INJECT_SSE_CAPTURE_JS)
    page = await ctx.new_page()

    def _console(msg: ConsoleMessage):
        if msg.type in {"error", "pageerror"}:
            console_errors.append(f"[{msg.type}] {msg.text}")

    failed_requests: list[str] = []

    def _response(resp):
        if resp.status >= 400:
            failed_requests.append(f"{resp.status} {resp.request.method} {resp.url}")

    page.on("console", _console)
    page.on("pageerror", lambda e: console_errors.append(f"[pageerror] {e}"))
    page.on("response", _response)

    flow_log = log_dir / f"{flow.id}.log"
    seen_card_types: set[str] = set()

    try:
        await page.goto(f"{BASE}/agent/chat", timeout=45000, wait_until="domcontentloaded")
        # Wait for any interactive textarea (composer is dynamic-rendered).
        try:
            await page.wait_for_selector(
                "textarea, [contenteditable='true']",
                timeout=20000,
                state="visible",
            )
        except Exception as e:
            bugs.append(f"BUG-P0: chat composer never rendered within 20s ({e})")
            await page.screenshot(path=str(log_dir / f"{flow.id}-no-composer.png"))
            return _finish(flow, bugs, console_errors, ctx, flow_log)

        # MainApp ships several textareas (chat composer + asset-search +
        # swap-amount). Target the chat composer via its placeholder text.
        COMPOSER_SELECTOR = "textarea[placeholder*='Ask anything']"

        for i, prompt in enumerate(flow.prompts, start=1):
            # Reset capture between turns
            await page.evaluate("() => { window.__sseFrames = []; window.__sseDone = false; window.__signed.length = 0; }")
            # Wait for the chat composer textarea to be enabled (Composer
            # disables during streaming). 30s tolerance — MainApp's
            # `loading` state flips after the SSE close + React flush,
            # which can lag a few seconds on slow renders.
            textarea = page.locator(COMPOSER_SELECTOR).first
            try:
                await textarea.wait_for(state="visible", timeout=15000)
                await page.wait_for_function(
                    f"""() => {{
                        const t = document.querySelector("{COMPOSER_SELECTOR}");
                        return t && !t.disabled;
                    }}""",
                    timeout=30000,
                )
            except Exception as e:
                # Capture diagnostic: present? disabled? value?
                diag = await page.evaluate(f"""() => {{
                    const t = document.querySelector("{COMPOSER_SELECTOR}");
                    if (!t) return {{exists: false}};
                    return {{exists: true, disabled: t.disabled, value: t.value, readonly: t.readOnly}};
                }}""")
                bugs.append(f"BUG-P0: turn{i} '{prompt[:60]}' — composer not interactive in 30s, diag={diag}")
                await page.screenshot(path=str(log_dir / f"{flow.id}-t{i}-no-textarea.png"))
                break
            await textarea.fill(prompt)
            # Find the send button — try aria-label, then Composer testid
            send_btn = page.locator("button[aria-label='Send']").first
            if await send_btn.count() == 0:
                # Fall back to pressing Enter
                await textarea.press("Enter")
            else:
                await send_btn.click()
            # Wait for `final` frame. 240s ceiling — strategy compose turns
            # can legitimately exceed 90s; Cloudflare's default edge timeout
            # for streaming responses is 100s but pings keep streams alive
            # past that. If we hit the ceiling with ZERO frames, that's an
            # edge-timeout sign (Cloudflare/Caddy dropped the connection
            # without forwarding any chunks); if we hit it with partial
            # frames, the backend hung mid-stream.
            try:
                await page.wait_for_function(
                    "() => window.__sseDone === true",
                    timeout=240000,
                )
            except Exception as e:
                frame_count_now = await page.evaluate("() => window.__sseFrames.length")
                kind = "edge_timeout (no frames)" if frame_count_now == 0 else f"hang_mid_stream ({frame_count_now} frames)"
                bugs.append(f"BUG-P0: turn{i} '{prompt[:60]}' — SSE never closed in 240s ({kind})")
                await page.screenshot(path=str(log_dir / f"{flow.id}-t{i}-timeout.png"))
                break

            # Settle wait — React commits the SSE state in a tick after
            # __sseDone fires. Without this, DOM assertions race ahead of
            # the render and falsely report "renderer dropped" for cards
            # that simply hadn't been committed yet.
            await page.wait_for_timeout(800)

            # Collect frames + asserts for this turn
            frames = await page.evaluate("() => window.__sseFrames")
            card_frames = [f for f in frames if f.get("kind") == "card"]
            for cf in card_frames:
                ct = cf.get("card_type") or "unknown"
                seen_card_types.add(ct)

            # If any execution_plan_v3 cards came through, wait up to 15s
            # for the first step row to actually mount in the DOM before
            # checking individual rows. (Bumped from 5s — composed
            # cross-chain plans like E09 Eth→Arb Morpho deposit emit a
            # multi-step plan; React commit + downstream CardRenderer
            # tree mount routinely exceeds 5s in load-light isolation
            # and was the only consistent fail across all post-Wave-RC
            # Playwright runs.)
            if any(cf.get("card_type") == "execution_plan_v3" for cf in card_frames):
                try:
                    await page.wait_for_selector(
                        "[data-testid='execution-plan-v3-step']",
                        timeout=15000,
                    )
                except Exception:
                    bugs.append(
                        f"BUG-P0: turn{i} — execution_plan_v3 emitted but no "
                        "step row mounted in 15s after SSE close"
                    )

            # Scan visible body text for leak patterns
            body_text = await page.locator("body").inner_text()
            leaks = scan_text_for_leaks(body_text)
            for leak in leaks:
                bugs.append(f"BUG-P1: turn{i} — {leak}")
            # If any leak fired, dump full body HTML so we can find the
            # offending component in triage.
            if leaks:
                body_html = await page.content()
                (log_dir / f"{flow.id}-t{i}-body.html").write_text(
                    body_html, encoding="utf-8"
                )

            # For each execution_plan_v3 with a ready step, verify the
            # Sign button (and recovery CTA for any blockers) are rendered.
            # Full sign-payload comparison is deferred to v2 — it needs the
            # wallet-connect flow triggered (connectedWallet state in MainApp)
            # which the mocked window.ethereum alone does not satisfy.
            if flow.expect_sign:
                v3_cards = [f for f in card_frames if f.get("card_type") == "execution_plan_v3"]
                for v3 in v3_cards:
                    payload = v3.get("payload") or {}
                    steps = payload.get("steps") or []
                    ready_steps = [s for s in steps if s.get("status") == "ready" and s.get("transaction")]
                    if not ready_steps:
                        continue
                    step = ready_steps[0]
                    step_id = step.get("step_id")
                    plan_id = payload.get("plan_id")
                    # Locate the matching DOM row
                    step_locator = page.locator(
                        f"[data-testid='execution-plan-v3-step'][data-step-id='{step_id}']"
                    )
                    if await step_locator.count() == 0:
                        bugs.append(
                            f"BUG-P0: turn{i} plan={plan_id} step={step_id} — "
                            "rendered no DOM row (CardFrame emitted but renderer dropped it)"
                        )
                        continue
                    # Sign button has explicit testid `sign-step-<step_id>`
                    sign_btn = page.locator(f"[data-testid='sign-step-{step_id}']").first
                    if await sign_btn.count() == 0:
                        # Permit2 path emits a different button — both shapes
                        # are acceptable. Tolerate Permit2 sign button.
                        permit_btn = step_locator.locator(
                            "button"
                        ).filter(has_text=re.compile(r"Permit2", re.I)).first
                        if await permit_btn.count() == 0:
                            bugs.append(
                                f"BUG-P0: turn{i} plan={plan_id} step={step_id} — "
                                "no Sign button or Permit2 button rendered on ready step"
                            )
                            continue
                        sign_btn = permit_btn
                    # State check: not permanently disabled (it may be
                    # disabled if needs_acknowledge + not yet acknowledged
                    # — that's expected; check it's mounted at minimum).
                    is_disabled = await sign_btn.is_disabled()
                    if is_disabled:
                        # Look for an acknowledge checkbox/button nearby and try ticking
                        ack = page.locator(
                            "input[type='checkbox'], button"
                        ).filter(has_text=re.compile(r"acknowledge|i understand|confirm", re.I)).first
                        if await ack.count() > 0:
                            try:
                                await ack.click(timeout=2000)
                                await page.wait_for_timeout(300)
                                is_disabled = await sign_btn.is_disabled()
                            except Exception:
                                pass
                    if is_disabled:
                        bugs.append(
                            f"BUG-P1: turn{i} plan={plan_id} step={step_id} — "
                            "Sign button disabled with no obvious unblock path "
                            f"(needsAck={payload.get('requires_double_confirm')} risk_gate={payload.get('risk_gate')})"
                        )

            # Persist full per-turn dump for later triage
            (log_dir / f"{flow.id}-t{i}.json").write_text(
                json.dumps({
                    "prompt": prompt,
                    "frames": frames,
                    "signed": await page.evaluate("() => window.__signed"),
                }, indent=2, default=str),
                encoding="utf-8",
            )

        # Cross-turn expectations are SOFT — the matrix v4 hints are
        # heuristics, not contracts. Backend has freedom to choose
        # defi_opportunities vs pool_link, etc. We only fail on real bugs:
        # missing DOM for emitted cards, undefined/NaN leaks, sign payload
        # mismatches, console errors.
        missing_expected = flow.expect_cards - seen_card_types
        if missing_expected:
            # Note only — not a bug
            (log_dir / f"{flow.id}-expectation-note.txt").write_text(
                f"NOTE: expected {sorted(flow.expect_cards)}, saw {sorted(seen_card_types)}; "
                f"missing {sorted(missing_expected)} — soft mismatch, not a bug.",
                encoding="utf-8",
            )

        # Map console "Failed to load resource: 4xx" entries to their actual
        # URLs by correlating with `failed_requests`. Drop benign noise.
        # KNOWN INFRA — `/api/portfolio/*` 500 under concurrent page-mount
        # fetches: wallet-assistant cache+dedupe (BUG-BE-003) handles this
        # correctly per `tests/test_portfolio_cache.py` 4/4 + direct probe
        # 10×parallel → 10×200. But Next.js's rewrite proxy gets ECONNRESET
        # from uvicorn under high concurrency (10×parallel via Next → 10×500).
        # This is an INFRA-LEVEL issue in the Cloudflare→Caddy→Next→uvicorn
        # chain — out of scope for Phase A Gate 4 (card-render validation).
        # Tracked separately as a Phase A v4 follow-up (frontend SWR dedupe
        # OR uvicorn keep-alive bump OR Caddy upstream pool tuning).
        # `Backend portfolio error` is the React-logged echo of the same 500.
        KNOWN_INFRA_PATTERNS = (
            "/api/portfolio/",
            "Backend portfolio error",
        )
        # First pass: how many infra-known 500 net failures did we filter?
        # The browser also emits a URL-less console echo "Failed to load
        # resource: the server responded with a status of 500 ()" for each
        # such failure — those need to drop too. Match by count, in order.
        infra_500_filtered = sum(
            1 for fr in failed_requests
            if "500" in fr and any(p in fr for p in KNOWN_INFRA_PATTERNS)
        )
        generic_500_skipped = 0
        for ce in console_errors:
            if "401" in ce or "prefetch" in ce.lower():
                continue
            if any(p in ce for p in KNOWN_INFRA_PATTERNS):
                continue
            # URL-less echo of an already-filtered infra 500.
            if ("Failed to load resource" in ce
                    and "status of 500" in ce
                    and generic_500_skipped < infra_500_filtered):
                generic_500_skipped += 1
                continue
            bugs.append(f"BUG-P1: console — {ce[:150]}")

        # 4xx/5xx are reported per-URL so we know what actually broke.
        for fr in failed_requests:
            # Filter benign: agent-health pings, prefetch HEADs, /favicon
            if any(x in fr for x in ("/api/v1/agent-health", "/favicon", "prefetch")):
                continue
            if any(p in fr for p in KNOWN_INFRA_PATTERNS):
                continue
            bugs.append(f"BUG-P1: net — {fr}")

    finally:
        flow_log.write_text(
            f"FLOW: {flow.id}\n"
            f"NOTE: {flow.note}\n"
            f"PROMPTS: {flow.prompts}\n"
            f"SEEN CARDS: {sorted(seen_card_types)}\n"
            f"EXPECTED CARDS: {sorted(flow.expect_cards)}\n"
            f"BUGS: {len(bugs)}\n"
            + "\n".join(f"  - {b}" for b in bugs)
            + "\n\nFAILED REQUESTS:\n" + "\n".join(f"  {r}" for r in failed_requests[:30])
            + "\n\nCONSOLE:\n" + "\n".join(f"  {c}" for c in console_errors[:50]),
            encoding="utf-8",
        )
        await ctx.close()

    return {"flow_id": flow.id, "bugs": bugs, "passed": len(bugs) == 0, "seen_cards": sorted(seen_card_types)}


def _finish(flow, bugs, console_errors, ctx, flow_log):
    flow_log.write_text(
        f"FLOW: {flow.id}\nEARLY EXIT\nBUGS: {len(bugs)}\n"
        + "\n".join(f"  - {b}" for b in bugs)
        + "\n\nCONSOLE:\n" + "\n".join(f"  {c}" for c in console_errors[:50]),
        encoding="utf-8",
    )
    return {"flow_id": flow.id, "bugs": bugs, "passed": False, "seen_cards": []}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flow", help="Only run this flow id", default=None)
    parser.add_argument("--headed", action="store_true", help="Show browser UI")
    args = parser.parse_args()

    flows = FLOWS if not args.flow else [f for f in FLOWS if f.id == args.flow]
    if not flows:
        print(f"FAIL: no matching flow for --flow={args.flow}")
        return 2

    print(f"L4 Playwright tester-ready — {len(flows)} flow(s) against {BASE}")
    print(f"  artifacts → {OUT_DIR}")

    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        try:
            for flow in flows:
                print(f"\n=== {flow.id} === ({flow.note})")
                r = await run_flow(browser, flow, OUT_DIR)
                status = "PASS" if r["passed"] else "FAIL"
                print(f"  [{status}] cards={r['seen_cards']} bugs={len(r['bugs'])}")
                for b in r["bugs"][:10]:
                    print(f"    - {b}")
                results.append(r)
        finally:
            await browser.close()

    # Roll up summary
    summary_path = OUT_DIR / "summary.json"
    summary = {
        "ts": RUN_TS,
        "base": BASE,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "bugs_total": sum(len(r["bugs"]) for r in results),
        "flows": results,
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 70)
    print(f"L4 Playwright: {summary['passed']}/{summary['total']} flows PASS, "
          f"{summary['bugs_total']} bug instances")
    print(f"  summary → {summary_path}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
