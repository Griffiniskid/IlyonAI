/**
 * Meteora — DLMM/Dynamic vaults. Same prep pattern as Orca: Jupiter-route
 * input into the pool's quote token (or directly into a Dynamic Vault share
 * mint when extra.shareMint is provided).
 */
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");

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
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }) {
    if (extra.shareMint) {
      const inputMint = resolveMint(asset || "USDC") || resolveMint("USDC");
      const { tx } = await buildSwap({
        inputMint,
        outputMint: extra.shareMint,
        amount,
        user,
        slippageBps,
        decimals: decimalsFor(asset || "USDC"),
      });
      return {
        transactions: [
          {
            b64: tx,
            summary: `Meteora vault entry: ${asset || "USDC"} → vault share`,
            description: "Direct Jupiter-routed entry into the Meteora Dynamic Vault share token.",
            receiptToken: "meteora-vault-share",
            feeUsd: 0.01,
            durationS: 25,
            warnings: [],
          },
        ],
      };
    }
    const inputMint = resolveMint(asset || "SOL") || SOL_MINT;
    const usdcMint = resolveMint("USDC");
    const half = (parseFloat(amount || "0") / 2).toString();
    const { tx } = await buildSwap({
      inputMint,
      outputMint: usdcMint,
      amount: half,
      user,
      slippageBps,
      decimals: decimalsFor(asset || "SOL"),
    });
    return {
      transactions: [
        {
          b64: tx,
          summary: `Meteora prep: convert half of ${asset || "SOL"} → USDC for DLMM entry`,
          description: "Stages capital so opening the Meteora DLMM position is one click in the Meteora app.",
          receiptToken: "USDC",
          feeUsd: 0.01,
          durationS: 25,
          warnings: ["DLMM bin entry runs in the Meteora app once this prep swap confirms."],
        },
      ],
    };
  },
};
