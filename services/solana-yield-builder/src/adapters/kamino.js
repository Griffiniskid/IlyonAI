/**
 * Kamino — V7-009 native build.
 *
 * Primary path: Kamino's signable transaction REST (`/v2/transactions/deposit`
 * and `/transactions/deposit`). When REST is unreachable, we no longer route
 * through Jupiter into JLP/JitoSOL — that was a misleading "yield proxy" that
 * minted the wrong receipt token and tracked the wrong APY. Instead we
 * hand-roll the Kamino Lend `deposit_reserve_liquidity_and_obligation_collateral`
 * (and matching withdraw) instructions using the program's Anchor discriminator
 * so the user gets a real Kamino position with the real receipt collateral mint.
 *
 * Anchor sighash scheme (spec §3.2):
 *   discriminator = sha256(`global:${snake_case_ix_name}`).slice(0, 8)
 *
 * The full klend-sdk is wired via package.json so production sidecars can
 * upgrade the native path to use the SDK's typed builders once the install
 * footprint is acceptable. The hand-roll here is the dependency-light
 * fallback that keeps the sidecar bootable without a 200MB npm tree.
 */
const crypto = require("crypto");
const fetch = require("node-fetch").default || require("node-fetch");
const {
  PublicKey,
  TransactionInstruction,
  TransactionMessage,
  VersionedTransaction,
  ComputeBudgetProgram,
  SystemProgram,
  SYSVAR_INSTRUCTIONS_PUBKEY,
} = require("@solana/web3.js");
const BN = require("bn.js");
const { simulateBase64Tx } = require("./simulate");
// V7-031 Token-2022 transfer-hook allowlist enforcement.
const { checkTransferHook } = require("./_token_safety");

function _kaminoHookBlocker(mintStr, hookProgramId) {
  return {
    kind: "blocker",
    code: "TRANSFER_HOOK_NOT_ALLOWED",
    blocker: "TRANSFER_HOOK_NOT_ALLOWED",
    error: "TRANSFER_HOOK_NOT_ALLOWED",
    message:
      `Kamino build blocked: reserve liquidity mint ${mintStr} declares a Token-2022 ` +
      `transfer hook (${hookProgramId}) that is not in the sidecar allowlist.`,
    mint: mintStr,
    hookProgramId,
    transactions: [],
  };
}

async function _kaminoCheckHook(connection, extra) {
  if (!connection || !extra) return null;
  const candidates = [
    extra.reserveLiquidityMint,
    extra.reserve_liquidity_mint,
    extra.inputMint,
    extra.input_mint,
    extra.accounts && (extra.accounts.reserveLiquidityMint || extra.accounts.reserve_liquidity_mint),
  ].filter(Boolean);
  for (const m of candidates) {
    const mintPk = m instanceof PublicKey ? m : new PublicKey(String(m));
    const hookCheck = await checkTransferHook(connection, mintPk);
    if (!hookCheck.ok) {
      return _kaminoHookBlocker(mintPk.toBase58(), hookCheck.hookProgramId);
    }
  }
  return null;
}

// Default to Kamino's public REST so production gets the real vault deposit
// path without needing extra env setup. Override KAMINO_API_BASE to point
// at staging or a local mock.
const BASE = process.env.KAMINO_API_BASE || "https://api.kamino.finance";

// Kamino Lend program ID — verified on mainnet (https://docs.kamino.finance).
// Surfaced on every deposit/withdraw tx so the agent's receipt-reader can
// match position-store entries by redemption_program.
const KAMINO_LEND_PROGRAM_ID = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD";
const KAMINO_LEND_PROGRAM_PK = new PublicKey(KAMINO_LEND_PROGRAM_ID);

// SPL Token program — Kamino collateral mints are classic SPL (not Token-2022).
const TOKEN_PROGRAM_ID = new PublicKey("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");

