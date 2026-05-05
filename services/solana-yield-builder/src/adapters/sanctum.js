/**
 * Sanctum INF — route any input → INF via Jupiter (INF is a Jupiter-quoted
 * SPL mint).
 */
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");

module.exports = {
  aliases: ["sanctum-infinity"],
  async quote({ asset, amount }) {
    return {
      expectedAmountOut: amount,
      receiptToken: "INF",
      apy: null,
      fees: { protocol: "Jupiter routing", network: "0.000005 SOL" },
    };
  },
  async build({ asset, amount, user, slippageBps = 50 }) {
    const inputMint = resolveMint(asset || "SOL") || SOL_MINT;
    const outputMint = resolveMint("INF");
    if (!outputMint) throw new Error("INF mint not registered.");
    const { tx } = await buildSwap({
      inputMint,
      outputMint,
      amount,
      user,
      slippageBps,
      decimals: decimalsFor(asset || "SOL"),
    });
    return {
      transactions: [
        {
          b64: tx,
          summary: `Sanctum route ${asset || "SOL"} → INF (via Jupiter)`,
          description: `Routes ${amount} ${asset || "SOL"} into INF LST shares through Jupiter aggregated liquidity.`,
          receiptToken: "INF",
          feeUsd: 0.01,
          durationS: 25,
          warnings: ["INF is the Sanctum Infinity LST aggregator share token."],
        },
      ],
    };
  },
};
