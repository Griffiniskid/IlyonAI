/**
 * API client for AI Sentinel backend
 */

import type {
  AnalysisResponse,
  TrendingResponse,
  PortfolioResponse,
  WhaleActivityResponse,
  TrackedWalletResponse,
  AuthChallengeResponse,
  AuthVerifyResponse,
  UserProfileResponse,
  ErrorResponse,
  AnalysisMode,
  DashboardStatsResponse,
} from "@/types";

export interface BlinkResponse {
  id: string;
  url: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

class APIError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(message: string, code: string, status: number, details?: Record<string, unknown>) {
    super(message);
    this.name = "APIError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  // Add auth token if available
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("session_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const data = await response.json();

  if (!response.ok) {
    const error = data as ErrorResponse;
    throw new APIError(
      error.error || "Request failed",
      error.code || "UNKNOWN_ERROR",
      response.status,
      error.details
    );
  }

  return data as T;
}

// ═══════════════════════════════════════════════════════════════════════════
// ANALYSIS API
// ═══════════════════════════════════════════════════════════════════════════

export async function analyzeToken(
  address: string,
  mode: AnalysisMode = "standard"
): Promise<AnalysisResponse> {
  return fetchAPI<AnalysisResponse>("/api/v1/analyze", {
    method: "POST",
    body: JSON.stringify({ address, mode }),
  });
}

export async function getTokenAnalysis(address: string): Promise<AnalysisResponse> {
  return fetchAPI<AnalysisResponse>(`/api/v1/token/${address}`);
}

export async function refreshAnalysis(
  address: string,
  mode: AnalysisMode = "standard"
): Promise<AnalysisResponse> {
  return fetchAPI<AnalysisResponse>(`/api/v1/token/${address}/refresh?mode=${mode}`, {
    method: "POST",
  });
}

export async function searchTokens(query: string, limit = 10): Promise<{
  results: Array<{ address: string; name: string; symbol: string }>;
  query: string;
  count: number;
}> {
  return fetchAPI(`/api/v1/search?query=${encodeURIComponent(query)}&limit=${limit}`);
}

// ═══════════════════════════════════════════════════════════════════════════
// BLINKS API
// ═══════════════════════════════════════════════════════════════════════════

export async function createBlink(tokenAddress: string): Promise<BlinkResponse> {
  return fetchAPI<BlinkResponse>("/api/v1/blinks/create", {
    method: "POST",
    body: JSON.stringify({ token_address: tokenAddress }),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// TRENDING API
// ═══════════════════════════════════════════════════════════════════════════

export async function getTrendingTokens(
  category: "trending" | "gainers" | "losers" | "new" = "trending",
  limit = 20
): Promise<TrendingResponse> {
  return fetchAPI<TrendingResponse>(`/api/v1/trending?category=${category}&limit=${limit}`);
}

export async function getNewPairs(limit = 20): Promise<TrendingResponse> {
  return fetchAPI<TrendingResponse>(`/api/v1/trending/new?limit=${limit}`);
}

export async function getGainers(limit = 20): Promise<TrendingResponse> {
  return fetchAPI<TrendingResponse>(`/api/v1/trending/gainers?limit=${limit}`);
}

export async function getLosers(limit = 20): Promise<TrendingResponse> {
  return fetchAPI<TrendingResponse>(`/api/v1/trending/losers?limit=${limit}`);
}

// ═══════════════════════════════════════════════════════════════════════════
// PORTFOLIO API
// ═══════════════════════════════════════════════════════════════════════════

export async function getPortfolio(): Promise<PortfolioResponse> {
  return fetchAPI<PortfolioResponse>("/api/v1/portfolio");
}

export async function getWalletPortfolio(wallet: string): Promise<PortfolioResponse> {
  return fetchAPI<PortfolioResponse>(`/api/v1/portfolio/${wallet}`);
}

export async function getTrackedWallets(): Promise<{ wallets: TrackedWalletResponse[] }> {
  return fetchAPI("/api/v1/portfolio/wallets");
}

export async function trackWallet(
  address: string,
  label?: string
): Promise<TrackedWalletResponse> {
  return fetchAPI<TrackedWalletResponse>("/api/v1/portfolio/wallets", {
    method: "POST",
    body: JSON.stringify({ address, label }),
  });
}

export async function untrackWallet(address: string): Promise<void> {
  await fetchAPI(`/api/v1/portfolio/wallets/${address}`, {
    method: "DELETE",
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// WHALE API
// ═══════════════════════════════════════════════════════════════════════════

export async function getWhaleActivity(params?: {
  token?: string;
  minAmountUsd?: number;
  type?: "buy" | "sell";
  limit?: number;
}): Promise<WhaleActivityResponse> {
  const searchParams = new URLSearchParams();
  if (params?.token) searchParams.set("token", params.token);
  if (params?.minAmountUsd) searchParams.set("min_amount_usd", params.minAmountUsd.toString());
  if (params?.type) searchParams.set("type", params.type);
  if (params?.limit) searchParams.set("limit", params.limit.toString());

  const query = searchParams.toString();
  return fetchAPI<WhaleActivityResponse>(`/api/v1/whales${query ? `?${query}` : ""}`);
}

export async function getWhaleActivityForToken(
  tokenAddress: string,
  limit = 50
): Promise<WhaleActivityResponse> {
  return fetchAPI<WhaleActivityResponse>(
    `/api/v1/whales/token/${tokenAddress}?limit=${limit}`
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// AUTH API
// ═══════════════════════════════════════════════════════════════════════════

export async function getAuthChallenge(walletAddress: string): Promise<AuthChallengeResponse> {
  return fetchAPI<AuthChallengeResponse>("/api/v1/auth/challenge", {
    method: "POST",
    body: JSON.stringify({ wallet_address: walletAddress }),
  });
}

export async function verifyAuth(
  walletAddress: string,
  signature: string,
  challenge: string
): Promise<AuthVerifyResponse> {
  return fetchAPI<AuthVerifyResponse>("/api/v1/auth/verify", {
    method: "POST",
    body: JSON.stringify({
      wallet_address: walletAddress,
      signature,
      challenge,
    }),
  });
}

export async function logout(): Promise<void> {
  await fetchAPI("/api/v1/auth/logout", { method: "POST" });
  if (typeof window !== "undefined") {
    localStorage.removeItem("session_token");
  }
}

export async function getMe(): Promise<UserProfileResponse> {
  return fetchAPI<UserProfileResponse>("/api/v1/auth/me");
}

// ═══════════════════════════════════════════════════════════════════════════
// DASHBOARD STATS API
// ═══════════════════════════════════════════════════════════════════════════

export async function getDashboardStats(): Promise<DashboardStatsResponse> {
  return fetchAPI<DashboardStatsResponse>("/api/v1/stats");
}

export { APIError };
