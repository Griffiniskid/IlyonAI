import React, { useState, useRef, useEffect } from "react";

// ── Design tokens ──────────────────────────────────────────────────────────
const C = {
  bg:        "hsl(222 47% 4%)",
  surface:   "rgba(8, 15, 28, 0.82)",
  card:      "rgba(15, 23, 42, 0.78)",
  border:    "rgba(255,255,255,0.08)",
  accent:    "#10b981",
  accentDim: "rgba(16,185,129,0.24)",
  green:     "#34d399",
  red:       "#f87171",
  blue:      "#60a5fa",
  textPrimary:   "hsl(210 40% 98%)",
  textSecondary: "hsl(215 20% 65%)",
  textMuted:     "rgba(148,163,184,0.55)",
};

// ── Types ──────────────────────────────────────────────────────────────────
type Role = "user" | "assistant";

interface Message {
  id: number;
  role: Role;
  text: string;
  ts: Date;
}

// ── Role-dependent style helpers ───────────────────────────────────────────
function msgWrapStyle(role: Role): React.CSSProperties {
  return {
    display: "flex",
    flexDirection: role === "user" ? "row-reverse" : "row",
    alignItems: "flex-end",
    gap: 8,
  };
}

function avatarStyle(role: Role): React.CSSProperties {
  return {
    width: 28,
    height: 28,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 13,
    fontWeight: 700,
    flexShrink: 0,
    background: role === "user" ? "rgba(16,185,129,0.15)" : "rgba(139,92,246,0.15)",
    color: role === "user" ? C.accent : C.blue,
    border: `1px solid ${role === "user" ? C.accentDim : "rgba(139,92,246,0.24)"}`,
  };
}

function bubbleStyle(role: Role): React.CSSProperties {
  return {
    maxWidth: "78%",
    padding: "10px 14px",
    borderRadius: role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
    background: role === "user" ? "rgba(16,185,129,0.12)" : C.card,
    border: `1px solid ${role === "user" ? C.accentDim : C.border}`,
    fontSize: 13,
    lineHeight: 1.55,
    color: C.textPrimary,
    wordBreak: "break-word",
    whiteSpace: "pre-wrap",
  };
}

