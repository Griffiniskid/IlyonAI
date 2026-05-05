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
    // No lpMint or invalid one: always do a prep-swap into the side that's
    // *missing* in the user's wallet. If the user already holds USDC, swap
    // half into SOL to balance the LP. If they hold SOL, swap half into USDC.
    const inputIsUsdc = inputMint === usdcMint;
    const targetMint = inputIsUsdc ? SOL_MINT : usdcMint;
    const targetSym = inputIsUsdc ? "SOL" : "USDC";
    const sourceSym = inputIsUsdc ? "USDC" : (asset || "SOL");
    const half = (parseFloat(amount || "0") / 2).toString();
    const { tx } = await buildSwap({
      inputMint,
      outputMint: targetMint,
      amount: half,
      user,
      slippageBps,
      decimals: decimalsFor(sourceSym),
    });
    return {
      transactions: [
        {
          b64: tx,
          summary: `Raydium prep: convert half of ${sourceSym} → ${targetSym} for LP entry`,
          description: `Stages capital for adding liquidity to a Raydium AMM v4 / CLMM pool. After this prep tx confirms, finalise the LP add inside the Raydium app for the SPACEX-WSOL or your selected pair.`,
          receiptToken: targetSym,
          feeUsd: 0.01,
          durationS: 25,
          warnings: ["Final LP add for Raydium runs in the Raydium app after this prep swap confirms."],
        },
      ],
    };
  },
};
