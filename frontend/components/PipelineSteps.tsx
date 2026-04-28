"use client";
import clsx from "clsx";
import type { Job, StepRun } from "@/lib/api";
import { api } from "@/lib/api";

const STEP_LABEL: Record<string, string> = {
  vad: "1. 切段 (VAD)",
  transcribe: "2. Whisper 轉錄",
  dict_pass: "3. 詞典預處理",
  rag_correct: "4. Qwen + CBETA 校正",
  review: "5. 人工 review",
  srt: "6. 生成 SRT",
};

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-neutral-700",
  running: "bg-blue-500 animate-pulse",
  paused: "bg-yellow-500",
  completed: "bg-emerald-500",
  failed: "bg-red-500",
  skipped: "bg-neutral-500",
};

async function action(jobId: string, stepName: string, action: string) {
  await api(`/jobs/${jobId}/steps/${stepName}/action`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export default function PipelineSteps({ job }: { job: Job }) {
  return (
    <div className="space-y-2">
      {job.steps.map((s) => (
        <StepRow key={s.id} jobId={job.id} step={s} />
      ))}
    </div>
  );
}

function StepRow({ jobId, step }: { jobId: string; step: StepRun }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
      <div className="flex items-center gap-3">
        <div className={clsx("h-2 w-2 rounded-full", STATUS_COLOR[step.status] ?? "bg-neutral-700")} />
        <div className="text-sm font-medium w-56">{STEP_LABEL[step.name] ?? step.name}</div>
        <div className="flex-1 h-2 rounded bg-neutral-800 overflow-hidden">
          <div
            className={clsx("h-full transition-all", STATUS_COLOR[step.status])}
            style={{ width: `${Math.round(step.progress * 100)}%` }}
          />
        </div>
        <div className="text-xs text-neutral-400 w-12 text-right">
          {Math.round(step.progress * 100)}%
        </div>
        <div className="flex gap-1">
          {step.status === "running" && (
            <button onClick={() => action(jobId, step.name, "pause")} className="btn">暫停</button>
          )}
          {step.status === "paused" && (
            <button onClick={() => action(jobId, step.name, "resume")} className="btn">繼續</button>
          )}
          <button onClick={() => action(jobId, step.name, "retry")} className="btn">重做</button>
          {step.name === "review" && (
            <button onClick={() => action(jobId, step.name, "skip")} className="btn">跳過</button>
          )}
        </div>
      </div>
      {step.log && (
        <pre className="mt-2 max-h-32 overflow-auto rounded bg-neutral-950/60 p-2 text-[11px] text-neutral-400 whitespace-pre-wrap">
          {step.log.slice(-2000)}
        </pre>
      )}
      <style jsx>{`
        .btn {
          font-size: 11px;
          padding: 2px 8px;
          border-radius: 4px;
          background: rgb(38 38 38);
          color: rgb(229 229 229);
        }
        .btn:hover { background: rgb(64 64 64); }
      `}</style>
    </div>
  );
}
