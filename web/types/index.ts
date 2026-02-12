/**
 * TypeScript type definitions for Ilyon AI Web
 * These mirror the Python Pydantic models for type safety
 */

// ═══════════════════════════════════════════════════════════════════════════
// TOKEN ANALYSIS TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface TokenBasicInfo {
  address: string;
  name: string;
  symbol: string;
  decimals: number;
  logo_url: string | null;
}

export interface ScoresResponse {
  overall: number;
  grade: string;
  safety: number;
  liquidity: number;
  distribution: number;
  social: number;
  activity: number;
  honeypot: number;
  deployer: number;
  anomaly: number;
}

export interface MarketDataResponse {
  price_usd: number;
  market_cap: number;
  fdv: number;
  liquidity_usd: number;
  volume_24h: number;
  volume_1h: number;
  price_change_24h: number;
  price_change_6h: number;
  price_change_1h: number;
  price_change_5m: number;
  buys_24h: number;
  sells_24h: number;
  txns_24h: number;
  age_hours: number;
  dex_name: string;
  pair_address: string | null;
}

export interface SecurityResponse {
  mint_authority_enabled: boolean;
  freeze_authority_enabled: boolean;
  liquidity_locked: boolean;
  lp_lock_percent: number;
  honeypot_status: string;
  honeypot_is_honeypot: boolean;
  honeypot_sell_tax_percent: number | null;
  honeypot_explanation: string;
  honeypot_warnings: string[];
}

export interface HolderAnalysisResponse {
  top_holder_pct: number;
  holder_concentration: number;
  suspicious_wallets: number;
  dev_wallet_risk: boolean;
  holder_flags: string[];
  top_holders: Array<{
    address: string;
    balance: number;
    percentage: number;
  }>;
}

export interface AIAnalysisResponse {
  available: boolean;
  verdict: "SAFE" | "CAUTION" | "RISKY" | "DANGEROUS" | "SCAM";
  score: number;
  confidence: number;
  rug_probability: number;
  summary: string;
  recommendation: string;
  red_flags: string[];
  green_flags: string[];
  code_audit: string;
  whale_risk: string;
  sentiment: string;
  trading: string;
  narrative: string;
  grok?: {
    narrative_score: number;
    sentiment: string;
    narrative_category: string;
    trending_status: string;
    narrative_summary: string;
    influencer_activity: string;
    influencer_tier?: string;
    community_vibe?: string;
    organic_score: number;
    key_themes?: string[];
    fud_warnings?: string[];
  };
}

export interface SocialsResponse {
  has_twitter: boolean;
  has_website: boolean;
  has_telegram: boolean;
  twitter_url: string | null;
  website_url: string | null;
  telegram_url: string | null;
  socials_count: number;
}

export interface WebsiteAnalysisResponse {
  quality: number;
  is_legitimate: boolean;
  has_privacy_policy: boolean;
  has_terms: boolean;
  has_copyright: boolean;
  has_contact: boolean;
  has_tokenomics: boolean;
  has_roadmap: boolean;
  has_team: boolean;
  has_whitepaper: boolean;
  has_audit: boolean;
  audit_provider: string | null;
  red_flags: string[];
  ai_quality: string;
  ai_concerns: string[];
}

export interface DeployerForensicsResponse {
  available: boolean;
  address: string | null;
  reputation_score: number;
  risk_level: string;
  tokens_deployed: number;
  rugged_tokens: number;
  rug_percentage: number;
  is_known_scammer: boolean;
  patterns_detected: string[];
  evidence_summary: string;
}

export interface AnomalyDetectionResponse {
  available: boolean;
  score: number;
  rug_probability: number;
  time_to_rug: string | null;
  severity: string;
  anomalies_detected: string[];
  recommendation: string;
  confidence: number;
}

