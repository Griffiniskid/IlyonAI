/**
 * Address Lookup Table (ALT) split detector + instruction-level splitter —
 * spec §13 Row 15.
 *
 * Two responsibilities, one module:
 *
 *   1. `checkTxAccountCount(b64Tx, threshold)` — post-build inspection of a
 *      serialized v0 VersionedTransaction. Counts static account keys and
 *      flags `needsSplit` when the count exceeds the Ledger blind-signing
 *      threshold (~28 static keys). Surfaces an ALT-key count so callers
 *      can decide whether the warning is still useful when a long tx
 *      already references a lookup table.
 *
 *   2. `splitInstructionsAcrossTransactions(ixs, opts)` — pre-build splitter.
 *      Takes an ordered array of TransactionInstruction-shaped objects and
 *      chunks them into N transaction groups so each group can be signed
 *      independently. The split bound is:
 *          - default: 28 instructions per tx (matches the static-key
 *            heuristic above; conservative for non-Ledger wallets)
 *          - ledger=true: 7 instructions per tx (Ledger's outer-IX limit
 *            before "TX too large" fires on the on-device parser)
 *
 *      The splitter preserves instruction order across the returned groups
 *      (group[0] always contains ix[0]). Callers that need atomic semantics
 *      across the split boundary must add their own pre-warm / commit step
 *      between groups (e.g. ALT extend tx first, then dependent tx).
 *
 *      Hardware wallets (Ledger Solana app especially) cannot sign v0
 *      transactions past a certain account-count threshold without ALTs
 *      because the on-device blind-signing buffer truncates. The splitter
 *      lets callers fan a single logical operation across multiple signable
 *      transactions when ALT extension alone isn't sufficient.
 */
const { VersionedTransaction } = require("@solana/web3.js");

const DEFAULT_MAX_IX_PER_TX = 28;
const LEDGER_MAX_OUTER_IX = 7;

/**
 * Decode a base64 v0 tx and count static account keys.
 *
 * @param {string} b64Tx - base64 serialized VersionedTransaction
 * @param {number} threshold - account-count warning threshold (default 28)
 * @returns {{ accounts: number, needsSplit: boolean, altKeys: number, ok: boolean, error?: string }}
 */
function checkTxAccountCount(b64Tx, threshold = DEFAULT_MAX_IX_PER_TX) {
  try {
    const raw = Buffer.from(b64Tx, "base64");
    const tx = VersionedTransaction.deserialize(raw);
    const msg = tx.message;
    const staticKeys = Array.isArray(msg.staticAccountKeys)
      ? msg.staticAccountKeys
      : (Array.isArray(msg.accountKeys) ? msg.accountKeys : []);
    const accounts = staticKeys.length;
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

/**
 * Split an ordered list of instructions across N transaction-ready groups.
 *
 * Each output group is a plain array of the same instruction objects passed
 * in — no copying, no reordering. Callers wrap each group in their own
 * `TransactionMessage.compileToV0Message` / `VersionedTransaction.sign`
 * pipeline.
 *
 * @param {Array<object>} instructions - ordered list of IX-shaped objects
 *   (the splitter is structurally agnostic — it doesn't peek inside).
 * @param {object} [opts]
 * @param {number} [opts.maxInstructionsPerTx=28] - cap for non-Ledger wallets
 * @param {number} [opts.maxOuterIxForLedger=7] - cap when `ledger: true`
 * @param {boolean} [opts.ledger=false] - apply the Ledger outer-IX limit
 * @returns {{ transactions: Array<Array<object>>, txCount: number, ledgerWarning: boolean }}
 */
function splitInstructionsAcrossTransactions(instructions, opts = {}) {
  const ledger = !!opts.ledger;
  const maxIx = ledger
    ? (Number.isInteger(opts.maxOuterIxForLedger) && opts.maxOuterIxForLedger > 0
        ? opts.maxOuterIxForLedger
        : LEDGER_MAX_OUTER_IX)
    : (Number.isInteger(opts.maxInstructionsPerTx) && opts.maxInstructionsPerTx > 0
        ? opts.maxInstructionsPerTx
        : DEFAULT_MAX_IX_PER_TX);

  if (!Array.isArray(instructions) || instructions.length === 0) {
    return { transactions: [], txCount: 0, ledgerWarning: ledger };
  }

  const transactions = [];
  for (let i = 0; i < instructions.length; i += maxIx) {
    transactions.push(instructions.slice(i, i + maxIx));
  }

  return {
    transactions,
    txCount: transactions.length,
    // `ledgerWarning` is `true` whenever we applied the Ledger cap — this
    // lets the UI surface "you'll need to confirm N taps on the device"
    // even when the split came out clean (txCount === 1).
    ledgerWarning: ledger,
  };
}

module.exports = {
  checkTxAccountCount,
  splitInstructionsAcrossTransactions,
  DEFAULT_MAX_IX_PER_TX,
  LEDGER_MAX_OUTER_IX,
};
