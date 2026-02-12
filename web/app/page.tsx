"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { GlassCard } from "@/components/ui/card";
import {
  Shield,
  Search,
  TrendingUp,
  Zap,
  Eye,
  BarChart3,
  Lock,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Users,
  Activity,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import { cn, formatCompact } from "@/lib/utils";
import { useDashboardStats } from "@/lib/hooks";

// Animated background orbs
function BackgroundEffects() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      {/* Main glow */}
      <div className="hero-glow top-[-200px] left-1/2 -translate-x-1/2" />

      {/* Floating orbs */}
      <div
        className="hero-orb w-[400px] h-[400px] top-[10%] left-[10%]"
        style={{ animationDelay: '0s' }}
      />
      <div
        className="hero-orb w-[300px] h-[300px] top-[60%] right-[5%]"
        style={{ animationDelay: '2s' }}
      />
      <div
        className="hero-orb w-[200px] h-[200px] bottom-[20%] left-[20%]"
        style={{ animationDelay: '4s' }}
      />

      {/* Grid pattern */}
      <div className="absolute inset-0 grid-pattern opacity-30" />
    </div>
  );
}

// Feature card component
function FeatureCard({
  icon: Icon,
  title,
  description,
  delay = 0
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  delay?: number;
}) {
  return (
    <div
      className="feature-card group animate-fade-in-up"
      style={{ animationDelay: `${delay}ms`, animationFillMode: 'both' }}
    >
      <div className="relative z-10">
        <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-6 group-hover:scale-110 group-hover:bg-emerald-500/20 transition-all duration-300">
          <Icon className="w-7 h-7 text-emerald-400" />
        </div>
        <h3 className="text-xl font-semibold mb-3 group-hover:text-emerald-400 transition-colors">
          {title}
        </h3>
        <p className="text-muted-foreground leading-relaxed">
          {description}
        </p>
      </div>
    </div>
  );
}

// Stat card
function StatCard({ value, label, icon: Icon, loading }: { value: string; label: string; icon: React.ElementType; loading?: boolean }) {
  return (
    <div className="stat-card text-center">
      <Icon className="w-6 h-6 sm:w-8 sm:h-8 text-emerald-400 mx-auto mb-2 sm:mb-3" />
      {loading ? (
        <div className="h-9 w-20 bg-muted/50 animate-pulse rounded mx-auto mb-1" />
      ) : (
        <div className="text-2xl sm:text-3xl font-bold text-emerald-400 mb-1">{value}</div>
      )}
      <div className="text-xs sm:text-sm text-muted-foreground">{label}</div>
    </div>
  );
}

