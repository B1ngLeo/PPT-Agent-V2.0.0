"use client";

import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";

const API_BASE = "/api";
const DEV_SUBJECT =
  process.env.NEXT_PUBLIC_DEV_USER_SUBJECT ?? "local-web-user";
const ACTIVE_SOURCE_KEY = "instant-ppt.active-source.v1";
const ACCEPTED = [".docx", ".pdf", ".pptx", ".html"];
const MIME: Record<string, string> = {
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pdf: "application/pdf",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  html: "text/html",
};

export type SourceState = {
  sourceId: string;
  filename: string;
  status: string;
  scanStatus: string;
  parseStatus: string;
  retryable: boolean;
  errorDetail: string | null;
  artifacts: Array<{ artifactId: string; kind: string }>;
};

type Phase = "idle" | "hashing" | "uploading" | "processing" | "done" | "error";

function authHeaders(): Record<string, string> {
  return {
    "X-Dev-User-Subject": DEV_SUBJECT,
    "X-Dev-User-Email": `${DEV_SUBJECT}@local.invalid`,
    "X-Dev-User-Name": "Local Creator",
  };
}

async function apiJson(path: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...init?.headers },
  });
  const body = await response.json();
  if (!response.ok)
    throw new Error(body.detail ?? `请求失败（${response.status}）`);
  return body;
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await file.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

function stageLabel(source: SourceState | null, phase: Phase): string {
  if (phase === "hashing") return "正在计算文件指纹";
  if (phase === "uploading") return "正在上传到私有隔离区";
  if (!source) return "等待选择来源文件";
  if (source.status === "parsed") return "解析完成，可以继续创作";
  if (source.status === "rejected" || source.status === "parse_failed") {
    return source.errorDetail ?? "来源处理失败";
  }
  if (source.scanStatus === "running") return "正在执行安全扫描";
  if (source.scanStatus === "clean" && source.parseStatus !== "succeeded") {
    return "安全检查通过，正在解析内容";
  }
  return "来源已入队，等待安全处理";
}

export function SourceUploader({
  onSourceReady,
}: {
  onSourceReady?: (source: SourceState) => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [source, setSource] = useState<SourceState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadSource = useCallback(async (sourceId: string) => {
    const body = await apiJson(`/v1/sources/${sourceId}`);
    const next = body.data as SourceState;
    setSource(next);
    if (next.status === "parsed") {
      setPhase("done");
      sessionStorage.removeItem(ACTIVE_SOURCE_KEY);
    } else if (next.status === "rejected" || next.status === "parse_failed") {
      setPhase("error");
    } else {
      setPhase("processing");
    }
    return next;
  }, []);

  useEffect(() => {
    const active = sessionStorage.getItem(ACTIVE_SOURCE_KEY);
    if (active) {
      loadSource(active).catch(() =>
        sessionStorage.removeItem(ACTIVE_SOURCE_KEY),
      );
    }
  }, [loadSource]);

  useEffect(() => {
    if (phase !== "processing" || !source?.sourceId) return;
    const timer = window.setInterval(() => {
      loadSource(source.sourceId).catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "状态刷新失败");
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [loadSource, phase, source?.sourceId]);

  useEffect(() => {
    if (source?.status === "parsed") onSourceReady?.(source);
  }, [onSourceReady, source]);

  const upload = useCallback(async (file: File) => {
    setError(null);
    setSource(null);
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!MIME[extension] || !ACCEPTED.includes(`.${extension}`)) {
      setPhase("error");
      setError("仅支持 DOCX、PDF、PPTX 和 HTML 文件");
      return;
    }
    if (file.size < 1 || file.size > 25 * 1024 * 1024) {
      setPhase("error");
      setError("文件大小必须在 1 B 到 25 MB 之间");
      return;
    }
    try {
      setPhase("hashing");
      const digest = await sha256(file);
      const createKey = crypto.randomUUID();
      const created = await apiJson("/v1/upload-sessions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": createKey,
        },
        body: JSON.stringify({
          schemaVersion: 1,
          data: {
            filename: file.name,
            declaredMimeType: MIME[extension],
            expectedSha256: digest,
            sizeBytes: file.size,
          },
          baseRevisionId: null,
        }),
      });
      setPhase("uploading");
      const form = new FormData();
      Object.entries(created.data.formFields as Record<string, string>).forEach(
        ([key, value]) => form.append(key, value),
      );
      form.append("file", file, file.name);
      const uploaded = await fetch(created.data.uploadUrl as string, {
        method: "POST",
        body: form,
      });
      if (!uploaded.ok) throw new Error("隔离区上传失败，请检查网络后重试");
      const completed = await apiJson(
        `/v1/upload-sessions/${created.data.uploadSessionId}:complete`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify({
            schemaVersion: 1,
            data: {},
            baseRevisionId: null,
          }),
        },
      );
      const next = completed.data as SourceState;
      sessionStorage.setItem(ACTIVE_SOURCE_KEY, next.sourceId);
      setSource(next);
      setPhase("processing");
    } catch (reason) {
      setPhase("error");
      setError(reason instanceof Error ? reason.message : "上传失败，请重试");
    }
  }, []);

  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void upload(file);
    event.target.value = "";
  };

  const retry = async () => {
    if (!source?.retryable) return;
    try {
      setError(null);
      const body = await apiJson(`/v1/sources/${source.sourceId}:retry-parse`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({
          schemaVersion: 1,
          data: {},
          baseRevisionId: null,
        }),
      });
      setSource(body.data as SourceState);
      sessionStorage.setItem(ACTIVE_SOURCE_KEY, source.sourceId);
      setPhase("processing");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重试失败");
    }
  };

  const busy = ["hashing", "uploading", "processing"].includes(phase);
  return (
    <section className="uploader-card" aria-labelledby="upload-title">
      <div className="card-heading">
        <div>
          <p className="eyebrow">SOURCE INTAKE</p>
          <h2 id="upload-title">添加主文档</h2>
        </div>
        <span className="limit">≤ 25 MB</span>
      </div>
      <input
        ref={inputRef}
        className="sr-only"
        id="source-file"
        aria-label="选择主文档"
        type="file"
        accept={ACCEPTED.join(",")}
        onChange={onFile}
        disabled={busy}
      />
      <button
        className={`dropzone${dragging ? " dragging" : ""}`}
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) void upload(file);
        }}
      >
        <span className="upload-icon" aria-hidden="true">
          ↑
        </span>
        <strong>{busy ? "处理中…" : "拖放文件，或点击选择"}</strong>
        <small>DOCX · PDF · PPTX · HTML</small>
      </button>
      <div
        className={`status-panel status-${phase}`}
        aria-live={phase === "error" ? "assertive" : "polite"}
        aria-atomic="true"
      >
        <div className="status-topline">
          <span className="status-dot" aria-hidden="true" />
          <span>{error ?? stageLabel(source, phase)}</span>
        </div>
        {source ? (
          <div className="source-meta">
            <span title={source.filename}>{source.filename}</span>
            <span>{source.artifacts?.length ?? 0} 个解析工件</span>
          </div>
        ) : null}
        {busy ? (
          <div className="progress-track">
            <span />
          </div>
        ) : null}
      </div>
      <div className="card-actions">
        {source?.retryable ? (
          <button
            className="secondary-button"
            type="button"
            onClick={() => void retry()}
          >
            重试安全处理
          </button>
        ) : null}
        <button
          className="primary-button"
          type="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {phase === "done" ? "添加另一份文档" : "选择文档"}
        </button>
      </div>
    </section>
  );
}
