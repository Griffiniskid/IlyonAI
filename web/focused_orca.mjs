import { chromium } from "playwright";
const EVM = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e";
const SOL = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8";
function seedScript([evm, sol]) {
  localStorage.setItem("ap_wallet", evm); localStorage.setItem("ap_sol_wallet", sol);
  localStorage.setItem("ap_wallet_type", "metamask");
  localStorage.setItem("ap_phantom_wallet_context", JSON.stringify({ solanaAddress: sol, evmAddress: evm, evmChainId: 1 }));
  const acc = [evm];
  window.ethereum = { isMetaMask: true, selectedAddress: evm, chainId: "0x1", request: async ({ method }) => method.includes("ccount") ? acc : method === "eth_chainId" ? "0x1" : null, on: () => {}, removeListener: () => {} };
  const pk = { toString: () => sol };
  window.phantom = { solana: { isPhantom: true, publicKey: pk, isConnected: true, connect: async () => ({ publicKey: pk }), on: () => {}, removeListener: () => {} } };
  window.solana = window.phantom.solana;
}
const Q = process.argv[2] || "orca pools on solana";
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ bypassCSP: true });
await ctx.addInitScript(seedScript, [EVM, SOL]);
const p = await ctx.newPage();
const sse = [];
p.on("response", async (r) => { if (r.url().includes("/api/v1/agent")) { try { const t = await r.text(); for (const m of t.matchAll(/"pool_deeplink":"([^"]+)"/g)) sse.push(m[1]); } catch (e) {} } });
await p.goto("http://localhost:3000", { waitUntil: "domcontentloaded", timeout: 60000 });
await p.waitForTimeout(2500);
const chatBtn = p.getByText(/open ai chat/i).first();
if (await chatBtn.count().catch(() => 0)) await chatBtn.click().catch(() => {});
const input = p.getByPlaceholder(/ask anything/i).first();
await input.waitFor({ state: "visible", timeout: 40000 });
await input.click(); await input.fill(Q); await input.press("Enter");
// confirm the message was sent (our text appears in the thread)
await p.waitForFunction((q) => document.body.innerText.includes(q), Q, { timeout: 20000 }).catch(() => {});
// wait up to 150s for an opportunity card OR a pool_link card
let rendered = [];
try {
  await p.waitForSelector('[data-testid="defi-opp-open-pool"], a:has-text("Open pool"), a:has-text("Open on")', { timeout: 150000 });
  await p.waitForTimeout(2000);
  rendered = await p.$$eval('[data-testid="defi-opp-open-pool"], a:has-text("Open pool"), a:has-text("Open on")', (els) => els.map((e) => e.getAttribute("href")));
} catch (e) {
  console.log("RENDER TIMEOUT:", String(e).split("\n")[0]);
}
console.log("QUERY:", Q);
console.log("SSE pool_deeplinks (backend sent):", sse.length);
sse.slice(0, 8).forEach((u) => console.log("   BACKEND:", u.slice(0, 80)));
console.log("RENDERED Open-pool hrefs (what user clicks):", rendered.length);
rendered.slice(0, 8).forEach((u) => console.log("   RENDERED:", (u || "(none)").slice(0, 80)));
const dl = rendered.filter((u) => (u || "").includes("defillama")).length;
console.log("RENDERED on DefiLlama:", dl, "/", rendered.length);
await browser.close();
