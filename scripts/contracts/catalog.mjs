import YAML from "yaml";

const SCHEMA_BASE = "https://contracts.instant-ppt.example/v1";
const ULID_PATTERN = "^[0-9A-HJKMNP-TV-Z]{26}$";
const ulid = { type: "string", pattern: ULID_PATTERN };
const timestamp = { type: "string", format: "date-time" };
const nonEmptyString = { type: "string", minLength: 1 };
const objectKey = {
  type: "string",
  pattern: "^[a-z0-9][a-z0-9/_\\-.]{0,511}$",
};

const ids = {
  organizationId: "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  actorId: "01ARZ3NDEKTSV4RRFFQ69G5FAW",
  draftId: "01ARZ3NDEKTSV4RRFFQ69G5FAX",
  sourceId: "01ARZ3NDEKTSV4RRFFQ69G5FAY",
  artifactId: "01ARZ3NDEKTSV4RRFFQ69G5FAZ",
  snapshotId: "01ARZ3NDEKTSV4RRFFQ69G5FB0",
  jobId: "01ARZ3NDEKTSV4RRFFQ69G5FB1",
  slideId: "01ARZ3NDEKTSV4RRFFQ69G5FB2",
  revisionId: "01ARZ3NDEKTSV4RRFFQ69G5FB3",
  templateId: "01ARZ3NDEKTSV4RRFFQ69G5FB4",
  templateVersionId: "01ARZ3NDEKTSV4RRFFQ69G5FB5",
  eventId: "01ARZ3NDEKTSV4RRFFQ69G5FB6",
  exportId: "01ARZ3NDEKTSV4RRFFQ69G5FB7",
  providerCallId: "01ARZ3NDEKTSV4RRFFQ69G5FB8",
};

const now = "2026-08-16T08:00:00Z";

function schema(
  title,
  properties,
  required = Object.keys(properties),
  extra = {},
) {
  return {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    $id: `${SCHEMA_BASE}/${title}.schema.json`,
    title,
    type: "object",
    additionalProperties: false,
    properties: {
      schemaVersion: { type: "integer", const: 1 },
      ...properties,
    },
    required: ["schemaVersion", ...required],
    ...extra,
  };
}

