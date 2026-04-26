"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Sparkles,
  ArrowRight,
  CheckCircle2,
  Search,
  TrendingUp,
  Shield,
  BarChart3,
  Activity,
  MessageSquare,
  ChevronRight,
} from "lucide-react";
import { useDashboardStats } from "@/lib/hooks";
import { formatCompact } from "@/lib/utils";
import { ChatPreview } from "@/components/landing/chat-preview";
import { ReasoningVisualization } from "@/components/landing/reasoning-viz";
import { QuickSearch } from "@/components/landing/quick-search";

// Animated background orbs
function BackgroundEffects() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      <div className="hero-glow top-[-200px] left-1/2 -translate-x-1/2" />
      <div className="hero-orb w-[400px] h-[400px] top-[10%] left-[10%]" style={{ animationDelay: "0s" }} />
      <div className="hero-orb w-[300px] h-[300px] top-[60%] right-[5%]" style={{ animationDelay: "2s" }} />
      <div className="hero-orb w-[200px] h-[200px] bottom-[20%] left-[20%]" style={{ animationDelay: "4s" }} />
      <div className="absolute inset-0 grid-pattern opacity-30" />
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

export default function HomePage() {
  const { data: statsData, isLoading: statsLoading } = useDashboardStats();

  return (
    <div className="relative">
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
                <span className="text-sm text-emerald-400">AI-Powered DeFi Assistant</span>
              </div>

              {/* Headline */}
              <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold leading-tight animate-fade-in-up">
                Your Intelligent
                <br />
                Crypto Trading
                <br />
                <span className="text-emerald-400">AI Assistant</span>
              </h1>

              {/* Subheadline */}
              <p className="text-xl text-muted-foreground max-w-lg animate-fade-in-up" style={{ animationDelay: "100ms" }}>
                Connect your wallet and trade with confidence. Ask anything in natural language — check balances, find best swap routes, track portfolios, bridge across chains, and get real-time market analysis.
              </p>

              {/* CTAs */}
              <div className="flex flex-col sm:flex-row items-start gap-4 animate-fade-in-up" style={{ animationDelay: "200ms" }}>
                <Link href="/agent/chat">
                  <Button size="lg" className="h-14 px-8 bg-emerald-600 hover:bg-emerald-500 text-black font-semibold rounded-xl">
                    <MessageSquare className="mr-2 w-5 h-5" />
                    Open AI Chat
                  </Button>
                </Link>
                <Button
                  size="lg"
                  variant="outline"
                  className="h-14 px-8"
                  onClick={() => document.getElementById("reasoning-viz")?.scrollIntoView({ behavior: "smooth" })}
                >
                  Try Demo Query
                  <ArrowRight className="ml-2 w-5 h-5" />
                </Button>
              </div>

              {/* Trust indicators */}
              <div className="flex flex-wrap items-center gap-6 pt-4 animate-fade-in-up" style={{ animationDelay: "300ms" }}>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>AI-Powered Trading</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Multi-Chain Support</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Non-Custodial Security</span>
                </div>
              </div>
            </div>

            {/* Right column - Chat Preview */}
            <div className="hidden lg:block">
              <ChatPreview />
            </div>
          </div>
        </div>
      </section>

      {/* Reasoning Visualization Section */}
      <section id="reasoning-viz" className="relative py-24 px-4 bg-card/30">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              See How Your AI
              <span className="text-gradient"> Thinks</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Every request triggers a chain of intelligent decisions
            </p>
          </div>

          <ReasoningVisualization />
        </div>
      </section>

      {/* Quick Search Strip */}
      <section className="relative py-16 px-4 border-t border-white/5">
        <div className="container mx-auto max-w-4xl">
          <div className="flex flex-col md:flex-row items-center gap-6">
            <div className="flex items-center gap-3 shrink-0">
              <Search className="w-5 h-5 text-emerald-400" />
              <span className="text-lg font-semibold">Analyze Any Token or Pool</span>
            </div>
            <div className="flex-1 w-full">
              <QuickSearch />
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="relative py-24 px-4">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              How It Works
            </h2>
            <p className="text-lg text-muted-foreground">
              Get started with AI-powered trading in three simple steps
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                step: "01",
                icon: "🔗",
                title: "Connect Wallet",
                description: "Link Phantom or MetaMask. We support Solana + major EVM networks in one app.",
              },
              {
                step: "02",
                icon: "💬",
                title: "Ask the AI",
                description: 'Type naturally: "Swap 0.5 SOL to USDC at best rate" or "What\'s my portfolio worth today?"',
              },
              {
                step: "03",
                icon: "⚡",
                title: "Execute Instantly",
                description: "Confirm the AI-generated transaction with one click. Fast, transparent, non-custodial.",
              },
            ].map((item, i) => (
              <div key={i} className="relative text-center group">
                <div className="text-6xl font-bold text-emerald-500/20 mb-4 group-hover:text-emerald-500/40 transition-colors">
                  {item.step}
                </div>
                <div className="text-3xl mb-3">{item.icon}</div>
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

      {/* Stats Section */}
      <section className="relative py-20 px-4 border-t border-white/5">
        <div className="container mx-auto max-w-6xl">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <StatCard
              value={statsData ? (statsData.total_tokens_analyzed ?? 0).toLocaleString() : "0"}
              label="Tokens Analyzed"
              icon={Search}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? formatCompact(statsData.total_volume_24h ?? 0) : "$0"}
              label="24h Trading Volume"
              icon={BarChart3}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? formatCompact(statsData.solana_tvl ?? 0) : "$0"}
              label="Multi-Chain TVL"
              icon={Activity}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? `${(statsData.safe_tokens_percent ?? 0).toFixed(1)}%` : "0%"}
              label="Safe Tokens"
              icon={Shield}
              loading={statsLoading}
            />
          </div>
        </div>
      </section>

      {/* Integrations / Partners Section */}
      <section className="relative py-24 px-4 border-t border-white/5 overflow-hidden">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-6">
              <Sparkles className="w-4 h-4 text-emerald-400" />
              <span className="text-sm text-emerald-400">Integrations</span>
            </div>
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              Powered by the Best
              <span className="text-gradient"> Protocols</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Seamlessly integrated with 15+ industry-leading protocols
            </p>
          </div>
        </div>

        {/* Infinite Scroll Marquee */}
        <div className="relative">
          {/* Gradient masks for fade effect */}
          <div className="absolute left-0 top-0 bottom-0 w-32 bg-gradient-to-r from-background to-transparent z-10 pointer-events-none" />
          <div className="absolute right-0 top-0 bottom-0 w-32 bg-gradient-to-l from-background to-transparent z-10 pointer-events-none" />
          
          {/* Row 1 - Scrolls Left */}
          <div className="flex overflow-hidden mb-6">
            <div className="flex animate-marquee-left gap-6 py-2">
              {[...Array(2)].map((_, dupIndex) => (
                <React.Fragment key={dupIndex}>
                  {[
                    { name: "Jupiter", logo: "/logos/jupiter.svg", bg: "#11131F" },
                    { name: "Enso", logo: "/logos/enso.svg", bg: "#1a1a1a" },
                    { name: "1inch", logo: "/logos/1inch.svg", bg: "#08272A" },
                    { name: "deBridge", logo: "/logos/debridge.svg", bg: "#0a0a0a" },
                    { name: "DefiLlama", logo: "/logos/defillama.svg", bg: "#1a1a1a" },
                    { name: "CoinGecko", logo: "/logos/coingecko.svg", bg: "#1a1a1a" },
                    { name: "Binance", logo: "/logos/binance.svg", bg: "#0B0E11" },
                    { name: "Moralis", logo: "/logos/moralis.svg", bg: "#1a1a1a" },
                  ].map((item) => (
                    <div
                      key={`${dupIndex}-${item.name}`}
                      className="flex-shrink-0 w-48 h-24 rounded-xl border border-white/10 bg-white/[0.02] backdrop-blur-sm flex items-center justify-center gap-3 px-4 hover:border-emerald-500/30 hover:bg-white/[0.04] transition-all duration-300 group"
                    >
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center overflow-hidden" style={{ backgroundColor: item.bg }}>
                        <img
                          src={item.logo}
                          alt={item.name}
                          className="w-7 h-7 object-contain opacity-70 group-hover:opacity-100 transition-opacity"
                          onError={(e) => {
                            const target = e.target as HTMLImageElement;
                            target.style.display = 'none';
                            target.parentElement!.innerHTML = `<span class="text-lg font-bold text-emerald-400">${item.name[0]}</span>`;
                          }}
                        />
                      </div>
                      <span className="text-sm font-semibold text-white/80 group-hover:text-white transition-colors">{item.name}</span>
                    </div>
                  ))}
                </React.Fragment>
              ))}
            </div>
          </div>

          {/* Row 2 - Scrolls Right */}
          <div className="flex overflow-hidden">
            <div className="flex animate-marquee-right gap-6 py-2">
              {[...Array(2)].map((_, dupIndex) => (
                <React.Fragment key={dupIndex}>
                  {[
                    { name: "Helius", logo: "/logos/helius.svg", bg: "#0a0a0a" },
                    { name: "DexScreener", logo: "/logos/dexscreener.svg", bg: "#0f172a" },
                    { name: "OpenRouter", logo: "/logos/openrouter.svg", bg: "#1a1a1a" },
                    { name: "Gemini", logo: "/logos/gemini.svg", bg: "#1a1a1a" },
                    { name: "Grok", logo: "/logos/grok.svg", bg: "#0a0a0a" },
                    { name: "Phantom", logo: "/logos/phantom.svg", bg: "#1a1a1a" },
                    { name: "MetaMask", logo: "/logos/metamask.svg", bg: "#1a1a1a" },
                  ].map((item) => (
                    <div
                      key={`${dupIndex}-${item.name}`}
                      className="flex-shrink-0 w-48 h-24 rounded-xl border border-white/10 bg-white/[0.02] backdrop-blur-sm flex items-center justify-center gap-3 px-4 hover:border-emerald-500/30 hover:bg-white/[0.04] transition-all duration-300 group"
                    >
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center overflow-hidden" style={{ backgroundColor: item.bg }}>
                        <img
                          src={item.logo}
                          alt={item.name}
                          className="w-7 h-7 object-contain opacity-70 group-hover:opacity-100 transition-opacity"
                          onError={(e) => {
                            const target = e.target as HTMLImageElement;
                            target.style.display = 'none';
                            target.parentElement!.innerHTML = `<span class="text-lg font-bold text-emerald-400">${item.name[0]}</span>`;
                          }}
                        />
                      </div>
                      <span className="text-sm font-semibold text-white/80 group-hover:text-white transition-colors">{item.name}</span>
                    </div>
                  ))}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>

        {/* Static Grid for Mobile */}
        <div className="container mx-auto max-w-6xl mt-16 md:hidden">
          <div className="grid grid-cols-2 gap-3">
            {[
              { name: "Jupiter", logo: "/logos/jupiter.svg" },
              { name: "Enso", logo: "/logos/enso.svg" },
              { name: "1inch", logo: "/logos/1inch.svg" },
              { name: "deBridge", logo: "/logos/debridge.svg" },
              { name: "DefiLlama", logo: "/logos/defillama.svg" },
              { name: "CoinGecko", logo: "/logos/coingecko.svg" },
              { name: "Binance", logo: "/logos/binance.svg" },
              { name: "Moralis", logo: "/logos/moralis.svg" },
              { name: "Helius", logo: "/logos/helius.svg" },
              { name: "DexScreener", logo: "/logos/dexscreener.svg" },
              { name: "OpenRouter", logo: "/logos/openrouter.svg" },
              { name: "Gemini", logo: "/logos/gemini.svg" },
              { name: "Grok", logo: "/logos/grok.svg" },
              { name: "Phantom", logo: "/logos/phantom.svg" },
              { name: "MetaMask", logo: "/logos/metamask.svg" },
            ].map((item) => (
              <div
                key={item.name}
                className="flex items-center gap-3 p-4 rounded-xl border border-white/10 bg-white/[0.02]"
              >
                <div className="w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center overflow-hidden flex-shrink-0">
                  <img
                    src={item.logo}
                    alt={item.name}
                    className="w-7 h-7 object-contain opacity-80"
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      target.style.display = 'none';
                      target.parentElement!.innerHTML = `<span class="text-lg font-bold text-emerald-400">${item.name[0]}</span>`;
                    }}
                  />
                </div>
                <span className="text-sm font-medium text-white/80">{item.name}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative py-24 px-4">
        <div className="container mx-auto max-w-4xl">
          <div className="relative glass-card text-center p-12 md:p-16 overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 to-transparent" />
            <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/20 rounded-full blur-3xl" />

            <div className="relative z-10">
              <h2 className="text-4xl md:text-5xl font-bold mb-6">
                Ready to Trade
                <span className="text-gradient"> Smarter?</span>
              </h2>
              <p className="text-lg text-muted-foreground mb-8 max-w-2xl mx-auto">
                Let AI handle the complexity. You just say what you want.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <Link href="/agent/chat">
                  <Button size="lg" className="h-14 px-8 bg-emerald-600 hover:bg-emerald-500 text-black font-semibold">
                    <MessageSquare className="mr-2 w-5 h-5" />
                    Open AI Chat
                  </Button>
                </Link>
                <Link href="/trending">
                  <Button size="lg" variant="outline" className="h-14 px-8">
                    <TrendingUp className="mr-2 w-5 h-5" />
                    View Trending
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
