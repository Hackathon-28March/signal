"use client";

import { useEffect, useRef, useState } from "react";

export type ActivityEvent = {
  id: string;
  timestamp: string;
  stage: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
  meta?: Record<string, string>;
};

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8080";

const stageBadgeColor: Record<string, string> = {
  TRANSCRIBE: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  CLASSIFY: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  MEMORY: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  ROUTE: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  JIRA: "bg-sky-500/20 text-sky-400 border-sky-500/30",
  NOTION: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  SLACK: "bg-violet-500/20 text-violet-400 border-violet-500/30",
  DIGEST: "bg-pink-500/20 text-pink-400 border-pink-500/30",
  SYSTEM: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
};

const typeIcon: Record<string, string> = {
  info: "○",
  success: "●",
  warning: "◆",
  error: "✕",
};

const typeColor: Record<string, string> = {
  info: "text-zinc-400",
  success: "text-emerald-400",
  warning: "text-yellow-400",
  error: "text-red-400",
};

export function ActivityFeed() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let retryDelay = 1000;

    function connect() {
      // Use Next.js rewrite proxy — avoids WSL2 cross-origin SSE issues
      const es = new EventSource(`/api/backend/alerts/stream`);
      esRef.current = es;

      es.onopen = () => {
        setConnected(true);
        retryDelay = 1000; // reset backoff on successful connect
      };

      es.addEventListener("activity", (e) => {
        try {
          const event: ActivityEvent = JSON.parse(e.data);
          setEvents((prev) => [...prev.slice(-299), event]);
        } catch {
          // ignore malformed events
        }
      });

      es.onerror = () => {
        setConnected(false);
        es.close();
        // reconnect with exponential backoff, max 10s
        retryRef.current = setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 10_000);
          connect();
        }, retryDelay);
      };
    }

    connect();

    return () => {
      esRef.current?.close();
      if (retryRef.current) clearTimeout(retryRef.current);
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return (
    <div className="flex flex-col h-full bg-zinc-950 text-sm font-mono">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <span className="text-zinc-200 font-sans font-semibold text-base">
          Live Activity
        </span>
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-zinc-600"}`}
          />
          <span className="text-zinc-500 text-xs font-sans">
            {connected ? "connected" : "connecting…"}
          </span>
        </div>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {events.length === 0 && (
          <div className="text-zinc-600 text-xs pt-4 text-center font-sans">
            Waiting for backend…
          </div>
        )}
        {events.map((ev) => (
          <div key={ev.id} className="flex gap-3 items-start">
            <span className="text-zinc-600 text-xs shrink-0 pt-0.5 w-16 text-right tabular-nums">
              {new Date(ev.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            <span className={`shrink-0 pt-0.5 ${typeColor[ev.type]}`}>
              {typeIcon[ev.type]}
            </span>
            <div className="flex flex-col gap-0.5 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded border ${stageBadgeColor[ev.stage] ?? stageBadgeColor.SYSTEM}`}
                >
                  {ev.stage}
                </span>
                <span className="text-zinc-300 break-all">{ev.message}</span>
              </div>
              {ev.meta && Object.keys(ev.meta).length > 0 && (
                <div className="text-zinc-600 text-xs pl-0.5">
                  {Object.entries(ev.meta).map(([k, v]) => (
                    <span key={k} className="mr-3">
                      {k}={v}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