const schemas = {
  UploadSession: schema("UploadSession", {
    uploadSessionId: ulid,
    organizationId: ulid,
    objectKey,
    declaredMimeType: {
      enum: [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/html",
      ],
    },
    expectedSha256: { type: "string", pattern: "^[a-f0-9]{64}$" },
    maxBytes: { type: "integer", minimum: 1, maximum: 52428800 },
    expiresAt: timestamp,
    status: {
      enum: ["pending", "uploaded", "completed", "expired", "rejected"],
    },
  }),
  SourceArtifact: schema("SourceArtifact", {
    artifactId: ulid,
    sourceId: ulid,
    organizationId: ulid,
    kind: { enum: ["markdown", "asset", "conversion_profile"] },
    objectKey,
    sha256: { type: "string", pattern: "^[a-f0-9]{64}$" },
    mimeType: nonEmptyString,
    sizeBytes: { type: "integer", minimum: 0 },
    parserVersion: nonEmptyString,
    createdAt: timestamp,
  }),
  SourcePackage: schema("SourcePackage", {
    sourceId: ulid,
    organizationId: ulid,
    sourceSha256: { type: "string", pattern: "^[a-f0-9]{64}$" },
    language: { enum: ["zh-CN", "en-US", "mixed"] },
    markdownArtifactId: ulid,
    assetArtifactIds: { type: "array", items: ulid, uniqueItems: true },
    conversionProfileArtifactId: ulid,
    parserVersion: nonEmptyString,
    createdAt: timestamp,
  }),
  IntentSpec: schema("IntentSpec", {
    intentRevisionId: ulid,
    title: nonEmptyString,
    audience: nonEmptyString,
    goal: nonEmptyString,
    targetSlideCount: { type: "integer", minimum: 4, maximum: 30 },
    language: { enum: ["zh-CN", "en-US"] },
    contentDepth: { enum: ["conclusion_first", "balanced", "research"] },
    visualPreference: {
      enum: ["data_first", "photo_illustration", "minimal_visual"],
    },
    notes: { type: "string", maxLength: 4000 },
    sourceRefs: { type: "array", items: ulid, uniqueItems: true },
  }),
  OutlineSpec: schema("OutlineSpec", {
    outlineRevisionId: ulid,
    storySummary: nonEmptyString,
    targetSlideCount: { type: "integer", minimum: 4, maximum: 30 },
    slides: {
      type: "array",
      minItems: 1,
      maxItems: 30,
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "outlineSlideId",
          "type",
          "title",
          "keyPoints",
          "sourceCitations",
        ],
        properties: {
          outlineSlideId: ulid,
          type: nonEmptyString,
          title: nonEmptyString,
          keyPoints: { type: "array", minItems: 1, items: nonEmptyString },
          sourceCitations: { type: "array", items: ulid, uniqueItems: true },
        },
      },
    },
  }),
  PlanningJob: schema(
    "PlanningJob",
    {
      planningJobId: ulid,
      draftId: ulid,
      operation: { enum: ["intent_infer", "outline_generate"] },
      status: {
        enum: ["queued", "running", "retrying", "succeeded", "failed"],
      },
      attempt: { type: "integer", minimum: 0, maximum: 5 },
      maxAttempts: { type: "integer", minimum: 1, maximum: 5 },
      terminal: { type: "boolean" },
      retryable: { type: "boolean" },
      errorCode: { anyOf: [nonEmptyString, { type: "null" }] },
      resultRevisionId: { anyOf: [ulid, { type: "null" }] },
      provider: { anyOf: [nonEmptyString, { type: "null" }] },
      model: { anyOf: [nonEmptyString, { type: "null" }] },
      createdAt: timestamp,
      updatedAt: timestamp,
      startedAt: { anyOf: [timestamp, { type: "null" }] },
      finishedAt: { anyOf: [timestamp, { type: "null" }] },
      result: {
        anyOf: [
          { type: "object", additionalProperties: true },
          { type: "null" },
        ],
      },
    },
    [
      "planningJobId",
      "draftId",
      "operation",
      "status",
      "attempt",
      "maxAttempts",
      "terminal",
      "retryable",
      "errorCode",
      "resultRevisionId",
      "provider",
      "model",
      "createdAt",
      "updatedAt",
      "startedAt",
      "finishedAt",
    ],
  ),
  ThemeSpec: schema("ThemeSpec", {
    themeId: nonEmptyString,
    colorTokens: {
      type: "object",
      additionalProperties: { type: "string", pattern: "^#[0-9A-Fa-f]{6}$" },
      minProperties: 2,
    },
    fontFamilies: { type: "array", minItems: 1, items: nonEmptyString },
    aspectRatio: { enum: ["16:9"] },
  }),
  TemplateBinding: schema("TemplateBinding", {
    templateId: ulid,
    templateVersionId: ulid,
    compatibilityVersion: nonEmptyString,
    roleBindings: { type: "object", additionalProperties: nonEmptyString },
  }),
  TemplateVersion: schema("TemplateVersion", {
    templateId: ulid,
    templateVersionId: ulid,
    name: nonEmptyString,
    category: nonEmptyString,
    mode: { const: "native" },
    themeSpec: { $ref: `${SCHEMA_BASE}/ThemeSpec.schema.json` },
    pageRoles: {
      type: "array",
      minItems: 1,
      items: nonEmptyString,
      uniqueItems: true,
    },
    editableElements: {
      type: "array",
      items: nonEmptyString,
      uniqueItems: true,
    },
    engineCompatibility: nonEmptyString,
    createdAt: timestamp,
  }),
  GenerationSnapshot: schema("GenerationSnapshot", {
    snapshotId: ulid,
    organizationId: ulid,
    draftId: ulid,
    intentRevisionId: ulid,
    outlineRevisionId: ulid,
    templateVersionId: ulid,
    modeId: { const: "native" },
    sourceHashes: {
      type: "array",
      items: { type: "string", pattern: "^[a-f0-9]{64}$" },
      uniqueItems: true,
    },
    promptVersion: nonEmptyString,
    engineVersion: nonEmptyString,
    containerVersion: nonEmptyString,
    fontPackVersion: nonEmptyString,
    providerConfigVersion: nonEmptyString,
    snapshotSha256: { type: "string", pattern: "^[a-f0-9]{64}$" },
    createdAt: timestamp,
  }),
  SlidePlan: schema("SlidePlan", {
    slideId: ulid,
    outlineSlideId: ulid,
    order: { type: "integer", minimum: 0 },
    role: nonEmptyString,
    title: nonEmptyString,
    body: { type: "array", minItems: 1, items: nonEmptyString },
    editable: { type: "boolean" },
  }),
  DeckPlan: schema("DeckPlan", {
    snapshotId: ulid,
    title: nonEmptyString,
    modeId: { const: "native" },
    templateBinding: { $ref: `${SCHEMA_BASE}/TemplateBinding.schema.json` },
    slides: {
      type: "array",
      minItems: 1,
      maxItems: 30,
      items: { $ref: `${SCHEMA_BASE}/SlidePlan.schema.json` },
    },
  }),
  JobEvent: schema("JobEvent", {
    eventId: ulid,
    jobId: ulid,
    seq: { type: "integer", minimum: 1 },
    type: {
      enum: [
        "job.queued",
        "job.started",
        "job.stage.changed",
        "job.cancel.requested",
        "job.cancelled",
        "job.completed",
        "job.partially_completed",
        "job.failed",
        "slide.started",
        "slide.stage.changed",
        "slide.ready",
        "slide.failed",
        "slide.retrying",
        "qa.completed",
        "artifact.published",
      ],
    },
    occurredAt: timestamp,
    snapshotId: ulid,
    slideId: { anyOf: [ulid, { type: "null" }] },
    attempt: { type: "integer", minimum: 0 },
    stage: nonEmptyString,
    status: nonEmptyString,
    progress: {
      type: "object",
      additionalProperties: false,
      required: ["completed", "total"],
      properties: {
        completed: { type: "integer", minimum: 0 },
        total: { type: "integer", minimum: 0 },
      },
    },
    data: { type: "object", additionalProperties: true },
    traceId: nonEmptyString,
  }),
  SseReset: schema("SseReset", {
    jobId: ulid,
    reason: { enum: ["retention_window_exceeded", "sequence_unavailable"] },
    snapshotUrl: { type: "string", pattern: "^/v1/jobs/" },
    latestSeq: { type: "integer", minimum: 0 },
  }),
  SseSnapshot: schema("SseSnapshot", {
    jobId: ulid,
    status: {
      enum: [
        "queued",
        "running",
        "cancel_requested",
        "cancelled",
        "succeeded",
        "partially_succeeded",
        "failed",
      ],
    },
    stage: nonEmptyString,
    engineProfile: {
      enum: ["default-agentic", "deterministic-template", "quick-engineering"],
    },
    authoringMode: { enum: ["agent-authoring", "deterministic-template"] },
    authoringDisclosure: {
      enum: [
        "agent-authored-editable-draft",
        "template-limited-editable-draft",
      ],
    },
    fallbackReason: { anyOf: [nonEmptyString, { type: "null" }] },
    latestSeq: { type: "integer", minimum: 0 },
    terminal: { type: "boolean" },
  }),
  QaReport: schema(
    "QaReport",
    {
      reportId: ulid,
      subjectType: { enum: ["slide", "deck", "package"] },
      subjectId: ulid,
      profile: {
        enum: ["quick-engineering", "default-agentic", "deterministic-template"],
      },
      quickGenerate: { type: "boolean" },
      passed: { type: "boolean" },
      findings: {
        type: "array",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["code", "severity", "message"],
          properties: {
            code: nonEmptyString,
            severity: { enum: ["info", "warning", "sev2", "sev1"] },
            message: nonEmptyString,
          },
        },
      },
      contentQa: {
        type: "object",
        additionalProperties: false,
        required: ["preRender", "finalSvg", "compiledPptx"],
        properties: {
          preRender: { type: "object", additionalProperties: true },
          finalSvg: { type: "object", additionalProperties: true },
          compiledPptx: { type: "object", additionalProperties: true },
        },
      },
      checkedAt: timestamp,
    },
    ["reportId", "subjectType", "subjectId", "passed", "findings", "checkedAt"],
  ),
  ArtifactManifest: schema(
    "ArtifactManifest",
    {
      artifactId: ulid,
      organizationId: ulid,
      artifactType: {
        enum: [
          "generation_source_bundle",
          "generation_baseline_pptx",
          "presentation_revision_manifest",
          "export_pptx",
        ],
      },
      objectKey,
      sha256: { type: "string", pattern: "^[a-f0-9]{64}$" },
      mimeType: nonEmptyString,
      sizeBytes: { type: "integer", minimum: 0 },
      engineVersion: nonEmptyString,
      fontPackVersion: nonEmptyString,
      engineProfile: {
        enum: ["quick-engineering", "default-agentic", "deterministic-template"],
      },
      authoringMode: { enum: ["agent-authoring", "deterministic-template"] },
      authoringDisclosure: {
        enum: [
          "agent-authored-editable-draft",
          "template-limited-editable-draft",
        ],
      },
      fallbackReason: { anyOf: [nonEmptyString, { type: "null" }] },
      suggestedFilename: nonEmptyString,
      quickGenerate: { type: "boolean" },
      snapshotId: { anyOf: [ulid, { type: "null" }] },
      presentationRevisionId: { anyOf: [ulid, { type: "null" }] },
      createdAt: timestamp,
    },
    [
      "artifactId",
      "organizationId",
      "artifactType",
      "objectKey",
      "sha256",
      "mimeType",
      "sizeBytes",
      "engineVersion",
      "fontPackVersion",
      "engineProfile",
      "authoringMode",
      "authoringDisclosure",
      "fallbackReason",
      "suggestedFilename",
      "snapshotId",
      "presentationRevisionId",
      "createdAt",
    ],
  ),
  SlideVersion: schema("SlideVersion", {
    slideVersionId: ulid,
    slideId: ulid,
    sourceSnapshotId: ulid,
    status: { enum: ["ready", "failed", "deleted"] },
    title: nonEmptyString,
    body: { type: "array", items: nonEmptyString },
    artifactId: { anyOf: [ulid, { type: "null" }] },
    createdAt: timestamp,
  }),
  PresentationRevision: schema("PresentationRevision", {
    presentationId: ulid,
    presentationRevisionId: ulid,
    basedOnRevisionId: { anyOf: [ulid, { type: "null" }] },
    organizationId: ulid,
    slideVersionIds: {
      type: "array",
      minItems: 1,
      items: ulid,
      uniqueItems: true,
    },
    acceptedMissingSlideIds: { type: "array", items: ulid, uniqueItems: true },
    engineProfile: {
      enum: ["default-agentic", "deterministic-template", "quick-engineering"],
    },
    authoringMode: { enum: ["agent-authoring", "deterministic-template"] },
    authoringDisclosure: {
      enum: [
        "agent-authored-editable-draft",
        "template-limited-editable-draft",
      ],
    },
    suggestedFilename: nonEmptyString,
    createdBy: ulid,
    createdAt: timestamp,
  }),
  ExportJob: schema("ExportJob", {
    exportId: ulid,
    organizationId: ulid,
    presentationRevisionId: ulid,
    status: { enum: ["queued", "running", "succeeded", "failed", "cancelled"] },
    artifactId: { anyOf: [ulid, { type: "null" }] },
    createdAt: timestamp,
    updatedAt: timestamp,
  }),
  ExportManifest: schema("ExportManifest", {
    exportId: ulid,
    presentationRevisionId: ulid,
    artifact: { $ref: `${SCHEMA_BASE}/ArtifactManifest.schema.json` },
    reusedFromArtifactId: { anyOf: [ulid, { type: "null" }] },
    compilerVersion: nonEmptyString,
    packageQaReportId: ulid,
    createdAt: timestamp,
  }),
  Entitlement: schema("Entitlement", {
    organizationId: ulid,
    capability: nonEmptyString,
    limit: { type: "integer", minimum: 0 },
    used: { type: "integer", minimum: 0 },
    resetsAt: timestamp,
  }),
  UsageReservation: schema("UsageReservation", {
    reservationId: ulid,
    organizationId: ulid,
    jobId: ulid,
    idempotencyKey: nonEmptyString,
    reservedSlides: { type: "integer", minimum: 1, maximum: 30 },
    status: { enum: ["reserved", "settled", "released"] },
    createdAt: timestamp,
  }),
  UsageLedger: schema("UsageLedger", {
    ledgerId: ulid,
    organizationId: ulid,
    jobId: ulid,
    slideCount: { type: "integer", minimum: 0 },
    modelTokens: { type: "integer", minimum: 0 },
    imageCount: { type: "integer", const: 0 },
    workerSeconds: { type: "number", minimum: 0 },
    exportCount: { type: "integer", minimum: 0 },
    recordedAt: timestamp,
  }),
  ProviderCall: schema("ProviderCall", {
    providerCallId: ulid,
    organizationId: ulid,
    provider: nonEmptyString,
    model: nonEmptyString,
    purpose: nonEmptyString,
    requestHash: { type: "string", pattern: "^[a-f0-9]{64}$" },
    status: { enum: ["succeeded", "failed", "rate_limited", "timed_out"] },
    inputTokens: { type: "integer", minimum: 0 },
    outputTokens: { type: "integer", minimum: 0 },
    startedAt: timestamp,
    finishedAt: timestamp,
  }),
  AuditEvent: schema("AuditEvent", {
    auditEventId: ulid,
    organizationId: ulid,
    actorId: ulid,
    resourceType: nonEmptyString,
    resourceId: ulid,
    action: nonEmptyString,
    requestId: nonEmptyString,
    outcome: { enum: ["allowed", "denied", "failed"] },
    occurredAt: timestamp,
  }),
  ProblemDetails: schema("ProblemDetails", {
    type: { type: "string", format: "uri-reference" },
    title: nonEmptyString,
    status: { type: "integer", minimum: 400, maximum: 599 },
    detail: nonEmptyString,
    instance: { type: "string", format: "uri-reference" },
    code: {
      enum: [
        "validation_error",
        "authorization_error",
        "quota_exceeded",
        "unsafe_file",
        "parse_failed",
        "provider_rate_limited",
        "provider_timeout",
        "engine_contract_failed",
        "slide_render_failed",
        "slide_qa_failed",
        "compile_failed",
        "package_qa_failed",
        "cancelled_by_user",
        "idempotency_key_reused",
        "revision_conflict",
        "internal_error",
      ],
    },
    retryable: { type: "boolean" },
    requestId: nonEmptyString,
    fieldErrors: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["field", "message"],
        properties: { field: nonEmptyString, message: nonEmptyString },
      },
    },
  }),
};

