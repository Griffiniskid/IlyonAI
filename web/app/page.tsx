"use client";

import Link from "next/link";
import { TokenSearch } from "@/components/common/token-search";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Shield,
  TrendingUp,
  Wallet,
  Fish,
  Zap,
  Brain,
  Lock,
  Search,
} from "lucide-react";

const features = [
  {
    icon: Brain,
    title: "AI-Powered Analysis",
    description: "GPT-4 powered security assessment with advanced pattern recognition",
  },
  {
    icon: Shield,
    title: "Security Checks",
    description: "Mint authority, freeze authority, LP locks, and honeypot detection",
  },
  {
    icon: Lock,
    title: "Wallet Forensics",
    description: "Track deployer reputation and detect known scammer patterns",
  },
  {
    icon: Zap,
    title: "Real-time Data",
    description: "Live market data from DexScreener with instant updates",
  },
];

const quickActions = [
  { href: "/trending", icon: TrendingUp, label: "Trending", color: "text-emerald-400" },
  { href: "/portfolio", icon: Wallet, label: "Portfolio", color: "text-blue-400" },
  { href: "/whales", icon: Fish, label: "Whales", color: "text-purple-400" },
];

export default function HomePage() {
  return (
    <div className="container mx-auto px-4 py-12">
      {/* Hero Section */}
      <div className="text-center mb-12">
        <h1 className="text-4xl md:text-6xl font-bold mb-4 tracking-tight">
          Secure Your{" "}
          <span className="text-emerald-400">Solana Journey</span>
        </h1>
        <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-8">
          AI-powered token security analysis. Detect rugpulls, honeypots, and scams
          before investing. Trusted by thousands of Solana traders.
        </p>

        {/* Main Search */}
        <div className="max-w-2xl mx-auto mb-8">
          <GlassCard className="p-6 md:p-8">
            <div className="flex items-center gap-2 text-muted-foreground text-sm mb-4">
              <Search className="h-4 w-4" />
              Analyze any Solana token
            </div>
            <TokenSearch size="large" autoFocus />
          </GlassCard>
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap justify-center gap-4">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return (
              <Link key={action.href} href={action.href}>
                <Button variant="outline" size="lg" className="gap-2">
                  <Icon className={`h-5 w-5 ${action.color}`} />
                  {action.label}
                </Button>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Features Grid */}
      <div className="mt-20">
        <h2 className="text-2xl font-bold text-center mb-8">
          Why Choose AI Sentinel?
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <GlassCard
                key={feature.title}
                className="text-center hover:border-emerald-500/30 transition-all"
              >
                <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                  <Icon className="h-6 w-6 text-emerald-400" />
                </div>
                <h3 className="font-semibold mb-2">{feature.title}</h3>
                <p className="text-sm text-muted-foreground">{feature.description}</p>
              </GlassCard>
            );
          })}
        </div>
      </div>

      {/* Stats Section */}
      <div className="mt-20">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {[
            { label: "Tokens Analyzed", value: "50K+" },
            { label: "Scams Detected", value: "2.5K+" },
            { label: "Users Protected", value: "10K+" },
            { label: "AI Accuracy", value: "94%" },
          ].map((stat) => (
            <GlassCard key={stat.label} className="text-center py-6">
              <div className="text-3xl font-bold text-emerald-400 mb-1">
                {stat.value}
              </div>
              <div className="text-sm text-muted-foreground">{stat.label}</div>
            </GlassCard>
          ))}
        </div>
      </div>

      {/* CTA Section */}
      <div className="mt-20 text-center">
        <GlassCard className="max-w-2xl mx-auto py-12 px-8">
          <h2 className="text-2xl font-bold mb-4">Ready to Trade Safely?</h2>
          <p className="text-muted-foreground mb-6">
            Enter any Solana token address to get a comprehensive security analysis
            powered by advanced AI.
          </p>
          <Link href="#top">
            <Button variant="glow" size="xl">
              Start Scanning
            </Button>
          </Link>
        </GlassCard>
      </div>
    </div>
  );
}
