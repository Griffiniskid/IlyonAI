/**
 * Meteora DAMM v2 + Dynamic Vault native adapter.
 * Mode select:
 *   extra.vaultMint or extra.vaultTokenMint → VaultImpl.deposit
 *   extra.poolId → CpAmm.createPositionAndAddLiquidity
 */
const { PublicKey, Keypair, ComputeBudgetProgram, Transaction, TransactionMessage, VersionedTransaction } = require("@solana/web3.js");
const { getMint, getEpochInfo, TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID } = require("@solana/spl-token");
const BN = require("bn.js");
let CpAmm;
let VaultImpl;
try { CpAmm = require("@meteora-ag/cp-amm-sdk").CpAmm; } catch (e) { CpAmm = null; }
try { const m = require("@meteora-ag/vault-sdk"); VaultImpl = m.default || m.VaultImpl || m; } catch (e) { VaultImpl = null; }
const { humanToAtoms } = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");

const DAMM_V2_PROGRAM = new PublicKey("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG");
const VAULT_PROGRAM   = new PublicKey("24Uqj9JCLxUeoC3hGfh5W3s9FM9uCHDS2SG3LYwBpyTi");

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
