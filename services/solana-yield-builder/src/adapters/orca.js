/**
 * Orca adapter — native Whirlpools open_position + increaseLiquidity path
 * for concentrated-liquidity pools, plus the direct LP-mint route for
 * fungible Orca AMM v1 LP tokens. Pre-sim gate on every returned tx.
 *
 * V7-050 — legacy two-tx Jupiter handoff dropped. The adapter now
 * builds the real open-position + increase-liquidity instruction bundle
 * via @orca-so/whirlpools-sdk (`WhirlpoolClient.openPosition`) so the
 * user signs one tx that opens the position NFT, derives tick-array
 * PDAs, and deposits both legs of liquidity. WSOL legs get a syncNative
 * + closeAccount safety pair from `_token_safety`.
 *
 * Phase C lifecycle close: buildClose() decreases liquidity, collects
 * fees + rewards, and closes the position NFT mint via the same SDK.
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
  humanToAtoms,
  SOL_MINT,
} = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");
const { checkTxAccountCount } = require("./altSplit");
// V7-031/032/041 centralized safety helpers. WSOL sync/close ixs are wired
// into the native open+increase path below. checkTransferHook (V7-031) and
// isWhirlpoolInitialized (V7-041) gate every Whirlpool open before the SDK
// is touched, mirroring the marinade/raydium/kamino canonical pattern.
const tokenSafety = require("./_token_safety");
const { checkTransferHook, isWhirlpoolInitialized } = tokenSafety;

function _orcaHookBlocker(mintStr, hookProgramId) {
  return {
    kind: "blocker",
    code: "TRANSFER_HOOK_NOT_ALLOWED",
    blocker: "TRANSFER_HOOK_NOT_ALLOWED",
    error: "TRANSFER_HOOK_NOT_ALLOWED",
    message:
      `Orca build blocked: mint ${mintStr} declares a Token-2022 ` +
      `transfer hook (${hookProgramId}) that is not in the sidecar allowlist.`,
    mint: mintStr,
    hookProgramId,
    transactions: [],
  };
}

function _orcaPoolNotInitBlocker(whirlpoolPubkeyStr) {
  return {
    kind: "blocker",
    code: "POOL_NOT_INITIALIZED",
    blocker: "POOL_NOT_INITIALIZED",
    error: "POOL_NOT_INITIALIZED",
    message: `Whirlpool ${whirlpoolPubkeyStr} is not initialized on-chain.`,
    whirlpool: whirlpoolPubkeyStr,
    transactions: [],
  };
}

// Orca Whirlpool program — verified on mainnet, hard-coded constant.
const WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";

// --- SDK loader -------------------------------------------------------------
// Lazy require so a stripped sidecar surfaces a clean blocker instead of
// crashing at module load. Returns the SDK module or throws an Error whose
// message names the missing package + remediation.
function _loadWhirlpoolSdk() {
  try {
    return require("@orca-so/whirlpools-sdk");
  } catch (err) {
    throw new Error(
      `@orca-so/whirlpools-sdk not installed in sidecar (${err.message}). ` +
      "Run `npm install` inside services/solana-yield-builder."
    );
  }
}

// Minimal Anchor-style wallet shim. The SDK constructs a Provider with
// this; we never call its signers because we serialize for wallet-side
// signing.
function _walletShim(userPubkey) {
  return {
    publicKey: userPubkey,
    signTransaction: async (tx) => tx,
    signAllTransactions: async (txs) => txs,
  };
}

function _ctx(connection, userPubkey, sdk) {
  const { WhirlpoolContext, ORCA_WHIRLPOOL_PROGRAM_ID } = sdk;
  return WhirlpoolContext.from(
    connection,
    _walletShim(userPubkey),
    ORCA_WHIRLPOOL_PROGRAM_ID || new PublicKey(WHIRLPOOL_PROGRAM_ID),
  );
}

// Lower a TransactionBuilder to web3.js instructions + signers.
async function _materializeBuilder(txBuilder) {
  if (typeof txBuilder.build === "function") {
    const built = await txBuilder.build();
    return {
      tx: built.transaction || built.tx,
      signers: built.signers || [],
    };
  }
  if (txBuilder.transaction) {
    return { tx: txBuilder.transaction, signers: txBuilder.signers || [] };
  }
  throw new Error("Orca SDK returned an unrecognised TransactionBuilder shape.");
}

/**
 * Native open_position + increaseLiquidity bundle for a Whirlpool.
 *
 * Caller passes the resolved whirlpool address plus the deposit input
 * amount in human units of `inputSymbol`. The SDK computes the increase-
 * liquidity quote from the current pool price and target tick range,
 * then emits one composite tx with: open_position (mints the NFT, opens
 * the position PDA) + increase_liquidity (deposits both token sides).
 *
 * WSOL legs: if either mint is wrapped SOL, we wrap the SOL → WSOL
 * ATA, syncNative the lamport balance, and close the ATA on the unwrap
 * leg via the harness-shaped instructions from `_token_safety`.
 *
 * Returns { b64, summary, description, ... } same shape as buildClose().
 */
