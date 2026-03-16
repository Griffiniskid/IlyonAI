/**
 * TypeScript type definitions for Ilyon AI Web
 * These mirror the Python Pydantic models for type safety
 */

// ═══════════════════════════════════════════════════════════════════════════
// TOKEN ANALYSIS TYPES
// ═══════════════════════════════════════════════════════════════════════════

// Supported chains
export type ChainName =
  | "solana"
  | "ethereum"
  | "base"
  | "arbitrum"
  | "bsc"
  | "polygon"
  | "optimism"
  | "avalanche";

export interface ChainInfo {
  chain: ChainName;
  chain_id: number | null;
  display_name: string;
  native_currency: string;
  explorer_url: string;
  is_evm: boolean;
  block_time_seconds: number;
}

export interface TokenBasicInfo {
  address: string;
  name: string;
  symbol: string;
  decimals: number;
  logo_url: string | null;
  chain: ChainName;
  chain_id: number | null;
  explorer_url: string | null;
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
  liquidity_locked: boolean | null;
  lp_lock_percent: number | null;
  liquidity_lock_status: "locked" | "unlocked" | "unknown";
  liquidity_lock_source?: string | null;
  liquidity_lock_note?: string | null;
  honeypot_status: string;
  honeypot_is_honeypot: boolean;
  honeypot_sell_tax_percent: number | null;
  honeypot_explanation: string;
  honeypot_warnings: string[];
  // Universal EVM + Solana security fields
  can_mint: boolean | null;
  can_blacklist: boolean | null;
  can_pause: boolean | null;
  is_upgradeable: boolean | null;
  is_renounced: boolean | null;
  // EVM-specific
  is_proxy_contract: boolean | null;
  is_verified: boolean | null;
  buy_tax: number | null;
  sell_tax: number | null;
  transfer_pausable: boolean | null;
  is_open_source: boolean | null;
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
  chain: ChainName;
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
  chain: ChainName;
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
  pair_address?: string | null;
  txns_1h?: number;
}

export interface TrendingResponse {
  tokens: TrendingTokenResponse[];
  updated_at: string;
  category: string;
  filter_chain?: ChainName | null;
}

// ═══════════════════════════════════════════════════════════════════════════
// PORTFOLIO TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface PortfolioTokenResponse {
  address: string;
  name: string;
  symbol: string;
  chain?: string;
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
  chain?: ChainName;
}

// ═══════════════════════════════════════════════════════════════════════════
// CONTRACT SCAN TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface VulnerabilityItem {
  name: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  description: string;
  location: string | null;
}

export interface ContractScanResponse {
  address: string;
  chain: ChainName;
  name?: string | null;
  is_verified: boolean;
  compiler_version: string | null;
  license?: string | null;
  is_proxy?: boolean;
  proxy_implementation?: string | null;
  overall_risk: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SAFE";
  risk_score: number;
  vulnerabilities: VulnerabilityItem[];
  ai_verdict: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SAFE" | null;
  ai_audit_summary?: string;
  key_findings: string[];
  recommendations: string[];
  similar_to_scam?: boolean;
  similarity_score?: number;
  scan_duration_ms?: number;
  scanned_at?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// SHIELD / APPROVALS TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface ApprovalItem {
  token_address: string;
  token_symbol?: string | null;
  token_name?: string | null;
  token_logo?: string | null;
  spender_address: string;
  spender_name: string | null;
  spender_is_verified: boolean;
  allowance: string;
  allowance_usd?: number | null;
  chain: ChainName;
  risk_score: number;
  risk_level: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  risk_reasons: string[];
  approved_at?: string | null;
  last_used?: string | null;
}

export interface ShieldScanResponse {
  wallet: string;
  chains_scanned: string[];
  scanned_at?: string;
  summary: {
    total_approvals: number;
    high_risk_count: number;
    medium_risk_count: number;
    low_risk_count: number;
  };
  approvals: ApprovalItem[];
  recommendation: string;
}

