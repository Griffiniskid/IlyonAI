export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASSISTANT_API_TARGET = process.env.ASSISTANT_API_TARGET || "http://localhost:8000";

export async function GET(): Promise<Response> {
  const upstream = await fetch(`${ASSISTANT_API_TARGET}/health`, {
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
