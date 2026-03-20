/**
 * API client for AI Sentinel backend
 */

import type {
  AnalysisResponse,
  TrendingResponse,
  PortfolioResponse,
  PortfolioChainMatrixResponse,
  WhaleActivityResponse,
  TrackedWalletResponse,
  AuthChallengeResponse,
  AuthVerifyResponse,
  UserProfileResponse,
  ErrorResponse,
  AnalysisMode,
  DashboardStatsResponse,
  ChainName,
  ChainInfo,
  ContractScanResponse,
  ShieldScanResponse,
  RevokePreparationResponse,
  PoolResponse,
  YieldOpportunityResponse,
  RektIncident,
  RektListResponse,
  AuditRecord,
  IntelStatsResponse,
  VulnerabilityItem,
  ApprovalItem,
  LendingMarketResponse,
  LendingMarketsResponse,
  HealthFactorResponse,
  DefiAnalyzerResponse,
  DefiProtocolMatch,
  DefiOpportunityResponse,
  DefiOpportunitiesResponse,
  DefiProtocolProfile,
  DefiCompareResponse,
  DefiPositionAnalysisResponse,
  DefiSimulationResponse,
  PoolAnalysisResponse,
  SearchResponse,
  SmartMoneyOverviewResponse,
  AlertRecordResponse,
  AlertRuleResponse,
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

function normalizeChainName(value: unknown): ChainName | undefined {
  if (typeof value !== "string") return undefined;

  const normalized = value.trim().toLowerCase();
  const mapping: Record<string, ChainName> = {
    solana: "solana",
    sol: "solana",
    ethereum: "ethereum",
    eth: "ethereum",
    base: "base",
    arbitrum: "arbitrum",
    arb: "arbitrum",
    bsc: "bsc",
    bnb: "bsc",
    "bnb chain": "bsc",
    "bnb smart chain": "bsc",
    polygon: "polygon",
    matic: "polygon",
    optimism: "optimism",
    op: "optimism",
    avalanche: "avalanche",
    avax: "avalanche",
  };

  return mapping[normalized];
}

function normalizeText(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);

  if (Array.isArray(value)) {
    return value.map((item) => normalizeText(item)).filter(Boolean).join(", ");
  }

  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const primary = normalizeText(
      record.title
      ?? record.headline
      ?? record.summary
      ?? record.label
      ?? record.name
      ?? record.message
      ?? record.reason
      ?? record.key,
      ""
    );
    const qualifier = normalizeText(record.risk_level ?? record.severity ?? record.level, "");

    if (primary && qualifier) return `${primary} (${qualifier})`;
    if (primary) return primary;

    try {
      return JSON.stringify(value);
    } catch {
      return fallback;
    }
  }

  return fallback;
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => normalizeText(item)).filter(Boolean);
}

function normalizeStringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};

  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, normalizeText(item)])
  );
}

function normalizeRiskLevel(value: unknown): "HIGH" | "MEDIUM" | "LOW" {
  const normalized = normalizeText(value, "LOW").toUpperCase();
  if (normalized === "HIGH" || normalized === "MEDIUM" || normalized === "LOW") return normalized;
  return "LOW";
}

function normalizeStrategyFit(value: unknown): "conservative" | "balanced" | "aggressive" {
  const normalized = normalizeText(value, "balanced").toLowerCase();
  if (normalized === "conservative" || normalized === "balanced" || normalized === "aggressive") return normalized;
  return "balanced";
}

function normalizeApyTier(value: unknown): "stable" | "moderate" | "high" | "extreme" {
  const normalized = normalizeText(value, "stable").toLowerCase();
  if (normalized === "stable" || normalized === "moderate" || normalized === "high" || normalized === "extreme") return normalized;
  return "stable";
}

function normalizeExposureType(value: unknown): "stable-stable" | "crypto-stable" | "crypto-crypto" {
  const normalized = normalizeText(value, "crypto-crypto").toLowerCase();
  if (normalized === "stable-stable" || normalized === "crypto-stable" || normalized === "crypto-crypto") return normalized;
  return "crypto-crypto";
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number") return null;
  if (!Number.isFinite(value)) return null;
  return value;
}

export function normalizeConfidencePercent(value: unknown): number {
  const numeric = toFiniteNumber(value);
  if (numeric == null) return 0;

  const normalized = numeric >= -1 && numeric <= 1
    ? numeric * 100
    : numeric;

  return Math.round(Math.min(100, Math.max(0, normalized)));
}

export function deriveSmartMoneyEntityConfidencePercent(
  overview: Pick<SmartMoneyOverviewResponse, "net_flow_usd" | "inflow_usd" | "outflow_usd"> | null | undefined
): number {
  if (!overview) return 0;

  const inflow = Math.max(0, toFiniteNumber(overview.inflow_usd) ?? 0);
  const outflow = Math.max(0, toFiniteNumber(overview.outflow_usd) ?? 0);
  const netFlow = Math.abs(toFiniteNumber(overview.net_flow_usd) ?? 0);
  const totalFlow = inflow + outflow;

  if (totalFlow <= 0) return 0;
  return normalizeConfidencePercent(netFlow / totalFlow);
}

function normalizeChainInfo(raw: any): ChainInfo {
  return {
    chain: normalizeChainName(raw.chain ?? raw.value ?? raw.name) ?? "solana",
    chain_id: raw.chain_id ?? null,
    display_name: raw.display_name ?? raw.name ?? raw.chain ?? "Unknown",
    native_currency: raw.native_currency ?? raw.native_token ?? "",
    explorer_url: raw.explorer_url ?? "",
    is_evm: Boolean(raw.is_evm),
    block_time_seconds: Number(raw.block_time_seconds ?? 0),
  };
}

function normalizeContractVulnerability(raw: any): VulnerabilityItem {
  const lineNumber = typeof raw.line_number === "number" ? raw.line_number : null;
  return {
    name: raw.name ?? raw.title ?? "Finding",
    severity: (String(raw.severity ?? "INFO").toUpperCase() as VulnerabilityItem["severity"]),
    description: raw.description ?? "",
    location: raw.location ?? (lineNumber ? `Line ${lineNumber}` : null),
  };
}

function normalizeContractScan(raw: any): ContractScanResponse {
  const vulnerabilities = Array.isArray(raw.vulnerabilities)
    ? raw.vulnerabilities.map(normalizeContractVulnerability)
    : [];

  const aiVerdictRaw = String(raw.ai_verdict ?? raw.ai_risk_verdict ?? "").toUpperCase();
  const aiVerdict = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "SAFE"].includes(aiVerdictRaw)
    ? (aiVerdictRaw as ContractScanResponse["ai_verdict"])
    : null;
  const keyFindings = Array.isArray(raw.key_findings)
    ? raw.key_findings
    : raw.ai_audit_summary
      ? [raw.ai_audit_summary]
      : [];
  const overallRiskRaw = String(raw.overall_risk ?? aiVerdict ?? "SAFE").toUpperCase();
  const overallRisk = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "SAFE"].includes(overallRiskRaw)
    ? (overallRiskRaw as ContractScanResponse["overall_risk"])
    : "SAFE";

  return {
    address: raw.address,
    chain: normalizeChainName(raw.chain) ?? "ethereum",
    name: raw.name ?? null,
    is_verified: Boolean(raw.is_verified),
    compiler_version: raw.compiler_version ?? null,
    license: raw.license ?? null,
    is_proxy: Boolean(raw.is_proxy),
    proxy_implementation: raw.proxy_implementation ?? null,
    overall_risk: overallRisk,
    risk_score: Number(raw.risk_score ?? 0),
    vulnerabilities,
    ai_verdict: aiVerdict,
    ai_audit_summary: raw.ai_audit_summary ?? "",
    key_findings: keyFindings,
    recommendations: Array.isArray(raw.recommendations) ? raw.recommendations : [],
    similar_to_scam: Boolean(raw.similar_to_scam),
    similarity_score: Number(raw.similarity_score ?? 0),
    scan_duration_ms: Number(raw.scan_duration_ms ?? 0),
    scanned_at: raw.scanned_at ?? new Date().toISOString(),
  };
}

