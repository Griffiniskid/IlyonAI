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
// V7-032 WSOL syncNative + closeAccount wiring for native-SOL deposit paths.
const { checkTransferHook, buildSyncNativeIx, buildCloseWsolIx } = require("./_token_safety");

// Wrapped SOL native mint — detect when reserveLiquidityMint == WSOL so the
// adapter can attach syncNative + closeAccount safety metadata around the
// klend deposit IX. Klend reserves can hold WSOL (SOL reserve); when the
// user is depositing native SOL into such a reserve, the wrapped lamports
// MUST be synced into the SPL accounting layer before deposit_reserve_*
// touches them, and any leftover wrapped dust MUST be closeAccount-ed
// post-deposit so the user reclaims the SOL.
const WSOL_MINT_STR = "So11111111111111111111111111111111111111112";

function _kaminoBuildWsolSafetyMeta(ownerPk, mintCandidates) {
  const candidates = (Array.isArray(mintCandidates) ? mintCandidates : [mintCandidates])
    .filter(Boolean)
    .map((m) => (m && m.toBase58 ? m.toBase58() : String(m)));
  if (!candidates.some((s) => s === WSOL_MINT_STR)) return [];
  let splToken;
  try { splToken = require("@solana/spl-token"); } catch (_e) { splToken = null; }
  const wsolMintPk = new PublicKey(WSOL_MINT_STR);
  let wsolAta;
  if (splToken && typeof splToken.getAssociatedTokenAddressSync === "function") {
    wsolAta = splToken.getAssociatedTokenAddressSync(wsolMintPk, ownerPk, true);
  } else {
    wsolAta = WSOL_MINT_STR;
  }
  return [
    { stage: "pre",  kind: "syncNative",   ata: String(wsolAta), ix: buildSyncNativeIx(wsolAta) },
    { stage: "post", kind: "closeAccount", ata: String(wsolAta), ix: buildCloseWsolIx(wsolAta, ownerPk) },
  ];
}

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
// Bare reserve deposit — mints kToken to user wallet without parking it in an
// obligation. Used by direct-supply flows that don't involve borrowing.
// IDL: klend `deposit_reserve_liquidity` (programs/klend/src/lib.rs:134).
const DISC_DEPOSIT_RESERVE = anchorSighash("deposit_reserve_liquidity");

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
 * Encode the bare `deposit_reserve_liquidity` IX data:
 * 8-byte discriminator || u64 LE liquidity_amount.
 *
 * Klend's bare deposit_reserve_liquidity (DISC_DEPOSIT_RESERVE) takes a single
 * `liquidity_amount: u64` arg — identical wire format to the obligation
 * variant, just a different discriminator and account map.
 */
function encodeDepositReserveData(liquidityAmountBN) {
  const buf = Buffer.alloc(8);
  liquidityAmountBN.toArrayLike(Buffer, "le", 8).copy(buf, 0);
  return Buffer.concat([DISC_DEPOSIT_RESERVE, buf]);
}

/**
 * Build the account-meta list for the bare klend `deposit_reserve_liquidity`
 * instruction. Order MUST match the canonical IDL exactly (see
 * programs/klend/src/handlers/handler_deposit_reserve_liquidity.rs
 * `#[derive(Accounts)] struct DepositReserveLiquidity`):
 *
 *   0. owner                       [signer]              — payer
 *   1. reserve                     [writable]            — Reserve state PDA
 *   2. lending_market              [readonly]            — LendingMarket
 *   3. lending_market_authority    [readonly]            — PDA
 *   4. reserve_liquidity_mint      [readonly]            — Token / Token-2022
 *   5. reserve_liquidity_supply    [writable]            — supply vault
 *   6. reserve_collateral_mint     [writable]            — kToken mint
 *   7. user_source_liquidity       [writable]            — user's input ATA
 *   8. user_destination_collateral [writable]            — user's kToken ATA
 *   9. collateral_token_program    [readonly]            — SPL Token (classic)
 *  10. liquidity_token_program     [readonly]            — Token interface
 *  11. instruction_sysvar_account  [readonly]            — Sysvar
 */
