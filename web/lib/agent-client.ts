import type { SSEFrame } from "@/types/agent";

export async function* streamAgent(
  body: { session_id: string; message: string; wallet?: string },
  token: string | null,
): AsyncGenerator<SSEFrame, void, void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch("/api/v1/agent", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!r.body) throw new Error("no body");
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const evMatch = raw.match(/^event: (.+)$/m);
      const dataMatch = raw.match(/^data: (.+)$/m);
      if (!dataMatch) continue;
      const event = evMatch?.[1] ?? "message";
      const data = JSON.parse(dataMatch[1]);
      // Add kind field based on event name
      data.kind = event;
      yield data as SSEFrame;
    }
  }
}
