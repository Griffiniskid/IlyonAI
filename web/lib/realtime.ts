export type RealtimeMode = "websocket" | "polling";
export type StreamStatus = "disconnected" | "live" | "reconnecting" | "polling";

interface RealtimeClientOptions {
  connectionTimeoutMs?: number;
}

export class RealtimeClient {
  private readonly baseUrl: string;
  private readonly connectionTimeoutMs: number;
  private socket: WebSocket | null = null;
  private _messageHandler: ((data: unknown) => void) | null = null;
  private _streamStatus: StreamStatus = "disconnected";
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _reconnectAttempts = 0;
  private _currentTopic: string | null = null;
  _force_socket_failure_for_test = false;

  constructor(baseUrl: string, options?: RealtimeClientOptions) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.connectionTimeoutMs = options?.connectionTimeoutMs ?? 3000;
  }

  get streamStatus(): StreamStatus {
    return this._streamStatus;
  }

  onMessage(handler: (data: unknown) => void): void {
    this._messageHandler = handler;
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          handler(parsed);
        } catch {
          // ignore non-JSON heartbeats
        }
      };
    }
  }

  async subscribe(
    topic: string,
    handler: (data: unknown) => void,
  ): Promise<RealtimeMode> {
    this._currentTopic = topic;
    this.onMessage(handler);
    const mode = await this.connect_or_fallback(topic);
    this._streamStatus = mode === "websocket" ? "live" : "polling";
    return mode;
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
          settle(() => {
            this._reconnectAttempts = 0;

            // Attach message handler
            if (this._messageHandler) {
              socket.onmessage = (event) => {
                try {
                  const parsed = JSON.parse(event.data);
                  this._messageHandler?.(parsed);
                } catch {
                  // ignore heartbeats
                }
              };
            }

            // Auto-reconnect on unexpected close
            socket.onclose = () => {
              if (this._streamStatus === "live") {
                this._attemptReconnect();
              }
            };

            resolve();
          });
        };

        socket.onerror = () => {
          settle(() => reject(new Error("WebSocket connection failed")));
        };

        socket.onclose = () => {
          settle(() => reject(new Error("WebSocket closed before opening")));
        };
      });

      this._streamStatus = "live";
      return "websocket";
    } catch {
      this.close();
      this._streamStatus = "polling";
      return "polling";
    }
  }

  private _attemptReconnect(): void {
    this._streamStatus = "reconnecting";
    this._reconnectAttempts++;
    const delay = Math.min(
      1000 * Math.pow(2, this._reconnectAttempts - 1),
      30000,
    );

    this._reconnectTimer = setTimeout(async () => {
      if (this._currentTopic) {
        const mode = await this.connect_or_fallback(this._currentTopic);
        if (mode === "polling") {
          this._streamStatus = "polling";
        }
      }
    }, delay);
  }

  close(): void {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.onclose = null; // prevent reconnect on intentional close
      this.socket.close();
      this.socket = null;
    }
    this._streamStatus = "disconnected";
    this._currentTopic = null;
  }

  private buildWebSocketUrl(topic: string): string {
    const wsBase = this.baseUrl
      .replace(/^http:\/\//, "ws://")
      .replace(/^https:\/\//, "wss://");
    const params = new URLSearchParams({ topic });
    return `${wsBase}/api/v1/stream/ws?${params.toString()}`;
  }
}