const positives = {
  UploadSession: {
    schemaVersion: 1,
    uploadSessionId: ids.sourceId,
    organizationId: ids.organizationId,
    objectKey: "org/01/quarantine/source.docx",
    declaredMimeType:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    expectedSha256: "a".repeat(64),
    maxBytes: 52428800,
    expiresAt: now,
    status: "pending",
  },
  SourceArtifact: {
    schemaVersion: 1,
    artifactId: ids.artifactId,
    sourceId: ids.sourceId,
    organizationId: ids.organizationId,
    kind: "markdown",
    objectKey: "org/01/published/source.md",
    sha256: "b".repeat(64),
    mimeType: "text/markdown",
    sizeBytes: 120,
    parserVersion: "source-parser@1",
    createdAt: now,
  },
  SourcePackage: {
    schemaVersion: 1,
    sourceId: ids.sourceId,
    organizationId: ids.organizationId,
    sourceSha256: "c".repeat(64),
    language: "zh-CN",
    markdownArtifactId: ids.artifactId,
    assetArtifactIds: [],
    conversionProfileArtifactId: ids.exportId,
    parserVersion: "source-parser@1",
    createdAt: now,
  },
  IntentSpec: {
    schemaVersion: 1,
    intentRevisionId: ids.revisionId,
    title: "年度经营复盘",
    audience: "管理层",
    goal: "经营复盘",
    targetSlideCount: 12,
    language: "zh-CN",
    contentDepth: "conclusion_first",
    visualPreference: "data_first",
    notes: "突出结论与行动",
    sourceRefs: [ids.artifactId],
  },
  OutlineSpec: {
    schemaVersion: 1,
    outlineRevisionId: ids.revisionId,
    storySummary: "从结果到原因再到行动",
    targetSlideCount: 4,
    slides: [
      {
        outlineSlideId: ids.slideId,
        type: "cover",
        title: "年度经营复盘",
        keyPoints: ["结论先行"],
        sourceCitations: [ids.artifactId],
      },
    ],
  },
  PlanningJob: {
    schemaVersion: 1,
    planningJobId: ids.jobId,
    draftId: ids.draftId,
    operation: "outline_generate",
    status: "retrying",
    attempt: 2,
    maxAttempts: 3,
    terminal: false,
    retryable: true,
    errorCode: "provider_timeout",
    resultRevisionId: null,
    provider: null,
    model: null,
    createdAt: now,
    updatedAt: now,
    startedAt: now,
    finishedAt: null,
    result: null,
  },
  ThemeSpec: {
    schemaVersion: 1,
    themeId: "editorial-cobalt",
    colorTokens: { primary: "#1746D1", background: "#F7F3E8" },
    fontFamilies: ["Noto Sans CJK SC"],
    aspectRatio: "16:9",
  },
  TemplateBinding: {
    schemaVersion: 1,
    templateId: ids.templateId,
    templateVersionId: ids.templateVersionId,
    compatibilityVersion: "engine-v4.7",
    roleBindings: { cover: "layout-cover" },
  },
  TemplateVersion: null,
  GenerationSnapshot: {
    schemaVersion: 1,
    snapshotId: ids.snapshotId,
    organizationId: ids.organizationId,
    draftId: ids.draftId,
    intentRevisionId: ids.revisionId,
    outlineRevisionId: ids.revisionId,
    templateVersionId: ids.templateVersionId,
    modeId: "native",
    sourceHashes: ["d".repeat(64)],
    promptVersion: "prompt-v1",
    engineVersion: "ppt-master-v4.7.0",
    containerVersion: "sha256:pending-g01",
    fontPackVersion: "fonts-v1",
    providerConfigVersion: "fake-v1",
    snapshotSha256: "e".repeat(64),
    createdAt: now,
  },
  SlidePlan: {
    schemaVersion: 1,
    slideId: ids.slideId,
    outlineSlideId: ids.slideId,
    order: 0,
    role: "cover",
    title: "年度经营复盘",
    body: ["结论先行"],
    editable: true,
  },
  DeckPlan: null,
  JobEvent: {
    schemaVersion: 1,
    eventId: ids.eventId,
    jobId: ids.jobId,
    seq: 1,
    type: "job.queued",
    occurredAt: now,
    snapshotId: ids.snapshotId,
    slideId: null,
    attempt: 0,
    stage: "deck_planning",
    status: "queued",
    progress: { completed: 0, total: 4 },
    data: {},
    traceId: "trace-001",
  },
  SseReset: {
    schemaVersion: 1,
    jobId: ids.jobId,
    reason: "retention_window_exceeded",
    snapshotUrl: `/v1/jobs/${ids.jobId}`,
    latestSeq: 42,
  },
  SseSnapshot: {
    schemaVersion: 1,
    jobId: ids.jobId,
    status: "running",
    stage: "slide_generation",
    engineProfile: "default-agentic",
    authoringMode: "agent-authoring",
    authoringDisclosure: "agent-authored-editable-draft",
    fallbackReason: null,
    latestSeq: 42,
    terminal: false,
  },
  QaReport: {
    schemaVersion: 1,
    reportId: ids.artifactId,
    subjectType: "slide",
    subjectId: ids.slideId,
    passed: true,
    findings: [],
    checkedAt: now,
  },
  ArtifactManifest: {
    schemaVersion: 1,
    artifactId: ids.artifactId,
    organizationId: ids.organizationId,
    artifactType: "generation_baseline_pptx",
    objectKey: "org/01/published/deck.pptx",
    sha256: "f".repeat(64),
    mimeType:
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    sizeBytes: 2048,
    engineVersion: "ppt-master-v4.7.0",
    fontPackVersion: "fonts-v1",
    engineProfile: "default-agentic",
    authoringMode: "agent-authoring",
    authoringDisclosure: "agent-authored-editable-draft",
    fallbackReason: null,
    suggestedFilename: "年度经营复盘.pptx",
    snapshotId: ids.snapshotId,
    presentationRevisionId: null,
    createdAt: now,
  },
  SlideVersion: {
    schemaVersion: 1,
    slideVersionId: ids.revisionId,
    slideId: ids.slideId,
    sourceSnapshotId: ids.snapshotId,
    status: "ready",
    title: "年度经营复盘",
    body: ["结论先行"],
    artifactId: ids.artifactId,
    createdAt: now,
  },
  PresentationRevision: {
    schemaVersion: 1,
    presentationId: ids.draftId,
    presentationRevisionId: ids.revisionId,
    basedOnRevisionId: null,
    organizationId: ids.organizationId,
    slideVersionIds: [ids.revisionId],
    acceptedMissingSlideIds: [],
    engineProfile: "default-agentic",
    authoringMode: "agent-authoring",
    authoringDisclosure: "agent-authored-editable-draft",
    suggestedFilename: "年度经营复盘.pptx",
    createdBy: ids.actorId,
    createdAt: now,
  },
  ExportJob: {
    schemaVersion: 1,
    exportId: ids.exportId,
    organizationId: ids.organizationId,
    presentationRevisionId: ids.revisionId,
    status: "queued",
    artifactId: null,
    createdAt: now,
    updatedAt: now,
  },
  ExportManifest: null,
  Entitlement: {
    schemaVersion: 1,
    organizationId: ids.organizationId,
    capability: "generation_slides_monthly",
    limit: 100,
    used: 0,
    resetsAt: "2026-09-01T00:00:00Z",
  },
  UsageReservation: {
    schemaVersion: 1,
    reservationId: ids.artifactId,
    organizationId: ids.organizationId,
    jobId: ids.jobId,
    idempotencyKey: "idem-001",
    reservedSlides: 12,
    status: "reserved",
    createdAt: now,
  },
  UsageLedger: {
    schemaVersion: 1,
    ledgerId: ids.artifactId,
    organizationId: ids.organizationId,
    jobId: ids.jobId,
    slideCount: 12,
    modelTokens: 3200,
    imageCount: 0,
    workerSeconds: 42.5,
    exportCount: 0,
    recordedAt: now,
  },
  ProviderCall: {
    schemaVersion: 1,
    providerCallId: ids.providerCallId,
    organizationId: ids.organizationId,
    provider: "fake",
    model: "deterministic-v1",
    purpose: "outline.generate",
    requestHash: "1".repeat(64),
    status: "succeeded",
    inputTokens: 120,
    outputTokens: 240,
    startedAt: now,
    finishedAt: now,
  },
  AuditEvent: {
    schemaVersion: 1,
    auditEventId: ids.eventId,
    organizationId: ids.organizationId,
    actorId: ids.actorId,
    resourceType: "draft",
    resourceId: ids.draftId,
    action: "draft.create",
    requestId: "request-001",
    outcome: "allowed",
    occurredAt: now,
  },
  ProblemDetails: {
    schemaVersion: 1,
    type: "https://errors.instant-ppt.example/validation_error",
    title: "请求参数无效",
    status: 422,
    detail: "一个或多个字段不符合合同",
    instance: "/v1/drafts",
    code: "validation_error",
    retryable: false,
    requestId: "request-001",
    fieldErrors: [{ field: "title", message: "不能为空" }],
  },
};

