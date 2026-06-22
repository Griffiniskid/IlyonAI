import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASSISTANT_API_TARGET = process.env.ASSISTANT_API_TARGET || "http://localhost:8000";
const SENTINEL_API_TARGET = process.env.SENTINEL_API_TARGET || "http://localhost:8080";
// Backstop only — catches a genuinely hung request so the user gets a friendly
// message instead of an infinite spinner. Kept generous so it never truncates a
// legitimately slow Sentinel query (balance/analysis/allocation can stream for a
// while). The wallet reasoning path is bounded separately by the backend agent's
// own 35s self-stop, so this does NOT need to be aggressive.
const REQUEST_TIMEOUT_MS = 90_000;

// When the agent genuinely can't complete a request (backend error, timeout, or
// it's unreachable) we never want the user to see a raw "Server error 500" chip.
// Instead we return a normal, conversational assistant message (HTTP 200) that
// explains what happened and points to things the agent can actually do.
const FRIENDLY_TIMEOUT =
  "That one took me longer than I could finish in time. Mind trying again? If it's a multi-step idea, tell me the exact tokens and amounts — e.g. “Swap 5 SOL to USDC” — and I'll build it one safe step at a time.";
const FRIENDLY_GENERIC =
  "I started working on that but couldn't finish it cleanly, so I stopped rather than guess. This usually means the request was too open-ended for me to execute safely — I can't chase speculative profit or invent a trade plan for you. Here's what I can do right now: check live token prices, show your balance, find the best pools, or build a specific swap, bridge, or stake. Try something like “Swap 5 SOL to USDC”, “Best SOL pool”, or “My balance”.";
const FRIENDLY_UNREACHABLE =
  "I couldn't reach my reasoning engine just now. Give me a few seconds and try again — if it keeps happening the service may be restarting.";

