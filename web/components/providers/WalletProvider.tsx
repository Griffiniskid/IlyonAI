"use client";
import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import * as metamask from "@/lib/wallets/metamask";
import * as phantom from "@/lib/wallets/phantom";

// ---------------------------------------------------------------------------
// Spec §5 / §8 — Signer Orchestrator wallet handshake (PDF p.10, lines 398-400):
//   "Wallet handshake (Phantom + Solflare + WalletConnect for Solana;
//    MetaMask + WalletConnect for EVM; Phantom for EVM where supported)."
//
// Spec §7 scenario #15 (PDF p.17): wrong-wallet-for-chain detector must know
// the full per-chain-family wallet catalog at planning time, not at sign time.
//
// This module exposes the Wallet-Standard-shaped catalog so callers (chat
// planner, signer orchestrator, /agent/swap UI) can introspect available
// adapters BEFORE prompting connect. Adapters whose npm package is not yet
// installed are surfaced as `available: false` stubs whose `connect()` throws
// a deterministic "package missing" error — so the spec contract surface is
// present today and the wiring becomes a one-line npm install + import swap
// when the deps land.
// ---------------------------------------------------------------------------

export type ChainFamily = "evm" | "solana";

export interface WalletAdapter {
  /** Stable adapter id matching Wallet-Standard convention. */
  id: string;
  /** Human-readable label for the connect-wallet UI. */
  name: ChainFamily extends never ? never : string;
  /** Which chain family this adapter signs for. */
  family: ChainFamily;
  /** True iff the underlying npm package is installed AND import resolved. */
  available: boolean;
  /** Adapter-specific connect. Returns the address string. */
  connect: () => Promise<string>;
  /** Sign an arbitrary UTF-8 message; returns base64 or 0x-hex per family. */
  signMessage: (msg: string) => Promise<string>;
}

const missing =
  (pkg: string, adapter: string) =>
  async (): Promise<never> => {
    throw new Error(
      `[wallet] ${adapter} adapter not available — npm install ${pkg} required ` +
        `(spec §5 Signer Orchestrator wallet handshake)`,
    );
  };

// EVM adapters --------------------------------------------------------------
const metamaskAdapter: WalletAdapter = {
  id: "metamask",
  name: "MetaMask",
  family: "evm",
  available: true,
  connect: () => metamask.connect(),
  signMessage: (msg) => metamask.signMessage(msg),
};

const walletConnectEvmAdapter: WalletAdapter = {
  id: "walletconnect-evm",
  name: "WalletConnect",
  family: "evm",
  available: false, // requires: @walletconnect/ethereum-provider
  connect: missing("@walletconnect/ethereum-provider", "WalletConnect (EVM)"),
  signMessage: missing("@walletconnect/ethereum-provider", "WalletConnect (EVM)"),
};

const coinbaseEvmAdapter: WalletAdapter = {
  id: "coinbase-wallet",
  name: "Coinbase Wallet",
  family: "evm",
  available: false, // requires: @coinbase/wallet-sdk (not in spec §5 but common; opt-in)
  connect: missing("@coinbase/wallet-sdk", "Coinbase Wallet"),
  signMessage: missing("@coinbase/wallet-sdk", "Coinbase Wallet"),
};

// Solana adapters -----------------------------------------------------------
const phantomAdapter: WalletAdapter = {
  id: "phantom",
  name: "Phantom",
  family: "solana",
  available: true,
  connect: () => phantom.connect(),
  signMessage: async (msg) => {
    const sig = await phantom.signMessage(msg);
    return btoa(String.fromCharCode(...Array.from(sig)));
  },
};

const solflareAdapter: WalletAdapter = {
  id: "solflare",
  name: "Solflare",
  family: "solana",
  available: false, // requires: @solana/wallet-adapter-solflare
  connect: missing("@solana/wallet-adapter-solflare", "Solflare"),
  signMessage: missing("@solana/wallet-adapter-solflare", "Solflare"),
};

const walletConnectSolanaAdapter: WalletAdapter = {
  id: "walletconnect-solana",
  name: "WalletConnect (Solana)",
  family: "solana",
  available: false, // requires: @walletconnect/solana-adapter (or equivalent)
  connect: missing("@walletconnect/solana-adapter", "WalletConnect (Solana)"),
  signMessage: missing("@walletconnect/solana-adapter", "WalletConnect (Solana)"),
};