positives.TemplateVersion = {
  schemaVersion: 1,
  templateId: ids.templateId,
  templateVersionId: ids.templateVersionId,
  name: "编辑部蓝",
  category: "business",
  mode: "native",
  themeSpec: positives.ThemeSpec,
  pageRoles: ["cover", "content"],
  editableElements: ["text", "shape"],
  engineCompatibility: "ppt-master-v4.7.0",
  createdAt: now,
};
positives.DeckPlan = {
  schemaVersion: 1,
  snapshotId: ids.snapshotId,
  title: "年度经营复盘",
  modeId: "native",
  templateBinding: positives.TemplateBinding,
  slides: [positives.SlidePlan],
};
positives.ExportManifest = {
  schemaVersion: 1,
  exportId: ids.exportId,
  presentationRevisionId: ids.revisionId,
  artifact: {
    ...positives.ArtifactManifest,
    artifactType: "export_pptx",
    presentationRevisionId: ids.revisionId,
  },
  reusedFromArtifactId: null,
  compilerVersion: "compiler-v1",
  packageQaReportId: ids.artifactId,
  createdAt: now,
};

const endpoints = [
  ["post", "/v1/drafts", "createDraft", 201],
  ["get", "/v1/drafts/{draftId}", "getDraft", 200],
  ["patch", "/v1/drafts/{draftId}", "updateDraft", 200],
  ["delete", "/v1/drafts/{draftId}", "deleteDraft", 202],
  ["post", "/v1/drafts/{draftId}:export-data", "exportDraftData", 202],
  ["get", "/v1/data-exports/{dataExportId}", "getDataExport", 200],
  ["post", "/v1/upload-sessions", "createUploadSession", 201],
  [
    "post",
    "/v1/upload-sessions/{uploadSessionId}:complete",
    "completeUploadSession",
    202,
  ],
  ["post", "/v1/drafts/{draftId}/sources", "attachDraftSource", 202],
  ["get", "/v1/sources/{sourceId}", "getSource", 200],
  ["post", "/v1/sources/{sourceId}:retry-parse", "retrySourceParse", 202],
  ["post", "/v1/drafts/{draftId}/intent:infer", "inferIntent", 202],
  ["get", "/v1/planning-jobs/{planningJobId}", "getPlanningJob", 200],
  [
    "post",
    "/v1/drafts/{draftId}/intent-revisions",
    "createIntentRevision",
    201,
  ],
  ["get", "/v1/drafts/{draftId}/intent-revisions", "listIntentRevisions", 200],
  ["get", "/v1/intent-revisions/{intentRevisionId}", "getIntentRevision", 200],
  ["post", "/v1/drafts/{draftId}/outline:generate", "generateOutline", 202],
  [
    "post",
    "/v1/drafts/{draftId}/outline-revisions",
    "createOutlineRevision",
    201,
  ],
  [
    "get",
    "/v1/drafts/{draftId}/outline-revisions",
    "listOutlineRevisions",
    200,
  ],
  [
    "get",
    "/v1/outline-revisions/{outlineRevisionId}",
    "getOutlineRevision",
    200,
  ],
  [
    "post",
    "/v1/outline-revisions/{outlineRevisionId}:approve",
    "approveOutlineRevision",
    200,
  ],
  ["get", "/v1/templates", "listTemplates", 200],
  [
    "get",
    "/v1/templates/{templateId}/versions/{templateVersionId}",
    "getTemplateVersion",
    200,
  ],
  ["post", "/v1/drafts/{draftId}/generation-jobs", "createGenerationJob", 202],
  ["get", "/v1/jobs/{jobId}", "getGenerationJob", 200],
  ["get", "/v1/jobs/{jobId}/events", "streamJobEvents", 200],
  ["post", "/v1/jobs/{jobId}:cancel", "cancelGenerationJob", 202],
  [
    "post",
    "/v1/jobs/{jobId}/slides/{slideId}:retry",
    "retryGenerationSlide",
    202,
  ],
  ["get", "/v1/presentations/{presentationId}", "getPresentation", 200],
  [
    "post",
    "/v1/presentations/{presentationId}/revisions",
    "createPresentationRevision",
    201,
  ],
  [
    "get",
    "/v1/presentations/{presentationId}/revisions",
    "listPresentationRevisions",
    200,
  ],
  [
    "get",
    "/v1/presentations/{presentationId}/revisions/{presentationRevisionId}",
    "getPresentationRevision",
    200,
  ],
  [
    "post",
    "/v1/presentations/{presentationId}/slides/{slideId}:regenerate",
    "regeneratePresentationSlide",
    202,
  ],
  [
    "post",
    "/v1/presentations/{presentationId}/exports",
    "createPresentationExport",
    202,
  ],
  ["get", "/v1/exports/{exportId}", "getExport", 200],
  [
    "post",
    "/v1/artifacts/{artifactId}:authorize-download",
    "authorizeArtifactDownload",
    200,
  ],
  ["get", "/v1/history", "listHistory", 200],
  ["get", "/v1/me/entitlements", "getMyEntitlements", 200],
  ["get", "/v1/me/usage", "getMyUsage", 200],
].map(([method, path, operationId, successStatus]) => ({
  method,
  path,
  operationId,
  successStatus,
}));

