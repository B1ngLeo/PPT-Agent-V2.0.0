"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import { SourceUploader, type SourceState } from "./source-uploader";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const DEV_SUBJECT =
  process.env.NEXT_PUBLIC_DEV_USER_SUBJECT ?? "local-web-user";
const ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

function AccessibilityAudit({ auditKey }: { auditKey: string }) {
  const enabled = process.env.NEXT_PUBLIC_A11Y_AUDIT === "1";
  const [result, setResult] = useState({
    state: "waiting",
    violations: -1,
    criticalSerious: -1,
    incomplete: -1,
    passes: -1,
    ids: [] as string[],
    issues: [] as Array<{
      id: string;
      impact: string | null;
      help: string;
      targets: string[];
    }>,
  });

  useEffect(() => {
    if (!enabled) return;
    setResult((current) => ({ ...current, state: "waiting" }));
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void import("axe-core")
        .then(({ default: axe }) =>
          axe.run(document, {
            runOnly: {
              type: "tag",
              values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
            },
          }),
        )
        .then((audit) => {
          if (cancelled) return;
          setResult({
            state: "complete",
            violations: audit.violations.length,
            criticalSerious: audit.violations.filter((item) =>
              ["critical", "serious"].includes(item.impact ?? ""),
            ).length,
            incomplete: audit.incomplete.length,
            passes: audit.passes.length,
            ids: audit.violations.map((item) => item.id),
            issues: audit.violations.map((item) => ({
              id: item.id,
              impact: item.impact ?? null,
              help: item.help,
              targets: item.nodes.flatMap((node) => node.target.map(String)),
            })),
          });
        })
        .catch(() => {
          if (!cancelled) setResult((current) => ({ ...current, state: "failed" }));
        });
    }, 1200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [auditKey, enabled]);

  if (!enabled) return null;
  return (
    <output className="a11y-audit-output" aria-label="axe accessibility audit results">
      {JSON.stringify({ auditKey, ...result })}
    </output>
  );
}

type ApiEnvelope<T> = {
  resourceId: string;
  data: T;
  nextCursor: string | null;
};

type Entitlement = {
  planCode: string;
  maxSlidesPerDeck: number;
  monthlySlideLimit: number;
  maxConcurrentJobs: number;
  allowedModes: string[];
};

type Usage = {
  metrics: { slides: number; images: number; modelTokens: number };
  reservedSlides: number;
};

type TemplateVersion = {
  templateId: string;
  templateVersionId: string;
  name: string;
  category: string;
  description: string;
  mode: "native";
  themeSpec: {
    colorTokens: { primary: string; background: string };
  };
};

type IntentRevision = {
  intentRevisionId: string;
  title: string;
  audience: string;
  goal: string;
  targetSlideCount: number;
  language: "zh-CN" | "en-US";
  contentDepth: "conclusion_first" | "balanced" | "research";
  visualPreference: "data_first" | "photo_illustration" | "minimal_visual";
  notes: string;
  sourceRefs: string[];
  basedOnRevisionId: string | null;
  actor: { id: string; kind: string };
};

type OutlineSlide = {
  outlineSlideId: string;
  type: string;
  title: string;
  keyPoints: string[];
  sourceCitations: string[];
};

type OutlineRevision = {
  outlineRevisionId: string;
  storySummary: string;
  targetSlideCount: number;
  slides: OutlineSlide[];
  basedOnRevisionId: string | null;
  operation: string;
  actor: { id: string; kind: string };
};

type GenerationSummary = {
  approvalId: string;
  draftId: string;
  intentRevisionId: string;
  outlineRevisionId: string;
  templateVersionId: string;
  mode: string;
  sourceSummary: {
    sourceId: string | null;
    status: string;
    artifacts: number;
  };
  snapshotInputHash: string;
  approvedAt: string;
  boundary: "generation_not_started";
};

type DraftSnapshot = {
  draftId: string;
  title: string;
  topic: string;
  sourceId: string | null;
  mode: "native";
  templateVersionId: string;
  currentIntentRevisionId: string | null;
  currentOutlineRevisionId: string | null;
  approvedOutlineRevisionId: string | null;
  status: string;
  lockVersion: number;
  updatedAt: string;
  currentIntent: IntentRevision | null;
  currentOutline: OutlineRevision | null;
  generationSummary: GenerationSummary | null;
  historyState?: "draft" | "monitor" | "result";
  jobId?: string | null;
  jobStatus?: string | null;
  presentationId?: string | null;
  presentationStatus?: string | null;
  route?: string;
};

type PresentationSlide = {
  slideVersionId: string;
  slideId: string;
  outlineSlideId: string;
  position: number;
  status: "ready" | "failed";
  title: string;
  body: string[];
  artifactId: string | null;
  sourceSlideVersionId: string | null;
  errorCode: string | null;
};

type PresentationRevision = {
  presentationRevisionId: string;
  presentationId: string;
  basedOnRevisionId: string | null;
  revisionNumber: number;
  operation: string;
  partial: boolean;
  acceptedMissing: boolean;
  manifestArtifactId: string;
  slides: PresentationSlide[];
  createdAt: string;
};

type Presentation = {
  presentationId: string;
  draftId: string;
  generationJobId: string;
  title: string;
  status: "ready" | "partial";
  currentRevisionId: string;
  lockVersion: number;
  currentRevision: PresentationRevision;
};

type PresentationExport = {
  exportId: string;
  presentationId: string;
  presentationRevisionId: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  stage: "queued" | "compiling" | "package_qa" | "publishing";
  artifactId: string | null;
  manifestArtifactId: string | null;
  errorCode: string | null;
};

type RegenerationOperation = {
  regenerationJobId: string;
  presentationId: string;
  baseRevisionId: string;
  slideId: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  resultRevisionId: string | null;
  errorCode: string | null;
};

type GenerationJobSlide = {
  slideId: string;
  outlineSlideId: string;
  position: number;
  title: string;
  status: "pending" | "running" | "ready" | "failed" | "retrying" | "cancelled";
  stage: "content_generation" | "rendering" | "qa";
  attempt: number;
  renderSha256: string | null;
  errorCode: string | null;
};

type GenerationArtifact = {
  artifactId: string;
  artifactType: string;
  slideId: string | null;
  sha256: string;
  mediaType: string;
  sizeBytes: number;
};

type GenerationJob = {
  jobId: string;
  snapshotId: string;
  draftId: string;
  organizationId: string;
  processor: "real" | "fake";
  status:
    | "queued"
    | "running"
    | "cancel_requested"
    | "succeeded"
    | "partially_succeeded"
    | "failed"
    | "cancelled";
  stage:
    | "deck_planning"
    | "slide_generation"
    | "deck_qa"
    | "compiling"
    | "package_qa"
    | "publishing";
  publicationVersion: number;
  latestSeq: number;
  terminal: boolean;
  attempt: number;
  progress: { completed: number; total: number };
  slides: GenerationJobSlide[];
  artifacts: GenerationArtifact[];
  publication: {
    publicationId: string;
    manifestArtifactId: string;
    manifestSha256: string;
  } | null;
  presentation: {
    presentationId: string;
    currentRevisionId: string;
    status: "ready" | "partial";
  } | null;
};

type StreamState = "connecting" | "live" | "reconnecting" | "closed";

type SaveState = "idle" | "saving" | "saved" | "failed";
type FailedSaveKind = "intent" | "outline" | null;

class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function authHeaders(): Record<string, string> {
  return {
    "X-Dev-User-Subject": DEV_SUBJECT,
    "X-Dev-User-Email": `${DEV_SUBJECT}@local.invalid`,
    "X-Dev-User-Name": "Local Creator",
  };
}

async function api<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiEnvelope<T>> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...init?.headers },
  });
  const body = (await response.json()) as {
    code?: string;
    detail?: string;
  } & ApiEnvelope<T>;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body.code ?? "request_failed",
      body.detail ?? `请求失败（${response.status}）`,
    );
  }
  return body;
}

async function downloadAuthorizedFile(url: string, filename: string) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`下载对象失败（${response.status}）`);
  const objectUrl = URL.createObjectURL(await response.blob());
  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }
}

function mutation(data: unknown, baseRevisionId: string | null = null) {
  return JSON.stringify({ schemaVersion: 1, data, baseRevisionId });
}