// ── Static styles ──────────────────────────────────────────────────────────
const S: Record<string, React.CSSProperties> = {
  root: {
    width: "100%",
    height: "100vh",
    background: C.bg,
    color: C.textPrimary,
    fontFamily: "Inter, 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif",
    fontSize: 13,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  header: {
    background: C.surface,
    borderBottom: `1px solid ${C.border}`,
    padding: "12px 16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexShrink: 0,
    backdropFilter: "blur(20px)",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 10 },
  logoIcon: {
    width: 26,
    height: 26,
    borderRadius: 7,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    fontSize: 13,
    fontWeight: 700,
    color: "#0D1117",
  },
  logoText: { fontSize: 14, fontWeight: 700, letterSpacing: "-0.2px" },
  networkPill: {
    background: C.card,
    border: `1px solid ${C.border}`,
    borderRadius: 20,
    padding: "2px 9px",
    fontSize: 11,
    color: C.textSecondary,
    display: "flex",
    alignItems: "center",
    gap: 5,
  },
  netDot: { width: 6, height: 6, borderRadius: "50%", background: C.green },
  portfolioStrip: {
    background: C.surface,
    borderBottom: `1px solid ${C.border}`,
    padding: "8px 16px",
    display: "flex",
    gap: 16,
    flexShrink: 0,
    overflowX: "auto",
  },
  portfolioItem: {
    display: "flex",
    flexDirection: "column",
    minWidth: 70,
  },
  portfolioLabel: {
    fontSize: 10,
    color: C.textMuted,
    letterSpacing: "0.6px",
    textTransform: "uppercase",
  },
  portfolioValue: { fontSize: 13, fontWeight: 600, color: C.textPrimary, marginTop: 2 },
  portfolioSub: { fontSize: 10, color: C.textMuted, marginTop: 1 },
  chatArea: {
    flex: 1,
    overflowY: "auto",
    padding: "16px",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  tsLabel: {
    fontSize: 10,
    color: C.textMuted,
    marginTop: 4,
    paddingInline: 2,
  },
  quickActions: {
    padding: "8px 16px",
    display: "flex",
    gap: 6,
    flexShrink: 0,
    borderTop: `1px solid ${C.border}`,
    background: C.surface,
    overflowX: "auto",
  },
  quickBtn: {
    background: C.card,
    border: `1px solid ${C.border}`,
    borderRadius: 20,
    padding: "5px 12px",
    fontSize: 11,
    color: C.textSecondary,
    cursor: "pointer",
    whiteSpace: "nowrap",
    fontFamily: "inherit",
  },
  inputArea: {
    background: C.surface,
    borderTop: `1px solid ${C.border}`,
    padding: "12px 16px",
    flexShrink: 0,
  },
  inputRow: {
    display: "flex",
    gap: 8,
    alignItems: "flex-end",
  },
  textarea: {
    flex: 1,
    background: C.card,
    border: `1px solid ${C.border}`,
    borderRadius: 10,
    padding: "10px 12px",
    fontSize: 13,
    color: C.textPrimary,
    fontFamily: "inherit",
    resize: "none",
    outline: "none",
    lineHeight: 1.5,
    maxHeight: 120,
    overflowY: "auto",
  },
  sendBtn: {
    width: 38,
    height: 38,
    background: `linear-gradient(135deg, ${C.accent}, #34d399)`,
    border: "none",
    borderRadius: 12,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 18,
    color: "#03150f",
    fontWeight: 700,
    flexShrink: 0,
  },
  sendBtnDisabled: {
    background: C.border,
    cursor: "not-allowed",
    color: C.textMuted,
  },
  inputHint: {
    fontSize: 10,
    color: C.textMuted,
    marginTop: 6,
    textAlign: "center",
  },
  typingDots: {
    display: "flex",
    gap: 4,
    padding: "6px 2px",
    alignItems: "center",
  },
};

// ── Typing animation ───────────────────────────────────────────────────────
function TypingDots() {
  return (
    <div style={S.typingDots}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: C.textMuted,
            display: "inline-block",
            animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </div>
  );
}

const QUICK_PROMPTS = [
  "📊 SOL price",
  "💰 Check balance",
  "🔄 Swap SOL → USDC",
  "🌊 SOL pools",
  "⛽ Gas fees",
];

const WELCOME: Message = {
  id: 0,
  role: "assistant",
  text: "👋 Hello! I'm your AI crypto assistant for Solana and the leading EVM chains.\n\nI can help you:\n• Check wallet balances across Solana and EVM\n• Get real-time token prices (SOL, ETH, BNB, USDT…)\n• Simulate and build swap transactions\n• Explore liquidity pools and bridge routes\n\nConnect your wallet and start chatting! 🚀",
  ts: new Date(),
};

let nextId = 1;

// ── Main component ─────────────────────────────────────────────────────────
export default function SidePanel() {
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [backendOk, setBackendOk] = useState<null | boolean>(null);
  const [walletAddress, setWalletAddress] = useState<string>(() => localStorage.getItem("ap_wallet") || "");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Keep wallet in sync if user connects/disconnects in another tab
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "ap_wallet") setWalletAddress(e.newValue || "");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  useEffect(() => {
    fetch("http://localhost:8000/health", { signal: AbortSignal.timeout(3000) })
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = textareaRef.current;
    if (el) { el.style.height = "auto"; el.style.height = `${el.scrollHeight}px`; }
  };

  const sendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMsg: Message = { id: nextId++, role: "user", text: trimmed, ts: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setLoading(true);

    try {
      const res = await fetch("http://localhost:8000/api/v1/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: trimmed,
          session_id: "sidepanel-session",
          user_address: walletAddress,
          chain_id: 56,
        }),
      });

      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      setMessages((prev) => [...prev, {
        id: nextId++,
        role: "assistant",
        text: data.response || "*(empty response)*",
        ts: new Date(),
      }]);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [...prev, {
        id: nextId++,
        role: "assistant",
        text: backendOk === false
          ? "⚠️ Cannot reach the backend server.\n\nMake sure it's running:\n```\n./start-server.sh\n```"
          : `❌ Error: ${errMsg}`,
        ts: new Date(),
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const formatTime = (d: Date) =>
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const statusColor = backendOk === null ? C.accentDim : backendOk ? C.green : C.red;
  const statusLabel = backendOk === null ? "Connecting…" : backendOk ? "Backend online" : "Backend offline";

  return (
    <>
      <style>{`
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #30363D; border-radius: 4px; }
        textarea:focus { border-color: #F0B90B !important; }
      `}</style>

      <div style={S.root}>
        {/* Header */}
        <header style={S.header}>
          <div style={S.headerLeft}>
            <div style={S.logoIcon}>
              <img src="/ilyon-logo.svg" alt="Ilyon AI" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            </div>
            <span style={S.logoText}>Ilyon AI Beta</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={S.networkPill}>
              <span style={S.netDot} />
              Solana + EVM
            </div>
            <div
              title={statusLabel}
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: statusColor,
                boxShadow: backendOk ? `0 0 6px ${C.green}` : "none",
              }}
            />
          </div>
        </header>

        {/* Portfolio strip */}
        <div style={S.portfolioStrip}>
          {[
            { label: "Wallet",  value: "Not connected", sub: "" },
            { label: "Network", value: "Solana + EVM",  sub: "Multi-chain" },
            { label: "BNB",     value: "$—",            sub: "0.00 BNB" },
            { label: "CAKE",    value: "$—",            sub: "PancakeSwap" },
          ].map((item) => (
            <div key={item.label} style={S.portfolioItem}>
              <div style={S.portfolioLabel}>{item.label}</div>
              <div style={S.portfolioValue}>{item.value}</div>
              {item.sub && <div style={S.portfolioSub}>{item.sub}</div>}
            </div>
          ))}
        </div>

        {/* Chat messages */}
        <div style={S.chatArea}>
          {messages.map((msg) => (
            <div key={msg.id} style={msgWrapStyle(msg.role)}>
              <div style={avatarStyle(msg.role)}>
                {msg.role === "user" ? "U" : "A"}
              </div>
              <div>
                <div style={bubbleStyle(msg.role)}>{msg.text}</div>
                <div style={{
                  ...S.tsLabel,
                  textAlign: msg.role === "user" ? "right" : "left",
                }}>
                  {formatTime(msg.ts)}
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div style={msgWrapStyle("assistant")}>
              <div style={avatarStyle("assistant")}>A</div>
              <div style={{ ...bubbleStyle("assistant"), paddingBlock: 8 }}>
                <TypingDots />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Quick prompts */}
        <div style={S.quickActions}>
          {QUICK_PROMPTS.map((p) => (
            <button key={p} style={S.quickBtn} onClick={() => sendMessage(p)}>
              {p}
            </button>
          ))}
        </div>

        {/* Input */}
        <div style={S.inputArea}>
          <div style={S.inputRow}>
            <textarea
              ref={textareaRef}
              style={S.textarea}
              rows={1}
              placeholder="Ask anything about Solana or multi-chain DeFi…"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button
              style={{
                ...S.sendBtn,
                ...(!input.trim() || loading ? S.sendBtnDisabled : {}),
              }}
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || loading}
            >
              ↑
            </button>
          </div>
          <div style={S.inputHint}>Enter to send · Shift+Enter for new line</div>
        </div>
      </div>
    </>
  );
}
