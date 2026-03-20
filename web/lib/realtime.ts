export type RealtimeMode = "websocket" | "polling";

interface RealtimeClientOptions {
  connectionTimeoutMs?: number;
}

export class RealtimeClient {
  private readonly baseUrl: string;
  private readonly connectionTimeoutMs: number;
  private socket: WebSocket | null = null;
  _force_socket_failure_for_test = false;

  constructor(baseUrl: string, options?: RealtimeClientOptions) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.connectionTimeoutMs = options?.connectionTimeoutMs ?? 3000;
  }

  async connect_or_fallback(topic: string): Promise<RealtimeMode> {
    try {
      if (this._force_socket_failure_for_test) {
        throw new Error("forced test socket failure");
      }

      if (typeof WebSocket === "undefined") {
        throw new Error("WebSocket unavailable");
      }

      const wsUrl = this.buildWebSocketUrl(topic);

      await new Promise<void>((resolve, reject) => {
        const socket = new WebSocket(wsUrl);
        this.socket = socket;
        let settled = false;
        const timeoutId = setTimeout(() => {
          if (!settled) {
            settled = true;
            reject(new Error("WebSocket connection timed out"));
          }
        }, this.connectionTimeoutMs);

        const settle = (fn: () => void) => {
          if (settled) return;
          settled = true;
          clearTimeout(timeoutId);
          fn();
        };

        socket.onopen = () => {
          settle(resolve);
        };

        socket.onerror = () => {
          settle(() => reject(new Error("WebSocket connection failed")));
        };

        socket.onclose = () => {
          settle(() => reject(new Error("WebSocket closed before opening")));
        };
      });

      return "websocket";
    } catch {
      this.close();
      return "polling";
    }
  }

  close(): void {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  private buildWebSocketUrl(topic: string): string {
    const wsBase = this.baseUrl.replace(/^http:\/\//, "ws://").replace(/^https:\/\//, "wss://");
    const params = new URLSearchParams({ topic });
    return `${wsBase}/api/v1/stream/ws?${params.toString()}`;
  }
}
