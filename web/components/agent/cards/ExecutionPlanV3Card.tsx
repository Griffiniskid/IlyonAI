"use client";

import { useEffect, useRef, useState } from "react";
import type { ExecutionPlanV3Payload, ExecutionPlanV3Step, ExecutionPlanV3Blocker } from "@/types/agent";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock, LockKeyhole, Play, Power, Route, ShieldAlert, Wallet, Zap } from "lucide-react";

interface Props {
  payload: ExecutionPlanV3Payload;
  onSignStep?: (planId: string, stepId: string) => void;
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-amber-300/15 bg-amber-300/[0.055] p-3">
      <div className="text-[10px] uppercase tracking-[0.18em] text-amber-100/55">{label}</div>
      <div className="mt-1 text-lg font-black text-white">{value}</div>
      {sub && <div className="text-[11px] text-amber-100/45">{sub}</div>}
    </div>
  );
}

function statusBadge(status: ExecutionPlanV3Step["status"]): { label: string; className: string } {
  if (status === "confirmed") return { label: "Confirmed", className: "border-emerald-300/30 bg-emerald-300/10 text-emerald-100" };
  if (status === "submitted") return { label: "Submitted", className: "border-cyan-300/30 bg-cyan-300/10 text-cyan-100" };
  if (status === "signing") return { label: "Awaiting Sign", className: "border-amber-300/40 bg-amber-300/10 text-amber-100" };
  if (status === "ready") return { label: "Ready", className: "border-amber-300/40 bg-amber-300/15 text-amber-100" };
  if (status === "failed") return { label: "Failed", className: "border-rose-300/40 bg-rose-300/10 text-rose-100" };
  if (status === "skipped") return { label: "Skipped", className: "border-white/15 bg-white/5 text-slate-300" };
  if (status === "blocked") return { label: "Blocked", className: "border-rose-300/30 bg-rose-300/5 text-rose-100" };
  return { label: "Pending", className: "border-white/10 bg-white/5 text-slate-300" };
}

