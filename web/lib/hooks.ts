"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useWallet } from "@solana/wallet-adapter-react";
import { useCallback, useState } from "react";
import * as api from "./api";
import type { AnalysisMode, AnalysisResponse } from "@/types";

// ═══════════════════════════════════════════════════════════════════════════
// ANALYSIS HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function useAnalyzeToken() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ address, mode }: { address: string; mode?: AnalysisMode }) =>
      api.analyzeToken(address, mode),
    onSuccess: (data, variables) => {
      // Cache the result
      queryClient.setQueryData(["token", variables.address], data);
    },
  });
}

export function useTokenAnalysis(address: string | null) {
  return useQuery({
    queryKey: ["token", address],
    queryFn: () => api.getTokenAnalysis(address!),
    enabled: !!address,
    staleTime: 2 * 60 * 1000, // 2 minutes
  });
}

export function useRefreshAnalysis() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ address, mode }: { address: string; mode?: AnalysisMode }) =>
      api.refreshAnalysis(address, mode),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["token", variables.address], data);
    },
  });
}

export function useSearchTokens(query: string) {
  return useQuery({
    queryKey: ["search", query],
    queryFn: () => api.searchTokens(query),
    enabled: query.length >= 2,
    staleTime: 60 * 1000, // 1 minute
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// TRENDING HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function useTrendingTokens(
  category: "trending" | "gainers" | "losers" | "new" = "trending"
) {
  return useQuery({
    queryKey: ["trending", category],
    queryFn: () => api.getTrendingTokens(category),
    staleTime: 30 * 1000, // 30 seconds
    refetchInterval: 30 * 1000, // Auto-refresh every 30s
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// PORTFOLIO HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function usePortfolio() {
  return useQuery({
    queryKey: ["portfolio"],
    queryFn: api.getPortfolio,
    staleTime: 60 * 1000, // 1 minute
  });
}

export function useWalletPortfolio(wallet: string | null) {
  return useQuery({
    queryKey: ["portfolio", wallet],
    queryFn: () => api.getWalletPortfolio(wallet!),
    enabled: !!wallet,
    staleTime: 60 * 1000,
  });
}

export function useTrackedWallets() {
  return useQuery({
    queryKey: ["trackedWallets"],
    queryFn: api.getTrackedWallets,
    staleTime: 60 * 1000,
  });
}

export function useTrackWallet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ address, label }: { address: string; label?: string }) =>
      api.trackWallet(address, label),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trackedWallets"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    },
  });
}

export function useUntrackWallet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (address: string) => api.untrackWallet(address),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trackedWallets"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    },
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// WHALE HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function useWhaleActivity(params?: {
  token?: string;
  minAmountUsd?: number;
  type?: "buy" | "sell";
  limit?: number;
}) {
  return useQuery({
    queryKey: ["whales", params],
    queryFn: () => api.getWhaleActivity(params),
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: 60 * 1000, // Auto-refresh every minute
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// DASHBOARD STATS HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboardStats"],
    queryFn: api.getDashboardStats,
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: 60 * 1000, // Auto-refresh every minute
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// AUTH HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function useAuth() {
  const { publicKey, signMessage, connected } = useWallet();
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const queryClient = useQueryClient();

  const authenticate = useCallback(async () => {
    if (!publicKey || !signMessage) {
      throw new Error("Wallet not connected");
    }

    setIsAuthenticating(true);

    try {
      // Get challenge
      const { challenge, message } = await api.getAuthChallenge(publicKey.toBase58());

      // Sign the message
      const encodedMessage = new TextEncoder().encode(message);
      const signature = await signMessage(encodedMessage);
      const signatureBase58 = Buffer.from(signature).toString("base64");

      // Verify signature
      const result = await api.verifyAuth(publicKey.toBase58(), signatureBase58, challenge);

      // Store token
      if (typeof window !== "undefined") {
        localStorage.setItem("session_token", result.session_token);
      }

      // Invalidate auth-dependent queries
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      queryClient.invalidateQueries({ queryKey: ["trackedWallets"] });

      return result;
    } finally {
      setIsAuthenticating(false);
    }
  }, [publicKey, signMessage, queryClient]);

  const logoutUser = useCallback(async () => {
    await api.logout();
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    queryClient.invalidateQueries({ queryKey: ["trackedWallets"] });
  }, [queryClient]);

  return {
    isConnected: connected,
    isAuthenticating,
    authenticate,
    logout: logoutUser,
    walletAddress: publicKey?.toBase58(),
  };
}

export function useUser() {
  return useQuery({
    queryKey: ["user"],
    queryFn: api.getMe,
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
