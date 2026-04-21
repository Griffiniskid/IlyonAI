"use client";
import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import * as metamask from "@/lib/wallets/metamask";
import * as phantom from "@/lib/wallets/phantom";

interface WalletState {
  evmAddress: string | null;
  solAddress: string | null;
  connectEvm: () => Promise<void>;
  connectSol: () => Promise<void>;
  signMessage: (msg: string) => Promise<string>;
}

const WalletCtx = createContext<WalletState>({
  evmAddress: null, solAddress: null,
  connectEvm: async () => {}, connectSol: async () => {},
  signMessage: async () => "",
});

export function useMultiWallet() { return useContext(WalletCtx); }

export function MultiWalletProvider({ children }: { children: ReactNode }) {
  const [evmAddress, setEvm] = useState<string | null>(null);
  const [solAddress, setSol] = useState<string | null>(null);

  const connectEvm = useCallback(async () => {
    const addr = await metamask.connect();
    setEvm(addr);
  }, []);

  const connectSol = useCallback(async () => {
    const addr = await phantom.connect();
    setSol(addr);
  }, []);

  const signMessage = useCallback(async (msg: string) => {
    if (evmAddress) {
      return metamask.signMessage(msg);
    }
    const sig = await phantom.signMessage(msg);
    return btoa(String.fromCharCode(...sig));
  }, [evmAddress]);

  return (
    <WalletCtx.Provider value={{ evmAddress, solAddress, connectEvm, connectSol, signMessage }}>
      {children}
    </WalletCtx.Provider>
  );
}
