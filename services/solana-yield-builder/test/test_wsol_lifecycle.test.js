"use strict";
/**
 * V7-032 — WSOL syncNative + closeAccount lifecycle pin test.
 *
 * Asserts that:
 *   1. `buildSyncNativeIx` returns a real `TransactionInstruction`
 *      (one program-id + one key entry pointing at the WSOL ATA) when
 *      `@solana/spl-token` is present (we inject a fake to simulate
 *      that in the dependency-free harness).
 *   2. `buildCloseWsolIx` returns a real `TransactionInstruction` with
 *      the ATA as the source account, destination as the lamport sink,
 *      and owner authorising the close.
 *   3. The fallback placeholder shape (when spl-token is absent AND no
 *      DI hook is set) still encodes the right pubkeys + program id —
 *      callers that only stash these as metadata don't crash.
 *   4. Plan-level assertion: a swap plan that has SOL as INPUT contains
 *      a `createSyncNative` IX targeting the user's WSOL ATA. A plan
 *      that has SOL as OUTPUT contains a `createCloseAccount` IX with
 *      `destination` + `owner` both set to the user pubkey.
 *
 * The test injects a fake `@solana/spl-token` surface via
 * `__setSplTokenImpl` so it never needs the real package installed.
 * This mirrors the strategy used by `test_transfer_hook_real.test.js`.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  buildSyncNativeIx,
  buildCloseWsolIx,
  TOKEN_PROGRAM_ID,
  __setSplTokenImpl,
} = require("../src/adapters/_token_safety");

// Sentinel pubkeys used throughout the test. Real base58 strings — the
// builders never validate, but downstream callers (orca.js) parse them
// via `new PublicKey(...)` so we stick to canonical Solana pubkey
// fixtures so the test exercises the same surface.
const USER_PUBKEY = "8Yv9Jp3ZyaQGyW1m3Cz9aNkRwAxMfdQZHmgYNgYhPqVu";
const WSOL_ATA = "C76C8XfMhFRDqyy9eYj1XwL5d5jB4kV3GtRQfHE3K6jK";
const WSOL_MINT = "So11111111111111111111111111111111111111112";

// Tag emitted by the fake spl-token surface so the assertions can prove
// the helpers actually called through to spl-token (vs returning the
// placeholder record).
const REAL_SYNC_TAG = "__fake_real_sync_native_ix__";
const REAL_CLOSE_TAG = "__fake_real_close_account_ix__";

function installFakeSplToken() {
  __setSplTokenImpl({
    createSyncNativeInstruction(account, programId) {
      // Real spl-token returns a `TransactionInstruction`. We return a
      // shape-compatible object the test can introspect, plus a tag the
      // assertions key off of to prove this path ran.
      return {
        __tag: REAL_SYNC_TAG,
        programId: programId || TOKEN_PROGRAM_ID,
        keys: [
          { pubkey: account, isSigner: false, isWritable: true },
        ],
        data: Buffer.from([17]), // sync_native discriminator
      };
    },
    createCloseAccountInstruction(account, destination, owner, multiSigners, programId) {
      return {
        __tag: REAL_CLOSE_TAG,
        programId: programId || TOKEN_PROGRAM_ID,
        keys: [
          { pubkey: account, isSigner: false, isWritable: true },
          { pubkey: destination, isSigner: false, isWritable: true },
          { pubkey: owner, isSigner: !multiSigners || multiSigners.length === 0, isWritable: false },
        ],
        data: Buffer.from([9]), // close_account discriminator
      };
    },
  });
}

function uninstallFakeSplToken() {
  __setSplTokenImpl(null);
}

// Minimal builder that emulates what an adapter would do when wiring
// WSOL legs into a Solana transaction plan. SOL input → emit
// `syncNative` before the swap IXs. SOL output → emit `closeAccount`
// after them. Mirrors the orca.js wiring pattern.
function buildSwapPlanWithWsolLifecycle({ user, inputMint, outputMint, wsolAta }) {
  const ixs = [];
  if (inputMint === WSOL_MINT) {
    ixs.push(buildSyncNativeIx(wsolAta));
  }
  // Stub swap IX in the middle. Real adapter would emit Jupiter / Orca /
  // Raydium IXs here.
  ixs.push({ __tag: "stub_swap_ix", programId: "Stub11111111111111111111111111111111111111" });
  if (outputMint === WSOL_MINT) {
    ixs.push(buildCloseWsolIx(wsolAta, user));
  }
  return { instructions: ixs };
}

// ── Tests ────────────────────────────────────────────────────────────

test("buildSyncNativeIx returns a real TransactionInstruction (spl-token path)", () => {
  installFakeSplToken();
  try {
    const ix = buildSyncNativeIx(WSOL_ATA);
    assert.equal(ix.__tag, REAL_SYNC_TAG, "expected the spl-token-backed builder to run");
    assert.equal(ix.programId, TOKEN_PROGRAM_ID);
    assert.equal(ix.keys.length, 1);
    assert.equal(ix.keys[0].pubkey, WSOL_ATA);
    assert.equal(ix.keys[0].isWritable, true);
    assert.ok(Buffer.isBuffer(ix.data) || ix.data instanceof Uint8Array);
  } finally {
    uninstallFakeSplToken();
  }
});

test("buildCloseWsolIx returns a real TransactionInstruction (spl-token path)", () => {
  installFakeSplToken();
  try {
    const ix = buildCloseWsolIx(WSOL_ATA, USER_PUBKEY);
    assert.equal(ix.__tag, REAL_CLOSE_TAG);
    assert.equal(ix.programId, TOKEN_PROGRAM_ID);
    assert.equal(ix.keys.length, 3);
    assert.equal(ix.keys[0].pubkey, WSOL_ATA, "account = WSOL ATA");
    assert.equal(ix.keys[1].pubkey, USER_PUBKEY, "destination = owner when not overridden");
    assert.equal(ix.keys[2].pubkey, USER_PUBKEY, "owner = owner");
    assert.equal(ix.keys[2].isSigner, true, "owner must sign close");
  } finally {
    uninstallFakeSplToken();
  }
});

test("buildCloseWsolIx honours explicit destination override", () => {
  installFakeSplToken();
  try {
    const ALT_DEST = "11111111111111111111111111111112";
    const ix = buildCloseWsolIx(WSOL_ATA, USER_PUBKEY, { destination: ALT_DEST });
    assert.equal(ix.keys[1].pubkey, ALT_DEST, "destination override flows through");
    assert.equal(ix.keys[2].pubkey, USER_PUBKEY, "owner unchanged");
  } finally {
    uninstallFakeSplToken();
  }
});

test("placeholder fallback: when spl-token is absent the legacy harness record is returned", () => {
  // Inject a fake-but-empty impl — _resolveSplToken sees `false` and
  // emits the placeholder. We can't directly simulate "module missing"
  // here without modifying require cache, so we rely on the DI hook.
  __setSplTokenImpl(null);
  // Force the lazy resolver to flip to `false` by setting the injected
  // surface explicitly to an object that lacks the spl methods. The
  // builder treats it as "no spl-token" and falls back.
  __setSplTokenImpl({}); // empty object → no createSyncNativeInstruction
  try {
    const ix = buildSyncNativeIx(WSOL_ATA);
    assert.equal(ix.__placeholder, true, "placeholder marker present");
    assert.equal(ix.kind, "sync_native");
    assert.equal(ix.account, WSOL_ATA);
    assert.equal(ix.programId, TOKEN_PROGRAM_ID);

    const closeIx = buildCloseWsolIx(WSOL_ATA, USER_PUBKEY);
    assert.equal(closeIx.__placeholder, true);
    assert.equal(closeIx.kind, "close_account");
    assert.equal(closeIx.account, WSOL_ATA);
    assert.equal(closeIx.destination, USER_PUBKEY);
    assert.equal(closeIx.owner, USER_PUBKEY);
  } finally {
    uninstallFakeSplToken();
  }
});

test("swap plan with SOL INPUT contains a createSyncNative IX targeting the WSOL ATA", () => {
  installFakeSplToken();
  try {
    const plan = buildSwapPlanWithWsolLifecycle({
      user: USER_PUBKEY,
      inputMint: WSOL_MINT,
      outputMint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", // USDC
      wsolAta: WSOL_ATA,
    });
    const syncIxs = plan.instructions.filter((ix) => ix.__tag === REAL_SYNC_TAG);
    assert.equal(syncIxs.length, 1, "exactly one syncNative IX on SOL-input swap");
    assert.equal(syncIxs[0].keys[0].pubkey, WSOL_ATA);

    const closeIxs = plan.instructions.filter((ix) => ix.__tag === REAL_CLOSE_TAG);
    assert.equal(closeIxs.length, 0, "no closeAccount when SOL is the input (not output)");
  } finally {
    uninstallFakeSplToken();
  }
});

test("swap plan with SOL OUTPUT contains a createCloseAccount IX with correct destination + owner", () => {
  installFakeSplToken();
  try {
    const plan = buildSwapPlanWithWsolLifecycle({
      user: USER_PUBKEY,
      inputMint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", // USDC
      outputMint: WSOL_MINT,
      wsolAta: WSOL_ATA,
    });
    const closeIxs = plan.instructions.filter((ix) => ix.__tag === REAL_CLOSE_TAG);
    assert.equal(closeIxs.length, 1, "exactly one closeAccount IX on SOL-output swap");
    const close = closeIxs[0];
    assert.equal(close.keys[0].pubkey, WSOL_ATA, "closes the user's WSOL ATA");
    assert.equal(close.keys[1].pubkey, USER_PUBKEY, "lamports flow back to owner");
    assert.equal(close.keys[2].pubkey, USER_PUBKEY, "owner authorises the close");

    const syncIxs = plan.instructions.filter((ix) => ix.__tag === REAL_SYNC_TAG);
    assert.equal(syncIxs.length, 0, "no syncNative when SOL is the output");
  } finally {
    uninstallFakeSplToken();
  }
});

test("round-trip plan: SOL → token → SOL has both syncNative AND closeAccount", () => {
  installFakeSplToken();
  try {
    const plan = buildSwapPlanWithWsolLifecycle({
      user: USER_PUBKEY,
      inputMint: WSOL_MINT,
      outputMint: WSOL_MINT,
      wsolAta: WSOL_ATA,
    });
    const syncIxs = plan.instructions.filter((ix) => ix.__tag === REAL_SYNC_TAG);
    const closeIxs = plan.instructions.filter((ix) => ix.__tag === REAL_CLOSE_TAG);
    assert.equal(syncIxs.length, 1);
    assert.equal(closeIxs.length, 1);
    // Ordering matters: syncNative must precede the swap, close must follow.
    const syncIdx = plan.instructions.indexOf(syncIxs[0]);
    const closeIdx = plan.instructions.indexOf(closeIxs[0]);
    const stubIdx = plan.instructions.findIndex((ix) => ix.__tag === "stub_swap_ix");
    assert.ok(syncIdx < stubIdx, "syncNative must be emitted before the swap IX");
    assert.ok(stubIdx < closeIdx, "closeAccount must be emitted after the swap IX");
  } finally {
    uninstallFakeSplToken();
  }
});