/**
 * Compute the 8-byte Anchor sighash for an instruction name.
 * Mirrors @coral-xyz/anchor's `instructionDiscriminator()`.
 */
function anchorSighash(ixName) {
  const preimage = `global:${ixName}`;
  return crypto.createHash("sha256").update(preimage).digest().slice(0, 8);
}

// Pre-computed at module load to avoid sha256 on every build call. Same scheme
// the on-chain Kamino Lend program uses to match incoming instructions.
const DISC_DEPOSIT = anchorSighash("deposit_reserve_liquidity_and_obligation_collateral");
const DISC_WITHDRAW = anchorSighash("withdraw_obligation_collateral_and_redeem_reserve_liquidity");
const DISC_INIT_OBLIGATION = anchorSighash("init_obligation");

/**
 * Encode the deposit IX data: 8-byte discriminator || u64 LE liquidity_amount.
 * Kamino's deposit_reserve_liquidity_and_obligation_collateral takes a single
 * liquidity_amount arg (lamports of the reserve liquidity mint).
 */
function encodeDepositData(liquidityAmountBN) {
  const buf = Buffer.alloc(8);
  // u64 little-endian. BN.toArrayLike(Buffer, 'le', 8) handles overflow safely.
  liquidityAmountBN.toArrayLike(Buffer, "le", 8).copy(buf, 0);
  return Buffer.concat([DISC_DEPOSIT, buf]);
}

/**
 * Encode the withdraw IX data: 8-byte discriminator || u64 LE collateral_amount.
 */
function encodeWithdrawData(collateralAmountBN) {
  const buf = Buffer.alloc(8);
  collateralAmountBN.toArrayLike(Buffer, "le", 8).copy(buf, 0);
  return Buffer.concat([DISC_WITHDRAW, buf]);
}

/**
 * Build the account-meta list for deposit_reserve_liquidity_and_obligation_collateral.
 *
 * Order MUST match the Kamino Lend IDL exactly:
 *   0. owner                            [signer, writable]
 *   1. obligation                       [writable]
 *   2. lending_market                   [readonly]
 *   3. lending_market_authority         [readonly]
 *   4. reserve                          [writable]
 *   5. reserve_liquidity_supply         [writable]
 *   6. reserve_collateral_mint          [writable]
 *   7. reserve_destination_deposit_collateral [writable]
 *   8. user_source_liquidity            [signer-owned, writable]
 *   9. placeholder_user_destination_collateral [readonly] — null pk slot
 *  10. collateral_token_program         [readonly]
 *  11. liquidity_token_program          [readonly]
 *  12. instruction_sysvar               [readonly]
 *
 * The runtime that calls this resolves all PDAs/ATAs from extra.* params
 * (Kamino REST normally fills these for us — when it's down we require
 * the caller to pass them through extra).
 */
function buildDepositAccounts({ owner, accounts }) {
  const need = [
    "obligation",
    "lendingMarket",
    "lendingMarketAuthority",
    "reserve",
    "reserveLiquiditySupply",
    "reserveCollateralMint",
    "reserveDestinationDepositCollateral",
    "userSourceLiquidity",
  ];
  for (const k of need) {
    if (!accounts[k]) {
      throw new Error(
        `Kamino native deposit: missing required account "${k}". REST fallback ` +
        `requires the caller to pass reserve+market+obligation PDAs through extra.accounts.`
      );
    }
  }
  return [
    { pubkey: owner,                                          isSigner: true,  isWritable: true  },
    { pubkey: new PublicKey(accounts.obligation),             isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.lendingMarket),          isSigner: false, isWritable: false },
    { pubkey: new PublicKey(accounts.lendingMarketAuthority), isSigner: false, isWritable: false },
    { pubkey: new PublicKey(accounts.reserve),                isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.reserveLiquiditySupply), isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.reserveCollateralMint),  isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.reserveDestinationDepositCollateral), isSigner: false, isWritable: true },
    { pubkey: new PublicKey(accounts.userSourceLiquidity),    isSigner: false, isWritable: true  },
    // Slot 9 — Kamino's IDL accepts SystemProgram::ID as the null placeholder
    // for the user-destination-collateral account (collateral is parked in
    // the obligation, not minted to the user, on supply-and-stake flows).
    { pubkey: SystemProgram.programId,                        isSigner: false, isWritable: false },
    { pubkey: TOKEN_PROGRAM_ID,                               isSigner: false, isWritable: false },
    { pubkey: TOKEN_PROGRAM_ID,                               isSigner: false, isWritable: false },
    { pubkey: SYSVAR_INSTRUCTIONS_PUBKEY,                     isSigner: false, isWritable: false },
  ];
}

