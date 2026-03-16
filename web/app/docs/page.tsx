"use client";

import Link from "next/link";
import { GlassCard } from "@/components/ui/card";
import {
  Shield,
  Search,
  TrendingUp,
  Zap,
  Eye,
  BarChart3,
  Lock,
  Wallet,
  Fish,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  BookOpen,
  Code,
  Globe,
  MessageCircle,
  ExternalLink,
  Layers,
  HelpCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";

function SectionAnchor({ id }: { id: string }) {
  return <div id={id} className="scroll-mt-24" />;
}

const sidebarSections = [
  { id: "getting-started", label: "Getting Started" },
  { id: "token-analysis", label: "Token Analysis" },
  { id: "pool-analysis", label: "Pool Analysis" },
  { id: "risk-framework", label: "Risk Framework" },
  { id: "security-checks", label: "Security Checks" },
  { id: "ai-insights", label: "AI Insights" },
  { id: "trending", label: "Trending Tokens" },
  { id: "whale-tracking", label: "Whale Tracking" },
  { id: "portfolio", label: "Portfolio" },
  { id: "wallet-connect", label: "Wallet Connection" },
  { id: "blinks", label: "Solana Blinks" },
  { id: "api", label: "API Reference" },
  { id: "faq", label: "FAQ" },
];

export default function DocsPage() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      <div className="flex gap-8">
        {/* Sidebar Navigation */}
        <aside className="hidden lg:block w-64 shrink-0">
          <div className="sticky top-24">
            <div className="flex items-center gap-2 mb-6">
              <BookOpen className="h-5 w-5 text-emerald-500" />
              <h2 className="font-semibold text-lg">Documentation</h2>
            </div>
            <nav className="space-y-1">
              {sidebarSections.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="block px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-card/50 rounded-lg transition"
                >
                  {section.label}
                </a>
              ))}
            </nav>

            <div className="mt-8 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <p className="text-sm text-emerald-400 font-medium mb-2">Need help?</p>
              <p className="text-xs text-muted-foreground mb-3">
                Join our community for support and updates.
              </p>
              <div className="flex flex-col gap-2">
                <a
                  href="https://t.me/ilyonProtocol"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition"
                >
                  <MessageCircle className="h-3 w-3" />
                  Telegram
                </a>
                <a
                  href="https://x.com/ilyonProtocol"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition"
                >
                  <Globe className="h-3 w-3" />
                  @ilyonProtocol
                </a>
              </div>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 min-w-0 max-w-4xl">
          {/* Header */}
          <div className="mb-12">
            <h1 className="text-4xl font-bold mb-4">Ilyon AI Documentation</h1>
            <p className="text-lg text-muted-foreground">
              Everything you need to know about using Ilyon AI to protect your multi-chain token trades and DeFi liquidity deployments.
            </p>
          </div>

          {/* Getting Started */}
          <SectionAnchor id="getting-started" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Zap className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Getting Started</h2>
            </div>
            <p className="text-muted-foreground mb-6">
              Ilyon AI is an AI-powered intelligence platform for Solana and major EVM ecosystems. It helps you identify risky tokens and evaluate DeFi pool opportunities from a single, unified search interface.
            </p>

            <h3 className="font-semibold text-lg mb-3">Quick Start</h3>
            <div className="space-y-4 mb-6">
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center text-sm font-bold text-emerald-400">
                  1
                </div>
                <div>
                  <div className="font-medium">Navigate to the homepage</div>
                  <p className="text-sm text-muted-foreground">
                    Visit the main page where you&apos;ll find the unified search bar.
                  </p>
                </div>
              </div>
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center text-sm font-bold text-emerald-400">
                  2
                </div>
                <div>
                  <div className="font-medium">Search for anything</div>
                  <p className="text-sm text-muted-foreground">
                    Paste a token address, type a pool name (e.g. &quot;USDT-WBNB PancakeSwap&quot;), or enter a DEX pair address. The search supports Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche.
                  </p>
                </div>
              </div>
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center text-sm font-bold text-emerald-400">
                  3
                </div>
                <div>
                  <div className="font-medium">Review the analysis</div>
                  <p className="text-sm text-muted-foreground">
                    Within seconds, you&apos;ll receive a comprehensive report. Token pages show safety checks and holder distribution; Pool pages show APR efficiency, quality, safety, and durability scores.
                  </p>
                </div>
              </div>
            </div>

            <div className="p-4 bg-emerald-500/10 rounded-lg border border-emerald-500/20">
              <p className="text-sm text-emerald-400">
                No wallet connection or signup is required to analyze tokens or pools. Connect your wallet to unlock portfolio tracking and additional features.
              </p>
            </div>
          </GlassCard>

          {/* Token Analysis */}
          <SectionAnchor id="token-analysis" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Search className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Token Analysis</h2>
            </div>
            <p className="text-muted-foreground mb-6">
              When you analyze a token, Ilyon AI performs a deep inspection across multiple dimensions to assess its safety:
            </p>

            <div className="grid md:grid-cols-2 gap-4 mb-6">
              <div className="p-4 rounded-lg bg-card/50 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="h-4 w-4 text-emerald-400" />
                  <span className="font-medium">Contract Security</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Analysis of mint authority, freeze authority, and proxy upgrades. Checks whether privileged functions are active or renounced.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-card/50 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <BarChart3 className="h-4 w-4 text-emerald-400" />
                  <span className="font-medium">Holder Distribution</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Examines the top token holders to identify centralization risks, insider clusters, and liquidity unlocks.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-card/50 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <Lock className="h-4 w-4 text-emerald-400" />
                  <span className="font-medium">Liquidity Analysis</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Checks liquidity pool depth, LP token lock status, burn percentage, and slippage estimation to gauge the exit risk.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-card/50 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <TrendingUp className="h-4 w-4 text-emerald-400" />
                  <span className="font-medium">Market Data</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Real-time price, 24h volume, market cap, and DexScreener verification to ensure the token isn&apos;t a low-volume phantom.
                </p>
              </div>
            </div>
          </GlassCard>

          {/* Pool Analysis */}
          <SectionAnchor id="pool-analysis" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Pool Analysis</h2>
            </div>
            <p className="text-muted-foreground mb-6">
              Ilyon AI evaluates DeFi liquidity pools and yield farms to answer one question: &quot;Is the APR worth the risk?&quot; 
              We map the DefiLlama database and live DEX pairs against a strict archetype-aware scoring engine.
            </p>
            <ul className="space-y-3 text-sm text-muted-foreground mb-6">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>Taxonomy:</strong> We sort pools into &quot;stable-stable&quot;, &quot;crypto-stable&quot;, &quot;crypto-crypto&quot;, and &quot;incentivized&quot; buckets so that risk evaluations are fair.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>Effective APR:</strong> Nominal APR is hair-cutted against fee instability, low liquidity, and reward-token sell pressure.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>Required Hurdle:</strong> Every pool&apos;s risk burden establishes a minimum acceptable APR. If a pool pays less than its hurdle, its score plummets.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>Scenarios:</strong> We inject historical exploit checks, dependencies (bridges/oracles), and recent TVL collapses.</span>
              </li>
            </ul>
          </GlassCard>

          {/* Risk Framework */}
          <SectionAnchor id="risk-framework" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Scores & Risk Framework</h2>
            </div>
            <p className="text-muted-foreground mb-6">
              Ilyon AI uses different scoring models depending on whether you are looking at a standalone Token or a DeFi Pool.
            </p>

            <h3 className="font-semibold text-lg mb-3">Token Safety Score</h3>
            <p className="text-sm text-muted-foreground mb-4">A simple 0-100 rating indicating how technically safe the contract is to trade.</p>
            <div className="space-y-3 mb-8">
              <div className="flex items-center gap-3 p-3 rounded-lg bg-card/50">
                <div className="w-3 h-3 rounded-full bg-emerald-500" />
                <div>
                  <span className="font-medium">80-100: Safe</span>
                  <span className="text-sm text-muted-foreground ml-2">Low technical risk. Token has passed most security checks.</span>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-card/50">
                <div className="w-3 h-3 rounded-full bg-yellow-500" />
                <div>
                  <span className="font-medium">50-79: Caution</span>
                  <span className="text-sm text-muted-foreground ml-2">Moderate risk. Some security concerns exist.</span>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-card/50">
                <div className="w-3 h-3 rounded-full bg-red-500" />
                <div>
                  <span className="font-medium">0-49: Danger</span>
                  <span className="text-sm text-muted-foreground ml-2">High risk. Multiple red flags detected or honeypot behavior.</span>
                </div>
              </div>
            </div>

            <h3 className="font-semibold text-lg mb-3">DeFi Pool Scores</h3>
            <p className="text-sm text-muted-foreground mb-4">Pools are evaluated across multiple complex dimensions:</p>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li>
                <strong className="text-foreground">Overall Score (0-100):</strong> The primary ring. Heavily influenced by APR Efficiency (is the effective yield high enough to cover the pool&apos;s specific risk burden?).
              </li>
              <li>
                <strong className="text-foreground">Pool Quality:</strong> Structural safety, history, and exit liquidity, independent of the current yield.
              </li>
              <li>
                <strong className="text-foreground">Risk Burden:</strong> A combination of IL exposure, token quality, protocol age, and dependency chains.
              </li>
              <li>
                <strong className="text-foreground">Yield Durability:</strong> Measures how much of the APR comes from organic volume versus inflationary token rewards.
              </li>
            </ul>
          </GlassCard>

          {/* Security Checks */}
          <SectionAnchor id="security-checks" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Eye className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Security Checks</h2>
            </div>
            <p className="text-muted-foreground mb-6">
              Each token analysis runs through a series of specific security checks. Here&apos;s what each check means:
            </p>

            <div className="space-y-4">
              <div className="p-4 rounded-lg border border-border/50">
                <h4 className="font-medium mb-1">Mint Authority</h4>
                <p className="text-sm text-muted-foreground">
                  Determines if new tokens can be minted. If the mint authority is active, the token creator can inflate the supply at any time, diluting existing holders. A renounced mint authority is a positive signal.
                </p>
              </div>
              <div className="p-4 rounded-lg border border-border/50">
                <h4 className="font-medium mb-1">Freeze Authority</h4>
                <p className="text-sm text-muted-foreground">
                  Checks if the token creator can freeze token accounts. An active freeze authority means your tokens could be locked at any time, preventing you from selling. This should be renounced for most legitimate tokens.
                </p>
              </div>
              <div className="p-4 rounded-lg border border-border/50">
                <h4 className="font-medium mb-1">LP Status</h4>
                <p className="text-sm text-muted-foreground">
                  Analyzes the liquidity pool. Checks if LP tokens are locked or burned. Burned LP is the most secure, followed by locked LP with a long lock duration. Unlocked LP means the creator could remove all liquidity (rug pull) at any time.
                </p>
              </div>
              <div className="p-4 rounded-lg border border-border/50">
                <h4 className="font-medium mb-1">Top Holder Analysis</h4>
                <p className="text-sm text-muted-foreground">
                  Reviews the distribution of tokens among the top 10 holders. High concentration (especially if a single non-LP wallet holds &gt;10%) can indicate insider control and potential dump risk.
                </p>
              </div>
              <div className="p-4 rounded-lg border border-border/50">
                <h4 className="font-medium mb-1">Honeypot Detection</h4>
                <p className="text-sm text-muted-foreground">
                  Simulates buy and sell transactions to detect tokens that allow purchases but block sells. This is a common scam technique where victims can buy but never sell their tokens.
                </p>
              </div>
              <div className="p-4 rounded-lg border border-border/50">
                <h4 className="font-medium mb-1">Website & Social Verification</h4>
                <p className="text-sm text-muted-foreground">
                  Checks if the token has a website, social media presence, and verifies they are active and legitimate. Tokens with no web presence are higher risk.
                </p>
              </div>
            </div>
          </GlassCard>

          {/* AI Insights */}
          <SectionAnchor id="ai-insights" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Zap className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">AI Insights</h2>
            </div>
            <p className="text-muted-foreground mb-6">
              Our backend orchestrates advanced language models to provide human-readable interpretations of on-chain data:
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground mb-6">
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>DeepSeek-v3 via OpenRouter:</strong> Powers the deep technical security reviews, protocol analysis, and pool commentary.</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>Grok 4.1 Fast:</strong> Handles Twitter integration and narrative sentiment analysis for trending tokens.</span>
              </li>
            </ul>
            <div className="p-4 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-yellow-400 mt-0.5 shrink-0" />
                <p className="text-sm text-yellow-400">
                  AI insights are informational and should not be treated as financial advice. Always do your own research (DYOR) before making trading decisions.
                </p>
              </div>
            </div>
          </GlassCard>

          {/* Trending Tokens */}
          <SectionAnchor id="trending" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Trending Tokens</h2>
            </div>
            <p className="text-muted-foreground mb-4">
              The <Link href="/trending" className="text-emerald-400 hover:underline">Trending</Link> page shows the most active tokens ranked by 24-hour volume across our supported ecosystems. Each trending token displays:
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground mb-4">
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Token name, symbol, and logo</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Current price and 24h price change</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>24-hour trading volume</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Market cap and liquidity</span>
              </li>
            </ul>
            <p className="text-sm text-muted-foreground">
              Click on any trending token to run a full security analysis. The trending list refreshes automatically.
            </p>
          </GlassCard>

          {/* Whale Tracking */}
          <SectionAnchor id="whale-tracking" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Fish className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Whale Tracking</h2>
            </div>
            <p className="text-muted-foreground mb-4">
              The <Link href="/whales" className="text-emerald-400 hover:underline">Whales</Link> page monitors massive on-chain transactions in real-time, helping you identify smart money movements or imminent dumps.
            </p>

            <h3 className="font-semibold text-lg mb-3">What Counts as a Whale Transaction?</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Transactions above a configurable USD threshold are flagged as whale activity. The default threshold captures transactions in the top percentile of trading volume.
            </p>

            <h3 className="font-semibold text-lg mb-3">Tracked Information</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Transaction type (buy/sell), token, and amount</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>USD value of the transaction</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Wallet address with explorer link</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Timestamp and transaction signature</span>
              </li>
            </ul>
          </GlassCard>

          {/* Portfolio */}
          <SectionAnchor id="portfolio" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Wallet className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Portfolio</h2>
            </div>
            <p className="text-muted-foreground mb-4">
              The <Link href="/portfolio" className="text-emerald-400 hover:underline">Portfolio</Link> page provides a security overview of the tokens in your connected wallet. After connecting your wallet, you can:
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground mb-4">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>View all tokens held in your wallet with their current values</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>See safety scores for each token at a glance</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Identify high-risk tokens in your holdings</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Click through to full analysis for any token</span>
              </li>
            </ul>
            <div className="p-4 bg-card/50 rounded-lg border border-border/50">
              <p className="text-sm text-muted-foreground">
                Portfolio tracking requires a wallet connection. Your wallet data is read-only — Ilyon AI never requests transaction signing permissions for portfolio viewing.
              </p>
            </div>
          </GlassCard>

          {/* Wallet Connection */}
          <SectionAnchor id="wallet-connect" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Wallet className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Wallet Connection</h2>
            </div>
            <p className="text-muted-foreground mb-4">
              Ilyon AI supports major Solana wallets through the standard Wallet Adapter:
            </p>
            <div className="grid sm:grid-cols-2 gap-3 mb-6">
              {["Phantom", "Solflare", "Backpack", "Ledger"].map((wallet) => (
                <div key={wallet} className="flex items-center gap-2 p-3 rounded-lg bg-card/50 border border-border/50">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span className="text-sm">{wallet}</span>
                </div>
              ))}
            </div>

            <h3 className="font-semibold text-lg mb-3">Authentication</h3>
            <p className="text-sm text-muted-foreground mb-4">
              For premium features and persistent settings, you can authenticate by signing a message with your wallet. This proves wallet ownership without any on-chain transaction or gas fee.
            </p>

            <h3 className="font-semibold text-lg mb-3">Privacy</h3>
            <p className="text-sm text-muted-foreground">
              Ilyon AI only reads your public wallet data (token balances, transaction history). We never request permissions to sign transactions or transfer tokens on your behalf.
            </p>
          </GlassCard>

          {/* Blinks */}
          <SectionAnchor id="blinks" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Globe className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Solana Blinks</h2>
            </div>
            <p className="text-muted-foreground mb-4">
              Ilyon AI supports Solana Blinks (Blockchain Links) — shareable, interactive cards that let anyone view a token&apos;s security analysis directly from a link on supported platforms like Twitter/X.
            </p>

            <h3 className="font-semibold text-lg mb-3">How Blinks Work</h3>
            <ul className="space-y-2 text-sm text-muted-foreground mb-4">
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>After analyzing a Solana token, you can generate a shareable Blink URL</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>The Blink contains a snapshot of the token&apos;s safety score and key metrics</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Share the Blink on X, Telegram, or any supported client</span>
              </li>
            </ul>
            <p className="text-sm text-muted-foreground">
              Blinks follow the Solana Actions specification. Note that blinks are native to the Solana ecosystem and are not used for EVM chains.
            </p>
          </GlassCard>

          {/* API Reference */}
          <SectionAnchor id="api" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Code className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">API Reference</h2>
            </div>
            <p className="text-muted-foreground mb-6">
              Ilyon AI exposes a REST API for programmatic access to intelligence. All endpoints are under the <code className="px-1.5 py-0.5 rounded bg-card text-sm font-mono">/api/v1</code> path.
            </p>

            <div className="space-y-4">
              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 text-xs font-mono font-bold">GET</span>
                  <code className="text-sm font-mono">/api/v1/search</code>
                </div>
                <p className="text-sm text-muted-foreground mb-2">
                  Unified search returning both matching tokens and matched liquidity pools across all supported chains.
                </p>
              </div>

              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-xs font-mono font-bold">POST</span>
                  <code className="text-sm font-mono">/api/v1/analyze</code>
                </div>
                <p className="text-sm text-muted-foreground mb-2">
                  Analyze a token by address. Returns technical checks and AI security breakdown.
                </p>
              </div>
              
              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-xs font-mono font-bold">POST</span>
                  <code className="text-sm font-mono">/api/v1/defi/pool/analyze</code>
                </div>
                <p className="text-sm text-muted-foreground mb-2">
                  Deep analysis of a DeFi LP pool or farm, including APR efficiency and risk burden scaling.
                </p>
              </div>

              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 text-xs font-mono font-bold">GET</span>
                  <code className="text-sm font-mono">/api/v1/whales</code>
                </div>
                <p className="text-sm text-muted-foreground">
                  Returns recent massive volume transactions (whale activity).
                </p>
              </div>
            </div>
          </GlassCard>

          {/* FAQ */}
          <SectionAnchor id="faq" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <HelpCircle className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">FAQ</h2>
            </div>

            <div className="space-y-6">
              <div>
                <h4 className="font-medium mb-2">Is Ilyon AI free to use?</h4>
                <p className="text-sm text-muted-foreground">
                  Yes. Token and pool analysis are free and do not require a wallet connection. Advanced features like portfolio/wallet tracking require a standard Web3 wallet connection.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">Which chains are supported?</h4>
                <p className="text-sm text-muted-foreground">
                  Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">Why does a safe pool have a low overall score?</h4>
                <p className="text-sm text-muted-foreground">
                  Our system grades pools based on the efficiency of their APR relative to their structural risk. A very safe pool that offers effectively 0% APR will score low overall, because the capital deployment is considered inefficient. You can always see its &quot;Pool Quality&quot; score separately to confirm it is structurally sound.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">How accurate is the token safety score?</h4>
                <p className="text-sm text-muted-foreground">
                  The safety score is based on verifiable on-chain factors and is designed to catch the most common scam patterns. However, no automated tool can guarantee 100% accuracy. Always combine our analysis with your own research.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">How can I report a false positive or missing scam?</h4>
                <p className="text-sm text-muted-foreground">
                  Reach out to us on{" "}
                  <a
                    href="https://t.me/ilyonProtocol"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-emerald-400 hover:underline"
                  >
                    Telegram
                  </a>{" "}
                  or{" "}
                  <a
                    href="https://x.com/ilyonProtocol"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-emerald-400 hover:underline"
                  >
                    Twitter
                  </a>.
                </p>
              </div>
            </div>
          </GlassCard>

          {/* CTA */}
          <div className="text-center py-8">
            <p className="text-muted-foreground mb-4">
              Ready to start analyzing?
            </p>
            <Link href="/">
              <Button size="lg" className="bg-emerald-600 hover:bg-emerald-500 text-black font-semibold">
                <Search className="mr-2 w-5 h-5" />
                Go to Search
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
