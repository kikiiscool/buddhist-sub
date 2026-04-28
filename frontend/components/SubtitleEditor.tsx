"use client";
import { useState } from "react";
import { api, type Segment } from "@/lib/api";

function fmt(t: number) {
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = (t % 60).toFixed(1);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.padStart(4, "0")}`;
}

export default function SubtitleEditor({ jobId, segments, onChange }: {
  jobId: string;
  segments: Segment[];
  onChange?: () => void;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/40">
      <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-2 text-xs text-neutral-400">
        <span>共 {segments.length} 段字幕 · 點擊可編輯</span>
        <a
          href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/jobs/${jobId}/srt`}
          className="text-amber-400 hover:underline"
        >
          下載 SRT
        </a>
      </div>
      <div className="max-h-[600px] overflow-auto divide-y divide-neutral-800">
        {segments.map((s) => (
          <Row key={s.id} jobId={jobId} seg={s} onChange={onChange} />
        ))}
      </div>
    </div>
  );
}

function Row({ jobId, seg, onChange }: { jobId: string; seg: Segment; onChange?: () => void }) {
  const [edit, setEdit] = useState(false);
  const [val, setVal] = useState(seg.text_final ?? seg.text_ai ?? seg.text_dict ?? seg.text_raw);

  async function save() {
    await api(`/jobs/${jobId}/segments/${seg.id}`, {
      method: "PATCH",
      body: JSON.stringify({ text_final: val }),
    });
    setEdit(false);
    onChange?.();
  }

  const display = seg.text_final ?? seg.text_ai ?? seg.text_dict ?? seg.text_raw;
  const changed = (seg.text_ai ?? "") !== (seg.text_dict ?? seg.text_raw);

  return (
    <div className="grid grid-cols-[120px_1fr] gap-3 px-4 py-2 text-sm hover:bg-neutral-900/60">
      <div className="text-[11px] text-neutral-500 font-mono pt-1">
        <div>{fmt(seg.start_s)}</div>
        <div className="text-neutral-600">→ {fmt(seg.end_s)}</div>
      </div>
      <div>
        {edit ? (
          <div className="flex gap-2">
            <textarea
              value={val}
              onChange={(e) => setVal(e.target.value)}
              className="flex-1 rounded bg-neutral-950 border border-neutral-700 px-2 py-1 text-sm"
              rows={2}
            />
            <button onClick={save} className="text-xs px-2 bg-amber-500 text-neutral-900 rounded">存</button>
            <button onClick={() => setEdit(false)} className="text-xs px-2 bg-neutral-700 rounded">取消</button>
          </div>
        ) : (
          <div className="cursor-text" onClick={() => setEdit(true)}>
            <div className="text-neutral-100">{display || <em className="text-neutral-600">(空)</em>}</div>
            {changed && (
              <div className="text-[11px] text-neutral-500 mt-1">
                <span className="line-through opacity-60">{seg.text_raw}</span>
                {seg.rag_refs?.length > 0 && (
                  <span className="ml-2 text-emerald-400">
                    ✓ {seg.rag_refs.length} CBETA refs
                  </span>
                )}
                {seg.edited_by_human && <span className="ml-2 text-amber-400">✎ 人手改</span>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