export interface RevokePreparationResponse {
  action: string;
  description: string;
  chain: string;
  chain_id: number | null;
  unsigned_transaction: {
    to: string;
    data: string;
    value: string;
    chainId: number | null;
  };
  warning: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// DEFI POOL / YIELD TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface PoolResponse {
  pool: string;
  project: string;
  symbol: string;
  chain: string;
  tvlUsd: number;
  apy: number;
  apyBase: number | null;
  apyReward: number | null;
  ilRisk: string | null;
  risk_score: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  risk_flags: string[];
}

export interface YieldOpportunityResponse extends PoolResponse {
  apy_tier: "stable" | "moderate" | "high" | "extreme";
  exposure_type: "stable-stable" | "crypto-stable" | "crypto-crypto";
  sustainability_ratio: number;
}

export interface DefiProtocolMatch {
  name: string;
  slug: string;
  symbol?: string;
  tvl: number;
  chains: string[];
  category?: string;
  audits?: string | number;
  url?: string;
  logo?: string;
  best_opportunity_score?: number;
  best_safety_score?: number;
}

export interface DefiConfidenceReport {
  score: number;
  label: string;
  coverage_ratio: number;
  source_count: number;
  freshness_hours?: number | null;
  partial_analysis: boolean;
  missing_critical_fields: string[];
  notes: string[];
}

export interface DefiScoreCap {
  dimension: string;
  cap: number;
  reason: string;
}

export interface DefiDependency {
  key: string;
  name: string;
  dependency_type: string;
  risk_score: number;
  confidence_score: number;
  source: string;
  freshness_hours?: number | null;
  notes: string;
}

export interface DefiAssetProfile {
  symbol: string;
  role: string;
  chain: string;
  quality_score: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  confidence_score: number;
  source: string;
  address?: string | null;
  thesis: string;
  token_analysis?: Record<string, unknown> | null;
}

export interface DefiDeployment {
  chain: string;
  display_name: string;
  tvl_usd?: number | null;
  share_pct?: number | null;
  deployment_key: string;
}

export interface OpportunityDimension {
  key: string;
  label: string;
  score: number;
  weight: number;
  summary: string;
}

export interface DefiEvidenceItem {
  key: string;
  title: string;
  summary: string;
  type: string;
  severity: "low" | "medium" | "high";
  source: string;
  url?: string | null;
}

export interface DefiScenarioItem {
  key: string;
  title: string;
  impact: string;
  severity: "low" | "medium" | "high";
  trigger: string;
}

export interface DefiOpportunitySummary {
  overall_score?: number;
  quality_score?: number;
  opportunity_score: number;
  safety_score: number;
  risk_burden_score?: number;
  yield_durability_score?: number;
  yield_quality_score: number;
  exit_liquidity_score?: number;
  exit_quality_score: number;
  apr_efficiency_score?: number;
  effective_apr?: number;
  required_apr?: number;
  return_potential_score?: number;
  confidence_score: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  strategy_fit: "conservative" | "balanced" | "aggressive";
  headline: string;
  thesis: string;
}

export interface DefiMarketBrief {
  available: boolean;
  headline: string;
  summary: string;
  market_regime: string;
  best_area: string;
  avoid_zone: string;
  monitor_triggers: string[];
}

export interface DefiProtocolAIAnalysis {
  available: boolean;
  headline: string;
  summary: string;
  best_for: string;
  main_risks: string[];
  monitor_triggers: string[];
  safer_alternative: string;
}

export interface DefiOpportunityAIAnalysis {
  available: boolean;
  headline: string;
  summary: string;
  best_for: string;
  why_it_exists: string;
  main_risks: string[];
  monitor_triggers: string[];
  safer_alternative: string;
}

export interface DefiOpportunityHistory {
  available: boolean;
  points?: Array<Record<string, unknown>>;
  apy_change_pct?: number;
  tvl_change_pct?: number;
}

