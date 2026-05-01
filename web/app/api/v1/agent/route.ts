import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASSISTANT_API_TARGET = process.env.ASSISTANT_API_TARGET || "http://localhost:8000";
const SENTINEL_API_TARGET = process.env.SENTINEL_API_TARGET || "http://localhost:8080";
const REQUEST_TIMEOUT_MS = 180_000;

export function _resolveBackendTarget(): string {
  const backend = process.env.AGENT_BACKEND || "sentinel";
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

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  const target = _resolveBackendTarget();
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
      "cache-control": "no-store",
    },
  });
}