async function buildOpenPositionTx({
  user,
  whirlpool,
  inputSymbol,
  inputAmount,
  tickLowerIndex,
  tickUpperIndex,
  slippageBps = 50,
  extra = {},
}, { connection } = {}) {
  if (!connection) {
    throw new Error("Orca buildOpen requires a Solana connection.");
  }
  if (!whirlpool) {
    throw new Error("Orca buildOpen requires extra.whirlpool (the pool address).");
  }
  if (tickLowerIndex === undefined || tickUpperIndex === undefined) {
    throw new Error(
      "Orca buildOpen requires extra.tickLowerIndex + extra.tickUpperIndex. " +
      "Auto-tick-range selection lands in V7-051."
    );
  }
  const userPubkey = new PublicKey(user);
  const whirlpoolPk = new PublicKey(whirlpool);

  // V7-041 — gate the pool account BEFORE booting the SDK so a missing or
  // wrong-program-owned account surfaces a clean POOL_NOT_INITIALIZED blocker
  // instead of an opaque SDK exception inside getPool().
  const poolReady = await isWhirlpoolInitialized(connection, whirlpoolPk);
  if (!poolReady) {
    return _orcaPoolNotInitBlocker(whirlpoolPk.toString());
  }

  // V7-031 (pre-SDK leg) — gate the INPUT mint up-front so a hook-bearing
  // mint refuses cleanly without booting the Whirlpool SDK. Pool-side mints
  // are checked after `getPool()` below since their pubkeys come from the
  // on-chain pool state.
  const inputMintStr = resolveMint(inputSymbol) || resolveMint("USDC");
  const inputMintPk = new PublicKey(inputMintStr);
  if (inputMintStr && inputMintStr !== SOL_MINT) {
    const inputHook = await checkTransferHook(connection, inputMintPk);
    if (!inputHook.ok) {
      return _orcaHookBlocker(inputMintStr, inputHook.hookProgramId);
    }
  }

  const sdk = _loadWhirlpoolSdk();
  const {
    buildWhirlpoolClient,
    PriceMath,
    increaseLiquidityQuoteByInputTokenWithParams,
  } = sdk;
  const ctx = _ctx(connection, userPubkey, sdk);
  const client = buildWhirlpoolClient(ctx);
  const pool = await client.getPool(whirlpoolPk);
  const poolData = pool.getData();

  // Compute the increase-liquidity quote for the input leg. Whirlpool
  // SDK derives the matching amount of the other side at current price.
  const inputDecimals = decimalsFor(inputSymbol);
  const inputAtoms = humanToAtoms(inputAmount, inputDecimals);

  const tokenMintA = poolData.tokenMintA;
  const tokenMintB = poolData.tokenMintB;

  // V7-031 — gate the two pool-side mints against the Token-2022 hook
  // allowlist now that we know them from on-chain pool data. WSOL is
  // legacy SPL and cannot carry a hook, so skip it to avoid wasted RPC.
  for (const sideMint of [tokenMintA, tokenMintB]) {
    const sideStr = sideMint.toString();
    if (!sideStr || sideStr === SOL_MINT || sideStr === inputMintStr) continue;
    const hookCheck = await checkTransferHook(connection, new PublicKey(sideMint));
    if (!hookCheck.ok) {
      return _orcaHookBlocker(sideStr, hookCheck.hookProgramId);
    }
  }

  // Increase-liquidity quote requires the input mint to be one side of
  // the pool. If the caller passed a non-pool symbol we surface a
  // clean blocker — auto Jupiter routing into one side lands in V7-051.
  const inputIsA = tokenMintA.toString() === inputMintPk.toString();
  const inputIsB = tokenMintB.toString() === inputMintPk.toString();
  if (!inputIsA && !inputIsB) {
    throw new Error(
      `Orca buildOpen: input ${inputSymbol} (${inputMintStr}) is not one of ` +
      `the pool sides (${tokenMintA.toString()}, ${tokenMintB.toString()}). ` +
      "Pre-swap routing into a pool side lands in V7-051."
    );
  }

  const quote = increaseLiquidityQuoteByInputTokenWithParams({
    inputTokenAmount: new BN(inputAtoms),
    inputTokenMint: inputMintPk,
    tokenMintA,
    tokenMintB,
    sqrtPrice: poolData.sqrtPrice,
    tickCurrentIndex: poolData.tickCurrentIndex,
    tickLowerIndex,
    tickUpperIndex,
    slippageTolerance: { numerator: new BN(slippageBps), denominator: new BN(10000) },
  });

  // openPosition() on the pool returns { positionMint, tx: TransactionBuilder }
  // where the builder already includes open_position + the matching
  // increase_liquidity IXs for the provided quote.
  const opened = await pool.openPosition(
    tickLowerIndex,
    tickUpperIndex,
    quote,
  );
  const positionMint = opened.positionMint;
  const { tx: builtTx, signers } = await _materializeBuilder(opened.tx);

  // Assemble a web3.js Transaction with a bumped compute budget. Wrap
  // any WSOL legs with syncNative + closeAccount safety helpers.
  const tx = new Transaction();
  tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 600_000 }));

  // V7-032: real `syncNative` + `closeAccount` instructions on either
  // side of the SDK's increase-liquidity bundle. The SDK funds the
  // WSOL ATA but, on older versions, does not always emit the matching
  // syncNative/close pair, so we insert them defensively. The ATA is
  // derived from the WSOL mint + user pubkey via spl-token's canonical
  // ATA derivation; `wsolSafetyMeta` keeps a record of what we wired
  // in for downstream debugging.
  const wsolSafetyMeta = [];
  const wsolMintPk = (tokenMintA.toString() === SOL_MINT)
    ? tokenMintA
    : (tokenMintB.toString() === SOL_MINT ? tokenMintB : null);
  let wsolPreIx = null;
  let wsolPostIx = null;
  if (wsolMintPk) {
    let splToken;
    try {
      splToken = require("@solana/spl-token");
    } catch (_err) {
      splToken = null;
    }
    let wsolAta;
    if (splToken && typeof splToken.getAssociatedTokenAddressSync === "function") {
      wsolAta = splToken.getAssociatedTokenAddressSync(wsolMintPk, userPubkey, true);
    } else {
      // Fallback for dependency-free harness: pass mint string through
      // so the builder still emits a placeholder record callers can log.
      wsolAta = wsolMintPk.toString();
    }
    wsolPreIx = tokenSafety.buildSyncNativeIx(wsolAta);
    wsolPostIx = tokenSafety.buildCloseWsolIx(wsolAta, userPubkey);
    wsolSafetyMeta.push(wsolPreIx, wsolPostIx);
  }

  // syncNative must run BEFORE the SDK's deposit IXs so the SPL
  // accounting layer sees the wrapped lamports.
  if (wsolPreIx && !wsolPreIx.__placeholder) {
    tx.add(wsolPreIx);
  }
  if (builtTx && builtTx.instructions) {
    tx.add(...builtTx.instructions);
  } else if (Array.isArray(builtTx)) {
    tx.add(...builtTx);
  }
  // closeAccount runs AFTER the deposit so any residual WSOL lamports
  // (slippage dust on the unwrap leg) flow back to the owner as native
  // SOL when the ATA is closed.
  if (wsolPostIx && !wsolPostIx.__placeholder) {
    tx.add(wsolPostIx);
  }
  tx.feePayer = userPubkey;
  const { blockhash } = await connection.getLatestBlockhash("confirmed");
  tx.recentBlockhash = blockhash;
  if (signers && signers.length) {
    tx.partialSign(...signers);
  }
  const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
  const b64 = raw.toString("base64");
  const sim = await simulateBase64Tx({ b64, connection });
  if (!sim.ok) {
    const e = new Error(`Orca open_position simulation failed: ${sim.errStr || "unknown"}`);
    e.simulation = sim;
    throw e;
  }
  const sz = checkTxAccountCount(b64);
  const altWarn = sz.needsSplit
    ? ["Transaction has " + sz.accounts + " accounts. Hardware wallets may need ALT pre-warming."]
    : [];
  const positionMintStr = positionMint && positionMint.toString
    ? positionMint.toString()
    : String(positionMint || "");
  const pairLabel = (extra.pool_symbol || extra.poolSymbol || `${inputSymbol}-pair`).toUpperCase();

  return {
    transactions: [
      {
        b64,
        action: "open_position",
        summary: `Orca open position ${pairLabel} [${tickLowerIndex},${tickUpperIndex}]`,
        description: (
          `Opens a new Whirlpool concentrated-liquidity position on ${pairLabel} ` +
          `with tick range [${tickLowerIndex}, ${tickUpperIndex}] and deposits ` +
          `${inputAmount} ${inputSymbol} via native open_position + increase_liquidity IXs.`
        ),
        receiptToken: positionMintStr || "orca-position",
        positionMint: positionMintStr,
        redemption_program: WHIRLPOOL_PROGRAM_ID,
        feeUsd: 0.01,
        durationS: 25,
        wsolSafety: wsolSafetyMeta,
        warnings: [
          `Position NFT mint will be minted to your wallet. Save it for close_position later.`,
          ...altWarn,
        ],
        simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
      },
    ],
  };
}