function normalizeApproval(raw: any): ApprovalItem {
  const riskLevelRaw = String(raw.risk_level ?? "LOW").toUpperCase();
  const riskLevel = ["CRITICAL", "HIGH", "MEDIUM", "LOW"].includes(riskLevelRaw)
    ? (riskLevelRaw as ApprovalItem["risk_level"])
    : "LOW";

  return {
    token_address: raw.token_address,
    token_symbol: raw.token_symbol ?? null,
    token_name: raw.token_name ?? null,
    token_logo: raw.token_logo ?? null,
    spender_address: raw.spender_address,
    spender_name: raw.spender_name ?? null,
    spender_is_verified: Boolean(raw.spender_is_verified),
    allowance: String(raw.allowance ?? "0"),
    allowance_usd: raw.allowance_usd != null ? Number(raw.allowance_usd) : null,
    chain: normalizeChainName(raw.chain) ?? "ethereum",
    risk_score: Number(raw.risk_score ?? 0),
    risk_level: riskLevel,
    risk_reasons: Array.isArray(raw.risk_reasons) ? raw.risk_reasons : [],
    approved_at: raw.approved_at ?? null,
    last_used: raw.last_used ?? null,
  };
}

function normalizeShieldScan(raw: any): ShieldScanResponse {
  const approvals = Array.isArray(raw.approvals) ? raw.approvals.map(normalizeApproval) : [];
  const summary = raw.summary ?? {
    total_approvals: raw.total_approvals ?? approvals.length,
    high_risk_count: raw.high_risk_count ?? approvals.filter((approval: ApprovalItem) => approval.risk_level === "HIGH").length,
    medium_risk_count: raw.medium_risk_count ?? approvals.filter((approval: ApprovalItem) => approval.risk_level === "MEDIUM").length,
    low_risk_count: raw.low_risk_count ?? approvals.filter((approval: ApprovalItem) => approval.risk_level === "LOW").length,
  };

  const chains = Array.isArray(raw.chains_scanned)
    ? raw.chains_scanned
    : raw.chain
      ? [raw.chain]
      : [];

  return {
    wallet: raw.wallet ?? raw.wallet_address ?? "",
    chains_scanned: chains
      .map((chain: unknown) => normalizeChainName(chain))
      .filter((chain: ChainName | undefined): chain is ChainName => Boolean(chain)),
    scanned_at: raw.scanned_at ?? undefined,
    summary,
    approvals,
    recommendation: raw.recommendation ?? "",
  };
}

function normalizeTrendingToken(raw: any): TrendingResponse["tokens"][number] {
  return {
    address: raw.address ?? "",
    chain: normalizeChainName(raw.chain) ?? "solana",
    name: raw.name ?? "Unknown",
    symbol: raw.symbol ?? "???",
    logo_url: raw.logo_url ?? null,
    price_usd: Number(raw.price_usd ?? 0),
    price_change_24h: Number(raw.price_change_24h ?? 0),
    price_change_1h: Number(raw.price_change_1h ?? 0),
    volume_24h: Number(raw.volume_24h ?? 0),
    liquidity_usd: Number(raw.liquidity_usd ?? 0),
    market_cap: Number(raw.market_cap ?? 0),
    age_hours: Number(raw.age_hours ?? 0),
    dex_name: raw.dex_name ?? "Unknown",
    pair_address: raw.pair_address ?? null,
    txns_1h: raw.txns_1h != null ? Number(raw.txns_1h) : undefined,
  };
}

function normalizeTrendingResponse(raw: any): TrendingResponse {
  return {
    tokens: Array.isArray(raw.tokens) ? raw.tokens.map(normalizeTrendingToken) : [],
    updated_at: raw.updated_at ?? new Date().toISOString(),
    category: raw.category ?? "trending",
    filter_chain: normalizeChainName(raw.filter_chain) ?? null,
  };
}

function normalizePool(raw: any): PoolResponse {
  return {
    pool: normalizeText(raw.pool ?? raw.pool_id, ""),
    project: normalizeText(raw.project),
    symbol: normalizeText(raw.symbol),
    chain: normalizeText(raw.chain),
    tvlUsd: Number(raw.tvlUsd ?? raw.tvl_usd ?? 0),
    apy: Number(raw.apy ?? 0),
    apyBase: raw.apyBase ?? raw.apy_base ?? null,
    apyReward: raw.apyReward ?? raw.apy_reward ?? null,
    ilRisk: raw.ilRisk != null || raw.il_risk != null ? normalizeText(raw.ilRisk ?? raw.il_risk) : null,
    risk_score: Number(raw.risk_score ?? 0),
    risk_level: normalizeRiskLevel(raw.risk_level),
    risk_flags: normalizeStringArray(raw.risk_flags),
  };
}

function normalizeYield(raw: any): YieldOpportunityResponse {
  return {
    ...normalizePool(raw),
    apy_tier: normalizeApyTier(raw.apy_tier),
    exposure_type: normalizeExposureType(raw.exposure_type),
    sustainability_ratio: Number(raw.sustainability_ratio ?? 0),
  };
}

function normalizeProtocolMatch(raw: any): DefiProtocolMatch {
  return {
    name: normalizeText(raw.name ?? raw.protocol, "Unknown"),
    slug: normalizeText(raw.slug, ""),
    symbol: raw.symbol != null ? normalizeText(raw.symbol) : undefined,
    tvl: Number(raw.tvl ?? 0),
    chains: normalizeStringArray(raw.chains),
    category: raw.category != null ? normalizeText(raw.category) : undefined,
    audits: raw.audits != null ? normalizeText(raw.audits) : undefined,
    url: raw.url != null ? normalizeText(raw.url) : undefined,
    logo: raw.logo != null ? normalizeText(raw.logo) : undefined,
    best_opportunity_score: raw.best_opportunity_score != null ? Number(raw.best_opportunity_score) : undefined,
    best_safety_score: raw.best_safety_score != null ? Number(raw.best_safety_score) : undefined,
  };
}

function normalizeLendingMarket(raw: any): LendingMarketResponse {
  return {
    pool_id: normalizeText(raw.pool_id ?? raw.pool, ""),
    protocol: normalizeText(raw.protocol, ""),
    protocol_display: normalizeText(raw.protocol_display ?? raw.protocol, "Unknown"),
    symbol: normalizeText(raw.symbol, ""),
    chain: normalizeText(raw.chain, ""),
    tvlUsd: Number(raw.tvlUsd ?? raw.tvl_usd ?? 0),
    apy_supply: Number(raw.apy_supply ?? 0),
    apy_borrow: Number(raw.apy_borrow ?? 0),
    utilization_pct: Number(raw.utilization_pct ?? 0),
    audit_status: normalizeText(raw.audit_status, "unknown"),
    auditors: normalizeStringArray(raw.auditors),
    incident_note: raw.incident_note != null ? normalizeText(raw.incident_note) : null,
    market_risk: {
      risk_level: normalizeRiskLevel(raw.market_risk?.risk_level),
      risk_score: Number(raw.market_risk?.risk_score ?? 0),
      risk_factors: normalizeStringArray(raw.market_risk?.risk_factors),
    },
    protocol_risk: raw.protocol_risk
      ? {
          risk_level: normalizeRiskLevel(raw.protocol_risk?.risk_level),
          risk_score: Number(raw.protocol_risk?.risk_score ?? 0),
          risk_factors: normalizeStringArray(raw.protocol_risk?.risk_factors),
        }
      : undefined,
    combined_risk_score: Number(raw.combined_risk_score ?? 0),
  };
}