function clientUlid(): string {
  let time = Date.now();
  let prefix = "";
  for (let index = 0; index < 10; index += 1) {
    prefix = ULID_ALPHABET[time % 32] + prefix;
    time = Math.floor(time / 32);
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return `${prefix}${Array.from(bytes, (value) => ULID_ALPHABET[value & 31]).join("")}`;
}

function intentPayload(value: IntentRevision) {
  return {
    title: value.title,
    audience: value.audience,
    goal: value.goal,
    targetSlideCount: value.targetSlideCount,
    language: value.language,
    contentDepth: value.contentDepth,
    visualPreference: value.visualPreference,
    notes: value.notes,
    sourceRefs: value.sourceRefs,
  };
}

function outlinePayload(value: OutlineRevision, operation = "edit") {
  return {
    storySummary: value.storySummary,
    targetSlideCount: value.targetSlideCount,
    slides: value.slides.map((slide) => ({
      outlineSlideId: slide.outlineSlideId,
      type: slide.type,
      title: slide.title,
      keyPoints: slide.keyPoints,
      sourceCitations: slide.sourceCitations,
    })),
    operation,
  };
}

function saveLabel(state: SaveState): string {
  if (state === "saving") return "保存中…";
  if (state === "saved") return "已保存";
  if (state === "failed") return "保存失败，本地内容已保留";
  return "所有修改都会形成版本";
}

function generationStageLabel(stage: GenerationJob["stage"]): string {
  const labels: Record<GenerationJob["stage"], string> = {
    deck_planning: "构建生成计划",
    slide_generation: "逐页生成与检查",
    deck_qa: "整稿质量检查",
    compiling: "编译原生 PPTX",
    package_qa: "验证可编辑包",
    publishing: "发布不可变工件",
  };
  return labels[stage];
}

function generationStatusLabel(status: GenerationJob["status"]): string {
  const labels: Record<GenerationJob["status"], string> = {
    queued: "已排队",
    running: "生成中",
    cancel_requested: "正在取消",
    succeeded: "生成完成",
    partially_succeeded: "部分完成",
    failed: "生成失败",
    cancelled: "已取消",
  };
  return labels[status];
}

async function streamGenerationEvents(
  jobId: string,
  signal: AbortSignal,
  lastEventId: string,
  onEvent: (eventId: string) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/v1/jobs/${jobId}/events`, {
    headers: {
      ...authHeaders(),
      Accept: "text/event-stream",
      ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
    },
    cache: "no-store",
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`任务事件连接失败（${response.status}）`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder
      .decode(chunk.value, { stream: true })
      .replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const idLine = block.split("\n").find((line) => line.startsWith("id:"));
      const dataLine = block
        .split("\n")
        .find((line) => line.startsWith("data:"));
      if (idLine && dataLine) onEvent(idLine.slice(3).trim());
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export function WorkspaceApp() {
  const [view, setView] = useState<
    "loading" | "home" | "workspace" | "monitor" | "presentation"
  >("loading");
  const [templates, setTemplates] = useState<TemplateVersion[]>([]);
  const [entitlement, setEntitlement] = useState<Entitlement | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [history, setHistory] = useState<DraftSnapshot[]>([]);
  const [topic, setTopic] = useState("");
  const [source, setSource] = useState<SourceState | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftSnapshot | null>(null);
  const [intent, setIntent] = useState<IntentRevision | null>(null);
  const [outline, setOutline] = useState<OutlineRevision | null>(null);
  const [summary, setSummary] = useState<GenerationSummary | null>(null);
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(
    null,
  );
  const [presentation, setPresentation] = useState<Presentation | null>(null);
  const [presentationMessage, setPresentationMessage] = useState(
    "这是 AI 可编辑草稿，每次修改都会创建不可变版本。",
  );
  const [regenerationInstruction, setRegenerationInstruction] =
    useState("让结论更清晰，并保留当前事实");
  const [streamState, setStreamState] = useState<StreamState>("closed");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [failedSaveKind, setFailedSaveKind] = useState<FailedSaveKind>(null);
  const [busyMessage, setBusyMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [assistantInput, setAssistantInput] = useState("");
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [assistantMessage, setAssistantMessage] =
    useState("我会把每次优化写成真实大纲版本。");
  const [undoStack, setUndoStack] = useState<OutlineRevision[]>([]);
  const [redoStack, setRedoStack] = useState<OutlineRevision[]>([]);
  const historyButtonRef = useRef<HTMLButtonElement>(null);
  const historyDialogRef = useRef<HTMLDialogElement>(null);
  const lastSavedIntent = useRef("");
  const lastSavedOutline = useRef("");
  const serverOutline = useRef<OutlineRevision | null>(null);
  const intentInFlight = useRef(false);
  const outlineInFlight = useRef(false);
  const intentEditToken = useRef(0);
  const outlineEditToken = useRef(0);
  const lastEventId = useRef("");
  const jobRefreshInFlight = useRef(false);

  useEffect(() => {
    const tablet = window.matchMedia(
      "(min-width: 768px) and (max-width: 1199px)",
    );
    const keepNonTabletOpen = () => {
      if (!tablet.matches) setAssistantOpen(true);
    };
    keepNonTabletOpen();
    tablet.addEventListener("change", keepNonTabletOpen);
    return () => tablet.removeEventListener("change", keepNonTabletOpen);
  }, []);

  const refreshHistory = useCallback(async () => {
    const response = await api<{ items: DraftSnapshot[] }>(
      "/v1/history?limit=20",
    );
    setHistory(response.data.items);
  }, []);

  const loadPresentation = useCallback(
    async (presentationId: string, push = false, showLoading = false) => {
      if (showLoading) setView("loading");
      try {
        const response = await api<Presentation>(
          `/v1/presentations/${presentationId}`,
        );
        setPresentation(response.data);
        setPresentationMessage(
          `当前为第 ${response.data.currentRevision.revisionNumber} 个不可变版本。`,
        );
        setView("presentation");
        if (push) {
          window.history.pushState(
            {},
            "",
            `/?draft=${response.data.draftId}&presentation=${response.data.presentationId}`,
          );
        }
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "演示文稿恢复失败");
        if (showLoading) setView("home");
      }
    },
    [],
  );

  const loadGenerationJob = useCallback(
    async (jobId: string, push = false, showLoading = false) => {
      if (jobRefreshInFlight.current) return;
      jobRefreshInFlight.current = true;
      if (showLoading) setView("loading");
      try {
        const response = await api<GenerationJob>(`/v1/jobs/${jobId}`);
        setGenerationJob(response.data);
        if (!lastEventId.current) {
          lastEventId.current = String(response.data.latestSeq);
        }
        setView("monitor");
        if (push) {
          window.history.pushState(
            {},
            "",
            `/?draft=${response.data.draftId}&job=${response.data.jobId}`,
          );
        }
        if (response.data.terminal) {
          setStreamState("closed");
          const usageResponse = await api<Usage>("/v1/me/usage");
          setUsage(usageResponse.data);
        }
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "任务恢复失败");
        if (showLoading) setView("home");
      } finally {
        jobRefreshInFlight.current = false;
      }
    },
    [],
  );

  const openDraft = useCallback(async (draftId: string, push = true) => {
    setView("loading");
    setError(null);
    try {
      const response = await api<DraftSnapshot>(`/v1/drafts/${draftId}`);
      const next = response.data;
      setDraft(next);
      setGenerationJob(null);
      setStreamState("closed");
      lastEventId.current = "";
      setIntent(next.currentIntent);
      setOutline(next.currentOutline);
      setSummary(next.generationSummary);
      lastSavedIntent.current = next.currentIntent
        ? JSON.stringify(intentPayload(next.currentIntent))
        : "";
      lastSavedOutline.current = next.currentOutline
        ? JSON.stringify(outlinePayload(next.currentOutline))
        : "";
      serverOutline.current = next.currentOutline;
      if (next.currentOutline) {
        const revisions = await api<{ items: OutlineRevision[] }>(
          `/v1/drafts/${draftId}/outline-revisions`,
        );
        setUndoStack(revisions.data.items.slice(0, -1));
      } else {
        setUndoStack([]);
      }
      setRedoStack([]);
      setSaveState("saved");
      setView("workspace");
      if (push) window.history.pushState({}, "", `/?draft=${draftId}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "草稿恢复失败");
      setView("home");
    }
  }, []);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      try {
        const [templateResponse, entitlementResponse, usageResponse] =
          await Promise.all([
            api<{ items: TemplateVersion[] }>("/v1/templates"),
            api<Entitlement>("/v1/me/entitlements"),
            api<Usage>("/v1/me/usage"),
          ]);
        if (!active) return;
        setTemplates(templateResponse.data.items);
        setSelectedTemplate(
          (current) =>
            current ??
            templateResponse.data.items[0]?.templateVersionId ??
            null,
        );
        setEntitlement(entitlementResponse.data);
        setUsage(usageResponse.data);
        await refreshHistory();
        const parameters = new URLSearchParams(window.location.search);
        const presentationId = parameters.get("presentation");
        const jobId = parameters.get("job");
        const draftId = parameters.get("draft");
        if (presentationId)
          await loadPresentation(presentationId, false, false);
        else if (jobId) await loadGenerationJob(jobId, false, false);
        else if (draftId) await openDraft(draftId, false);
        else setView("home");
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "初始化失败");
        setView("home");
      }
    }
    void bootstrap();
    return () => {
      active = false;
    };
  }, [loadGenerationJob, loadPresentation, openDraft, refreshHistory]);

  const generationJobId = generationJob?.jobId;
  const generationJobTerminal = generationJob?.terminal;

  useEffect(() => {
    if (view !== "monitor" || !generationJobId || generationJobTerminal) return;
    const activeJobId = generationJobId;
    const controller = new AbortController();
    let reconnectAttempt = 0;
    let active = true;
    async function connect() {
      while (active && !controller.signal.aborted) {
        setStreamState(reconnectAttempt === 0 ? "connecting" : "reconnecting");
        try {
          await streamGenerationEvents(
            activeJobId,
            controller.signal,
            lastEventId.current,
            (eventId) => {
              lastEventId.current = eventId;
              setStreamState("live");
              void loadGenerationJob(activeJobId);
            },
          );
          if (!controller.signal.aborted) reconnectAttempt += 1;
        } catch (reason) {
          if (controller.signal.aborted) return;
          reconnectAttempt += 1;
          setError(
            reason instanceof Error ? reason.message : "任务事件连接已中断",
          );
        }
        if (!active || controller.signal.aborted) return;
        const delay = Math.min(1000 * 2 ** (reconnectAttempt - 1), 8000);
        await new Promise<void>((resolve) => window.setTimeout(resolve, delay));
      }
    }
    void connect();
    return () => {
      active = false;
      controller.abort();
    };
  }, [generationJobId, generationJobTerminal, loadGenerationJob, view]);

  useEffect(() => {
    const dialog = historyDialogRef.current;
    if (!dialog) return;
    if (historyOpen && !dialog.open) dialog.showModal();
    if (!historyOpen && dialog.open) dialog.close();
  }, [historyOpen]);

  const onSourceReady = useCallback((next: SourceState) => setSource(next), []);

  const createWorkspace = async () => {
    if (!topic.trim() && !source?.sourceId) return;
    setBusyMessage("正在创建草稿…");
    setError(null);
    try {
      const created = await api<DraftSnapshot>("/v1/drafts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: mutation({
          topic,
          sourceId: source?.sourceId ?? null,
          mode: "native",
          templateVersionId: selectedTemplate,
        }),
      });
      window.history.replaceState({}, "", `/?draft=${created.data.draftId}`);
      setBusyMessage("正在推断创作意图…");
      const inferred = await api<IntentRevision>(
        `/v1/drafts/${created.data.draftId}/intent:infer`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({ language: "zh-CN" }),
        },
      );
      setBusyMessage("正在生成可编辑大纲…");
      await api<OutlineRevision>(
        `/v1/drafts/${created.data.draftId}/outline:generate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({ action: "generate", instruction: "" }),
        },
      );
      void inferred;
      await refreshHistory();
      await openDraft(created.data.draftId, false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "草稿创建失败");
    } finally {
      setBusyMessage(null);
    }
  };

  const persistIntent = useCallback(
    async (value: IntentRevision) => {
      if (!draft || intentInFlight.current) return;
      intentInFlight.current = true;
      const editToken = intentEditToken.current;
      setSaveState("saving");
      try {
        const response = await api<IntentRevision>(
          `/v1/drafts/${draft.draftId}/intent-revisions`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Idempotency-Key": crypto.randomUUID(),
            },
            body: mutation(intentPayload(value), draft.currentIntentRevisionId),
          },
        );
        lastSavedIntent.current = JSON.stringify(intentPayload(response.data));
        setDraft((current) =>
          current
            ? {
                ...current,
                currentIntentRevisionId: response.data.intentRevisionId,
              }
            : current,
        );
        if (intentEditToken.current === editToken) setIntent(response.data);
        setFailedSaveKind(null);
        setSaveState("saved");
      } catch (reason) {
        setFailedSaveKind("intent");
        setSaveState("failed");
        setError(reason instanceof Error ? reason.message : "意图保存失败");
      } finally {
        intentInFlight.current = false;
      }
    },
    [draft],
  );

  useEffect(() => {
    if (!intent || !draft || intentInFlight.current || saveState === "failed")
      return;
    const serialized = JSON.stringify(intentPayload(intent));
    if (serialized === lastSavedIntent.current) return;
    setSaveState("saving");
    const timer = window.setTimeout(() => void persistIntent(intent), 800);
    return () => window.clearTimeout(timer);
  }, [draft, intent, persistIntent, saveState]);

  const persistOutline = useCallback(
    async (value: OutlineRevision, operation: string, addUndo: boolean) => {
      if (!draft || outlineInFlight.current) return;
      outlineInFlight.current = true;
      const editToken = outlineEditToken.current;
      const previous = serverOutline.current;
      setSaveState("saving");
      try {
        const response = await api<OutlineRevision>(
          `/v1/drafts/${draft.draftId}/outline-revisions`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Idempotency-Key": crypto.randomUUID(),
            },
            body: mutation(
              outlinePayload(value, operation),
              draft.currentOutlineRevisionId,
            ),
          },
        );
        if (addUndo && previous) setUndoStack((stack) => [...stack, previous]);
        if (addUndo) setRedoStack([]);
        serverOutline.current = response.data;
        lastSavedOutline.current = JSON.stringify(
          outlinePayload(response.data),
        );
        setDraft((current) =>
          current
            ? {
                ...current,
                currentOutlineRevisionId: response.data.outlineRevisionId,
                status: "outline_ready",
              }
            : current,
        );
        if (outlineEditToken.current === editToken) setOutline(response.data);
        setFailedSaveKind(null);
        setSaveState("saved");
      } catch (reason) {
        setFailedSaveKind("outline");
        setSaveState("failed");
        setError(reason instanceof Error ? reason.message : "大纲保存失败");
      } finally {
        outlineInFlight.current = false;
      }
    },
    [draft],
  );

  useEffect(() => {
    if (!outline || !draft || outlineInFlight.current || saveState === "failed")
      return;
    const serialized = JSON.stringify(outlinePayload(outline));
    if (serialized === lastSavedOutline.current) return;
    setSaveState("saving");
    const timer = window.setTimeout(
      () => void persistOutline(outline, "edit", true),
      800,
    );
    return () => window.clearTimeout(timer);
  }, [draft, outline, persistOutline, saveState]);

  const changeIntent = <Key extends keyof IntentRevision>(
    key: Key,
    value: IntentRevision[Key],
  ) => {
    intentEditToken.current += 1;
    setIntent((current) => (current ? { ...current, [key]: value } : current));
  };

  const setOutlineAndCommit = (next: OutlineRevision, operation: string) => {
    outlineEditToken.current += 1;
    setOutline(next);
    void persistOutline(next, operation, true);
  };

  const mutateSlide = (
    index: number,
    mutate: (slide: OutlineSlide) => OutlineSlide,
  ) => {
    if (!outline) return;
    outlineEditToken.current += 1;
    setOutline({
      ...outline,
      slides: outline.slides.map((slide, position) =>
        position === index ? mutate(slide) : slide,
      ),
    });
  };

  const moveSlide = (index: number, offset: number) => {
    if (!outline) return;
    const target = index + offset;
    if (target < 0 || target >= outline.slides.length) return;
    const slides = [...outline.slides];
    [slides[index], slides[target]] = [slides[target], slides[index]];
    setOutlineAndCommit({ ...outline, slides }, "move");
  };

  const addSlide = () => {
    if (!outline || outline.slides.length >= 30) return;
    const next: OutlineRevision = {
      ...outline,
      targetSlideCount: Math.min(30, outline.targetSlideCount + 1),
      slides: [
        ...outline.slides,
        {
          outlineSlideId: clientUlid(),
          type: "content",
          title: "新增页面",
          keyPoints: ["补充这一页的核心论点"],
          sourceCitations: [],
        },
      ],
    };
    setOutlineAndCommit(next, "add");
  };

  const deleteSlide = (index: number) => {
    if (!outline || outline.slides.length <= 1) return;
    const next = {
      ...outline,
      targetSlideCount: Math.max(4, outline.targetSlideCount - 1),
      slides: outline.slides.filter((_, position) => position !== index),
    };
    setOutlineAndCommit(next, "delete");
  };

  const runAiRevision = async (
    action: "optimize" | "rewrite_slide",
    targetSlideId: string | null = null,
  ) => {
    if (!draft || !outline || outlineInFlight.current) return;
    outlineInFlight.current = true;
    setSaveState("saving");
    setAssistantMessage("AI 正在生成一个可比较的新版本…");
    try {
      const response = await api<OutlineRevision>(
        `/v1/drafts/${draft.draftId}/outline:generate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation(
            {
              action,
              instruction: assistantInput,
              outlineSlideId: targetSlideId,
            },
            draft.currentOutlineRevisionId,
          ),
        },
      );
      if (serverOutline.current)
        setUndoStack((stack) => [...stack, serverOutline.current!]);
      setRedoStack([]);
      serverOutline.current = response.data;
      lastSavedOutline.current = JSON.stringify(outlinePayload(response.data));
      setOutline(response.data);
      setDraft((current) =>
        current
          ? {
              ...current,
              currentOutlineRevisionId: response.data.outlineRevisionId,
            }
          : current,
      );
      setAssistantInput("");
      setAssistantMessage(
        `已创建 ${response.data.outlineRevisionId.slice(-6)} 版本，可撤销。`,
      );
      setSaveState("saved");
    } catch (reason) {
      setSaveState("failed");
      setAssistantMessage("AI 未能创建版本，现有内容保持不变。可重试。");
      setError(reason instanceof Error ? reason.message : "AI 优化失败");
    } finally {
      outlineInFlight.current = false;
    }
  };

  const undo = () => {
    if (!outline || undoStack.length === 0) return;
    const target = undoStack[undoStack.length - 1];
    setUndoStack((stack) => stack.slice(0, -1));
    setRedoStack((stack) => [...stack, outline]);
    outlineEditToken.current += 1;
    setOutline(target);
    void persistOutline(target, "undo", false);
  };

  const redo = () => {
    if (!outline || redoStack.length === 0) return;
    const target = redoStack[redoStack.length - 1];
    setRedoStack((stack) => stack.slice(0, -1));
    setUndoStack((stack) => [...stack, outline]);
    outlineEditToken.current += 1;
    setOutline(target);
    void persistOutline(target, "redo", false);
  };

  const approve = async () => {
    if (!draft?.currentOutlineRevisionId) return;
    setBusyMessage("正在固定批准边界…");
    setError(null);
    try {
      const response = await api<GenerationSummary>(
        `/v1/outline-revisions/${draft.currentOutlineRevisionId}:approve`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({}),
        },
      );
      setSummary(response.data);
      setDraft((current) =>
        current
          ? {
              ...current,
              approvedOutlineRevisionId: response.data.outlineRevisionId,
              status: "approved",
            }
          : current,
      );
      await refreshHistory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批准失败");
    } finally {
      setBusyMessage(null);
    }
  };

  const startGeneration = async () => {
    if (
      !draft ||
      !summary ||
      draft.currentOutlineRevisionId !== summary.outlineRevisionId ||
      saveState === "saving"
    )
      return;
    setBusyMessage("正在创建真实生成任务…");
    setError(null);
    try {
      const response = await api<GenerationJob>(
        `/v1/drafts/${draft.draftId}/generation-jobs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({}),
        },
      );
      setGenerationJob(response.data);
      lastEventId.current = String(response.data.latestSeq);
      setStreamState("connecting");
      setView("monitor");
      window.history.pushState(
        {},
        "",
        `/?draft=${draft.draftId}&job=${response.data.jobId}`,
      );
      await refreshHistory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "生成任务创建失败");
    } finally {
      setBusyMessage(null);
    }
  };

  const cancelGeneration = async () => {
    if (!generationJob || generationJob.terminal) return;
    setBusyMessage("正在请求取消…");
    setError(null);
    try {
      const response = await api<GenerationJob>(
        `/v1/jobs/${generationJob.jobId}:cancel`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({}),
        },
      );
      setGenerationJob(response.data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "取消请求失败");
    } finally {
      setBusyMessage(null);
    }
  };

  const retryGenerationSlide = async (slideId: string) => {
    if (!generationJob) return;
    setBusyMessage("正在重试失败页面…");
    setError(null);
    try {
      await api<{ status: string; attempt: number }>(
        `/v1/jobs/${generationJob.jobId}/slides/${slideId}:retry`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({}),
        },
      );
      lastEventId.current = "";
      await loadGenerationJob(generationJob.jobId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "页面重试失败");
    } finally {
      setBusyMessage(null);
    }
  };

  const applyPresentationOperations = async (
    operations: Array<Record<string, unknown>>,
    message: string,
  ) => {
    if (!presentation || busyMessage) return;
    setBusyMessage(message);
    setError(null);
    try {
      await api<PresentationRevision>(
        `/v1/presentations/${presentation.presentationId}/revisions`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({ operations }, presentation.currentRevisionId),
        },
      );
      await loadPresentation(presentation.presentationId);
      setPresentationMessage("修改已保存为新版本，可从版本历史追溯。");
      await refreshHistory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "演示文稿修改失败");
      setPresentationMessage("当前版本保持不变；本地输入仍在，可重试。");
    } finally {
      setBusyMessage(null);
    }
  };

  const changePresentationSlide = (
    slideId: string,
    change: Partial<Pick<PresentationSlide, "title" | "body">>,
  ) => {
    setPresentation((current) =>
      current
        ? {
            ...current,
            currentRevision: {
              ...current.currentRevision,
              slides: current.currentRevision.slides.map((slide) =>
                slide.slideId === slideId ? { ...slide, ...change } : slide,
              ),
            },
          }
        : current,
    );
  };

  const regeneratePresentationSlide = async (slideId: string) => {
    if (!presentation || busyMessage) return;
    const instruction = regenerationInstruction.trim();
    setBusyMessage("AI 正在后台重生成；旧版本仍可见…");
    setPresentationMessage("候选页通过质量检查前，当前就绪版本不会被替换。");
    setError(null);
    try {
      const queued = await api<RegenerationOperation>(
        `/v1/presentations/${presentation.presentationId}/slides/${slideId}:regenerate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({ instruction }, presentation.currentRevisionId),
        },
      );
      let operation = queued.data;
      for (
        let attempt = 0;
        attempt < 120 &&
        (operation.status === "queued" || operation.status === "running");
        attempt += 1
      ) {
        await new Promise<void>((resolve) => window.setTimeout(resolve, 500));
        operation = (
          await api<RegenerationOperation>(
            `/v1/operations/${queued.data.regenerationJobId}`,
          )
        ).data;
      }
      if (operation.status !== "succeeded") {
        throw new Error(
          operation.errorCode
            ? `单页重生成失败：${operation.errorCode}`
            : "单页重生成未能完成",
        );
      }
      await loadPresentation(presentation.presentationId);
      setPresentationMessage("新页面已通过质量检查并原子切换为当前版本。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "单页重生成失败");
      setPresentationMessage("重生成未发布；之前的就绪版本仍保持可见。");
    } finally {
      setBusyMessage(null);
    }
  };

  const exportPresentation = async () => {
    if (!presentation || busyMessage) return;
    setBusyMessage("正在按当前精确版本编译并执行包检…");
    setError(null);
    try {
      const queued = await api<PresentationExport>(
        `/v1/presentations/${presentation.presentationId}/exports`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation(
            {
              presentationRevisionId: presentation.currentRevisionId,
              filename: `${presentation.title}.pptx`,
            },
            presentation.currentRevisionId,
          ),
        },
      );
      let exportJob = queued.data;
      for (
        let attempt = 0;
        attempt < 120 &&
        (exportJob.status === "queued" || exportJob.status === "running");
        attempt += 1
      ) {
        await new Promise<void>((resolve) => window.setTimeout(resolve, 500));
        exportJob = (
          await api<PresentationExport>(`/v1/exports/${queued.data.exportId}`)
        ).data;
      }
      if (exportJob.status !== "succeeded" || !exportJob.artifactId) {
        throw new Error(
          exportJob.errorCode
            ? `导出失败：${exportJob.errorCode}`
            : "导出未能完成",
        );
      }
      const authorization = await api<{
        downloadUrl: string;
        expiresAt: string;
      }>(`/v1/artifacts/${exportJob.artifactId}:authorize-download`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: mutation({}),
      });
      await downloadAuthorizedFile(
        authorization.data.downloadUrl,
        `${presentation.title}.pptx`,
      );
      setPresentationMessage(
        `已导出版本 ${exportJob.presentationRevisionId.slice(-8)}，短期下载链接已签发。`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出失败");
    } finally {
      setBusyMessage(null);
    }
  };

  const exportProjectData = async () => {
    if (!presentation || busyMessage) return;
    setBusyMessage("正在固定项目数据快照…");
    setError(null);
    try {
      const result = await api<{ artifactId: string }>(
        `/v1/drafts/${presentation.draftId}:export-data`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({}),
        },
      );
      const authorization = await api<{ downloadUrl: string }>(
        `/v1/artifacts/${result.data.artifactId}:authorize-download`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({}),
        },
      );
      await downloadAuthorizedFile(
        authorization.data.downloadUrl,
        `${presentation.title}-project-data.json`,
      );
      setPresentationMessage("项目结构化数据快照已固定并可下载。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目数据导出失败");
    } finally {
      setBusyMessage(null);
    }
  };

  const deleteProject = async () => {
    if (!presentation || busyMessage) return;
    setBusyMessage("正在撤销访问并排队清理项目…");
    try {
      const response = await fetch(
        `${API_BASE}/v1/drafts/${presentation.draftId}`,
        { method: "DELETE", headers: authHeaders() },
      );
      if (!response.ok) throw new Error(`删除失败（${response.status}）`);
      setPresentation(null);
      setBusyMessage(null);
      returnHome();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目删除失败");
      setBusyMessage(null);
    }
  };

  const openHistoryItem = (item: DraftSnapshot) => {
    setHistoryOpen(false);
    if (item.historyState === "result" && item.presentationId) {
      void loadPresentation(item.presentationId, true, true);
    } else if (item.historyState === "monitor" && item.jobId) {
      void loadGenerationJob(item.jobId, true, true);
    } else {
      void openDraft(item.draftId);
    }
  };

  const returnHome = () => {
    setView("home");
    setGenerationJob(null);
    setPresentation(null);
    setStreamState("closed");
    lastEventId.current = "";
    window.history.pushState({}, "", "/");
    void refreshHistory();
  };

  if (view === "loading") {
    return (
      <main
        id="main-content"
        className="loading-screen"
        aria-live="polite"
        tabIndex={-1}
      >
        <span className="loading-mark">即</span>
        <p>正在恢复你的创作现场…</p>
      </main>
    );
  }

  return (
    <main
      id="main-content"
      className={view === "home" ? "home-shell" : "workspace-shell"}
      tabIndex={-1}
    >
      <header className="product-header" aria-label="产品导航">
        <button
          className="brand brand-button"
          type="button"
          onClick={returnHome}
        >
          <span className="brand-mark" aria-hidden="true">
            即
          </span>
          <span>即刻AI-PPT</span>
        </button>
        <div className="header-actions">
          {entitlement ? (
            <span className="quota-chip">
              本月 {usage?.metrics.slides ?? 0} /{" "}
              {entitlement.monthlySlideLimit} 页
            </span>
          ) : null}
          <button
            ref={historyButtonRef}
            className="quiet-button"
            type="button"
            onClick={() => setHistoryOpen(true)}
          >
            历史创作
          </button>
        </div>
      </header>

      {view === "presentation" && presentation ? (
        <div className="presentation-editor">
          <div className="presentation-topbar">
            <button
              className="quiet-button"
              type="button"
              onClick={() => void openDraft(presentation.draftId)}
            >
              ← 返回大纲
            </button>
            <div>
              <strong>{presentation.title}</strong>
              <span aria-live="polite">
                rev {presentation.currentRevision.revisionNumber} ·{" "}
                {presentation.currentRevisionId.slice(-8)}
              </span>
            </div>
            <div className="presentation-top-actions">
              <button
                className="secondary-button"
                type="button"
                disabled={Boolean(busyMessage)}
                onClick={() => void exportProjectData()}
              >
                导出项目数据
              </button>
              <button
                className="primary-button"
                type="button"
                disabled={
                  Boolean(busyMessage) ||
                  (presentation.currentRevision.partial &&
                    !presentation.currentRevision.acceptedMissing)
                }
                onClick={() => void exportPresentation()}
              >
                {busyMessage ?? "导出当前版本 PPTX"}
              </button>
            </div>
          </div>

          <section
            className="ai-draft-banner"
            aria-labelledby="draft-banner-title"
          >
            <div>
              <p className="eyebrow">AI EDITABLE DRAFT</p>
              <h1 id="draft-banner-title">AI 可编辑草稿</h1>
              <p aria-live="polite">{presentationMessage}</p>
              <label className="regeneration-instruction">
                <span>AI 单页修改要求</span>
                <input
                  value={regenerationInstruction}
                  maxLength={2000}
                  onChange={(event) =>
                    setRegenerationInstruction(event.target.value)
                  }
                  placeholder="例如：让结论更锋利，并保留数据事实"
                />
              </label>
            </div>
            <dl>
              <div>
                <dt>状态</dt>
                <dd>
                  {presentation.status === "ready" ? "全部就绪" : "部分就绪"}
                </dd>
              </div>
              <div>
                <dt>页面</dt>
                <dd>{presentation.currentRevision.slides.length}</dd>
              </div>
              <div>
                <dt>版本锁</dt>
                <dd>{presentation.lockVersion}</dd>
              </div>
            </dl>
          </section>

          {error ? (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button type="button" onClick={() => setError(null)}>
                关闭
              </button>
            </div>
          ) : null}

          {presentation.currentRevision.partial ? (
            <section
              className="partial-warning"
              aria-labelledby="partial-title"
            >
              <div>
                <p className="eyebrow">NO SILENT OMISSION</p>
                <h2 id="partial-title">仍有失败页面，不会静默漏导</h2>
                <p>可重生成失败页、删除对应槽位，或明确接受缺页后导出。</p>
              </div>
              <button
                className="secondary-button"
                type="button"
                disabled={
                  presentation.currentRevision.acceptedMissing ||
                  Boolean(busyMessage)
                }
                onClick={() =>
                  void applyPresentationOperations(
                    [{ type: "accept_missing" }],
                    "正在记录缺页接受决定…",
                  )
                }
              >
                {presentation.currentRevision.acceptedMissing
                  ? "已明确接受缺页"
                  : "明确接受缺页并允许导出"}
              </button>
            </section>
          ) : null}

          <section
            className="presentation-slides"
            aria-labelledby="presentation-slides-title"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">IMMUTABLE SLIDE VERSIONS</p>
                <h2 id="presentation-slides-title">逐页编辑</h2>
              </div>
              <p>可编辑文字、调整顺序、删除或让 AI 只重生成一页。</p>
            </div>
            <div className="presentation-slide-list">
              {presentation.currentRevision.slides.map((slide, index) => (
                <article
                  className={`presentation-slide-card status-${slide.status}`}
                  key={slide.slideId}
                >
                  <div className="presentation-slide-number">
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <small>
                      {slide.status === "ready" ? "已就绪" : "失败槽位"}
                    </small>
                  </div>
                  <div className="presentation-slide-copy">
                    <label>
                      <span>页面标题</span>
                      <input
                        value={slide.title}
                        maxLength={300}
                        onChange={(event) =>
                          changePresentationSlide(slide.slideId, {
                            title: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      <span>正文要点（每行一个）</span>
                      <textarea
                        rows={4}
                        value={slide.body.join("\n")}
                        onChange={(event) =>
                          changePresentationSlide(slide.slideId, {
                            body: event.target.value.split("\n"),
                          })
                        }
                      />
                    </label>
                    <small>
                      stable slide · {slide.slideId.slice(-8)} · version{" "}
                      {slide.slideVersionId.slice(-8)}
                    </small>
                  </div>
                  <div
                    className="presentation-slide-actions"
                    aria-label={`第 ${index + 1} 页操作`}
                  >
                    <button
                      type="button"
                      disabled={index === 0 || Boolean(busyMessage)}
                      onClick={() =>
                        void applyPresentationOperations(
                          [
                            {
                              type: "move",
                              slideId: slide.slideId,
                              position: index,
                            },
                          ],
                          "正在创建排序版本…",
                        )
                      }
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      disabled={
                        index ===
                          presentation.currentRevision.slides.length - 1 ||
                        Boolean(busyMessage)
                      }
                      onClick={() =>
                        void applyPresentationOperations(
                          [
                            {
                              type: "move",
                              slideId: slide.slideId,
                              position: index + 2,
                            },
                          ],
                          "正在创建排序版本…",
                        )
                      }
                    >
                      ↓
                    </button>
                    <button
                      className="save-slide-button"
                      type="button"
                      disabled={!slide.title.trim() || Boolean(busyMessage)}
                      onClick={() =>
                        void applyPresentationOperations(
                          [
                            {
                              type: "update_text",
                              slideId: slide.slideId,
                              title: slide.title,
                              body: slide.body,
                            },
                          ],
                          "正在保存页面版本…",
                        )
                      }
                    >
                      保存文字
                    </button>
                    <button
                      type="button"
                      disabled={Boolean(busyMessage)}
                      onClick={() =>
                        void regeneratePresentationSlide(slide.slideId)
                      }
                    >
                      AI 重生成
                    </button>
                    <button
                      className="danger-button"
                      type="button"
                      disabled={
                        presentation.currentRevision.slides.length === 1 ||
                        Boolean(busyMessage)
                      }
                      onClick={() =>
                        void applyPresentationOperations(
                          [{ type: "delete", slideId: slide.slideId }],
                          "正在创建删除版本…",
                        )
                      }
                    >
                      删除
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section
            className="project-lifecycle"
            aria-labelledby="project-lifecycle-title"
          >
            <div>
              <p className="eyebrow">PROJECT LIFECYCLE</p>
              <h2 id="project-lifecycle-title">项目访问与清理</h2>
              <p>
                删除后 API、事件流和下载授权会立即失效，对象由后台审计任务清理。
              </p>
            </div>
            <button
              className="danger-button"
              type="button"
              disabled={Boolean(busyMessage)}
              onClick={() => void deleteProject()}
            >
              删除整个项目
            </button>
          </section>
        </div>
      ) : view === "monitor" && generationJob ? (
        <div className="generation-monitor">
          <div className="monitor-topbar">
            <button
              className="quiet-button"
              type="button"
              onClick={() => void openDraft(generationJob.draftId)}
            >
              ← 返回大纲
            </button>
            <div>
              <strong>真实生成任务 · {generationJob.jobId.slice(-6)}</strong>
              <span
                className={`stream-state stream-${streamState}`}
                aria-live="polite"
              >
                <i aria-hidden="true" />
                {streamState === "live"
                  ? "实时事件已连接"
                  : streamState === "closed"
                    ? "任务状态已固定"
                    : streamState === "reconnecting"
                      ? "事件重连中"
                      : "正在连接事件"}
              </span>
            </div>
            <button
              className="secondary-button"
              type="button"
              disabled={generationJob.terminal || Boolean(busyMessage)}
              onClick={() => void cancelGeneration()}
            >
              {generationJob.status === "cancel_requested"
                ? "正在取消"
                : "取消任务"}
            </button>
          </div>

          <ol className="stepper monitor-stepper" aria-label="生成步骤">
            {[
              ["01", "生成计划", "deck_planning"],
              ["02", "逐页生成", "slide_generation"],
              ["03", "整稿检查", "deck_qa"],
              ["04", "编译与包检", "compiling"],
              ["05", "不可变发布", "publishing"],
            ].map(([number, label, stage], index, stages) => {
              const currentIndex = stages.findIndex(
                ([, , candidate]) => candidate === generationJob.stage,
              );
              const packageStage = generationJob.stage === "package_qa";
              const effectiveIndex = packageStage ? 3 : currentIndex;
              const complete = generationJob.terminal || index < effectiveIndex;
              const active =
                !generationJob.terminal && index === effectiveIndex;
              return (
                <li
                  key={stage}
                  className={complete ? "done" : active ? "active" : ""}
                >
                  <b>{number}</b>
                  <span>{label}</span>
                </li>
              );
            })}
          </ol>

          {error ? (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button type="button" onClick={() => setError(null)}>
                关闭
              </button>
            </div>
          ) : null}

          <section className="monitor-hero" aria-labelledby="monitor-title">
            <div className="monitor-status-copy">
              <p className="eyebrow">DURABLE GENERATION · NATIVE MODE</p>
              <h1 id="monitor-title">
                {generationStatusLabel(generationJob.status)}
              </h1>
              <p aria-live="polite">
                {generationJob.terminal
                  ? generationJob.status === "succeeded"
                    ? "全部页面、原生 PPTX 与不可变清单已经发布。"
                    : generationJob.status === "partially_succeeded"
                      ? "成功页面已发布；失败槽位保留，可单页重试。"
                      : generationJob.status === "cancelled"
                        ? "任务已安全终止，未创建演示文稿。"
                        : "任务未发布演示文稿，可返回大纲检查输入。"
                  : generationStageLabel(generationJob.stage)}
              </p>
              <div className="progress-copy">
                <span>
                  {generationJob.progress.completed} /{" "}
                  {generationJob.progress.total} 页就绪
                </span>
                <span>任务尝试 {generationJob.attempt}</span>
              </div>
              <progress
                max={generationJob.progress.total}
                value={generationJob.progress.completed}
                aria-label="页面生成进度"
              />
            </div>
            <dl className="monitor-facts">
              <div>
                <dt>Snapshot</dt>
                <dd>{generationJob.snapshotId.slice(-10)}</dd>
              </div>
              <div>
                <dt>事件序号</dt>
                <dd>{generationJob.latestSeq}</dd>
              </div>
              <div>
                <dt>发布版本</dt>
                <dd>v{generationJob.publicationVersion}</dd>
              </div>
              <div>
                <dt>处理器</dt>
                <dd>
                  {generationJob.processor === "real"
                    ? "真实 Worker"
                    : "Fixture"}
                </dd>
              </div>
            </dl>
          </section>

          <section
            className="monitor-slides"
            aria-labelledby="monitor-slides-title"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">STABLE SLIDE IDS</p>
                <h2 id="monitor-slides-title">逐页状态</h2>
              </div>
              <p>刷新或重试不会改变页面身份；成功页面不会重复生成。</p>
            </div>
            <div className="generation-slide-grid">
              {generationJob.slides.map((slide) => (
                <article
                  className={`generation-slide status-${slide.status}`}
                  key={slide.slideId}
                >
                  <div className="generation-slide-head">
                    <span>{String(slide.position).padStart(2, "0")}</span>
                    <strong>
                      {slide.status === "ready" ? "已就绪" : slide.status}
                    </strong>
                  </div>
                  <h3>{slide.title}</h3>
                  <p>
                    {slide.status === "running" || slide.status === "retrying"
                      ? slide.stage === "content_generation"
                        ? "生成内容"
                        : slide.stage === "rendering"
                          ? "渲染 SVG"
                          : "逐页质量检查"
                      : slide.status === "failed"
                        ? `错误：${slide.errorCode ?? "slide_failed"}`
                        : slide.status === "ready"
                          ? `渲染指纹 ${slide.renderSha256?.slice(0, 12) ?? "待发布"}…`
                          : "等待 Worker"}
                  </p>
                  <small>
                    slide · {slide.slideId.slice(-8)} · attempt {slide.attempt}
                  </small>
                  {slide.status === "failed" && slide.attempt < 2 ? (
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={Boolean(busyMessage)}
                      onClick={() => void retryGenerationSlide(slide.slideId)}
                    >
                      只重试这一页
                    </button>
                  ) : null}
                </article>
              ))}
            </div>
          </section>

          {generationJob.presentation ? (
            <section
              className="publication-card"
              aria-labelledby="publication-title"
            >
              <div>
                <p className="eyebrow">IMMUTABLE GENERATION PUBLICATION</p>
                <h2 id="publication-title">
                  {generationJob.presentation.status === "ready"
                    ? "原生基线已发布"
                    : "部分基线已发布"}
                </h2>
                <p>
                  修订 {generationJob.presentation.currentRevisionId.slice(-8)}{" "}
                  · 清单{" "}
                  {generationJob.publication?.manifestSha256.slice(0, 14)}…
                </p>
              </div>
              <div className="publication-artifacts">
                {generationJob.artifacts
                  .filter((artifact) => artifact.slideId === null)
                  .map((artifact) => (
                    <span key={artifact.artifactId}>
                      {artifact.artifactType.replace("generation_", "")} ·{" "}
                      {(artifact.sizeBytes / 1024).toFixed(1)} KB
                    </span>
                  ))}
              </div>
              <small>
                生成基线已固定；进入编辑器后的修改会创建独立修订，不会覆盖原始发布。
              </small>
              <button
                className="primary-button"
                type="button"
                onClick={() =>
                  void loadPresentation(
                    generationJob.presentation!.presentationId,
                    true,
                    true,
                  )
                }
              >
                打开可编辑演示
              </button>
            </section>
          ) : null}
        </div>
      ) : view === "home" ? (
        <div className="home-content">
          <section className="creation-hero" aria-labelledby="home-title">
            <div className="creation-copy">
              <p className="eyebrow">IDEA TO EDITABLE DECK</p>
              <h1 id="home-title">让想法即刻成片。</h1>
              <p>
                先确认创作意图与故事结构，再进入原生可编辑 PPT
                生成。每一步都可恢复、可比较、可追溯。
              </p>
              <div className="capability-row" aria-label="当前能力">
                <span>原生专业模式</span>
                <span>不可变版本</span>
                <span>AI 修改可撤销</span>
              </div>
            </div>
            <section
              className="creation-panel"
              aria-labelledby="creation-title"
            >
              <div className="panel-title-row">
                <div>
                  <p className="eyebrow">NEW DRAFT</p>
                  <h2 id="creation-title">今天要讲什么？</h2>
                </div>
                <span className="mode-badge">仅原生专业</span>
              </div>
              <label htmlFor="topic">主题或目标</label>
              <textarea
                id="topic"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="例如：面向管理层的 2027 年产品增长策略"
                rows={4}
                maxLength={1000}
              />
              <div className="or-divider">
                <span>或添加主文档</span>
              </div>
              <SourceUploader onSourceReady={onSourceReady} />
              <button
                className="primary-button create-button"
                type="button"
                disabled={
                  (!topic.trim() && !source?.sourceId) || Boolean(busyMessage)
                }
                onClick={() => void createWorkspace()}
              >
                {busyMessage ?? "生成大纲"}
              </button>
              <p className="boundary-note">
                此步骤只生成意图与大纲，不会启动 PPT 生成任务。
              </p>
            </section>
          </section>

          <section
            className="template-catalog"
            aria-labelledby="template-title"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">BUILT-IN CATALOG</p>
                <h2 id="template-title">选择叙事气质</h2>
              </div>
              <p>模板来自 API 的不可变版本；历史草稿不会随模板升级改变。</p>
            </div>
            <div className="template-grid">
              {templates.map((template) => {
                const selected =
                  selectedTemplate === template.templateVersionId;
                return (
                  <button
                    className={`template-card${selected ? " selected" : ""}`}
                    type="button"
                    key={template.templateVersionId}
                    aria-pressed={selected}
                    onClick={() =>
                      setSelectedTemplate(template.templateVersionId)
                    }
                  >
                    <span
                      className="template-preview"
                      style={
                        {
                          "--preview-primary":
                            template.themeSpec.colorTokens.primary,
                          "--preview-background":
                            template.themeSpec.colorTokens.background,
                        } as CSSProperties
                      }
                    >
                      <i />
                      <b />
                      <em />
                    </span>
                    <span className="template-copy">
                      <strong>{template.name}</strong>
                      <small>{template.description}</small>
                    </span>
                    {selected ? (
                      <span className="selected-label">已选择</span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      ) : draft && intent && outline ? (
        <div className="workspace">
          <div className="workspace-topbar">
            <button className="quiet-button" type="button" onClick={returnHome}>
              ← 返回首页
            </button>
            <div>
              <strong>{draft.title}</strong>
              <span
                className={`save-state save-${saveState}`}
                aria-live="polite"
              >
                {saveLabel(saveState)}
              </span>
            </div>
            <div className="workspace-actions">
              {saveState === "failed" ? (
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => {
                    setError(null);
                    setSaveState("idle");
                    if (failedSaveKind === "intent" && intent)
                      void persistIntent(intent);
                    if (failedSaveKind === "outline" && outline)
                      void persistOutline(outline, "edit", false);
                  }}
                >
                  重试保存
                </button>
              ) : null}
              <button
                className="primary-button"
                type="button"
                disabled={saveState === "saving" || Boolean(busyMessage)}
                onClick={() => void approve()}
              >
                {busyMessage ?? "批准当前大纲"}
              </button>
            </div>
          </div>

          <ol className="stepper" aria-label="创作步骤">
            <li className="done">
              <b>01</b>
              <span>主题与来源</span>
            </li>
            <li className="done">
              <b>02</b>
              <span>创作意图</span>
            </li>
            <li className="active">
              <b>03</b>
              <span>故事与大纲</span>
            </li>
            <li>
              <b>04</b>
              <span>生成确认</span>
            </li>
          </ol>

          {error ? (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button type="button" onClick={() => setError(null)}>
                关闭
              </button>
            </div>
          ) : null}

          {summary ? (
            <section
              className="approval-summary"
              aria-labelledby="summary-title"
            >
              <div>
                <p className="eyebrow">APPROVED INPUT BOUNDARY</p>
                <h2 id="summary-title">生成前确认摘要已固定</h2>
                <p>
                  Intent {summary.intentRevisionId.slice(-6)} · Outline{" "}
                  {summary.outlineRevisionId.slice(-6)} · 模板{" "}
                  {summary.templateVersionId.slice(-6)} · {summary.mode}
                </p>
                <small>
                  输入指纹 {summary.snapshotInputHash.slice(0, 16)}…
                </small>
              </div>
              <div>
                {draft.currentOutlineRevisionId !==
                summary.outlineRevisionId ? (
                  <p className="revision-warning">
                    你已继续编辑；批准摘要仍绑定旧版本，未被覆盖。
                  </p>
                ) : (
                  <p className="revision-ok">当前内容与已批准版本一致。</p>
                )}
                <button
                  className="primary-button"
                  type="button"
                  disabled={
                    draft.currentOutlineRevisionId !==
                      summary.outlineRevisionId ||
                    saveState === "saving" ||
                    Boolean(busyMessage)
                  }
                  onClick={() => void startGeneration()}
                >
                  {busyMessage ?? "开始真实生成"}
                </button>
                <small>
                  将创建可恢复的真实 Worker 任务，并锁定精确批准版本。
                </small>
              </div>
            </section>
          ) : null}

          <div className="workspace-body">
            <div className="editor-column">
              <section className="intent-card" aria-labelledby="intent-title">
                <div className="card-section-heading">
                  <div>
                    <p className="eyebrow">INTENT REVISION</p>
                    <h2 id="intent-title">确认创作意图</h2>
                  </div>
                  <span>rev · {intent.intentRevisionId.slice(-6)}</span>
                </div>
                <div className="intent-grid">
                  <label>
                    标题
                    <input
                      value={intent.title}
                      onChange={(event) =>
                        changeIntent("title", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    受众
                    <input
                      value={intent.audience}
                      onChange={(event) =>
                        changeIntent("audience", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    目标
                    <input
                      value={intent.goal}
                      onChange={(event) =>
                        changeIntent("goal", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    目标页数
                    <input
                      type="number"
                      min={4}
                      max={30}
                      value={intent.targetSlideCount}
                      onChange={(event) =>
                        changeIntent(
                          "targetSlideCount",
                          Number(event.target.value),
                        )
                      }
                    />
                  </label>
                  <label>
                    语言
                    <select
                      value={intent.language}
                      onChange={(event) =>
                        changeIntent(
                          "language",
                          event.target.value as IntentRevision["language"],
                        )
                      }
                    >
                      <option value="zh-CN">简体中文</option>
                      <option value="en-US">English</option>
                    </select>
                  </label>
                  <label>
                    内容深度
                    <select
                      value={intent.contentDepth}
                      onChange={(event) =>
                        changeIntent(
                          "contentDepth",
                          event.target.value as IntentRevision["contentDepth"],
                        )
                      }
                    >
                      <option value="conclusion_first">结论先行</option>
                      <option value="balanced">均衡展开</option>
                      <option value="research">研究深入</option>
                    </select>
                  </label>
                  <label>
                    视觉偏好
                    <select
                      value={intent.visualPreference}
                      onChange={(event) =>
                        changeIntent(
                          "visualPreference",
                          event.target
                            .value as IntentRevision["visualPreference"],
                        )
                      }
                    >
                      <option value="data_first">数据优先</option>
                      <option value="photo_illustration">图片插画</option>
                      <option value="minimal_visual">克制视觉</option>
                    </select>
                  </label>
                  <label className="notes-field">
                    补充说明
                    <textarea
                      rows={2}
                      value={intent.notes}
                      onChange={(event) =>
                        changeIntent("notes", event.target.value)
                      }
                    />
                  </label>
                </div>
                {intent.targetSlideCount !== outline.targetSlideCount ? (
                  <p className="field-warning">
                    页数已改变，请用“整纲优化”调整大纲；系统不会静默改写。
                  </p>
                ) : null}
              </section>

              <section className="story-card" aria-labelledby="story-title">
                <div className="card-section-heading">
                  <div>
                    <p className="eyebrow">STORYLINE</p>
                    <h2 id="story-title">一句话故事线</h2>
                  </div>
                  <span>{outline.slides.length} 页</span>
                </div>
                <textarea
                  aria-label="一句话故事线"
                  rows={2}
                  value={outline.storySummary}
                  onChange={(event) => {
                    outlineEditToken.current += 1;
                    setOutline({
                      ...outline,
                      storySummary: event.target.value,
                    });
                  }}
                />
              </section>

              <section
                className="outline-section"
                aria-labelledby="outline-title"
              >
                <div className="outline-section-head">
                  <div>
                    <p className="eyebrow">OUTLINE REVISION</p>
                    <h2 id="outline-title">逐页大纲</h2>
                  </div>
                  <div className="revision-controls">
                    <button
                      type="button"
                      onClick={undo}
                      disabled={
                        undoStack.length === 0 || saveState === "saving"
                      }
                    >
                      撤销
                    </button>
                    <button
                      type="button"
                      onClick={redo}
                      disabled={
                        redoStack.length === 0 || saveState === "saving"
                      }
                    >
                      恢复
                    </button>
                    <button
                      type="button"
                      onClick={addSlide}
                      disabled={
                        outline.slides.length >= 30 || saveState === "saving"
                      }
                    >
                      ＋ 新增页面
                    </button>
                  </div>
                </div>
                <div className="outline-list">
                  {outline.slides.map((slide, index) => (
                    <article
                      className="outline-card"
                      key={slide.outlineSlideId}
                    >
                      <span className="slide-number">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <div className="outline-copy">
                        <label>
                          <span className="sr-only">第 {index + 1} 页标题</span>
                          <input
                            value={slide.title}
                            onChange={(event) =>
                              mutateSlide(index, (current) => ({
                                ...current,
                                title: event.target.value,
                              }))
                            }
                          />
                        </label>
                        <label>
                          <span className="sr-only">
                            第 {index + 1} 页要点，每行一个
                          </span>
                          <textarea
                            rows={3}
                            value={slide.keyPoints.join("\n")}
                            onChange={(event) =>
                              mutateSlide(index, (current) => ({
                                ...current,
                                keyPoints: event.target.value.split("\n"),
                              }))
                            }
                          />
                        </label>
                        <small>
                          {slide.type} · ID {slide.outlineSlideId.slice(-6)}
                        </small>
                      </div>
                      <div
                        className="outline-actions"
                        aria-label={`第 ${index + 1} 页操作`}
                      >
                        <button
                          type="button"
                          title="上移"
                          aria-label={`上移第 ${index + 1} 页`}
                          disabled={index === 0 || saveState === "saving"}
                          onClick={() => moveSlide(index, -1)}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          title="下移"
                          aria-label={`下移第 ${index + 1} 页`}
                          disabled={
                            index === outline.slides.length - 1 ||
                            saveState === "saving"
                          }
                          onClick={() => moveSlide(index, 1)}
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          title="AI 改写"
                          aria-label={`AI 改写第 ${index + 1} 页`}
                          disabled={saveState === "saving"}
                          onClick={() =>
                            void runAiRevision(
                              "rewrite_slide",
                              slide.outlineSlideId,
                            )
                          }
                        >
                          AI
                        </button>
                        <button
                          type="button"
                          title="删除"
                          aria-label={`删除第 ${index + 1} 页`}
                          disabled={
                            outline.slides.length === 1 ||
                            saveState === "saving"
                          }
                          onClick={() => deleteSlide(index)}
                        >
                          ×
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            </div>

            <aside className="assistant-panel" aria-label="AI 大纲助手">
              <details
                className="assistant-drawer"
                open={assistantOpen}
                onToggle={(event) => setAssistantOpen(event.currentTarget.open)}
              >
                <summary className="assistant-drawer-summary">
                  <span>AI 大纲助手</span>
                  <small>展开可操作抽屉</small>
                </summary>
                <div className="assistant-content">
                  <p className="eyebrow">AI REVISION ASSISTANT</p>
                  <h2 id="assistant-title">用一句话调整结构</h2>
                  <p>{assistantMessage}</p>
                  <label htmlFor="assistant-input">优化要求</label>
                  <textarea
                    id="assistant-input"
                    rows={4}
                    value={assistantInput}
                    onChange={(event) => setAssistantInput(event.target.value)}
                    placeholder="例如：让结论更锋利，并把行动计划提前"
                  />
                  <button
                    className="primary-button"
                    type="button"
                    disabled={saveState === "saving"}
                    onClick={() => void runAiRevision("optimize")}
                  >
                    整纲优化并创建版本
                  </button>
                  <div className="assistant-facts">
                    <span>Provider：deterministic fake</span>
                    <span>图片调用：0</span>
                    <span>当前 rev：{outline.outlineRevisionId.slice(-6)}</span>
                  </div>
                </div>
              </details>
            </aside>
          </div>
        </div>
      ) : null}

      {error && view === "home" ? (
        <div className="home-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>
            关闭
          </button>
        </div>
      ) : null}

      <AccessibilityAudit auditKey={view} />

      <dialog
        ref={historyDialogRef}
        className="history-dialog"
        aria-labelledby="history-title"
        onClose={() => {
          setHistoryOpen(false);
          historyButtonRef.current?.focus();
        }}
      >
        <div className="dialog-heading">
          <div>
            <p className="eyebrow">PERSISTED HISTORY</p>
            <h2 id="history-title">历史创作</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="关闭历史创作"
            onClick={() => setHistoryOpen(false)}
          >
            ×
          </button>
        </div>
        {history.length ? (
          <div className="history-list">
            {history.map((item) => (
              <button
                type="button"
                className="history-item"
                key={item.draftId}
                onClick={() => openHistoryItem(item)}
              >
                <span>
                  <strong>{item.title}</strong>
                  <small>
                    {new Date(item.updatedAt).toLocaleString("zh-CN")}
                  </small>
                </span>
                <span>
                  {item.historyState === "result"
                    ? `结果 · ${item.presentationStatus}`
                    : item.historyState === "monitor"
                      ? `任务 · ${item.jobStatus}`
                      : `草稿 · ${item.status}`}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="empty-state">
            还没有草稿。输入主题，创建第一份可恢复的工作台。
          </p>
        )}
      </dialog>
    </main>
  );
}