function StepRow({
  step,
  planId,
  isFirstReady,
  acknowledged,
  needsAcknowledge,
  onSignStep,
}: {
  step: ExecutionPlanV3Step;
  planId: string;
  isFirstReady: boolean;
  acknowledged: boolean;
  needsAcknowledge: boolean;
  onSignStep?: (planId: string, stepId: string) => void;
}) {
  const badge = statusBadge(step.status);
  const canSign = isFirstReady && step.status === "ready" && (!needsAcknowledge || acknowledged);
  return (
    <div data-testid="execution-plan-v3-step" data-step-id={step.step_id} className="relative rounded-3xl border border-white/10 bg-slate-950/55 p-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 gap-3">
          <div className="z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-amber-300/25 bg-amber-300/15 text-sm font-black text-amber-100">
            {step.index}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-base font-black text-white">
              <span className="capitalize">{step.action.replace(/_/g, " ")}</span>
              {step.amount_in && step.asset_in && (
                <span className="text-amber-100">{step.amount_in} {step.asset_in}</span>
              )}
              <ArrowRight className="h-4 w-4 text-amber-200/40" />
              <span className="truncate text-slate-100">{step.title}</span>
            </div>
            <div className="mt-1 text-xs text-slate-400">{step.description}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2.5 py-1 text-cyan-100">{step.chain}</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">via {step.protocol}</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">{step.wallet}</span>
              {step.gas_estimate_usd != null && (
                <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">Gas ≈ ${step.gas_estimate_usd.toFixed(2)}</span>
              )}
              {step.slippage_bps != null && (
                <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">Slippage {(step.slippage_bps / 100).toFixed(2)}%</span>
              )}
            </div>
            {step.risk_warnings && step.risk_warnings.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-xs text-amber-200/80">
                {step.risk_warnings.map((warn, idx) => (
                  <li key={idx}>⚠ {warn}</li>
                ))}
              </ul>
            )}
            {step.receipt && (step.receipt as { tx_hash?: string }).tx_hash && (
              <div className="mt-2 text-xs text-emerald-200/80">
                Receipt: {(step.receipt as { tx_hash?: string }).tx_hash}
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className={`inline-flex items-center gap-1 rounded-2xl border px-3 py-1.5 text-xs font-bold ${badge.className}`}>
            <LockKeyhole className="h-3.5 w-3.5" /> {badge.label}
          </span>
          {step.status === "ready" && isFirstReady && onSignStep && (
            <button
              type="button"
              data-testid={`sign-step-${step.step_id}`}
              disabled={!canSign}
              onClick={() => onSignStep(planId, step.step_id)}
              className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-amber-300 to-orange-300 px-4 py-2 text-xs font-black text-amber-950 shadow-lg shadow-amber-950/30 transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Play className="h-3.5 w-3.5" /> Sign step {step.index}
            </button>
          )}
          {step.status === "ready" && !isFirstReady && (
            <span className="text-[10px] text-slate-500">unlocks after step {step.index - 1}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function BlockerRow({ blocker }: { blocker: ExecutionPlanV3Blocker }) {
  return (
    <div className="rounded-2xl border border-rose-300/30 bg-rose-300/5 p-3">
      <div className="flex items-center gap-2 text-sm font-black text-rose-100">
        <ShieldAlert className="h-4 w-4" /> {blocker.title}
      </div>
      <div className="mt-1 text-xs text-rose-100/80">{blocker.detail}</div>
      {blocker.cta && <div className="mt-2 text-[11px] text-rose-100/60">{blocker.cta}</div>}
    </div>
  );
}

export function ExecutionPlanV3Card({ payload, onSignStep }: Props) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [autoExecute, setAutoExecute] = useState(false);
  const lastSignedStepIdRef = useRef<string | null>(null);
  const steps = payload.steps || [];
  const totals = payload.totals || ({} as ExecutionPlanV3Payload["totals"]);
  const firstReady = steps.find((step) => step.status === "ready");
  const needsAck = payload.requires_double_confirm || payload.risk_gate !== "clear";
  const allDone = steps.length > 0 && steps.every((step) => step.status === "confirmed" || step.status === "skipped");
  const hasFailed = steps.some((step) => step.status === "failed");

  useEffect(() => {
    if (!autoExecute || !onSignStep || !firstReady || hasFailed) return;
    if (needsAck && !acknowledged) return;
    if (lastSignedStepIdRef.current === firstReady.step_id) return;
    lastSignedStepIdRef.current = firstReady.step_id;
    onSignStep(payload.plan_id, firstReady.step_id);
  }, [autoExecute, firstReady, hasFailed, needsAck, acknowledged, onSignStep, payload.plan_id]);

  useEffect(() => {
    if (allDone || hasFailed) {
      setAutoExecute(false);
    }
  }, [allDone, hasFailed]);

  return (
    <div data-testid="execution-plan-v3-card" data-plan-id={payload.plan_id} className="relative overflow-hidden rounded-[28px] border border-amber-300/25 bg-[#1b1205]/95 shadow-[0_28px_100px_rgba(245,158,11,0.16)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(251,191,36,0.22),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(168,85,247,0.18),transparent_34%)]" />
      <div className="relative border-b border-white/10 p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-amber-100">
              <Zap className="h-3.5 w-3.5" /> {payload.title || "Execution Plan"}
            </div>
            <div className="text-2xl font-black tracking-tight text-white">{payload.summary}</div>
            {payload.research_thesis && (
              <div className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">{payload.research_thesis}</div>
            )}
          </div>
          <div className="flex items-center gap-3 rounded-3xl border border-amber-300/25 bg-amber-300/10 px-4 py-3">
            <Wallet className="h-7 w-7 text-amber-200" />
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-amber-100/60">Signatures</div>
              <div className="text-3xl font-black text-white">{totals.signatures_required ?? steps.length}</div>
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <StatTile label="Status" value={payload.status} />
          <StatTile label="Risk gate" value={payload.risk_gate} />
          <StatTile label="Total Gas" value={totals.estimated_gas_usd ? `$${totals.estimated_gas_usd.toFixed(2)}` : "-"} />
          <StatTile
            label="Chains"
            value={(totals.chains_touched || []).join(" + ") || "-"}
            sub={`${totals.estimated_duration_s ?? 0}s ETA`}
          />
        </div>
      </div>

      {payload.blockers && payload.blockers.length > 0 && (
        <div className="relative space-y-2 border-b border-white/10 p-5">
          <div className="text-sm font-black text-rose-100">Execution Blocked</div>
          {payload.blockers.map((blocker) => (
            <BlockerRow key={blocker.code} blocker={blocker} />
          ))}
          <div className="text-[11px] text-rose-100/60">
            No signing button is shown until every blocker is resolved.
          </div>
        </div>
      )}

      <div className="relative p-5">
        <div className="mb-3 flex items-center gap-2 text-sm font-black text-white"><Route className="h-4 w-4 text-amber-200" /> Ordered route</div>
        <div className="space-y-3">
          {steps.map((step) => (
            <StepRow
              key={step.step_id}
              step={step}
              planId={payload.plan_id}
              isFirstReady={firstReady?.step_id === step.step_id}
              acknowledged={acknowledged}
              needsAcknowledge={needsAck}
              onSignStep={onSignStep}
            />
          ))}
        </div>

        {needsAck && firstReady && (
          <label data-testid="risk-acknowledgement" className="mt-4 flex items-center gap-2 rounded-2xl border border-amber-300/25 bg-amber-300/10 p-3 text-xs text-amber-100">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              className="h-4 w-4 rounded border-amber-300/50 bg-transparent"
            />
            I understand this is a {payload.risk_gate.replace("_", " ")} strategy and accept the listed risks before signing.
          </label>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          {steps.length > 1 && firstReady && !allDone && !hasFailed && (
            <button
              type="button"
              data-testid="execute-all"
              onClick={() => setAutoExecute((value) => !value)}
              disabled={needsAck && !acknowledged}
              className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-xs font-black transition disabled:cursor-not-allowed disabled:opacity-40 ${
                autoExecute
                  ? "border-rose-300/40 bg-rose-300/15 text-rose-100 hover:bg-rose-300/25"
                  : "border-amber-300/30 bg-amber-300/10 text-amber-100 hover:bg-amber-300/20"
              }`}
            >
              <Power className="h-3.5 w-3.5" />
              {autoExecute ? "Pause auto-execute" : "Execute all (auto-advance)"}
            </button>
          )}
          {autoExecute && (
            <span className="text-[11px] text-amber-100/70">
              Auto-advancing through steps. Each one still pops your wallet for a real signature.
            </span>
          )}
        </div>

        <div className="mt-3 rounded-3xl border border-white/10 bg-white/[0.035] p-4 text-xs text-slate-300">
          <div className="flex flex-wrap items-center gap-3">
            <AlertTriangle className="h-4 w-4 text-amber-300" /> Each step is wallet-gated and only the next ready step can be signed.
            <CheckCircle2 className="h-4 w-4 text-emerald-300" /> Later steps unlock after on-chain receipt verification.
          </div>
        </div>
      </div>
    </div>
  );
}
