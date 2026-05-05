"use client";

import type { SentinelEntityCardPayload } from "@/types/agent";
import { Building2, Search } from "lucide-react";

interface Props { payload: SentinelEntityCardPayload }

export function SentinelEntityCard({ payload }: Props) {
  return (
    <div data-testid="sentinel-entity-card" className="relative overflow-hidden rounded-[28px] border border-indigo-300/20 bg-[#0a0d2a]/95 p-5 shadow-[0_18px_70px_rgba(99,102,241,0.12)]">
      <div className="inline-flex items-center gap-2 rounded-full border border-indigo-300/25 bg-indigo-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-indigo-100">
        <Building2 className="h-3.5 w-3.5" /> Sentinel Entity
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Search className="h-3.5 w-3.5 text-slate-400" />
        <span className="text-xs text-slate-400">Query:</span>
        <code className="text-xs text-slate-200">{payload.query}</code>
      </div>

      {payload.empty ? (
        <div className="mt-4 rounded-2xl border border-amber-300/25 bg-amber-300/5 p-3 text-xs text-amber-100">
          {payload.empty_reason || `No Sentinel-tagged entity profile matches "${payload.query}" yet. Try an exact 0x… or Solana mint instead.`}
        </div>
      ) : (
        <>
          <div className="mt-3 text-base font-black text-white">{payload.name || payload.query}</div>
          {payload.description && <div className="mt-1.5 text-xs text-slate-300">{payload.description}</div>}
          {payload.tags && payload.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {payload.tags.slice(0, 12).map((t, i) => (
                <span key={i} className="rounded-full border border-cyan-300/25 bg-cyan-300/10 px-2 py-0.5 text-[10px] text-cyan-100">{t}</span>
              ))}
            </div>
          )}
          {payload.addresses && payload.addresses.length > 0 && (
            <div className="mt-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1.5">Linked addresses ({payload.addresses.length})</div>
              <div className="space-y-1">
                {payload.addresses.slice(0, 8).map((a, i) => (
                  <code key={i} className="block break-all text-[11px] text-slate-200">{a}</code>
                ))}
                {payload.addresses.length > 8 && <div className="text-[10px] text-slate-500">+ {payload.addresses.length - 8} more</div>}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
