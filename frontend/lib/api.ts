export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const WS = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export type StepRun = {
  id: string;
  name: string;
  order_idx: number;
  status: "pending" | "running" | "paused" | "completed" | "failed" | "skipped";
  progress: number;
  log: string | null;
  started_at: string | null;
  finished_at: string | null;
  metrics: Record<string, unknown>;
};

export type Job = {
  id: string;
  name: string;
  audio_key: string;
  audio_duration_s: number | null;
  status: string;
  config: Record<string, unknown>;
  error: string | null;
  created_at: string;
  updated_at: string;
  steps: StepRun[];
};

export type Segment = {
  id: string;
  idx: number;
  start_s: number;
  end_s: number;
  text_raw: string;
  text_dict: string | null;
  text_ai: string | null;
  text_final: string | null;
  confidence: number | null;
  rag_refs: { canon: string; work_id: string; juan: number | null; score: number }[];
  edited_by_human: boolean;
};
