"use client";

import { useEffect, useState } from "react";

interface Coin {
  id: string;
  symbol: string;
  chain: string;
  price: number | null;
  change: number | null;
}

const COINS: Coin[] = [
  { id: "solana", symbol: "SOL", chain: "Solana", price: null, change: null },
  { id: "ethereum", symbol: "ETH", chain: "Ethereum", price: null, change: null },
  { id: "binancecoin", symbol: "BNB", chain: "BNB Chain", price: null, change: null },
  { id: "tether", symbol: "USDT", chain: "Tether", price: null, change: null },
];

function fmt(n: number | null) {
  if (n === null) return "—";
  if (n < 1) return `$${n.toFixed(4)}`;
  if (n < 100) return `$${n.toFixed(2)}`;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function SidebarMarketList() {
  const [coins, setCoins] = useState<Coin[]>(COINS);

  useEffect(() => {
    let stop = false;
    const ids = COINS.map((c) => c.id).join(",");
    const fetchPrices = async () => {
      try {
        const r = await fetch(
          `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true`,
          { cache: "no-store" },
        );
        if (!r.ok) return;
        const data = (await r.json()) as Record<string, { usd: number; usd_24h_change?: number }>;
        if (stop) return;
        setCoins(
          COINS.map((c) => ({
            ...c,
            price: data[c.id]?.usd ?? null,
            change: data[c.id]?.usd_24h_change ?? null,
          })),
        );
      } catch {
        /* ignore network blips */
      }
    };
    fetchPrices();
    const id = window.setInterval(fetchPrices, 60_000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="flex flex-col gap-2">
      <h4 className="px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">Market</h4>
      <div className="flex flex-col gap-1">
        {coins.map((c) => (
          <a
            key={c.symbol}
            href={`/agent/chat?tab=chat&prompt=${encodeURIComponent(`Show me ${c.symbol} price`)}`}
            className="flex items-center justify-between rounded-md px-3 py-2 text-xs hover:bg-secondary"
          >
            <div>
              <div className="font-semibold text-foreground">{c.symbol}</div>
              <div className="text-[10px] text-muted-foreground">{c.chain}</div>
            </div>
            <div className="text-right">
              <div className="font-mono text-foreground">{fmt(c.price)}</div>
              {c.change !== null && (
                <div className={`text-[10px] font-mono ${c.change >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {c.change >= 0 ? "▲" : "▼"} {Math.abs(c.change).toFixed(2)}%
                </div>
              )}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