const stateMachines = {
  schemaVersion: 1,
  machines: {
    source: {
      initial: "upload_pending",
      terminal: ["parsed", "rejected", "parse_failed", "cancelled"],
      transitions: {
        upload_pending: ["uploading", "cancelled"],
        uploading: ["uploaded", "rejected", "cancelled"],
        uploaded: ["scanning", "rejected"],
        scanning: ["clean", "rejected"],
        clean: ["parsing"],
        parsing: ["parsed", "parse_failed"],
        parse_failed: [],
        parsed: [],
        rejected: [],
        cancelled: [],
      },
    },
    job: {
      initial: "queued",
      terminal: ["succeeded", "partially_succeeded", "failed", "cancelled"],
      transitions: {
        queued: ["running", "cancel_requested"],
        running: [
          "succeeded",
          "partially_succeeded",
          "failed",
          "cancel_requested",
        ],
        cancel_requested: [
          "cancelled",
          "succeeded",
          "partially_succeeded",
          "failed",
        ],
        succeeded: [],
        partially_succeeded: [],
        failed: [],
        cancelled: [],
      },
    },
    slide: {
      initial: "pending",
      terminal: ["ready", "cancelled"],
      conditionallyTerminal: ["failed"],
      transitions: {
        pending: ["running", "cancelled"],
        running: ["ready", "failed", "cancelled"],
        failed: ["retrying"],
        retrying: ["running", "failed", "cancelled"],
        ready: [],
        cancelled: [],
      },
    },
    export: {
      initial: "queued",
      terminal: ["succeeded", "failed", "cancelled"],
      transitions: {
        queued: ["running", "cancelled"],
        running: ["succeeded", "failed", "cancelled"],
        succeeded: [],
        failed: [],
        cancelled: [],
      },
    },
    planning: {
      initial: "queued",
      terminal: ["succeeded", "failed"],
      transitions: {
        queued: ["running"],
        running: ["retrying", "succeeded", "failed"],
        retrying: ["running", "failed"],
        succeeded: [],
        failed: [],
      },
    },
  },
  jobEventStatusMap: {
    "job.queued": "queued",
    "job.started": "running",
    "job.cancel.requested": "cancel_requested",
    "job.completed": "succeeded",
    "job.partially_completed": "partially_succeeded",
    "job.failed": "failed",
    "job.cancelled": "cancelled",
  },
  terminalRules: {
    succeeded: "all required slides ready and package/publish succeeded",
    partially_succeeded:
      "at least one required slide ready and at least one exhausted failure",
    failed:
      "no required slide ready or unrecoverable deck/package/publish failure",
    cancelled:
      "cancel transaction committed before another terminal transaction",
  },
  logicalTaskKey: ["organizationId", "snapshotId", "stage", "slideId?"],
  executionMetadataExcludedFromLogicalKey: ["attempt"],
};

