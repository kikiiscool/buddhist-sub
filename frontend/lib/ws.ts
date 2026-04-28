import { useEffect, useRef, useState } from "react";
import { WS } from "./api";

export type WsEvent = { event: string; ts: number; [k: string]: unknown };

export function useJobSocket(jobId: string | null) {
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const ref = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const ws = new WebSocket(`${WS}/ws/jobs/${jobId}`);
    ref.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (m) => {
      try {
        const ev = JSON.parse(m.data) as WsEvent;
        setEvents((es) => [...es.slice(-499), ev]);
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, [jobId]);

  return { events, connected, send: (data: unknown) => ref.current?.send(JSON.stringify(data)) };
}