/**
 * Build the account-meta list for withdraw_obligation_collateral_and_redeem_reserve_liquidity.
 *
 * Order MUST match the Kamino Lend IDL exactly:
 *   0. owner                            [signer, writable]
 *   1. obligation                       [writable]
 *   2. lending_market                   [readonly]
 *   3. lending_market_authority         [readonly]
 *   4. reserve                          [writable]
 *   5. reserve_source_collateral        [writable]
 *   6. reserve_collateral_mint          [writable]
 *   7. reserve_liquidity_supply         [writable]
 *   8. user_destination_liquidity       [writable]
 *   9. placeholder_user_destination_collateral [readonly]
 *  10. collateral_token_program         [readonly]
 *  11. liquidity_token_program          [readonly]
 *  12. instruction_sysvar               [readonly]
 */
function buildWithdrawAccounts({ owner, accounts }) {
  const need = [
    "obligation",
    "lendingMarket",
    "lendingMarketAuthority",
    "reserve",
    "reserveSourceCollateral",
    "reserveCollateralMint",
    "reserveLiquiditySupply",
    "userDestinationLiquidity",
  ];
  for (const k of need) {
    if (!accounts[k]) {
      throw new Error(
        `Kamino native withdraw: missing required account "${k}". REST fallback ` +
        `requires the caller to pass reserve+market+obligation PDAs through extra.accounts.`
      );
    }
  }
  return [
    { pubkey: owner,                                          isSigner: true,  isWritable: true  },
    { pubkey: new PublicKey(accounts.obligation),             isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.lendingMarket),          isSigner: false, isWritable: false },
    { pubkey: new PublicKey(accounts.lendingMarketAuthority), isSigner: false, isWritable: false },
    { pubkey: new PublicKey(accounts.reserve),                isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.reserveSourceCollateral), isSigner: false, isWritable: true },
    { pubkey: new PublicKey(accounts.reserveCollateralMint),  isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.reserveLiquiditySupply), isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.userDestinationLiquidity), isSigner: false, isWritable: true },
    { pubkey: SystemProgram.programId,                        isSigner: false, isWritable: false },
    { pubkey: TOKEN_PROGRAM_ID,                               isSigner: false, isWritable: false },
    { pubkey: TOKEN_PROGRAM_ID,                               isSigner: false, isWritable: false },
    { pubkey: SYSVAR_INSTRUCTIONS_PUBKEY,                     isSigner: false, isWritable: false },
  ];
}

/**
 * Build a Kamino Lend native deposit IX (no SDK).
 * Returns a @solana/web3.js TransactionInstruction the caller can drop into
 * a VersionedTransaction.
 */
function buildKaminoDepositIx({ owner, amountLamports, accounts }) {
  const ownerPk = owner instanceof PublicKey ? owner : new PublicKey(owner);
  const amountBN = BN.isBN(amountLamports) ? amountLamports : new BN(amountLamports.toString());
  return new TransactionInstruction({
    programId: KAMINO_LEND_PROGRAM_PK,
    keys: buildDepositAccounts({ owner: ownerPk, accounts }),
    data: encodeDepositData(amountBN),
  });
}

/**
 * Build a Kamino Lend native withdraw IX (no SDK).
 */
