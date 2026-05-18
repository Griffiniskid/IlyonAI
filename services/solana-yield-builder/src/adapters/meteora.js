/**
 * Meteora DAMM v2 + Dynamic Vault native adapter.
 * Mode select:
 *   extra.vaultMint or extra.vaultTokenMint → VaultImpl.deposit
 *   extra.poolId → CpAmm.createPositionAndAddLiquidity
 */
const { PublicKey, Keypair, ComputeBudgetProgram, Transaction, TransactionInstruction, TransactionMessage, VersionedTransaction } = require("@solana/web3.js");
const { getMint, getEpochInfo, TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID } = require("@solana/spl-token");
const BN = require("bn.js");
const crypto = require("crypto");
let CpAmm;
let VaultImpl;
try { CpAmm = require("@meteora-ag/cp-amm-sdk").CpAmm; } catch (e) { CpAmm = null; }
try { const m = require("@meteora-ag/vault-sdk"); VaultImpl = m.default || m.VaultImpl || m; } catch (e) { VaultImpl = null; }
const { humanToAtoms } = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");
// V7-031 Token-2022 transfer-hook allowlist enforcement.
const { checkTransferHook } = require("./_token_safety");

function _meteoraHookBlocker(mintStr, hookProgramId) {
  return {
    kind: "blocker",
    code: "TRANSFER_HOOK_NOT_ALLOWED",
    blocker: "TRANSFER_HOOK_NOT_ALLOWED",
    error: "TRANSFER_HOOK_NOT_ALLOWED",
    message:
      `Meteora build blocked: input mint ${mintStr} declares a Token-2022 transfer ` +
      `hook (${hookProgramId}) that is not in the sidecar allowlist. Risk team must ` +
      `approve the hook program before this pool routes here.`,
    mint: mintStr,
    hookProgramId,
    transactions: [],
  };
}

const DAMM_V2_PROGRAM = new PublicKey("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG");
const VAULT_PROGRAM   = new PublicKey("24Uqj9JCLxUeoC3hGfh5W3s9FM9uCHDS2SG3LYwBpyTi");

// V7-060 — Meteora DLMM (Dynamic Liquidity Market Maker).
// Program ID per https://docs.meteora.ag/dlmm/dlmm-overview / on-chain mainnet.
const DLMM_PROGRAM = new PublicKey("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo");

function _anchorDiscMet(name) {
  return crypto.createHash("sha256").update(`global:${name}`).digest().slice(0, 8);
}
const REMOVE_LIQUIDITY_BY_RANGE_DISC = _anchorDiscMet("remove_liquidity_by_range");

/**
 * V7-060 — Meteora DLMM remove_liquidity_by_range IX builder.
 *
 * Hand-rolled Anchor IX for the on-chain `remove_liquidity_by_range` entrypoint.
 * Encodes binIdFrom/binIdTo as i32 LE + bps_to_remove (u16 LE, defaults 10000 = 100%)
 * in the instruction data payload.
 *
 * Layout: 8 disc | 4 binIdFrom (i32 LE) | 4 binIdTo (i32 LE) | 2 bpsToRemove (u16 LE)
 *
 * Account order (per DLMM IDL):
 *   0. position           [mut]    — the LB position pubkey
 *   1. lbPair             [mut]
 *   2. binArrayBitmapExt  [optional, mut]
 *   3. userTokenX         [mut]
 *   4. userTokenY         [mut]
 *   5. reserveX           [mut]
 *   6. reserveY           [mut]
 *   7. tokenXMint         [readonly]
 *   8. tokenYMint         [readonly]
 *   9. binArrayLower      [mut]
 *  10. binArrayUpper      [mut]
 *  11. sender             [signer]
 *  12. tokenXProgram      [readonly]
 *  13. tokenYProgram      [readonly]
 *  14. eventAuthority     [readonly]
 *  15. program            [readonly] — self-ref for CPI events
 *
 * Caller passes a `position` pubkey plus the rest via `opts.accounts.*`.
 * For the dependency-light hand-roll, this returns the minimal IX with
 * only the position + sender + program-self accounts wired up when opts.accounts
 * is absent — sim will catch missing accounts at simulation time.
 */
