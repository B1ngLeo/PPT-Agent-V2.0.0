"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import { SourceUploader, type SourceState } from "./source-uploader";

const API_BASE = "/api";
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
          if (!cancelled)
            setResult((current) => ({ ...current, state: "failed" }));
        });
    }, 1200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [auditKey, enabled]);

  if (!enabled) return null;
  return (
    <output
      className="a11y-audit-output"
      aria-label="axe accessibility audit results"
    >
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
  maxImagesPerDeck: number;
  monthlyImageLimit: number;
  monthlyImageCostLimitMicrounits: number;
  maxConcurrentJobs: number;
  allowedModes: string[];
};

type Usage = {
  metrics: {
    slides: number;
    images: number;
    modelTokens: number;
    modelCostMicrounits?: number;
    imageCostMicrounits?: number;
  };
  reservedSlides: number;
  reservedImages: number;
  reservedImageCostMicrounits: number;
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

const TEMPLATE_CATEGORY_LABELS: Record<string, string> = {
  business: "总结汇报",
  strategy: "商业计划",
  research: "教育培训",
  marketing: "营销推广",
  corporate: "企业宣讲",
  hr: "人资行政",
  healthcare: "医疗健康",
};

function templateCategoryLabel(category: string): string {
  return TEMPLATE_CATEGORY_LABELS[category] ?? category;
}

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

type VisualStyleOption = {
  id: string;
  name: string;
  rationale: string;
  recommended: boolean;
  colors: {
    theme: string;
    background: string;
    text: string;
    secondaryText: string;
  };
  typography: {
    headingFont: string;
    bodyFont: string;
  };
};

type VisualStyleProposal = {
  options: VisualStyleOption[];
};

type PlanningJob = {
  planningJobId: string;
  draftId: string;
  operation: "intent_infer" | "outline_generate" | "visual_style_generate";
  status: "queued" | "running" | "retrying" | "succeeded" | "failed";
  attempt: number;
  maxAttempts: number;
  terminal: boolean;
  retryable: boolean;
  errorCode: string | null;
  resultRevisionId: string | null;
  provider: string | null;
  model: string | null;
  result?: IntentRevision | OutlineRevision | VisualStyleProposal | null;
};

type GenerationImageScope = "none" | "cover_only" | "selective";
type VisualReviewLevel = "off" | "standard";

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
  planningProvider: {
    provider: string;
    model: string;
    purpose: string;
  } | null;
  planningJob: PlanningJob | null;
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
  contentMode: "source-grounded" | "limited-general-draft" | null;
  engineProfile:
    "default-agentic" | "deterministic-template" | "quick-engineering" | null;
  authoringMode: "agent-authoring" | "deterministic-template" | null;
  authoringDisclosure:
    "agent-authored-editable-draft" | "template-limited-editable-draft" | null;
  suggestedFilename: string | null;
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
  engineProfile:
    "default-agentic" | "deterministic-template" | "quick-engineering" | null;
  authoringMode: "agent-authoring" | "deterministic-template";
  authoringDisclosure:
    "agent-authored-editable-draft" | "template-limited-editable-draft";
  fallbackReason: string | null;
  visualReview: {
    required?: boolean;
    level?: VisualReviewLevel;
    policyVersion?: string;
    maxRounds?: number;
    authoringModel?: string;
    visualReviewModel?: string;
  };
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
  workflow: {
    workflowRunId: string;
    status: string;
    stage: string;
    attempt: number;
    checkpointSetId: string | null;
    errorCode: string | null;
    recoveryAction: string | null;
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

function planningIdempotencyKey(
  stage: "intent" | "outline",
  draftId: string,
  revisionId: string | null = null,
) {
  return `web-${stage}-${draftId}-${revisionId ?? "initial"}-v1`;
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

function visualPreferenceLabel(
  preference: IntentRevision["visualPreference"],
): string {
  if (preference === "photo_illustration") return "图片插画";
  if (preference === "minimal_visual") return "克制视觉";
  return "数据优先";
}

function planningProgressLabel(job: PlanningJob): string {
  const operation =
    job.operation === "intent_infer"
      ? "识别创作意图"
      : job.operation === "outline_generate"
        ? "生成可编辑大纲"
        : "生成三套视觉风格";
  if (job.status === "retrying")
    return `${operation}暂时失败，正在自动重试（${job.attempt}/${job.maxAttempts}）…`;
  if (job.status === "queued") return `${operation}已排队…`;
  return `${operation}中（${job.attempt}/${job.maxAttempts}）…`;
}

function visualStyleProposal(
  value: PlanningJob["result"],
): VisualStyleProposal | null {
  if (!value || !("options" in value) || !Array.isArray(value.options)) {
    return null;
  }
  return value.options.length === 3 ? (value as VisualStyleProposal) : null;
}

async function waitForPlanningJob(
  initial: PlanningJob,
  onProgress: (job: PlanningJob) => void,
): Promise<PlanningJob> {
  let current = initial;
  const deadline = Date.now() + 30 * 60 * 1000;
  while (!current.terminal) {
    if (Date.now() >= deadline)
      throw new Error("规划任务仍在后台运行，请稍后从历史创作恢复。");
    onProgress(current);
    await new Promise<void>((resolve) => window.setTimeout(resolve, 1500));
    current = (
      await api<PlanningJob>(`/v1/planning-jobs/${current.planningJobId}`)
    ).data;
  }
  onProgress(current);
  if (current.status === "failed")
    throw new ApiError(
      503,
      current.errorCode ?? "planning_failed",
      current.retryable
        ? "AI 规划暂时不可用，后台重试已用尽，可稍后再次发起。"
        : "AI 规划失败，现有草稿保持不变。",
    );
  return current;
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

function generationStageStepIndex(stage: GenerationJob["stage"]): number {
  if (stage === "deck_planning") return 0;
  if (stage === "slide_generation") return 1;
  if (stage === "deck_qa") return 2;
  return 3;
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

function manualInterventionKind(
  job: GenerationJob,
): "image" | "visual" | "generic" {
  if (job.workflow?.errorCode === "IMAGE_RESOURCE_NEEDS_MANUAL") return "image";
  if (job.workflow?.errorCode === "VISUAL_REVIEW_BLOCKING") return "visual";
  return "generic";
}

function generatedPageLabel(job: GenerationJob): string {
  return job.status === "succeeded" || job.status === "partially_succeeded"
    ? "页就绪"
    : "页已生成";
}

function generationSlideStatusLabel(slide: GenerationJobSlide): string {
  if (slide.status === "ready") return "已就绪";
  if (slide.status === "running" && slide.renderSha256) return "已生成";
  if (slide.status === "running") return "生成中";
  if (slide.status === "retrying") return "重试中";
  if (slide.status === "pending") return "等待中";
  if (slide.status === "failed") return "失败";
  return "已取消";
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
  const [activeTemplateCategory, setActiveTemplateCategory] =
    useState("精品推荐");
  const [draft, setDraft] = useState<DraftSnapshot | null>(null);
  const [intent, setIntent] = useState<IntentRevision | null>(null);
  const [outline, setOutline] = useState<OutlineRevision | null>(null);
  const [summary, setSummary] = useState<GenerationSummary | null>(null);
  const [visualStyleOptions, setVisualStyleOptions] = useState<
    VisualStyleOption[]
  >([]);
  const [selectedVisualStyleId, setSelectedVisualStyleId] = useState<
    string | null
  >(null);
  const [visualStylePlanningJobId, setVisualStylePlanningJobId] = useState<
    string | null
  >(null);
  const [continueLimitedDraft, setContinueLimitedDraft] = useState(false);
  const [generationImageScope, setGenerationImageScope] =
    useState<GenerationImageScope>("none");
  const [visualReviewLevel, setVisualReviewLevel] =
    useState<VisualReviewLevel>("off");
  const [selectedImageOutlineIds, setSelectedImageOutlineIds] = useState<
    string[]
  >([]);
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
    useState("我会重新优化并生成大纲");
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

  const loadPresentation = useCallback(
    async (presentationId: string, push = false, showLoading = false) => {
      if (showLoading) setView("loading");
      try {
        const response = await api<Presentation>(
          `/v1/presentations/${presentationId}`,
        );
        setPresentation(response.data);
        await loadGenerationJob(response.data.generationJobId, false, false);
        const resultUrl = `/?draft=${response.data.draftId}&job=${response.data.generationJobId}`;
        if (push) window.history.pushState({}, "", resultUrl);
        else window.history.replaceState({}, "", resultUrl);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "生成结果恢复失败");
        if (showLoading) setView("home");
      }
    },
    [loadGenerationJob],
  );

  const applyDraftSnapshot = useCallback(async (next: DraftSnapshot) => {
    setDraft(next);
    setGenerationJob(null);
    setStreamState("closed");
    lastEventId.current = "";
    setIntent(next.currentIntent);
    setOutline(next.currentOutline);
    setSummary(next.generationSummary);
    const restoredStyles =
      next.planningJob?.operation === "visual_style_generate"
        ? visualStyleProposal(next.planningJob.result)
        : null;
    setVisualStyleOptions(restoredStyles?.options ?? []);
    setSelectedVisualStyleId(
      restoredStyles?.options.find((option) => option.recommended)?.id ??
        restoredStyles?.options[0]?.id ??
        null,
    );
    setVisualStylePlanningJobId(
      restoredStyles ? (next.planningJob?.planningJobId ?? null) : null,
    );
    lastSavedIntent.current = next.currentIntent
      ? JSON.stringify(intentPayload(next.currentIntent))
      : "";
    lastSavedOutline.current = next.currentOutline
      ? JSON.stringify(outlinePayload(next.currentOutline))
      : "";
    serverOutline.current = next.currentOutline;
    if (next.currentOutline) {
      const revisions = await api<{ items: OutlineRevision[] }>(
        `/v1/drafts/${next.draftId}/outline-revisions`,
      );
      setUndoStack(revisions.data.items.slice(0, -1));
    } else {
      setUndoStack([]);
    }
    setRedoStack([]);
    setSaveState("saved");
    setView("workspace");
  }, []);

  const openDraft = useCallback(
    async (draftId: string, push = true) => {
      setView("loading");
      setError(null);
      try {
        const response = await api<DraftSnapshot>(`/v1/drafts/${draftId}`);
        await applyDraftSnapshot(response.data);
        if (push) window.history.pushState({}, "", `/?draft=${draftId}`);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "草稿恢复失败");
        setView("home");
      }
    },
    [applyDraftSnapshot],
  );

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

  const continuePlanning = useCallback(
    async (draftId: string) => {
      setError(null);
      try {
        setBusyMessage("正在核对已保存的规划状态…");
        let current = (await api<DraftSnapshot>(`/v1/drafts/${draftId}`)).data;
        if (current.planningJob && !current.planningJob.terminal) {
          await waitForPlanningJob(current.planningJob, (progress) =>
            setBusyMessage(planningProgressLabel(progress)),
          );
          current = (await api<DraftSnapshot>(`/v1/drafts/${draftId}`)).data;
        }
        if (!current.currentIntent) {
          const active =
            current.planningJob?.operation === "intent_infer" &&
            !current.planningJob.terminal
              ? current.planningJob
              : null;
          const job =
            active ??
            (
              await api<PlanningJob>(`/v1/drafts/${draftId}/intent:infer`, {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "Idempotency-Key":
                    current.planningJob?.operation === "intent_infer" &&
                    current.planningJob.status === "failed"
                      ? crypto.randomUUID()
                      : planningIdempotencyKey("intent", draftId),
                },
                body: mutation({ language: "zh-CN" }),
              })
            ).data;
          await waitForPlanningJob(job, (progress) =>
            setBusyMessage(planningProgressLabel(progress)),
          );
          current = (await api<DraftSnapshot>(`/v1/drafts/${draftId}`)).data;
        }
        if (!current.currentOutline) {
          const active =
            current.planningJob?.operation === "outline_generate" &&
            !current.planningJob.terminal
              ? current.planningJob
              : null;
          const job =
            active ??
            (
              await api<PlanningJob>(`/v1/drafts/${draftId}/outline:generate`, {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "Idempotency-Key":
                    current.planningJob?.operation === "outline_generate" &&
                    current.planningJob.status === "failed"
                      ? crypto.randomUUID()
                      : planningIdempotencyKey(
                          "outline",
                          draftId,
                          current.currentIntentRevisionId,
                        ),
                },
                body: mutation({ action: "generate", instruction: "" }),
              })
            ).data;
          await waitForPlanningJob(job, (progress) =>
            setBusyMessage(planningProgressLabel(progress)),
          );
        }
        await refreshHistory();
        await openDraft(draftId, false);
      } catch (reason) {
        try {
          const current = (await api<DraftSnapshot>(`/v1/drafts/${draftId}`))
            .data;
          await applyDraftSnapshot(current);
          setError(
            current.currentOutline
              ? "已从持久化规划任务恢复完整大纲。"
              : current.planningJob && !current.planningJob.terminal
                ? "规划任务仍在后台运行，可刷新或稍后从历史创作恢复。"
                : current.currentIntent
                  ? "创作意图已保存；大纲任务未完成，可继续生成。"
                  : reason instanceof Error
                    ? reason.message
                    : "规划任务暂时不可用。",
          );
        } catch {
          setError(
            reason instanceof Error ? reason.message : "规划流程暂时不可用",
          );
          setView("home");
        }
      } finally {
        setBusyMessage(null);
      }
    },
    [applyDraftSnapshot, openDraft, refreshHistory],
  );

  useEffect(() => {
    const job = draft?.planningJob;
    if (view !== "workspace" || !draft || !job || job.terminal || busyMessage)
      return;
    void continuePlanning(draft.draftId);
  }, [busyMessage, continuePlanning, draft, view]);

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
      await continuePlanning(created.data.draftId);
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
      const response = await api<PlanningJob>(
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
      const completed = await waitForPlanningJob(response.data, (progress) =>
        setAssistantMessage(planningProgressLabel(progress)),
      );
      const revised = completed.result;
      if (!revised || !("outlineRevisionId" in revised))
        throw new Error("规划任务完成但未返回大纲版本。");
      if (serverOutline.current)
        setUndoStack((stack) => [...stack, serverOutline.current!]);
      setRedoStack([]);
      serverOutline.current = revised;
      lastSavedOutline.current = JSON.stringify(outlinePayload(revised));
      setOutline(revised);
      setDraft((current) =>
        current
          ? {
              ...current,
              currentOutlineRevisionId: revised.outlineRevisionId,
              planningJob: completed,
              planningProvider:
                completed.provider && completed.model
                  ? {
                      provider: completed.provider,
                      model: completed.model,
                      purpose: "outline_generate",
                    }
                  : current.planningProvider,
            }
          : current,
      );
      setAssistantInput("");
      setAssistantMessage(
        `已创建 ${revised.outlineRevisionId.slice(-6)} 版本，可撤销。`,
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

  const requestVisualStyles = async (
    draftId: string,
    approvalId: string,
  ): Promise<void> => {
    setVisualStyleOptions([]);
    setSelectedVisualStyleId(null);
    setVisualStylePlanningJobId(null);
    const queued = await api<PlanningJob>(
      `/v1/drafts/${draftId}/visual-styles:generate`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: mutation({}, approvalId),
      },
    );
    const completed = await waitForPlanningJob(queued.data, (progress) =>
      setBusyMessage(planningProgressLabel(progress)),
    );
    const proposal = visualStyleProposal(completed.result);
    if (!proposal) {
      throw new Error("视觉风格生成结果不完整，请重新生成");
    }
    setVisualStyleOptions(proposal.options);
    setSelectedVisualStyleId(
      proposal.options.find((option) => option.recommended)?.id ??
        proposal.options[0].id,
    );
    setVisualStylePlanningJobId(completed.planningJobId);
  };

  const retryVisualStyles = async () => {
    if (!draft || !summary) return;
    setBusyMessage("正在生成三套视觉风格…");
    setError(null);
    try {
      await requestVisualStyles(draft.draftId, summary.approvalId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "视觉风格生成失败");
    } finally {
      setBusyMessage(null);
    }
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
      setContinueLimitedDraft(false);
      setVisualReviewLevel("off");
      setDraft((current) =>
        current
          ? {
              ...current,
              approvedOutlineRevisionId: response.data.outlineRevisionId,
              status: "approved",
            }
          : current,
      );
      setBusyMessage("正在生成三套视觉风格…");
      await requestVisualStyles(draft.draftId, response.data.approvalId);
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
      !visualStylePlanningJobId ||
      !selectedVisualStyleId ||
      draft.currentOutlineRevisionId !== summary.outlineRevisionId ||
      saveState === "saving"
    )
      return;
    setBusyMessage("正在创建真实生成任务…");
    setError(null);
    try {
      const imageNotes =
        generationImageScope === "cover_only"
          ? { cover: "封面使用非证据型编辑插画，并为原生标题保留安静区域" }
          : generationImageScope === "selective"
            ? Object.fromEntries(
                (outline?.slides ?? [])
                  .filter((slide) =>
                    selectedImageOutlineIds.includes(slide.outlineSlideId),
                  )
                  .map((slide) => [
                    slide.outlineSlideId,
                    `${slide.title} 的非证据型编辑插画，不承载数字、参数或事实结论`,
                  ]),
              )
            : {};
      const response = await api<GenerationJob>(
        `/v1/drafts/${draft.draftId}/generation-jobs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation({
            continueLimitedDraft:
              summary.sourceSummary.sourceId === null && continueLimitedDraft,
            authorizeStrategistDesignLock: true,
            visualReviewLevel,
            visualStylePlanningJobId,
            visualStyleOptionId: selectedVisualStyleId,
            imagePolicy:
              generationImageScope === "none"
                ? { scope: "none", usage: ["none"], notes: {} }
                : {
                    scope: generationImageScope,
                    usage: ["ai"],
                    notes: imageNotes,
                    aiPath: "auto",
                    aiPathChain: ["api", "manual"],
                  },
          }),
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
    if (!generationJob?.presentation || busyMessage) return;
    setBusyMessage("正在按当前精确版本编译并执行包检…");
    setError(null);
    try {
      const presentationResponse = await api<Presentation>(
        `/v1/presentations/${generationJob.presentation.presentationId}`,
      );
      const exportTarget = presentationResponse.data;
      const exportFilename =
        exportTarget.currentRevision.suggestedFilename ??
        `${exportTarget.title}.pptx`;
      const queued = await api<PresentationExport>(
        `/v1/presentations/${exportTarget.presentationId}/exports`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: mutation(
            {
              presentationRevisionId: exportTarget.currentRevisionId,
              filename: exportFilename,
            },
            exportTarget.currentRevisionId,
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
        exportFilename,
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

  const homeTemplateCategories = [
    "精品推荐",
    ...Array.from(
      new Set(
        templates.map((template) => templateCategoryLabel(template.category)),
      ),
    ),
  ];
  const visibleHomeTemplates =
    activeTemplateCategory === "精品推荐"
      ? templates.slice(0, 8)
      : templates
          .filter(
            (template) =>
              templateCategoryLabel(template.category) ===
              activeTemplateCategory,
          )
          .slice(0, 8);

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
          <span className="brand-wordmark">
            即刻<strong>AI-PPT</strong>
          </span>
        </button>
        <div className="header-actions">
          {view !== "home" && entitlement ? (
            <span className="quota-chip">
              本月 {usage?.metrics.slides ?? 0} /{" "}
              {entitlement.monthlySlideLimit} 页 · {usage?.metrics.images ?? 0}{" "}
              / {entitlement.monthlyImageLimit} 图
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
          {view === "home" ? (
            <span className="account-avatar" aria-label="当前账户 YL">
              YL
            </span>
          ) : null}
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
            </div>
          </div>

          <section
            className="ai-draft-banner"
            aria-labelledby="draft-banner-title"
          >
            <div>
              <p className="eyebrow">
                {presentation.currentRevision.authoringMode ===
                "deterministic-template"
                  ? "DETERMINISTIC TEMPLATE · LIMITED DRAFT"
                  : "AGENT-AUTHORED · EDITABLE DRAFT"}
              </p>
              <h1 id="draft-banner-title">
                {presentation.currentRevision.authoringMode ===
                "deterministic-template"
                  ? "模板化受限初稿"
                  : "Agent 创作的 AI 可编辑草稿"}
              </h1>
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

          {presentation.currentRevision.authoringMode ===
          "deterministic-template" ? (
            <section
              className="partial-warning limited-draft-warning"
              aria-labelledby="template-limited-draft-title"
            >
              <div>
                <p className="eyebrow">FALLBACK DISCLOSURE</p>
                <h2 id="template-limited-draft-title">这是模板化受限初稿</h2>
                <p>
                  本版本由确定性模板降级链路生成，不计入 Agent
                  创作成功率；导出文件名也会保留“模板化受限初稿”标记。
                </p>
              </div>
            </section>
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

          {presentation.currentRevision.contentMode ===
          "limited-general-draft" ? (
            <section
              className="partial-warning limited-draft-warning"
              aria-labelledby="limited-draft-title"
            >
              <div>
                <p className="eyebrow">LIMITED GENERAL DRAFT</p>
                <h2 id="limited-draft-title">这是无可信来源的受限通用初稿</h2>
                <p>
                  当前内容未完成外部事实核验，也没有执行网页研究；请补充已批准来源后再将其用于事实解读。
                </p>
              </div>
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
            <div className="monitor-top-actions">
              {generationJob.presentation ? (
                <button
                  className="primary-button"
                  type="button"
                  disabled={
                    generationJob.presentation.status !== "ready" ||
                    Boolean(busyMessage)
                  }
                  onClick={() => void exportPresentation()}
                >
                  {busyMessage ?? "导出 PPTX"}
                </button>
              ) : (
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
              )}
            </div>
          </div>

          <ol className="stepper" aria-label="生成步骤">
            {[
              ["01", "生成计划"],
              ["02", "逐页生成"],
              ["03", "整稿检查"],
              ["04", "编译与发布"],
            ].map(([number, label], index) => {
              const currentIndex = generationStageStepIndex(
                generationJob.stage,
              );
              const completedSuccessfully = [
                "succeeded",
                "partially_succeeded",
              ].includes(generationJob.status);
              const complete = completedSuccessfully || index < currentIndex;
              const active = !completedSuccessfully && index === currentIndex;
              return (
                <li
                  key={number}
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
              <p className="eyebrow">
                {generationJob.authoringMode === "deterministic-template"
                  ? "DETERMINISTIC TEMPLATE · LIMITED DRAFT"
                  : "MAIN PRESENTATION AGENT · NATIVE MODE"}
              </p>
              <h1 id="monitor-title">
                {generationJob.workflow?.status === "needs_manual"
                  ? manualInterventionKind(generationJob) === "image"
                    ? "等待人工补充图片"
                    : manualInterventionKind(generationJob) === "visual"
                      ? "视觉复核需要人工处理"
                      : "任务需要人工处理"
                  : generationJob.authoringMode === "deterministic-template"
                    ? `模板化受限初稿 · ${generationStatusLabel(generationJob.status)}`
                    : generationStatusLabel(generationJob.status)}
              </h1>
              <p aria-live="polite">
                {generationJob.workflow?.status === "needs_manual"
                  ? manualInterventionKind(generationJob) === "image"
                    ? "必需图片尚未解决；任务已在导出前安全停止，没有静默省略资源。"
                    : manualInterventionKind(generationJob) === "visual"
                      ? "页面已生成，但整稿视觉复核仍有阻断项；任务已在导出前安全停止。"
                      : "工作流需要人工处理；任务已在导出前安全停止。"
                  : generationJob.authoringMode === "deterministic-template"
                    ? "Agent 创作链路未用于本任务；当前结果是显式标识的模板化受限初稿。"
                    : generationJob.terminal
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
                  {generationJob.progress.total}{" "}
                  {generatedPageLabel(generationJob)}
                </span>
                <span>任务尝试 {generationJob.attempt}</span>
              </div>
              <progress
                max={generationJob.progress.total}
                value={generationJob.progress.completed}
                aria-label="页面生成进度"
              />
            </div>
          </section>

          {generationJob.authoringMode === "deterministic-template" ? (
            <section
              className="partial-warning limited-draft-warning"
              aria-labelledby="monitor-template-limited-title"
            >
              <div>
                <p className="eyebrow">FALLBACK DISCLOSURE</p>
                <h2 id="monitor-template-limited-title">
                  模板化降级已显式启用
                </h2>
                <p>
                  原因：
                  {generationJob.fallbackReason ??
                    "旧快照未包含 Agent 创作策略"}
                  。该结果不会写入 Agent 作者证据，也不会被计入 Agent 成功率。
                </p>
              </div>
            </section>
          ) : null}

          {generationJob.workflow?.status === "needs_manual" ? (
            <section
              className="partial-warning"
              aria-labelledby="needs-manual-title"
            >
              <div>
                <p className="eyebrow">NEEDS MANUAL · NO SILENT OMISSION</p>
                <h2 id="needs-manual-title">
                  {manualInterventionKind(generationJob) === "image"
                    ? "需要人工补充并验证图片资源"
                    : manualInterventionKind(generationJob) === "visual"
                      ? "需要人工检查视觉复核阻断项"
                      : "需要人工处理工作流阻断项"}
                </h2>
                <p>
                  {manualInterventionKind(generationJob) === "image"
                    ? "请按已保存的图片提示与资源计划补充文件，完成图片验证后从当前检查点恢复。"
                    : manualInterventionKind(generationJob) === "visual"
                      ? "请检查页面渲染和视觉复核报告；修复阻断项后从视觉复核检查点恢复。"
                      : (generationJob.workflow.recoveryAction ??
                        "请按已保存的资源计划处理后，从当前检查点恢复。")}
                </p>
                <small>
                  阶段{" "}
                  {generationJob.workflow.stage === "image_resources"
                    ? "图片资源"
                    : generationJob.workflow.stage}{" "}
                  · 错误码{" "}
                  {generationJob.workflow.errorCode ?? "workflow_needs_manual"}
                </small>
              </div>
            </section>
          ) : null}

          <section
            className="monitor-slides"
            aria-labelledby="monitor-slides-title"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">STABLE SLIDE IDS</p>
                <h2 id="monitor-slides-title">逐页状态</h2>
              </div>
            </div>
            <div className="generation-slide-grid">
              {generationJob.slides.map((slide) => (
                <article
                  className={`generation-slide status-${slide.status}`}
                  key={slide.slideId}
                >
                  <div className="generation-slide-head">
                    <span>{String(slide.position).padStart(2, "0")}</span>
                    <strong>{generationSlideStatusLabel(slide)}</strong>
                  </div>
                  <h3>{slide.title}</h3>
                  {slide.status !== "ready" ? (
                    <p>
                      {slide.status === "running" || slide.status === "retrying"
                        ? slide.renderSha256
                          ? "已生成，等待整稿复核"
                          : slide.stage === "content_generation"
                            ? "生成内容"
                            : slide.stage === "rendering"
                              ? "渲染页面"
                              : "逐页质量检查"
                        : slide.status === "failed"
                          ? "生成失败"
                          : "等待生成"}
                    </p>
                  ) : null}
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
        </div>
      ) : view === "home" ? (
        <div className="home-content">
          <section className="homepage-hero" aria-labelledby="home-title">
            <h1 id="home-title">
              让想法<span>即刻成片</span>
            </h1>
            <section
              className="homepage-composer"
              aria-labelledby="creation-title"
            >
              <h2 id="creation-title" className="sr-only">
                AI 创作输入
              </h2>
              <label className="sr-only" htmlFor="topic">
                主题或目标
              </label>
              <textarea
                id="topic"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="帮我生成一份 PPT，例如：面向管理层的 2027 年产品增长策略……"
                rows={5}
                maxLength={1000}
              />
              <div className="composer-toolbar">
                <div className="composer-tools">
                  <SourceUploader
                    variant="compact"
                    onSourceReady={onSourceReady}
                  />
                  <div className="mode-switch" aria-label="创作模式">
                    <button className="active" type="button">
                      自由设计
                    </button>
                    <button type="button" disabled title="即将开放">
                      模板复用
                    </button>
                  </div>
                </div>
                <button
                  className="primary-button homepage-generate"
                  type="button"
                  disabled={
                    (!topic.trim() && !source?.sourceId) || Boolean(busyMessage)
                  }
                  onClick={() => void createWorkspace()}
                >
                  {busyMessage ?? "立即生成"}
                </button>
              </div>
            </section>
          </section>

          <section
            className="homepage-templates"
            aria-labelledby="template-title"
          >
            <div className="homepage-template-heading">
              <h2 id="template-title">选择模板创作</h2>
              <button
                className="upload-template-button"
                type="button"
                onClick={() => setError("自定义模板上传将在后续版本开放。")}
              >
                <span aria-hidden="true">＋</span>
                上传模板
              </button>
            </div>
            <div
              className="template-category-row"
              role="tablist"
              aria-label="模板分类"
            >
              {homeTemplateCategories.map((category) => (
                <button
                  className={
                    activeTemplateCategory === category ? "active" : ""
                  }
                  type="button"
                  role="tab"
                  aria-selected={activeTemplateCategory === category}
                  key={category}
                  onClick={() => setActiveTemplateCategory(category)}
                >
                  {category}
                </button>
              ))}
            </div>
            <div className="template-grid">
              {visibleHomeTemplates.map((template) => {
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
      ) : view === "workspace" && draft && (!intent || !outline) ? (
        <div className="workspace planning-recovery">
          <div className="workspace-topbar">
            <button className="quiet-button" type="button" onClick={returnHome}>
              ← 返回首页
            </button>
            <div>
              <strong>{draft.title}</strong>
              <span className="save-state" aria-live="polite">
                规划可恢复
              </span>
            </div>
            <div className="workspace-actions">
              <button
                className="primary-button"
                type="button"
                disabled={Boolean(busyMessage)}
                onClick={() => void continuePlanning(draft.draftId)}
              >
                {busyMessage ??
                  (intent ? "继续生成可编辑大纲" : "核对并继续意图识别")}
              </button>
            </div>
          </div>

          <ol className="stepper" aria-label="创作步骤">
            <li className="done">
              <b>01</b>
              <span>主题与来源</span>
            </li>
            <li className={intent ? "done" : "active"}>
              <b>02</b>
              <span>创作意图</span>
            </li>
            <li className={intent ? "active" : ""}>
              <b>03</b>
              <span>逐页大纲</span>
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

          <section className="planning-recovery-card" aria-live="polite">
            <p className="eyebrow">RECOVERABLE PLANNING</p>
            <h1>{intent ? "创作意图已保存" : "正在建立创作意图"}</h1>
            <p>
              {intent
                ? "服务端已经保存意图版本，可以从这里继续生成逐页大纲，不需要重新创建草稿。"
                : "草稿已经安全保存。系统会先核对服务端状态，再继续意图识别，避免重复调用。"}
            </p>
            {intent ? (
              <dl>
                <div>
                  <dt>制作目标</dt>
                  <dd>{intent.goal}</dd>
                </div>
                <div>
                  <dt>目标受众</dt>
                  <dd>{intent.audience}</dd>
                </div>
                <div>
                  <dt>页数规模</dt>
                  <dd>{intent.targetSlideCount} 页</dd>
                </div>
                <div>
                  <dt>配图偏好</dt>
                  <dd>{visualPreferenceLabel(intent.visualPreference)}</dd>
                </div>
                <div className="planning-notes">
                  <dt>补充说明</dt>
                  <dd>{intent.notes || "无"}</dd>
                </div>
              </dl>
            ) : null}
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
            <li className={summary ? "done" : "active"}>
              <b>03</b>
              <span>逐页大纲</span>
            </li>
            <li className={summary ? "active" : undefined}>
              <b>04</b>
              <span>视觉风格</span>
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
              <div className="approval-summary-heading">
                <div>
                  <p className="eyebrow">VISUAL STYLE CONFIRMATION</p>
                  <h2 id="summary-title">视觉风格确认</h2>
                </div>
                <button
                  className="quiet-button"
                  type="button"
                  disabled={Boolean(busyMessage)}
                  onClick={() => void retryVisualStyles()}
                >
                  重新生成
                </button>
              </div>
              <p className="visual-style-intro">
                AI
                已根据创作意图和批准大纲生成三套方案。选择一套后，色彩与字体会随生成快照一并锁定。
              </p>
              {visualStyleOptions.length === 3 ? (
                <div
                  className="visual-style-grid"
                  role="radiogroup"
                  aria-label="视觉风格方案"
                >
                  {visualStyleOptions.map((option, index) => {
                    const selected = option.id === selectedVisualStyleId;
                    const swatches = [
                      ["主题", option.colors.theme],
                      ["背景", option.colors.background],
                      ["文字", option.colors.text],
                      ["次要文字", option.colors.secondaryText],
                    ];
                    return (
                      <button
                        key={option.id}
                        className={`visual-style-card${selected ? " selected" : ""}`}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => setSelectedVisualStyleId(option.id)}
                      >
                        <span className="visual-style-card-heading">
                          <span className="visual-style-index">
                            {String.fromCharCode(65 + index)}
                          </span>
                          <strong>{option.name}</strong>
                          {option.recommended ? <em>推荐</em> : null}
                        </span>
                        <span className="visual-style-rationale">
                          {option.rationale}
                        </span>
                        <span className="visual-style-swatches">
                          {swatches.map(([label, color]) => (
                            <span key={label} title={`${label} ${color}`}>
                              <i style={{ backgroundColor: color }} />
                              <small>{label}</small>
                              <code>{color}</code>
                            </span>
                          ))}
                        </span>
                        <span className="visual-style-fonts">
                          <span>标题 {option.typography.headingFont}</span>
                          <span>正文 {option.typography.bodyFont}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="visual-style-empty" aria-live="polite">
                  <span>{busyMessage ?? "尚未生成视觉风格方案"}</span>
                  {!busyMessage ? (
                    <button
                      type="button"
                      onClick={() => void retryVisualStyles()}
                    >
                      生成三套方案
                    </button>
                  ) : null}
                </div>
              )}
              {draft.currentOutlineRevisionId !== summary.outlineRevisionId ||
              summary.sourceSummary.sourceId === null ? (
                <div className="approval-summary-status">
                  {draft.currentOutlineRevisionId !==
                  summary.outlineRevisionId ? (
                    <p className="revision-warning">
                      你已继续编辑；批准摘要仍绑定旧版本，未被覆盖。
                    </p>
                  ) : null}
                  {summary.sourceSummary.sourceId === null ? (
                    <label className="limited-draft-choice">
                      <input
                        type="checkbox"
                        checked={continueLimitedDraft}
                        onChange={(event) =>
                          setContinueLimitedDraft(event.target.checked)
                        }
                      />
                      <span>
                        当前没有已批准来源。我选择继续“受限通用初稿”，其中不会把事实解读伪装成已核实结论。
                      </span>
                    </label>
                  ) : null}
                </div>
              ) : null}
              <div className="generation-policy-grid">
                <fieldset className="image-policy-choice">
                  <legend>图片策略</legend>
                  <label>
                    <span>页面范围</span>
                    <select
                      value={generationImageScope}
                      onChange={(event) => {
                        const value = event.target
                          .value as GenerationImageScope;
                        setGenerationImageScope(value);
                        if (
                          value === "selective" &&
                          selectedImageOutlineIds.length === 0 &&
                          outline?.slides[0]
                        ) {
                          setSelectedImageOutlineIds([
                            outline.slides[0].outlineSlideId,
                          ]);
                        }
                      }}
                    >
                      <option value="none">不使用图片</option>
                      <option value="cover_only">仅封面 AI 插画</option>
                      <option value="selective">选择页面 AI 插画</option>
                    </select>
                  </label>
                  {generationImageScope === "selective" ? (
                    <div className="image-slide-options">
                      {(outline?.slides ?? [])
                        .map((slide, index) => ({ slide, index }))
                        .filter(
                          ({ slide, index }) =>
                            index === 0 ||
                            [
                              "section",
                              "content",
                              "closing",
                              "ending",
                            ].includes(slide.type),
                        )
                        .map(({ slide, index }) => (
                          <label key={slide.outlineSlideId}>
                            <input
                              type="checkbox"
                              checked={selectedImageOutlineIds.includes(
                                slide.outlineSlideId,
                              )}
                              disabled={
                                !selectedImageOutlineIds.includes(
                                  slide.outlineSlideId,
                                ) &&
                                selectedImageOutlineIds.length >=
                                  (entitlement?.maxImagesPerDeck ?? 0)
                              }
                              onChange={(event) =>
                                setSelectedImageOutlineIds((current) =>
                                  event.target.checked
                                    ? [
                                        ...new Set([
                                          ...current,
                                          slide.outlineSlideId,
                                        ]),
                                      ]
                                    : current.filter(
                                        (value) =>
                                          value !== slide.outlineSlideId,
                                      ),
                                )
                              }
                            />
                            <span>
                              P{String(index + 1).padStart(2, "0")} ·{" "}
                              {slide.title}
                            </span>
                          </label>
                        ))}
                    </div>
                  ) : null}
                </fieldset>
                <fieldset className="image-policy-choice">
                  <legend>视觉复核</legend>
                  <label>
                    <span>复核级别</span>
                    <select
                      value={visualReviewLevel}
                      onChange={(event) =>
                        setVisualReviewLevel(
                          event.target.value as VisualReviewLevel,
                        )
                      }
                    >
                      <option value="off">关闭（推荐，零视觉模型调用）</option>
                      <option value="standard">
                        标准：一次审核与最多一次原子修复
                      </option>
                    </select>
                  </label>
                </fieldset>
              </div>
              <div className="generation-actions">
                <button
                  className="primary-button"
                  type="button"
                  disabled={
                    draft.currentOutlineRevisionId !==
                      summary.outlineRevisionId ||
                    saveState === "saving" ||
                    (summary.sourceSummary.sourceId === null &&
                      !continueLimitedDraft) ||
                    (generationImageScope === "selective" &&
                      (selectedImageOutlineIds.length === 0 ||
                        selectedImageOutlineIds.length >
                          (entitlement?.maxImagesPerDeck ?? 0))) ||
                    (generationImageScope === "cover_only" &&
                      (entitlement?.maxImagesPerDeck ?? 0) < 1) ||
                    !visualStylePlanningJobId ||
                    !selectedVisualStyleId ||
                    Boolean(busyMessage)
                  }
                  onClick={() => void startGeneration()}
                >
                  {busyMessage ?? "开始真实生成"}
                </button>
                <small>设计方案确认与锁定将自动写入不可变生成快照。</small>
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
                </div>
                <div className="intent-grid">
                  <label>
                    制作目标
                    <input
                      value={intent.goal}
                      onChange={(event) =>
                        changeIntent("goal", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    目标受众
                    <input
                      value={intent.audience}
                      onChange={(event) =>
                        changeIntent("audience", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    页数规模
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
                    配图偏好
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
