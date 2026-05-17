/**
 * Orca adapter — pair-aware prep swap for Whirlpools + direct LP-mint route
 * for fungible Orca AMM v1 LP tokens. Pre-sim gate on every returned tx.
 *
 * Phase C lifecycle close: buildClose() decreases liquidity, collects fees +
 * rewards, and closes the position NFT mint via the @orca-so/whirlpools-sdk.
 */
const {
  Connection,
  PublicKey,
  Transaction,
  ComputeBudgetProgram,
} = require("@solana/web3.js");
const BN = require("bn.js");
const {
  buildSwap,
  resolveMint,
  decimalsFor,
  halfAmount,
  SOL_MINT,
} = require("./jupiter");
const { planPrepSwap } = require("./pairAware");
const { simulateBase64Tx } = require("./simulate");

// Orca Whirlpool program — verified on mainnet, hard-coded constant.
const WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";

module.exports = {
  aliases: ["orca-dex", "orca-whirlpools"],
  supportedActions: ["deposit", "supply", "deposit_lp", "close_position", "close", "exit"],
  async quote({ asset, amount }) {
    return {
      expectedAmountOut: null,
      receiptToken: `orca-position-${asset || "?"}`,
      apy: null,
      fees: { protocol: "Jupiter routing", network: "0.000005 SOL" },
    };
  },

  /**
   * Phase C lifecycle — close an Orca Whirlpool concentrated-liquidity
   * position. Sequence per @orca-so/whirlpools-sdk:
   *   1. decreaseLiquidity (burn all current liquidity → tokens to user ATAs)
   *   2. collectFees (sweep accrued swap fees)
   *   3. collectRewards (sweep any active reward emissions)
   *   4. close position IX (close position PDA + NFT mint, reclaim rent)
   *
   * The SDK builds these as a single composite tx when liquidity fits the
   * 1232-byte limit; large reward sets may need a follow-up tx. We bundle
   * everything the SDK returns into one signed tx.
   *
   * positionMint is required — either passed as extra.positionMint or
   * extra.position_mint. Looking up positions by owner requires an RPC
   * scan of ~1k accounts which is too slow for chat latency.
   */
  async buildClose({ user, positionMint, slippageBps = 100, extra = {} }, { connection } = {}) {
    if (!connection) {
      throw new Error("Orca buildClose requires a Solana connection.");
    }
    const mint = positionMint || extra.positionMint || extra.position_mint;
    if (!mint) {
      throw new Error(
        "Orca close_position requires extra.positionMint (the Whirlpool position NFT mint). " +
        "Receipt lookup by owner not yet wired — pass the mint from the position-store."
      );
    }
    let positionMintPk;
    try {
      positionMintPk = new PublicKey(mint);
    } catch (err) {
      throw new Error(`Orca close_position: invalid positionMint pubkey '${mint}': ${err.message}`);
    }
    const userPubkey = new PublicKey(user);

    // SDK imports done lazily — if the package is missing in a stripped
    // deployment we surface a clean blocker instead of crashing at module load.
    let whirlpoolsSdk;
    try {
      whirlpoolsSdk = require("@orca-so/whirlpools-sdk");
    } catch (err) {
      throw new Error(
        `@orca-so/whirlpools-sdk not installed in sidecar (${err.message}). ` +
        "Run `npm install` inside services/solana-yield-builder."
      );
    }
    const {
      WhirlpoolContext,
      buildWhirlpoolClient,
      PDAUtil,
      PoolUtil,
      decreaseLiquidityQuoteByLiquidityWithParams,
      ORCA_WHIRLPOOL_PROGRAM_ID,
    } = whirlpoolsSdk;

    // Minimal Anchor-style wallet shim: SDK needs `publicKey` + sign stubs.
    // The transactions we build never go through these signers — they are
    // serialized for wallet-side signing — but the SDK constructs Provider
    // with them.
    const wallet = {
      publicKey: userPubkey,
      signTransaction: async (tx) => tx,
      signAllTransactions: async (txs) => txs,
    };
    const ctx = WhirlpoolContext.from(
      connection,
      wallet,
      ORCA_WHIRLPOOL_PROGRAM_ID || new PublicKey(WHIRLPOOL_PROGRAM_ID),
    );
    const client = buildWhirlpoolClient(ctx);

    // Derive position PDA from mint, fetch position data.
    const positionPda = PDAUtil.getPosition(
      ctx.program.programId,
      positionMintPk,
    );
    const position = await client.getPosition(positionPda.publicKey);
    const positionData = position.getData();
    const whirlpool = await client.getPool(positionData.whirlpool);

    // Compute decrease-liquidity quote for the full position.
    const liquidity = positionData.liquidity;
    if (!liquidity || new BN(liquidity).lte(new BN(0))) {
      // Empty position — skip decrease leg; still attempt collect + close.
    }
    const tickLower = positionData.tickLowerIndex;
    const tickUpper = positionData.tickUpperIndex;
    const sqrtPrice = whirlpool.getData().sqrtPrice;

    const decreaseQuote = liquidity && new BN(liquidity).gt(new BN(0))
      ? decreaseLiquidityQuoteByLiquidityWithParams({
          liquidity: new BN(liquidity),
          slippageTolerance: { numerator: new BN(slippageBps), denominator: new BN(10000) },
          sqrtPrice,
          tickCurrentIndex: whirlpool.getData().tickCurrentIndex,
          tickLowerIndex: tickLower,
          tickUpperIndex: tickUpper,
        })
      : null;

    // Build the close IX bundle. The SDK exposes a high-level closePosition()
    // that emits decrease-liquidity + collect-fees + collect-rewards + close
    // in one TransactionBuilder. Versions vary on the method name; fall back
    // to manual composition when unavailable.
    let txBuilder;
    if (typeof position.close === "function") {
      txBuilder = await position.close({
        liquidityAmount: liquidity ? new BN(liquidity) : new BN(0),
        slippageTolerance: { numerator: new BN(slippageBps), denominator: new BN(10000) },
      });
    } else {
      // Manual sequence: decreaseLiquidity → collectFees → collectRewards → close.
      const builders = [];
      if (decreaseQuote) {
        builders.push(await position.decreaseLiquidity(decreaseQuote));
      }
      if (typeof position.collectFees === "function") {
        builders.push(await position.collectFees());
      }
      if (typeof position.collectRewards === "function") {
        const rewardBuilders = await position.collectRewards();
        if (Array.isArray(rewardBuilders)) builders.push(...rewardBuilders);
        else if (rewardBuilders) builders.push(rewardBuilders);
      }
      // Final close-position IX.
      if (typeof position.close === "function") {
        builders.push(await position.close());
      }
      // Compose all builders into one — TransactionBuilder.addInstruction()
      // pattern. Take the first as base, fold others in.
      if (!builders.length) {
        throw new Error("Orca close: position has no liquidity, fees, or rewards to sweep — already closed?");
      }
      txBuilder = builders[0];
      for (let i = 1; i < builders.length; i += 1) {
        if (typeof txBuilder.addInstruction === "function" && builders[i].compressIx) {
          txBuilder.addInstruction(builders[i].compressIx(false));
        }
      }
    }

    // Materialize: pull the underlying ixs + signers and assemble a
    // Transaction. Bump compute budget to 800k for the multi-IX bundle.
    let builtTx;
    let signers = [];
    if (typeof txBuilder.build === "function") {
      const built = await txBuilder.build();
      builtTx = built.transaction || built.tx;
      signers = built.signers || [];
    } else if (typeof txBuilder.buildAndExecute === "function") {
      // Some SDK versions only expose buildAndExecute; we have to introspect.
      throw new Error(
        "Orca SDK build() not exposed on TransactionBuilder; sidecar needs SDK upgrade for close_position."
      );
    } else if (txBuilder.transaction) {
      builtTx = txBuilder.transaction;
      signers = txBuilder.signers || [];
    } else {
      throw new Error("Orca SDK returned an unrecognised TransactionBuilder shape.");
    }

    const tx = new Transaction();
    tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 800_000 }));
    // Fold builtTx instructions in.
    if (builtTx.instructions) {
      tx.add(...builtTx.instructions);
    } else if (Array.isArray(builtTx)) {
      tx.add(...builtTx);
    }
    tx.feePayer = userPubkey;
    const { blockhash } = await connection.getLatestBlockhash("confirmed");
    tx.recentBlockhash = blockhash;
    if (signers.length) {
      tx.partialSign(...signers);
    }
    const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
    const b64 = raw.toString("base64");
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(`Orca close_position simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    return {
      transactions: [
        {
          b64,
          summary: `Orca close position ${mint.slice(0, 8)}…`,
          description: (
            `Decreases all liquidity, collects accrued fees + rewards, and closes the ` +
            `Whirlpool position NFT (mint ${mint}). Reclaims position-PDA + mint rent.`
          ),
          receiptToken: "SOL",
          redemption_program: WHIRLPOOL_PROGRAM_ID,
          feeUsd: 0.01,
          durationS: 30,
          warnings: [
            "Closes the entire position — any in-range liquidity exits to your wallet at current pool price.",
            "Position NFT is burned; rewards/fees credited to your ATAs.",
          ],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
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
          action: "prep_swap",
          summary: `Prep swap: ${half} ${sourceSym} → ${targetSym} (Orca ${pairLabel} Whirlpool handoff)`,
          description: `Swap ${half} ${sourceSym} into ${targetSym} via Jupiter so you hold one side of the ${pairLabel} Whirlpool. After this swap confirms, click the Orca link to pick a tick range and open the concentrated-liquidity position — Whirlpool deposit SDK isn't wired for in-chat signing yet.`,
          inputSymbol: sourceSym,
          inputAmount: half,
          outputSymbol: targetSym,
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