const errorCodes = {
  schemaVersion: 1,
  codes: positives.ProblemDetails.code
    ? schemas.ProblemDetails.properties.code.enum.map((code) => ({
        code,
        retryable: [
          "provider_rate_limited",
          "provider_timeout",
          "internal_error",
        ].includes(code),
      }))
    : [],
};

const goalRequirements = {
  schemaVersion: 1,
  goals: {
    G01: {
      schemas: [
        "SourcePackage",
        "DeckPlan",
        "SlidePlan",
        "QaReport",
        "ArtifactManifest",
        "ProblemDetails",
      ],
      endpoints: [],
    },
    G02: {
      schemas: [
        "GenerationSnapshot",
        "JobEvent",
        "SseReset",
        "SseSnapshot",
        "UsageReservation",
        "UsageLedger",
        "ProblemDetails",
      ],
      endpoints: [
        "createGenerationJob",
        "getGenerationJob",
        "streamJobEvents",
        "cancelGenerationJob",
        "retryGenerationSlide",
      ],
    },
    G03: {
      schemas: [
        "Entitlement",
        "AuditEvent",
        "ArtifactManifest",
        "ProblemDetails",
      ],
      endpoints: [
        "getMyEntitlements",
        "getMyUsage",
        "authorizeArtifactDownload",
      ],
    },
    G04: {
      schemas: [
        "UploadSession",
        "SourcePackage",
        "SourceArtifact",
        "ProblemDetails",
      ],
      endpoints: [
        "createUploadSession",
        "completeUploadSession",
        "attachDraftSource",
        "getSource",
        "retrySourceParse",
      ],
    },
    G05: {
      schemas: [
        "IntentSpec",
        "OutlineSpec",
        "PlanningJob",
        "TemplateVersion",
        "ProviderCall",
        "ProblemDetails",
      ],
      endpoints: [
        "createDraft",
        "getDraft",
        "updateDraft",
        "inferIntent",
        "getPlanningJob",
        "createIntentRevision",
        "generateOutline",
        "createOutlineRevision",
        "approveOutlineRevision",
        "listTemplates",
        "getTemplateVersion",
      ],
    },
    G06: {
      schemas: [
        "GenerationSnapshot",
        "DeckPlan",
        "SlidePlan",
        "JobEvent",
        "QaReport",
        "ArtifactManifest",
        "UsageReservation",
        "UsageLedger",
      ],
      endpoints: [
        "createGenerationJob",
        "getGenerationJob",
        "streamJobEvents",
        "cancelGenerationJob",
        "retryGenerationSlide",
      ],
    },
    G07: {
      schemas: [
        "PresentationRevision",
        "SlideVersion",
        "ExportJob",
        "ExportManifest",
        "ArtifactManifest",
      ],
      endpoints: [
        "getPresentation",
        "createPresentationRevision",
        "regeneratePresentationSlide",
        "createPresentationExport",
        "getExport",
        "listHistory",
        "exportDraftData",
      ],
    },
    G08: {
      schemas: Object.keys(schemas),
      endpoints: endpoints.map(({ operationId }) => operationId),
    },
  },
};

