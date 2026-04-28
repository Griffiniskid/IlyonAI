import React, { useState, useEffect } from "react";

// ── Design tokens ──────────────────────────────────────────────────────────
const C = {
  bg:        "hsl(222 47% 4%)",
  surface:   "rgba(8, 15, 28, 0.82)",
  card:      "rgba(15, 23, 42, 0.78)",
  border:    "rgba(255,255,255,0.08)",
  accent:    "#10b981",
  accentDim: "#065f46",
  accentSoft:"#34d399",
  green:     "#34d399",
  red:       "#f87171",
  textPrimary:   "hsl(210 40% 98%)",
  textSecondary: "hsl(215 20% 65%)",
  textMuted:     "rgba(148,163,184,0.55)",
};

const S: Record<string, React.CSSProperties> = {
  root: {
    width: 380,
    minHeight: 520,
    background: C.bg,
    color: C.textPrimary,
    fontFamily: "Inter, 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif",
    fontSize: 13,
    display: "flex",
    flexDirection: "column",
  },
  // Header
  header: {
    background: C.surface,
    borderBottom: `1px solid ${C.border}`,
    padding: "12px 16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    backdropFilter: "blur(20px)",
  },
  logo: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  logoIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    fontSize: 14,
    fontWeight: 700,
    color: "#0D1117",
  },
  logoText: {
    fontSize: 14,
    fontWeight: 700,
    color: C.textPrimary,
    letterSpacing: "-0.2px",
  },
  networkBadge: {
    background: "#1C2128",
    border: `1px solid ${C.border}`,
    borderRadius: 20,
    padding: "3px 10px",
    fontSize: 11,
    color: C.textSecondary,
    display: "flex",
    alignItems: "center",
    gap: 5,
  },
  netDot: {
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: C.green,
  },
  // Body
  body: {
    flex: 1,
    padding: "16px",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  // Wallet card
  walletCard: {
    background: `linear-gradient(135deg, rgba(15,23,42,0.92) 0%, rgba(8,15,28,0.88) 100%)`,
    border: `1px solid ${C.border}`,
    borderRadius: 12,
    padding: 16,
  },
  walletLabel: {
    fontSize: 11,
    color: C.textMuted,
    textTransform: "uppercase" as const,
    letterSpacing: "0.8px",
    marginBottom: 6,
  },
  walletAddress: {
    fontSize: 13,
    color: C.textSecondary,
    fontFamily: "monospace",
    marginBottom: 16,
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  connectBtn: {
    background: `linear-gradient(135deg, ${C.accent}, ${C.accentSoft})`,
    color: "#03150f",
    border: "none",
    borderRadius: 12,
    padding: "8px 14px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  balanceRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-end",
  },
  balanceMain: {
    fontSize: 24,
    fontWeight: 700,
    color: C.textPrimary,
    letterSpacing: "-0.5px",
  },
  balanceSub: {
    fontSize: 12,
    color: C.textMuted,
    marginBottom: 2,
  },
  balanceUsd: {
    fontSize: 12,
    color: C.textSecondary,
    marginTop: 2,
  },
  // Tokens list
  sectionLabel: {
    fontSize: 11,
    color: C.textMuted,
    textTransform: "uppercase" as const,
    letterSpacing: "0.8px",
    marginBottom: 8,
  },
  tokenRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 12px",
    background: C.card,
    border: `1px solid ${C.border}`,
    borderRadius: 14,
    marginBottom: 6,
    backdropFilter: "blur(18px)",
  },
  tokenLeft: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  tokenIcon: {
    width: 32,
    height: 32,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 14,
    fontWeight: 700,
  },
  tokenName: {
    fontWeight: 600,
    fontSize: 13,
    color: C.textPrimary,
  },
  tokenNetwork: {
    fontSize: 11,
    color: C.textMuted,
  },
  tokenAmount: {
    textAlign: "right" as const,
  },
  tokenBalance: {
    fontWeight: 600,
    fontSize: 13,
    color: C.textPrimary,
  },
  tokenUsd: {
    fontSize: 11,
    color: C.textMuted,
  },
  // Quick actions
  actionsGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 8,
  },
  actionBtn: {
    background: C.card,
    border: `1px solid ${C.border}`,
    borderRadius: 14,
    padding: "12px 10px",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 6,
    color: C.textSecondary,
    fontSize: 12,
    fontWeight: 500,
    transition: "border-color 0.15s",
  },
  actionBtnPrimary: {
    background: `linear-gradient(135deg, rgba(16, 185, 129, 0.18), rgba(52, 211, 153, 0.12))`,
    border: `1px solid rgba(16,185,129,0.24)`,
    borderRadius: 14,
    padding: "12px 10px",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 6,
    color: C.accent,
    fontSize: 12,
    fontWeight: 600,
    gridColumn: "1 / -1",
  },
  actionIcon: {
    fontSize: 20,
  },
  // Status bar
  statusBar: {
    background: C.surface,
    borderTop: `1px solid ${C.border}`,
    padding: "8px 16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    backdropFilter: "blur(20px)",
  },
  statusItem: {
    display: "flex",
    alignItems: "center",
    gap: 5,
    fontSize: 11,
    color: C.textMuted,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: "50%",
  },
};

