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

/**
 * Convert a human-readable decimal string to atomic units using BigInt math.
 * Avoids the Math.floor(parseFloat * 10**decimals) precision loss that bites
 * 18-decimal EVM-style tokens AND sub-lamport SOL fractions.
 *   "0.1"     × 9  -> 100000000n
 *   "1.234"   × 6  -> 1234000n
 *   "0.0001"  × 18 -> 100000000000000n
 *   "all" / empty -> 0n (caller must override)
 */
function humanToAtoms(amount, decimals) {
  if (amount === null || amount === undefined) return 0n;
  const s = String(amount).trim();
  if (!s || s === "all") return 0n;
  if (!/^[0-9]*\.?[0-9]*$/.test(s)) {
    throw new Error(`invalid amount: ${amount}`);
  }
  const [whole = "0", frac = ""] = s.split(".");
  const fracPadded = (frac + "0".repeat(decimals)).slice(0, decimals);
  const combined = (whole + fracPadded).replace(/^0+/, "") || "0";
  return BigInt(combined);
}

async function buildSwap({ inputMint, outputMint, amount, user, slippageBps = 50, decimals = 9 }) {
  // BigInt atom conversion — no float, no precision loss on 18-dec / dust.
  let atoms;
  try {
    atoms = humanToAtoms(amount, decimals);
  } catch (err) {
    throw new Error(`buildSwap atom conv: ${err.message}`);
  }
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

/**
 * Decimal-safe halving for prep-swap "swap half the input" flows.
 * "1" -> "0.5"; "0.000001" -> "0.0000005"; rejects malformed input.
 */
function halfAmount(amount) {
  const s = String(amount || "0").trim();
  if (!/^[0-9]*\.?[0-9]*$/.test(s) || s === "" || s === ".") return "0";
  // Use a fixed 9-dp ceiling on the decimal portion; matches Solana mint
  // precision and is plenty for the prep-swap UX.
  const atoms = humanToAtoms(s, 18);
  const half = atoms / 2n;
  if (half === 0n) return "0";
  const str = half.toString().padStart(19, "0");
  const whole = str.slice(0, -18).replace(/^0+/, "") || "0";
  const frac = str.slice(-18).replace(/0+$/, "");
  return frac ? `${whole}.${frac}` : whole;
}

module.exports = { buildSwap, resolveMint, decimalsFor, humanToAtoms, halfAmount, SOL_MINT, KNOWN_MINTS };
