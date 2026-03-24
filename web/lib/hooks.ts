"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useWallet } from "@solana/wallet-adapter-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { RealtimeClient, type StreamStatus } from "./realtime";
import * as api from "./api";
import type { AlertRecordResponse, AnalysisMode, AnalysisResponse, ChainName, SmartMoneyOverviewResponse } from "@/types";

// ═══════════════════════════════════════════════════════════════════════════
// ANALYSIS HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function useAnalyzeToken() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      address,
      mode,
      chain,
    }: {
      address: string;
      mode?: AnalysisMode;
      chain?: ChainName;
    }) => api.analyzeToken(address, mode, chain),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["token", variables.address, variables.chain ?? "auto"], data);
    },
  });
}

export function useTokenAnalysis(address: string | null, chain?: ChainName | null) {
  return useQuery({
    queryKey: ["token", address, chain ?? "auto"],
    queryFn: () => api.getTokenAnalysis(address!, chain ?? undefined),
    enabled: !!address,
    staleTime: 2 * 60 * 1000, // 2 minutes
  });
}

export function useRefreshAnalysis() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      address,
      mode,
      chain,
    }: {
      address: string;
      mode?: AnalysisMode;
      chain?: ChainName;
    }) => api.refreshAnalysis(address, mode, chain),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["token", variables.address, variables.chain ?? "auto"], data);
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

export function useSearchCatalog(query: string, chain?: string | null) {
  return useQuery({
    queryKey: ["search", query, chain ?? "all"],
    queryFn: () => api.searchTokens(query, chain ?? undefined),
    enabled: query.length >= 2,
    staleTime: 60 * 1000,
  });
}

