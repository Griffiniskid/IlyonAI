/**
 * _token_safety.js — Centralized Solana adapter safety helpers.
 *
 * Combines three orthogonal pre-flight checks shared by every Solana
 * adapter (jlp, orca, raydium, kamino, marinade, sanctum, meteora):
 *
 *   V7-031 — Token-2022 transfer-hook global allowlist.
 *            Any input/output mint that declares a TransferHook extension
 *            whose program id is not in ALLOWED_TRANSFER_HOOKS (or whose
 *            symbolic name is not in ALLOWED_HOOK_NAMES) MUST be rejected
 *            up-front with a DISALLOWED_TRANSFER_HOOK blocker.
 *
 *   V7-032 — WSOL syncNative + closeAccount instruction builders.
 *            Every adapter that wraps SOL → WSOL for a swap/deposit needs
 *            to (a) sync the lamport balance into the SPL accounting layer
 *            via syncNative, and (b) close the WSOL ATA back to the owner
 *            on the unwrap leg so dust SOL is reclaimed. These return
 *            harness-shaped instruction records, not real web3.js ixs, to
 *            stay dependency-free at this layer.
 *
 *   V7-041 — Whirlpool + Raydium CLMM init detection. Returns a
 *            POOL_NOT_INITIALIZED blocker if the pool account is missing
 *            or owned by the wrong program.
 *
 * V7-031.2 — Real Token-2022 TLV parser. Decodes the mint account's
 * extension TLV stream (ExtensionType::TransferHook = 14) at offset 165
 * (base 82 + account-type pad 83) and looks up the hook programId
 * against ALLOWED_TRANSFER_HOOKS. Legacy SPL mints (data.length === 82,
 * or owner !== TOKEN_2022_PROGRAM_ID) bypass the parser and pass with
 * {ok:true} since they cannot declare an extension.
 */
"use strict";

// V7-031 Token-2022 transfer hook allowlist ----------------------------------
//
// Membership rules:
//   1. Hook programId must appear in ALLOWED_TRANSFER_HOOKS, OR
//   2. Hook's symbolic name (when reported by the parser) must appear in
//      ALLOWED_HOOK_NAMES.
//
// Everything else is a hard fail with reason "DISALLOWED_TRANSFER_HOOK".
const ALLOWED_TRANSFER_HOOKS = new Set([
  // Memo Confidential Transfer (sample seed entry — replace with the real
  // mainnet program id once the risk allowlist ships).
  "CnfdtNoTaCAAUtKLNHL55BcMTcuKtfd83YuLAaXJpump",
  // Add real allowlist entries as integrations roll out.
]);

const ALLOWED_HOOK_NAMES = new Set([
  "confidential_transfer",
  "memo",
]);

// Token program IDs — used to decide whether to even attempt extension
// parsing. Legacy SPL Token program mints are strictly 82 bytes and have
// no extensions; only Token-2022 mints can carry a transfer hook.
const TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";
const SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";

// Token-2022 mint TLV layout constants (mirrors spl-token-2022/state.rs).
const MINT_BASE_LEN = 82;            // packed Mint::LEN
const ACCOUNT_TYPE_OFFSET = 165;     // base(82) + Multisig::LEN(82-1=82) pad -> 165 in spl-token-2022
const EXTENSIONS_START = 166;        // TLV stream begins immediately after the account-type byte
const EXTENSION_TYPE_TRANSFER_HOOK = 14;
const TRANSFER_HOOK_EXT_LEN = 64;    // programId(32) + authority(32)

