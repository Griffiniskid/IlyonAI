/**
 * Sanctum Infinity (S-Controller) — native AddLiquidity IX (spec §9l).
 *
 * Replaces the previous Jupiter-swap proxy. Builds a hand-rolled
 * shank-style AddLiquidity instruction against the S-Controller program
 * (5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx) so the user mints INF
 * at the protocol's exchange rate — no Jupiter aggregator tax — and the
 * receipt is a verifiable INF SPL balance delta.
 *
 * V7-032 — WSOL syncNative + closeAccount NOT needed.
 *   AddLiquidity accepts ONLY pre-existing LSTs (MSOL/JITOSOL/BSOL via
 *   `PINNED_LSTS`); `resolveLstFromSymbol()` hard-throws on any input
 *   that is not in that allowlist (including raw SOL / WSOL). Sanctum
 *   has no native-SOL entry path — the user must already hold an LST
 *   SPL balance, and the receipt INF is its own distinct SPL mint. No
 *   WSOL ATA is ever touched, so syncNative is meaningless and there is
 *   no ATA to closeAccount. Verdict: gate INTENTIONALLY NOT WIRED — no
 *   native-SOL path exists. (Allowlisted in
 *   tests/defi/test_wsol_sync_close_audit.py.)
 *
 * Instruction layout (borsh, 22 bytes total):
 *   u8  disc                = 3
 *   u8  lst_value_calc_accs = remaining-account count for SOL-value calc
 *   u32 lst_index           LE
 *   u64 lst_amount          LE  (atoms in lst_mint's decimals)
 *   u64 min_lp_out          LE  (atoms in INF decimals=9)
 *
 * Accounts (11 fixed in order, then `lst_value_calc_accs` remaining):
 *   0  signer                     (user, writable, signer)
 *   1  lst_mint                   (readonly)
 *   2  src_lst_acc                (user LST ATA, writable)
 *   3  dst_lp_acc                 (user INF ATA, writable)
 *   4  lp_token_mint = INF        (writable)
 *   5  protocol_fee_accumulator   (ATA of protocol_fee PDA, writable)
 *   6  lst_token_program          (readonly)
 *   7  lp_token_program = TOKEN   (readonly)
 *   8  pool_state PDA             (writable)
 *   9  lst_state_list PDA         (writable)
 *   10 pool_reserves              (ATA of pool_state, writable)
 *   ... remaining: calc_program + calc-specific + pricing (flat-fee)
 *
 * PDAs:
 *   pool_state     = find_pda([b"state"],            PROGRAM_ID)
 *   lst_state_list = find_pda([b"lst-state-list"],   PROGRAM_ID)
 *   protocol_fee   = find_pda([b"protocol-fee"],     PROGRAM_ID)
 *
 * LST index resolution: read lst_state_list account, stride 80 bytes
 *   (1+1+1+5+8+32+32). If `data.length % STRIDE == 8`, skip the 8-byte
 *   borsh length prefix. Walk records, mint at offset 1+1+1+5+8 = 16 → +32.
 *   Returns the matching record's index.
 */
const {
  PublicKey,
  Transaction,
  TransactionInstruction,
  ComputeBudgetProgram,
} = require("@solana/web3.js");
const {
  TOKEN_PROGRAM_ID,
  getAssociatedTokenAddressSync,
  createAssociatedTokenAccountIdempotentInstruction,
} = require("@solana/spl-token");
const { humanToAtoms } = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");
const { checkTxAccountCount } = require("./altSplit");
// V7-031 Token-2022 transfer-hook allowlist enforcement.
const { checkTransferHook } = require("./_token_safety");

const PROGRAM_ID = new PublicKey("5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx");
const INF_MINT = new PublicKey("5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm");
const FLAT_FEE_PROGRAM = new PublicKey("1barXKncTeQbCfDLPyx5GbXuxBn8Z5JZjJ7DMzMqz9z");
const DEFAULT_SOL_VALUE_CALC_PROGRAM = new PublicKey(
  "sp1V4h2gWorkGhVcazBc22Hfo2f5sd7jcjT4EDPrWFF",
);