function normalizeDefiMarketBrief(raw: any) {
  if (!raw) return null;
  return {
    available: Boolean(raw.available),
    headline: normalizeText(raw.headline, "Market brief"),
    summary: normalizeText(raw.summary),
    market_regime: normalizeText(raw.market_regime, "mixed"),
    best_area: normalizeText(raw.best_area),
    avoid_zone: normalizeText(raw.avoid_zone),
    monitor_triggers: normalizeStringArray(raw.monitor_triggers),
  };
}

function normalizeOpportunityDimension(raw: any) {
  return {
    key: normalizeText(raw.key, "dimension"),
    label: normalizeText(raw.label ?? raw.key, "Dimension"),
    score: Number(raw.score ?? 0),
    weight: Number(raw.weight ?? 0),
    summary: normalizeText(raw.summary),
  };
}

function normalizeDefiEvidence(raw: any) {
  return {
    key: normalizeText(raw.key, "evidence"),
    title: normalizeText(raw.title, "Evidence"),
    summary: normalizeText(raw.summary),
    type: normalizeText(raw.type, "metric"),
    severity: normalizeText(raw.severity, "low"),
    source: normalizeText(raw.source, "internal"),
    url: raw.url != null ? normalizeText(raw.url) : null,
  };
}

function normalizeDefiScenario(raw: any) {
  return {
    key: normalizeText(raw.key, "scenario"),
    title: normalizeText(raw.title, "Scenario"),
    impact: normalizeText(raw.impact),
    severity: normalizeText(raw.severity, "medium"),
    trigger: normalizeText(raw.trigger),
  };
}

function normalizeDefiConfidence(raw: any) {
  if (!raw) return null;
  return {
    score: Number(raw.score ?? 0),
    label: normalizeText(raw.label, "LOW"),
    coverage_ratio: Number(raw.coverage_ratio ?? 0),
    source_count: Number(raw.source_count ?? 0),
    freshness_hours: raw.freshness_hours != null ? Number(raw.freshness_hours) : null,
    partial_analysis: Boolean(raw.partial_analysis),
    missing_critical_fields: normalizeStringArray(raw.missing_critical_fields),
    notes: normalizeStringArray(raw.notes),
  };
}

function normalizeDefiScoreCap(raw: any) {
  return {
    dimension: normalizeText(raw.dimension, "score"),
    cap: Number(raw.cap ?? 0),
    reason: normalizeText(raw.reason),
  };
}

function normalizeDefiDependency(raw: any) {
  return {
    key: normalizeText(raw.key, "dependency"),
    name: normalizeText(raw.name, "Dependency"),
    dependency_type: normalizeText(raw.dependency_type, "dependency"),
    risk_score: Number(raw.risk_score ?? 0),
    confidence_score: Number(raw.confidence_score ?? 0),
    source: normalizeText(raw.source, "internal"),
    freshness_hours: raw.freshness_hours != null ? Number(raw.freshness_hours) : null,
    notes: normalizeText(raw.notes),
  };
}

function normalizeDefiAssetProfile(raw: any) {
  return {
    symbol: normalizeText(raw.symbol, "Unknown"),
    role: normalizeText(raw.role, "asset"),
    chain: normalizeText(raw.chain, "unknown"),
    quality_score: Number(raw.quality_score ?? 0),
    risk_level: normalizeRiskLevel(raw.risk_level),
    confidence_score: Number(raw.confidence_score ?? 0),
    source: normalizeText(raw.source, "heuristic"),
    address: raw.address != null ? normalizeText(raw.address) : null,
    thesis: normalizeText(raw.thesis),
    token_analysis: raw.token_analysis && typeof raw.token_analysis === "object" ? raw.token_analysis : null,
  };
}

function normalizeDefiDeployment(raw: any) {
  return {
    chain: normalizeText(raw.chain, "unknown"),
    display_name: normalizeText(raw.display_name ?? raw.chain, "Unknown"),
    tvl_usd: raw.tvl_usd != null ? Number(raw.tvl_usd) : null,
    share_pct: raw.share_pct != null ? Number(raw.share_pct) : null,
    deployment_key: normalizeText(raw.deployment_key ?? raw.chain, "deployment"),
  };
}

function normalizeProtocolAI(raw: any) {
  if (!raw) return null;
  return {
    available: Boolean(raw.available),
    headline: normalizeText(raw.headline, "Protocol brief"),
    summary: normalizeText(raw.summary),
    best_for: normalizeText(raw.best_for),
    main_risks: normalizeStringArray(raw.main_risks),
    monitor_triggers: normalizeStringArray(raw.monitor_triggers),
    safer_alternative: normalizeText(raw.safer_alternative),
  };
}

function normalizeOpportunityAI(raw: any) {
  if (!raw) return null;
  return {
    available: Boolean(raw.available),
    headline: normalizeText(raw.headline, "Opportunity brief"),
    summary: normalizeText(raw.summary),
    best_for: normalizeText(raw.best_for),
    why_it_exists: normalizeText(raw.why_it_exists),
    main_risks: normalizeStringArray(raw.main_risks),
    monitor_triggers: normalizeStringArray(raw.monitor_triggers),
    safer_alternative: normalizeText(raw.safer_alternative),
  };
}

