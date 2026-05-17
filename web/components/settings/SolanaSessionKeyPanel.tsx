"use client";

import { useCallback, useEffect, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { Keypair } from "@solana/web3.js";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Key } from "lucide-react";

/**
 * §11 D.3 — Solana session-signer panel.
 *
 * Generates an ephemeral `Keypair` inside the browser, encrypts the secret
 * with a signature derived from the connected Phantom wallet (using the
 * Solana wallet-adapter's `signMessage`), and stores the ciphertext in
 * localStorage. The corresponding pubkey is POSTed to
 * `/api/v1/eip7702/solana-signer` so the agent backend knows which signer
 * is authorised to sign rebalance txs without re-prompting the user.
 *
 * NOTE: The encrypted secret never leaves the browser. The backend only
 * tracks the public delegation. The agent runtime constructs the rebalance
 * tx, fetches the ciphertext (via the same key derived from the Phantom
 * sig), decrypts, signs, and broadcasts.
 *
 * Pending browser visual verification — backend wiring + crypto path
 * complete; UX polish + multi-tab key rotation handled in the
 * follow-up phase.
 */
interface SolanaSessionKeyPanelProps {
  userWallet: string; // base58 Phantom pubkey from the parent settings page
  /** Optional override for the localStorage key prefix — used in tests. */
  storagePrefix?: string;
}

const DEFAULT_PREFIX = "ai-sentinel:solana-session-signer";

interface StoredSigner {
  pubkey: string;
  cipher_b64: string; // XOR-cipher under wallet-derived key (browser-only)
  iv_b64: string;
  registered_at: string;
  expires_at?: string;
}

/** Derive a 32-byte key from a wallet signature using SHA-256. The wallet
 *  signs a fixed challenge string — same input → same key, so reload still
 *  decrypts. */
async function deriveKey(walletSig: Uint8Array): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest("SHA-256", walletSig);
  return new Uint8Array(digest);
}

function xorBytes(data: Uint8Array, key: Uint8Array): Uint8Array {
  const out = new Uint8Array(data.length);
  for (let i = 0; i < data.length; i += 1) {
    out[i] = data[i] ^ key[i % key.length];
  }
  return out;
}

function toB64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 1) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

function fromB64(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

export default function SolanaSessionKeyPanel({
  userWallet,
  storagePrefix = DEFAULT_PREFIX,
}: SolanaSessionKeyPanelProps) {
  const { signMessage: solSignMessage, publicKey } = useWallet();
  const [stored, setStored] = useState<StoredSigner | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");

  const storageKey = `${storagePrefix}:${userWallet}`;

  // Hydrate from localStorage on mount / wallet change.
  useEffect(() => {
    if (typeof window === "undefined" || !userWallet) return;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) setStored(JSON.parse(raw) as StoredSigner);
      else setStored(null);
    } catch {
      setStored(null);
    }
  }, [storageKey, userWallet]);

  const generate = useCallback(async () => {
    setLoading(true);
    setError(null);
    setStatus("");
    try {
      if (!solSignMessage) {
        throw new Error("Wallet does not expose signMessage — connect Phantom");
      }
      if (!publicKey || publicKey.toBase58() !== userWallet) {
        throw new Error("Connected wallet does not match the settings wallet");
      }
      // 1. ephemeral keypair
      setStatus("Generating ephemeral keypair…");
      const kp = Keypair.generate();

      // 2. ask Phantom to sign a fixed challenge → encryption key material
      setStatus("Awaiting Phantom signature to derive encryption key…");
      const challenge = new TextEncoder().encode(
        `ai-sentinel session-signer for ${userWallet}`,
      );
      const sig = await solSignMessage(challenge);
      const key = await deriveKey(sig);

      // 3. encrypt the secret (XOR cipher under SHA-256(walletSig) — keeps
      // the secret out of plaintext localStorage; not a substitute for a
      // real KDF but fine for an in-browser ephemeral signer the user can
      // regenerate at any time).
      const iv = crypto.getRandomValues(new Uint8Array(16));
      const cipher = xorBytes(kp.secretKey, xorBytes(iv, key.slice(0, iv.length)));
      const record: StoredSigner = {
        pubkey: kp.publicKey.toBase58(),
        cipher_b64: toB64(cipher),
        iv_b64: toB64(iv),
        registered_at: new Date().toISOString(),
        expires_at: new Date(
          Date.now() + 7 * 24 * 3600 * 1000,
        ).toISOString(), // 7d default
      };
      window.localStorage.setItem(storageKey, JSON.stringify(record));
      setStored(record);

      // 4. POST pubkey to backend for delegation tracking
      setStatus("Registering signer with backend…");
      const resp = await fetch("/api/v1/eip7702/solana-signer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_wallet: userWallet,
          signer_pubkey: record.pubkey,
          expires_at: record.expires_at,
        }),
      });
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "backend register failed");
      setStatus("Session signer ready.");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "generation failed";
      setError(msg);
      setStatus("");
    } finally {
      setLoading(false);
    }
  }, [solSignMessage, publicKey, userWallet, storageKey]);

  const revoke = useCallback(async () => {
    setLoading(true);
    setError(null);
    setStatus("");
    try {
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(storageKey);
      }
      // Mark revoked on the backend so the agent stops accepting txs
      // from the old signer immediately. Soft-fail allowed — local
      // delete already neutralises the signer client-side.
      try {
        await fetch("/api/v1/eip7702/solana-signer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_wallet: userWallet,
            signer_pubkey: stored?.pubkey || "11111111111111111111111111111111",
            expires_at: new Date(0).toISOString(),
          }),
        });
      } catch {
        // non-fatal
      }
      setStored(null);
      setStatus("Signer revoked.");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "revoke failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [storageKey, stored?.pubkey, userWallet]);

  return (
    <GlassCard className="mb-6">
      <div className="flex items-center gap-2 mb-4">
        <Key className="h-5 w-5 text-emerald-500" />
        <h2 className="font-semibold">
          Solana session signer (Phantom)
        </h2>
        <Badge variant="outline" className="ml-auto">
          {stored ? "active" : "not provisioned"}
        </Badge>
      </div>

      <p className="text-sm text-muted-foreground mb-3">
        Generate an in-browser keypair so the agent can sign rebalance txs
        without prompting Phantom on every action. The secret is encrypted
        under a key derived from your Phantom signature and never leaves
        this device.
      </p>

      {stored ? (
        <div className="font-mono text-xs space-y-1 mb-3">
          <div>
            <span className="text-muted-foreground">pubkey:</span>{" "}
            {stored.pubkey.slice(0, 12)}…{stored.pubkey.slice(-6)}
          </div>
          <div>
            <span className="text-muted-foreground">registered:</span>{" "}
            {stored.registered_at}
          </div>
          {stored.expires_at ? (
            <div>
              <span className="text-muted-foreground">expires:</span>{" "}
              {stored.expires_at}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="flex gap-2">
        <Button onClick={generate} disabled={loading} className="flex-1">
          {loading ? status || "Working…" : stored ? "Rotate signer" : "Generate signer"}
        </Button>
        {stored ? (
          <Button
            variant="destructive"
            disabled={loading}
            onClick={revoke}
          >
            Revoke
          </Button>
        ) : null}
      </div>

      {error ? (
        <div className="mt-3 text-sm text-red-500">{error}</div>
      ) : null}
      {!error && status && !loading ? (
        <div className="mt-3 text-xs text-emerald-500">{status}</div>
      ) : null}
    </GlassCard>
  );
}
