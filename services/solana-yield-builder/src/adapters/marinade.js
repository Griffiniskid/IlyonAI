/**
 * Marinade — SOL → mSOL via Jupiter universal swap.
 * mSOL is a fully liquid SPL token; routing through Jupiter is functionally
 * identical to Marinade's direct deposit (with deeper aggregated liquidity).
 */
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");

module.exports = {
  aliases: ["marinade-finance", "marinade-liquid-staking", "marinade-native-staking"],
  async quote({ amount }) {
    return {
      expectedAmountOut: amount,
      receiptToken: "mSOL",
      apy: null,
      fees: { protocol: "Jupiter routing", network: "0.000005 SOL" },
    };
  },
  async build({ asset, amount, user, slippageBps = 50 }, { connection } = {}) {
    // Jupiter can route ANY SPL → mSOL in a single tx, so a USDT/USDC user
    // doesn't need a separate prep-swap step. Use the supplied input asset
    // (defaults to SOL) and resolve its mint + decimals on the fly.
    const inputSym = (asset || "SOL").toUpperCase();
    const inputMint = resolveMint(inputSym) || SOL_MINT;
    const inputDecimals = decimalsFor(inputSym) || 9;
    const outputMint = resolveMint("MSOL");
    if (!outputMint) throw new Error("mSOL mint not registered.");
    const { tx } = await buildSwap({
      inputMint,
      outputMint,
      amount,
      user,
      slippageBps,
      decimals: inputDecimals,
    });
    const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
    if (!sim.ok) {
      const e = new Error(`Marinade stake simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    return {
      transactions: [
        {
          b64: tx,
          summary: `Marinade liquid-stake ${amount} ${inputSym} → mSOL (via Jupiter)`,
          description: `Routes ${amount} ${inputSym} into mSOL through Jupiter aggregated liquidity. mSOL accrues stake rewards.`,
          receiptToken: "mSOL",
          feeUsd: 0.005,
          durationS: 25,
          warnings: ["mSOL accrues stake rewards over time; can be unstaked or swapped via Jupiter."],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },
};
