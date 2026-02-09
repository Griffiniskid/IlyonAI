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
  HelpCircle,
  MessageCircle,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function SectionAnchor({ id }: { id: string }) {
  return <div id={id} className="scroll-mt-24" />;
}

const sidebarSections = [
  { id: "getting-started", label: "Getting Started" },
  { id: "token-analysis", label: "Token Analysis" },
  { id: "safety-score", label: "Safety Score" },
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
              Everything you need to know about using Ilyon AI to protect your Solana trades.
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
              Ilyon AI is an AI-powered security analysis platform for the Solana ecosystem. It helps you identify risky tokens before you trade by analyzing smart contracts, holder distribution, liquidity, and more.
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
                    Visit the main page where you&apos;ll find the token search bar.
                  </p>
                </div>
              </div>
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center text-sm font-bold text-emerald-400">
                  2
                </div>
                <div>
                  <div className="font-medium">Paste a Solana token address</div>
                  <p className="text-sm text-muted-foreground">
                    Enter any SPL token mint address into the search field. You can find token addresses on DEX platforms like Jupiter, Raydium, or from block explorers like Solscan.
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
                    Within seconds, you&apos;ll receive a comprehensive safety report including a security score, risk factors, holder analysis, and AI-generated insights.
                  </p>
                </div>
              </div>
            </div>

            <div className="p-4 bg-emerald-500/10 rounded-lg border border-emerald-500/20">
              <p className="text-sm text-emerald-400">
                No wallet connection or signup is required to analyze tokens. Connect your wallet to unlock portfolio tracking and additional features.
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
              When you analyze a token, Ilyon AI performs a deep inspection across multiple dimensions to assess its safety. The analysis covers:
            </p>

            <div className="grid md:grid-cols-2 gap-4 mb-6">
              <div className="p-4 rounded-lg bg-card/50 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="h-4 w-4 text-emerald-400" />
                  <span className="font-medium">Contract Security</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Analysis of mint authority, freeze authority, and update authority states. Checks whether these privileged functions are active or renounced.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-card/50 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <BarChart3 className="h-4 w-4 text-emerald-400" />
                  <span className="font-medium">Holder Distribution</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Examines the top token holders, their percentages, and identifies potential concentration risks or insider wallets.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-card/50 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <Lock className="h-4 w-4 text-emerald-400" />
                  <span className="font-medium">Liquidity Analysis</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Checks liquidity pool size, LP token lock status, burn status, and liquidity-to-market-cap ratio.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-card/50 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <TrendingUp className="h-4 w-4 text-emerald-400" />
                  <span className="font-medium">Market Data</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Real-time price, 24h volume, market cap, price changes, and trading activity from DexScreener and on-chain sources.
                </p>
              </div>
            </div>

            <h3 className="font-semibold text-lg mb-3">Analysis Sources</h3>
            <p className="text-sm text-muted-foreground">
              Data is aggregated from multiple on-chain and off-chain sources including Solana RPC nodes, DexScreener, Solscan, and proprietary analysis engines to provide the most accurate and up-to-date information.
            </p>
          </GlassCard>

          {/* Safety Score */}
          <SectionAnchor id="safety-score" />
          <GlassCard className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="h-5 w-5 text-emerald-500" />
              <h2 className="text-2xl font-bold">Safety Score</h2>
            </div>
            <p className="text-muted-foreground mb-6">
              Every analyzed token receives a safety score from 0 to 100. This score is a weighted composite of multiple risk factors designed to give you a quick overview of the token&apos;s safety.
            </p>

            <h3 className="font-semibold text-lg mb-3">Score Ranges</h3>
            <div className="space-y-3 mb-6">
              <div className="flex items-center gap-3 p-3 rounded-lg bg-card/50">
                <div className="w-3 h-3 rounded-full bg-emerald-500" />
                <div>
                  <span className="font-medium">80-100: Safe</span>
                  <span className="text-sm text-muted-foreground ml-2">Low risk. Token has passed most security checks and shows healthy distribution.</span>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-card/50">
                <div className="w-3 h-3 rounded-full bg-yellow-500" />
                <div>
                  <span className="font-medium">50-79: Caution</span>
                  <span className="text-sm text-muted-foreground ml-2">Moderate risk. Some security concerns exist. Review the detailed analysis before trading.</span>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-card/50">
                <div className="w-3 h-3 rounded-full bg-orange-500" />
                <div>
                  <span className="font-medium">25-49: Warning</span>
                  <span className="text-sm text-muted-foreground ml-2">High risk. Multiple red flags detected. Exercise extreme caution.</span>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-card/50">
                <div className="w-3 h-3 rounded-full bg-red-500" />
                <div>
                  <span className="font-medium">0-24: Danger</span>
                  <span className="text-sm text-muted-foreground ml-2">Very high risk. Strong indicators of a scam, rug pull, or honeypot.</span>
                </div>
              </div>
            </div>

            <h3 className="font-semibold text-lg mb-3">Score Factors</h3>
            <p className="text-sm text-muted-foreground mb-4">
              The safety score is computed from 50+ weighted factors including:
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Mint authority status (renounced vs. active)</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Freeze authority status</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>LP lock/burn percentage and duration</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Top holder concentration (&gt;50% in a single wallet is a red flag)</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Liquidity depth relative to market cap</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Token age and trading history</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Social presence and website verification</span>
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
              Each analysis includes AI-generated insights that provide a human-readable interpretation of the raw data. Powered by advanced language models, these insights help you understand:
            </p>
            <ul className="space-y-2 text-sm text-muted-foreground mb-6">
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>A plain-English summary of the token&apos;s safety profile</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Key risk factors explained in context</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Comparison against common scam patterns</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Actionable trading recommendations</span>
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
              The <Link href="/trending" className="text-emerald-400 hover:underline">Trending</Link> page shows the most active tokens on Solana ranked by 24-hour trading volume. Each trending token displays:
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
              Click on any trending token to run a full security analysis. The trending list refreshes automatically to keep data current.
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
              The <Link href="/whales" className="text-emerald-400 hover:underline">Whales</Link> page monitors large transactions on Solana in real-time. Whale activity can be a leading indicator of significant price movements.
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
                <span>Wallet address with link to Solscan</span>
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
              The <Link href="/portfolio" className="text-emerald-400 hover:underline">Portfolio</Link> page provides a security overview of the tokens in your connected wallet. After connecting your Solana wallet, you can:
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
              Ilyon AI supports all major Solana wallets through the Solana Wallet Adapter standard:
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
              For premium features, you can authenticate by signing a message with your wallet. This proves wallet ownership without any on-chain transaction or gas fee. Your session remains active until you sign out.
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
              Ilyon AI supports Solana Blinks (Blockchain Links) — shareable, interactive cards that let anyone view a token&apos;s security analysis directly from a link.
            </p>

            <h3 className="font-semibold text-lg mb-3">How Blinks Work</h3>
            <ul className="space-y-2 text-sm text-muted-foreground mb-4">
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>After analyzing a token, click &quot;Create Blink&quot; to generate a shareable link</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>The Blink contains a snapshot of the token&apos;s safety score and key metrics</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Share the Blink on Twitter, Telegram, or any platform</span>
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span>Recipients can view the analysis and interact with it directly</span>
              </li>
            </ul>
            <p className="text-sm text-muted-foreground">
              Blinks follow the Solana Actions specification, making them compatible with wallets and platforms that support the standard.
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
              Ilyon AI exposes a REST API for programmatic access to token analysis. All endpoints are available under the <code className="px-1.5 py-0.5 rounded bg-card text-sm font-mono">/api/v1</code> base path.
            </p>

            <div className="space-y-4">
              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-xs font-mono font-bold">POST</span>
                  <code className="text-sm font-mono">/api/v1/analyze</code>
                </div>
                <p className="text-sm text-muted-foreground mb-2">
                  Analyze a token by its mint address. Returns a full security report.
                </p>
                <div className="bg-card/80 rounded p-3 font-mono text-xs text-muted-foreground overflow-x-auto">
                  <pre>{`{
  "token_address": "So11111111111111111111111111111111111111112"
}`}</pre>
                </div>
              </div>

              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 text-xs font-mono font-bold">GET</span>
                  <code className="text-sm font-mono">/api/v1/trending</code>
                </div>
                <p className="text-sm text-muted-foreground">
                  Returns the current list of trending tokens with price and volume data.
                </p>
              </div>

              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 text-xs font-mono font-bold">GET</span>
                  <code className="text-sm font-mono">/api/v1/whales</code>
                </div>
                <p className="text-sm text-muted-foreground">
                  Returns recent whale transactions on Solana.
                </p>
              </div>

              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 text-xs font-mono font-bold">GET</span>
                  <code className="text-sm font-mono">/api/v1/stats</code>
                </div>
                <p className="text-sm text-muted-foreground">
                  Returns platform statistics including total tokens analyzed, volume, and active token counts.
                </p>
              </div>

              <div className="p-4 rounded-lg border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-xs font-mono font-bold">POST</span>
                  <code className="text-sm font-mono">/api/v1/blinks</code>
                </div>
                <p className="text-sm text-muted-foreground">
                  Create a Solana Blink for a token analysis. Requires authentication.
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
                  Yes. Token analysis is free and does not require a wallet connection or account. Some advanced features like portfolio tracking require connecting a wallet.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">How accurate is the safety score?</h4>
                <p className="text-sm text-muted-foreground">
                  The safety score is based on 50+ verifiable on-chain factors and is designed to catch the most common scam patterns. However, no automated tool can guarantee 100% accuracy. New scam techniques may not be immediately detected. Always combine our analysis with your own research.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">Can a &quot;safe&quot; token still lose value?</h4>
                <p className="text-sm text-muted-foreground">
                  Absolutely. The safety score measures technical security factors (rug pull risk, honeypot risk, etc.), not market performance. A token can be technically safe but still lose value due to market conditions, lack of demand, or other factors.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">Which Solana tokens can be analyzed?</h4>
                <p className="text-sm text-muted-foreground">
                  Any SPL token with at least one active liquidity pool can be analyzed. Tokens without liquidity pools may return limited data.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">How often is data refreshed?</h4>
                <p className="text-sm text-muted-foreground">
                  Market data (price, volume) is fetched in real-time. On-chain security data is cached for a short period to optimize performance. You can force a refresh by clicking the refresh button on any token analysis page.
                </p>
              </div>

              <div>
                <h4 className="font-medium mb-2">Is my wallet safe when connecting?</h4>
                <p className="text-sm text-muted-foreground">
                  Yes. Ilyon AI only reads public wallet data. We use the standard Solana Wallet Adapter which never exposes your private keys. Authentication uses message signing (not transaction signing), which costs no gas and poses no risk to your funds.
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
                  </a>{" "}
                  with the token address and details.
                </p>
              </div>
            </div>
          </GlassCard>

          {/* CTA */}
          <div className="text-center py-8">
            <p className="text-muted-foreground mb-4">
              Ready to start analyzing tokens?
            </p>
            <Link href="/">
              <Button size="lg" className="bg-emerald-600 hover:bg-emerald-500 text-black font-semibold">
                <Search className="mr-2 w-5 h-5" />
                Analyze a Token
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