// ── Mock data ──────────────────────────────────────────────────────────────
const MOCK_TOKENS = [
  { symbol: "BNB",  name: "BNB Chain",  icon: "⬡", color: "#F0B90B", bg: "rgba(45,37,8,0.9)", amount: "0.00",  usd: "$0.00" },
  { symbol: "USDT", name: "Tether USD", icon: "₮", color: "#26A17B", bg: "#0E2722", amount: "0.00",  usd: "$0.00" },
  { symbol: "CAKE", name: "PancakeSwap",icon: "🥞", color: "#D1884F", bg: "#2E1E0E", amount: "0.00",  usd: "$0.00" },
];

export default function App() {
  const [backendOk, setBackendOk] = useState<null | boolean>(null);
  const [walletConnected] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/health", { signal: AbortSignal.timeout(3000) })
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, []);

  return (
    <div style={S.root}>
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header style={S.header}>
        <div style={S.logo}>
          <div style={S.logoIcon}>
            <img src="/ilyon-logo.svg" alt="Ilyon AI" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          </div>
          <span style={S.logoText}>Ilyon AI Beta</span>
        </div>
        <div style={S.networkBadge}>
          <span style={S.netDot} />
          Solana + EVM
        </div>
      </header>

      {/* ── Body ────────────────────────────────────────────────────────── */}
      <div style={S.body}>

        {/* Wallet card */}
        <div style={S.walletCard}>
          {walletConnected ? (
            <>
              <div style={S.walletLabel}>Wallet</div>
              <div style={S.walletAddress}>
                0x742d...3F4a
                <span style={{ fontSize: 10, color: C.accentDim, cursor: "pointer" }}>⎘</span>
              </div>
              <div style={S.balanceRow}>
                <div>
                  <div style={S.balanceMain}>0.00 BNB</div>
                  <div style={S.balanceUsd}>≈ $0.00 USD</div>
                </div>
              </div>
            </>
          ) : (
            <>
              <div style={S.walletLabel}>Connect Wallet</div>
              <div style={{ fontSize: 12, color: C.textMuted, marginBottom: 14, lineHeight: 1.5 }}>
                Connect Phantom or MetaMask to view balances and interact with Solana and EVM DeFi protocols.
              </div>
              <button style={S.connectBtn}>
                <span>🔗</span> Connect Wallet
              </button>
            </>
          )}
        </div>

        {/* Token balances */}
        <div>
          <div style={S.sectionLabel}>Tokens</div>
          {MOCK_TOKENS.map((t) => (
            <div key={t.symbol} style={S.tokenRow}>
              <div style={S.tokenLeft}>
                <div style={{ ...S.tokenIcon, color: t.color, background: t.bg }}>
                  {t.icon}
                </div>
                <div>
                  <div style={S.tokenName}>{t.symbol}</div>
                  <div style={S.tokenNetwork}>{t.name}</div>
                </div>
              </div>
              <div style={S.tokenAmount}>
                <div style={S.tokenBalance}>{t.amount}</div>
                <div style={S.tokenUsd}>{t.usd}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Quick actions */}
        <div>
          <div style={S.sectionLabel}>Quick Actions</div>
          <div style={S.actionsGrid}>
            <button style={S.actionBtnPrimary}>
              <span style={S.actionIcon}>💬</span>
              Open AI Assistant
            </button>
            <button style={S.actionBtn}>
              <span style={S.actionIcon}>⚖️</span>
              Check Balance
            </button>
            <button style={S.actionBtn}>
              <span style={S.actionIcon}>🔄</span>
              Swap Tokens
            </button>
          </div>
        </div>
      </div>

      {/* ── Status bar ──────────────────────────────────────────────────── */}
      <div style={S.statusBar}>
        <div style={S.statusItem}>
          <span style={{
            ...S.statusDot,
            background: backendOk === null ? C.accentDim : backendOk ? C.green : C.red,
          }} />
          {backendOk === null ? "Connecting…" : backendOk ? "Backend online" : "Backend offline"}
        </div>
        <div style={{ ...S.statusItem, color: C.accentDim }}>
          v0.1.0
        </div>
      </div>
    </div>
  );
}
