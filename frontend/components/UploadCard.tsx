"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function UploadCard() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const init = await api<{ audio_key: string; upload_url: string }>("/uploads/init", {
        method: "POST",
        body: JSON.stringify({ filename: file.name, content_type: file.type || "audio/mpeg" }),
      });
      // Direct PUT to MinIO/S3 with progress
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

      const job = await api<{ id: string }>("/jobs", {
        method: "POST",
        body: JSON.stringify({ name: name || file.name, audio_key: init.audio_key, config: {} }),
      });
      router.push(`/jobs/${job.id}`);
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-6 space-y-4 max-w-xl">
      <h2 className="text-base font-medium">上傳 MP3</h2>
      <input
        type="text"
        placeholder="任務名稱 (例:法師心經開示 2026-04)"
        className="w-full rounded bg-neutral-950 border border-neutral-800 px-3 py-2 text-sm"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <input
        type="file"
        accept="audio/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="block text-sm"
      />
      {progress > 0 && progress < 100 && (
        <div className="text-xs text-neutral-400">上傳中 {progress}%</div>
      )}
      {error && <div className="text-xs text-red-400">{error}</div>}
      <button
        disabled={!file || busy}
        onClick={submit}
        className="rounded bg-amber-500/90 hover:bg-amber-500 px-4 py-2 text-sm font-medium text-neutral-900 disabled:opacity-50"
      >
        {busy ? "處理中…" : "開始轉換"}
      </button>
    </div>
  );
}
