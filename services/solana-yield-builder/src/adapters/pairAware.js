/**
 * Pair-aware prep-swap helper.
 *
 * Replaces the legacy USDC/SOL-hardcoded prep logic. Given:
 *   - extra.underlying_tokens : array of base58 mints OR symbols for the pool
 *   - asset (user's input symbol)
 *
 * We pick the *missing* pool side as the swap target. Falls back to USDC/SOL
 * heuristic only when the pool's underlying tokens were not provided.
 *
 * BigInt math for the atomic-unit conversion so 18-decimal EVM-style precision
 * loss never appears on the Solana sidecar wire either.
 */
const { resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");

const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

function isBase58Mint(s) {
  return typeof s === "string" && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(s) && s.length >= 32 && s.length <= 44;
}

function symbolForMint(mint, fallback) {
  if (!mint) return fallback || null;
  if (mint === SOL_MINT) return "SOL";
  if (mint === USDC_MINT) return "USDC";
  return fallback || mint.slice(0, 6);
}

/**
 * Resolve pool side mints from extra.underlying_tokens.
 * Accepts an array containing either base58 mints, symbols, or a mix.
 * Returns { mints: [mintA, mintB], symbols: [symA, symB] }.
 */
function resolvePoolSides(extra) {
  const tokens = extra?.underlying_tokens || extra?.underlyingTokens || [];
  const mints = [];
  const symbols = [];
  for (const tok of tokens.slice(0, 2)) {
    if (!tok) {
      mints.push(null);
      symbols.push(null);
      continue;
    }
    if (isBase58Mint(tok)) {
      mints.push(tok);
      symbols.push(symbolForMint(tok));
    } else {
      const m = resolveMint(tok);
      mints.push(m || null);
      symbols.push(String(tok).toUpperCase());
    }
  }
  while (mints.length < 2) {
    mints.push(null);
    symbols.push(null);
  }
  return { mints, symbols };
}

/**
 * Decide the swap target mint for a single-sided LP zap.
 *
 * Logic:
 *  1. If user's input mint is one of the pool sides -> target = the OTHER side.
 *  2. Else if pool sides are known -> swap into pool's quote side (prefer USDC,
 *     else SOL, else side[0]); user still needs a follow-up swap, but at least
 *     they end up holding a real pool token.
 *  3. Else (no pool data) -> fall back to USDC/SOL heuristic with a warning.
 *
 * Returns { inputMint, targetMint, inputSym, targetSym, mode, warnings }.
 *   mode = "pair-aware" | "quote-only" | "fallback"
 */
function planPrepSwap({ asset, extra }) {
  const warnings = [];
  const inAsset = (asset || "SOL").toUpperCase();
  const inputMint = resolveMint(inAsset) || SOL_MINT;
  const { mints, symbols } = resolvePoolSides(extra);
  const [m0, m1] = mints;
  const [s0, s1] = symbols;

  // Case 1: user already holds one pool side -> swap into the OTHER side.
  if (m0 && m1 && (inputMint === m0 || inputMint === m1)) {
    const targetMint = inputMint === m0 ? m1 : m0;
    const targetSym = inputMint === m0 ? (s1 || symbolForMint(targetMint)) : (s0 || symbolForMint(targetMint));
    return {
      inputMint,
      targetMint,
      inputSym: inAsset,
      targetSym,
      mode: "pair-aware",
      warnings,
    };
  }

  // Case 2: pool sides known but user holds neither. Route into the side
  // that's more likely to have Jupiter liquidity (prefer SOL > USDC > side0).
  if (m0 || m1) {
    let targetMint = null;
    let targetSym = null;
    for (const [m, sym] of [[m0, s0], [m1, s1]]) {
      if (!m) continue;
      if (m === SOL_MINT) { targetMint = m; targetSym = "SOL"; break; }
      if (m === USDC_MINT) { targetMint = m; targetSym = "USDC"; }
      else if (!targetMint) { targetMint = m; targetSym = sym; }
    }
    warnings.push(`Input ${inAsset} is not in the pool pair (${s0 || "?"}/${s1 || "?"}). Routing into ${targetSym} first; finish the second swap on the protocol app.`);
    return {
      inputMint,
      targetMint: targetMint || SOL_MINT,
      inputSym: inAsset,
      targetSym: targetSym || "SOL",
      mode: "quote-only",
      warnings,
    };
  }

  // Case 3: no pool data — fall back to USDC/SOL heuristic.
  const inputIsUsdc = inputMint === USDC_MINT;
  const targetMint = inputIsUsdc ? SOL_MINT : USDC_MINT;
  const targetSym = inputIsUsdc ? "SOL" : "USDC";
  warnings.push("Pool sides unknown — using USDC/SOL fallback heuristic. Verify pool tokens on the protocol app before finalizing.");
  return {
    inputMint,
    targetMint,
    inputSym: inputIsUsdc ? "USDC" : inAsset,
    targetSym,
    mode: "fallback",
    warnings,
  };
}

module.exports = { planPrepSwap, resolvePoolSides, isBase58Mint, symbolForMint, USDC_MINT };
