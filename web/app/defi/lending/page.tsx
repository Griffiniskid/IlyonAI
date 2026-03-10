"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Building2,
  CheckCircle,
  Calculator,
  Loader2,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import * as api from "@/lib/api";
import type { DefiSimulationResponse, HealthFactorResponse, LendingMarketResponse } from "@/types";

// Known lending protocols for quick filter
const PROTOCOLS = [
  { id: "aave-v3",    label: "Aave V3",    chains: ["ETH", "ARB", "BASE", "OP", "AVAX", "MATIC"] },
  { id: "compound-v3",label: "Compound V3",chains: ["ETH", "BASE", "ARB"] },
  { id: "morpho",     label: "Morpho",     chains: ["ETH", "BASE"] },
  { id: "spark",      label: "Spark",      chains: ["ETH"] },
  { id: "solend",     label: "Solend",     chains: ["SOL"] },
  { id: "marginfi",   label: "MarginFi",   chains: ["SOL"] },
  { id: "kamino",     label: "Kamino",     chains: ["SOL"] },
];

const CHAIN_FILTERS = [
  "All", "Ethereum", "Base", "Arbitrum", "Polygon", "Optimism", "Avalanche", "Solana",
];

function RiskBadge({ level }: { level: string }) {
  const styles: Record<string, string> = {
    HIGH:   "bg-red-500/10 text-red-400 border-red-500/20",
    MEDIUM: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
    LOW:    "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  };
  return (
    <span className={cn("px-2 py-0.5 rounded-full text-xs font-medium border", styles[level] || styles.MEDIUM)}>
      {level}
    </span>
  );
}

function HealthCalculator() {
  const [collateral, setCollateral] = useState("");
  const [debt, setDebt] = useState("");
  const [protocol, setProtocol] = useState("aave-v3");
  const [result, setResult] = useState<HealthFactorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const calculate = async () => {
    if (!collateral || !debt) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.calculateHealthFactor({
        collateralUsd: Number(collateral),
        debtUsd: Number(debt),
        protocol,
      });
      setResult(response);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Failed to calculate health factor.");
    } finally {
      setLoading(false);
    }
  };

  const hf = result?.health_factor ?? null;
  const status = result?.status ?? null;

  const statusColor: Record<string, string> = {
    SAFE:     "text-emerald-400",
    MODERATE: "text-blue-400",
    WARNING:  "text-yellow-400",
    DANGER:   "text-red-400",
  };

  return (
    <div className="bg-card/60 border border-white/10 rounded-xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <Calculator className="w-5 h-5 text-emerald-400" />
        <h3 className="font-semibold">Health Factor Calculator</h3>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Collateral (USD)</label>
          <Input
            type="number"
            placeholder="10000"
            value={collateral}
            onChange={e => setCollateral(e.target.value)}
            className="bg-black/20 border-white/10"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Debt (USD)</label>
          <Input
            type="number"
            placeholder="5000"
            value={debt}
            onChange={e => setDebt(e.target.value)}
            className="bg-black/20 border-white/10"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Protocol</label>
          <select
            value={protocol}
            onChange={e => setProtocol(e.target.value)}
            className="w-full h-9 rounded-md bg-black/20 border border-white/10 px-2 text-sm text-foreground"
          >
            {PROTOCOLS.map(p => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>
      </div>

      <Button
        onClick={calculate}
        disabled={loading || !collateral || !debt}
        className="bg-emerald-600 hover:bg-emerald-500 text-black"
      >
        {loading ? "Calculating..." : "Calculate"}
      </Button>

      {result && (
        <div className="mt-4 p-4 rounded-lg bg-black/30 border border-white/10">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-muted-foreground">Health Factor</span>
            <span className={cn("text-2xl font-bold", statusColor[status || ""] || "text-foreground")}>
              {hf === null ? "—" : hf === Infinity ? "∞" : hf.toFixed(2)}
            </span>
          </div>
          <div className={cn("text-sm font-medium mb-2", statusColor[status || ""] || "")}>
            {status}
          </div>
          <p className="text-sm text-muted-foreground">{result.message}</p>
          {(result.collateral_drop_to_liquidation_pct ?? 0) > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              Collateral can drop {(result.collateral_drop_to_liquidation_pct ?? 0).toFixed(1)}% before liquidation
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      )}
    </div>
  );
}

function SimulationSuite() {
  const [lending, setLending] = useState({ collateral: "10000", debt: "5000", utilization: "72", drop: "20", rateSpike: "8" });
  const [lp, setLp] = useState({ deposit: "5000", apy: "18", tvl: "2000000", priceMove: "20", emissionsDecay: "40" });
  const [lendingResult, setLendingResult] = useState<DefiSimulationResponse | null>(null);
  const [lpResult, setLpResult] = useState<DefiSimulationResponse | null>(null);
  const [loading, setLoading] = useState<"lending" | "lp" | null>(null);

  const runLending = async () => {
    setLoading("lending");
    try {
      setLendingResult(await api.simulateLendingPosition({
        collateralUsd: Number(lending.collateral),
        debtUsd: Number(lending.debt),
        utilizationPct: Number(lending.utilization),
        collateralDropPct: Number(lending.drop),
        borrowRateSpikePct: Number(lending.rateSpike),
      }));
    } finally {
      setLoading(null);
    }
  };

  const runLp = async () => {
    setLoading("lp");
    try {
      setLpResult(await api.simulateLpPosition({
        depositUsd: Number(lp.deposit),
        apy: Number(lp.apy),
        tvlUsd: Number(lp.tvl),
        priceMovePct: Number(lp.priceMove),
        emissionsDecayPct: Number(lp.emissionsDecay),
      }));
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="bg-card/60 border border-white/10 rounded-xl p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="font-semibold">Lending Stress Simulator</h3>
            <p className="text-sm text-muted-foreground mt-1">Model collateral drawdowns, borrow-rate spikes, and reserve stress.</p>
          </div>
          <Link href="/defi/compare" className="text-xs text-emerald-400 inline-flex items-center gap-1">Compare <ArrowRight className="w-3 h-3" /></Link>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input value={lending.collateral} onChange={(e) => setLending({ ...lending, collateral: e.target.value })} type="number" placeholder="Collateral USD" className="bg-black/20 border-white/10" />
          <Input value={lending.debt} onChange={(e) => setLending({ ...lending, debt: e.target.value })} type="number" placeholder="Debt USD" className="bg-black/20 border-white/10" />
          <Input value={lending.utilization} onChange={(e) => setLending({ ...lending, utilization: e.target.value })} type="number" placeholder="Utilization %" className="bg-black/20 border-white/10" />
          <Input value={lending.drop} onChange={(e) => setLending({ ...lending, drop: e.target.value })} type="number" placeholder="Collateral drop %" className="bg-black/20 border-white/10" />
          <Input value={lending.rateSpike} onChange={(e) => setLending({ ...lending, rateSpike: e.target.value })} type="number" placeholder="Borrow spike %" className="bg-black/20 border-white/10 col-span-2" />
        </div>
        <Button onClick={runLending} disabled={loading !== null} className="mt-4 bg-emerald-600 hover:bg-emerald-500 text-black">
          {loading === "lending" ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Simulating...</> : "Run lending stress"}
        </Button>
        {lendingResult && (
          <div className="mt-4 space-y-3">
            <p className="text-sm text-muted-foreground">{lendingResult.summary}</p>
            {lendingResult.scenarios.map((scenario) => (
              <div key={scenario.name} className="rounded-lg border border-white/10 bg-black/20 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-sm">{scenario.name}</div>
                  <RiskBadge level={scenario.severity.toUpperCase()} />
                </div>
                <div className="mt-2 text-sm text-muted-foreground">{scenario.summary}</div>
                <div className="mt-2 text-sm">{scenario.value.toFixed(2)} {scenario.unit}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-card/60 border border-white/10 rounded-xl p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="font-semibold">LP / Farm Stress Simulator</h3>
            <p className="text-sm text-muted-foreground mt-1">Model impermanent loss, emissions decay, and exit impact before entering.</p>
          </div>
          <Link href="/defi" className="text-xs text-emerald-400 inline-flex items-center gap-1">Discover <ArrowRight className="w-3 h-3" /></Link>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input value={lp.deposit} onChange={(e) => setLp({ ...lp, deposit: e.target.value })} type="number" placeholder="Deposit USD" className="bg-black/20 border-white/10" />
          <Input value={lp.apy} onChange={(e) => setLp({ ...lp, apy: e.target.value })} type="number" placeholder="APY %" className="bg-black/20 border-white/10" />
          <Input value={lp.tvl} onChange={(e) => setLp({ ...lp, tvl: e.target.value })} type="number" placeholder="Pool TVL USD" className="bg-black/20 border-white/10" />
          <Input value={lp.priceMove} onChange={(e) => setLp({ ...lp, priceMove: e.target.value })} type="number" placeholder="Price move %" className="bg-black/20 border-white/10" />
          <Input value={lp.emissionsDecay} onChange={(e) => setLp({ ...lp, emissionsDecay: e.target.value })} type="number" placeholder="Emissions decay %" className="bg-black/20 border-white/10 col-span-2" />
        </div>
        <Button onClick={runLp} disabled={loading !== null} className="mt-4 bg-emerald-600 hover:bg-emerald-500 text-black">
          {loading === "lp" ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Simulating...</> : "Run LP stress"}
        </Button>
        {lpResult && (
          <div className="mt-4 space-y-3">
            <p className="text-sm text-muted-foreground">{lpResult.summary}</p>
            {lpResult.scenarios.map((scenario) => (
              <div key={scenario.name} className="rounded-lg border border-white/10 bg-black/20 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-sm">{scenario.name}</div>
                  <RiskBadge level={scenario.severity.toUpperCase()} />
                </div>
                <div className="mt-2 text-sm text-muted-foreground">{scenario.summary}</div>
                <div className="mt-2 text-sm">{scenario.value.toFixed(2)} {scenario.unit}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function formatUSD(n: number) {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

export default function LendingPage() {
  const [chain, setChain] = useState("All");
  const [protocol, setProtocol] = useState<string | null>(null);
  const [asset, setAsset] = useState("");
  const [view, setView] = useState<"supply" | "borrow">("supply");

  const { data, isLoading, error } = useQuery({
    queryKey: ["lending-markets", chain, protocol, asset],
    queryFn: () => api.getLendingMarkets({
      chain: chain !== "All" ? chain.toLowerCase() : undefined,
      protocol: protocol ?? undefined,
      asset: asset || undefined,
      limit: 80,
    }),
    staleTime: 60_000,
  });

  const markets: LendingMarketResponse[] = data?.markets ?? [];
  const sorted = [...markets].sort((a, b) =>
    view === "supply"
      ? b.apy_supply - a.apy_supply
      : a.apy_borrow - b.apy_borrow
  );

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
          <div className="flex items-center gap-3">
            <Building2 className="w-7 h-7 text-emerald-400" />
            <h1 className="text-3xl font-bold">Lending Markets</h1>
          </div>
          <Button asChild variant="outline">
            <Link href="/defi/compare">
              Compare Protocols <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
        <p className="text-muted-foreground">
          Compare supply and borrow rates across Aave, Compound, Morpho, Solend, and more.
          All markets are risk-scored and audit-verified.
        </p>
      </div>

      {/* Health Calculator */}
      <div className="mb-8">
        <HealthCalculator />
      </div>

      <div className="mb-8">
        <SimulationSuite />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Chain filter */}
        <div className="flex gap-1 flex-wrap">
          {CHAIN_FILTERS.map(c => (
            <button
              key={c}
              onClick={() => setChain(c)}
              className={cn(
                "px-3 py-1 rounded-full text-xs font-medium border transition-colors",
                chain === c
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                  : "bg-white/5 text-muted-foreground border-white/10 hover:border-white/20"
              )}
            >
              {c}
            </button>
          ))}
        </div>

        {/* Asset search */}
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="Asset (USDC, ETH...)"
            value={asset}
            onChange={e => setAsset(e.target.value.toUpperCase())}
            className="pl-7 h-8 text-xs bg-black/20 border-white/10 w-36"
          />
        </div>

        {/* View toggle */}
        <div className="flex rounded-lg border border-white/10 overflow-hidden ml-auto">
          {(["supply", "borrow"] as const).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                "px-4 py-1.5 text-xs font-medium transition-colors capitalize",
                view === v
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {v === "supply" ? "Best Supply APY" : "Lowest Borrow APY"}
            </button>
          ))}
        </div>
      </div>

      {/* Protocol quick-filter row */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <button
          onClick={() => setProtocol(null)}
          className={cn(
            "px-3 py-1 rounded-full text-xs border transition-colors",
            !protocol ? "bg-white/10 text-foreground border-white/20" : "text-muted-foreground border-white/10 hover:border-white/20"
          )}
        >
          All Protocols
        </button>
        {PROTOCOLS.map(p => (
          <button
            key={p.id}
            onClick={() => setProtocol(protocol === p.id ? null : p.id)}
            className={cn(
              "px-3 py-1 rounded-full text-xs border transition-colors",
              protocol === p.id
                ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                : "text-muted-foreground border-white/10 hover:border-white/20"
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Markets table */}
      {isLoading ? (
        <div className="text-center py-16 text-muted-foreground">Loading lending markets...</div>
      ) : error ? (
        <div className="text-center py-16 text-red-400">
          {error instanceof Error ? error.message : "Failed to load lending markets."}
        </div>
      ) : markets.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">No markets found for current filters.</div>
      ) : (
        <div className="space-y-2">
          {/* Header row */}
          <div className="grid grid-cols-7 gap-4 px-4 py-2 text-xs text-muted-foreground font-medium">
            <div className="col-span-2">Market</div>
            <div className="text-right">TVL</div>
            <div className="text-right">Supply APY</div>
            <div className="text-right">Borrow APY</div>
            <div className="text-right">Utilization</div>
            <div className="text-right">Risk</div>
          </div>

          {sorted.map((market, i) => (
            <div
              key={`${market.pool_id}-${i}`}
              className="grid grid-cols-7 gap-4 px-4 py-3 rounded-xl bg-card/50 border border-white/5 hover:border-white/10 transition-colors items-center"
            >
              {/* Protocol + Symbol */}
              <div className="col-span-2">
                <div className="font-medium text-sm">{market.symbol}</div>
                <div className="text-xs text-muted-foreground">
                  <Link href={`/defi/protocol/${market.protocol}`} className="hover:text-foreground transition-colors">
                    {market.protocol_display}
                  </Link>
                  <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-white/5">
                    {market.chain}
                  </span>
                  {market.audit_status === "audited" && (
                    <CheckCircle className="inline ml-1 w-3 h-3 text-emerald-400" />
                  )}
                </div>
              </div>

              {/* TVL */}
              <div className="text-right text-sm">{formatUSD(market.tvlUsd)}</div>

              {/* Supply APY */}
              <div className="text-right">
                <span className={cn("text-sm font-medium", market.apy_supply > 10 ? "text-emerald-400" : "")}>
                  {market.apy_supply > 0 ? `${market.apy_supply.toFixed(2)}%` : "—"}
                </span>
              </div>

              {/* Borrow APY */}
              <div className="text-right">
                <span className={cn("text-sm", market.apy_borrow > 20 ? "text-red-400" : "text-muted-foreground")}>
                  {market.apy_borrow > 0 ? `${market.apy_borrow.toFixed(2)}%` : "—"}
                </span>
              </div>

              {/* Utilization */}
              <div className="text-right">
                <span className={cn("text-sm", (market.utilization_pct || 0) > 85 ? "text-red-400" : "text-muted-foreground")}>
                  {market.utilization_pct != null ? `${market.utilization_pct.toFixed(0)}%` : "—"}
                </span>
              </div>

              {/* Risk */}
              <div className="text-right">
                <RiskBadge level={market.market_risk?.risk_level || "LOW"} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Summary */}
      {markets.length > 0 && (
        <div className="mt-4 text-sm text-muted-foreground text-right">
          Showing {sorted.length} markets · Data from DefiLlama
        </div>
      )}
    </div>
  );
}
