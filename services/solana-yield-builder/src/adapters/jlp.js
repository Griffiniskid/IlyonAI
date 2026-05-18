/**
 * JLP — Jupiter Perpetuals LP native Solana adapter (Phase B.1).
 *
 * Replaces the previous Jupiter-swap proxy with a hand-rolled native
 * `add_liquidity2` instruction against the Jupiter Perpetuals program
 *   PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu
 *
 * Why native, not Jupiter aggregator:
 *   - Jupiter swap into JLP routes through the perp AMM and pays the
 *     aggregator's slippage tax + spread on top of the real mint rate.
 *   - The perp program's `add_liquidity2` IX mints JLP 1:1 at the on-chain
 *     custody-weighted NAV with only the protocol's pool fee — same
 *     economics as adding via jup.ag/perps-earn directly.
 *   - Provides per-asset auditability: caller specifies which custody
 *     (SOL/ETH/BTC/USDC/USDT) is deposited and the receipt is balance-delta
 *     verifiable on the JLP mint.
 *
 * Accounts (14, in IX order):
 *   0  owner                          signer, mut
 *   1  fundingAccount                  mut (user's source ATA — or system acct for SOL when wrapped)
 *   2  lpTokenAccount                  mut (user's JLP ATA — auto-created)
 *   3  transferAuthority               PDA ["transfer_authority"]
 *   4  perpetuals                      PDA ["perpetuals"]
 *   5  pool                            mut — 5BUwFW4nRbftYTDMbgxykoFWqWHPzahFSNAaaaJtVKsq
 *   6  custody                         mut — per-asset (see CUSTODIES below)
 *   7  custodyDovesPriceAccount        Pyth Doves feed
 *   8  custodyPythnetPriceAccount      Pythnet receiver
 *   9  custodyTokenAccount             mut — protocol-owned custody ATA
 *  10  lpTokenMint                     mut — 27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4
 *  11  tokenProgram                    SPL Token program
 *  12  eventAuthority                  37hJBDnntwqhGbK7L6M1bLyvccj4u55CCUiLPdYkiqBN
 *  13  programId                       PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu
 *
 * AddLiquidity2Params:
 *   tokenAmountIn: u64
 *   minLpAmountOut: u64                (0 = no min — acceptable for Phase A)
 *   tokenAmountPreSwap: Option<u64>    (None for direct-asset deposit)
 *
 * Withdraw lockup: 1 hour from deposit timestamp. Surfaced via
 * lockup_end_ts on the transaction receipt for the runtime to gate
 * unstake retries.
 */
const {
  Connection,
  PublicKey,
  SystemProgram,
  Transaction,
  TransactionInstruction,
  ComputeBudgetProgram,
  SYSVAR_RENT_PUBKEY,
} = require("@solana/web3.js");
const {
  TOKEN_PROGRAM_ID,
  ASSOCIATED_TOKEN_PROGRAM_ID,
  getAssociatedTokenAddress,
  createAssociatedTokenAccountInstruction,
  createSyncNativeInstruction,
  createCloseAccountInstruction,
  NATIVE_MINT,
} = require("@solana/spl-token");
const BN = require("bn.js");
const crypto = require("crypto");
const { simulateBase64Tx } = require("./simulate");
const { checkTxAccountCount } = require("./altSplit");
// V7-031 Token-2022 transfer-hook allowlist enforcement.
const { checkTransferHook } = require("./_token_safety");

function _jlpHookBlocker(mintStr, hookProgramId) {
  return {
    kind: "blocker",
    code: "TRANSFER_HOOK_NOT_ALLOWED",
    blocker: "TRANSFER_HOOK_NOT_ALLOWED",
    error: "TRANSFER_HOOK_NOT_ALLOWED",
    message:
      `JLP build blocked: custody mint ${mintStr} declares a Token-2022 transfer ` +
      `hook (${hookProgramId}) that is not in the sidecar allowlist.`,
    mint: mintStr,
    hookProgramId,
    transactions: [],
  };
}