/**
 * Spec-mandated wallet catalog. Order matches spec §5 reading:
 *   EVM:    MetaMask, WalletConnect, (Coinbase opt-in)
 *   Solana: Phantom, Solflare, WalletConnect
 *
 * Consumers should filter by `family` and `available` before rendering.
 */
export const WALLET_ADAPTERS: ReadonlyArray<WalletAdapter> = [
  metamaskAdapter,
  walletConnectEvmAdapter,
  coinbaseEvmAdapter,
  phantomAdapter,
  solflareAdapter,
  walletConnectSolanaAdapter,
];

export function getAdaptersForFamily(family: ChainFamily): WalletAdapter[] {
  return WALLET_ADAPTERS.filter((a) => a.family === family);
}

export function getAvailableAdapters(family?: ChainFamily): WalletAdapter[] {
  return WALLET_ADAPTERS.filter(
    (a) => a.available && (family === undefined || a.family === family),
  );
}

interface WalletState {
  evmAddress: string | null;
  solAddress: string | null;
  /** Active adapter id per family (for UX + scenario #15 detector). */
  activeEvmAdapter: string | null;
  activeSolAdapter: string | null;
  connectEvm: (adapterId?: string) => Promise<void>;
  connectSol: (adapterId?: string) => Promise<void>;
  signMessage: (msg: string) => Promise<string>;
  /** Spec-mandated catalog accessor for connect-wallet UI. */
  adapters: ReadonlyArray<WalletAdapter>;
}

const WalletCtx = createContext<WalletState>({
  evmAddress: null,
  solAddress: null,
  activeEvmAdapter: null,
  activeSolAdapter: null,
  connectEvm: async () => {},
  connectSol: async () => {},
  signMessage: async () => "",
  adapters: WALLET_ADAPTERS,
});

export function useMultiWallet() {
  return useContext(WalletCtx);
}

export function MultiWalletProvider({ children }: { children: ReactNode }) {
  const [evmAddress, setEvm] = useState<string | null>(null);
  const [solAddress, setSol] = useState<string | null>(null);
  const [activeEvmAdapter, setActiveEvm] = useState<string | null>(null);
  const [activeSolAdapter, setActiveSol] = useState<string | null>(null);

  const connectEvm = useCallback(async (adapterId: string = "metamask") => {
    const adapter = WALLET_ADAPTERS.find(
      (a) => a.id === adapterId && a.family === "evm",
    );
    if (!adapter) {
      throw new Error(`[wallet] unknown EVM adapter "${adapterId}"`);
    }
    const addr = await adapter.connect();
    setEvm(addr);
    setActiveEvm(adapter.id);
  }, []);

  const connectSol = useCallback(async (adapterId: string = "phantom") => {
    const adapter = WALLET_ADAPTERS.find(
      (a) => a.id === adapterId && a.family === "solana",
    );
    if (!adapter) {
      throw new Error(`[wallet] unknown Solana adapter "${adapterId}"`);
    }
    const addr = await adapter.connect();
    setSol(addr);
    setActiveSol(adapter.id);
  }, []);

  const signMessage = useCallback(
    async (msg: string) => {
      if (evmAddress && activeEvmAdapter) {
        const adapter = WALLET_ADAPTERS.find((a) => a.id === activeEvmAdapter);
        if (adapter) return adapter.signMessage(msg);
      }
      if (solAddress && activeSolAdapter) {
        const adapter = WALLET_ADAPTERS.find((a) => a.id === activeSolAdapter);
        if (adapter) return adapter.signMessage(msg);
      }
      // Fallback preserves legacy behavior (Phantom-first) for any caller that
      // signed messages before an adapter was explicitly selected.
      if (evmAddress) return metamask.signMessage(msg);
      const sig = await phantom.signMessage(msg);
      return btoa(String.fromCharCode(...Array.from(sig)));
    },
    [evmAddress, solAddress, activeEvmAdapter, activeSolAdapter],
  );

  return (
    <WalletCtx.Provider
      value={{
        evmAddress,
        solAddress,
        activeEvmAdapter,
        activeSolAdapter,
        connectEvm,
        connectSol,
        signMessage,
        adapters: WALLET_ADAPTERS,
      }}
    >
      {children}
    </WalletCtx.Provider>
  );
}
