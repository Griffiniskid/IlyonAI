/**
 * Universal Jupiter swap helper.
 *
 * Most Solana yield protocols mint a tradable LST/share token (mSOL, JitoSOL,
 * INF, JLP, kUSDC, b-SOL, hSOL, …). Jupiter quotes any tokenIn → that token,
 * returning a signable VersionedTransaction — that's the "low-effort sign one
 * tx" execution path the user asked for.
 *
 * Public API:
 *   GET  https://quote-api.jup.ag/v6/quote?inputMint=...&outputMint=...&amount=...
 *   POST https://quote-api.jup.ag/v6/swap
 */
const fetch = require("node-fetch").default || require("node-fetch");

// Jupiter free public API (lite-api). Falls back to legacy v6 host if needed.
const JUP_BASE = process.env.JUPITER_API_BASE || "https://lite-api.jup.ag/swap/v1";
const QUOTE_URL = `${JUP_BASE}/quote`;
const SWAP_URL = `${JUP_BASE}/swap`;

const SOL_MINT = "So11111111111111111111111111111111111111112";

const KNOWN_MINTS = {
  SOL: SOL_MINT,
  WSOL: SOL_MINT,
  USDC: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  USDT: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
  MSOL: "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
  JITOSOL: "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
  BSOL: "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",
  INF: "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm",
  JLP: "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4",
  KUSDC: "5e4z5q7Tav7p2BfL3PFPVoZpdKvNPPmGuBWrnNZ9KVKr", // placeholder; resolved per-protocol
};

async function buildSwap({ inputMint, outputMint, amount, user, slippageBps = 50, decimals = 9 }) {
  const atoms = BigInt(Math.floor(parseFloat(amount || "0") * 10 ** decimals));
  if (atoms <= 0n) throw new Error("amount must be > 0");
  const quoteUrl = `${QUOTE_URL}?inputMint=${inputMint}&outputMint=${outputMint}&amount=${atoms.toString()}&slippageBps=${slippageBps}`;
  const quoteResp = await fetch(quoteUrl);
  if (!quoteResp.ok) {
    throw new Error(`Jupiter quote returned ${quoteResp.status}`);
  }
  const quote = await quoteResp.json();
  const swapResp = await fetch(SWAP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      quoteResponse: quote,
      userPublicKey: user,
      wrapAndUnwrapSol: true,
      dynamicComputeUnitLimit: true,
    }),
  });
  if (!swapResp.ok) {
    const text = await swapResp.text();
    throw new Error(`Jupiter swap returned ${swapResp.status}: ${text.slice(0, 200)}`);
  }
  const swap = await swapResp.json();
  if (!swap?.swapTransaction) throw new Error("Jupiter response missing swapTransaction.");
  return { tx: swap.swapTransaction, quote };
}

function resolveMint(symbol) {
  if (!symbol) return null;
  return KNOWN_MINTS[symbol.toUpperCase()] || null;
}

function decimalsFor(symbol) {
  if (!symbol) return 9;
  const upper = symbol.toUpperCase();
  if (upper === "USDC" || upper === "USDT") return 6;
  return 9;
}

module.exports = { buildSwap, resolveMint, decimalsFor, SOL_MINT, KNOWN_MINTS };