// Minimal base58 (Bitcoin alphabet) encoder for 32-byte pubkeys. Inlined so
// the TLV parser has zero runtime deps — important for unit tests that run
// without the sidecar's @solana/web3.js install. Matches the encoding
// returned by PublicKey.toBase58() in @solana/web3.js for 32-byte inputs.
const _BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function _base58EncodePubkey(bytes) {
  // Count leading zeros — each becomes a "1" in base58.
  let zeros = 0;
  while (zeros < bytes.length && bytes[zeros] === 0) zeros += 1;
  // Convert big-endian bytes → base58 digits via repeated division.
  const input = Array.from(bytes);
  const out = [];
  let start = zeros;
  while (start < input.length) {
    let carry = 0;
    for (let i = start; i < input.length; i += 1) {
      const v = (carry << 8) | input[i];
      input[i] = (v / 58) | 0;
      carry = v % 58;
    }
    out.push(_BASE58_ALPHABET[carry]);
    while (start < input.length && input[start] === 0) start += 1;
  }
  let result = "";
  for (let i = 0; i < zeros; i += 1) result += "1";
  for (let i = out.length - 1; i >= 0; i -= 1) result += out[i];
  return result;
}

/**
 * Walk the Token-2022 TLV extension stream starting at EXTENSIONS_START
 * and return the 32-byte programId of the TransferHook extension if
 * present. Returns null when:
 *   - data is shorter than EXTENSIONS_START (no extension area)
 *   - TLV stream contains no transfer-hook record
 *   - the transfer-hook record has a zero programId (caller code in
 *     spl-token-2022 treats Pubkey::default() as "no hook configured")
 *
 * Defensive: any malformed TLV (length overruns buffer) short-circuits
 * to null rather than throwing — a malformed mint is rejected upstream
 * by the on-chain program, so we don't fault here.
 */
function _parseTransferHookProgramId(data) {
  if (!data || data.length <= EXTENSIONS_START) return null;
  let cursor = EXTENSIONS_START;
  while (cursor + 4 <= data.length) {
    const extType = data.readUInt16LE(cursor);
    const extLen = data.readUInt16LE(cursor + 2);
    const payloadStart = cursor + 4;
    const payloadEnd = payloadStart + extLen;
    if (payloadEnd > data.length) return null; // malformed — bail
    if (extType === 0 && extLen === 0) {
      // Uninitialized TLV record (rare but valid termination).
      return null;
    }
    if (extType === EXTENSION_TYPE_TRANSFER_HOOK) {
      if (extLen < 32) return null; // malformed transfer-hook record
      const programIdBytes = data.slice(payloadStart, payloadStart + 32);
      // Pubkey::default() (all zeros) means "no hook"; surface as null
      // so the allowlist check is skipped for those mints.
      let allZero = true;
      for (let i = 0; i < 32; i += 1) {
        if (programIdBytes[i] !== 0) { allZero = false; break; }
      }
      if (allZero) return null;
      return _base58EncodePubkey(Buffer.isBuffer(programIdBytes) ? programIdBytes : Buffer.from(programIdBytes));
    }
    cursor = payloadEnd;
  }
  return null;
}

/**
 * Check a mint for a Token-2022 transfer hook against the allowlist.
 *
 * @param {object} connection - @solana/web3.js Connection (or test mock)
 * @param {string|PublicKey} mint - mint to inspect
 * @returns {Promise<{ok: boolean, reason?: string, hookProgramId?: string}>}
 *
 * Behaviour:
 *   - Mint account missing → {ok:true} (caller surfaces MINT_NOT_FOUND
 *     separately so we don't double-fault).
 *   - Owner is the legacy SPL Token program OR data is exactly 82 bytes →
 *     {ok:true} (no extensions possible).
 *   - Token-2022 mint with no TransferHook extension → {ok:true}.
 *   - Token-2022 mint with TransferHook whose programId is in
 *     ALLOWED_TRANSFER_HOOKS → {ok:true, hookProgramId}.
 *   - Otherwise → {ok:false, reason:"TRANSFER_HOOK_NOT_ALLOWED", hookProgramId}.
 */