function friendlyResponse(message: string): Response {
  // Shaped like a normal agent JSON reply so the frontend renders it as a
  // regular assistant message, not an error. `degraded` lets the UI tag it.
  return new Response(JSON.stringify({ response: message, degraded: true }), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

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

// In-process session→backend affinity: an ambiguous follow-up ("yes do that",
// "ok", "the first one") must stay on the backend that holds the conversation
// (and its chat memory). Otherwise it falls back to the sentinel, which has no
// context, and the thread is lost.
type Affinity = { backend: BackendKind; ts: number };
const _sessionBackend = new Map<string, Affinity>();
const AFFINITY_TTL_MS = 30 * 60 * 1000;

function sessionIdFromBody(body: string): string {
  try {
    const o = JSON.parse(body) as Record<string, unknown>;
    return String(o.session_id || o.chat_id || "");
  } catch {
    return "";
  }
}

// True when a message only makes sense as a continuation of the prior turn
// (short affirmation / pronoun follow-up with no actionable DeFi keyword).
export function _isAmbiguousFollowup(text: string): boolean {
  const q = (text || "").trim().toLowerCase();
  if (!q) return false;
  if (/^(yes|yep|yeah|yup|ok|okay|sure|sounds good|go ahead|please do|do it|do that|yes do that|yes please|that one|the (first|second|third|last) one|continue|proceed|go on)\b/.test(q)) {
    return true;
  }
  const hasSignal =
    /\b(swap|bridge|cross[- ]?chain|un[-\s]?stake|stake|staking|redeem|transfer|send|deposit|pool|farm|vault|yield|apy|apr|price|balance|analy[sz]e|safe|rug|scan|audit|holders?|allocat|rebalance)\b/.test(q) ||
    /0x[a-f0-9]{6,}|[1-9A-HJ-NP-Za-km-z]{32,}/.test(q);
  // very short + keyword-free → treat as a contextual continuation
  return q.split(/\s+/).length <= 4 && !hasSignal;
}

// Analytical / advice / "what-if" questions. These must be REASONED by a chat
// LLM, not handled by the execution agent (which can dump links or build a tx).
// The sentinel answers them in a single, reliable LLM call.
const _REASONING_RE =
  /\b(should\s+i|shall\s+i|do\s+you\s+(?:think|recommend|reckon)|what\s+do\s+you\s+think|is\s+it\s+worth|worth\s+it|is\s+it\s+a\s+good\s+idea|good\s+idea|bad\s+idea|what\s+happens|what\s+would\s+happen|what\s+if|happens\s+if|how\s+much|how\s+many|how\s+long|why\s+(?:did|do|does|is|are|should|would|wouldn|can|cant|not)|can\s+i\s+(?:lose|still|really|even|safely)|could\s+i|would\s+it|is\s+it\s+safe|is\s+it\s+better|is\s+it\s+smart|is\s+it\s+risky|what.?s\s+the\s+(?:catch|risk|downside|point)|pros\s+and\s+cons|trade-?offs?|which\s+is\s+(?:better|safer|best)|compare|explain|help\s+me\s+(?:decide|understand|choose)|what\s+should\s+i\s+do|makes?\s+sense|pointless|too\s+(?:small|little|risky|much)|eat\s+(?:the|my|up|into)|net\s+of\s+fees|after\s+fees|worth\s+the\s+fees|better\s+to|or\s+(?:should\s+i|just)|safe\s+to|risky\s+to|lose\s+(?:money|funds|my)|where\s+(?:can|do)\s+i\s+(?:check|see|view|find|track|monitor)|my\s+(?:position|stake|staking|jitosol)|(?:we|i)\s+just\s+did|that\s+we\s+did|what\s+we\s+did)\b/i;

export function _isReasoningQuestion(text: string): boolean {
  const q = (text || "").trim();
  if (!q || q.length > 400) return false;
  return _REASONING_RE.test(q);
}

// Imperative unstake/redeem commands must EXECUTE on the wallet backend, even
// though they contain "my position / my jitoSOL" which _REASONING_RE also matches.
// A leading advice/question word ("should I unstake?", "how much if I unstake?")
// still routes to reasoning instead.
const _UNSTAKE_CMD_RE =
  /\bun[-\s]?stake\b|\b(?:redeem|withdraw)\b[^.?!]*\b(?:stak|jito|msol|steth|reth|cbeth|sfrxeth|meth|stkbnb|ankrbnb|stmatic|lst)/i;
const _UNSTAKE_QUESTION_RE =
  /\b(should|shall|is\s+it|are\s+there|worth|good\s+idea|bad\s+idea|can\s+i|could\s+i|would|how\s+(?:much|many|do|long|to|can|should)|why|what|when|where|pros|cons|explain|compare|better\s+to|or\s+should)\b/i;
export function _isUnstakeCommand(text: string): boolean {
  const q = (text || "").trim();
  if (!q || q.length > 300) return false;
  if (!_UNSTAKE_CMD_RE.test(q)) return false;
  return !_UNSTAKE_QUESTION_RE.test(q); // a question ABOUT unstaking → not a command
}

export function _selectBackendTarget(body: string): BackendKind {
  const q = textFromAgentBody(body).toLowerCase();
  // Imperative unstake → execute on wallet backend. Checked BEFORE the reasoning
  // gate, which would otherwise capture "unstake my jitoSOL" via "my position".
  if (_isUnstakeCommand(q)) {
    return "wallet";
  }
  // Reasoning/advice questions → sentinel (reliable single-call reasoning).
  if (_isReasoningQuestion(q)) {
    return "sentinel";
  }
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
  const text = textFromAgentBody(body);
  const sid = sessionIdFromBody(body);
  let selected = _selectBackendTarget(body);
  // Keep an ambiguous follow-up on the same backend that holds the conversation.
  if (_isAmbiguousFollowup(text) && sid) {
    const aff = _sessionBackend.get(sid);
    if (aff && Date.now() - aff.ts < AFFINITY_TTL_MS) selected = aff.backend;
  }
  if (sid) {
    _sessionBackend.set(sid, { backend: selected, ts: Date.now() });
    if (_sessionBackend.size > 1000) {
      const cutoff = Date.now() - AFFINITY_TTL_MS;
      _sessionBackend.forEach((v, k) => { if (v.ts < cutoff) _sessionBackend.delete(k); });
    }
  }
  const target = _resolveBackendTarget(selected);

  let upstream: Response;
  try {
    upstream = await fetch(`${target}/api/v1/agent`, {
      method: "POST",
      headers: upstreamHeaders(request),
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    // fetch threw: timeout/abort or the backend is unreachable. Degrade to a
    // human message instead of letting Next return a bare 500.
    const isTimeout = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
    console.error(`[agent-proxy] upstream ${selected} fetch failed:`, err);
    return friendlyResponse(isTimeout ? FRIENDLY_TIMEOUT : FRIENDLY_UNREACHABLE);
  }

  // Backend returned a server-side failure (5xx). Surface a conversational
  // message rather than passing a raw 500/502/503/504 to the chat UI. The real
  // error is logged for operators; 4xx (rate-limit, credits, validation) pass
  // through so the frontend's specific handling still applies.
  if (upstream.status >= 500) {
    let detail = "";
    try { detail = (await upstream.clone().text()).slice(0, 500); } catch { /* ignore */ }
    console.error(`[agent-proxy] upstream ${selected} returned ${upstream.status}: ${detail}`);
    return friendlyResponse(FRIENDLY_GENERIC);
  }

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