function normalizeOpportunity(raw: any, depth = 0): DefiOpportunityResponse {
  return {
    id: normalizeText(raw.id, ""),
    kind: raw.kind ?? "pool",
    product_type: raw.product_type != null ? normalizeText(raw.product_type) : null,
    score_family: raw.score_family != null ? normalizeText(raw.score_family) : null,
    title: normalizeText(raw.title ?? raw.symbol, "Opportunity"),
    subtitle: normalizeText(raw.subtitle),
    protocol: normalizeText(raw.protocol),
    protocol_name: normalizeText(raw.protocol_name ?? raw.protocol, "Unknown"),
    protocol_slug: normalizeText(raw.protocol_slug ?? raw.protocol),
    project: normalizeText(raw.project ?? raw.protocol),
    symbol: normalizeText(raw.symbol),
    chain: normalizeText(raw.chain),
    apy: Number(raw.apy ?? 0),
    tvl_usd: Number(raw.tvl_usd ?? raw.tvlUsd ?? 0),
    tags: normalizeStringArray(raw.tags),
    behavior: raw.behavior && typeof raw.behavior === "object" ? raw.behavior : typeof raw.behavior === "string" ? raw.behavior : null,
    summary: {
      overall_score: raw.summary?.overall_score != null ? Number(raw.summary?.overall_score) : undefined,
      quality_score: raw.summary?.quality_score != null ? Number(raw.summary?.quality_score) : undefined,
      opportunity_score: Number(raw.summary?.opportunity_score ?? 0),
      safety_score: Number(raw.summary?.safety_score ?? 0),
      risk_burden_score: raw.summary?.risk_burden_score != null ? Number(raw.summary?.risk_burden_score) : undefined,
      yield_durability_score: raw.summary?.yield_durability_score != null ? Number(raw.summary?.yield_durability_score) : undefined,
      yield_quality_score: Number(raw.summary?.yield_quality_score ?? 0),
      exit_liquidity_score: raw.summary?.exit_liquidity_score != null ? Number(raw.summary?.exit_liquidity_score) : undefined,
      exit_quality_score: Number(raw.summary?.exit_quality_score ?? 0),
      apr_efficiency_score: raw.summary?.apr_efficiency_score != null ? Number(raw.summary?.apr_efficiency_score) : undefined,
      effective_apr: raw.summary?.effective_apr != null ? Number(raw.summary?.effective_apr) : undefined,
      required_apr: raw.summary?.required_apr != null ? Number(raw.summary?.required_apr) : undefined,
      return_potential_score: raw.summary?.return_potential_score != null ? Number(raw.summary?.return_potential_score) : undefined,
      confidence_score: Number(raw.summary?.confidence_score ?? 0),
      risk_level: normalizeRiskLevel(raw.summary?.risk_level),
      strategy_fit: normalizeStrategyFit(raw.summary?.strategy_fit),
      headline: normalizeText(raw.summary?.headline),
      thesis: normalizeText(raw.summary?.thesis),
    },
    dimensions: Array.isArray(raw.dimensions) ? raw.dimensions.map(normalizeOpportunityDimension) : [],
    confidence: normalizeDefiConfidence(raw.confidence),
    score_caps: Array.isArray(raw.score_caps) ? raw.score_caps.map(normalizeDefiScoreCap) : [],
    evidence: Array.isArray(raw.evidence) ? raw.evidence.map(normalizeDefiEvidence) : [],
    scenarios: Array.isArray(raw.scenarios) ? raw.scenarios.map(normalizeDefiScenario) : [],
    dependencies: Array.isArray(raw.dependencies) ? raw.dependencies.map(normalizeDefiDependency) : [],
    assets: Array.isArray(raw.assets) ? raw.assets.map(normalizeDefiAssetProfile) : [],
    deployment: raw.deployment && typeof raw.deployment === "object" ? raw.deployment : {},
    ranking_profile: raw.ranking_profile ?? null,
    raw: raw.raw && typeof raw.raw === "object" ? raw.raw : {},
    history: raw.history
      ? {
          available: Boolean(raw.history.available),
          points: Array.isArray(raw.history.points) ? raw.history.points : [],
          apy_change_pct: raw.history.apy_change_pct != null ? Number(raw.history.apy_change_pct) : undefined,
          tvl_change_pct: raw.history.tvl_change_pct != null ? Number(raw.history.tvl_change_pct) : undefined,
        }
      : null,
    protocol_profile: depth === 0 && raw.protocol_profile ? normalizeDefiProtocolProfile(raw.protocol_profile, depth + 1) : null,
    related_opportunities: Array.isArray(raw.related_opportunities)
      ? raw.related_opportunities.map((item: any) => normalizeOpportunity(item, depth + 1))
      : [],
    rate_comparison: raw.rate_comparison
      ? {
          asset: raw.rate_comparison.asset ?? "",
          markets_found: Number(raw.rate_comparison.markets_found ?? 0),
          best_supply: Array.isArray(raw.rate_comparison.best_supply)
            ? raw.rate_comparison.best_supply.map(normalizeLendingMarket)
            : [],
          lowest_borrow: Array.isArray(raw.rate_comparison.lowest_borrow)
            ? raw.rate_comparison.lowest_borrow.map(normalizeLendingMarket)
            : [],
          all_markets: Array.isArray(raw.rate_comparison.all_markets)
            ? raw.rate_comparison.all_markets.map(normalizeLendingMarket)
            : [],
        }
      : null,
    safer_alternative: raw.safer_alternative ? normalizeOpportunity(raw.safer_alternative, depth + 1) : null,
    ai_analysis: normalizeOpportunityAI(raw.ai_analysis),
  };
}

function normalizeDefiProtocolProfile(raw: any, depth = 0): DefiProtocolProfile {
  return {
    protocol: normalizeText(raw.protocol ?? raw.slug, ""),
    display_name: normalizeText(raw.display_name ?? raw.protocol, "Unknown"),
    slug: normalizeText(raw.slug ?? raw.protocol, ""),
    category: raw.category != null ? normalizeText(raw.category) : null,
    url: raw.url != null ? normalizeText(raw.url) : null,
    logo: raw.logo != null ? normalizeText(raw.logo) : null,
    chains: normalizeStringArray(raw.chains),
    ranking_profile: raw.ranking_profile != null ? normalizeText(raw.ranking_profile) : null,
    summary: {
      tvl_usd: Number(raw.summary?.tvl_usd ?? raw.summary?.tvl ?? 0),
      safety_score: Number(raw.summary?.safety_score ?? 0),
      opportunity_score: Number(raw.summary?.opportunity_score ?? 0),
      confidence_score: Number(raw.summary?.confidence_score ?? 0),
      risk_level: normalizeRiskLevel(raw.summary?.risk_level),
      incident_count: Number(raw.summary?.incident_count ?? 0),
      audit_count: Number(raw.summary?.audit_count ?? 0),
      deployment_count: Number(raw.summary?.deployment_count ?? 0),
    },
    dimensions: Array.isArray(raw.dimensions) ? raw.dimensions.map(normalizeOpportunityDimension) : [],
    confidence: normalizeDefiConfidence(raw.confidence),
    chain_breakdown: Array.isArray(raw.chain_breakdown)
      ? raw.chain_breakdown.map((item: any) => ({ chain: item.chain ?? "", tvl_usd: item.tvl_usd != null ? Number(item.tvl_usd) : null, share_pct: item.share_pct != null ? Number(item.share_pct) : null }))
      : [],
    deployments: Array.isArray(raw.deployments) ? raw.deployments.map(normalizeDefiDeployment) : [],
    top_markets: Array.isArray(raw.top_markets) ? raw.top_markets.map(normalizeLendingMarket) : [],
    top_pools: Array.isArray(raw.top_pools) ? raw.top_pools.map(normalizePool) : [],
    top_opportunities: depth <= 0 && Array.isArray(raw.top_opportunities)
      ? raw.top_opportunities.map((item: any) => normalizeOpportunity(item, depth + 1))
      : [],
    audits: Array.isArray(raw.audits) ? raw.audits : [],
    incidents: Array.isArray(raw.incidents) ? raw.incidents : [],
    evidence: Array.isArray(raw.evidence) ? raw.evidence.map(normalizeDefiEvidence) : [],
    scenarios: Array.isArray(raw.scenarios) ? raw.scenarios.map(normalizeDefiScenario) : [],
    dependencies: Array.isArray(raw.dependencies) ? raw.dependencies.map(normalizeDefiDependency) : [],
    assets: Array.isArray(raw.assets) ? raw.assets.map(normalizeDefiAssetProfile) : [],
    docs_profile: raw.docs_profile && typeof raw.docs_profile === "object" ? raw.docs_profile : {},
    governance: raw.governance && typeof raw.governance === "object" ? raw.governance : {},
    methodology: normalizeStringRecord(raw.methodology),
    ai_analysis: normalizeProtocolAI(raw.ai_analysis),
  };
}

