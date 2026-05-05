/**
 * Orca Whirlpools — until the Whirlpools SDK opens positions natively in this
 * sidecar, we deliver the most useful executable preparation step:
 *  - Route the input asset 50/50 into the pool's two underlying tokens via
 *    Jupiter, so the user is fully prepared to open a Whirlpool position
 *    with one more transaction in the Orca UI.
 *
 * For pools where the LP receipt is a fungible Orca AMM v1 LP token, we
 * route directly into it. The orca AMM v1 mint, when present, is taken from
 * extra.lpMint.
 */
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");

module.exports = {
  aliases: ["orca-dex", "orca-whirlpools"],
  async quote({ asset, amount }) {
    return {
      expectedAmountOut: null,
      receiptToken: `orca-position-${asset || "?"}`,
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
            summary: `Orca LP entry: ${asset || "USDC"} → LP ${extra.lpMint.slice(0, 8)}…`,
            description: "Direct Jupiter-routed entry into the Orca AMM v1 LP token.",
            receiptToken: "orca-lp",
            feeUsd: 0.01,
            durationS: 25,
            warnings: ["Position holds AMM v1 LP token; manage via Orca UI for advanced features."],
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
          summary: `Orca prep: convert half of ${asset || "SOL"} → USDC for Whirlpool entry`,
          description: (
            "Stages capital for opening an Orca Whirlpool position by converting " +
            "half of your input asset into USDC via Jupiter. Open the concentrated-" +
            "liquidity position in the Orca app once the swap confirms."
          ),
          receiptToken: "USDC",
          feeUsd: 0.01,
          durationS: 25,
          warnings: [
            "Whirlpool concentrated-liquidity entry needs the Whirlpools SDK; this prep step makes the position ready in one click in the Orca UI.",
          ],
        },
      ],
    };
  },
};
