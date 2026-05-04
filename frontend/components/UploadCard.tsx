"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

type UploadResult = {
  filename: string;
  jobId?: string;
  error?: string;
};

export default function UploadCard() {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function uploadOne(file: File) {
    const init = await api<{ audio_key: string; upload_url: string }>("/uploads/init", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, content_type: file.type || "audio/mpeg" }),
    });

    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(xhr.statusText));
      xhr.onerror = () => reject("upload failed");
      xhr.open("PUT", init.upload_url);
      if (file.type) xhr.setRequestHeader("Content-Type", file.type);
      xhr.send(file);
    });

    return api<{ id: string }>("/jobs", {
      method: "POST",
      body: JSON.stringify({
        name: name ? `${name} - ${file.name}` : file.name,
        audio_key: init.audio_key,
        config: {},
      }),
    });
  }

  async function submit() {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    setResults([]);
    let firstJobId: string | null = null;

    try {
      const localResults: UploadResult[] = [];
      for (const file of files) {
        setCurrentFile(file.name);
        setProgress(0);
        try {
          const job = await uploadOne(file);
          firstJobId ??= job.id;
          localResults.push({ filename: file.name, jobId: job.id });
        } catch (e: unknown) {
          localResults.push({ filename: file.name, error: String(e) });
        }
        setResults([...localResults]);
      }

      if (firstJobId) {
        router.push(`/jobs/${firstJobId}`);
      }
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setCurrentFile(null);
      setProgress(0);
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-6 space-y-4 max-w-xl">
      <h2 className="text-base font-medium">上傳 MP3（支援批次）</h2>
      <input
        type="text"
        placeholder="任務名稱前綴 (例:法師心經開示 2026-04)"
        className="w-full rounded bg-neutral-950 border border-neutral-800 px-3 py-2 text-sm"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <input
        type="file"
        accept="audio/*"
        multiple
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        className="block text-sm"
      />
      {files.length > 0 && <div className="text-xs text-neutral-400">已選擇 {files.length} 個檔案</div>}
      {busy && currentFile && (
        <div className="text-xs text-neutral-400">
          正在上傳 {currentFile} {progress > 0 && progress < 100 ? `(${progress}%)` : ""}
        </div>
      )}
      {results.length > 0 && (
        <ul className="text-xs space-y-1">
          {results.map((r) => (
            <li key={r.filename} className={r.error ? "text-red-400" : "text-emerald-400"}>
              {r.filename}: {r.error ? `失敗 (${r.error})` : `已建立任務 ${r.jobId}`}
            </li>
          ))}
        </ul>
      )}
      {error && <div className="text-xs text-red-400">{error}</div>}
      <button
        disabled={!files.length || busy}
        onClick={submit}
        className="rounded bg-amber-500/90 hover:bg-amber-500 px-4 py-2 text-sm font-medium text-neutral-900 disabled:opacity-50"
      >
        {busy ? "處理中…" : files.length > 1 ? "開始批次轉換" : "開始轉換"}
      </button>
    </div>
  );
}