function normalizeDefiOpportunitiesResponse(raw: any): DefiOpportunitiesResponse {
  return {
    opportunities: Array.isArray(raw.opportunities) ? raw.opportunities.map((item: any) => normalizeOpportunity(item)) : [],
    count: Number(raw.count ?? 0),
    summary: {
      total_pool_tvl: Number(raw.summary?.total_pool_tvl ?? 0),
      avg_pool_apy: Number(raw.summary?.avg_pool_apy ?? 0),
      avg_yield_apy: Number(raw.summary?.avg_yield_apy ?? 0),
      high_risk_pool_count: Number(raw.summary?.high_risk_pool_count ?? 0),
      high_risk_yield_count: Number(raw.summary?.high_risk_yield_count ?? 0),
      stressed_lending_market_count: Number(raw.summary?.stressed_lending_market_count ?? 0),
      avg_opportunity_score: Number(raw.summary?.avg_opportunity_score ?? 0),
      avg_safety_score: Number(raw.summary?.avg_safety_score ?? 0),
      avg_confidence_score: Number(raw.summary?.avg_confidence_score ?? 0),
    },
    highlights: {
      best_conservative: raw.highlights?.best_conservative ? normalizeOpportunity(raw.highlights.best_conservative) : null,
      best_balanced: raw.highlights?.best_balanced ? normalizeOpportunity(raw.highlights.best_balanced) : null,
      best_aggressive: raw.highlights?.best_aggressive ? normalizeOpportunity(raw.highlights.best_aggressive) : null,
    },
    methodology: normalizeStringRecord(raw.methodology),
    filters: {
      chain: raw.filters?.chain ?? null,
      query: raw.filters?.query ?? null,
      min_tvl: Number(raw.filters?.min_tvl ?? 0),
      min_apy: Number(raw.filters?.min_apy ?? 0),
      ranking_profile: raw.filters?.ranking_profile ?? null,
    },
    ai_market_brief: normalizeDefiMarketBrief(raw.ai_market_brief),
    data_source: raw.data_source ?? "DefiLlama",
  };
}

function normalizeDefiAnalyzer(raw: any): DefiAnalyzerResponse {
  return {
    query: raw.query != null ? normalizeText(raw.query) : null,
    chain: raw.chain != null ? normalizeText(raw.chain) : null,
    ranking_profile: raw.ranking_profile != null ? normalizeText(raw.ranking_profile) : null,
    public_ranking_default: normalizeText(raw.public_ranking_default, "balanced"),
    count: {
      pools: Number(raw.count?.pools ?? 0),
      yields: Number(raw.count?.yields ?? 0),
      lending_markets: Number(raw.count?.lending_markets ?? 0),
      protocols: Number(raw.count?.protocols ?? 0),
      opportunities: Number(raw.count?.opportunities ?? 0),
    },
    summary: {
      total_pool_tvl: Number(raw.summary?.total_pool_tvl ?? 0),
      avg_pool_apy: Number(raw.summary?.avg_pool_apy ?? 0),
      avg_yield_apy: Number(raw.summary?.avg_yield_apy ?? 0),
      high_risk_pool_count: Number(raw.summary?.high_risk_pool_count ?? 0),
      high_risk_yield_count: Number(raw.summary?.high_risk_yield_count ?? 0),
      stressed_lending_market_count: Number(raw.summary?.stressed_lending_market_count ?? 0),
      avg_opportunity_score: Number(raw.summary?.avg_opportunity_score ?? 0),
      avg_safety_score: Number(raw.summary?.avg_safety_score ?? 0),
      avg_confidence_score: Number(raw.summary?.avg_confidence_score ?? 0),
    },
    highlights: {
      safest_pool: raw.highlights?.safest_pool ? normalizePool(raw.highlights.safest_pool) : null,
      best_sustainable_yield: raw.highlights?.best_sustainable_yield ? normalizeYield(raw.highlights.best_sustainable_yield) : null,
      lowest_risk_lending_market: raw.highlights?.lowest_risk_lending_market ? normalizeLendingMarket(raw.highlights.lowest_risk_lending_market) : null,
      largest_protocol: raw.highlights?.largest_protocol ? normalizeProtocolMatch(raw.highlights.largest_protocol) : null,
      best_conservative: raw.highlights?.best_conservative ? normalizeOpportunity(raw.highlights.best_conservative) : null,
      best_balanced: raw.highlights?.best_balanced ? normalizeOpportunity(raw.highlights.best_balanced) : null,
      best_aggressive: raw.highlights?.best_aggressive ? normalizeOpportunity(raw.highlights.best_aggressive) : null,
    },
    top_pools: Array.isArray(raw.top_pools) ? raw.top_pools.map(normalizePool) : [],
    top_yields: Array.isArray(raw.top_yields) ? raw.top_yields.map(normalizeYield) : [],
    top_lending_markets: Array.isArray(raw.top_lending_markets) ? raw.top_lending_markets.map(normalizeLendingMarket) : [],
    top_opportunities: Array.isArray(raw.top_opportunities) ? raw.top_opportunities.map((item: any) => normalizeOpportunity(item)) : [],
    protocol_spotlights: Array.isArray(raw.protocol_spotlights) ? raw.protocol_spotlights.map(normalizeProtocolMatch) : [],
    matching_protocols: Array.isArray(raw.matching_protocols) ? raw.matching_protocols.map(normalizeProtocolMatch) : [],
    methodology: normalizeStringRecord(raw.methodology),
    ai_market_brief: normalizeDefiMarketBrief(raw.ai_market_brief),
    data_source: normalizeText(raw.data_source, "DefiLlama"),
  };
}

function normalizeDefiCompareResponse(raw: any): DefiCompareResponse {
  return {
    asset: normalizeText(raw.asset),
    chain: raw.chain != null ? normalizeText(raw.chain) : null,
    mode: normalizeText(raw.mode, "supply"),
    ranking_profile: normalizeText(raw.ranking_profile, "balanced"),
    summary: {
      markets_compared: Number(raw.summary?.markets_compared ?? 0),
      best_balanced: raw.summary?.best_balanced ? normalizeOpportunity(raw.summary.best_balanced) : null,
      safest: raw.summary?.safest ? normalizeOpportunity(raw.summary.safest) : null,
      best_yield: raw.summary?.best_yield ? normalizeOpportunity(raw.summary.best_yield) : null,
      avoid: raw.summary?.avoid ? normalizeOpportunity(raw.summary.avoid) : null,
    },
    matrix: Array.isArray(raw.matrix)
      ? raw.matrix.map((item: any) => ({
          opportunity_id: normalizeText(item.opportunity_id),
          protocol: normalizeText(item.protocol, "Unknown"),
          chain: normalizeText(item.chain, "unknown"),
          asset: normalizeText(item.asset),
          apy: Number(item.apy ?? 0),
          opportunity_score: Number(item.opportunity_score ?? 0),
          safety_score: Number(item.safety_score ?? 0),
          yield_quality_score: Number(item.yield_quality_score ?? 0),
          exit_quality_score: Number(item.exit_quality_score ?? 0),
          confidence_score: Number(item.confidence_score ?? 0),
          headline: normalizeText(item.headline),
        }))
      : [],
    opportunities: Array.isArray(raw.opportunities) ? raw.opportunities.map((item: any) => normalizeOpportunity(item)) : [],
    methodology: normalizeStringRecord(raw.methodology),
    ai_market_brief: normalizeDefiMarketBrief(raw.ai_market_brief),
  };
}

function normalizeDefiSimulationResponse(raw: any): DefiSimulationResponse {
  return {
    kind: normalizeText(raw.kind, "simulation"),
    summary: normalizeText(raw.summary),
    base_case: raw.base_case && typeof raw.base_case === "object" ? raw.base_case : {},
    scenarios: Array.isArray(raw.scenarios)
      ? raw.scenarios.map((item: any) => ({
          name: normalizeText(item.name, "Scenario"),
          summary: normalizeText(item.summary),
          metric: normalizeText(item.metric, "metric"),
          value: Number(item.value ?? 0),
          unit: normalizeText(item.unit),
          severity: normalizeText(item.severity, "medium"),
        }))
      : [],
    recommendations: normalizeStringArray(raw.recommendations),
  };
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

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : { error: await response.text() };

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
  mode: AnalysisMode = "standard",
  chain?: ChainName
): Promise<AnalysisResponse> {
  return fetchAPI<AnalysisResponse>("/api/v1/analyze", {
    method: "POST",
    body: JSON.stringify({ address, mode, chain: chain ?? null }),
  });
}