function buildKaminoWithdrawIx({ owner, collateralAmount, accounts }) {
  const ownerPk = owner instanceof PublicKey ? owner : new PublicKey(owner);
  const amountBN = BN.isBN(collateralAmount) ? collateralAmount : new BN(collateralAmount.toString());
  return new TransactionInstruction({
    programId: KAMINO_LEND_PROGRAM_PK,
    keys: buildWithdrawAccounts({ owner: ownerPk, accounts }),
    data: encodeWithdrawData(amountBN),
  });
}

/**
 * Wrap one or more IXs into a serialized v0 base64 VersionedTransaction.
 * Adds a Compute Budget bump (Kamino lend IXs typically need ~200k+ CUs).
 */
async function packIxs({ owner, ixs, connection }) {
  const ownerPk = owner instanceof PublicKey ? owner : new PublicKey(owner);
  const cuIx = ComputeBudgetProgram.setComputeUnitLimit({ units: 400_000 });
  const { blockhash } = await connection.getLatestBlockhash("confirmed");
  const message = new TransactionMessage({
    payerKey: ownerPk,
    recentBlockhash: blockhash,
    instructions: [cuIx, ...ixs],
  }).compileToV0Message();
  const tx = new VersionedTransaction(message);
  return Buffer.from(tx.serialize()).toString("base64");
}

