"use client";

import { useCallback, useState } from "react";

type UploadState = "idle" | "dragging" | "uploading" | "done" | "error";

export function UploadZone() {
  const [state, setState] = useState<UploadState>("idle");
  const [message, setMessage] = useState<string>("");

  const handleUpload = useCallback(async (file: File) => {
    setState("uploading");
    setMessage(`Processing ${file.name}…`);

    try {
      const form = new FormData();
      form.append("file", file);

      const res = await fetch("/api/backend/upload", {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        throw new Error(`Upload failed: ${res.statusText}`);
      }

      setState("done");
      setMessage("Signal received — pipeline running");

      setTimeout(() => {
        setState("idle");
        setMessage("");
      }, 3000);
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Upload failed");
      setTimeout(() => {
        setState("idle");
        setMessage("");
      }, 4000);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setState("idle");
      const file = e.dataTransfer.files[0];
      if (file) handleUpload(file);
    },
    [handleUpload],
  );

  const onFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleUpload(file);
      e.target.value = "";
    },
    [handleUpload],
  );

  const borderColor = {
    idle: "border-zinc-700 hover:border-zinc-500",
    dragging: "border-emerald-500 bg-emerald-500/5",
    uploading: "border-blue-500 bg-blue-500/5",
    done: "border-emerald-500 bg-emerald-500/5",
    error: "border-red-500 bg-red-500/5",
  }[state];

  const icon = {
    idle: "↑",
    dragging: "↓",
    uploading: "⟳",
    done: "✓",
    error: "✕",
  }[state];

  const iconColor = {
    idle: "text-zinc-500",
    dragging: "text-emerald-400",
    uploading: "text-blue-400 animate-spin",
    done: "text-emerald-400",
    error: "text-red-400",
  }[state];

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setState("dragging");
      }}
      onDragLeave={() => setState("idle")}
      onDrop={onDrop}
      className={`relative border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer ${borderColor}`}
      onClick={() => document.getElementById("file-input")?.click()}
    >
      <input
        id="file-input"
        type="file"
        accept="audio/*,.mp3,.mp4,.wav,.m4a,.webm,.ogg"
        className="hidden"
        onChange={onFileChange}
      />
      <div className={`text-3xl mb-2 ${iconColor}`}>{icon}</div>
      <p className="text-zinc-300 text-sm font-medium">
        {state === "idle" && "Drop a call recording here"}
        {state === "dragging" && "Release to upload"}
        {state === "uploading" && "Uploading…"}
        {state === "done" && "Pipeline triggered"}
        {state === "error" && "Upload failed"}
      </p>
      {message && state !== "idle" && (
        <p className="text-zinc-500 text-xs mt-1">{message}</p>
      )}
      {state === "idle" && (
        <p className="text-zinc-600 text-xs mt-1">
          mp3, mp4, wav, m4a, webm, ogg
        </p>
      )}
    </div>
  );
}
