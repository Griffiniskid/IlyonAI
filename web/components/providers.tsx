"use client";

import { ReactNode, useMemo } from "react";
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
      <ConnectionProvider endpoint={endpoint}>
        <WalletProvider wallets={wallets} autoConnect>
          <WalletModalProvider>
            <MultiWalletProvider>
              <ToastProvider>{children}</ToastProvider>
            </MultiWalletProvider>
          </WalletModalProvider>
        </WalletProvider>
      </ConnectionProvider>
    </QueryClientProvider>
  );
}
