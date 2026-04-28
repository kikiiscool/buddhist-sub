import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "佛法字幕生成器", description: "Cantonese dharma subtitle generator" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-HK">
      <body className="min-h-screen">
        <header className="border-b border-neutral-800 px-6 py-4">
          <h1 className="text-lg font-semibold tracking-wide">佛法字幕生成器</h1>
          <p className="text-xs text-neutral-400">MP3 → Whisper → 詞典 → Qwen 校正 → SRT</p>
        </header>
        <main className="p-6">{children}</main>
      </body>
    </html>
  );
}
