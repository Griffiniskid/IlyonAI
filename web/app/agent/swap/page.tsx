"use client";
import { useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import type { SwapQuotePayload } from "@/types/agent";

export default function AgentSwapPage() {
  const { publicKey } = useWallet();
  const [tokenIn, setTokenIn] = useState("");
  const [tokenOut, setTokenOut] = useState("");
  const [amount, setAmount] = useState("");
  const [quote, setQuote] = useState<SwapQuotePayload | null>(null);
  const [loading, setLoading] = useState(false);

  const handleQuote = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v1/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: crypto.randomUUID(),
          message: `Simulate swap ${amount} ${tokenIn} for ${tokenOut}`,
          wallet: publicKey?.toBase58(),
        }),
      });
      // Parse SSE response for card data
      const text = await r.text();
      // Extract the last card frame
      const lines = text.split("\n");
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.card_type === "swap_quote") setQuote(data.payload || data.card_payload);
          } catch { /* skip unparseable lines */ }
        }
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto p-8">
      <h1 className="text-2xl font-bold text-white mb-6">Swap Tokens</h1>
      <div className="space-y-4 bg-slate-800 rounded-lg p-6">
        <div>
          <label className="text-sm text-slate-400">Token In</label>
          <input value={tokenIn} onChange={(e) => setTokenIn(e.target.value)}
            className="w-full mt-1 bg-slate-700 rounded px-3 py-2 text-white" placeholder="SOL" />
        </div>
        <div>
          <label className="text-sm text-slate-400">Token Out</label>
          <input value={tokenOut} onChange={(e) => setTokenOut(e.target.value)}
            className="w-full mt-1 bg-slate-700 rounded px-3 py-2 text-white" placeholder="USDC" />
        </div>
        <div>
          <label className="text-sm text-slate-400">Amount</label>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} type="number"
            className="w-full mt-1 bg-slate-700 rounded px-3 py-2 text-white" placeholder="1.0" />
        </div>
        <button onClick={handleQuote} disabled={loading || !tokenIn || !tokenOut || !amount}
          className="w-full py-2 rounded-lg bg-blue-600 text-white font-medium disabled:opacity-50 hover:bg-blue-700">
          {loading ? "Quoting..." : "Get Quote"}
        </button>
        {quote && (
          <div className="mt-4 p-4 border border-slate-600 rounded-lg">
            <pre className="text-xs text-slate-300">{JSON.stringify(quote, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
