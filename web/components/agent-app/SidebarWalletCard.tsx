"use client";

import { useEffect, useState } from "react";

interface Session {
  token: string | null;
  walletType: string | null;
  sol: string | null;
  evm: string | null;
  displayName: string | null;
}

const EMPTY: Session = { token: null, walletType: null, sol: null, evm: null, displayName: null };

function readSession(): Session {
  if (typeof window === "undefined") return EMPTY;
  return {
    token: localStorage.getItem("ap_token"),
    walletType: localStorage.getItem("ap_wallet_type"),
    sol: localStorage.getItem("ap_sol_wallet"),
    evm: localStorage.getItem("ap_wallet"),
    displayName: localStorage.getItem("ap_display_name"),
  };
}

function shortAddr(a: string | null | undefined) {
  if (!a) return "";
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

export function SidebarWalletCard() {
  // SSR + first client render share the empty state to avoid hydration mismatch.
  const [mounted, setMounted] = useState(false);
  const [sess, setSess] = useState<Session>(EMPTY);

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

  const isAuthed = mounted && !!(sess.token || sess.sol || sess.evm);
  const addr = sess.walletType === "phantom" ? sess.sol : sess.evm;
  const label = sess.walletType === "phantom" ? "PHANTOM" : sess.walletType === "metamask" ? "METAMASK" : "ACCOUNT";

  if (!isAuthed) {
    return (
      <a
        href="/agent/chat?tab=chat"
        className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs hover:bg-emerald-500/20 transition"
      >
        <div className="font-semibold text-emerald-300">Connect / Sign in</div>
        <div className="mt-1 text-[10px] text-emerald-200/80">Wallet, email, or Phantom</div>
      </a>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card/40 p-3 text-xs">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground/80">{label}</div>
      <div className="mt-1 font-mono text-[11px] text-foreground">{addr ? shortAddr(addr) : sess.displayName || "Signed in"}</div>
    </div>
  );
}
