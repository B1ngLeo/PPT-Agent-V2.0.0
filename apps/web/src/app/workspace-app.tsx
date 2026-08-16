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
};

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

export function WorkspaceApp() {
  const [view, setView] = useState<"loading" | "home" | "workspace">("loading");
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

  const openDraft = useCallback(async (draftId: string, push = true) => {
    setView("loading");
    setError(null);
    try {
      const response = await api<DraftSnapshot>(`/v1/drafts/${draftId}`);
      const next = response.data;
      setDraft(next);
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
        const draftId = new URLSearchParams(window.location.search).get(
          "draft",
        );
        if (draftId) await openDraft(draftId, false);
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
  }, [openDraft, refreshHistory]);

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

  const returnHome = () => {
    setView("home");
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

      {view === "home" ? (
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
                <button className="primary-button" type="button" disabled>
                  开始生成（G06 开放）
                </button>
                <small>当前明确停在确认边界，未创建 generation job。</small>
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
                onClick={() => {
                  setHistoryOpen(false);
                  void openDraft(item.draftId);
                }}
              >
                <span>
                  <strong>{item.title}</strong>
                  <small>
                    {new Date(item.updatedAt).toLocaleString("zh-CN")}
                  </small>
                </span>
                <span>
                  {item.status} · {item.mode}
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