function buildDepositReserveAccounts({ owner, accounts }) {
  const need = [
    "reserve",
    "lendingMarket",
    "lendingMarketAuthority",
    "reserveLiquidityMint",
    "reserveLiquiditySupply",
    "reserveCollateralMint",
    "userSourceLiquidity",
    "userDestinationCollateral",
  ];
  for (const k of need) {
    if (!accounts[k]) {
      throw new Error(
        `Kamino klend_reserve deposit: missing required account "${k}". Caller must ` +
        `pass reserve+market+mints+user ATAs through extra.accounts.`
      );
    }
  }
  // Liquidity-side token program may be Token-2022 for some reserves. Caller
  // can override via accounts.liquidityTokenProgram; otherwise default to
  // classic SPL Token (the common case).
  const liquidityTokenProgram = accounts.liquidityTokenProgram
    ? new PublicKey(accounts.liquidityTokenProgram)
    : TOKEN_PROGRAM_ID;
  return [
    { pubkey: owner,                                            isSigner: true,  isWritable: false },
    { pubkey: new PublicKey(accounts.reserve),                  isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.lendingMarket),            isSigner: false, isWritable: false },
    { pubkey: new PublicKey(accounts.lendingMarketAuthority),   isSigner: false, isWritable: false },
    { pubkey: new PublicKey(accounts.reserveLiquidityMint),     isSigner: false, isWritable: false },
    { pubkey: new PublicKey(accounts.reserveLiquiditySupply),   isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.reserveCollateralMint),    isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.userSourceLiquidity),      isSigner: false, isWritable: true  },
    { pubkey: new PublicKey(accounts.userDestinationCollateral), isSigner: false, isWritable: true },
    { pubkey: TOKEN_PROGRAM_ID,                                 isSigner: false, isWritable: false },
    { pubkey: liquidityTokenProgram,                            isSigner: false, isWritable: false },
    { pubkey: SYSVAR_INSTRUCTIONS_PUBKEY,                       isSigner: false, isWritable: false },
  ];
}

/**
 * Build a bare klend `deposit_reserve_liquidity` IX (no SDK). Mints reserve
 * collateral (kToken) directly to the user's destination ATA — does NOT
 * deposit it into an obligation. Use when the caller wants the kToken in
 * their wallet, not as obligation collateral.
 */