// Token preview component (Demo visualization)
function TokenPreview() {
  const [activeRisk, setActiveRisk] = useState(0);
  const risks = [
    { label: "Mint Authority", status: "safe", icon: CheckCircle2 },
    { label: "Freeze Authority", status: "safe", icon: CheckCircle2 },
    { label: "LP Locked", status: "warning", icon: AlertTriangle },
    { label: "Top 10 Holders", status: "safe", icon: CheckCircle2 },
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveRisk(prev => (prev + 1) % risks.length);
    }, 2000);
    return () => clearInterval(interval);
  }, [risks.length]);

  return (
    <div className="relative">
      <div className="glass-card p-6 rounded-2xl animate-fade-in-up" style={{ animationDelay: '400ms' }}>
        {/* Demo badge */}
        <div className="absolute -top-2 -right-2 px-2 py-1 bg-emerald-500/20 border border-emerald-500/30 rounded-full text-xs text-emerald-400 font-medium">
          Demo
        </div>
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center text-black font-bold text-lg">
              T
            </div>
            <div>
              <div className="font-semibold text-lg">Token Analysis</div>
              <div className="text-sm text-muted-foreground">Example Output</div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-emerald-400">85</div>
            <div className="text-xs text-muted-foreground">Safety Score</div>
          </div>
        </div>

        {/* Score ring */}
        <div className="relative w-32 h-32 mx-auto mb-6">
          <svg className="w-full h-full -rotate-90">
            <circle
              cx="64"
              cy="64"
              r="56"
              fill="none"
              stroke="hsl(var(--muted))"
              strokeWidth="8"
            />
            <circle
              cx="64"
              cy="64"
              r="56"
              fill="none"
              stroke="#10b981"
              strokeWidth="8"
              strokeDasharray={`${85 * 3.52} 352`}
              strokeLinecap="round"
              className="transition-all duration-1000"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <div className="text-3xl font-bold text-emerald-400">85</div>
              <div className="text-xs text-muted-foreground">SAFE</div>
            </div>
          </div>
        </div>

        {/* Risk items */}
        <div className="space-y-2">
          {risks.map((risk, i) => {
            const Icon = risk.icon;
            const isActive = i === activeRisk;
            return (
              <div
                key={risk.label}
                className={cn(
                  "flex items-center justify-between p-3 rounded-lg transition-all duration-300",
                  isActive ? "bg-emerald-500/10 border border-emerald-500/30" : "bg-white/5"
                )}
              >
                <span className="text-sm">{risk.label}</span>
                <Icon className={cn(
                  "w-5 h-5",
                  risk.status === "safe" ? "text-emerald-400" : "text-yellow-400"
                )} />
              </div>
            );
          })}
        </div>
      </div>

      {/* Decorative elements */}
      <div className="absolute -top-4 -right-4 w-24 h-24 bg-emerald-500/20 rounded-full blur-2xl" />
      <div className="absolute -bottom-4 -left-4 w-32 h-32 bg-emerald-500/10 rounded-full blur-3xl" />
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [tokenAddress, setTokenAddress] = useState("");
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const { data: statsData, isLoading: statsLoading } = useDashboardStats();

  const handleAnalyze = (e: React.FormEvent) => {
    e.preventDefault();
    if (tokenAddress.trim()) {
      router.push(`/token/${tokenAddress.trim()}`);
    }
  };

  return (
    <div className="min-h-screen relative">
      <BackgroundEffects />

      {/* Hero Section */}
      <section className="relative pt-20 pb-32 px-4">
        <div className="container mx-auto max-w-7xl">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            {/* Left column - Text */}
            <div className="space-y-8">
              {/* Badge */}
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 animate-fade-in-down">
                <Sparkles className="w-4 h-4 text-emerald-400" />
                <span className="text-sm text-emerald-400">AI-Powered Security Analysis</span>
              </div>

              {/* Headline */}
              <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold leading-tight animate-fade-in-up">
                Protect Your
                <br />
                <span className="text-emerald-400">Solana Trades</span>
              </h1>

              {/* Subheadline */}
              <p className="text-xl text-muted-foreground max-w-lg animate-fade-in-up" style={{ animationDelay: '100ms' }}>
                Advanced token security analysis powered by AI. Detect rugs, honeypots, and scams before you trade.
              </p>

              {/* Search bar */}
              <form onSubmit={handleAnalyze} className="animate-fade-in-up" style={{ animationDelay: '200ms' }}>
                <div className={cn(
                  "relative flex flex-col sm:flex-row gap-2 p-2 rounded-2xl transition-all duration-300",
                  isSearchFocused
                    ? "bg-card/80 border border-emerald-500/50 shadow-lg shadow-emerald-500/10"
                    : "bg-card/60 border border-white/10"
                )}>
                  <div className="relative flex-1">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
                    <Input
                      type="text"
                      placeholder="Enter token address..."
                      value={tokenAddress}
                      onChange={(e) => setTokenAddress(e.target.value)}
                      onFocus={() => setIsSearchFocused(true)}
                      onBlur={() => setIsSearchFocused(false)}
                      className="pl-12 h-12 sm:h-14 bg-transparent border-none text-base sm:text-lg placeholder:text-muted-foreground"
                    />
                  </div>
                  <Button
                    type="submit"
                    size="lg"
                    className="h-12 sm:h-14 px-8 bg-emerald-600 hover:bg-emerald-500 text-black font-semibold rounded-xl"
                  >
                    Analyze
                    <ArrowRight className="ml-2 w-5 h-5" />
                  </Button>
                </div>
              </form>

              {/* Trust indicators */}
              <div className="flex flex-wrap items-center gap-6 pt-4 animate-fade-in-up" style={{ animationDelay: '300ms' }}>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Free to use</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>No signup required</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Real-time analysis</span>
                </div>
              </div>
            </div>

            {/* Right column - Preview */}
            <div className="hidden lg:block">
              <TokenPreview />
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="relative py-20 px-4 border-t border-white/5">
        <div className="container mx-auto max-w-6xl">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <StatCard
              value={statsData ? statsData.total_tokens_analyzed.toLocaleString() : "0"}
              label="Tokens Analyzed"
              icon={Search}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? formatCompact(statsData.total_volume_24h) : "$0"}
              label="24h Trading Volume"
              icon={BarChart3}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? formatCompact(statsData.solana_tvl || 0) : "$0"}
              label="Solana TVL"
              icon={Activity}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? `${statsData.safe_tokens_percent.toFixed(1)}%` : "0%"}
              label="Safe Tokens"
              icon={Shield}
              loading={statsLoading}
            />
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="relative py-24 px-4">
        <div className="container mx-auto max-w-7xl">
          {/* Section header */}
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              Everything You Need to
              <br />
              <span className="text-gradient">Trade Safely</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Comprehensive security analysis tools designed for the Solana ecosystem
            </p>
          </div>

          {/* Features grid */}
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            <FeatureCard
              icon={Shield}
              title="Security Analysis"
              description="Deep analysis of token contracts, mint authorities, freeze functions, and ownership patterns to identify potential risks."
              delay={0}
            />
            <FeatureCard
              icon={Eye}
              title="Honeypot Detection"
              description="Simulate trades to detect honeypots, high taxes, and other mechanisms that could prevent you from selling."
              delay={100}
            />
            <FeatureCard
              icon={BarChart3}
              title="Holder Analysis"
              description="Visualize token distribution, identify whale wallets, and track insider accumulation patterns."
              delay={200}
            />
            <FeatureCard
              icon={Zap}
              title="AI Insights"
              description="GPT-4 powered analysis provides human-readable explanations and trading recommendations."
              delay={300}
            />
            <FeatureCard
              icon={TrendingUp}
              title="Market Data"
              description="Real-time price, volume, liquidity, and market cap data from DexScreener and on-chain sources."
              delay={400}
            />
            <FeatureCard
              icon={Lock}
              title="LP Analysis"
              description="Verify liquidity pool locks, analyze LP distribution, and detect potential rug pull setups."
              delay={500}
            />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="relative py-24 px-4 bg-card/30">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              How It Works
            </h2>
            <p className="text-lg text-muted-foreground">
              Get comprehensive token analysis in seconds
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                step: "01",
                title: "Paste Address",
                description: "Enter any Solana token address or search by name"
              },
              {
                step: "02",
                title: "AI Analysis",
                description: "Our AI analyzes 50+ security factors in real-time"
              },
              {
                step: "03",
                title: "Get Results",
                description: "Receive a detailed safety score and recommendations"
              }
            ].map((item, i) => (
              <div key={i} className="relative text-center group">
                <div className="text-6xl font-bold text-emerald-500/20 mb-4 group-hover:text-emerald-500/40 transition-colors">
                  {item.step}
                </div>
                <h3 className="text-xl font-semibold mb-2">{item.title}</h3>
                <p className="text-muted-foreground">{item.description}</p>
                {i < 2 && (
                  <ChevronRight className="hidden md:block absolute top-8 -right-4 w-8 h-8 text-emerald-500/30" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative py-24 px-4">
        <div className="container mx-auto max-w-4xl">
          <div className="relative glass-card text-center p-12 md:p-16 overflow-hidden">
            {/* Background glow */}
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 to-transparent" />
            <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/20 rounded-full blur-3xl" />

            <div className="relative z-10">
              <h2 className="text-4xl md:text-5xl font-bold mb-6">
                Ready to Trade
                <span className="text-gradient"> Safely?</span>
              </h2>
              <p className="text-lg text-muted-foreground mb-8 max-w-2xl mx-auto">
                Join thousands of traders who use Ilyon AI to protect their investments on Solana.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <Link href="/trending">
                  <Button size="lg" className="h-14 px-8 bg-emerald-600 hover:bg-emerald-500 text-black font-semibold">
                    <TrendingUp className="mr-2 w-5 h-5" />
                    Explore Trending
                  </Button>
                </Link>
                <Link href="/whales">
                  <Button size="lg" variant="outline" className="h-14 px-8">
                    <Activity className="mr-2 w-5 h-5" />
                    Track Whales
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

    </div>
  );
}
