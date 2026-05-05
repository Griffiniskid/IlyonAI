/**
 * Jito — SOL → JitoSOL via Jupiter universal swap.
 */
const { buildSwap, resolveMint, SOL_MINT } = require("./jupiter");

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
  async build({ amount, user, slippageBps = 50 }) {
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
        },
      ],
    };
  },
};