export interface DefiOpportunityResponse {
  id: string;
  kind: "pool" | "yield" | "lending";
  product_type?: string | null;
  score_family?: string | null;
  title: string;
  subtitle: string;
  protocol: string;
  protocol_name: string;
  protocol_slug: string;
  project: string;
  symbol: string;
  chain: string;
  apy: number;
  tvl_usd: number;
  tags: string[];
  summary: DefiOpportunitySummary;
  dimensions: OpportunityDimension[];
  confidence?: DefiConfidenceReport | null;
  score_caps?: DefiScoreCap[];
  evidence: DefiEvidenceItem[];
  scenarios: DefiScenarioItem[];
  dependencies?: DefiDependency[];
  assets?: DefiAssetProfile[];
  deployment?: Record<string, unknown>;
  ranking_profile?: string | null;
  raw: Record<string, unknown>;
  history?: DefiOpportunityHistory | null;
  protocol_profile?: DefiProtocolProfile | null;
  related_opportunities?: DefiOpportunityResponse[];
  rate_comparison?: {
    asset: string;
    markets_found: number;
    best_supply: LendingMarketResponse[];
    lowest_borrow: LendingMarketResponse[];
      all_markets: LendingMarketResponse[];
   } | null;
  safer_alternative?: DefiOpportunityResponse | null;
  ai_analysis?: DefiOpportunityAIAnalysis | null;
}

export interface DefiProtocolSummary {
  tvl_usd: number;
  safety_score: number;
  opportunity_score: number;
  confidence_score: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  incident_count: number;
  audit_count: number;
  deployment_count: number;
}

export interface DefiProtocolProfile {
  protocol: string;
  display_name: string;
  slug: string;
  category?: string | null;
  url?: string | null;
  logo?: string | null;
  chains: string[];
  ranking_profile?: string | null;
  summary: DefiProtocolSummary;
  dimensions: OpportunityDimension[];
  confidence?: DefiConfidenceReport | null;
  chain_breakdown: Array<{
    chain: string;
    tvl_usd: number | null;
    share_pct?: number | null;
  }>;
  deployments?: DefiDeployment[];
  top_markets: LendingMarketResponse[];
  top_pools: PoolResponse[];
  top_opportunities: DefiOpportunityResponse[];
  audits: AuditRecord[];
  incidents: RektIncident[];
  evidence: DefiEvidenceItem[];
  scenarios: DefiScenarioItem[];
  dependencies?: DefiDependency[];
  assets?: DefiAssetProfile[];
  docs_profile?: Record<string, unknown>;
  governance?: Record<string, unknown>;
  methodology: Record<string, string>;
  ai_analysis?: DefiProtocolAIAnalysis | null;
}

export interface DefiOpportunitiesResponse {
  opportunities: DefiOpportunityResponse[];
  count: number;
  summary: {
    total_pool_tvl: number;
    avg_pool_apy: number;
    avg_yield_apy: number;
    high_risk_pool_count: number;
    high_risk_yield_count: number;
    stressed_lending_market_count: number;
    avg_opportunity_score: number;
    avg_safety_score: number;
    avg_confidence_score: number;
  };
  highlights: {
    best_conservative?: DefiOpportunityResponse | null;
    best_balanced?: DefiOpportunityResponse | null;
    best_aggressive?: DefiOpportunityResponse | null;
  };
  methodology: Record<string, string>;
  filters: {
    chain?: string | null;
    query?: string | null;
    min_tvl: number;
    min_apy: number;
    ranking_profile?: string | null;
  };
  ai_market_brief?: DefiMarketBrief | null;
  data_source: string;
}

export interface DefiAnalyzerResponse {
  query?: string | null;
  chain?: string | null;
  ranking_profile?: string | null;
  public_ranking_default?: string;
  count: {
    pools: number;
    yields: number;
    lending_markets: number;
    protocols: number;
    opportunities?: number;
  };
  summary: {
    total_pool_tvl: number;
    avg_pool_apy: number;
    avg_yield_apy: number;
    high_risk_pool_count: number;
    high_risk_yield_count: number;
    stressed_lending_market_count: number;
    avg_opportunity_score?: number;
    avg_safety_score?: number;
    avg_confidence_score?: number;
  };
  highlights: {
    safest_pool?: PoolResponse | null;
    best_sustainable_yield?: YieldOpportunityResponse | null;
    lowest_risk_lending_market?: LendingMarketResponse | null;
    largest_protocol?: DefiProtocolMatch | null;
    best_conservative?: DefiOpportunityResponse | null;
    best_balanced?: DefiOpportunityResponse | null;
    best_aggressive?: DefiOpportunityResponse | null;
  };
  top_pools: PoolResponse[];
  top_yields: YieldOpportunityResponse[];
  top_lending_markets: LendingMarketResponse[];
  top_opportunities: DefiOpportunityResponse[];
  protocol_spotlights: DefiProtocolMatch[];
  matching_protocols: DefiProtocolMatch[];
  methodology?: Record<string, string>;
  ai_market_brief?: DefiMarketBrief | null;
  data_source: string;
}

