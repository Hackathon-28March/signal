"use client";

import { useCallback, useEffect, useState } from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8080";

type Digest = {
  markdown: string;
  generated_at: string;
  signal_count: number;
};

export function DigestPanel() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDigest = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/backend/digest`);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      setDigest(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load digest");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDigest();
    const timer = setInterval(fetchDigest, 30_000);
    return () => clearInterval(timer);
  }, [fetchDigest]);

  return (
    <div className="flex flex-col gap-2 p-4 border border-zinc-800 rounded-lg bg-zinc-900/50">
      <div className="flex items-center justify-between">
        <span className="text-zinc-200 font-semibold text-sm">CEO Digest</span>
        <button
          onClick={fetchDigest}
          className="text-zinc-600 hover:text-zinc-400 text-xs transition-colors"
        >
          {loading ? "refreshing…" : "refresh"}
        </button>
      </div>

      {error && (
        <p className="text-red-400 text-xs">Unavailable: {error}</p>
      )}

      {!digest && !error && !loading && (
        <p className="text-zinc-600 text-xs">No signals processed yet.</p>
      )}

      {digest && (
        <>
          {/* Render markdown as plain pre-formatted text — readable without a parser */}
          <pre className="text-zinc-400 text-[11px] leading-relaxed whitespace-pre-wrap font-sans">
            {digest.markdown}
          </pre>
          <p className="text-zinc-600 text-[10px] border-t border-zinc-800 pt-2">
            {digest.signal_count ?? 0} signals ·{" "}
            {digest.generated_at
              ? new Date(digest.generated_at).toLocaleString()
              : ""}
          </p>
        </>
      )}
    </div>
  );
}
