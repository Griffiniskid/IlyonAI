"use strict";
/**
 * V7-031 — Real Token-2022 transfer-hook TLV parser pin test.
 *
 * Mocks a connection.getAccountInfo() response with a synthetic Token-2022
 * mint that declares a TransferHook extension (type 0x0E = 14), then asserts:
 *
 *   1. Allowlisted hook programId → {ok: true, hookProgramId}
 *   2. Non-allowlisted programId   → {ok: false, reason: "TRANSFER_HOOK_NOT_ALLOWED"}
 *   3. Legacy SPL mint (82 bytes, owner = SPL token program) → {ok: true}
 *   4. Token-2022 mint with no extensions → {ok: true}
 *   5. Missing mint (getAccountInfo → null) → {ok: true} (no double-fault)
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  checkTransferHook,
  ALLOWED_TRANSFER_HOOKS,
  TOKEN_2022_PROGRAM_ID,
  SPL_TOKEN_PROGRAM_ID,
  EXTENSION_TYPE_TRANSFER_HOOK,
  _parseTransferHookProgramId,
} = require("../src/adapters/_token_safety");

// Minimal base58 decoder for 32-byte pubkeys — mirrors the encoder inside
// _token_safety.js so the test stays dependency-free.
const BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function decodeBase58Pubkey(str) {
  const map = new Map();
  for (let i = 0; i < BASE58.length; i += 1) map.set(BASE58[i], i);
  let zeros = 0;
  while (zeros < str.length && str[zeros] === "1") zeros += 1;
  const digits = [0];
  for (let i = zeros; i < str.length; i += 1) {
    const v = map.get(str[i]);
    if (v === undefined) throw new Error(`bad base58 char ${str[i]}`);
    let carry = v;
    for (let j = 0; j < digits.length; j += 1) {
      const x = digits[j] * 58 + carry;
      digits[j] = x & 0xff;
      carry = x >>> 8;
    }
    while (carry) {
      digits.push(carry & 0xff);
      carry >>>= 8;
    }
  }
  const out = Buffer.alloc(32, 0);
  let outIdx = zeros;
  for (let i = digits.length - 1; i >= 0; i -= 1) {
    if (outIdx >= 32) throw new Error("decoded pubkey overflows 32 bytes");
    out[outIdx++] = digits[i];
  }
  return out;
}

// Build a synthetic Token-2022 mint account buffer with a TransferHook extension
// at the canonical extension area.
//
// Layout:
//   [0..82)   base mint (zeros are fine for the parser — it never reads them)
//   [82..165) account-type padding region (165 bytes total head before extensions)
//   [165]     account-type discriminator byte (1 = Mint)
//   [166..]   TLV stream: u16 LE type | u16 LE length | <data>
function buildToken2022MintWithHook(hookProgramIdBytes, opts = {}) {
  const extType = opts.extType != null ? opts.extType : EXTENSION_TYPE_TRANSFER_HOOK;
  const extLen = opts.extLen != null ? opts.extLen : 64; // 32 programId + 32 authority
  const totalLen = 166 + 4 + extLen;
  const buf = Buffer.alloc(totalLen, 0);
  buf.writeUInt8(1, 165); // account-type = Mint
  buf.writeUInt16LE(extType, 166);
  buf.writeUInt16LE(extLen, 168);
  hookProgramIdBytes.copy(buf, 170, 0, 32);
  // authority bytes (170+32 onward) intentionally zero — parser does not read them.
  return buf;
}

function buildBaseSplMint() {
  // Classic SPL mint is exactly 82 bytes, owner = legacy SPL token program.
  return Buffer.alloc(82, 0);
}

function buildToken2022MintNoExtensions() {
  // Token-2022 mint with the account-type discriminator written but no TLV
  // extension records past it.
  const buf = Buffer.alloc(166, 0);
  buf.writeUInt8(1, 165);
  return buf;
}

function mockConn(accountInfoMap) {
  return {
    async getAccountInfo(mint) {
      const key = typeof mint === "string" ? mint : (mint?.toString?.() || String(mint));
      return accountInfoMap.get(key) || null;
    },
  };
}

// ── Tests ───────────────────────────────────────────────────────────────────

test("checkTransferHook: allowlisted programId → ok:true", async () => {
  const allowed = Array.from(ALLOWED_TRANSFER_HOOKS)[0];
  assert.ok(allowed, "expected at least one entry in ALLOWED_TRANSFER_HOOKS");
  const programIdBytes = decodeBase58Pubkey(allowed);
  const mintData = buildToken2022MintWithHook(programIdBytes);
  const mintAddr = "FakeMint1111111111111111111111111111111111111";
  const conn = mockConn(new Map([[
    mintAddr,
    { owner: TOKEN_2022_PROGRAM_ID, data: mintData },
  ]]));
  const res = await checkTransferHook(conn, mintAddr);
  assert.equal(res.ok, true);
  assert.equal(res.hookProgramId, allowed);
});

test("checkTransferHook: non-allowlisted programId → ok:false + TRANSFER_HOOK_NOT_ALLOWED", async () => {
  // Use a deterministic 32-byte programId that is NOT in the allowlist.
  const unknown = Buffer.alloc(32, 0);
  unknown[0] = 0xab;
  unknown[31] = 0xcd;
  const mintData = buildToken2022MintWithHook(unknown);
  const mintAddr = "FakeMint2222222222222222222222222222222222222";
  const conn = mockConn(new Map([[
    mintAddr,
    { owner: TOKEN_2022_PROGRAM_ID, data: mintData },
  ]]));
  const res = await checkTransferHook(conn, mintAddr);
  assert.equal(res.ok, false);
  assert.equal(res.reason, "TRANSFER_HOOK_NOT_ALLOWED");
  assert.ok(typeof res.hookProgramId === "string" && res.hookProgramId.length > 0);
  assert.ok(!ALLOWED_TRANSFER_HOOKS.has(res.hookProgramId));
});

test("checkTransferHook: legacy SPL mint (82 bytes, SPL owner) → ok:true", async () => {
  const mintAddr = "FakeMint3333333333333333333333333333333333333";
  const conn = mockConn(new Map([[
    mintAddr,
    { owner: SPL_TOKEN_PROGRAM_ID, data: buildBaseSplMint() },
  ]]));
  const res = await checkTransferHook(conn, mintAddr);
  assert.equal(res.ok, true);
  assert.equal(res.hookProgramId, undefined);
  assert.equal(res.reason, undefined);
});

test("checkTransferHook: Token-2022 mint with no extension records → ok:true", async () => {
  const mintAddr = "FakeMint4444444444444444444444444444444444444";
  const conn = mockConn(new Map([[
    mintAddr,
    { owner: TOKEN_2022_PROGRAM_ID, data: buildToken2022MintNoExtensions() },
  ]]));
  const res = await checkTransferHook(conn, mintAddr);
  assert.equal(res.ok, true);
});

test("checkTransferHook: missing mint (getAccountInfo → null) → ok:true (no double-fault)", async () => {
  const conn = mockConn(new Map());
  const res = await checkTransferHook(conn, "MissingMint5555555555555555555555555555555555");
  assert.equal(res.ok, true);
});

test("_parseTransferHookProgramId: zero programId (Pubkey::default) → null (no hook)", () => {
  const mintData = buildToken2022MintWithHook(Buffer.alloc(32, 0));
  assert.equal(_parseTransferHookProgramId(mintData), null);
});

test("_parseTransferHookProgramId: malformed TLV (length overruns buffer) → null", () => {
  // Build a transfer-hook header that claims a 9999-byte payload but
  // truncate the buffer right after the header.
  const buf = Buffer.alloc(166 + 4, 0);
  buf.writeUInt8(1, 165);
  buf.writeUInt16LE(EXTENSION_TYPE_TRANSFER_HOOK, 166);
  buf.writeUInt16LE(9999, 168);
  assert.equal(_parseTransferHookProgramId(buf), null);
});

test("_parseTransferHookProgramId: skips non-hook extension, finds hook in second TLV record", () => {
  // First record: some other extension (type 1, length 4)
  // Second record: transfer-hook with allowlisted programId
  const allowed = Array.from(ALLOWED_TRANSFER_HOOKS)[0];
  const programIdBytes = decodeBase58Pubkey(allowed);
  const buf = Buffer.alloc(166 + 4 + 4 + 4 + 64, 0);
  buf.writeUInt8(1, 165);
  // Other extension (type=1, len=4)
  buf.writeUInt16LE(1, 166);
  buf.writeUInt16LE(4, 168);
  // Transfer-hook record after it
  const hookOff = 166 + 4 + 4;
  buf.writeUInt16LE(EXTENSION_TYPE_TRANSFER_HOOK, hookOff);
  buf.writeUInt16LE(64, hookOff + 2);
  programIdBytes.copy(buf, hookOff + 4, 0, 32);
  assert.equal(_parseTransferHookProgramId(buf), allowed);
});
