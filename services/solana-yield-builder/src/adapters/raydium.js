/**
 * Raydium — AMM v4 fungible LP tokens are tradable on Jupiter; CLMM positions
 * need the SDK. Same prep + LP-mint pattern as Orca/Meteora.
 */
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");

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
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }) {
    if (extra.lpMint) {
      const inputMint = resolveMint(asset || "USDC") || resolveMint("USDC");
      const { tx } = await buildSwap({
        inputMint,
        outputMint: extra.lpMint,
        amount,
        user,
        slippageBps,
        decimals: decimalsFor(asset || "USDC"),
      });
      return {
        transactions: [
          {
            b64: tx,
            summary: `Raydium AMM v4 LP entry: ${asset || "USDC"} → LP ${extra.lpMint.slice(0, 8)}…`,
            description: "Direct Jupiter-routed entry into the Raydium AMM LP token.",
            receiptToken: "raydium-lp",
            feeUsd: 0.01,
            durationS: 25,
            warnings: [],
          },
        ],
      };
    }
    const inAsset = (asset || "SOL").toUpperCase();
    const inputMint = resolveMint(inAsset) || SOL_MINT;
    const usdcMint = resolveMint("USDC");
    if (inputMint === usdcMint) {
      throw new Error(
        "Raydium build needs `extra.lpMint` (LP token mint) when source asset already is USDC. " +
        "Resolve it from DefiLlama pool metadata before calling /build."
      );
    }
    const half = (parseFloat(amount || "0") / 2).toString();
    const { tx } = await buildSwap({
      inputMint,
      outputMint: usdcMint,
      amount: half,
      user,
      slippageBps,
      decimals: decimalsFor(inAsset),
    });
    return {
      transactions: [
        {
          b64: tx,
          summary: `Raydium prep: convert half of ${asset || "SOL"} → USDC for LP entry`,
          description: "Stages capital for adding to a Raydium AMM v4 or CLMM pool.",
          receiptToken: "USDC",
          feeUsd: 0.01,
          durationS: 25,
          warnings: ["Final LP add for Raydium runs in the Raydium app once this prep swap confirms."],
        },
      ],
    };
  },
};