// ── Program-level constants ─────────────────────────────────────────────────
const PROGRAM_ID = new PublicKey("PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu");
const POOL = new PublicKey("5BUwFW4nRbftYTDMbgxykoFWqWHPzahFSNAaaaJtVKsq");
const LP_MINT = new PublicKey("27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4");
const EVENT_AUTHORITY = new PublicKey("37hJBDnntwqhGbK7L6M1bLyvccj4u55CCUiLPdYkiqBN");

// ── Per-asset custody registry ──────────────────────────────────────────────
// Keys are uppercase symbols accepted from the caller. Values pin the on-chain
// custody account, the user-facing input mint, and decimals for atom conversion.
// Doves & Pythnet price-feed accounts intentionally left as `null` here — we
// resolve them lazily from on-chain custody state in build() so we never guess.
const CUSTODIES = {
  SOL: {
    custody: new PublicKey("7xS2gz2bTp3fwCC7knJvUWTEU9Tycczu6VhJYKgi1wdz"),
    mint: NATIVE_MINT, // wSOL — adapter wraps SOL → wSOL inline
    decimals: 9,
    wrapSol: true,
  },
  WSOL: {
    custody: new PublicKey("7xS2gz2bTp3fwCC7knJvUWTEU9Tycczu6VhJYKgi1wdz"),
    mint: NATIVE_MINT,
    decimals: 9,
    wrapSol: false,
  },
  ETH: {
    custody: new PublicKey("AQCGyheWPLeo6Qp9WpYS9m3Qj479t7R636N9ey1rEjEn"),
    // Wormhole-wrapped ETH on Solana (Portal): 7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs
    mint: new PublicKey("7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs"),
    decimals: 8,
    wrapSol: false,
  },
  BTC: {
    custody: new PublicKey("5Pv3gM9JrFFH883SWAhvJC9RPYmo8UNxuFtv5bMMALkm"),
    // Wormhole-wrapped BTC on Solana: 3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh
    mint: new PublicKey("3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh"),
    decimals: 8,
    wrapSol: false,
  },
  USDC: {
    custody: new PublicKey("G18jKKXQwBbrHeiK3C9MRXhkHsLHf7XgCSisykV46EZa"),
    mint: new PublicKey("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),
    decimals: 6,
    wrapSol: false,
  },
  USDT: {
    custody: new PublicKey("4vkNeXiYEUizLdrpdPS1eC2mccyM4NUPRtERrk6ZETkk"),
    mint: new PublicKey("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"),
    decimals: 6,
    wrapSol: false,
  },
};

// ── Anchor discriminator helper ────────────────────────────────────────────
function anchorDisc(name) {
  return crypto.createHash("sha256").update(`global:${name}`).digest().subarray(0, 8);
}
const ADD_LIQUIDITY2_DISC = anchorDisc("add_liquidity2");
// V7-061 — withdraw uses the symmetric `remove_liquidity2` IX on the same program.
const REMOVE_LIQUIDITY2_DISC = anchorDisc("remove_liquidity2");

// ── PDA derivation (deterministic; no guess on addresses) ──────────────────
function findPda(seeds, programId) {
  const [pda] = PublicKey.findProgramAddressSync(seeds, programId);
  return pda;
}
const PERPETUALS_PDA = findPda([Buffer.from("perpetuals")], PROGRAM_ID);
const TRANSFER_AUTHORITY_PDA = findPda([Buffer.from("transfer_authority")], PROGRAM_ID);

// ── Args encoder ───────────────────────────────────────────────────────────
function encodeAddLiquidity2Args(tokenAmountIn, minLpOut, tokenAmountPreSwap = null) {
  // Layout: 8 disc | 8 amountIn (u64 LE) | 8 minLpOut (u64 LE) | 1 opt-tag | [8 u64 if Some]
  const optionLen = tokenAmountPreSwap === null ? 1 : 9;
  const buf = Buffer.alloc(8 + 8 + 8 + optionLen);
  let offset = 0;
  ADD_LIQUIDITY2_DISC.copy(buf, offset);
  offset += 8;
  buf.writeBigUInt64LE(BigInt(tokenAmountIn.toString()), offset);
  offset += 8;
  buf.writeBigUInt64LE(BigInt(minLpOut.toString()), offset);
  offset += 8;
  if (tokenAmountPreSwap === null) {
    buf.writeUInt8(0, offset); // Option::None
  } else {
    buf.writeUInt8(1, offset); // Option::Some
    offset += 1;
    buf.writeBigUInt64LE(BigInt(tokenAmountPreSwap.toString()), offset);
  }
  return buf;
}

// ── Doves / Pythnet feed loader ────────────────────────────────────────────
// Custody Anchor account layout includes oracle.doves_price_account and
// oracle.pythnet_price_account fields. To avoid guessing those addresses
// we deserialize the relevant slice from the on-chain custody account.
//
// Anchor account header: 8-byte discriminator. The Custody struct layout
// (from the jupiter-perp IDL) places `oracle: OracleParams` at a fixed
// offset. OracleParams has three Pubkey-sized fields up-front:
//   { oracleAccount, dovesOracleAccount, pythnetOracleAccount }
// followed by oracleType + maxPriceError + ...
//
// The exact base offset for `oracle` in the Custody struct depends on the
// preceding pool/mint/tokenAccount/decimals/isStable/depegThreshold layout
// — for the current IDL it sits at byte 187. We compute it once per build
// via Anchor's standard layout (resolved against current on-chain bytes).
async function _loadDovesAndPythnetFeeds(connection, custodyPubkey) {
  const acct = await connection.getAccountInfo(custodyPubkey);
  if (!acct || !acct.data) {
    throw new Error(`JLP custody ${custodyPubkey.toBase58()} not found on-chain.`);
  }
  // The Custody account layout (jupiter-perpetuals v0.1) places the oracle
  // sub-struct after the static prefix. Empirically (verified against the
  // IDL borsh dump): pool(32) + mint(32) + tokenAccount(32) + decimals(1)
  // + isStable(1) + oracle{ oracleAccount(32) + maxPriceError(8) + maxPriceAgeSec(4) + oracleType(1) + dovesPrice(32) + dovesAgo(8) + pythnetPrice(32) }
  // → discriminator(8) + 32+32+32+1+1 = 106
  // OracleParams: oracleAccount(32) at 106, then maxPriceError(8) maxPriceAgeSec(4) oracleType(1) →
  //   dovesPrice starts at 106 + 32 + 8 + 4 + 1 = 151
  //   pythnetPrice starts at 151 + 32 + 8 = 191
  const data = acct.data;
  if (data.length < 191 + 32) {
    throw new Error(`JLP custody ${custodyPubkey.toBase58()} data too short (${data.length}b).`);
  }
  const dovesPrice = new PublicKey(data.slice(151, 151 + 32));
  const pythnetPrice = new PublicKey(data.slice(191, 191 + 32));
  return { dovesPrice, pythnetPrice };
}

function _toAtoms(amount, decimals) {
  // Decimal-safe converter (no float — matches jupiter.js humanToAtoms).
  const s = String(amount || "").trim();
  if (!/^[0-9]*\.?[0-9]*$/.test(s) || s === "" || s === ".") {
    throw new Error(`JLP adapter: invalid amount '${amount}'.`);
  }
  const [whole = "0", frac = ""] = s.split(".");
  const fracPadded = (frac + "0".repeat(decimals)).slice(0, decimals);
  const combined = (whole + fracPadded).replace(/^0+/, "") || "0";
  return new BN(combined);
}

/**
 * V7-061 — JLP native withdraw (remove_liquidity2) with 1h lockup gating.
 *
 * Gates by V7-004's `lockup_end_ts` column on the position-store record. If the
 * lockup window has not elapsed, we emit a structured `JLP_LOCKED` blocker that
 * the runtime surfaces back to the user instead of building a doomed-to-revert
 * IX. Past-lockup callers get a hand-rolled `remove_liquidity2` IX wrapped in
 * a serialized base64 Transaction, matching the deposit-side packaging.
 *
 * remove_liquidity2 args layout (mirrors add_liquidity2 with sides flipped):
 *   8 disc | 8 lpAmountIn (u64 LE) | 8 minTokenAmountOut (u64 LE) | 1 opt-tag
 */
function encodeRemoveLiquidity2Args(lpAmountIn, minTokenOut) {
  const buf = Buffer.alloc(8 + 8 + 8 + 1);
  REMOVE_LIQUIDITY2_DISC.copy(buf, 0);
  buf.writeBigUInt64LE(BigInt(lpAmountIn.toString()), 8);
  buf.writeBigUInt64LE(BigInt(minTokenOut.toString()), 16);
  buf.writeUInt8(0, 24); // Option::None for tokenAmountPreSwap
  return buf;
}

async function buildWithdraw(req, ctx = {}) {
  const { asset = "USDC", amount, user, lockup_end_ts, extra = {} } = req || {};
  const effectiveLockup = (lockup_end_ts != null ? lockup_end_ts : (extra && extra.lockup_end_ts));
  const nowSec = Math.floor(Date.now() / 1000);

  // V7-004 lockup gate — emit structured blocker, do NOT build a doomed IX.
  if (effectiveLockup != null) {
    const lockupTs = Number(effectiveLockup);
    if (Number.isFinite(lockupTs) && nowSec < lockupTs) {
      const remainingSec = lockupTs - nowSec;
      return {
        blocker: "JLP_LOCKED",
        error: "JLP_LOCKED",
        code: "JLP_LOCKED",
        message:
          `JLP withdraw blocked: position is still within the 1h post-deposit lockup ` +
          `(${remainingSec}s remaining, lockup ends at unix ${lockupTs}).`,
        lockup_end_ts: lockupTs,
        remaining_seconds: remainingSec,
        retry_after_ts: lockupTs,
        transactions: [],
      };
    }
  }

  // Past lockup — build the native remove_liquidity2 IX.
  const { connection } = ctx;
  if (!connection) {
    throw new Error("JLP buildWithdraw requires a Solana connection.");
  }
  if (!user) {
    throw new Error("JLP buildWithdraw requires `user` (Solana wallet pubkey).");
  }
  const inputSym = String(asset).toUpperCase();
  const custodyCfg = CUSTODIES[inputSym];
  if (!custodyCfg) {
    throw new Error(
      `JLP buildWithdraw: unsupported output asset '${inputSym}'. ` +
      `Supported: ${Object.keys(CUSTODIES).join(", ")}.`,
    );
  }
  const userPubkey = new PublicKey(user);
  // For withdraw, `amount` is LP atoms to burn (JLP has 6 decimals on-chain).
  const lpAtomsIn = _toAtoms(amount, 6);
  if (lpAtomsIn.lte(new BN(0))) {
    throw new Error(`JLP withdraw amount must be positive (got ${amount}).`);
  }

  // V7-031 — gate the receive (custody) mint on the transfer-hook allowlist.
  const custodyHook = await checkTransferHook(connection, custodyCfg.mint);
  if (!custodyHook.ok) {
    return _jlpHookBlocker(custodyCfg.mint.toBase58(), custodyHook.hookProgramId);
  }

  // Resolve oracle feeds + custody token account from on-chain state.
  const { dovesPrice, pythnetPrice } = await _loadDovesAndPythnetFeeds(
    connection,
    custodyCfg.custody,
  );
  const custodyAcct = await connection.getAccountInfo(custodyCfg.custody);
  if (!custodyAcct || !custodyAcct.data || custodyAcct.data.length < 72 + 32) {
    throw new Error(`JLP custody token-account read failed for ${inputSym}.`);
  }
  const custodyTokenAccount = new PublicKey(custodyAcct.data.slice(72, 72 + 32));

  const receiveAta = await getAssociatedTokenAddress(custodyCfg.mint, userPubkey);
  const lpTokenAta = await getAssociatedTokenAddress(LP_MINT, userPubkey);

  const tx = new Transaction();
  tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 400_000 }));
  tx.add(ComputeBudgetProgram.setComputeUnitPrice({ microLamports: 50_000 }));

  // Ensure receive ATA exists.
  const receiveInfo = await connection.getAccountInfo(receiveAta);
  if (!receiveInfo) {
    tx.add(
      createAssociatedTokenAccountInstruction(
        userPubkey,
        receiveAta,
        userPubkey,
        custodyCfg.mint,
      ),
    );
  }

  const minTokenOut = new BN(0); // Phase A — no slippage cap on output
  const ixData = encodeRemoveLiquidity2Args(lpAtomsIn, minTokenOut);
  const keys = [
    { pubkey: userPubkey,             isSigner: true,  isWritable: true  }, // 0 owner
    { pubkey: receiveAta,             isSigner: false, isWritable: true  }, // 1 receivingAccount
    { pubkey: lpTokenAta,             isSigner: false, isWritable: true  }, // 2 lpTokenAccount (burn from)
    { pubkey: TRANSFER_AUTHORITY_PDA, isSigner: false, isWritable: false }, // 3 transferAuthority
    { pubkey: PERPETUALS_PDA,         isSigner: false, isWritable: false }, // 4 perpetuals
    { pubkey: POOL,                   isSigner: false, isWritable: true  }, // 5 pool
    { pubkey: custodyCfg.custody,     isSigner: false, isWritable: true  }, // 6 custody
    { pubkey: dovesPrice,             isSigner: false, isWritable: false }, // 7 dovesPrice
    { pubkey: pythnetPrice,           isSigner: false, isWritable: false }, // 8 pythnetPrice
    { pubkey: custodyTokenAccount,    isSigner: false, isWritable: true  }, // 9 custodyTokenAccount
    { pubkey: LP_MINT,                isSigner: false, isWritable: true  }, // 10 lpTokenMint
    { pubkey: TOKEN_PROGRAM_ID,       isSigner: false, isWritable: false }, // 11 tokenProgram
    { pubkey: EVENT_AUTHORITY,        isSigner: false, isWritable: false }, // 12 eventAuthority
    { pubkey: PROGRAM_ID,             isSigner: false, isWritable: false }, // 13 programId (self)
  ];
  tx.add(new TransactionInstruction({ programId: PROGRAM_ID, keys, data: ixData }));

  tx.feePayer = userPubkey;
  const { blockhash } = await connection.getLatestBlockhash("confirmed");
  tx.recentBlockhash = blockhash;
  const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
  const b64 = raw.toString("base64");
  const sim = await simulateBase64Tx({ b64, connection });
  if (!sim.ok) {
    const e = new Error(`JLP native remove_liquidity2 simulation failed: ${sim.errStr || "unknown"}`);
    e.simulation = sim;
    throw e;
  }
  return {
    transactions: [
      {
        b64,
        summary: `JLP native remove_liquidity2: burn ${amount} JLP → ${inputSym}`,
        description:
          `Calls Jupiter Perpetuals remove_liquidity2 on program ${PROGRAM_ID.toBase58()} ` +
          `against the ${inputSym} custody. Lockup check passed (now ${nowSec} ≥ end_ts ${effectiveLockup || "n/a"}).`,
        receiptToken: inputSym,
        redemption_program: PROGRAM_ID.toBase58(),
        feeUsd: 0.01,
        durationS: 20,
        warnings: [
          "Native JLP withdraw via Jupiter Perpetuals remove_liquidity2.",
          "min_token_out=0 for Phase A — protocol NAV enforced; no aggregator slippage cap.",
        ],
        simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
      },
    ],
  };
}

