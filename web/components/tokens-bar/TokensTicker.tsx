"use client";
import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Shield } from "lucide-react";

interface Token {
  symbol: string;
  price_usd: string;
  change_24h_pct: number;
  sentinel_lite: { score: number; badge: string };
}

export function TokensTicker() {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    const fetchTokens = async () => {
      try {
        const r = await fetch("/api/v1/tokens/ticker");
        if (r.ok) {
          const d = await r.json();
          setTokens(d.tokens || []);
        }
      } catch {}
    };
    fetchTokens();
    const interval = setInterval(fetchTokens, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY < 100);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (!tokens.length || !visible) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-slate-900/95 border-b border-slate-800 h-8 overflow-hidden">
      <div className="flex items-center h-full px-4 gap-6 animate-marquee">
        {tokens.map((t) => (
          <div key={t.symbol} className="flex items-center gap-1 text-xs whitespace-nowrap">
            <span className="font-semibold text-slate-200">{t.symbol}</span>
            <span className="text-slate-400">${t.price_usd}</span>
            <span className={t.change_24h_pct >= 0 ? "text-green-400" : "text-red-400"}>
              {t.change_24h_pct >= 0 ? <TrendingUp className="inline h-3 w-3" /> : <TrendingDown className="inline h-3 w-3" />}
              {Math.abs(t.change_24h_pct).toFixed(1)}%
            </span>
            <Shield className={`inline h-3 w-3 ${t.sentinel_lite.badge === "safe" ? "text-green-400" : t.sentinel_lite.badge === "caution" ? "text-yellow-400" : "text-red-400"}`} />
          </div>
        ))}
      </div>
    </div>
  );
}
