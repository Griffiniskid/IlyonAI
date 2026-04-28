"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Wallet, LogOut, RefreshCw } from "lucide-react";

interface AssistantSession {
  token: string | null;
  walletType: string | null;
  sol: string | null;
  evm: string | null;
}

const EMPTY: AssistantSession = { token: null, walletType: null, sol: null, evm: null };

function readSession(): AssistantSession {
  if (typeof window === "undefined") return EMPTY;
  return {
    token: localStorage.getItem("ap_token"),
    walletType: localStorage.getItem("ap_wallet_type"),
    sol: localStorage.getItem("ap_sol_wallet"),
    evm: localStorage.getItem("ap_wallet"),
  };
}

function shortAddr(a: string | null) {
  if (!a) return "";
  return `${a.slice(0, 8)}…${a.slice(-6)}`;
}

function clearAssistantSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("ap_token");
  localStorage.removeItem("ap_wallet");
  localStorage.removeItem("ap_sol_wallet");
  localStorage.removeItem("ap_phantom_wallet_context");
  localStorage.removeItem("ap_wallet_type");
  localStorage.removeItem("ap_chat_session");
  localStorage.removeItem("ap_user");
  localStorage.removeItem("ap_display_name");
  // Notify MainApp (and any sidebar widget) to re-read state.
  window.dispatchEvent(new StorageEvent("storage"));
}

export default function AssistantWalletSettings() {
  const [mounted, setMounted] = useState(false);
  const [sess, setSess] = useState<AssistantSession>(EMPTY);

  useEffect(() => {
    setMounted(true);
    const tick = () => setSess(readSession());
    tick();
    const id = window.setInterval(tick, 1500);
    window.addEventListener("storage", tick);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("storage", tick);
    };
  }, []);

  if (!mounted) return null;

  const isConnected = !!(sess.token || sess.sol || sess.evm);
  const addr = sess.walletType === "phantom" ? sess.sol : sess.evm;
  const label = sess.walletType === "phantom" ? "Phantom · Solana" : sess.walletType === "metamask" ? "MetaMask · BNB Chain" : "Connected wallet";

  function disconnect() {
    clearAssistantSession();
  }

  function switchAccount() {
    clearAssistantSession();
    // Send the user back to the agent flow so the auth modal opens fresh.
    window.location.href = "/agent/chat?tab=chat";
  }

  return (
    <GlassCard className="mb-6">
      <div className="flex items-center gap-2 mb-4">
        <Wallet className="h-5 w-5 text-emerald-500" />
        <h2 className="font-semibold">Agent Wallet</h2>
      </div>

      {isConnected ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
              <div className="font-mono text-sm mt-1 truncate">{addr ? shortAddr(addr) : "Email session"}</div>
              <Badge variant="safe" className="mt-2">Connected</Badge>
            </div>
            <div className="flex flex-col gap-2 shrink-0">
              <Button variant="outline" onClick={switchAccount} className="whitespace-nowrap">
                <RefreshCw className="h-4 w-4 mr-2" />
                Switch account
              </Button>
              <Button variant="outline" onClick={disconnect} className="whitespace-nowrap">
                <LogOut className="h-4 w-4 mr-2" />
                Disconnect
              </Button>
            </div>
          </div>
          <div className="pt-3 border-t border-border text-xs text-muted-foreground">
            This is the wallet used for AI Agent chat, swaps, and portfolio. Disconnecting clears the
            session locally; "Switch account" lets you reconnect with a different wallet.
          </div>
        </div>
      ) : (
        <div className="text-center py-6">
          <Wallet className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground mb-4">No agent wallet connected.</p>
          <Button onClick={() => (window.location.href = "/agent/chat?tab=chat")}>
            Connect a wallet
          </Button>
        </div>
      )}
    </GlassCard>
  );
}
