/**
 * Marinade — native SOL → mSOL via marinade-ts-sdk (spec §9l).
 *
 * Replaces the Jupiter universal-swap proxy. Uses Marinade's own program
 * (MarBmsSgKXdrN1egZf5sqe1TMThiL5GkpwDnnvVm4iJ) directly so the user
 * pays the protocol's exchange rate, not Jupiter's slippage tax. Receipt
 * is mSOL SPL token, balance-delta verifiable.
 *
 * Two entrypoints:
 *   - deposit(sol_amount)               → mSOL instant liquid
 *   - depositStakeAccount(stakeAccount) → mSOL no cool-down (next-epoch activation)
 *
 * For non-SOL inputs (USDC, USDT, ETH, etc.) the adapter still requires
 * a Jupiter prep-swap leg because Marinade only accepts SOL natively.
 * Surface this as two signed transactions in chat.
 */
const { Connection, Keypair, PublicKey, Transaction } = require("@solana/web3.js");
const BN = require("bn.js");
const { Marinade, MarinadeConfig } = require("@marinade.finance/marinade-ts-sdk");
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");
const { checkTxAccountCount } = require("./altSplit");

const MSOL_MINT = "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So";
// Marinade staking program (canonical mainnet ID, surfaced as redemption_program
// for receipt-reader matching on Phase C order_unstake / liquid unstake legs).
const MARINADE_PROGRAM_ID = "MarBmsSgKXdrN1egZf5sqe1TMThczhMLJhYpaUm1cmRr";

