export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASSISTANT_API_TARGET = process.env.ASSISTANT_API_TARGET || "http://localhost:8000";
const SENTINEL_API_TARGET = process.env.SENTINEL_API_TARGET || "http://localhost:8080";

function resolveBackendTarget(): string {
  return process.env.AGENT_BACKEND === "wallet" ? ASSISTANT_API_TARGET : SENTINEL_API_TARGET;
}

export async function GET(): Promise<Response> {
  const upstream = await fetch(`${resolveBackendTarget()}/health`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: {
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": "no-store",
    },
  });
}