export interface DefiCompareRow {
  opportunity_id: string;
  protocol: string;
  chain: string;
  asset: string;
  apy: number;
  opportunity_score: number;
  safety_score: number;
  yield_quality_score: number;
  exit_quality_score: number;
  confidence_score: number;
  headline: string;
}

export interface DefiCompareResponse {
  asset: string;
  chain?: string | null;
  mode: string;
  ranking_profile: string;
  summary: {
    markets_compared: number;
    best_balanced?: DefiOpportunityResponse | null;
    safest?: DefiOpportunityResponse | null;
    best_yield?: DefiOpportunityResponse | null;
    avoid?: DefiOpportunityResponse | null;
  };
  matrix: DefiCompareRow[];
  opportunities: DefiOpportunityResponse[];
  methodology: Record<string, string>;
  ai_market_brief?: DefiMarketBrief | null;
}

export interface DefiSimulationScenario {
  name: string;
  summary: string;
  metric: string;
  value: number;
  unit: string;
  severity: "low" | "medium" | "high";
}

export interface DefiSimulationResponse {
  kind: string;
  summary: string;
  base_case: Record<string, unknown>;
  scenarios: DefiSimulationScenario[];
  recommendations: string[];
}

export interface DefiPositionAnalysisResponse extends DefiSimulationResponse {
  position_size_usd: number;
  monitor_triggers: string[];
}

export interface LendingRiskBreakdown {
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  risk_score: number;
  risk_factors: string[];
}

export interface LendingMarketResponse {
  pool_id: string;
  protocol: string;
  protocol_display: string;
  symbol: string;
  chain: string;
  tvlUsd: number;
  apy_supply: number;
  apy_borrow: number;
  utilization_pct: number;
  audit_status: string;
  auditors: string[];
  incident_note?: string | null;
  market_risk: LendingRiskBreakdown;
  protocol_risk?: LendingRiskBreakdown;
  combined_risk_score: number;
}

export interface LendingMarketsResponse {
  markets: LendingMarketResponse[];
  count: number;
  filters: {
    protocol?: string | null;
    chain?: string | null;
    asset?: string | null;
  };
  data_source: string;
}

export interface HealthFactorResponse {
  health_factor: number;
  status: "SAFE" | "MODERATE" | "WARNING" | "DANGER";
  message: string;
  collateral_drop_to_liquidation_pct?: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// INTEL / REKT TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface RektIncident {
  id: string;
  name: string;
  date: string;
  amount_usd: number;
  protocol: string;
  chains: string[];
  attack_type: string;
  description: string;
  post_mortem_url: string;
  funds_recovered: boolean;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
}

export interface AuditRecord {
  id: string;
  protocol: string;
  auditor: string;
  date: string;
  report_url: string;
  severity_findings: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    informational: number;
  };
  verdict: "PASS" | "FAIL";
  chains: string[];
}

export interface IntelStatsResponse {
  rekt: {
    total_incidents: number;
    total_stolen_usd: number;
    total_recovered_usd: number;
    recovery_rate: number;
    top_attack_types: Array<{ type: string; count: number }>;
    chains_most_hit: Array<{ chain: string; count: number }>;
  };
  audits: {
    total_audits: number;
    pass_count: number;
    fail_count: number;
  };
}

export interface SearchResultResponse {
  type: "token" | "pool" | "protocol" | string;
  product_type?: string | null;
  title: string;
  subtitle: string;
  address?: string | null;
  chain?: string | null;
  score?: number | null;
  url?: string | null;
  logo?: string | null;
}

export interface SearchResponse {
  query: string;
  input_type: string;
  results: SearchResultResponse[];
  count: number;
  total: number;
}

export type PoolAnalysisResponse = DefiOpportunityResponse;

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