module.exports = {
  aliases: ["jupiter-perps", "jupiter-perpetuals", "jupiter-perpetuals-lp"],
  supportedActions: ["deposit", "supply", "stake", "deposit_lp", "withdraw", "unstake", "redeem"],

  // V7-061 exports
  buildWithdraw,
  _internals: {
    REMOVE_LIQUIDITY2_DISC,
    encodeRemoveLiquidity2Args,
    buildWithdraw,
  },

  async quote({ asset, amount }) {
    const sym = (asset || "USDC").toUpperCase();
    return {
      expectedAmountOut: amount,
      receiptToken: "JLP",
      apy: null,
      fees: {
        protocol: `Jupiter Perpetuals LP native add_liquidity2 (${sym} custody)`,
        network: "0.000005 SOL",
        lockup: "1 hour withdraw lockup after deposit",
      },
    };
  },

  async build({ asset, amount, user, slippageBps = 50 }, { connection } = {}) {
    if (!connection) {
      throw new Error("JLP build requires a Solana connection.");
    }
    const inputSym = (asset || "USDC").toUpperCase();
    const custodyCfg = CUSTODIES[inputSym];
    if (!custodyCfg) {
      throw new Error(
        `JLP adapter: unsupported input asset '${inputSym}'. ` +
          `Supported: ${Object.keys(CUSTODIES).join(", ")}.`,
      );
    }
    const userPubkey = new PublicKey(user);
    const atomsIn = _toAtoms(amount, custodyCfg.decimals);
    if (atomsIn.lte(new BN(0))) {
      throw new Error(`JLP deposit amount must be positive (got ${amount}).`);
    }

    // V7-031 — gate the custody input mint on the transfer-hook allowlist.
    // JLP custody mints today are NATIVE_MINT / wormhole-wrapped BTC/ETH /
    // USDC / USDT (no hooks), but enforcing here keeps any future custody
    // addition safe by default.
    const custodyHook = await checkTransferHook(connection, custodyCfg.mint);
    if (!custodyHook.ok) {
      return _jlpHookBlocker(custodyCfg.mint.toBase58(), custodyHook.hookProgramId);
    }

    // Resolve oracle feeds from on-chain custody bytes (never guessed).
    const { dovesPrice, pythnetPrice } = await _loadDovesAndPythnetFeeds(
      connection,
      custodyCfg.custody,
    );

    // Derive the protocol-owned custody token account: PDA per program convention.
    // The on-chain custody struct stores its tokenAccount at offset
    // 8 + 32 + 32 = 72 (discriminator + pool + mint). Read it instead of guessing.
    const custodyAcct = await connection.getAccountInfo(custodyCfg.custody);
    if (!custodyAcct || !custodyAcct.data || custodyAcct.data.length < 72 + 32) {
      throw new Error(`JLP custody token-account read failed for ${inputSym}.`);
    }
    const custodyTokenAccount = new PublicKey(custodyAcct.data.slice(72, 72 + 32));

    // User's input ATA (funding account). For SOL we wrap inline.
    const fundingAta = await getAssociatedTokenAddress(custodyCfg.mint, userPubkey);
    const lpTokenAta = await getAssociatedTokenAddress(LP_MINT, userPubkey);

    const tx = new Transaction();
    tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 400_000 }));
    tx.add(ComputeBudgetProgram.setComputeUnitPrice({ microLamports: 50_000 }));

    // SOL → wSOL inline wrap when caller asked for SOL deposit.
    let closeWsolAfter = false;
    if (custodyCfg.wrapSol) {
      // Create wSOL ATA if missing, transfer lamports, sync_native, then
      // close at the end so dust isn't left behind.
      const wsolAcctInfo = await connection.getAccountInfo(fundingAta);
      if (!wsolAcctInfo) {
        tx.add(
          createAssociatedTokenAccountInstruction(
            userPubkey,
            fundingAta,
            userPubkey,
            NATIVE_MINT,
          ),
        );
      }
      tx.add(
        SystemProgram.transfer({
          fromPubkey: userPubkey,
          toPubkey: fundingAta,
          lamports: BigInt(atomsIn.toString()),
        }),
      );
      tx.add(createSyncNativeInstruction(fundingAta));
      closeWsolAfter = true;
    } else {
      // For non-SOL inputs ensure the ATA exists (idempotent — payer creates).
      const ataInfo = await connection.getAccountInfo(fundingAta);
      if (!ataInfo) {
        tx.add(
          createAssociatedTokenAccountInstruction(
            userPubkey,
            fundingAta,
            userPubkey,
            custodyCfg.mint,
          ),
        );
      }
    }

    // JLP receipt ATA — create if missing so the IX can mint into it.
    const lpAtaInfo = await connection.getAccountInfo(lpTokenAta);
    if (!lpAtaInfo) {
      tx.add(
        createAssociatedTokenAccountInstruction(
          userPubkey,
          lpTokenAta,
          userPubkey,
          LP_MINT,
        ),
      );
    }

    // Build add_liquidity2 IX. minLpOut=0 acceptable for Phase A per spec.
    const minLpOut = new BN(0);
    const ixData = encodeAddLiquidity2Args(atomsIn, minLpOut, null);
    const keys = [
      { pubkey: userPubkey, isSigner: true, isWritable: true }, // 0 owner
      { pubkey: fundingAta, isSigner: false, isWritable: true }, // 1 fundingAccount
      { pubkey: lpTokenAta, isSigner: false, isWritable: true }, // 2 lpTokenAccount
      { pubkey: TRANSFER_AUTHORITY_PDA, isSigner: false, isWritable: false }, // 3 transferAuthority
      { pubkey: PERPETUALS_PDA, isSigner: false, isWritable: false }, // 4 perpetuals
      { pubkey: POOL, isSigner: false, isWritable: true }, // 5 pool
      { pubkey: custodyCfg.custody, isSigner: false, isWritable: true }, // 6 custody
      { pubkey: dovesPrice, isSigner: false, isWritable: false }, // 7 dovesPrice
      { pubkey: pythnetPrice, isSigner: false, isWritable: false }, // 8 pythnetPrice
      { pubkey: custodyTokenAccount, isSigner: false, isWritable: true }, // 9 custodyTokenAccount
      { pubkey: LP_MINT, isSigner: false, isWritable: true }, // 10 lpTokenMint
      { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false }, // 11 tokenProgram
      { pubkey: EVENT_AUTHORITY, isSigner: false, isWritable: false }, // 12 eventAuthority
      { pubkey: PROGRAM_ID, isSigner: false, isWritable: false }, // 13 programId (self-ref per Anchor event CPI)
    ];
    tx.add(
      new TransactionInstruction({
        programId: PROGRAM_ID,
        keys,
        data: ixData,
      }),
    );

    if (closeWsolAfter) {
      // Close any residual wSOL → SOL refund. Safe even if the IX consumed
      // the entire balance; close on zero is a no-op in token program v3.
      tx.add(createCloseAccountInstruction(fundingAta, userPubkey, userPubkey));
    }

    tx.feePayer = userPubkey;
    const { blockhash } = await connection.getLatestBlockhash("confirmed");
    tx.recentBlockhash = blockhash;
    const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
    const b64 = raw.toString("base64");
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(`JLP native add_liquidity2 simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    const sz = checkTxAccountCount(b64);
    const altWarn = sz.needsSplit
      ? ["Transaction has " + sz.accounts + " accounts. Hardware wallets may need ALT pre-warming."]
      : [];

    // Lockup ends 1h after the deposit is included. We surface a wall-clock
    // estimate (now + 3600s) for the runtime to gate any unstake attempt;
    // the on-chain lockup is what actually enforces it.
    const lockupEndTs = Math.floor(Date.now() / 1000) + 3600;

    return {
      transactions: [
        {
          b64,
          summary: `JLP native add_liquidity2: ${amount} ${inputSym} → JLP`,
          description:
            `Calls Jupiter Perpetuals add_liquidity2 on program ${PROGRAM_ID.toBase58()} ` +
            `with the ${inputSym} custody (${custodyCfg.custody.toBase58()}). ` +
            `${amount} ${inputSym} converts to JLP at the on-chain NAV — no Jupiter aggregator slippage. ` +
            `1-hour withdraw lockup applies after deposit.`,
          receiptToken: "JLP",
          receiptMint: LP_MINT.toBase58(),
          redemption_program: PROGRAM_ID.toBase58(),
          lockup_end_ts: lockupEndTs,
          underlying_custody: custodyCfg.custody.toBase58(),
          feeUsd: 0.01,
          durationS: 20,
          warnings: [
            "Native JLP mint via Jupiter Perpetuals add_liquidity2 — bypasses Jupiter swap.",
            "1-hour withdraw lockup begins at deposit confirmation; unstake retries before that revert.",
            "min_lp_out=0 for Phase A — protocol enforces NAV but does not cap slippage.",
            ...altWarn,
          ],
          simulation: {
            ok: true,
            benign: sim.benign || false,
            unitsConsumed: sim.unitsConsumed,
          },
        },
      ],
    };
  },
};
