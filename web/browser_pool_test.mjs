// Real-browser test: drive the live app like a user, read the ACTUAL rendered
// "Open pool" hrefs. FRESH context per query (no chat persistence carryover).
import { chromium } from "playwright";

const EVM = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e";
const SOL = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8";

const QUERIES = [
  "orca pools on solana",
  "raydium pools on solana",
  "uniswap v3 pools on ethereum",
  "pancakeswap pools on bsc",
  "curve pools on ethereum",
  "aave lending on ethereum",
];

function classify(url) {
  if (!url) return "NONE";
  const u = url.toLowerCase();
  if (u.includes("defillama.com")) return "DEFILLAMA";
  if (/[?&](search|query|textsearch)=/.test(u)) return "LIST";
  if (/\/(pools|liquidity|pool|dlmm|markets)\/?$/.test(u)) return "LIST";
  if (u.includes("reserve-overview") || u.includes("pool_id=")) return "EXACT";
  if (/0x[a-f0-9]{40}/.test(u) || /\/[1-9A-HJ-NP-Za-km-z]{32,44}/.test(url)) return "EXACT";
  return "OTHER";
}

function seedScript([evm, sol]) {
  localStorage.setItem("ap_wallet", evm);
  localStorage.setItem("ap_sol_wallet", sol);
  localStorage.setItem("ap_wallet_type", "metamask");
  localStorage.setItem("ap_phantom_wallet_context", JSON.stringify({ solanaAddress: sol, evmAddress: evm, evmChainId: 1 }));
  const acc = [evm];
  window.ethereum = { isMetaMask: true, selectedAddress: evm, chainId: "0x1",
    request: async ({ method }) => method.includes("ccount") ? acc : method === "eth_chainId" ? "0x1" : method === "personal_sign" ? "0x" + "11".repeat(65) : null,
    on: () => {}, removeListener: () => {} };
  const pk = { toString: () => sol };
  window.phantom = { solana: { isPhantom: true, publicKey: pk, isConnected: true, connect: async () => ({ publicKey: pk }), on: () => {}, removeListener: () => {} } };
  window.solana = window.phantom.solana;
}

const browser = await chromium.launch({ headless: true });
const results = [];
for (const q of QUERIES) {
  const ctx = await browser.newContext({ bypassCSP: true });   // FRESH per query
  await ctx.addInitScript(seedScript, [EVM, SOL]);
  const p = await ctx.newPage();
  let sseUrls = [];
  p.on("response", async (r) => {
    if (r.url().includes("/api/v1/agent")) {
      try { const t = await r.text(); for (const m of t.matchAll(/"pool_deeplink":"([^"]+)"/g)) sseUrls.push(m[1]); } catch (e) {}
    }
  });
  try {
    await p.goto("http://localhost:3000", { waitUntil: "domcontentloaded", timeout: 60000 });
    await p.waitForTimeout(2000);
    const chatBtn = p.getByText(/open ai chat/i).first();
    if (await chatBtn.count().catch(() => 0)) await chatBtn.click().catch(() => {});
    else await p.getByRole("link", { name: /^Chat$/ }).first().click().catch(() => {});
    const input = p.getByPlaceholder(/ask anything/i).first();
    await input.waitFor({ timeout: 40000 });
    await input.click();
    await input.fill(q);
    await input.press("Enter");
    await p.waitForSelector('[data-testid="defi-opp-open-pool"], a:has-text("Open pool")', { timeout: 90000 });
    await p.waitForTimeout(1500);
    const links = await p.$$eval('[data-testid="defi-opp-open-pool"], a:has-text("Open pool")',
      (els) => els.map((e) => e.getAttribute("href")));
    results.push({ q, ok: true, links, sseUrls });
  } catch (e) {
    const body = (await p.locator("body").innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 200);
    results.push({ q, ok: false, err: String(e).split("\n")[0].slice(0, 80), bodySnippet: body, sseUrls });
  } finally {
    await ctx.close();
  }
}
await browser.close();

console.log("=".repeat(90));
const counts = {};
for (const r of results) {
  console.log("\nQUERY:", r.q, r.ok ? "" : "(FAILED: " + r.err + ")");
  if (!r.ok) { console.log("  SSE seen:", r.sseUrls.length, "| body:", r.bodySnippet); continue; }
  for (const href of r.links) {
    const c = classify(href);
    counts[c] = (counts[c] || 0) + 1;
    console.log("  [" + c + "]", (href || "(none)").slice(0, 74));
  }
}
console.log("\n" + "=".repeat(90));
console.log("RENDERED (what the user actually clicks):", JSON.stringify(counts));
console.log("DefiLlama-on-OpenPool (want 0):", counts["DEFILLAMA"] || 0);
