import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASSISTANT_API_TARGET = process.env.ASSISTANT_API_TARGET || "http://localhost:8000";
const SENTINEL_API_TARGET = process.env.SENTINEL_API_TARGET || "http://localhost:8080";
const REQUEST_TIMEOUT_MS = 180_000;

export type BackendKind = "wallet" | "sentinel";

function forcedBackend(): BackendKind | null {
  const backend = process.env.AGENT_BACKEND;
  return backend === "wallet" || backend === "sentinel" ? backend : null;
}

function textFromAgentBody(body: string): string {
  try {
    const parsed = JSON.parse(body);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return body;
    const obj = parsed as Record<string, unknown>;
    return String(obj.query || obj.message || obj.input || "");
  } catch {
    return body;
  }
}

export function _selectBackendTarget(body: string): BackendKind {
  const q = textFromAgentBody(body).toLowerCase();
  if (/\b(sentinel|allocation|allocate|rebalance|methodology|risk[- ]?weighted|scor(?:e|ing))\b/.test(q)) {
    return "sentinel";
  }
  const poolOrStrategy = /\b(pool|pools|farm|farms|vault|vaults|opportunit(?:y|ies)|add liquidity|liquidity deposit)\b|\b(?:put|deposit)\b.*\b(?:pool|farm|vault)\b/.test(q);
  const directWalletExecution = /\b(swap|bridge|cross[- ]?chain|transfer|send)\b/.test(q) || (/\b(stake|staking)\b/.test(q) && !poolOrStrategy);
  if (directWalletExecution) {
    return "wallet";
  }
  if (poolOrStrategy || /\b(yield|apy|apr)\b/.test(q)) {
    return "sentinel";
  }
  if (/\bdeposit\b/.test(q)) return "wallet";
  return "sentinel";
}

export function _resolveBackendTarget(selected?: BackendKind): string {
  const backend = forcedBackend() ?? selected ?? "sentinel";
  if (backend === "wallet") {
    return process.env.ASSISTANT_API_TARGET || "http://localhost:8000";
  }
  return process.env.SENTINEL_API_TARGET || "http://localhost:8080";
}

function upstreamHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");

  headers.set("content-type", contentType || "application/json");
  if (authorization) headers.set("authorization", authorization);
  if (cookie) headers.set("cookie", cookie);
  return headers;
}

function normalizeAgentBody(body: string): string {
  try {
    const parsed = JSON.parse(body);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return body;
    const next = { ...parsed } as Record<string, unknown>;
    if (typeof next.message !== "string" && typeof next.query === "string") {
      next.message = next.query;
    }
    if (typeof next.wallet !== "string" && typeof next.user_address === "string") {
      next.wallet = next.user_address;
    }
    return JSON.stringify(next);
  } catch {
    return body;
  }
}

export async function POST(request: NextRequest): Promise<Response> {
  const body = normalizeAgentBody(await request.text());
  const selected = _selectBackendTarget(body);
  const target = _resolveBackendTarget(selected);
  const upstream = await fetch(`${target}/api/v1/agent`, {
    method: "POST",
    headers: upstreamHeaders(request),
    body,
    cache: "no-store",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: {
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": upstream.headers.get("content-type")?.includes("text/event-stream") ? "no-cache, no-transform" : "no-store",
      "x-accel-buffering": "no",
    },
  });
}