module.exports = {
  aliases: ["kamino-finance", "kamino-lend", "kamino-vault"],
  supportedActions: ["deposit", "supply", "withdraw", "unstake", "redeem", "close", "exit"],
  KAMINO_LEND_PROGRAM_ID,

  // Exposed for the pin test + future runtime overrides.
  _internals: {
    KAMINO_LEND_PROGRAM_PK,
    DISC_DEPOSIT,
    DISC_WITHDRAW,
    DISC_INIT_OBLIGATION,
    anchorSighash,
    encodeDepositData,
    encodeWithdrawData,
    buildKaminoDepositIx,
    buildKaminoWithdrawIx,
    packIxs,
  },

  /**
   * Phase 4 lifecycle — Kamino vault withdraw.
   * REST primary; native hand-rolled IX fallback when REST unreachable.
   */
  async buildUnstake({ asset, amount, user, extra = {} }, { connection } = {}) {
    // V7-031 — gate the reserve liquidity mint on the transfer-hook allowlist.
    const hookBlocker = await _kaminoCheckHook(connection, extra);
    if (hookBlocker) return hookBlocker;
    const tryUrls = [
      `${BASE}/v2/transactions/withdraw`,
      `${BASE}/transactions/withdraw`,
    ];
    for (const url of tryUrls) {
      try {
        const ctl = new AbortController();
        const tmo = setTimeout(() => ctl.abort(), 4000);
        let resp;
        try {
          resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: ctl.signal,
            body: JSON.stringify({
              asset, amount, user,
              market: extra.market || extra.market_address || extra.poolAddress,
              reserve: extra.reserve || extra.reserve_address,
              strategy: extra.strategy || extra.strategy_address,
            }),
          });
        } finally {
          clearTimeout(tmo);
        }
        if (!resp.ok) continue;
        const data = await resp.json();
        const tx = data?.transaction || data?.tx;
        if (!tx) continue;
        const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
        if (!sim.ok) {
          const e = new Error(`Kamino REST withdraw simulation failed: ${sim.errStr || "unknown"}`);
          e.simulation = sim;
          throw e;
        }
        return {
          transactions: [
            {
              b64: tx,
              summary: `Kamino withdraw ${amount} ${asset}`,
              description: `Direct Kamino vault withdraw via official REST (${url}).`,
              receiptToken: asset || "USDC",
              redemption_program: KAMINO_LEND_PROGRAM_ID,
              feeUsd: 0.01,
              durationS: 30,
              warnings: [],
              source: "kamino-rest",
              simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
            },
          ],
        };
      } catch (err) {
        if (err?.simulation) throw err;
        continue;
      }
    }

    // Native fallback — hand-rolled Kamino Lend withdraw IX (program
    // KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD). Requires the caller
    // to pass reserve+market+obligation PDAs through extra.accounts.
    if (!connection) {
      throw new Error("Kamino native withdraw fallback requires a Solana connection.");
    }
    if (!extra || !extra.accounts) {
      throw new Error(
        "Kamino REST unreachable and no extra.accounts payload passed for native " +
        "fallback. Pass obligation/lendingMarket/lendingMarketAuthority/reserve/" +
        "reserveSourceCollateral/reserveCollateralMint/reserveLiquiditySupply/" +
        "userDestinationLiquidity to enable hand-rolled IX."
      );
    }
    const ownerPk = new PublicKey(user);
    // Kamino reserves report collateral exchange-rate; the caller already
    // converts the user-facing `amount` into collateral lamports before
    // handing it in via extra.collateralAmountLamports. Fallback to the
    // raw amount if not pre-converted (acceptable for full-position close).
    const collateralLamports = new BN(
      (extra.collateralAmountLamports ?? amount).toString()
    );
    const withdrawIx = buildKaminoWithdrawIx({
      owner: ownerPk,
      collateralAmount: collateralLamports,
      accounts: extra.accounts,
    });
    const b64 = await packIxs({ owner: ownerPk, ixs: [withdrawIx], connection });
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(`Kamino native withdraw simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    return {
      transactions: [
        {
          b64,
          summary: `Kamino native withdraw ${amount} ${asset}`,
          description: (
            `Calls Kamino Lend withdraw_obligation_collateral_and_redeem_reserve_liquidity ` +
            `directly on ${KAMINO_LEND_PROGRAM_ID}. Native IX path — REST was unreachable.`
          ),
          receiptToken: asset || "USDC",
          redemption_program: KAMINO_LEND_PROGRAM_ID,
          feeUsd: 0.005,
          durationS: 30,
          warnings: ["Kamino REST unreachable; routed via hand-rolled Kamino Lend native IX."],
          source: "kamino-native",
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },

  /**
   * Phase C lifecycle — explicit withdraw entrypoint. Delegates to
   * buildUnstake and stamps redemption_program on the result.
   */
  async buildWithdraw({ asset, amount, user, extra = {} }, ctx = {}) {
    const result = await this.buildUnstake({ asset, amount, user, extra }, ctx);
    if (result && Array.isArray(result.transactions)) {
      for (const tx of result.transactions) {
        if (!tx.redemption_program) tx.redemption_program = KAMINO_LEND_PROGRAM_ID;
      }
    }
    return result;
  },

  async quote({ asset }) {
    return {
      expectedAmountOut: null,
      receiptToken: `k${(asset || "USDC").toUpperCase()}`,
      apy: null,
      fees: { protocol: "Kamino Lend native", network: "0.000005 SOL" },
    };
  },

  async build({ asset, amount, user, extra = {} }, { connection } = {}) {
    // V7-031 — gate the reserve liquidity mint on the transfer-hook allowlist
    // before we touch REST or the native fallback. Skipped silently when no
    // mint is resolvable (most Kamino paths derive it from `asset` symbol
    // server-side; transfer-hook checking only fires when extra.* carries one).
    const hookBlocker = await _kaminoCheckHook(connection, extra);
    if (hookBlocker) return hookBlocker;
    // Primary path: real Kamino REST. Tries a couple of endpoint shapes
    // because Kamino has shipped both /transactions/deposit and
    // /v2/transactions/deposit at different points.
    const tryRestEndpoints = [
      `${BASE}/v2/transactions/deposit`,
      `${BASE}/transactions/deposit`,
    ];
    for (const url of tryRestEndpoints) {
      try {
        // 4s timeout per endpoint attempt — without it a stalled Kamino REST
        // host can blow past the sidecar's 12s ceiling, which surfaces a
        // bare TimeoutError to the agent instead of the native fallback.
        const ctl = new AbortController();
        const tmo = setTimeout(() => ctl.abort(), 4000);
        let resp;
        try {
          resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: ctl.signal,
            body: JSON.stringify({
              asset, amount, user,
              market: extra.market || extra.market_address || extra.poolAddress,
              reserve: extra.reserve || extra.reserve_address,
              strategy: extra.strategy || extra.strategy_address,
            }),
          });
        } finally {
          clearTimeout(tmo);
        }
        if (!resp.ok) continue;
        const data = await resp.json();
        const tx = data?.transaction || data?.tx;
        if (!tx) continue;
        const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
        if (!sim.ok) {
          // Real REST returned a tx that simulates failure — let the user see
          // the reason instead of falling through to a synthetic native build
          // that may also fail with the same underlying account-state issue.
          const e = new Error(`Kamino REST tx simulation failed: ${sim.errStr || "unknown"}`);
          e.simulation = sim;
          throw e;
        }
        return {
          transactions: [
            {
              b64: tx,
              summary: `Kamino deposit ${amount} ${asset}`,
              description: `Direct Kamino vault deposit via official REST (${url}).`,
              receiptToken: `k${(asset || "USDC").toUpperCase()}`,
              feeUsd: 0.01,
              durationS: 30,
              warnings: [],
              source: "kamino-rest",
              simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
            },
          ],
        };
      } catch (err) {
        if (err?.simulation) throw err; // propagate genuine sim failures
        continue;                       // try next endpoint shape
      }
    }

    // V7-009 native fallback — hand-rolled Kamino Lend
    // deposit_reserve_liquidity_and_obligation_collateral IX. Mints the
    // REAL reserve collateral receipt (kUSDC, kSOL, etc.) to the user's
    // obligation; no Jupiter proxy, no JLP/JitoSOL substitution.
    if (!connection) {
      throw new Error("Kamino native deposit fallback requires a Solana connection.");
    }
    if (!extra || !extra.accounts) {
      throw new Error(
        "Kamino REST unreachable and no extra.accounts payload passed for native " +
        "fallback. Pass obligation/lendingMarket/lendingMarketAuthority/reserve/" +
        "reserveLiquiditySupply/reserveCollateralMint/reserveDestinationDepositCollateral/" +
        "userSourceLiquidity to enable hand-rolled IX. (No JLP/JitoSOL proxy — spec §3.2.)"
      );
    }
    const ownerPk = new PublicKey(user);
    // Caller pre-converts `amount` (UI units) into liquidity lamports using
    // the reserve's mint decimals; pass via extra.liquidityAmountLamports.
    const liquidityLamports = new BN(
      (extra.liquidityAmountLamports ?? amount).toString()
    );
    const depositIx = buildKaminoDepositIx({
      owner: ownerPk,
      amountLamports: liquidityLamports,
      accounts: extra.accounts,
    });
    const b64 = await packIxs({ owner: ownerPk, ixs: [depositIx], connection });
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(`Kamino native deposit simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    return {
      transactions: [
        {
          b64,
          summary: `Kamino native deposit ${amount} ${asset || "USDC"}`,
          description: (
            `Calls Kamino Lend deposit_reserve_liquidity_and_obligation_collateral ` +
            `directly on ${KAMINO_LEND_PROGRAM_ID}. Real kToken receipt minted to your ` +
            `obligation — no Jupiter/JLP/JitoSOL proxy. REST was unreachable.`
          ),
          receiptToken: `k${(asset || "USDC").toUpperCase()}`,
          redemption_program: KAMINO_LEND_PROGRAM_ID,
          feeUsd: 0.005,
          durationS: 30,
          warnings: ["Kamino REST unreachable; routed via hand-rolled Kamino Lend native IX."],
          source: "kamino-native",
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },
};