module.exports = {
  aliases: ["marinade-finance", "marinade-liquid-staking", "marinade-native-staking"],
  supportedActions: ["deposit", "supply", "stake", "withdraw", "unstake", "redeem", "order_unstake"],
  MARINADE_PROGRAM_ID,

  async quote({ amount }) {
    return {
      expectedAmountOut: amount,
      receiptToken: "mSOL",
      apy: null,
      fees: { protocol: "Marinade native (no Jupiter slippage)", network: "0.000005 SOL" },
    };
  },

  /**
   * Phase 4 lifecycle — Marinade native liquid unstake (mSOL → SOL).
   * Uses marinade.liquidUnstake(amount_mSOL). Subject to ~0.3% fee +
   * pool depth. For amount==0 (full unstake), the runtime must fetch
   * the user's full mSOL balance first.
   */
  async buildUnstake({ amount, user }, { connection } = {}) {
    if (!connection) {
      throw new Error("Marinade unstake requires a Solana connection.");
    }
    const userPubkey = new PublicKey(user);
    const config = new MarinadeConfig({ connection, publicKey: userPubkey });
    const marinade = new Marinade(config);
    const mSOL_lamports = new BN(Math.floor(Number(amount) * 1_000_000_000));
    if (mSOL_lamports.lte(new BN(0))) {
      throw new Error(`Marinade unstake amount must be positive (got ${amount}).`);
    }
    const { transaction } = await marinade.liquidUnstake(mSOL_lamports);
    transaction.feePayer = userPubkey;
    const { blockhash } = await connection.getLatestBlockhash("confirmed");
    transaction.recentBlockhash = blockhash;
    const raw = transaction.serialize({
      requireAllSignatures: false,
      verifySignatures: false,
    });
    const b64 = raw.toString("base64");
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(`Marinade native unstake simulation failed: ${sim.errStr || "unknown"}`);
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
          summary: `Marinade liquid unstake ${amount} mSOL → SOL`,
          description: (
            `Calls Marinade liquidUnstake(${amount} mSOL). Returns SOL immediately via ` +
            `Marinade's instant-unstake liquidity pool. Fee ~0.3% on top of exchange rate.`
          ),
          receiptToken: "SOL",
          redemption_program: MARINADE_PROGRAM_ID,
          feeUsd: 0.005,
          durationS: 15,
          warnings: [
            "Instant unstake incurs ~0.3% Marinade fee; deferred unstake (next epoch) is fee-free.",
            ...altWarn,
          ],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },

  /**
   * Phase C lifecycle — Marinade order_unstake (deferred, fee-free).
   *
   * Calls marinade.orderUnstake(mSOL_amount) which:
   *   - Burns mSOL from the user.
   *   - Creates a TicketAccount (a fresh Keypair signer the sidecar generates).
   *   - The user can claim the SOL after the next epoch boundary
   *     (~2-3 days on mainnet) by calling claim() on the ticket.
   *
   * The TicketAccount Keypair MUST partial-sign the tx — its secret is
   * burned after signing (single-use). We return the ticket pubkey so
   * the receipt-reader / position-store can track the pending claim.
   */
  async buildOrderUnstake({ amount, user, extra = {} }, { connection } = {}) {
    if (!connection) {
      throw new Error("Marinade orderUnstake requires a Solana connection.");
    }
    const userPubkey = new PublicKey(user);
    const config = new MarinadeConfig({ connection, publicKey: userPubkey });
    const marinade = new Marinade(config);
    const mSOL_lamports = new BN(Math.floor(Number(amount) * 1_000_000_000));
    if (mSOL_lamports.lte(new BN(0))) {
      throw new Error(`Marinade orderUnstake amount must be positive (got ${amount}).`);
    }

    // SDK signature: orderUnstake(amount, ticketAccountKeypair?) — when no
    // ticket keypair passed, the SDK generates one and returns it as a signer.
    const result = await marinade.orderUnstake(mSOL_lamports);
    const transaction = result.transaction || result.tx;
    // ticketAccount can come back as a Keypair or as { publicKey, secretKey }
    // depending on SDK version. Normalise to pubkey + signer.
    const ticketKeypair = result.ticketAccountKeypair || result.ticket || result.newTicketAccount;
    if (!transaction) {
      throw new Error("Marinade orderUnstake: SDK returned no transaction.");
    }
    transaction.feePayer = userPubkey;
    const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash("confirmed");
    transaction.recentBlockhash = blockhash;
    // The TicketAccount Keypair is generated client-side and MUST sign the
    // create-account IX or the tx reverts. partialSign before serialise.
    if (ticketKeypair && typeof transaction.partialSign === "function") {
      transaction.partialSign(ticketKeypair);
    }
    const raw = transaction.serialize({
      requireAllSignatures: false,
      verifySignatures: false,
    });
    const b64 = raw.toString("base64");
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(`Marinade orderUnstake simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    const sz = checkTxAccountCount(b64);
    const altWarn = sz.needsSplit
      ? ["Transaction has " + sz.accounts + " accounts. Hardware wallets may need ALT pre-warming."]
      : [];

    // Lockup end: next epoch boundary. Solana epochs ≈ 2-3 days. Compute a
    // conservative ts hint (now + 3d) so the UI can render a "ready ~Thu" badge.
    const lockupEndTs = Math.floor(Date.now() / 1000) + 3 * 24 * 60 * 60;
    const ticketPubkey = ticketKeypair?.publicKey
      ? ticketKeypair.publicKey.toBase58()
      : null;

    return {
      transactions: [
        {
          b64,
          summary: `Marinade order unstake ${amount} mSOL (next-epoch claim)`,
          description: (
            `Calls Marinade orderUnstake(${amount} mSOL). Burns the mSOL and creates a ` +
            `TicketAccount${ticketPubkey ? ` (${ticketPubkey.slice(0, 8)}…)` : ""} that becomes ` +
            `claimable for SOL after the next epoch boundary (~2-3 days on mainnet). ` +
            `Fee-free vs liquid unstake's ~0.3% pool fee.`
          ),
          receiptToken: "SOL",
          redemption_program: MARINADE_PROGRAM_ID,
          unstake_ticket: ticketPubkey,
          lockup_end_ts: lockupEndTs,
          feeUsd: 0.005,
          durationS: 15,
          warnings: [
            "Delayed unstake: SOL is NOT immediately available — claim after next epoch boundary (~2-3 days).",
            "Lose the ticket pubkey = lose the SOL. The agent's position-store will retain it for you.",
            "For instant liquidity use 'unstake' (liquid) which costs ~0.3% fee.",
            ...altWarn,
          ],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },

  /**
   * Build deposit transaction(s).
   * - SOL-input → single tx: marinade.deposit(amount)
   * - Non-SOL input → two txs: Jupiter prep-swap → SOL, then marinade.deposit
   */
  async build({ asset, amount, user, slippageBps = 50 }, { connection } = {}) {
    if (!connection) {
      throw new Error("Marinade build requires a Solana connection.");
    }
    const inputSym = (asset || "SOL").toUpperCase();
    const userPubkey = new PublicKey(user);

    const config = new MarinadeConfig({
      connection,
      publicKey: userPubkey,
    });
    const marinade = new Marinade(config);

    // SOL-direct path: one signed tx, no Jupiter leg.
    if (inputSym === "SOL" || inputSym === "WSOL") {
      const lamports = new BN(Math.floor(Number(amount) * 1_000_000_000));
      if (lamports.lte(new BN(0))) {
        throw new Error(`Marinade deposit amount must be positive (got ${amount}).`);
      }
      const { transaction } = await marinade.deposit(lamports);
      transaction.feePayer = userPubkey;
      const { blockhash } = await connection.getLatestBlockhash("confirmed");
      transaction.recentBlockhash = blockhash;
      const raw = transaction.serialize({
        requireAllSignatures: false,
        verifySignatures: false,
      });
      const b64 = raw.toString("base64");
      const sim = await simulateBase64Tx({ b64, connection });
      if (!sim.ok) {
        const e = new Error(`Marinade native deposit simulation failed: ${sim.errStr || "unknown"}`);
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
            summary: `Marinade native stake ${amount} SOL → mSOL`,
            description: (
              `Calls Marinade's deposit program directly (MarBmsSgKXdrN1egZf5sqe1TMThiL5GkpwDnnvVm4iJ). ` +
              `${amount} SOL converts to mSOL at Marinade's exchange rate — no Jupiter aggregator slippage.`
            ),
            receiptToken: "mSOL",
            feeUsd: 0.005,
            durationS: 15,
            warnings: [
              "Native stake via Marinade program — exchange rate enforced on-chain.",
              "mSOL accrues stake rewards; redeem any time via Jupiter or Marinade unstake.",
              ...altWarn,
            ],
            simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
          },
        ],
      };
    }

    // Non-SOL input: prep-swap leg through Jupiter into SOL, then Marinade native deposit.
    // (We can't bundle this into one signed tx without exceeding 1232-byte limit + losing
    // Marinade's native exchange rate. Two signatures is the right default per spec §6b.)
    const inputMint = resolveMint(inputSym);
    if (!inputMint) {
      throw new Error(`Marinade adapter: unknown input asset ${inputSym}.`);
    }
    const inputDecimals = decimalsFor(inputSym) || 9;
    const { tx: swapB64 } = await buildSwap({
      inputMint,
      outputMint: SOL_MINT,
      amount,
      user,
      slippageBps,
      decimals: inputDecimals,
    });
    const swapSim = await simulateBase64Tx({ b64: swapB64, connection });
    if (!swapSim.ok) {
      const e = new Error(`Marinade prep-swap simulation failed: ${swapSim.errStr || "unknown"}`);
      e.simulation = swapSim;
      throw e;
    }

    // For the deposit leg we can only build calldata after the swap confirms
    // (we don't know exact SOL out yet). Emit a placeholder describing the
    // dependent flow; the runtime rebuilds the second leg post-swap-confirm
    // using the actual SOL delta. This is the snapshot→rebuild pattern (§6c).
    return {
      transactions: [
        {
          b64: swapB64,
          summary: `Prep swap: ${amount} ${inputSym} → SOL`,
          description: (
            `Routes ${amount} ${inputSym} into SOL via Jupiter. Step 2 then calls Marinade's ` +
            `deposit program directly to mint mSOL at Marinade's native exchange rate.`
          ),
          receiptToken: "SOL",
          feeUsd: 0.005,
          durationS: 25,
          warnings: ["Two-step flow: Jupiter swap, then Marinade native deposit. Sign both."],
          simulation: { ok: true, benign: swapSim.benign || false, unitsConsumed: swapSim.unitsConsumed },
        },
        {
          // Placeholder — runtime rebuilds with actual SOL delta after swap confirms.
          b64: "PENDING_REBUILD_AFTER_SWAP",
          summary: `Marinade native deposit (auto-rebuilt after swap)`,
          description: (
            `Once the swap confirms, this step will be rebuilt with the actual SOL amount ` +
            `and call marinade.deposit(amount) on Marinade's program. Receipt: mSOL.`
          ),
          receiptToken: "mSOL",
          feeUsd: 0.005,
          durationS: 15,
          warnings: ["Step amount depends on Jupiter swap output — rebuilt automatically."],
          pendingRebuild: { kind: "marinade_native_deposit", afterStep: 0 },
        },
      ],
    };
  },
};
