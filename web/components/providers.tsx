"use client";

import { ReactNode, useMemo, type FC } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  ConnectionProvider,
  WalletProvider,
} from "@solana/wallet-adapter-react";
import { WalletModalProvider } from "@solana/wallet-adapter-react-ui";
import { clusterApiUrl } from "@solana/web3.js";
import { ToastProvider } from "@/components/ui/toaster";
import { MultiWalletProvider } from "@/components/providers/WalletProvider";

// Import wallet adapter CSS
import "@solana/wallet-adapter-react-ui/styles.css";

// `@solana/wallet-adapter-*` typings predate @types/react 18.3 (which dropped
// implicit `children` from FC<P>), so the providers fail as JSX components
// under the current types. Re-typing them locally as FC with explicit
// `children` is the minimum surface change that satisfies the compiler
// without touching upstream packages.
type ProviderWithChildren<P> = FC<P & { children?: ReactNode }>;
const ConnectionProviderT = ConnectionProvider as ProviderWithChildren<{
  endpoint: string;
  config?: Record<string, unknown>;
}>;
const WalletProviderT = WalletProvider as ProviderWithChildren<{
  wallets: unknown[];
  autoConnect?: boolean;
}>;
const WalletModalProviderT = WalletModalProvider as ProviderWithChildren<
  Record<string, unknown>
>;

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000, // 30 seconds
      gcTime: 5 * 60 * 1000, // 5 minutes (formerly cacheTime)
      refetchOnWindowFocus: false,
      retry: 2,
    },
  },
});

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  // Solana network and RPC endpoint
  const network = process.env.NEXT_PUBLIC_SOLANA_NETWORK || "mainnet-beta";
  const endpoint = useMemo(() => {
    // Use custom RPC if provided, otherwise use default
    if (process.env.NEXT_PUBLIC_SOLANA_RPC_URL) {
      return process.env.NEXT_PUBLIC_SOLANA_RPC_URL;
    }
    return clusterApiUrl(network as any);
  }, [network]);

  // Empty array - wallet adapter will auto-detect wallets via Wallet Standard
  // This is the recommended approach for modern wallet support
  const wallets = useMemo(() => [], []);

  return (
    <QueryClientProvider client={queryClient}>
      <ConnectionProviderT endpoint={endpoint}>
        <WalletProviderT wallets={wallets} autoConnect>
          <WalletModalProviderT>
            <MultiWalletProvider>
              <ToastProvider>{children}</ToastProvider>
            </MultiWalletProvider>
          </WalletModalProviderT>
        </WalletProviderT>
      </ConnectionProviderT>
    </QueryClientProvider>
  );
}