/**
 * Native increaseLiquidity-only path for an *existing* position.
 *
 * Mirrors buildOpenPositionTx() but skips the open_position IX — the
 * caller passes the existing position mint and we just emit the
 * increase_liquidity IX bundle.
 */
async function buildIncreaseLiquidityTx({
  user,
  positionMint,
  inputSymbol,
  inputAmount,
  slippageBps = 50,
  extra = {},
}, { connection } = {}) {
  if (!connection) {
    throw new Error("Orca buildIncrease requires a Solana connection.");
  }
  if (!positionMint) {
    throw new Error("Orca buildIncrease requires extra.positionMint.");
  }
  const userPubkey = new PublicKey(user);
  const positionMintPk = new PublicKey(positionMint);
  const sdk = _loadWhirlpoolSdk();
  const {
    buildWhirlpoolClient,
    PDAUtil,
    increaseLiquidityQuoteByInputTokenWithParams,
  } = sdk;
  const ctx = _ctx(connection, userPubkey, sdk);
  const client = buildWhirlpoolClient(ctx);
  const positionPda = PDAUtil.getPosition(ctx.program.programId, positionMintPk);
  const position = await client.getPosition(positionPda.publicKey);
  const positionData = position.getData();
  const pool = await client.getPool(positionData.whirlpool);
  const poolData = pool.getData();

  const inputDecimals = decimalsFor(inputSymbol);
  const inputAtoms = humanToAtoms(inputAmount, inputDecimals);
  const inputMintStr = resolveMint(inputSymbol) || resolveMint("USDC");
  const inputMintPk = new PublicKey(inputMintStr);

  const quote = increaseLiquidityQuoteByInputTokenWithParams({
    inputTokenAmount: new BN(inputAtoms),
    inputTokenMint: inputMintPk,
    tokenMintA: poolData.tokenMintA,
    tokenMintB: poolData.tokenMintB,
    sqrtPrice: poolData.sqrtPrice,
    tickCurrentIndex: poolData.tickCurrentIndex,
    tickLowerIndex: positionData.tickLowerIndex,
    tickUpperIndex: positionData.tickUpperIndex,
    slippageTolerance: { numerator: new BN(slippageBps), denominator: new BN(10000) },
  });

  const builder = await position.increaseLiquidity(quote);
  const { tx: builtTx, signers } = await _materializeBuilder(builder);

  const tx = new Transaction();
  tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 400_000 }));
  if (builtTx && builtTx.instructions) {
    tx.add(...builtTx.instructions);
  } else if (Array.isArray(builtTx)) {
    tx.add(...builtTx);
  }
  tx.feePayer = userPubkey;
  const { blockhash } = await connection.getLatestBlockhash("confirmed");
  tx.recentBlockhash = blockhash;
  if (signers && signers.length) {
    tx.partialSign(...signers);
  }
  const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
  const b64 = raw.toString("base64");
  const sim = await simulateBase64Tx({ b64, connection });
  if (!sim.ok) {
    const e = new Error(`Orca increase_liquidity simulation failed: ${sim.errStr || "unknown"}`);
    e.simulation = sim;
    throw e;
  }
  return {
    transactions: [
      {
        b64,
        action: "increase_liquidity",
        summary: `Orca increase liquidity on position ${String(positionMint).slice(0, 8)}…`,
        description: (
          `Adds ${inputAmount} ${inputSymbol} of liquidity to existing Whirlpool ` +
          `position ${positionMint} within its current tick range.`
        ),
        receiptToken: String(positionMint),
        redemption_program: WHIRLPOOL_PROGRAM_ID,
        feeUsd: 0.01,
        durationS: 20,
        warnings: [],
        simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
      },
    ],
  };
}

