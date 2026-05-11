/**
 * Meteora — DLMM and Dynamic Vault adapter. Pair-aware prep swap with pre-sim
 * gate, and direct vault-share route when extra.shareMint is provided.
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

module.exports = {
  aliases: ["meteora-dlmm", "meteora-vault"],
  async quote({ asset, amount }) {
    return {
      expectedAmountOut: null,
      receiptToken: `meteora-${asset || "?"}`,
      apy: null,
      fees: { protocol: "Jupiter routing", network: "0.000005 SOL" },
    };
  },
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }, { connection } = {}) {
    if (extra.shareMint) {
      const inputSym = (asset || "USDC").toUpperCase();
      const inputMint = resolveMint(inputSym) || resolveMint("USDC");
      const { tx } = await buildSwap({
        inputMint,
        outputMint: extra.shareMint,
        amount,
        user,
        slippageBps,
        decimals: decimalsFor(inputSym),
      });
      const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
      if (!sim.ok) {
        const e = new Error(`Meteora vault-share simulation failed: ${sim.errStr || "unknown"}`);
        e.simulation = sim;
        throw e;
      }
      return {
        transactions: [
          {
            b64: tx,
            summary: `Meteora vault entry: ${inputSym} → vault share`,
            description: "Direct Jupiter-routed entry into the Meteora Dynamic Vault share token.",
            receiptToken: "meteora-vault-share",
            feeUsd: 0.01,
            durationS: 25,
            warnings: [],
            simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
          },
        ],
      };
    }

    // Pair-aware prep for DLMM pools.
    const plan = planPrepSwap({ asset, extra });
    const sourceSym = plan.inputSym;
    const targetSym = plan.targetSym;
    const inputMint = plan.inputMint;
    const targetMint = plan.targetMint;

    const half = halfAmount(amount);
    if (half === "0") {
      const e = new Error(`Meteora prep: amount '${amount}' too small after half-split`);
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
      const e = new Error(`Meteora prep-swap simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }

    const tokens = extra.underlying_tokens || extra.underlyingTokens || [];
    const meteoraUrl =
      tokens.length >= 2
        ? `https://app.meteora.ag/dlmm/${tokens[0]}-${tokens[1]}`
        : "https://app.meteora.ag/dlmm";
    const pairLabel = (extra.pool_symbol || extra.poolSymbol || `${sourceSym}-${targetSym}`).toUpperCase();

    return {
      transactions: [
        {
          b64: tx,
          summary: `Meteora prep: convert half of ${sourceSym} → ${targetSym} for DLMM ${pairLabel}`,
          description: `Stages capital for the Meteora DLMM ${pairLabel} pool by routing half of ${sourceSym} → ${targetSym}. Open the DLMM position on Meteora once this swap confirms: ${meteoraUrl}`,
          receiptToken: targetSym,
          feeUsd: 0.01,
          durationS: 25,
          protocolUrl: meteoraUrl,
          warnings: [
            `DLMM bin entry for ${pairLabel} runs on Meteora: ${meteoraUrl}`,
            ...plan.warnings,
          ],
          mode: plan.mode,
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },
};