export async function getTokenAnalysis(
  address: string,
  chain?: ChainName
): Promise<AnalysisResponse> {
  const params = new URLSearchParams();

  if (chain) {
    params.set("chain", chain);
  }

  const suffix = params.toString();
  return fetchAPI<AnalysisResponse>(`/api/v1/token/${address}${suffix ? `?${suffix}` : ""}`);
}

export async function refreshAnalysis(
  address: string,
  mode: AnalysisMode = "standard",
  chain?: ChainName
): Promise<AnalysisResponse> {
  const params = new URLSearchParams({ mode });

  if (chain) {
    params.set("chain", chain);
  }

  return fetchAPI<AnalysisResponse>(`/api/v1/token/${address}/refresh?${params.toString()}`, {
    method: "POST",
  });
}

export async function searchTokens(
  query: string,
  chain?: string,
  limit = 10
): Promise<SearchResponse> {
  const params = new URLSearchParams({ query, limit: String(limit) });
  if (chain) params.set("chain", chain);
  const raw = await fetchAPI<any>(`/api/v1/search?${params.toString()}`);
  return {
    query: normalizeText(raw.query, query),
    input_type: normalizeText(raw.input_type, "search_query"),
    results: Array.isArray(raw.results)
      ? raw.results.map((item: any) => ({
          type: normalizeText(item.type, "token"),
          product_type: item.product_type != null ? normalizeText(item.product_type) : null,
          title: normalizeText(item.title),
          subtitle: normalizeText(item.subtitle),
          address: item.address != null ? normalizeText(item.address) : null,
          chain: item.chain != null ? normalizeText(item.chain) : null,
          score: item.score != null ? Number(item.score) : null,
          url: item.url != null ? normalizeText(item.url) : null,
          logo: item.logo != null ? normalizeText(item.logo) : null,
        }))
      : [],
    count: Number(raw.count ?? 0),
    total: Number(raw.total ?? 0),
  };
}

export async function analyzePool(
  poolId: string,
  params?: { includeAi?: boolean; rankingProfile?: string; pairAddress?: string; chain?: string; source?: string }
): Promise<PoolAnalysisResponse> {
  const data = await fetchAPI<any>("/api/v1/defi/pool/analyze", {
    method: "POST",
    body: JSON.stringify({
      pool_id: poolId,
      pair_address: params?.pairAddress ?? null,
      chain: params?.chain ?? null,
      source: params?.source ?? null,
      include_ai: params?.includeAi ?? true,
      ranking_profile: params?.rankingProfile ?? "balanced",
    }),
  });
  return normalizeOpportunity(data);
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
  limit = 20,
  forceRefresh = false,
  chain?: ChainName
): Promise<TrendingResponse> {
  const params = new URLSearchParams({ category, limit: limit.toString() });
  if (forceRefresh) params.set("force_refresh", "1");
  if (chain) params.set("chain", chain);
  const data = await fetchAPI<any>(`/api/v1/trending?${params}`);
  return normalizeTrendingResponse(data);
}

export async function getNewPairs(limit = 20, chain?: ChainName): Promise<TrendingResponse> {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (chain) params.set("chain", chain);
  const data = await fetchAPI<any>(`/api/v1/trending/new?${params}`);
  return normalizeTrendingResponse(data);
}

export async function getGainers(limit = 20, chain?: ChainName): Promise<TrendingResponse> {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (chain) params.set("chain", chain);
  const data = await fetchAPI<any>(`/api/v1/trending/gainers?${params}`);
  return normalizeTrendingResponse(data);
}