function stripSchemaMeta(value) {
  if (Array.isArray(value)) return value.map(stripSchemaMeta);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !["$schema", "$id"].includes(key))
      .map(([key, entry]) => {
        if (
          key === "$ref" &&
          typeof entry === "string" &&
          entry.startsWith(`${SCHEMA_BASE}/`)
        ) {
          const schemaName = entry
            .slice(`${SCHEMA_BASE}/`.length)
            .replace(/\.schema\.json$/, "");
          return [key, `#/components/schemas/${schemaName}`];
        }
        return [key, stripSchemaMeta(entry)];
      }),
  );
}

function openApiDocument() {
  const paths = {};
  for (const endpoint of endpoints) {
    paths[endpoint.path] ??= {};
    const pathParams = [...endpoint.path.matchAll(/\{([^}]+)\}/g)].map(
      (match) => ({
        name: match[1],
        in: "path",
        required: true,
        schema: { type: "string", pattern: ULID_PATTERN },
      }),
    );
    const isWrite = endpoint.method !== "get";
    paths[endpoint.path][endpoint.method] = {
      operationId: endpoint.operationId,
      tags: [endpoint.path.split("/")[2] || "system"],
      parameters: [
        ...pathParams,
        ...(isWrite
          ? [
              {
                name: "Idempotency-Key",
                in: "header",
                required: true,
                schema: { type: "string", minLength: 1, maxLength: 255 },
              },
            ]
          : []),
      ],
      ...(isWrite
        ? {
            requestBody: {
              required: true,
              content: {
                "application/json": {
                  schema: {
                    $ref:
                      endpoint.operationId === "createGenerationJob"
                        ? "#/components/schemas/CreateGenerationJobRequest"
                        : "#/components/schemas/MutationRequest",
                  },
                },
              },
            },
          }
        : {}),
      responses: {
        [endpoint.successStatus]: {
          description: "Successful response",
          headers:
            endpoint.successStatus === 202
              ? { Location: { required: true, schema: { type: "string" } } }
              : undefined,
          content:
            endpoint.operationId === "streamJobEvents"
              ? { "text/event-stream": { schema: { type: "string" } } }
              : {
                  "application/json": {
                    schema: { $ref: "#/components/schemas/ResourceResponse" },
                  },
                },
        },
        default: {
          description: "RFC 7807 problem",
          content: {
            "application/problem+json": {
              schema: { $ref: "#/components/schemas/ProblemDetails" },
            },
          },
        },
      },
    };
  }
  return {
    openapi: "3.1.0",
    info: {
      title: "即刻AI-PPT API",
      version: "1.0.0",
      description:
        "P1 contract baseline. Implementations are delivered by later Goals.",
    },
    servers: [
      { url: "http://localhost:8000", description: "Local development" },
    ],
    security: [{ bearerAuth: [] }],
    paths,
    components: {
      securitySchemes: {
        bearerAuth: { type: "http", scheme: "bearer", bearerFormat: "JWT" },
      },
      schemas: {
        ...Object.fromEntries(
          Object.entries(schemas).map(([name, value]) => [
            name,
            stripSchemaMeta(value),
          ]),
        ),
        MutationRequest: {
          type: "object",
          additionalProperties: false,
          required: ["schemaVersion", "data"],
          properties: {
            schemaVersion: { type: "integer", const: 1 },
            data: { type: "object", additionalProperties: true },
            baseRevisionId: {
              anyOf: [
                { type: "string", pattern: ULID_PATTERN },
                { type: "null" },
              ],
            },
          },
        },
        GenerationImagePolicy: {
          title: "GenerationImagePolicy",
          oneOf: [
            {
              type: "object",
              additionalProperties: false,
              required: ["scope", "usage", "notes"],
              properties: {
                scope: { const: "none" },
                usage: { const: ["none"] },
                notes: { type: "object", maxProperties: 0 },
                aiPath: { type: "null" },
                aiPathChain: { type: "array", maxItems: 0 },
              },
            },
            {
              type: "object",
              additionalProperties: false,
              required: ["scope", "usage", "notes", "aiPath", "aiPathChain"],
              properties: {
                scope: { const: "cover_only" },
                usage: { const: ["ai"] },
                notes: {
                  type: "object",
                  additionalProperties: false,
                  required: ["cover"],
                  properties: { cover: nonEmptyString },
                },
                aiPath: { enum: ["auto", "api", "host-native", "manual"] },
                aiPathChain: {
                  type: "array",
                  minItems: 1,
                  maxItems: 3,
                  uniqueItems: true,
                  items: { enum: ["api", "host-native", "manual"] },
                },
              },
            },
            {
              type: "object",
              additionalProperties: false,
              required: ["scope", "usage", "notes", "aiPath", "aiPathChain"],
              properties: {
                scope: { const: "selective" },
                usage: { const: ["ai"] },
                notes: {
                  type: "object",
                  minProperties: 1,
                  propertyNames: { pattern: ULID_PATTERN },
                  additionalProperties: nonEmptyString,
                },
                aiPath: { enum: ["auto", "api", "host-native", "manual"] },
                aiPathChain: {
                  type: "array",
                  minItems: 1,
                  maxItems: 3,
                  uniqueItems: true,
                  items: { enum: ["api", "host-native", "manual"] },
                },
              },
            },
          ],
        },
        CreateGenerationJobData: {
          title: "CreateGenerationJobData",
          type: "object",
          additionalProperties: false,
          properties: {
            intentRevisionId: { anyOf: [ulid, { type: "null" }] },
            outlineRevisionId: { anyOf: [ulid, { type: "null" }] },
            templateVersionId: { anyOf: [ulid, { type: "null" }] },
            slideCount: {
              type: "integer",
              minimum: 1,
              maximum: 30,
              default: 3,
            },
            sourceHashes: {
              type: "array",
              items: { type: "string", pattern: "^[a-f0-9]{64}$" },
            },
            failureModes: {
              type: "object",
              additionalProperties: { enum: ["none", "once", "always"] },
            },
            stepDelayMs: {
              type: "integer",
              minimum: 0,
              maximum: 10000,
              default: 0,
            },
            crashOnceAtPosition: {
              anyOf: [
                { type: "integer", minimum: 1, maximum: 30 },
                { type: "null" },
              ],
            },
            continueLimitedDraft: { type: "boolean", default: false },
            authorizeStrategistDesignLock: {
              type: "boolean",
              default: false,
              description:
                "Explicitly authorizes the Strategist design proposal and spec lock before Executor authoring.",
            },
            imagePolicy: { $ref: "#/components/schemas/GenerationImagePolicy" },
          },
        },
        CreateGenerationJobRequest: {
          title: "CreateGenerationJobRequest",
          type: "object",
          additionalProperties: false,
          required: ["schemaVersion", "data"],
          properties: {
            schemaVersion: { type: "integer", const: 1 },
            data: { $ref: "#/components/schemas/CreateGenerationJobData" },
            baseRevisionId: { anyOf: [ulid, { type: "null" }] },
          },
        },
        ResourceResponse: {
          type: "object",
          additionalProperties: false,
          required: ["schemaVersion", "resourceId", "resourceType", "data"],
          properties: {
            schemaVersion: { type: "integer", const: 1 },
            resourceId: { type: "string", pattern: ULID_PATTERN },
            resourceType: { type: "string", minLength: 1 },
            data: { type: "object", additionalProperties: true },
            nextCursor: { anyOf: [{ type: "string" }, { type: "null" }] },
          },
        },
      },
    },
  };
}