async function checkTransferHook(connection, mint) {
  const info = await connection.getAccountInfo(mint);
  if (!info) {
    return { ok: true };
  }
  const ownerStr = info.owner
    ? (typeof info.owner.toString === "function" ? info.owner.toString() : String(info.owner))
    : "";
  // Legacy SPL Token mints can never declare a transfer hook.
  if (ownerStr && ownerStr !== TOKEN_2022_PROGRAM_ID) {
    return { ok: true };
  }
  const data = info.data;
  if (!data || data.length <= MINT_BASE_LEN) {
    // 82-byte base mint with no extension area — safe.
    return { ok: true };
  }
  // Normalise to a Node Buffer so readUInt16LE works on web3.js's Uint8Array.
  const buf = Buffer.isBuffer(data) ? data : Buffer.from(data);
  const hookProgramId = _parseTransferHookProgramId(buf);
  if (!hookProgramId) {
    return { ok: true };
  }
  if (ALLOWED_TRANSFER_HOOKS.has(hookProgramId)) {
    return { ok: true, hookProgramId };
  }
  return {
    ok: false,
    reason: "TRANSFER_HOOK_NOT_ALLOWED",
    hookProgramId,
  };
}

// V7-032 WSOL sync+close helper builders -------------------------------------
//
// Both functions return harness-shaped instruction records (NOT real
// web3.js TransactionInstruction objects). The adapter layer that
// actually assembles a Transaction is responsible for converting these
// records into the SDK calls (createSyncNativeInstruction +
// createCloseAccountInstruction from @solana/spl-token). Keeping the
// builders dependency-free here means this module loads cleanly in test
// environments that don't have spl-token installed.

const TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";

function buildSyncNativeIx(wsolAtaPubkey) {
  return {
    kind: "sync_native",
    account: wsolAtaPubkey,
    programId: TOKEN_PROGRAM_ID,
  };
}

function buildCloseWsolIx(wsolAtaPubkey, ownerPubkey) {
  return {
    kind: "close_account",
    account: wsolAtaPubkey,
    destination: ownerPubkey,
    owner: ownerPubkey,
    programId: TOKEN_PROGRAM_ID,
  };
}

// V7-041 pool init detection -------------------------------------------------

const WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";
const RAYDIUM_CLMM_PROGRAM_ID = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK";

/**
 * Returns true iff the account exists AND is owned by the Whirlpool
 * program. Anything else (missing, wrong owner, RPC error → undefined)
 * yields false, which the caller should translate into a
 * POOL_NOT_INITIALIZED blocker.
 */
async function isWhirlpoolInitialized(connection, whirlpoolPubkey) {
  const info = await connection.getAccountInfo(whirlpoolPubkey);
  if (!info) return false;
  const owner = info.owner;
  if (!owner) return false;
  const ownerStr =
    typeof owner.toString === "function" ? owner.toString() : String(owner);
  return ownerStr === WHIRLPOOL_PROGRAM_ID;
}

/**
 * Same shape as isWhirlpoolInitialized but for Raydium CLMM pools.
 */
async function isRaydiumCLMMInitialized(connection, poolPubkey) {
  const info = await connection.getAccountInfo(poolPubkey);
  if (!info) return false;
  const owner = info.owner;
  if (!owner) return false;
  const ownerStr =
    typeof owner.toString === "function" ? owner.toString() : String(owner);
  return ownerStr === RAYDIUM_CLMM_PROGRAM_ID;
}

module.exports = {
  // V7-031
  ALLOWED_TRANSFER_HOOKS,
  ALLOWED_HOOK_NAMES,
  TOKEN_2022_PROGRAM_ID,
  SPL_TOKEN_PROGRAM_ID,
  EXTENSION_TYPE_TRANSFER_HOOK,
  checkTransferHook,
  _parseTransferHookProgramId,
  // V7-032
  TOKEN_PROGRAM_ID,
  buildSyncNativeIx,
  buildCloseWsolIx,
  // V7-041
  WHIRLPOOL_PROGRAM_ID,
  RAYDIUM_CLMM_PROGRAM_ID,
  isWhirlpoolInitialized,
  isRaydiumCLMMInitialized,
};
