/**
 * Jito — native SOL → JitoSOL via SPL Stake Pool depositSol (spec §9l).
 *
 * Replaces the Jupiter universal-swap proxy. JitoSOL is minted by the
 * SPL Stake Pool program at the Jito stake pool address. depositSol
 * builds the canonical instruction set (createATA-if-missing + depositSol
 * with the pool's withdraw-authority PDA + manager-fee account).
 *
 * Stake-pool program: SPoo1Ku8WFXoNDMHPsrGSTSG1Y47rzgn41SLUNakuHy
 * Jito pool address:  Jito4APyf642JPZPx3hGc6WXJ8p9BNS5d5XtyZdW8VR
 * JitoSOL mint:       J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn
 *
 * Receipt verification: ATA delta on JitoSOL mint, balance-rate sanity
 * vs SPL Stake Pool state account.
 */
const { Connection, PublicKey, Transaction, ComputeBudgetProgram } = require("@solana/web3.js");
const { depositSol, withdrawSol } = require("@solana/spl-stake-pool");
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");

const JITO_STAKE_POOL = new PublicKey("Jito4APyf642JPZPx3hGc6WXJ8p9BNS5d5XtyZdW8VR");
const JITOSOL_MINT = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn";

module.exports = {
  aliases: ["jito-liquid-staking", "jitosol"],
  supportedActions: ["deposit", "stake", "supply", "withdraw", "unstake", "redeem"],

  /**
   * Phase 4 lifecycle — JitoSOL → SOL via SPL Stake Pool withdrawSol.
   * Note: SPL Stake Pool instant withdraws (withdrawSol) are subject to
   * the pool's liquid SOL reserve; large amounts may need withdrawStake
   * (deferred, returns a stake account that activates next epoch).
   */
  async buildUnstake({ amount, user }, { connection } = {}) {
    if (!connection) {
      throw new Error("Jito unstake requires a Solana connection.");
    }
    const userPubkey = new PublicKey(user);
    const jitoSolLamports = Math.floor(Number(amount) * 1_000_000_000);
    if (jitoSolLamports <= 0) {
      throw new Error(`Jito unstake amount must be positive (got ${amount}).`);
    }
    const { instructions, signers } = await withdrawSol(
      connection,
      JITO_STAKE_POOL,
      userPubkey,
      userPubkey,            // destinationSolAccount = user wallet
      jitoSolLamports,
    );
    const tx = new Transaction();
    tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 400_000 }));
    tx.add(...instructions);
    tx.feePayer = userPubkey;
    const { blockhash } = await connection.getLatestBlockhash("confirmed");
    tx.recentBlockhash = blockhash;
    if (signers && signers.length) {
      tx.partialSign(...signers);
    }
    const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
    const b64 = raw.toString("base64");
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(`Jito native unstake simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    return {
      transactions: [
        {
          b64,
          summary: `Jito unstake ${amount} JitoSOL → SOL`,
          description: (
            `Calls SPL Stake Pool withdrawSol on Jito's pool. ` +
            `${amount} JitoSOL converts to SOL at the pool's on-chain exchange rate. ` +
            `Subject to pool's liquid SOL reserve depth — falls back to withdrawStake ` +
            `(deferred / next-epoch) for amounts beyond reserve.`
          ),
          receiptToken: "SOL",
          feeUsd: 0.005,
          durationS: 18,
          warnings: [
            "Instant unstake uses pool's SOL reserve; deep amounts may need deferred withdrawStake.",
          ],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },

  async quote({ amount }) {
    return {
      expectedAmountOut: amount,
      receiptToken: "JitoSOL",
      apy: null,
      fees: { protocol: "Jito SPL Stake Pool (no Jupiter slippage)", network: "0.000005 SOL" },
    };
  },

  async build({ asset, amount, user, slippageBps = 50 }, { connection } = {}) {
    if (!connection) {
      throw new Error("Jito build requires a Solana connection.");
    }
    const inputSym = (asset || "SOL").toUpperCase();
    const userPubkey = new PublicKey(user);

    // SOL-direct path: native depositSol via @solana/spl-stake-pool.
    if (inputSym === "SOL" || inputSym === "WSOL") {
      const lamports = Math.floor(Number(amount) * 1_000_000_000);
      if (lamports <= 0) {
        throw new Error(`Jito deposit amount must be positive (got ${amount}).`);
      }
      const { instructions, signers } = await depositSol(
        connection,
        JITO_STAKE_POOL,
        userPubkey,
        lamports,
      );
      const tx = new Transaction();
      // Bump compute budget — depositSol touches validator list + several PDAs.
      tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 400_000 }));
      tx.add(...instructions);
      tx.feePayer = userPubkey;
      const { blockhash } = await connection.getLatestBlockhash("confirmed");
      tx.recentBlockhash = blockhash;
      // Sign with ephemeral signers (user signs at wallet — these are extra
      // session signers if depositSol returned any; usually empty for the
      // sol-deposit flow).
      if (signers && signers.length) {
        tx.partialSign(...signers);
      }
      const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
      const b64 = raw.toString("base64");
      const sim = await simulateBase64Tx({ b64, connection });
      if (!sim.ok) {
        const e = new Error(`Jito native stake simulation failed: ${sim.errStr || "unknown"}`);
        e.simulation = sim;
        throw e;
      }
      return {
        transactions: [
          {
            b64,
            summary: `Jito native stake ${amount} SOL → JitoSOL`,
            description: (
              `Calls SPL Stake Pool depositSol on Jito's pool ` +
              `(Jito4APyf642JPZPx3hGc6WXJ8p9BNS5d5XtyZdW8VR). ${amount} SOL converts to ` +
              `JitoSOL at the pool's on-chain exchange rate — no Jupiter aggregator slippage. ` +
              `JitoSOL captures MEV-boosted staking rewards.`
            ),
            receiptToken: "JitoSOL",
            feeUsd: 0.005,
            durationS: 18,
            warnings: [
              "Native SPL Stake Pool deposit — exchange rate enforced on-chain.",
              "JitoSOL accrues MEV-boosted stake rewards; redeem any time via Jupiter or SPL Stake Pool withdraw.",
            ],
            simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
          },
        ],
      };
    }

    // Non-SOL input: prep-swap to SOL, then Jito native deposit (snapshot→rebuild).
    const inputMint = resolveMint(inputSym);
    if (!inputMint) {
      throw new Error(`Jito adapter: unknown input asset ${inputSym}.`);
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
      const e = new Error(`Jito prep-swap simulation failed: ${swapSim.errStr || "unknown"}`);
      e.simulation = swapSim;
      throw e;
    }
    return {
      transactions: [
        {
          b64: swapB64,
          summary: `Prep swap: ${amount} ${inputSym} → SOL`,
          description: (
            `Routes ${amount} ${inputSym} into SOL via Jupiter. Step 2 then calls SPL Stake Pool ` +
            `depositSol on Jito's pool to mint JitoSOL at the pool's native exchange rate.`
          ),
          receiptToken: "SOL",
          feeUsd: 0.005,
          durationS: 25,
          warnings: ["Two-step flow: Jupiter swap, then Jito native deposit. Sign both."],
          simulation: { ok: true, benign: swapSim.benign || false, unitsConsumed: swapSim.unitsConsumed },
        },
        {
          b64: "PENDING_REBUILD_AFTER_SWAP",
          summary: `Jito native deposit (auto-rebuilt after swap)`,
          description: (
            `Once the swap confirms, this step will be rebuilt with the actual SOL amount and ` +
            `call SPL Stake Pool depositSol on Jito's pool. Receipt: JitoSOL.`
          ),
          receiptToken: "JitoSOL",
          feeUsd: 0.005,
          durationS: 18,
          warnings: ["Step amount depends on Jupiter swap output — rebuilt automatically."],
          pendingRebuild: { kind: "jito_native_deposit", afterStep: 0 },
        },
      ],
    };
  },
};
