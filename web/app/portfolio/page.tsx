"use client";

import { useState, useEffect } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useToast } from "@/components/ui/toaster";
import { ChainExposureTable } from "@/components/portfolio/chain-exposure-table";
import { RiskBreakdown } from "@/components/portfolio/risk-breakdown";

// Dynamically import WalletMultiButton with SSR disabled to prevent hydration mismatch
const WalletMultiButton = dynamic(
  () => import("@solana/wallet-adapter-react-ui").then((mod) => mod.WalletMultiButton),
  { ssr: false }
);
import Image from "next/image";
import {
  usePortfolio,
  useWalletPortfolio,
  useTrackedWallets,
  useTrackWallet,
  useAuth,
  usePortfolioChainMatrix,
} from "@/lib/hooks";
import { APIError, getRektIncidents } from "@/lib/api";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Wallet,
  Plus,
  Loader2,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  ExternalLink,
  Shield,
} from "lucide-react";
import {
  formatUSD,
  formatPercentage,
  truncateAddress,
  isValidSolanaAddress,
  cn,
} from "@/lib/utils";
import type { RektIncident } from "@/types";

export default function PortfolioPage() {
  const { connected, publicKey } = useWallet();
  const [walletInput, setWalletInput] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const [trackedAddress, setTrackedAddress] = useState<string | null>(null);
  const { addToast } = useToast();
  const [rektIncidents, setRektIncidents] = useState<RektIncident[]>([]);

  const { data: portfolio, isLoading: portfolioLoading, refetch } = useWalletPortfolio(
    publicKey?.toBase58() || null
  );
  const { data: chainMatrix } = usePortfolioChainMatrix();
  const { data: trackedPortfolio, isLoading: trackedLoading } = useWalletPortfolio(trackedAddress);
  const trackWallet = useTrackWallet();

  useEffect(() => {
    if (!portfolio?.tokens?.length) {
      setRektIncidents([]);
      return;
    }

    const search = portfolio.tokens.slice(0, 3).map((token) => token.symbol).filter(Boolean).join(" ");
    if (!search) {
      setRektIncidents([]);
      return;
    }

    let active = true;
    getRektIncidents({ search, limit: 3 })
      .then((result) => {
        if (active) {
          setRektIncidents(result.incidents);
        }
      })
      .catch(() => {
        if (active) {
          setRektIncidents([]);
        }
      });

    return () => {
      active = false;
    };
  }, [portfolio?.tokens]);

  const handleAddWallet = () => {
    setInputError(null);

    if (!walletInput.trim()) {
      setInputError("Please enter a wallet address");
      return;
    }

    if (!isValidSolanaAddress(walletInput.trim())) {
      setInputError("Invalid Solana address");
      return;
    }

    const address = walletInput.trim();
    trackWallet.mutate(
      { address },
      {
        onSuccess: () => {
          addToast(`Now tracking wallet ${address.slice(0, 8)}...`, "success");
          setTrackedAddress(address);
          setWalletInput("");
        },
        onError: (error) => {
          if (error instanceof APIError && error.status === 401) {
            setInputError("Please authenticate in Settings first");
            addToast("Authentication required. Go to Settings to authenticate.", "error");
          } else {
            setInputError(error.message || "Failed to track wallet");
            addToast("Failed to track wallet", "error");
          }
        },
      }
    );
  };

  // Not connected state
  if (!connected) {
    return (
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-lg mx-auto">
          <GlassCard className="text-center py-12">
            <Wallet className="h-16 w-16 text-muted-foreground mx-auto mb-6" />
            <h2 className="text-2xl font-bold mb-4">Connect Your Wallet</h2>
            <p className="text-muted-foreground mb-8">
              Connect your Solana wallet to view your portfolio and track your holdings
            </p>
            <WalletMultiButton />
          </GlassCard>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2">Portfolio</h1>
          <p className="text-muted-foreground">
            Track your multi-chain holdings and their security status
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => refetch()}
          disabled={portfolioLoading}
        >
          <RefreshCw
            className={cn("h-4 w-4 mr-2", portfolioLoading && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      {/* Portfolio summary */}
      {portfolio && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 mb-8">
          <GlassCard className="text-center">
            <div className="text-sm text-muted-foreground mb-1">Total Value</div>
            <div className="text-2xl font-mono font-bold">
              {formatUSD(portfolio.total_value_usd)}
            </div>
          </GlassCard>

          <GlassCard className="text-center">
            <div className="text-sm text-muted-foreground mb-1">24h P&L</div>
            <div
              className={cn(
                "text-2xl font-mono font-bold",
                portfolio.total_pnl_percent >= 0 ? "text-emerald-400" : "text-red-400"
              )}
            >
              {formatPercentage(portfolio.total_pnl_percent)}
            </div>
          </GlassCard>

          <GlassCard className="text-center">
            <div className="text-sm text-muted-foreground mb-1">Tokens</div>
            <div className="text-2xl font-mono font-bold">
              {portfolio.tokens.length}
            </div>
          </GlassCard>

          <GlassCard className="text-center">
            <div className="text-sm text-muted-foreground mb-1">Health Score</div>
            <div
              className={cn(
                "text-2xl font-mono font-bold",
                portfolio.health_score >= 70 && "text-emerald-400",
                portfolio.health_score < 70 && portfolio.health_score >= 40 && "text-yellow-400",
                portfolio.health_score < 40 && "text-red-400"
              )}
            >
              {portfolio.health_score}/100
            </div>
          </GlassCard>
        </div>
      )}

      {/* Add wallet */}
      <GlassCard className="mb-8">
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <Plus className="h-5 w-5" />
          Track Another Wallet
        </h3>
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
          <Input
            placeholder="Enter Solana wallet address..."
            value={walletInput}
            onChange={(e) => {
              setWalletInput(e.target.value);
              setInputError(null);
            }}
            className="flex-1"
          />
          <Button
            onClick={handleAddWallet}
            disabled={trackWallet.isPending}
            className="sm:w-auto w-full"
          >
            {trackWallet.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "Track"
            )}
          </Button>
        </div>
        {inputError && (
          <p className="text-red-400 text-sm mt-2">{inputError}</p>
        )}
      </GlassCard>

      <GlassCard className="mb-8">
        <h3 className="font-semibold">Risk Context: Hacks & Exploits</h3>
        <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
          {rektIncidents.length === 0 ? (
            <li>No related incidents found.</li>
          ) : (
            rektIncidents.map((incident) => <li key={incident.id}>{incident.name}</li>)
          )}
        </ul>
      </GlassCard>

      <section id="exposures">
        <GlassCard className="mb-8">
        <h3 className="font-semibold mb-4">Multi-Chain Exposure</h3>
        <ChainExposureTable matrix={chainMatrix} />
        </GlassCard>
      </section>

      <section id="scenarios">
        <GlassCard className="mb-8">
        <h3 className="font-semibold mb-4">Capability Risk Breakdown</h3>
        <RiskBreakdown matrix={chainMatrix} />
        </GlassCard>
      </section>

      {/* Loading state */}
      {portfolioLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        </div>
      )}

      {/* Token list */}
      {portfolio && portfolio.tokens.length > 0 && (
        <GlassCard>
          <h3 className="font-semibold mb-4">Holdings</h3>
          <div className="divide-y divide-border">
            {portfolio.tokens.map((token) => (
              <Link
                key={token.address}
                href={`/token/${token.address}`}
                className="flex items-center justify-between py-4 hover:bg-card/50 -mx-6 px-6 transition"
              >
                <div className="flex items-center gap-4">
                  {token.logo_url ? (
                    <Image
                      src={token.logo_url}
                      alt={token.symbol}
                      width={40}
                      height={40}
                      className="rounded-full"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center font-bold">
                      {token.symbol[0]}
                    </div>
                  )}
                  <div>
                    <div className="font-semibold">{token.symbol}</div>
                    <div className="text-sm text-muted-foreground">
                      {token.balance.toLocaleString()} tokens
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <div className="font-mono font-semibold">
                      {formatUSD(token.balance_usd)}
                    </div>
                    <div
                      className={cn(
                        "text-sm font-mono",
                        token.price_change_24h >= 0 ? "text-emerald-400" : "text-red-400"
                      )}
                    >
                      {formatPercentage(token.price_change_24h)}
                    </div>
                  </div>

                  {token.safety_score !== null && (
                    <Badge
                      variant={
                        token.safety_score >= 70
                          ? "safe"
                          : token.safety_score >= 40
                          ? "caution"
                          : "danger"
                      }
                    >
                      <Shield className="h-3 w-3 mr-1" />
                      {token.safety_score}
                    </Badge>
                  )}

                  <ExternalLink className="h-4 w-4 text-muted-foreground" />
                </div>
              </Link>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Empty state */}
      {portfolio && portfolio.tokens.length === 0 && (
        <GlassCard className="text-center py-12">
          <Wallet className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">No Tokens Found</h3>
          <p className="text-muted-foreground">
            This wallet doesn't have any token holdings
          </p>
        </GlassCard>
      )}

      {/* Tracked wallet holdings */}
      {trackedAddress && (
        <div className="mt-8">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">
              Tracked: {truncateAddress(trackedAddress, 6)}
            </h3>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setTrackedAddress(null)}
            >
              Dismiss
            </Button>
          </div>

          {trackedLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
            </div>
          )}

          {trackedPortfolio && trackedPortfolio.tokens.length > 0 && (
            <GlassCard>
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm text-muted-foreground">
                  Total Value: <span className="font-mono font-semibold text-foreground">{formatUSD(trackedPortfolio.total_value_usd)}</span>
                  {" · "}
                  {trackedPortfolio.tokens.length} tokens
                </div>
              </div>
              <div className="divide-y divide-border">
                {trackedPortfolio.tokens.map((token) => (
                  <Link
                    key={token.address}
                    href={`/token/${token.address}`}
                    className="flex items-center justify-between py-3 hover:bg-card/50 -mx-6 px-6 transition"
                  >
                    <div className="flex items-center gap-3">
                      {token.logo_url ? (
                        <Image
                          src={token.logo_url}
                          alt={token.symbol}
                          width={32}
                          height={32}
                          className="rounded-full"
                        />
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-sm font-bold">
                          {token.symbol[0]}
                        </div>
                      )}
                      <div>
                        <div className="font-semibold text-sm">{token.symbol}</div>
                        <div className="text-xs text-muted-foreground">
                          {token.balance.toLocaleString()} tokens
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className="font-mono text-sm font-semibold">
                          {formatUSD(token.balance_usd)}
                        </div>
                        <div
                          className={cn(
                            "text-xs font-mono",
                            token.price_change_24h >= 0 ? "text-emerald-400" : "text-red-400"
                          )}
                        >
                          {formatPercentage(token.price_change_24h)}
                        </div>
                      </div>

                      {token.safety_score !== null && token.safety_score !== undefined && (
                        <Badge
                          variant={
                            token.safety_score >= 70
                              ? "safe"
                              : token.safety_score >= 40
                              ? "caution"
                              : "danger"
                          }
                        >
                          <Shield className="h-3 w-3 mr-1" />
                          {token.safety_score}
                        </Badge>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            </GlassCard>
          )}

          {trackedPortfolio && trackedPortfolio.tokens.length === 0 && (
            <GlassCard className="text-center py-8">
              <p className="text-muted-foreground text-sm">No token holdings found for this wallet</p>
            </GlassCard>
          )}
        </div>
      )}
    </div>
  );
}
