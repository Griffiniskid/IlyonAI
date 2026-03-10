"use client";

import Link from "next/link";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  Bot,
  BookOpen,
  Code,
  Database,
  Layers,
  Search,
  Shield,
  Wallet,
} from "lucide-react";

const SUPPORTED_CHAINS = [
  "Solana",
  "Ethereum",
  "Base",
  "Arbitrum",
  "BSC",
  "Polygon",
  "Optimism",
  "Avalanche",
];

const WORKFLOWS = [
  {
    icon: Search,
    title: "Token analysis",
    description:
      "Analyze a token address, review market/security data, inspect holder concentration, and read the AI verdict.",
    endpoints: ["POST /api/v1/analyze", "GET /api/v1/token/{address}?chain={chain}", "POST /api/v1/token/{address}/refresh?chain={chain}"],
  },
  {
    icon: Shield,
    title: "Security operations",
    description:
      "Scan EVM contracts, review wallet approvals, and prepare revoke transactions without executing them.",
    endpoints: ["POST /api/v1/contract/scan", "GET /api/v1/shield/{wallet}", "POST /api/v1/shield/revoke"],
  },
  {
    icon: Layers,
    title: "DeFi intelligence",
    description:
      "Discover opportunities, inspect protocol due diligence, compare markets, and simulate stress across supported ecosystems.",
    endpoints: ["GET /api/v1/defi/opportunities", "GET /api/v2/defi/compare", "GET /api/v2/defi/protocols/{slug}", "POST /api/v2/defi/simulate/lending"],
  },
  {
    icon: Bot,
    title: "AI chat",
    description:
      "Use the chat agent to analyze tokens, contracts, wallets, audits, and DeFi opportunities from one interface.",
    endpoints: ["POST /api/v1/chat", "GET /api/v1/chat/session", "GET /api/v1/chat/session/{session_id}"],
  },
];

const API_SECTIONS = [
  {
    method: "POST",
    path: "/api/v1/analyze",
    body: `{
  "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
  "chain": "ethereum",
  "mode": "standard"
}`,
    notes: "Creates or refreshes a full token analysis response.",
  },
  {
    method: "GET",
    path: "/api/v1/search?query=usdc&chain=base",
    body: null,
    notes: "Searches DexScreener-backed token results and returns chain-aware links.",
  },
  {
    method: "POST",
    path: "/api/v1/contract/scan",
    body: `{
  "address": "0x1f98431c8aD98523631AE4a59f267346ea31F984",
  "chain": "ethereum"
}`,
    notes: "Runs EVM contract analysis and returns normalized vulnerabilities, risk score, and AI findings.",
  },
  {
    method: "GET",
    path: "/api/v2/defi/compare?asset=USDC&chain=base",
    body: null,
    notes: "Compares the same asset path across protocols using safety, yield quality, exit quality, and confidence.",
  },
  {
    method: "POST",
    path: "/api/v2/defi/simulate/lending",
    body: `{
  "collateral_usd": 10000,
  "debt_usd": 5000,
  "utilization_pct": 72,
  "collateral_drop_pct": 20
}`,
    notes: "Runs lending stress simulation over collateral drawdown, rate spikes, and reserve stress.",
  },
  {
    method: "GET",
    path: "/api/v1/docs",
    body: null,
    notes: "Returns machine-readable API docs and example workflows.",
  },
];

function MethodBadge({ method }: { method: string }) {
  const styles: Record<string, string> = {
    GET: "bg-blue-500/15 text-blue-300 border-blue-500/25",
    POST: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  };

  return (
    <span className={`inline-flex rounded-md border px-2 py-1 text-xs font-mono ${styles[method] ?? styles.GET}`}>
      {method}
    </span>
  );
}