export async function getLosers(limit = 20, chain?: ChainName): Promise<TrendingResponse> {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (chain) params.set("chain", chain);
  const data = await fetchAPI<any>(`/api/v1/trending/losers?${params}`);
  return normalizeTrendingResponse(data);
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

export async function getPortfolioChainMatrix(): Promise<PortfolioChainMatrixResponse> {
  const raw = await fetchAPI<any>("/api/v1/portfolio/chains");
  const payload = raw?.data ?? raw;

  return {
    chains: payload?.chains ?? {},
    capabilities: Array.isArray(payload?.capabilities) ? payload.capabilities : [],
  };
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
  chain?: ChainName;
  minAmountUsd?: number;
  type?: "buy" | "sell";
  limit?: number;
  forceRefresh?: boolean;
}): Promise<WhaleActivityResponse> {
  const searchParams = new URLSearchParams();
  if (params?.token) searchParams.set("token", params.token);
  if (params?.chain) searchParams.set("chain", params.chain);
  if (params?.minAmountUsd) searchParams.set("min_amount_usd", params.minAmountUsd.toString());
  if (params?.type) searchParams.set("type", params.type);
  if (params?.limit) searchParams.set("limit", params.limit.toString());
  if (params?.forceRefresh) searchParams.set("force_refresh", "1");

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
// SMART MONEY API
// ═══════════════════════════════════════════════════════════════════════════

export async function getSmartMoneyOverview(options?: RequestInit): Promise<SmartMoneyOverviewResponse> {
  return fetchAPI<SmartMoneyOverviewResponse>("/api/v1/smart-money/overview", options);
}

export async function getAlerts(severity?: string): Promise<AlertRecordResponse[]> {
  const params = new URLSearchParams();
  if (severity) params.set("severity", severity);
  return fetchAPI<AlertRecordResponse[]>(`/api/v1/alerts${params.toString() ? `?${params.toString()}` : ""}`);
}

export async function getAlertRules(): Promise<AlertRuleResponse[]> {
  return fetchAPI<AlertRuleResponse[]>("/api/v1/alerts/rules");
}

export async function createAlertRule(payload: {
  name: string;
  severity: string[];
}): Promise<AlertRuleResponse> {
  return fetchAPI<AlertRuleResponse>("/api/v1/alerts/rules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAlertRule(
  ruleId: string,
  payload: { name?: string; severity?: string[] }
): Promise<AlertRuleResponse> {
  return fetchAPI<AlertRuleResponse>(`/api/v1/alerts/rules/${ruleId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteAlertRule(ruleId: string): Promise<void> {
  await fetchAPI(`/api/v1/alerts/rules/${ruleId}`, { method: "DELETE" });
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

// ═══════════════════════════════════════════════════════════════════════════
// CHAINS API
// ═══════════════════════════════════════════════════════════════════════════

export async function getChains(): Promise<{ chains: ChainInfo[]; count: number }> {
  const data = await fetchAPI<{ chains: any[]; count?: number; total?: number }>("/api/v1/chains");
  return {
    chains: (data.chains ?? []).map(normalizeChainInfo),
    count: data.count ?? data.total ?? 0,
  };
}

export async function getChainInfo(chain: ChainName): Promise<ChainInfo> {
  const data = await fetchAPI<any>(`/api/v1/chains/${chain}`);
  return normalizeChainInfo(data);
}

// ═══════════════════════════════════════════════════════════════════════════
// CONTRACT SCAN API
// ═══════════════════════════════════════════════════════════════════════════

export async function scanContract(
  address: string,
  chain: ChainName
): Promise<ContractScanResponse> {
  const data = await fetchAPI<any>("/api/v1/contract/scan", {
    method: "POST",
    body: JSON.stringify({ address, chain }),
  });
  return normalizeContractScan(data);
}

export async function getContractScan(
  chain: ChainName,
  address: string
): Promise<ContractScanResponse> {
  const data = await fetchAPI<any>(`/api/v1/contract/${chain}/${address}`);
  return normalizeContractScan(data);
}

// ═══════════════════════════════════════════════════════════════════════════
// SHIELD / APPROVALS API
// ═══════════════════════════════════════════════════════════════════════════

export async function scanWalletApprovals(
  wallet: string,
  chain?: ChainName,
  minRisk?: number
): Promise<ShieldScanResponse> {
  const params = new URLSearchParams();
  if (chain) params.set("chain", chain);
  if (minRisk != null) params.set("min_risk", minRisk.toString());
  const query = params.toString();
  const data = await fetchAPI<any>(
    `/api/v1/shield/${wallet}${query ? `?${query}` : ""}`
  );
  return normalizeShieldScan(data);
}

export async function prepareRevoke(
  tokenAddress: string,
  spenderAddress: string,
  chain: ChainName
): Promise<RevokePreparationResponse> {
  return fetchAPI<RevokePreparationResponse>("/api/v1/shield/revoke", {
    method: "POST",
    body: JSON.stringify({
      token_address: tokenAddress,
      spender_address: spenderAddress,
      chain,
    }),
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// DEFI POOLS / YIELDS API
// ═══════════════════════════════════════════════════════════════════════════

export async function getDefiPools(params?: {
  chain?: string;
  protocol?: string;
  minTvl?: number;
  minApy?: number;
  maxApy?: number;
  limit?: number;
}): Promise<{ pools: PoolResponse[]; count: number; total_tvl: number }> {
  const p = new URLSearchParams();
  if (params?.chain) p.set("chain", params.chain);
  if (params?.protocol) p.set("protocol", params.protocol);
  if (params?.minTvl != null) p.set("min_tvl", params.minTvl.toString());
  if (params?.minApy != null) p.set("min_apy", params.minApy.toString());
  if (params?.maxApy != null) p.set("max_apy", params.maxApy.toString());
  if (params?.limit != null) p.set("limit", params.limit.toString());
  const query = p.toString();
  const data = await fetchAPI<any>(`/api/v1/defi/pools${query ? `?${query}` : ""}`);
  return {
    pools: Array.isArray(data.pools) ? data.pools.map(normalizePool) : [],
    count: data.count ?? 0,
    total_tvl: data.total_tvl ?? data.summary?.total_tvl ?? 0,
  };
}

export async function getDefiYields(params?: {
  chain?: string;
  exposure?: "stable-stable" | "crypto-stable" | "crypto-crypto";
  minApy?: number;
  maxApy?: number;
  minTvl?: number;
  minSustainability?: number;
  limit?: number;
}): Promise<{ yields: YieldOpportunityResponse[]; count: number }> {
  const p = new URLSearchParams();
  if (params?.chain) p.set("chain", params.chain);
  if (params?.exposure) p.set("exposure", params.exposure);
  if (params?.minApy != null) p.set("min_apy", params.minApy.toString());
  if (params?.maxApy != null) p.set("max_apy", params.maxApy.toString());
  if (params?.minTvl != null) p.set("min_tvl", params.minTvl.toString());
  if (params?.minSustainability != null)
    p.set("min_sustainability", params.minSustainability.toString());
  if (params?.limit != null) p.set("limit", params.limit.toString());
  const query = p.toString();
  const data = await fetchAPI<any>(`/api/v1/defi/yields${query ? `?${query}` : ""}`);
  return {
    yields: Array.isArray(data.yields) ? data.yields.map(normalizeYield) : [],
    count: data.count ?? 0,
  };
}

export async function analyzeDefi(params?: {
  query?: string;
  chain?: string;
  minTvl?: number;
  minApy?: number;
  limit?: number;
  includeAi?: boolean;
  rankingProfile?: string;
}): Promise<DefiAnalyzerResponse> {
  const p = new URLSearchParams();
  if (params?.query) p.set("query", params.query);
  if (params?.chain) p.set("chain", params.chain);
  if (params?.minTvl != null) p.set("min_tvl", params.minTvl.toString());
  if (params?.minApy != null) p.set("min_apy", params.minApy.toString());
  if (params?.limit != null) p.set("limit", params.limit.toString());
  if (params?.includeAi != null) p.set("include_ai", String(params.includeAi));
  if (params?.rankingProfile) p.set("ranking_profile", params.rankingProfile);
  const query = p.toString();
  const data = await fetchAPI<any>(`/api/v1/defi/analyze${query ? `?${query}` : ""}`);
  return normalizeDefiAnalyzer(data);
}

export async function getDefiOpportunities(params?: {
  query?: string;
  chain?: string;
  minTvl?: number;
  minApy?: number;
  limit?: number;
  includeAi?: boolean;
  rankingProfile?: string;
}): Promise<DefiOpportunitiesResponse> {
  const p = new URLSearchParams();
  if (params?.query) p.set("query", params.query);
  if (params?.chain) p.set("chain", params.chain);
  if (params?.minTvl != null) p.set("min_tvl", params.minTvl.toString());
  if (params?.minApy != null) p.set("min_apy", params.minApy.toString());
  if (params?.limit != null) p.set("limit", params.limit.toString());
  if (params?.includeAi != null) p.set("include_ai", String(params.includeAi));
  if (params?.rankingProfile) p.set("ranking_profile", params.rankingProfile);
  const query = p.toString();
  const data = await fetchAPI<any>(`/api/v1/defi/opportunities${query ? `?${query}` : ""}`);
  return normalizeDefiOpportunitiesResponse(data);
}

export async function getDefiOpportunity(
  opportunityId: string,
  params?: { includeAi?: boolean; rankingProfile?: string }
): Promise<DefiOpportunityResponse> {
  const p = new URLSearchParams();
  if (params?.includeAi != null) p.set("include_ai", String(params.includeAi));
  if (params?.rankingProfile) p.set("ranking_profile", params.rankingProfile);
  const query = p.toString();
  const data = await fetchAPI<any>(`/api/v1/defi/opportunities/${opportunityId}${query ? "?" + query : ""}`);
  return normalizeOpportunity(data);
}

export async function createOpportunityAnalysis(
  payload: import("../types").DefiDiscoverRequest
): Promise<import("../types").DefiDiscoverResponse> {
  return fetchAPI<import("../types").DefiDiscoverResponse>("/api/v1/defi/discover", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getDefiProtocolProfile(
  slug: string,
  params?: { includeAi?: boolean; rankingProfile?: string }
): Promise<DefiProtocolProfile> {
  const p = new URLSearchParams();
  if (params?.includeAi != null) p.set("include_ai", String(params.includeAi));
  if (params?.rankingProfile) p.set("ranking_profile", params.rankingProfile);
  const query = p.toString();
  const data = await fetchAPI<any>(`/api/v1/defi/protocol/${slug}${query ? `?${query}` : ""}`);
  return normalizeDefiProtocolProfile(data);
}

export async function getDefiComparison(params: {
  asset: string;
  chain?: string;
  protocols?: string[];
  mode?: "supply" | "borrow";
  includeAi?: boolean;
  rankingProfile?: string;
}): Promise<DefiCompareResponse> {
  const p = new URLSearchParams({ asset: params.asset });
  if (params.chain) p.set("chain", params.chain);
  if (params.protocols?.length) p.set("protocols", params.protocols.join(","));
  if (params.mode) p.set("mode", params.mode);
  if (params.includeAi != null) p.set("include_ai", String(params.includeAi));
  if (params.rankingProfile) p.set("ranking_profile", params.rankingProfile);
  const data = await fetchAPI<any>(`/api/v2/defi/compare?${p.toString()}`);
  return normalizeDefiCompareResponse(data);
}

export async function simulateLpPosition(payload: {
  depositUsd: number;
  apy: number;
  tvlUsd: number;
  priceMovePct?: number;
  emissionsDecayPct?: number;
  stableDepegPct?: number;
}): Promise<DefiSimulationResponse> {
  const data = await fetchAPI<any>("/api/v2/defi/simulate/lp", {
    method: "POST",
    body: JSON.stringify({
      deposit_usd: payload.depositUsd,
      apy: payload.apy,
      tvl_usd: payload.tvlUsd,
      price_move_pct: payload.priceMovePct ?? 0,
      emissions_decay_pct: payload.emissionsDecayPct ?? 0,
      stable_depeg_pct: payload.stableDepegPct ?? 0,
    }),
  });
  return normalizeDefiSimulationResponse(data);
}

export async function simulateLendingPosition(payload: {
  collateralUsd: number;
  debtUsd: number;
  liquidationThreshold?: number;
  collateralDropPct?: number;
  stableDepegPct?: number;
  borrowRateSpikePct?: number;
  utilizationPct?: number;
  utilizationShockPct?: number;
}): Promise<DefiSimulationResponse> {
  const data = await fetchAPI<any>("/api/v2/defi/simulate/lending", {
    method: "POST",
    body: JSON.stringify({
      collateral_usd: payload.collateralUsd,
      debt_usd: payload.debtUsd,
      liquidation_threshold: payload.liquidationThreshold ?? 0.8,
      collateral_drop_pct: payload.collateralDropPct ?? 0,
      stable_depeg_pct: payload.stableDepegPct ?? 0,
      borrow_rate_spike_pct: payload.borrowRateSpikePct ?? 0,
      utilization_pct: payload.utilizationPct ?? 0,
      utilization_shock_pct: payload.utilizationShockPct ?? 0,
    }),
  });
  return normalizeDefiSimulationResponse(data);
}

export async function analyzeDefiPosition(payload: {
  kind: "lp" | "lending";
  depositUsd?: number;
  apy?: number;
  tvlUsd?: number;
  collateralUsd?: number;
  debtUsd?: number;
  liquidationThreshold?: number;
  priceMovePct?: number;
  emissionsDecayPct?: number;
  stableDepegPct?: number;
  borrowRateSpikePct?: number;
  utilizationPct?: number;
  utilizationShockPct?: number;
}): Promise<DefiPositionAnalysisResponse> {
  const data = await fetchAPI<any>("/api/v2/defi/positions/analyze", {
    method: "POST",
    body: JSON.stringify({
      kind: payload.kind,
      deposit_usd: payload.depositUsd ?? 0,
      apy: payload.apy ?? 0,
      tvl_usd: payload.tvlUsd ?? 0,
      collateral_usd: payload.collateralUsd ?? 0,
      debt_usd: payload.debtUsd ?? 0,
      liquidation_threshold: payload.liquidationThreshold ?? 0.8,
      price_move_pct: payload.priceMovePct ?? 0,
      emissions_decay_pct: payload.emissionsDecayPct ?? 0,
      stable_depeg_pct: payload.stableDepegPct ?? 0,
      borrow_rate_spike_pct: payload.borrowRateSpikePct ?? 0,
      utilization_pct: payload.utilizationPct ?? 0,
      utilization_shock_pct: payload.utilizationShockPct ?? 0,
    }),
  });
  return {
    ...normalizeDefiSimulationResponse(data),
    position_size_usd: Number(data.position_size_usd ?? 0),
    monitor_triggers: normalizeStringArray(data.monitor_triggers),
  };
}

export async function getDefiProtocols(
  chain?: string,
  limit = 50
): Promise<{ protocols: unknown[]; count: number }> {
  const p = new URLSearchParams({ limit: limit.toString() });
  if (chain) p.set("chain", chain);
  return fetchAPI(`/api/v1/defi/protocols?${p}`);
}

export async function getLendingMarkets(params?: {
  protocol?: string;
  chain?: string;
  asset?: string;
  limit?: number;
}): Promise<LendingMarketsResponse> {
  const p = new URLSearchParams();
  if (params?.protocol) p.set("protocol", params.protocol);
  if (params?.chain) p.set("chain", params.chain);
  if (params?.asset) p.set("asset", params.asset);
  if (params?.limit != null) p.set("limit", params.limit.toString());
  const query = p.toString();
  const data = await fetchAPI<any>(`/api/v1/defi/lending${query ? `?${query}` : ""}`);
  return {
    markets: Array.isArray(data.markets) ? data.markets.map(normalizeLendingMarket) : [],
    count: Number(data.count ?? 0),
    filters: {
      protocol: data.filters?.protocol ?? null,
      chain: data.filters?.chain ?? null,
      asset: data.filters?.asset ?? null,
    },
    data_source: data.data_source ?? "DefiLlama",
  };
}

export async function calculateHealthFactor(params: {
  collateralUsd: number;
  debtUsd: number;
  protocol?: string;
  ltv?: number;
}): Promise<HealthFactorResponse> {
  const searchParams = new URLSearchParams({
    collateral_usd: params.collateralUsd.toString(),
    debt_usd: params.debtUsd.toString(),
  });

  if (params.protocol) searchParams.set("protocol", params.protocol);
  if (params.ltv != null) searchParams.set("ltv", params.ltv.toString());

  return fetchAPI<HealthFactorResponse>(`/api/v1/defi/health?${searchParams.toString()}`);
}

// ═══════════════════════════════════════════════════════════════════════════
// INTEL / REKT API
// ═══════════════════════════════════════════════════════════════════════════

export async function getRektIncidents(params?: {
  chain?: string;
  attackType?: string;
  minAmount?: number;
  search?: string;
  limit?: number;
}): Promise<RektListResponse> {
  const p = new URLSearchParams();
  if (params?.chain) p.set("chain", params.chain);
  if (params?.attackType) p.set("attack_type", params.attackType);
  if (params?.minAmount != null) p.set("min_amount", params.minAmount.toString());
  if (params?.search) p.set("search", params.search);
  if (params?.limit != null) p.set("limit", params.limit.toString());
  const query = p.toString();
  const raw = await fetchAPI<any>(`/api/v1/intel/rekt${query ? `?${query}` : ""}`);
  const payload = raw?.data ?? raw;
  const incidents = Array.isArray(payload?.incidents) ? payload.incidents : [];
  const meta = raw?.meta ?? {};

  return {
    incidents: incidents as RektIncident[],
    count: Number(payload?.count ?? incidents.length),
    total_stolen_usd: Number(payload?.total_stolen_usd ?? 0),
    meta: {
      cursor: typeof meta.cursor === "string" ? meta.cursor : null,
      freshness: typeof meta.freshness === "string" ? meta.freshness : "unknown",
    },
  };
}

export async function getRektIncident(id: string): Promise<RektIncident | null> {
  const raw = await fetchAPI<any>(`/api/v1/intel/rekt/${id}`);
  const payload = raw?.data ?? raw;
  if (!payload || typeof payload !== "object") {
    return null;
  }
  return payload as RektIncident;
}

export async function getAudits(params?: {
  protocol?: string;
  auditor?: string;
  chain?: string;
  verdict?: "PASS" | "FAIL";
  limit?: number;
}): Promise<{ audits: AuditRecord[]; count: number }> {
  const p = new URLSearchParams();
  if (params?.protocol) p.set("protocol", params.protocol);
  if (params?.auditor) p.set("auditor", params.auditor);
  if (params?.chain) p.set("chain", params.chain);
  if (params?.verdict) p.set("verdict", params.verdict);
  if (params?.limit != null) p.set("limit", params.limit.toString());
  const query = p.toString();
  return fetchAPI(`/api/v1/intel/audits${query ? `?${query}` : ""}`);
}

export async function getIntelStats(): Promise<IntelStatsResponse> {
  return fetchAPI<IntelStatsResponse>("/api/v1/intel/stats");
}

export { APIError };