function endpointFixture(endpoint) {
  const pathParams = Object.fromEntries(
    [...endpoint.path.matchAll(/\{([^}]+)\}/g)].map((match) => [
      match[1],
      ids.draftId,
    ]),
  );
  const concretePath = endpoint.path.replace(/\{[^}]+\}/g, ids.draftId);
  const isWrite = endpoint.method !== "get";
  return {
    operationId: endpoint.operationId,
    request: {
      method: endpoint.method.toUpperCase(),
      path: endpoint.path,
      pathParams,
      query: endpoint.method === "get" ? { cursor: null, limit: 20 } : {},
      headers: isWrite
        ? { "Idempotency-Key": `fixture-${endpoint.operationId}` }
        : {},
      body: isWrite
        ? endpoint.operationId === "createGenerationJob"
          ? {
              schemaVersion: 1,
              data: {
                imagePolicy: {
                  scope: "none",
                  usage: ["none"],
                  notes: {},
                  aiPath: null,
                  aiPathChain: [],
                },
              },
              baseRevisionId: null,
            }
          : {
              schemaVersion: 1,
              data: { fixture: endpoint.operationId },
              baseRevisionId: null,
            }
        : null,
    },
    response: {
      status: endpoint.successStatus,
      headers:
        endpoint.successStatus === 202
          ? { Location: `/v1/operations/${ids.jobId}` }
          : {},
      body: {
        schemaVersion: 1,
        resourceId: ids.draftId,
        resourceType: endpoint.operationId,
        data: { fixture: true },
        nextCursor: null,
      },
    },
    error: {
      ...positives.ProblemDetails,
      instance: concretePath,
      requestId: `request-${endpoint.operationId}`,
    },
  };
}

export function generatedOutputs() {
  const output = new Map();
  for (const [name, value] of Object.entries(schemas)) {
    output.set(
      `packages/contracts/schemas/v1/${name}.schema.json`,
      `${JSON.stringify(value, null, 2)}\n`,
    );
    output.set(
      `packages/contracts/fixtures/schemas/${name}.valid.json`,
      `${JSON.stringify(positives[name], null, 2)}\n`,
    );
    const invalid = { ...positives[name], schemaVersion: 2 };
    output.set(
      `packages/contracts/fixtures/schemas/${name}.invalid.json`,
      `${JSON.stringify(invalid, null, 2)}\n`,
    );
  }
  for (const endpoint of endpoints) {
    output.set(
      `packages/contracts/fixtures/endpoints/${endpoint.operationId}.json`,
      `${JSON.stringify(endpointFixture(endpoint), null, 2)}\n`,
    );
  }
  output.set(
    "packages/contracts/openapi.yaml",
    YAML.stringify(openApiDocument(), { lineWidth: 120 }),
  );
  output.set(
    "packages/contracts/state-machines.json",
    `${JSON.stringify(stateMachines, null, 2)}\n`,
  );
  output.set(
    "packages/contracts/error-codes.json",
    `${JSON.stringify(errorCodes, null, 2)}\n`,
  );
  output.set(
    "packages/contracts/required-contracts.json",
    `${JSON.stringify(goalRequirements, null, 2)}\n`,
  );
  return output;
}

export { endpoints, ids, positives, schemas, stateMachines };
