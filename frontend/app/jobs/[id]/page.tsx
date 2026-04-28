"use client";
import useSWR from "swr";
import { API, type Job, type Segment } from "@/lib/api";
import { useJobSocket } from "@/lib/ws";
import PipelineSteps from "@/components/PipelineSteps";
import SubtitleEditor from "@/components/SubtitleEditor";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function JobPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { data: job, mutate: refetchJob } = useSWR<Job>(`${API}/jobs/${id}`, fetcher, {
    refreshInterval: 1500,
  });
  const { data: segments, mutate: refetchSegs } = useSWR<Segment[]>(
    `${API}/jobs/${id}/segments`,
    fetcher,
    { refreshInterval: 2000 },
  );
  const { events, connected } = useJobSocket(id);

  if (!job) return <div className="text-sm text-neutral-500">載入中…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium">{job.name}</h2>
          <div className="text-xs text-neutral-500">
            狀態:{job.status} · WebSocket {connected ? "已連線" : "斷開"}
          </div>
        </div>
      </div>

      <PipelineSteps job={job} />

      <div className="grid grid-cols-1 xl:grid-cols-[2fr_1fr] gap-4">
        <div>
          <h3 className="text-sm font-medium mb-2">字幕</h3>
          <SubtitleEditor jobId={id} segments={segments ?? []} onChange={() => { refetchSegs(); refetchJob(); }} />
        </div>
        <div>
          <h3 className="text-sm font-medium mb-2">事件流</h3>
          <pre className="rounded-lg border border-neutral-800 bg-neutral-950 p-3 text-[11px] text-neutral-400 max-h-[600px] overflow-auto">
            {events.slice().reverse().map((e, i) => (
              <div key={i}>
                <span className="text-amber-400">{e.event}</span>{" "}
                {JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k]) => k !== "event" && k !== "ts")))}
              </div>
            ))}
            {events.length === 0 && <span className="text-neutral-600">(等待中)</span>}
          </pre>
        </div>
      </div>
    </div>
  );
}