function buildRemoveByRange(positionPubkey, binIdFrom, binIdTo, opts = {}) {
  const position = positionPubkey instanceof PublicKey
    ? positionPubkey
    : new PublicKey(positionPubkey);
  const from = parseInt(binIdFrom, 10);
  const to = parseInt(binIdTo, 10);
  if (!Number.isInteger(from) || !Number.isInteger(to)) {
    throw new Error(`Meteora DLMM removeByRange: binIdFrom/binIdTo must be integers (got ${binIdFrom}/${binIdTo}).`);
  }
  if (to < from) {
    throw new Error(`Meteora DLMM removeByRange: binIdTo (${to}) must be >= binIdFrom (${from}).`);
  }
  const bpsToRemove = Number.isFinite(opts.bpsToRemove) ? Math.max(0, Math.min(10000, opts.bpsToRemove | 0)) : 10000;

  // Encode IX data: disc(8) || binIdFrom(i32 LE) || binIdTo(i32 LE) || bpsToRemove(u16 LE)
  const data = Buffer.alloc(8 + 4 + 4 + 2);
  REMOVE_LIQUIDITY_BY_RANGE_DISC.copy(data, 0);
  data.writeInt32LE(from, 8);
  data.writeInt32LE(to, 12);
  data.writeUInt16LE(bpsToRemove, 16);

  const accounts = opts.accounts || {};
  const sender = opts.sender
    ? (opts.sender instanceof PublicKey ? opts.sender : new PublicKey(opts.sender))
    : position; // sim will reject if caller forgot; never silently fake-sign
  // Account-meta list — fields callers don't supply default to the position
  // pubkey as a deterministic placeholder so the data-encoding test can
  // exercise IX structure without a full account dictionary.
  const acctOr = (k) => (accounts[k] ? new PublicKey(accounts[k]) : position);
  const keys = [
    { pubkey: position,                     isSigner: false, isWritable: true  }, // 0 position
    { pubkey: acctOr("lbPair"),             isSigner: false, isWritable: true  }, // 1 lbPair
    { pubkey: acctOr("binArrayBitmapExt"),  isSigner: false, isWritable: true  }, // 2 binArrayBitmapExt
    { pubkey: acctOr("userTokenX"),         isSigner: false, isWritable: true  }, // 3 userTokenX
    { pubkey: acctOr("userTokenY"),         isSigner: false, isWritable: true  }, // 4 userTokenY
    { pubkey: acctOr("reserveX"),           isSigner: false, isWritable: true  }, // 5 reserveX
    { pubkey: acctOr("reserveY"),           isSigner: false, isWritable: true  }, // 6 reserveY
    { pubkey: acctOr("tokenXMint"),         isSigner: false, isWritable: false }, // 7 tokenXMint
    { pubkey: acctOr("tokenYMint"),         isSigner: false, isWritable: false }, // 8 tokenYMint
    { pubkey: acctOr("binArrayLower"),      isSigner: false, isWritable: true  }, // 9 binArrayLower
    { pubkey: acctOr("binArrayUpper"),      isSigner: false, isWritable: true  }, // 10 binArrayUpper
    { pubkey: sender,                       isSigner: true,  isWritable: true  }, // 11 sender
    { pubkey: TOKEN_PROGRAM_ID,             isSigner: false, isWritable: false }, // 12 tokenXProgram
    { pubkey: TOKEN_PROGRAM_ID,             isSigner: false, isWritable: false }, // 13 tokenYProgram
    { pubkey: acctOr("eventAuthority"),     isSigner: false, isWritable: false }, // 14 eventAuthority
    { pubkey: DLMM_PROGRAM,                 isSigner: false, isWritable: false }, // 15 program (self)
  ];
  return new TransactionInstruction({
    programId: DLMM_PROGRAM,
    keys,
    data,
  });
}