function buildDepositReserveLiquidity({
  connection,        // accepted for symmetry; unused inside the IX builder
  market,            // optional convenience: shorthand for accounts.lendingMarket
  reserve,           // optional convenience: shorthand for accounts.reserve
  owner,
  obligation,        // accepted for caller symmetry; ignored (no obligation in bare deposit)
  liquidityAmount,
  userSource,        // optional convenience: shorthand for accounts.userSourceLiquidity
  userDestination,   // optional convenience: shorthand for accounts.userDestinationCollateral
  accounts = {},
} = {}) {
  const ownerPk = owner instanceof PublicKey ? owner : new PublicKey(owner);
  // Merge shorthand args into accounts map so callers can pass either shape.
  const merged = {
    ...accounts,
    reserve:                  accounts.reserve                  || reserve,
    lendingMarket:            accounts.lendingMarket            || market,
    userSourceLiquidity:      accounts.userSourceLiquidity      || userSource,
    userDestinationCollateral: accounts.userDestinationCollateral || userDestination,
  };
  const amountBN = BN.isBN(liquidityAmount)
    ? liquidityAmount
    : new BN(liquidityAmount.toString());
  // obligation arg is intentionally unused — bare deposit has no obligation
  // account. Reference it so linters don't flag the unused param.
  void obligation;
  void connection;
  return new TransactionInstruction({
    programId: KAMINO_LEND_PROGRAM_PK,
    keys: buildDepositReserveAccounts({ owner: ownerPk, accounts: merged }),
    data: encodeDepositReserveData(amountBN),
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
    DISC_DEPOSIT_RESERVE,
    anchorSighash,
    encodeDepositData,
    encodeWithdrawData,
    encodeDepositReserveData,
    buildKaminoDepositIx,
    buildKaminoWithdrawIx,
    buildDepositReserveLiquidity,
    buildDepositReserveAccounts,
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

    // Direct klend reserve supply path — bare deposit_reserve_liquidity.
    // Triggered when the caller explicitly wants the kToken minted to their
    // wallet (NOT parked in an obligation). This is the "supply, don't
    // collateralize" entrypoint that the obligation variant + Kamino REST
    // both bypass. SPEC_COVERAGE: closes the klend.deposit_reserve_liquidity
    // gap.
    if (extra && (extra.kind === "klend_reserve" || extra.kind === "klend_deposit_reserve")) {
      if (!connection) {
        throw new Error("Kamino klend_reserve deposit requires a Solana connection.");
      }
      if (!extra.accounts) {
        throw new Error(
          "Kamino klend_reserve deposit: pass reserve/lendingMarket/lendingMarketAuthority/" +
          "reserveLiquidityMint/reserveLiquiditySupply/reserveCollateralMint/" +
          "userSourceLiquidity/userDestinationCollateral via extra.accounts."
        );
      }
      const ownerPk = new PublicKey(user);
      const liquidityLamports = new BN(
        (extra.liquidityAmountLamports ?? amount).toString()
      );
      const depositIx = buildDepositReserveLiquidity({
        connection,
        owner: ownerPk,
        liquidityAmount: liquidityLamports,
        accounts: extra.accounts,
      });
      const b64 = await packIxs({ owner: ownerPk, ixs: [depositIx], connection });
      const sim = await simulateBase64Tx({ b64, connection });
      if (!sim.ok) {
        const e = new Error(`Kamino klend_reserve deposit simulation failed: ${sim.errStr || "unknown"}`);
        e.simulation = sim;
        throw e;
      }
      // V7-032 — when reserveLiquidityMint is WSOL, attach syncNative +
      // closeAccount safety metadata so the user's WSOL ATA gets refreshed
      // pre-deposit and any leftover wrapped dust is reclaimed post-deposit.
      const reserveLiquidityMint = extra.accounts.reserveLiquidityMint;
      const klendReserveWsolSafety = _kaminoBuildWsolSafetyMeta(ownerPk, [reserveLiquidityMint]);
      return {
        transactions: [
          {
            b64,
            summary: `Kamino klend reserve supply ${amount} ${asset || "USDC"}`,
            description: (
              `Calls Kamino Lend deposit_reserve_liquidity (bare reserve supply) ` +
              `directly on ${KAMINO_LEND_PROGRAM_ID}. Mints kToken to your wallet — ` +
              `no obligation parking, no Jupiter proxy.`
            ),
            receiptToken: `k${(asset || "USDC").toUpperCase()}`,
            redemption_program: KAMINO_LEND_PROGRAM_ID,
            feeUsd: 0.005,
            durationS: 30,
            wsolSafety: klendReserveWsolSafety,
            warnings: klendReserveWsolSafety.length
              ? [`WSOL reserve detected: syncNative + closeAccount safety wired (ATA ${String(klendReserveWsolSafety[0].ata).slice(0, 8)}…).`]
              : [],
            source: "kamino-native-reserve",
            simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
          },
        ],
      };
    }

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
    // V7-032 — obligation-variant deposit may also take WSOL as the underlying
    // liquidity mint (klend SOL reserve). Caller can pass reserveLiquidityMint
    // via extra.accounts or extra.reserveLiquidityMint; gate against WSOL and
    // attach syncNative + closeAccount safety metadata.
    const obligationReserveLiquidityMint =
      extra.accounts.reserveLiquidityMint
      || extra.reserveLiquidityMint
      || extra.reserve_liquidity_mint;
    const obligationWsolSafety = _kaminoBuildWsolSafetyMeta(
      ownerPk,
      [obligationReserveLiquidityMint],
    );
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
          wsolSafety: obligationWsolSafety,
          warnings: [
            "Kamino REST unreachable; routed via hand-rolled Kamino Lend native IX.",
            ...(obligationWsolSafety.length
              ? [`WSOL reserve detected: syncNative + closeAccount safety wired (ATA ${String(obligationWsolSafety[0].ata).slice(0, 8)}…).`]
              : []),
          ],
          source: "kamino-native",
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },
};
