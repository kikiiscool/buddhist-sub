"use client";
import useSWR from "swr";
import Link from "next/link";
import UploadCard from "@/components/UploadCard";
import { API, type Job } from "@/lib/api";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function Home() {
  const { data: jobs } = useSWR<Job[]>(`${API}/jobs`, fetcher, { refreshInterval: 3000 });
  return (
    <div className="space-y-8">
      <UploadCard />

      <section>
        <h2 className="text-base font-medium mb-3">最近任務</h2>
        <div className="space-y-2">
          {(jobs ?? []).map((j) => (
            <Link
              key={j.id}
              href={`/jobs/${j.id}`}
              className="block rounded-lg border border-neutral-800 bg-neutral-900/40 p-3 hover:border-amber-500/40"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">{j.name}</div>
                  <div className="text-xs text-neutral-500">{j.created_at}</div>
                </div>
                <span className="text-xs px-2 py-1 rounded bg-neutral-800">{j.status}</span>
              </div>
            </Link>
          ))}
          {(!jobs || jobs.length === 0) && (
            <div className="text-sm text-neutral-500">仲未有任務 — 上傳一個 MP3 開始</div>
          )}
        </div>
      </section>
    </div>
  );
}
