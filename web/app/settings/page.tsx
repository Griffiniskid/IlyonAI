"use client";

import { useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import dynamic from "next/dynamic";
import { useAuth, useUser } from "@/lib/hooks";
import { useToast } from "@/components/ui/toaster";

// Dynamically import WalletMultiButton with SSR disabled to prevent hydration mismatch
const WalletMultiButton = dynamic(
  () => import("@solana/wallet-adapter-react-ui").then((mod) => mod.WalletMultiButton),
  { ssr: false }
);
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Settings,
  Wallet,
  Bell,
  Shield,
  Moon,
  Sun,
  Loader2,
  Check,
  ExternalLink,
  LogOut,
} from "lucide-react";
import { truncateAddress, cn } from "@/lib/utils";

const INTEGRATION_KEYS = [
  { key: "helius_api_key", label: "Helius API Key", description: "Solana RPC and DAS API" },
  { key: "moralis_api_key", label: "Moralis API Key", description: "EVM token and NFT data" },
  { key: "etherscan_api_key", label: "Etherscan API Key", description: "Ethereum explorer" },
  { key: "bscscan_api_key", label: "BscScan API Key", description: "BSC explorer" },
  { key: "polygonscan_api_key", label: "PolygonScan API Key", description: "Polygon explorer" },
  { key: "arbiscan_api_key", label: "Arbiscan API Key", description: "Arbitrum explorer" },
  { key: "basescan_api_key", label: "BaseScan API Key", description: "Base explorer" },
] as const;

