/**
 * Orca adapter — pair-aware prep swap for Whirlpools + direct LP-mint route
 * for fungible Orca AMM v1 LP tokens. Pre-sim gate on every returned tx.
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
  aliases: ["orca-dex", "orca-whirlpools"],
  async quote({ asset, amount }) {
    return {
      expectedAmountOut: null,
      receiptToken: `orca-position-${asset || "?"}`,
      apy: null,
      fees: { protocol: "Jupiter routing", network: "0.000005 SOL" },
    };
  },
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }, { connection } = {}) {
    if (extra.lpMint) {
      const inputSym = (asset || "USDC").toUpperCase();
      const inputMint = resolveMint(inputSym) || resolveMint("USDC");
      const { tx } = await buildSwap({
        inputMint,
        outputMint: extra.lpMint,
        amount,
        user,
        slippageBps,
        decimals: decimalsFor(inputSym),
      });
      const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
      if (!sim.ok) {
        const e = new Error(`Orca LP-mint route simulation failed: ${sim.errStr || "unknown"}`);
        e.simulation = sim;
        throw e;
      }
      return {
        transactions: [
          {
            b64: tx,
            summary: `Orca LP entry: ${inputSym} → LP ${extra.lpMint.slice(0, 8)}…`,
            description: "Direct Jupiter-routed entry into the Orca AMM v1 LP token.",
            receiptToken: "orca-lp",
            feeUsd: 0.01,
            durationS: 25,
            warnings: ["Position holds AMM v1 LP token; manage via Orca UI for advanced features."],
            simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
          },
        ],
      };
    }

    // Pair-aware prep for Whirlpools / non-LP-mint pools.
    const plan = planPrepSwap({ asset, extra });
    const sourceSym = plan.inputSym;
    const targetSym = plan.targetSym;
    const inputMint = plan.inputMint;
    const targetMint = plan.targetMint;

    const half = halfAmount(amount);
    if (half === "0") {
      const e = new Error(`Orca prep: amount '${amount}' too small after half-split`);
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
      const e = new Error(`Orca prep-swap simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }

    const tokens = extra.underlying_tokens || extra.underlyingTokens || [];
    const orcaUrl =
      tokens.length >= 2
        ? `https://www.orca.so/liquidity/browse?tokens=${tokens[0]}-${tokens[1]}`
        : "https://www.orca.so/liquidity";
    const pairLabel = (extra.pool_symbol || extra.poolSymbol || `${sourceSym}-${targetSym}`).toUpperCase();

    return {
      transactions: [
        {
          b64: tx,
          summary: `Step 1/2 prep-swap: ${sourceSym} → ${targetSym} for ${pairLabel} Whirlpool entry`,
          description: `Swap half of your ${sourceSym} into ${targetSym} via Jupiter so both ${pairLabel} pool tokens sit in your wallet. After this prep tx confirms, click 'Open on Orca' below to open a concentrated-liquidity position — Orca's Whirlpool deposit SDK isn't wired for in-chat signing yet.`,
          receiptToken: targetSym,
          feeUsd: 0.01,
          durationS: 25,
          protocolUrl: orcaUrl,
          warnings: [
            `Whirlpool position needs a tick range chosen on Orca: ${orcaUrl}`,
            ...plan.warnings,
          ],
          mode: plan.mode,
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },
};
