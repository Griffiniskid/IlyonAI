"use client";

import { useEffect, useState } from "react";

const COINS = [
  { id: "bitcoin", symbol: "BTC" },
  { id: "ethereum", symbol: "ETH" },
  { id: "binancecoin", symbol: "BNB" },
  { id: "solana", symbol: "SOL" },
  { id: "arbitrum", symbol: "ARB" },
  { id: "optimism", symbol: "OP" },
  { id: "tether", symbol: "USDT" },
  { id: "pancakeswap-token", symbol: "CAKE" },
];

interface PriceRow {
  symbol: string;
  price: number;
  change24h: number;
}

async function fetchPrices(): Promise<PriceRow[]> {
  const ids = COINS.map((c) => c.id).join(",");
  const r = await fetch(
    `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true`,
    { signal: AbortSignal.timeout(8000) },
  );
  if (!r.ok) return [];
  const data = (await r.json()) as Record<string, { usd: number; usd_24h_change: number }>;
  return COINS.map((c) => ({
    symbol: c.symbol,
    price: data[c.id]?.usd ?? 0,
    change24h: data[c.id]?.usd_24h_change ?? 0,
  })).filter((row) => row.price > 0);
}

function formatPrice(n: number): string {
  if (n >= 1000) return `$${Math.round(n).toLocaleString()}`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  return `$${n.toFixed(4)}`;
}

export function MarketTickerBar() {
  const [rows, setRows] = useState<PriceRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const r = await fetchPrices();
      if (!cancelled && r.length) setRows(r);
    };
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!rows.length) {
    return <div className="h-8 border-b border-border/50 bg-background/80 backdrop-blur" aria-hidden />;
  }

  // Duplicate the list so the marquee loops smoothly
  const doubled = [...rows, ...rows];

  return (
    <div className="fixed top-0 left-0 right-0 h-8 overflow-hidden border-b border-border/50 bg-background/80 backdrop-blur" style={{ zIndex: 9999 }}>
      <div className="flex h-full animate-[ticker_60s_linear_infinite] items-center whitespace-nowrap will-change-transform">
        {doubled.map((row, i) => {
          const up = row.change24h >= 0;
          return (
            <div key={`${row.symbol}-${i}`} className="flex items-center gap-2 px-4 text-[11px] font-medium">
              <span className="text-muted-foreground">{row.symbol}</span>
              <span className="text-foreground">{formatPrice(row.price)}</span>
              <span className={up ? "text-emerald-400" : "text-rose-400"}>
                {up ? "▲" : "▼"} {Math.abs(row.change24h).toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
      <style jsx global>{`
        @keyframes ticker {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  );
}
