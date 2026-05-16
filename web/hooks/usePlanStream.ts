/**
 * Plan-scoped SSE subscription.
 *
 * Subscribes to `/api/v1/stream/sse?topic=plan:{plan_id}` to receive
 * runtime events for a specific composed plan — bridge_resolution,
 * step_status_change, drift_alert, etc.
 *
 * Use in ExecutionPlanV3Card to flip the bridge step's status
 * (PENDING_DST_FILL → ready) without re-polling the chat API.
 */
import { useEffect, useRef, useState } from "react";

export interface PlanStreamEvent {
  kind: string;
  state?: string;
  plan_id?: string;
  step_id?: string;
  step_status?: string;
  actual_dst_amount?: number | string;
  user_wallet?: string;
  [key: string]: unknown;
}

export function usePlanStream(planId: string | null | undefined): {
  lastEvent: PlanStreamEvent | null;
  events: PlanStreamEvent[];
  connected: boolean;
} {
  const [lastEvent, setLastEvent] = useState<PlanStreamEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const eventsRef = useRef<PlanStreamEvent[]>([]);
  const [, setBump] = useState(0);

  useEffect(() => {
    if (!planId) return;
    const url = `/api/v1/stream/sse?topic=plan:${encodeURIComponent(planId)}`;
    const es = new EventSource(url, { withCredentials: true });
    setConnected(false);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (msg) => {
      try {
        const payload = JSON.parse(msg.data) as PlanStreamEvent;
        eventsRef.current = [...eventsRef.current, payload].slice(-100);
        setLastEvent(payload);
        setBump((b) => b + 1);
      } catch {
        // Non-JSON SSE — ignore.
      }
    };
    return () => {
      es.close();
      setConnected(false);
    };
  }, [planId]);

  return { lastEvent, events: eventsRef.current, connected };
}
