/**
 * Address Lookup Table (ALT) split detector — spec §13 Row 15.
 *
 * Hardware wallets (Ledger Solana app especially) cannot sign v0 transactions
 * past a certain account-count threshold without ALTs because the on-device
 * blind-signing buffer truncates. The threshold is empirically ~28 static
 * account keys before Ledger's "TX too large" error fires.
 *
 * This helper decodes a base64 serialized v0 VersionedTransaction and returns
 * a structural report. Callers should attach a warning (NOT fail-closed) when
 * `needsSplit` is true so the runtime can surface "SPLIT_REQUIRED" guidance
 * to the frontend — the user signs a pre-warm ALT extend tx first, then the
 * main tx referencing the warmed ALT pubkey.
 *
 * For the v6 batch we only warn. A future iteration can auto-build the
 * AddressLookupTableProgram.extendLookupTable instruction here.
 */
const { VersionedTransaction } = require("@solana/web3.js");

/**
 * Decode a base64 v0 tx and count static account keys.
 *
 * @param {string} b64Tx - base64 serialized VersionedTransaction
 * @param {number} threshold - account-count warning threshold (default 28)
 * @returns {{ accounts: number, needsSplit: boolean, altKeys: number, ok: boolean, error?: string }}
 */
function checkTxAccountCount(b64Tx, threshold = 28) {
  try {
    const raw = Buffer.from(b64Tx, "base64");
    const tx = VersionedTransaction.deserialize(raw);
    const msg = tx.message;
    const staticKeys = Array.isArray(msg.staticAccountKeys)
      ? msg.staticAccountKeys
      : (Array.isArray(msg.accountKeys) ? msg.accountKeys : []);
    const accounts = staticKeys.length;
    // Already-referenced ALT keys reduce sign-time pressure: hardware
    // wallets resolve via the ALT lookup, not the static key list. We
    // surface the alt-key count so callers can decide whether the warning
    // is still useful when a long tx already references a lookup table.
    let altKeys = 0;
    const altList = msg.addressTableLookups || [];
    for (const a of altList) {
      altKeys += (a.writableIndexes?.length || 0) + (a.readonlyIndexes?.length || 0);
    }
    return {
      accounts,
      altKeys,
      needsSplit: accounts > threshold,
      ok: true,
    };
  } catch (err) {
    return {
      accounts: 0,
      altKeys: 0,
      needsSplit: false,
      ok: false,
      error: String(err && err.message ? err.message : err),
    };
  }
}

module.exports = { checkTxAccountCount };
