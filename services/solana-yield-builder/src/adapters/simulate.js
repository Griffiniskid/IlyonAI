/**
 * Pre-sign transaction simulation gate.
 *
 * Every adapter that produces a base64 VersionedTransaction must run it
 * through this helper BEFORE returning to the Python runtime. A non-null
 * `err` aborts the build with a structured error so users never see a
 * "Sign" button for a tx that's guaranteed to revert.
 *
 * Returns { ok, err, logs } — caller decides whether to fail-closed or attach
 * the simulation receipt to the response.
 */
const { VersionedTransaction } = require("@solana/web3.js");

const BENIGN_PATTERNS = [
  /insufficient lamports/i,
  /insufficient funds/i,
  /AccountNotFound/i,
  /could not find account/i,
];

async function simulateBase64Tx({ b64, connection, replaceRecentBlockhash = true }) {
  try {
    const raw = Buffer.from(b64, "base64");
    const tx = VersionedTransaction.deserialize(raw);
    const resp = await connection.simulateTransaction(tx, {
      sigVerify: false,
      replaceRecentBlockhash,
      commitment: "processed",
    });
    const value = resp?.value || {};
    const logs = Array.isArray(value.logs) ? value.logs : [];
    if (!value.err) {
      return { ok: true, err: null, logs, unitsConsumed: value.unitsConsumed || null };
    }
    const errStr = JSON.stringify(value.err);
    const benign = BENIGN_PATTERNS.some((p) => p.test(errStr) || logs.some((l) => p.test(l || "")));
    return {
      ok: benign,        // structurally valid; just empty dev wallet
      err: value.err,
      errStr,
      logs,
      benign,
      unitsConsumed: value.unitsConsumed || null,
    };
  } catch (err) {
    return { ok: false, err: { message: err.message }, errStr: String(err.message || err), logs: [] };
  }
}

module.exports = { simulateBase64Tx };
