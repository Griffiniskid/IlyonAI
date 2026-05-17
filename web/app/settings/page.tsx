"use client";

import { useWallet } from "@solana/wallet-adapter-react";
import dynamic from "next/dynamic";
import AssistantWalletSettings from "@/components/agent-app/AssistantWalletSettings";
import SessionKeyPanel from "@/components/settings/SessionKeyPanel";
import AuditLogPanel from "@/components/settings/AuditLogPanel";
import Eip7702OptInPanel from "@/components/settings/Eip7702OptInPanel";
import SolanaSessionKeyPanel from "@/components/settings/SolanaSessionKeyPanel";

// Dynamically import WalletMultiButton with SSR disabled to prevent hydration mismatch
const WalletMultiButton = dynamic(
  () => import("@solana/wallet-adapter-react-ui").then((mod) => mod.WalletMultiButton),
  { ssr: false }
);
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Wallet,
  ExternalLink,
  LogOut,
} from "lucide-react";
import { truncateAddress } from "@/lib/utils";

export default function SettingsPage() {
  const { connected, publicKey, disconnect } = useWallet();

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2">Settings</h1>
      <p className="text-muted-foreground mb-8">
        Manage your account and preferences
      </p>

      {/* Agent wallet (Phantom/MetaMask/email session used for the AI Agent) */}
      <AssistantWalletSettings />

      {/* Session-key policies (§11 D.5/D.6) */}
      {connected && publicKey ? (
        <div className="mt-6 space-y-4">
          <SessionKeyPanel userWallet={publicKey.toBase58()} />
          <Eip7702OptInPanel userWallet={publicKey.toBase58()} />
          <SolanaSessionKeyPanel userWallet={publicKey.toBase58()} />
          <AuditLogPanel userWallet={publicKey.toBase58()} />
        </div>
      ) : null}

      {/* Wallet Section */}
      <section id="auth">
        <GlassCard className="mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Wallet className="h-5 w-5 text-emerald-500" />
          <h2 className="font-semibold">Wallet Connection</h2>
        </div>

        {connected ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-mono text-sm">
                  {truncateAddress(publicKey?.toBase58() || "", 8)}
                </div>
                <Badge variant="safe" className="mt-1">Connected</Badge>
              </div>
              <div className="flex gap-2">
                <WalletMultiButton />
                <Button variant="outline" onClick={() => disconnect()}>
                  <LogOut className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center py-6">
            <Wallet className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground mb-4">
              Connect your wallet to access all features
            </p>
            <WalletMultiButton />
          </div>
        )}
        </GlassCard>
      </section>

      {/* Links */}
      <section>
        <GlassCard>
        <h2 className="font-semibold mb-4">Resources</h2>

        <div className="space-y-2">
          {[
            { label: "Documentation", href: "/docs" },
            { label: "Twitter", href: "https://x.com/ilyonProtocol" },
            { label: "Telegram", href: "https://t.me/ilyonProtocol" },
          ].map((link) => (
            <a
              key={link.label}
              href={link.href}
              target={link.href.startsWith("http") ? "_blank" : undefined}
              rel={link.href.startsWith("http") ? "noopener noreferrer" : undefined}
              className="flex items-center justify-between p-3 rounded-lg hover:bg-card/50 transition"
            >
              <span>{link.label}</span>
              <ExternalLink className="h-4 w-4 text-muted-foreground" />
            </a>
          ))}
        </div>
        </GlassCard>
      </section>
    </div>
  );
}