function IntegrationKeys() {
  const [keys, setKeys] = useState<Record<string, string>>(() => {
    if (typeof window === "undefined") return {};
    try {
      return JSON.parse(localStorage.getItem("ilyon_api_keys") || "{}");
    } catch {
      return {};
    }
  });

  const handleChange = (key: string, value: string) => {
    const updated = { ...keys, [key]: value };
    setKeys(updated);
    localStorage.setItem("ilyon_api_keys", JSON.stringify(updated));
  };

  return (
    <div className="space-y-3">
      {INTEGRATION_KEYS.map((item) => (
        <div key={item.key}>
          <label className="text-sm font-medium block mb-1">{item.label}</label>
          <p className="text-xs text-muted-foreground mb-1">{item.description}</p>
          <div className="flex gap-2">
            <Input
              type="password"
              value={keys[item.key] || ""}
              onChange={(e) => handleChange(item.key, e.target.value)}
              placeholder="Enter API key..."
              className="font-mono text-sm"
            />
            {keys[item.key] ? (
              <Badge variant="safe" className="shrink-0 self-center">
                <Check className="h-3 w-3 mr-1" />
                Set
              </Badge>
            ) : (
              <Badge variant="outline" className="shrink-0 self-center text-muted-foreground">
                Not set
              </Badge>
            )}
          </div>
        </div>
      ))}
      <div className="mt-3 p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
        <p className="text-xs text-yellow-400">
          Keys are stored in your browser only. Server-side key management will be available in a future update.
        </p>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { connected, publicKey, disconnect, signMessage } = useWallet();
  const { authenticate, isAuthenticating, logout } = useAuth();
  const { data: user, isLoading: userLoading } = useUser();

  const { addToast } = useToast();

  const [notifications, setNotifications] = useState({
    priceAlerts: true,
    whaleActivity: false,
    securityAlerts: true,
  });

  const handleAuthenticate = async () => {
    if (!signMessage) {
      addToast("Your wallet does not support message signing. Try a different wallet.", "error");
      return;
    }
    try {
      await authenticate();
      addToast("Successfully authenticated!", "success");
    } catch (error: any) {
      const message = error?.message || "Authentication failed";
      if (message.includes("User rejected")) {
        addToast("Signature request was rejected", "error");
      } else {
        addToast(`Authentication failed: ${message}`, "error");
      }
    }
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2">Settings</h1>
      <p className="text-muted-foreground mb-8">
        Manage your account and preferences
      </p>

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

            {/* Authentication status */}
            <div className="pt-4 border-t border-border">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Session Authentication</div>
                  <div className="text-sm text-muted-foreground">
                    Sign a message to access premium features
                  </div>
                </div>
                {user ? (
                  <div className="flex items-center gap-2">
                    <Badge variant="safe">
                      <Check className="h-3 w-3 mr-1" />
                      Authenticated
                    </Badge>
                    <Button variant="outline" size="sm" onClick={logout}>
                      Sign Out
                    </Button>
                  </div>
                ) : (
                  <Button
                    onClick={handleAuthenticate}
                    disabled={isAuthenticating}
                  >
                    {isAuthenticating ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <Shield className="h-4 w-4 mr-2" />
                    )}
                    Authenticate
                  </Button>
                )}
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

      {/* Account Stats */}
      {user && (
        <GlassCard className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="h-5 w-5 text-emerald-500" />
            <h2 className="font-semibold">Account Statistics</h2>
          </div>

          <div className="grid grid-cols-3 gap-2 sm:gap-4">
            <div className="text-center p-3 sm:p-4 bg-card/50 rounded-lg">
              <div className="text-xl sm:text-2xl font-bold">{user.analyses_count}</div>
              <div className="text-xs sm:text-sm text-muted-foreground">Analyses</div>
            </div>
            <div className="text-center p-3 sm:p-4 bg-card/50 rounded-lg">
              <div className="text-xl sm:text-2xl font-bold">{user.tracked_wallets}</div>
              <div className="text-xs sm:text-sm text-muted-foreground">Tracked</div>
            </div>
            <div className="text-center p-3 sm:p-4 bg-card/50 rounded-lg">
              <div className="text-xl sm:text-2xl font-bold">{user.alerts_count}</div>
              <div className="text-xs sm:text-sm text-muted-foreground">Alerts</div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-border text-sm text-muted-foreground">
            Member since {new Date(user.created_at).toLocaleDateString()}
          </div>
        </GlassCard>
      )}

      {/* Notifications */}
      <section id="preferences">
        <GlassCard className="mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Bell className="h-5 w-5 text-emerald-500" />
          <h2 className="font-semibold">Notifications</h2>
        </div>

        <div className="space-y-4">
          {[
            {
              key: "priceAlerts",
              label: "Price Alerts",
              description: "Get notified when token prices hit your targets",
            },
            {
              key: "whaleActivity",
              label: "Whale Activity",
              description: "Alerts for large transactions on tracked tokens",
            },
            {
              key: "securityAlerts",
              label: "Security Alerts",
              description: "Warnings when token security changes",
            },
          ].map((item) => (
            <div
              key={item.key}
              className="flex items-center justify-between py-2"
            >
              <div>
                <div className="font-medium">{item.label}</div>
                <div className="text-sm text-muted-foreground">
                  {item.description}
                </div>
              </div>
              <Button
                variant={
                  notifications[item.key as keyof typeof notifications]
                    ? "default"
                    : "outline"
                }
                size="sm"
                onClick={() =>
                  setNotifications((prev) => ({
                    ...prev,
                    [item.key]: !prev[item.key as keyof typeof notifications],
                  }))
                }
                className={
                  notifications[item.key as keyof typeof notifications]
                    ? "bg-emerald-600"
                    : ""
                }
              >
                {notifications[item.key as keyof typeof notifications]
                  ? "On"
                  : "Off"}
              </Button>
            </div>
          ))}
        </div>

        <div className="mt-4 p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
          <div className="text-sm text-yellow-400">
            Browser notifications require permission. Coming soon!
          </div>
        </div>
        </GlassCard>
      </section>

      {/* API Integrations */}
      <section id="integrations">
        <GlassCard className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="h-5 w-5 text-emerald-500" />
            <h2 className="font-semibold">API Integrations</h2>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Configure API keys to enable full functionality. Keys are stored locally in your browser.
          </p>
          <IntegrationKeys />
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