// Pinned LST set — these are the live mints we know the protocol indexes.
// `lst_index` is ALWAYS resolved on-chain at build time; the table only
// pins (mint, decimals, token_program) so we don't hand-roll an account
// resolver per LST. Extending requires only adding a mint here.
const PINNED_LSTS = {
  MSOL: {
    mint: new PublicKey("mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"),
    decimals: 9,
    tokenProgram: TOKEN_PROGRAM_ID,
  },
  JITOSOL: {
    mint: new PublicKey("J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"),
    decimals: 9,
    tokenProgram: TOKEN_PROGRAM_ID,
  },
  BSOL: {
    mint: new PublicKey("bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1"),
    decimals: 9,
    tokenProgram: TOKEN_PROGRAM_ID,
  },
};

const LST_RECORD_STRIDE = 80; // 1+1+1+5+8+32+32
const LST_MINT_OFFSET = 16;   // 1+1+1+5+8

function findPda(seedStrs) {
  const seeds = seedStrs.map((s) => Buffer.from(s, "utf8"));
  const [pda] = PublicKey.findProgramAddressSync(seeds, PROGRAM_ID);
  return pda;
}

/**
 * Walk the lst_state_list account buffer at 80-byte stride and return the
 * 0-based index of the record whose mint equals `lstMint`. Throws if not
 * found — caller must surface as a typed error.
 */
function resolveLstIndex(data, lstMint) {
  if (!data || data.length === 0) {
    throw new Error("Sanctum lst_state_list account empty.");
  }
  // Some serializations prefix the slice with an 8-byte borsh length.
  const headerSkip = data.length % LST_RECORD_STRIDE === 8 ? 8 : 0;
  const payload = data.slice(headerSkip);
  const recordCount = Math.floor(payload.length / LST_RECORD_STRIDE);
  for (let i = 0; i < recordCount; i++) {
    const off = i * LST_RECORD_STRIDE + LST_MINT_OFFSET;
    const candidate = new PublicKey(payload.slice(off, off + 32));
    if (candidate.equals(lstMint)) {
      return i;
    }
  }
  throw new Error(`Sanctum: lst_mint ${lstMint.toBase58()} not in lst_state_list.`);
}

/**
 * Encode the 22-byte AddLiquidity instruction data.
 *   disc(1) | calc_accs(1) | lst_index(4) | lst_amount(8) | min_lp_out(8)
 */
function encodeAddLiquidityData({ lstValueCalcAccs, lstIndex, lstAmount, minLpOut }) {
  const buf = Buffer.alloc(22);
  buf.writeUInt8(3, 0);                                    // discriminator
  buf.writeUInt8(lstValueCalcAccs & 0xff, 1);              // calc-accs count
  buf.writeUInt32LE(lstIndex >>> 0, 2);                    // lst_index LE
  buf.writeBigUInt64LE(BigInt(lstAmount), 6);              // lst_amount LE
  buf.writeBigUInt64LE(BigInt(minLpOut), 14);              // min_lp_out LE
  return buf;
}

function resolveLstFromSymbol(asset) {
  const sym = String(asset || "").toUpperCase();
  const hit = PINNED_LSTS[sym];
  if (!hit) {
    throw new Error(
      `Sanctum native AddLiquidity requires a supported LST input (MSOL/JITOSOL/BSOL); got ${sym}.`,
    );
  }
  return { sym, ...hit };
}

