"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { useAnalyzeToken, useRefreshAnalysis } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScoreCard } from "@/components/token/score-card";
import { SecurityChecks } from "@/components/token/security-checks";
import { MarketData } from "@/components/token/market-data";
import { AIAnalysis } from "@/components/token/ai-analysis";
import {
  ArrowLeft,
  RefreshCw,
  Share2,
  ExternalLink,
  Copy,
  Check,
  Loader2,
  AlertTriangle,
  Users,
  Globe,
  Twitter,
  MessageCircle,
} from "lucide-react";
import {
  formatUSD,
  formatPercentage,
  truncateAddress,
  copyToClipboard,
  cn,
} from "@/lib/utils";
import { useState } from "react";

export default function TokenAnalysisPage() {
  const params = useParams();
  const router = useRouter();
  const address = params.address as string;

  const [copied, setCopied] = useState(false);
  const [analysisStage, setAnalysisStage] = useState(0);

  const {
    mutate: analyze,
    data: analysis,
    isPending: isAnalyzing,
    error,
  } = useAnalyzeToken();

  const { mutate: refresh, isPending: isRefreshing } = useRefreshAnalysis();

  // Start analysis on mount
  useEffect(() => {
    if (address) {
      analyze({ address, mode: "standard" });
    }
  }, [address, analyze]);

  // Simulate analysis stages
  useEffect(() => {
    if (isAnalyzing) {
      const stages = [1, 2, 3, 4];
      let i = 0;
      const interval = setInterval(() => {
        setAnalysisStage(stages[i]);
        i++;
        if (i >= stages.length) clearInterval(interval);
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [isAnalyzing]);

  const handleCopyAddress = async () => {
    await copyToClipboard(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRefresh = () => {
    refresh({ address, mode: "standard" });
  };

  // Loading state
  if (isAnalyzing && !analysis) {
    return (
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-2xl mx-auto">
          <GlassCard className="text-center py-12">
            <Loader2 className="h-12 w-12 text-emerald-500 animate-spin mx-auto mb-6" />
            <h2 className="text-xl font-semibold mb-4">Analyzing Token...</h2>
            <p className="text-muted-foreground mb-6 font-mono text-sm">
              {truncateAddress(address, 8)}
            </p>

            {/* Analysis stages */}
            <div className="max-w-md mx-auto space-y-3">
              {[
                { stage: 1, label: "Collecting market data..." },
                { stage: 2, label: "Running security checks..." },
                { stage: 3, label: "AI analysis in progress..." },
                { stage: 4, label: "Calculating risk scores..." },
              ].map((item) => (
                <div
                  key={item.stage}
                  className={cn(
                    "flex items-center gap-3 text-sm transition-opacity",
                    analysisStage >= item.stage ? "opacity-100" : "opacity-30"
                  )}
                >
                  {analysisStage > item.stage ? (
                    <Check className="h-4 w-4 text-emerald-400" />
                  ) : analysisStage === item.stage ? (
                    <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                  ) : (
                    <div className="h-4 w-4 rounded-full border border-muted" />
                  )}
                  {item.label}
                </div>
              ))}
            </div>

            <Progress value={analysisStage * 25} className="max-w-md mx-auto mt-6" />
          </GlassCard>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !analysis) {
    return (
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-2xl mx-auto">
          <GlassCard className="text-center py-12">
            <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-4" />
            <h2 className="text-xl font-semibold mb-2">Analysis Failed</h2>
            <p className="text-muted-foreground mb-6">
              {(error as Error).message || "Failed to analyze token"}
            </p>
            <div className="flex gap-4 justify-center">
              <Button variant="outline" onClick={() => router.back()}>
                <ArrowLeft className="h-4 w-4 mr-2" />
                Go Back
              </Button>
              <Button onClick={() => analyze({ address })}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Try Again
              </Button>
            </div>
          </GlassCard>
        </div>
      </div>
    );
  }

  if (!analysis) return null;

  const { token, scores, market, security, holders, ai, socials, deployer } = analysis;

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.back()}
        className="mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back
      </Button>

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          {token.logo_url && (
            <Image
              src={token.logo_url}
              alt={token.symbol}
              width={48}
              height={48}
              className="rounded-full"
            />
          )}
          <div>
            <h1 className="text-2xl md:text-3xl font-bold">
              {token.name}{" "}
              <span className="text-muted-foreground">(${token.symbol})</span>
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <code className="text-sm text-muted-foreground font-mono">
                {truncateAddress(address, 8)}
              </code>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={handleCopyAddress}
              >
                {copied ? (
                  <Check className="h-3 w-3 text-emerald-400" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
              </Button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            <RefreshCw
              className={cn("h-4 w-4 mr-2", isRefreshing && "animate-spin")}
            />
            Refresh
          </Button>
          <Button variant="outline" size="sm">
            <Share2 className="h-4 w-4 mr-2" />
            Share
          </Button>
        </div>
      </div>

      {/* Price header */}
      <GlassCard className="mb-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="text-3xl font-mono font-bold">
              {formatUSD(market.price_usd)}
            </div>
            <div
              className={cn(
                "text-lg font-semibold",
                market.price_change_24h >= 0 ? "text-emerald-400" : "text-red-400"
              )}
            >
              {formatPercentage(market.price_change_24h)} (24h)
            </div>
          </div>
          <div className="flex gap-6 text-sm">
            <div>
              <div className="text-muted-foreground">Market Cap</div>
              <div className="font-mono font-semibold">{formatUSD(market.market_cap)}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Liquidity</div>
              <div className="font-mono font-semibold">{formatUSD(market.liquidity_usd)}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Volume 24h</div>
              <div className="font-mono font-semibold">{formatUSD(market.volume_24h)}</div>
            </div>
          </div>
        </div>
      </GlassCard>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Score Card */}
        <GlassCard className="flex items-center justify-center py-8">
          <ScoreCard
            score={scores.overall}
            grade={scores.grade}
            verdict={ai.verdict}
            size="lg"
          />
        </GlassCard>

        {/* Security Checks */}
        <SecurityChecks security={security} />

        {/* Market Data */}
        <MarketData market={market} />
      </div>

      {/* AI Analysis - Full width */}
      <div className="mt-6">
        <AIAnalysis ai={ai} />
      </div>

      {/* Additional info row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
        {/* Holder Analysis */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-5 w-5 text-emerald-500" />
            <h3 className="font-semibold">Holder Analysis</h3>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Top Holder</span>
              <span className="font-mono">{holders.top_holder_pct.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Concentration</span>
              <span className="font-mono">{holders.holder_concentration.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Suspicious Wallets</span>
              <span
                className={cn(
                  "font-mono",
                  holders.suspicious_wallets > 0 ? "text-yellow-400" : "text-emerald-400"
                )}
              >
                {holders.suspicious_wallets}
              </span>
            </div>
            {holders.dev_wallet_risk && (
              <Badge variant="risky" className="mt-2">
                Dev wallet risk detected
              </Badge>
            )}
          </div>
        </GlassCard>

        {/* Socials */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Globe className="h-5 w-5 text-emerald-500" />
            <h3 className="font-semibold">Social Presence</h3>
          </div>
          <div className="space-y-3">
            {socials.website_url && (
              <a
                href={socials.website_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm hover:text-emerald-400 transition"
              >
                <Globe className="h-4 w-4" />
                Website
                <ExternalLink className="h-3 w-3 ml-auto" />
              </a>
            )}
            {socials.twitter_url && (
              <a
                href={socials.twitter_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm hover:text-emerald-400 transition"
              >
                <Twitter className="h-4 w-4" />
                Twitter
                <ExternalLink className="h-3 w-3 ml-auto" />
              </a>
            )}
            {socials.telegram_url && (
              <a
                href={socials.telegram_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm hover:text-emerald-400 transition"
              >
                <MessageCircle className="h-4 w-4" />
                Telegram
                <ExternalLink className="h-3 w-3 ml-auto" />
              </a>
            )}
            {!socials.has_twitter && !socials.has_website && !socials.has_telegram && (
              <p className="text-muted-foreground text-sm">No socials found</p>
            )}
          </div>
        </GlassCard>

        {/* Deployer */}
        {deployer.available && (
          <GlassCard>
            <div className="flex items-center gap-2 mb-4">
              <Shield className="h-5 w-5 text-emerald-500" />
              <h3 className="font-semibold">Deployer Forensics</h3>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Reputation</span>
                <span
                  className={cn(
                    "font-mono",
                    deployer.reputation_score >= 70 && "text-emerald-400",
                    deployer.reputation_score < 70 &&
                      deployer.reputation_score >= 40 &&
                      "text-yellow-400",
                    deployer.reputation_score < 40 && "text-red-400"
                  )}
                >
                  {deployer.reputation_score.toFixed(0)}/100
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Risk Level</span>
                <Badge
                  variant={
                    deployer.risk_level === "CLEAN"
                      ? "safe"
                      : deployer.risk_level === "LOW"
                      ? "safe"
                      : deployer.risk_level === "MEDIUM"
                      ? "caution"
                      : "danger"
                  }
                >
                  {deployer.risk_level}
                </Badge>
              </div>
              {deployer.is_known_scammer && (
                <Badge variant="danger" className="mt-2">
                  Known Scammer!
                </Badge>
              )}
            </div>
          </GlassCard>
        )}
      </div>
    </div>
  );
}

// Import Shield for deployer section
import { Shield } from "lucide-react";
