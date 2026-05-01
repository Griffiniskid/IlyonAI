import type { StepStatusFrame } from "@/types/agent";

const statusTone: Record<StepStatusFrame["status"], string> = {
  pending: "text-slate-300 bg-slate-500/15 border-slate-500/30",
  ready: "text-cyan-300 bg-cyan-500/15 border-cyan-500/30",
  signing: "text-purple-300 bg-purple-500/15 border-purple-500/30",
  broadcast: "text-blue-300 bg-blue-500/15 border-blue-500/30",
  confirmed: "text-emerald-300 bg-emerald-500/15 border-emerald-500/30",
  failed: "text-red-300 bg-red-500/15 border-red-500/30",
  skipped: "text-yellow-300 bg-yellow-500/15 border-yellow-500/30",
};

export function StepStatusCard({ frame }: { frame: StepStatusFrame }) {
  return (
    <div
      data-testid="step-status-card"
      className="rounded-xl border border-slate-700/80 bg-slate-800/60 px-4 py-3 shadow-lg"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Step {frame.order}</div>
          <div className="mt-1 text-sm font-medium text-white">{frame.step_id.replace(/_/g, " ")}</div>
        </div>
        <span className={`rounded-md border px-2 py-1 text-xs font-semibold ${statusTone[frame.status]}`}>
          {frame.status}
        </span>
      </div>
      {frame.tx_hash ? <div className="mt-2 truncate font-mono text-xs text-slate-400">{frame.tx_hash}</div> : null}
      {frame.error ? <div className="mt-2 text-xs text-red-300">{frame.error}</div> : null}
    </div>
  );
}