module.exports = {
  aliases: ["sanctum-infinity", "sanctum-liquid-staking", "sanctum-inf"],
  supportedActions: ["deposit", "supply", "stake"],

  async quote({ asset, amount }) {
    return {
      expectedAmountOut: amount,
      receiptToken: "INF",
      apy: null,
      fees: {
        protocol: "Sanctum S-Controller AddLiquidity (flat-fee pricing)",
        network: "0.000005 SOL",
      },
      receiptMint: INF_MINT.toBase58(),
      redemption_program: PROGRAM_ID.toBase58(),
      inputAsset: (asset || "").toUpperCase() || null,
    };
  },

  /**
   * Build the native AddLiquidity transaction.
   * Required: connection.
   * Optional via `extra`:
   *   - solValueCalcProgram: override default sanctum-spl calc program.
   *   - calcAccs: AccountMeta[] for the LST-specific SOL-value-calc accs.
   *     Each entry: { pubkey: "...", isSigner: bool, isWritable: bool }
   */
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }, { connection } = {}) {
    if (!connection) {
      throw new Error("Sanctum build requires a Solana connection.");
    }
    const userPubkey = new PublicKey(user);
    const lst = resolveLstFromSymbol(asset);

    // Atomic amount in LST's decimals — BigInt path, no float loss.
    const lstAmount = humanToAtoms(amount, lst.decimals);
    if (lstAmount <= 0n) {
      throw new Error(`Sanctum AddLiquidity amount must be > 0 (got ${amount}).`);
    }

    // V7-031 — gate the LST input mint AND the INF receipt mint on the
    // Token-2022 transfer-hook allowlist before we touch on-chain state.
    for (const m of [lst.mint, INF_MINT]) {
      const hookCheck = await checkTransferHook(connection, m);
      if (!hookCheck.ok) {
        return {
          kind: "blocker",
          code: "TRANSFER_HOOK_NOT_ALLOWED",
          blocker: "TRANSFER_HOOK_NOT_ALLOWED",
          error: "TRANSFER_HOOK_NOT_ALLOWED",
          message:
            `Sanctum build blocked: mint ${m.toBase58()} declares a Token-2022 ` +
            `transfer hook (${hookCheck.hookProgramId}) that is not in the sidecar allowlist.`,
          mint: m.toBase58(),
          hookProgramId: hookCheck.hookProgramId,
          transactions: [],
        };
      }
    }

    // Derive PDAs + reserve/fee ATAs.
    const poolState = findPda(["state"]);
    const lstStateList = findPda(["lst-state-list"]);
    const protocolFee = findPda(["protocol-fee"]);
    const poolReserves = getAssociatedTokenAddressSync(
      lst.mint,
      poolState,
      true,                       // allowOwnerOffCurve — pool_state is a PDA
      lst.tokenProgram,
    );
    const protocolFeeAccumulator = getAssociatedTokenAddressSync(
      lst.mint,
      protocolFee,
      true,
      lst.tokenProgram,
    );

    // Resolve lst_index from on-chain lst_state_list (cannot guess).
    const lstListAcc = await connection.getAccountInfo(lstStateList);
    if (!lstListAcc) {
      throw new Error("Sanctum lst_state_list account not found on chain.");
    }
    const lstIndex = resolveLstIndex(lstListAcc.data, lst.mint);

    // Caller-supplied calc + pricing remaining accounts. Defaults are
    // sanctum-spl calc program (live) + flat-fee pricing program. The
    // calc-specific accounts (pool_state, validator_list, etc. per LST)
    // MUST be passed via extra.calcAccs because they're per-stake-pool
    // and we refuse to guess them.
    const solValueCalcProgram = new PublicKey(
      extra.solValueCalcProgram || DEFAULT_SOL_VALUE_CALC_PROGRAM,
    );
    const calcAccsRaw = Array.isArray(extra.calcAccs) ? extra.calcAccs : [];
    const remainingAccs = [
      // calc_program
      { pubkey: solValueCalcProgram, isSigner: false, isWritable: false },
      // calc-specific (caller-supplied)
      ...calcAccsRaw.map((a) => ({
        pubkey: new PublicKey(a.pubkey),
        isSigner: !!a.isSigner,
        isWritable: !!a.isWritable,
      })),
      // flat-fee pricing program
      { pubkey: FLAT_FEE_PROGRAM, isSigner: false, isWritable: false },
    ];
    const lstValueCalcAccs = remainingAccs.length;

    // Slippage → min_lp_out. INF and SOL both 1e9 atoms; LST atoms are
    // also 1e9 here (all pinned LSTs are 9-dec) so the 1:1 rate floor
    // pre-haircut is a safe lower-bound that the on-chain calc will
    // refine. The slippageBps haircut keeps us from blowing past
    // protocol fee + exchange-rate drift.
    const slip = BigInt(Math.max(0, Math.min(10_000, slippageBps)));
    const minLpOut = (lstAmount * (10_000n - slip)) / 10_000n;

    const data = encodeAddLiquidityData({
      lstValueCalcAccs,
      lstIndex,
      lstAmount: lstAmount.toString(),
      minLpOut: minLpOut.toString(),
    });

    // Derive user ATAs and emit idempotent-create ixs so first-time
    // depositors don't hit AccountNotFound.
    const srcLstAcc = getAssociatedTokenAddressSync(
      lst.mint,
      userPubkey,
      false,
      lst.tokenProgram,
    );
    const dstLpAcc = getAssociatedTokenAddressSync(
      INF_MINT,
      userPubkey,
      false,
      TOKEN_PROGRAM_ID,
    );

    const keys = [
      { pubkey: userPubkey,             isSigner: true,  isWritable: true  },
      { pubkey: lst.mint,               isSigner: false, isWritable: false },
      { pubkey: srcLstAcc,              isSigner: false, isWritable: true  },
      { pubkey: dstLpAcc,               isSigner: false, isWritable: true  },
      { pubkey: INF_MINT,               isSigner: false, isWritable: true  },
      { pubkey: protocolFeeAccumulator, isSigner: false, isWritable: true  },
      { pubkey: lst.tokenProgram,       isSigner: false, isWritable: false },
      { pubkey: TOKEN_PROGRAM_ID,       isSigner: false, isWritable: false },
      { pubkey: poolState,              isSigner: false, isWritable: true  },
      { pubkey: lstStateList,           isSigner: false, isWritable: true  },
      { pubkey: poolReserves,           isSigner: false, isWritable: true  },
      ...remainingAccs,
    ];

    const addLiquidityIx = new TransactionInstruction({
      programId: PROGRAM_ID,
      keys,
      data,
    });

    const tx = new Transaction();
    tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 600_000 }));
    // Make sure both ATAs exist before the program touches them.
    tx.add(
      createAssociatedTokenAccountIdempotentInstruction(
        userPubkey,
        srcLstAcc,
        userPubkey,
        lst.mint,
        lst.tokenProgram,
      ),
    );
    tx.add(
      createAssociatedTokenAccountIdempotentInstruction(
        userPubkey,
        dstLpAcc,
        userPubkey,
        INF_MINT,
        TOKEN_PROGRAM_ID,
      ),
    );
    tx.add(addLiquidityIx);
    tx.feePayer = userPubkey;
    const { blockhash } = await connection.getLatestBlockhash("confirmed");
    tx.recentBlockhash = blockhash;

    const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
    const b64 = raw.toString("base64");

    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(`Sanctum AddLiquidity simulation failed: ${sim.errStr || "unknown"}`);
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
          summary: `Sanctum AddLiquidity ${amount} ${lst.sym} → INF`,
          description: (
            `Hand-rolled S-Controller AddLiquidity IX (disc=3) against program ` +
            `${PROGRAM_ID.toBase58()}. Mints INF (${INF_MINT.toBase58()}) at the ` +
            `protocol's on-chain exchange rate using the pinned flat-fee pricing ` +
            `program and the caller-supplied SOL-value calc program for ${lst.sym}. ` +
            `Min LP out floored at ${minLpOut.toString()} atoms after ${slippageBps} bps slippage.`
          ),
          receiptToken: "INF",
          receiptMint: INF_MINT.toBase58(),
          redemption_program: PROGRAM_ID.toBase58(),
          feeUsd: 0.01,
          durationS: 20,
          warnings: [
            "Native Sanctum AddLiquidity — exchange rate enforced on-chain via flat-fee pricing program.",
            calcAccsRaw.length === 0
              ? `extra.calcAccs was empty — sim will fail unless ${lst.sym}'s SOL-value calc accounts are provided.`
              : `Using ${calcAccsRaw.length} caller-supplied calc account(s) for ${lst.sym}.`,
            ...altWarn,
          ],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },

  // Exposed for unit tests + the sidecar's lst_state_list parser plug-points.
  _internal: {
    PROGRAM_ID,
    INF_MINT,
    FLAT_FEE_PROGRAM,
    DEFAULT_SOL_VALUE_CALC_PROGRAM,
    PINNED_LSTS,
    findPda,
    resolveLstIndex,
    encodeAddLiquidityData,
  },
};
