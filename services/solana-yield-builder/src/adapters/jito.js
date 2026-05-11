/**
 * Jito — SOL → JitoSOL via Jupiter universal swap.
 */
const { buildSwap, resolveMint, SOL_MINT } = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");

module.exports = {
  aliases: ["jito-liquid-staking", "jitosol"],
  async quote({ amount }) {
    return {
      expectedAmountOut: amount,
      receiptToken: "JitoSOL",
      apy: null,
      fees: { protocol: "Jupiter routing", network: "0.000005 SOL" },
    };
  },
  async build({ amount, user, slippageBps = 50 }, { connection } = {}) {
    const outputMint = resolveMint("JITOSOL");
    if (!outputMint) throw new Error("JitoSOL mint not registered.");
    const { tx } = await buildSwap({
      inputMint: SOL_MINT,
      outputMint,
      amount,
      user,
      slippageBps,
      decimals: 9,
    });
    const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
    if (!sim.ok) {
      const e = new Error(`Jito stake simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    return {
      transactions: [
        {
          b64: tx,
          summary: `Jito stake ${amount} SOL → JitoSOL (via Jupiter)`,
          description: `Routes ${amount} SOL into JitoSOL through Jupiter aggregated liquidity. JitoSOL captures MEV-boosted staking rewards.`,
          receiptToken: "JitoSOL",
          feeUsd: 0.005,
          durationS: 25,
          warnings: ["JitoSOL captures MEV rewards; can be unstaked or swapped via Jupiter."],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },
};