async function serializeTx(tx, signers, owner, connection) {
  const { blockhash } = await connection.getLatestBlockhash("confirmed");
  if (tx instanceof Transaction) {
    tx.feePayer = owner; tx.recentBlockhash = blockhash;
    if (signers?.length) tx.partialSign(...signers);
    return Buffer.from(tx.serialize({ requireAllSignatures: false, verifySignatures: false })).toString("base64");
  }
  if (typeof tx.build === "function") {
    const built = await tx.build();
    if (signers?.length) built.sign(signers);
    return Buffer.from(built.serialize()).toString("base64");
  }
  if (signers?.length && typeof tx.sign === "function") tx.sign(signers);
  return Buffer.from(tx.serialize()).toString("base64");
}

module.exports = {
  aliases: ["meteora-damm","meteora-damm-v2","meteora-cp-amm","meteora-vault","meteora-dynamic-vault","meteora-dlmm"],
  supportedActions: ["deposit","deposit_lp","supply"],

  // V7-060 exports — Meteora DLMM remove_liquidity_by_range.
  DLMM_PROGRAM: DLMM_PROGRAM.toBase58(),
  buildRemoveByRange,
  _internals: {
    DLMM_PROGRAM,
    REMOVE_LIQUIDITY_BY_RANGE_DISC,
    buildRemoveByRange,
  },

  async quote({ asset }) {
    return { expectedAmountOut: null, receiptToken: "meteora-position-nft", apy: null,
             fees: { protocol: "Meteora DAMM v2 native (~0.25% LP fee)", network: "0.00001 SOL" } };
  },

  async build({ protocol, asset, amount, user, extra = {}, slippageBps = 50 }, { connection }) {
    if (!connection) throw new Error("Meteora build requires a Solana connection.");
    const owner = new PublicKey(user);

    // Mode B: Dynamic Vault
    if (extra.vaultMint || extra.vaultTokenMint) {
      if (!VaultImpl) throw new Error("Meteora vault-sdk not installed — npm install @meteora-ag/vault-sdk required.");
      const tokenMint = new PublicKey(extra.vaultTokenMint || extra.vaultMint);
      // V7-031 — refuse non-allowlisted Token-2022 transfer hooks on the vault deposit mint.
      const vaultHook = await checkTransferHook(connection, tokenMint);
      if (!vaultHook.ok) return _meteoraHookBlocker(tokenMint.toBase58(), vaultHook.hookProgramId);
      const vault = await VaultImpl.create(connection, tokenMint);
      const decimals = (await getMint(connection, tokenMint, "confirmed", TOKEN_PROGRAM_ID)).decimals;
      const amt = humanToAtoms(amount, decimals);
      if (amt <= 0n) throw new Error(`Meteora vault: amount '${amount}' too small.`);
      const tx = await vault.deposit(owner, new BN(amt.toString()));
      const b64 = await serializeTx(tx, null, owner, connection);
      const sim = await simulateBase64Tx({ b64, connection });
      if (!sim.ok) { const e = new Error(`Meteora vault sim failed: ${sim.errStr || "unknown"}`); e.simulation = sim; throw e; }
      return { transactions: [{
        b64, summary: `Meteora Dynamic Vault deposit ${amount} ${asset || ""}`,
        description: `Deposit via VAULT_PROGRAM ${VAULT_PROGRAM.toBase58()}.`,
        receiptToken: "meteora-vault-share",
        receiptMint: vault.vaultState?.lpMint?.toBase58() || null,
        redemption_program: VAULT_PROGRAM.toBase58(),
        feeUsd: 0.01, durationS: 20, warnings: [],
        simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
      }] };
    }

    // Mode A: DAMM v2
    if (!CpAmm) throw new Error("Meteora cp-amm-sdk not installed.");
    const poolPubkey = new PublicKey(extra.poolId || extra.poolAddress || extra.pool_address);
    const cpAmm = new CpAmm(connection);
    const pool = await cpAmm.fetchPoolState(poolPubkey);

    const tokenAMint = pool.tokenAMint;
    const tokenBMint = pool.tokenBMint;
    // V7-031 — gate both pool sides on the Token-2022 transfer-hook allowlist.
    for (const m of [tokenAMint, tokenBMint]) {
      if (!m) continue;
      const hookCheck = await checkTransferHook(connection, m);
      if (!hookCheck.ok) {
        return _meteoraHookBlocker(m.toBase58 ? m.toBase58() : String(m), hookCheck.hookProgramId);
      }
    }
    const tokenAProgram = pool.tokenAFlag ? TOKEN_2022_PROGRAM_ID : TOKEN_PROGRAM_ID;
    const tokenBProgram = pool.tokenBFlag ? TOKEN_2022_PROGRAM_ID : TOKEN_PROGRAM_ID;
    const isTokenA = (asset || "").toUpperCase() === pool.tokenASymbol?.toUpperCase();
    const inMintInfo = isTokenA
      ? await getMint(connection, tokenAMint, "confirmed", tokenAProgram)
      : await getMint(connection, tokenBMint, "confirmed", tokenBProgram);
    const decimals = inMintInfo.decimals;
    const inAtoms = new BN(humanToAtoms(amount, decimals).toString());
    if (inAtoms.lten(0)) throw new Error(`Meteora: amount '${amount}' too small.`);

    const epoch = (await getEpochInfo(connection)).epoch;
    const quote = await cpAmm.getDepositQuote({
      inAmount: inAtoms, isTokenA,
      minSqrtPrice: pool.minSqrtPrice ?? new BN(0),
      maxSqrtPrice: pool.maxSqrtPrice ?? new BN("18446744073709551615"),
      sqrtPrice: pool.sqrtPrice,
      inputTokenInfo: { mint: inMintInfo, currentEpoch: epoch },
      collectFeeMode: pool.collectFeeMode,
      tokenAAmount: pool.tokenAReserve, tokenBAmount: pool.tokenBReserve, liquidity: pool.liquidity,
    });

    const slipNum = BigInt(Math.max(1, slippageBps));
    const minA = isTokenA ? quote.actualInputAmount : quote.outputAmount;
    const minB = isTokenA ? quote.outputAmount : quote.actualInputAmount;
    const threshA = new BN(((BigInt(minA.toString()) * (10_000n - slipNum)) / 10_000n).toString());
    const threshB = new BN(((BigInt(minB.toString()) * (10_000n - slipNum)) / 10_000n).toString());

    const positionNft = Keypair.generate();
    const txBuilder = await cpAmm.createPositionAndAddLiquidity({
      owner, pool: poolPubkey, positionNft: positionNft.publicKey,
      liquidityDelta: quote.liquidityDelta,
      maxAmountTokenA: isTokenA ? inAtoms : new BN(minA.toString()),
      maxAmountTokenB: isTokenA ? new BN(minB.toString()) : inAtoms,
      tokenAAmountThreshold: threshA, tokenBAmountThreshold: threshB,
      tokenAMint, tokenBMint, tokenAProgram, tokenBProgram,
    });
    const b64 = await serializeTx(txBuilder, [positionNft], owner, connection);
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) { const e = new Error(`Meteora DAMM v2 sim failed: ${sim.errStr || "unknown"}`); e.simulation = sim; throw e; }
    return { transactions: [{
      b64,
      summary: `Meteora DAMM v2 createPositionAndAddLiquidity (${pool.tokenASymbol || "A"}-${pool.tokenBSymbol || "B"})`,
      description: `DAMM v2 program ${DAMM_V2_PROGRAM.toBase58()}. NFT receipt ${positionNft.publicKey.toBase58()}.`,
      receiptToken: "meteora-position-nft",
      receiptMint: positionNft.publicKey.toBase58(),
      position_nft: positionNft.publicKey.toBase58(),
      redemption_program: DAMM_V2_PROGRAM.toBase58(),
      feeUsd: 0.02, durationS: 30,
      warnings: ["Position is NFT-gated.", "Transfer-hook Token-2022 mints unsupported on DAMM v2."],
      simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
    }] };
  },
};
