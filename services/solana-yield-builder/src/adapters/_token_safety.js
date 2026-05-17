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
 * Real Token-2022 TLV parsing is intentionally stubbed here — the full
 * implementation needs to decode the mint account's extension TLV stream
 * (ExtensionType::TransferHook = 14) and look up the hook programId. That
 * lands in V7-031.2 once the allowlist policy is finalized with the risk
 * team. The interface below is forward-compatible so callers can wire it
 * in today and the parser will drop in behind the same return shape.
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

/**
 * Check a mint for a Token-2022 transfer hook against the allowlist.
 *
 * @param {object} connection - @solana/web3.js Connection (or test mock)
 * @param {string|PublicKey} mint - mint to inspect
 * @returns {Promise<{ok: boolean, reason?: string, hookProgram?: string}>}
 *
 * Current behaviour: returns {ok:true} for legacy SPL mints (no extension
 * data) and {ok:true} by default for Token-2022 mints. The TLV parser is
 * stubbed — see file header. Once the parser lands, this function will
 * return {ok:false, reason:"DISALLOWED_TRANSFER_HOOK", hookProgram:"..."}
 * for any mint whose hook is outside the allowlist.
 */
async function checkTransferHook(connection, mint) {
  const info = await connection.getAccountInfo(mint);
  if (!info) {
    // Mint account missing entirely — caller will surface a separate
    // MINT_NOT_FOUND blocker. We return ok here so we don't double-fault.
    return { ok: true };
  }
  // TODO: parse mint TLV extensions for real allowlist enforcement.
  // Until then we accept everything; the allowlist sets above are
  // already exported so callers can pre-validate against them once the
  // parser is plumbed in.
  return { ok: true };
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
  checkTransferHook,
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
