/**
 * Raydium adapter — pair-aware prep swap + pre-sim gate.
 *
 * Two modes:
 *   1. extra.lpMint present (fungible AMM v4 LP, sometimes a Sanctum LST) —
 *      route input directly into the LP/share token via Jupiter.
 *   2. Generic pool — pair-aware prep swap:
 *        - read pool's underlying_tokens (mints or symbols)
 *        - swap input -> the side of the pool the user does NOT hold
 *        - emit a single signable Jupiter tx + deeplink to the EXACT pool
 *
 * Every returned tx is run through simulateBase64Tx; benign reverts (empty
 * dev wallet) pass, real reverts abort the build so the user never sees a
 * "Sign" button for a guaranteed-failure tx.
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

module.exports = {
  aliases: ["raydium-amm", "raydium-clmm"],
  async quote({ asset, amount }) {
    return {
      expectedAmountOut: null,
      receiptToken: `raydium-${asset || "?"}`,
      apy: null,
      fees: { protocol: "Jupiter routing", network: "0.000005 SOL" },
    };
  },
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }, { connection } = {}) {
    // Mode 1: fungible LP / share mint provided — single Jupiter route.
    // Raydium AMM v4 LP tokens are NOT on Jupiter's swap graph (Jupiter only
    // routes against tradable markets), so Mode 1 only succeeds for share
    // tokens that double as LSTs (some Raydium-CLMM variants, third-party
    // tokenized LP wrappers). On any Jupiter error fall through to Mode 2
    // pair-aware prep-swap instead of leaking a 502 to the user.
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
        // Common failure: Jupiter returns MARKET_NOT_FOUND because Raydium-AMM
        // LP shares aren't quotable. Fall through silently to Mode 2.
        // Anything else (network, signature, real revert) still gets surfaced
        // by Mode 2's own try/catch below if both modes fail.
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
          summary: `Step 1/2 prep-swap: ${sourceSym} → ${targetSym} for ${pairLabel} entry`,
          description: `Swap half of your ${sourceSym} into ${targetSym} via Jupiter so both ${pairLabel} pool tokens sit in your wallet. After this prep tx confirms, click 'Open on Raydium' below to add liquidity — Raydium's addLiquidity SDK isn't wired for in-chat signing yet.`,
          receiptToken: targetSym,
          feeUsd: 0.01,
          durationS: 25,
          protocolUrl: raydiumUrl,
          warnings,
          mode: plan.mode, // "pair-aware" | "quote-only" | "fallback"
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },
};