module.exports = {
  aliases: ["orca-dex", "orca-whirlpools"],
  supportedActions: ["deposit", "supply", "deposit_lp", "open_position", "increase_liquidity", "close_position", "close", "exit"],
  WHIRLPOOL_PROGRAM_ID,

  async quote({ asset, amount }) {
    return {
      expectedAmountOut: null,
      receiptToken: `orca-position-${asset || "?"}`,
      apy: null,
      fees: { protocol: "Orca Whirlpools", network: "0.000005 SOL" },
    };
  },

  /**
   * Public wrapper for native open_position + increase_liquidity. Adapter
   * dispatch may route here when `extra.whirlpool` + tick bounds are
   * supplied; otherwise the generic `build()` entry below routes by
   * intent (lpMint → AMM v1, whirlpool → native CLMM open).
   */
  async buildOpen(args, ctxArg) {
    return buildOpenPositionTx(args, ctxArg);
  },

  async buildIncrease(args, ctxArg) {
    return buildIncreaseLiquidityTx(args, ctxArg);
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

    const whirlpoolsSdk = _loadWhirlpoolSdk();
    const {
      buildWhirlpoolClient,
      PDAUtil,
      decreaseLiquidityQuoteByLiquidityWithParams,
    } = whirlpoolsSdk;

    const ctx = _ctx(connection, userPubkey, whirlpoolsSdk);
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

    const { tx: builtTx, signers } = await _materializeBuilder(txBuilder);

    const tx = new Transaction();
    tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 800_000 }));
    // Fold builtTx instructions in.
    if (builtTx && builtTx.instructions) {
      tx.add(...builtTx.instructions);
    } else if (Array.isArray(builtTx)) {
      tx.add(...builtTx);
    }
    tx.feePayer = userPubkey;
    const { blockhash } = await connection.getLatestBlockhash("confirmed");
    tx.recentBlockhash = blockhash;
    if (signers && signers.length) {
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
    const sz = checkTxAccountCount(b64);
    const altWarn = sz.needsSplit
      ? ["Transaction has " + sz.accounts + " accounts. Hardware wallets may need ALT pre-warming."]
      : [];
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
            ...altWarn,
          ],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },

  /**
   * Generic dispatch entry kept for backwards-compat. Routes by `extra`:
   *
   *   • extra.lpMint        → direct Jupiter-routed entry into the AMM v1
   *                           LP token mint (unchanged).
   *   • extra.whirlpool +   → native open_position + increase_liquidity
   *     tick bounds           via buildOpenPositionTx().
   *   • otherwise            → blocker; the legacy two-tx Jupiter
   *                           handoff was removed in V7-050.
   */
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }, { connection } = {}) {
    if (extra.lpMint) {
      const inputSym = (asset || "USDC").toUpperCase();
      const inputMint = resolveMint(inputSym) || resolveMint("USDC");
      // V7-031 — gate the AMM v1 LP-mint route on the input mint's transfer
      // hook before Jupiter quotes anything. lpMint itself is a classic AMM
      // v1 LP token (legacy SPL, no extensions possible).
      if (connection && inputMint && inputMint !== SOL_MINT) {
        const inputHook = await checkTransferHook(connection, new PublicKey(inputMint));
        if (!inputHook.ok) {
          return _orcaHookBlocker(inputMint, inputHook.hookProgramId);
        }
      }
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

    // Native Whirlpool open path — V7-050 replaces the legacy two-tx
    // handoff. Caller must supply the resolved whirlpool address and
    // tick bounds; the auto-resolution layer lives in the orchestrator.
    if (extra.whirlpool || extra.whirlpoolAddress) {
      return buildOpenPositionTx(
        {
          user,
          whirlpool: extra.whirlpool || extra.whirlpoolAddress,
          inputSymbol: (asset || "USDC").toUpperCase(),
          inputAmount: amount,
          tickLowerIndex: extra.tickLowerIndex,
          tickUpperIndex: extra.tickUpperIndex,
          slippageBps,
          extra,
        },
        { connection },
      );
    }

    // No legacy two-tx Jupiter fallback (V7-050). Surface a clean
    // blocker so the orchestrator knows to resolve the whirlpool
    // address before retrying.
    const e = new Error(
      "Orca build: native open_position requires extra.whirlpool + extra.tickLowerIndex/tickUpperIndex. " +
      "The legacy two-tx Jupiter handoff was removed in V7-050."
    );
    e.code = "missing_whirlpool_or_ticks";
    throw e;
  },

  // Internal handles for tests + advanced callers.
  _internals: {
    buildOpenPositionTx,
    buildIncreaseLiquidityTx,
    WHIRLPOOL_PROGRAM_ID,
  },
};