export default function DocsPage() {
  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <div className="mb-10 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">
            <BookOpen className="h-3.5 w-3.5" />
            Product + API docs
          </div>
          <h1 className="text-4xl font-bold">Ilyon AI Documentation</h1>
          <p className="mt-3 max-w-3xl text-lg text-muted-foreground">
            Ilyon AI is a multi-chain DeFi intelligence platform for token analysis, approval scanning, contract review, DeFi research, and chat-assisted investigation.
          </p>
        </div>
        <div className="flex gap-3">
          <Link href="/chat">
            <Button variant="outline">Open AI Chat</Button>
          </Link>
          <Link href="/">
            <Button className="bg-emerald-600 text-black hover:bg-emerald-500">Analyze a Token</Button>
          </Link>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <GlassCard>
          <div className="mb-4 flex items-center gap-2">
            <Database className="h-5 w-5 text-emerald-400" />
            <h2 className="text-xl font-semibold">Supported chains</h2>
          </div>
          <p className="mb-4 text-sm text-muted-foreground">
            Token analysis and discovery cover Solana plus major EVM networks. Contract scanning and approval management are EVM-focused. Chat can orchestrate these tools, but it never executes transactions.
          </p>
          <div className="flex flex-wrap gap-2">
            {SUPPORTED_CHAINS.map((chain) => (
              <span key={chain} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-muted-foreground">
                {chain}
              </span>
            ))}
          </div>
        </GlassCard>

        <GlassCard>
          <div className="mb-4 flex items-center gap-2">
            <Wallet className="h-5 w-5 text-emerald-400" />
            <h2 className="text-xl font-semibold">Safety model</h2>
          </div>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p>- Read-only analysis only; no wallet transactions are executed by the AI.</p>
            <p>- Approval revokes are prepared as unsigned transactions for the user to review.</p>
            <p>- AI verdicts are advisory and should be paired with your own due diligence.</p>
          </div>
        </GlassCard>
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        {WORKFLOWS.map(({ icon: Icon, title, description, endpoints }) => (
          <GlassCard key={title}>
            <div className="mb-4 flex items-center gap-2">
              <Icon className="h-5 w-5 text-emerald-400" />
              <h2 className="text-xl font-semibold">{title}</h2>
            </div>
            <p className="mb-4 text-sm text-muted-foreground">{description}</p>
            <div className="space-y-2">
              {endpoints.map((endpoint) => (
                <div key={endpoint} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-slate-200">
                  {endpoint}
                </div>
              ))}
            </div>
          </GlassCard>
        ))}
      </div>

      <GlassCard className="mt-8">
        <div className="mb-4 flex items-center gap-2">
          <Code className="h-5 w-5 text-emerald-400" />
          <h2 className="text-xl font-semibold">Key endpoints</h2>
        </div>
        <div className="space-y-4">
          {API_SECTIONS.map((section) => (
            <div key={section.path} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="mb-2 flex flex-wrap items-center gap-3">
                <MethodBadge method={section.method} />
                <code className="text-sm text-slate-100">{section.path}</code>
              </div>
              <p className="mb-3 text-sm text-muted-foreground">{section.notes}</p>
              {section.body && (
                <pre className="overflow-x-auto rounded-lg bg-black/30 p-3 text-xs text-emerald-200">
                  <code>{section.body}</code>
                </pre>
              )}
            </div>
          ))}
        </div>
      </GlassCard>

      <GlassCard className="mt-8">
        <h2 className="mb-4 text-xl font-semibold">Common UI paths</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {[
            ["/token/[address]?chain=...", "Deep token analysis with security, market, holder, website, and AI sections."],
            ["/contract", "Manual EVM contract scanning and AI-assisted code risk review."],
            ["/shield", "Wallet approval scanner with revoke preparation across supported EVM chains."],
            ["/defi", "DeFi discover hub for ranked opportunities, protocol spotlights, and AI market context."],
            ["/defi/compare", "Protocol-vs-protocol comparison for the same asset and chain surface."],
            ["/defi/lending", "Lending market browser plus health, LP, and stress simulation tools."],
            ["/audits", "Protocol audit database for reviewing third-party audit records."],
            ["/chat", "Conversational interface for the same backend intelligence tools."],
          ].map(([path, description]) => (
            <div key={path} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-muted-foreground">
              <div className="mb-1 font-mono text-slate-100">{path}</div>
              <div>{description}</div>
            </div>
          ))}
        </div>
      </GlassCard>

      <div className="mt-8 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-6 py-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-xl font-semibold">Need the raw contract?</h2>
            <p className="text-sm text-muted-foreground">
              The backend also exposes machine-readable docs at <code className="rounded bg-black/20 px-1.5 py-0.5 text-xs">/api/v1/docs</code> for integrations and SDK work.
            </p>
          </div>
          <Link href="/chat">
            <Button variant="outline">
              Explore with AI
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
