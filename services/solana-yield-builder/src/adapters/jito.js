/**
 * Jito — SOL → JitoSOL via Jupiter universal swap.
 */
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");
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
  async build({ asset, amount, user, slippageBps = 50 }, { connection } = {}) {
    // Jupiter routes any SPL → JitoSOL in one tx — accept user-supplied
    // input asset (USDC/USDT/SOL/etc) instead of hardcoding SOL.
    const inputSym = (asset || "SOL").toUpperCase();
    const inputMint = resolveMint(inputSym) || SOL_MINT;
    const inputDecimals = decimalsFor(inputSym) || 9;
    const outputMint = resolveMint("JITOSOL");
    if (!outputMint) throw new Error("JitoSOL mint not registered.");
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
      const e = new Error(`Jito stake simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    return {
      transactions: [
        {
          b64: tx,
          summary: `Jito stake ${amount} ${inputSym} → JitoSOL (via Jupiter)`,
          description: `Routes ${amount} ${inputSym} into JitoSOL through Jupiter aggregated liquidity. JitoSOL captures MEV-boosted staking rewards.`,
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
