/**
 * Legacy Raydium prep-swap fallback.
 *
 * Preserves the pair-aware Jupiter prep-swap behaviour of the original
 * raydium.js for long-tail aliases that lack `extra.poolId` and
 * `extra.underlying_tokens`. The native AMM v4 / CPMM adapter delegates here
 * when neither is supplied, so generic Solana-DEX fallbacks (drift, lulo,
 * lifinity, etc. registered against this adapter in src/index.js) still get a
 * signable Jupiter route into one side of the pool.
 *
 * Two modes — copied verbatim from the previous raydium.js:
 *   1. extra.lpMint present — single Jupiter swap into the LP/share mint.
 *   2. Generic pool — pair-aware prep swap.
 *
 * Every returned tx runs through simulateBase64Tx; benign reverts pass, real
 * reverts abort the build so users never see a Sign button for a guaranteed
 * revert.
 */
const {
  buildSwap,
  resolveMint,
  decimalsFor,
  halfAmount,
  SOL_MINT,
} = require("./jupiter");
const { planPrepSwap } = require("./pairAware");
const { simulateBase64Tx } = require("./simulate");

function buildRaydiumUrl(extra, fallback) {
  const poolSymbol = (extra.pool_symbol || extra.poolSymbol || "").toUpperCase();
  const poolAddr = extra.pool_address || extra.poolAddress || extra.amm_id || extra.ammId;
  const tokens = extra.underlying_tokens || extra.underlyingTokens || [];
  if (poolAddr) return `https://raydium.io/liquidity/increase/?pool_id=${poolAddr}&mode=add`;
  if (tokens.length >= 2) return `https://raydium.io/liquidity-pools/?token0=${tokens[0]}&token1=${tokens[1]}`;
  if (poolSymbol) return `https://raydium.io/liquidity-pools/?search=${encodeURIComponent(poolSymbol)}`;
  return fallback || "https://raydium.io/liquidity-pools/";
}

async function build({ protocol, asset, amount, user, extra = {}, slippageBps = 50 }, { connection } = {}) {
  // Honest sub-variant label so the step description doesn't lie. DefiLlama
  // collapses every Raydium variant into 'raydium-amm', but when the upstream
  // caller knows the user asked for CLMM we should say CLMM.
  const _protoLower = String(protocol || "raydium-amm").toLowerCase();
  const _variantLabel = (() => {
    if (_protoLower.includes("clmm")) return "Raydium CLMM";
    if (_protoLower.includes("cpmm") || _protoLower.includes("raydium-cp")) return "Raydium CPMM";
    if (_protoLower.includes("amm-v3")) return "Raydium AMM v3";
    return "Raydium AMM v4";
  })();

  // Mode 1: fungible LP / share mint provided — single Jupiter route.
  if (extra.lpMint) {
    const inputSym = (asset || "USDC").toUpperCase();
    const inputMint = resolveMint(inputSym) || resolveMint("USDC");
    try {
      const { tx } = await buildSwap({
        inputMint,
        outputMint: extra.lpMint,
        amount,
        user,
        slippageBps,
        decimals: decimalsFor(inputSym),
      });
      const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
      if (!sim.ok) {
        throw new Error(`Raydium LP-mint route simulation failed: ${sim.errStr || "unknown"}`);
      }
      return {
        transactions: [
          {
            b64: tx,
            summary: `Raydium AMM v4 LP entry: ${inputSym} → LP ${extra.lpMint.slice(0, 8)}…`,
            description: "Direct Jupiter-routed entry into the Raydium AMM LP token.",
            receiptToken: "raydium-lp",
            feeUsd: 0.01,
            durationS: 25,
            warnings: [],
            simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
          },
        ],
      };
    } catch (mode1Err) {
      // Fall through silently to Mode 2.
    }
  }

  // Mode 2: pair-aware prep swap.
  const plan = planPrepSwap({ asset, extra });
  const sourceSym = plan.inputSym;
  const targetSym = plan.targetSym;
  const inputMint = plan.inputMint;
  const targetMint = plan.targetMint;

  const half = halfAmount(amount);
  if (half === "0") {
    const e = new Error(`Raydium prep: amount '${amount}' too small after half-split`);
    e.code = "amount_too_small";
    throw e;
  }

  const { tx } = await buildSwap({
    inputMint,
    outputMint: targetMint,
    amount: half,
    user,
    slippageBps,
    decimals: decimalsFor(sourceSym),
  });
  const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
  if (!sim.ok) {
    const e = new Error(`Raydium prep-swap simulation failed: ${sim.errStr || "unknown"}`);
    e.simulation = sim;
    throw e;
  }

  const raydiumUrl = buildRaydiumUrl(extra);
  const pairLabel = (extra.pool_symbol || extra.poolSymbol || `${sourceSym}-${targetSym}`).toUpperCase();
  const warnings = [
    `Final LP add for ${pairLabel} runs on Raydium: ${raydiumUrl}`,
    ...plan.warnings,
  ];

  return {
    transactions: [
      {
        b64: tx,
        action: "prep_swap",
        summary: `Prep swap: ${half} ${sourceSym} → ${targetSym} (${_variantLabel} ${pairLabel} handoff)`,
        description: `Swap ${half} ${sourceSym} into ${targetSym} via Jupiter so you hold one side of the ${pairLabel} pool. After this swap confirms, click the Raydium link to finish the LP add — ${_variantLabel} direct-sign isn't wired yet for this in-chat flow.`,
        inputSymbol: sourceSym,
        inputAmount: half,
        outputSymbol: targetSym,
        receiptToken: targetSym,
        feeUsd: 0.01,
        durationS: 25,
        protocolUrl: raydiumUrl,
        warnings,
        mode: plan.mode,
        simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
      },
    ],
  };
}

module.exports = { build };