export interface AnalysisResponse {
  token: TokenBasicInfo;
  scores: ScoresResponse;
  market: MarketDataResponse;
  security: SecurityResponse;
  holders: HolderAnalysisResponse;
  ai: AIAnalysisResponse;
  socials: SocialsResponse;
  website: WebsiteAnalysisResponse;
  deployer: DeployerForensicsResponse;
  anomaly: AnomalyDetectionResponse;
  recommendation: string;
  analyzed_at: string;
  analysis_mode: string;
  cached: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════
// TRENDING TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface TrendingTokenResponse {
  address: string;
  name: string;
  symbol: string;
  logo_url: string | null;
  price_usd: number;
  price_change_24h: number;
  price_change_1h: number;
  volume_24h: number;
  liquidity_usd: number;
  market_cap: number;
  age_hours: number;
  dex_name: string;
  txns_1h?: number;
}

export interface TrendingResponse {
  tokens: TrendingTokenResponse[];
  updated_at: string;
  category: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// PORTFOLIO TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface PortfolioTokenResponse {
  address: string;
  name: string;
  symbol: string;
  logo_url: string | null;
  balance: number;
  balance_usd: number;
  price_usd: number;
  price_change_24h: number;
  safety_score: number | null;
  risk_level: string;
}

export interface PortfolioResponse {
  wallet_address: string;
  total_value_usd: number;
  total_pnl_usd: number;
  total_pnl_percent: number;
  tokens: PortfolioTokenResponse[];
  health_score: number;
  last_updated: string;
}

export interface TrackedWalletResponse {
  address: string;
  label: string | null;
  added_at: string;
  last_synced: string | null;
  token_count: number;
  total_value_usd: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// WHALE TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface WhaleTransactionResponse {
  signature: string;
  wallet_address: string;
  wallet_label: string | null;
  token_address: string;
  token_symbol: string;
  token_name: string;
  type: "buy" | "sell";
  amount_tokens: number;
  amount_usd: number;
  price_usd: number;
  timestamp: string;
  dex_name: string;
}

export interface WhaleActivityResponse {
  transactions: WhaleTransactionResponse[];
  updated_at: string;
  filter_token: string | null;
  min_amount_usd: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// AUTH TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface AuthChallengeResponse {
  challenge: string;
  expires_at: string;
  message: string;
}

export interface AuthVerifyResponse {
  success: boolean;
  wallet_address: string;
  session_token: string;
  expires_at: string;
}

export interface UserProfileResponse {
  wallet_address: string;
  created_at: string;
  analyses_count: number;
  tracked_wallets: number;
  alerts_count: number;
  premium_until: string | null;
}

// ═══════════════════════════════════════════════════════════════════════════
// ERROR TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface ErrorResponse {
  error: string;
  code: string;
  details?: Record<string, unknown>;
}

// ═══════════════════════════════════════════════════════════════════════════
// UTILITY TYPES
// ═══════════════════════════════════════════════════════════════════════════

export type VerdictType = "SAFE" | "CAUTION" | "RISKY" | "DANGEROUS" | "SCAM";

export type GradeType = "A+" | "A" | "B" | "C" | "D" | "F";

export type AnalysisMode = "quick" | "standard" | "deep";

export interface AnalyzeRequest {
  address: string;
  mode: AnalysisMode;
}

// ═══════════════════════════════════════════════════════════════════════════
// DASHBOARD STATS TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface VolumeDataPoint {
  time: string;
  volume: number;
}

export interface RiskDistributionItem {
  name: string;
  count: number;
  color: string;
}

export interface MarketDistributionItem {
  name: string;
  value: number;
  color: string;
}

export interface TopTokenVolume {
  symbol: string;
  volume: number;
  address: string;
}

export interface DashboardStatsResponse {
  total_volume_24h: number;
  volume_change_24h: number;
  solana_tvl: number;
  sol_price: number;
  sol_price_change_24h: number;
  active_tokens: number;
  active_tokens_change: number;
  safe_tokens_percent: number;
  safe_tokens_change: number;
  scams_detected: number;
  scams_change: number;
  high_risk_tokens: number;
  volume_chart: VolumeDataPoint[];
  risk_distribution: RiskDistributionItem[];
  market_distribution: MarketDistributionItem[];
  top_tokens_by_volume: TopTokenVolume[];
  tokens_analyzed_today: number;
  total_tokens_analyzed: number;
  avg_liquidity: number;
  total_liquidity: number;
  updated_at: string;
}