export function useAnalyzePool() {
  return useMutation({
    mutationFn: ({
      poolId,
      includeAi,
      rankingProfile,
      pairAddress,
      chain,
      source,
    }: {
      poolId: string;
      includeAi?: boolean;
      rankingProfile?: string;
      pairAddress?: string;
      chain?: string;
      source?: string;
    }) => api.analyzePool(poolId, { includeAi, rankingProfile, pairAddress, chain, source }),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// TRENDING HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function useTrendingTokens(
  category: "trending" | "gainers" | "losers" | "new" = "trending",
  chain?: ChainName | null,
) {
  // New pairs need faster refresh to show tokens created seconds ago
  const interval = category === "new" ? 10 * 1000 : 30 * 1000;
  return useQuery({
    queryKey: ["trending", category, chain ?? "all"],
    queryFn: () => api.getTrendingTokens(category, 20, false, chain ?? undefined),
    staleTime: interval,
    refetchInterval: interval,
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

export function usePortfolioChainMatrix() {
  return useQuery({
    queryKey: ["portfolio", "chains"],
    queryFn: api.getPortfolioChainMatrix,
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
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["trackedWallets"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio", variables.address] });
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

export function useWhaleActivity(
  params?: {
    token?: string;
    chain?: ChainName;
    minAmountUsd?: number;
    type?: "buy" | "sell";
    limit?: number;
  },
  enabled: boolean = false
) {
  return useQuery({
    queryKey: ["whales", params],
    queryFn: () => api.getWhaleActivity(params),
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes (matches backend cache)
  });
}

export function useSmartMoneyOverview() {
  return useQuery<SmartMoneyOverviewResponse>({
    queryKey: ["smartMoney", "overview"],
    queryFn: api.getSmartMoneyOverview,
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  });
}

export function useWhaleStream() {
  const queryClient = useQueryClient();
  const { data, isLoading, error, isFetching } = useSmartMoneyOverview();
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("disconnected");
  const clientRef = useRef<RealtimeClient | null>(null);

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";
    const client = new RealtimeClient(apiBase);
    clientRef.current = client;

    client
      .subscribe("whale-transactions", (event: unknown) => {
        const tx = event as Record<string, unknown>;
        if (!tx?.signature) return;

        queryClient.setQueryData<SmartMoneyOverviewResponse>(
          ["smartMoney", "overview"],
          (old) => {
            if (!old) return old;
            const newTx =
              tx as unknown as SmartMoneyOverviewResponse["recent_transactions"][number];
            return {
              ...old,
              recent_transactions: [newTx, ...old.recent_transactions].slice(
                0,
                200,
              ),
            };
          },
        );
      })
      .then((mode) => {
        setStreamStatus(mode === "websocket" ? "live" : "polling");
      });

    return () => {
      client.close();
    };
  }, [queryClient]);

  // Sync status from client on interval (for reconnection state changes)
  useEffect(() => {
    const interval = setInterval(() => {
      if (clientRef.current) {
        setStreamStatus(clientRef.current.streamStatus);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return { data, isLoading, isFetching, error, streamStatus };
}

export function useWalletProfile(address: string | null) {
  return useQuery({
    queryKey: ["wallet-profile", address],
    queryFn: () => api.getWalletProfile(address!),
    enabled: !!address,
    staleTime: 60_000,
  });
}

export function useWalletForensics(address: string | null) {
  return useQuery({
    queryKey: ["wallet-forensics", address],
    queryFn: () => api.getWalletForensics(address!),
    enabled: !!address,
    staleTime: 5 * 60_000,
  });
}

export function useAlerts(severity?: string) {
  return useQuery<AlertRecordResponse[]>({
    queryKey: ["alerts", severity ?? "all"],
    queryFn: () => api.getAlerts(severity),
    staleTime: 30 * 1000,
  });
}

export function useAlertRules() {
  return useQuery({
    queryKey: ["alertRules"],
    queryFn: api.getAlertRules,
    staleTime: 60 * 1000,
  });
}

export function useUpdateAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      alertId,
      action,
      snoozed_until,
    }: {
      alertId: string;
      action: "seen" | "acknowledge" | "snooze" | "unsnooze" | "resolve";
      snoozed_until?: string;
    }) => api.updateAlertRecord(alertId, { action, snoozed_until }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useAlertSummary() {
  const { data = [] } = useAlerts();
  const unreadCount = data.filter((alert) => alert.state === "new").length;
  return { unreadCount, alerts: data };
}

// ═══════════════════════════════════════════════════════════════════════════
// DEFI OPPORTUNITY HOOKS
// ═══════════════════════════════════════════════════════════════════════════

export function useCreateOpportunityAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: import("@/types").DefiDiscoverRequest) =>
      api.createOpportunityAnalysis(payload),
    onSuccess: (data) => {
      // pre-populate the query cache for the opportunity if needed
      if (data.opportunityId) {
        queryClient.setQueryData(["opportunity", data.opportunityId, "default", false], {
          id: data.opportunityId,
          // other fields would be loaded in the next poll
        });
      }
    },
  });
}

export function useOpportunityAnalysis(
  opportunityId: string | null,
  options?: { includeAi?: boolean; rankingProfile?: string; pollInterval?: number }
) {
  return useQuery({
    queryKey: ["opportunity", opportunityId, options?.rankingProfile ?? "default", options?.includeAi ?? false],
    queryFn: () => {
      if (!opportunityId) return null;
      return api.getDefiOpportunity(opportunityId, {
        includeAi: options?.includeAi,
        rankingProfile: options?.rankingProfile,
      });
    },
    enabled: !!opportunityId,
    refetchInterval: options?.pollInterval || false,
    retry: options?.pollInterval ? false : 3, // Disable exponential backoff retries while polling
    staleTime: 60 * 1000,
  });
}

export function useDefiOpportunities(params?: {
  query?: string;
  chain?: string;
  minTvl?: number;
  minApy?: number;
  limit?: number;
  includeAi?: boolean;
  rankingProfile?: string;
  pollInterval?: number;
}) {
  const { pollInterval, ...queryParams } = params || {};
  return useQuery({
    queryKey: ["opportunities", queryParams],
    queryFn: () => api.getDefiOpportunities(queryParams),
    refetchInterval: pollInterval || false,
    staleTime: 60 * 1000,
  });
}

export function useDefiAnalyzer(params?: {
  query?: string;
  chain?: string;
  minTvl?: number;
  minApy?: number;
  limit?: number;
  includeAi?: boolean;
  rankingProfile?: string;
  pollInterval?: number;
}) {
  const { pollInterval, ...queryParams } = params || {};
  return useQuery({
    queryKey: ["analyzer", queryParams],
    queryFn: () => api.analyzeDefi(queryParams),
    refetchInterval: pollInterval || false,
    staleTime: 60 * 1000,
  });
}

export function useDefiComparison(params: {
  asset: string;
  chain?: string;
  protocols?: string[];
  mode?: "supply" | "borrow";
  includeAi?: boolean;
  rankingProfile?: string;
}) {
  return useQuery({
    queryKey: ["comparison", params],
    queryFn: () => api.getDefiComparison(params),
    enabled: !!params.asset,
    staleTime: 60 * 1000,
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
