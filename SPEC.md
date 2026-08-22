# 即刻AI-PPT 产品与技术 SPEC

> 文档状态：Implementation Baseline v1.0（待 P0 Gate 验证）  
> 适用范围：P0 技术/合规验证 + P1 闭环 MVP  
> 更新日期：2026-08-16  
> 产品代号：即刻AI-PPT  
> 首页口号：输入清晰的idea,获得即刻可用的PPT

## 0. 文档合同

### 0.1 目的

本 SPEC 将现有技术方案、交互原型与工程约束收敛为可实现、可测试、可验收的开发基线。它回答四个问题：

1. P0/P1 必须交付什么；
2. 哪些行为属于系统合同，而不是原型演示；
3. Web、API、Worker、数据库、队列与对象存储如何协作；
4. 什么证据可以证明 MVP 已完成。

### 0.2 规范性来源与优先级

实现发生冲突时按以下优先级处理：

1. 本文件 `SPEC.md`；
2. 已批准的 ADR、OpenAPI、JSON Schema 与数据库迁移；
3. [交互原型](designs/ppt-ai-mvp/prototype.html)及其[设计说明](designs/ppt-ai-mvp/prototype-spec.md)，用于视觉、信息架构和交互意图；
4. [技术方案评审稿](designs/ppt-ai-mvp/technical-solution.md)，用于背景、调研、架构理由与风险说明。

原型中的本地计时器、模拟 Toast、硬编码模板、内存历史和假进度不构成生产实现要求；本 SPEC 对应条款才是验收依据。

### 0.3 关键词

- **必须 / MUST**：P1 退出条件，不满足不得宣称 MVP 完成。
- **应该 / SHOULD**：默认实现；偏离时必须记录 ADR 与替代验证证据。
- **可以 / MAY**：可选增强，不得阻塞 P1 主链路。
- **P0 Gate**：进入 P1 产品开发前必须通过的技术、许可与恢复性门禁。
- **P1 Core**：本 SPEC 定义的闭环 MVP。
- **P1.1**：不阻塞 P1 Core 的可选私有模板扩展。
- **Revision**：用户可编辑内容（Intent、Outline、Presentation）的不可变历史记录；API 与表名统一使用 revision。
- **Version**：Schema、模板、引擎、字体包等技术/资产版本，不与用户编辑历史混用。
- **Organization**：P1 唯一租户隔离边界；“tenant”只作为架构泛称，不作为第二套业务实体。
- **Partial**：用户文案泛称；机器状态统一为 `partially_succeeded`，事件统一为 `job.partially_completed`。

## 1. 已冻结的默认决策

以下决策用于消除当前方案中的范围冲突。修改任一项必须新增 ADR，并同步更新本 SPEC 与 `PLAN.md`。

| 决策项 | P0/P1 默认值 |
|---|---|
| 品牌 | 使用“即刻AI-PPT”；不得复制 WPS 名称、Logo、会员文案或高度近似 trade dress。 |
| 主架构 | Next.js Web + FastAPI API + Celery Worker；PostgreSQL 为业务真相源，Redis 仅用于队列、短期缓存和事件分发。 |
| 生成引擎 | 固定审计后的 `ppt-master` tag/commit，通过独立 `engine-adapter` 封装；业务代码不得直接调用上游脚本。 |
| P1 生成模式 | 只开放“原生专业”；“视觉创意”与“模板复用”不得伪装可用，默认由 feature flag 关闭。 |
| 页面创作路径 | 新快照默认冻结 `agent-authoring`；运维可将新快照回退为 `deterministic-template`。fallback 必须在 profile/state/manifest/UI/文件名显示“模板化受限初稿”，不计入 Agent 成功率；旗标不改变已冻结 snapshot 或已发布 revision。 |
| P1 模板能力 | 支持内置模板选择；私有 PPTX 上传、分析和版式映射属于 P1.1，非 P1 Core 退出条件。 |
| 主文档数量 | 每个草稿 P1 支持零或一个主文档；多文档合并不在 P1。 |
| 文档输入白名单 | DOCX、PDF、PPTX、HTML；不支持 DOC、PPT、MD、EPUB 和 URL 抓取。 |
| 私有模板白名单 | 仅 PPTX；不支持旧 `.ppt`。 |
| PDF 解析 | 在 P0 Gate 前完成 PyMuPDF 商业许可或宽松许可证替代栈决策；未通过不得上线 PDF。 |
| 编辑能力 | 文本修改、页面排序、删除、单页重生成；不做 PowerPoint 级自由画布。 |
| 取消语义 | P1 支持安全取消，不支持“暂停后继续”。UI 必须使用“取消任务/取消请求中”，不得复用原型的“暂停/继续”措辞。 |
| 租户模型 | 每个用户自动拥有 personal organization；所有资源仍按 `organization_id` 隔离。 |
| AI/图片供应商 | 通过服务端 Provider Gateway 接入；文本使用 Kimi `kimi-k3`，图片使用 OpenAI `gpt-image-2`。图片默认为 `image_scope=none`，只有用户确认 `cover_only/selective`、组织额度可用、快照冻结受控配置且 Worker 运行时开关/密钥同时就绪时才可请求 Provider；仅设置环境变量不得开启图片。当前每稿上限 1 张，AI 图片仅用于封面/章节/抽象非证据型页面，以独立可替换 PPTX 图片对象嵌入；显式路径失败不可换 Provider 或静默省略 required 资源，未批准的 fallback 必须进入 `Needs-Manual`。密钥只在明确图片任务的子进程中按白名单注入；合同和回归默认使用确定性 Fake Provider。ADR-005 记录具名批准、披露和无法独立验证的代理/上游风险接受。当前仅本地版本将生产 KES/KMS 控制记为不适用/延后；任何对外、多人、托管、QA/预发布或生产部署前必须恢复为必选门禁并补齐机器证据与 Security 签署。 |
| 生成结果定位 | 明确标注为“可编辑初稿”；结果仍需用户核验事实、数据、图表和图片。 |

## 2. 产品定义

### 2.1 问题

用户通常只有一个主题、零散资料或旧文档，却需要在有限时间内产出结构清晰、视觉一致、可继续编辑的演示文稿。现有“一键生成”产品容易在目标、受众、故事线未确认前直接产出整套结果，导致返工、不可追踪修改与长任务失控。

### 2.2 产品承诺

即刻AI-PPT 先帮助用户把创作意图和大纲确认清楚，再异步生成可编辑的原生 PPTX，并让用户能够看到真实进度、恢复历史、处理失败页面和导出明确版本。

### 2.3 P1 成功定义

一个已登录用户可以完成以下闭环：

`创建草稿 → 输入主题或上传主文档 → 确认意图 → 编辑并批准大纲 → 选择内置模板 → 固定生成快照 → 逐页生成与 QA → 处理失败页 → 轻编辑结果 → 导出可打开的原生 PPTX → 从历史恢复`

### 2.4 目标用户

| 角色 | 核心任务 | 主要痛点 |
|---|---|---|
| 业务负责人 | 快速形成汇报、策略、复盘或行动计划 | 逻辑不清、事实证据不足、时间紧 |
| 内容/品牌人员 | 统一表达结构与模板 | 反复套版、样式不一致、版本难追踪 |
| 方案/销售人员 | 将材料转成客户提案 | 文档长、信息取舍困难、需要可编辑交付物 |
| 结果审核者 | 核验并修改生成稿 | 失败页不可恢复、不可追溯 AI 修改、导出版本不明确 |

## 3. 目标与非目标

### 3.1 P0 目标

1. 固定并审计生成引擎版本、依赖、字体包和许可证；
2. 建立 10 份金样本，从解析到 SVG、QA、PPTX 的可重复验证；
3. 验证上传隔离、恶意文件防护与资源限制；
4. 验证 PostgreSQL 持久状态、幂等任务、Worker 崩溃恢复、Redis 重启和 SSE 续传；
5. 形成 P1 可依赖的 OpenAPI、JSON Schema、状态机和错误码合同。

### 3.2 P1 Core 目标

1. 登录、personal organization 与跨租户隔离；
2. 草稿、主题输入、单主文档上传、扫描和解析；
3. 版本化意图与大纲，支持编辑、撤销/恢复、批准；
4. 原生专业模式与内置模板；
5. 不可变生成快照、持久任务、逐页进度、取消和单页重试；
6. 结果预览、有限编辑、PPTX 导出与历史恢复；
7. 审计、配额占位、观测、响应式和 WCAG 2.1 AA 基线。
8. 明确可选的封面/选定页图片资源流程，包含资产分析、路径恢复、Needs-Manual、独立 PPTX 对象、配额/费用和审计。

### 3.3 非目标

- 任意旧 PPT 一键美化；
- 图片、截图或 PDF 完整反向还原为可编辑图层；
- 视觉创意模式和图片化页面；受控图片资源不扩展为整页位图或事实证据生成；
- PowerPoint 级元素自由画布；
- 多人实时协作、评论和复杂版本合并；
- 多源文档合并、URL 抓取、EPUB、DOC、PPT、MD 输入；
- 私有模板分析的高级映射、组织模板治理和公开模板市场；
- 完整会员、支付、账单和公开商品体系；
- PDF/图片导出、TTS、公开分享链接；
- 复制 WPS 的视觉品牌、定价、会员权益或宣传 SLA。

## 4. 领域与系统边界

### 4.1 逻辑模块

| 模块 | 责任 | 明确不负责 |
|---|---|---|
| `identity-tenancy` | 登录、用户、personal organization、成员关系、鉴权上下文 | 草稿和任务业务状态 |
| `draft-workspace` | 草稿、标题、当前版本指针、自动保存、历史恢复 | AI 生成与文件解析 |
| `source-ingestion` | 上传会话、隔离区、扫描、格式识别、解析和素材工件 | 生成演示文稿 |
| `intent-outline` | 意图、大纲、故事线、版本、批准和乐观锁 | Worker 调度 |
| `template-catalog` | 内置模板及其不可变版本、主题元数据 | 用户模板高级分析（P1.1） |
| `generation-orchestrator` | 生成快照、任务/页面状态、取消、重试、配额预占 | 直接运行上游脚本 |
| `engine-adapter` | 将版本化合同映射为 `ppt-master` 输入输出 | 访问业务数据库和用户会话 |
| `job-events` | 事件持久化、outbox、Redis 分发、SSE 回放 | 作为业务真相源 |
| `presentation-editor` | 演示文稿 revision、稳定 slide ID、排序、文本修改、删除、单页重生成 | 自由画布 |
| `artifact-export` | 工件 manifest、PPTX 导出、QA、下载授权和保留期 | 永久公开 URL |
| `quota-provider` | 权益、用量预占/结算、Provider 调用和成本记录 | 商品支付流程 |
| `audit-observability` | 审计、trace、日志、指标、脱敏 | 保存源文档正文到日志 |

### 4.2 部署边界

```text
apps/
  web/                   # Next.js 产品 UI 与 BFF
services/
  api/                   # FastAPI 业务 API 与 SSE
  worker/                # Celery 任务、沙箱、Provider Gateway
packages/
  contracts/             # OpenAPI、JSON Schema、派生类型
vendor/
  ppt-master/            # 固定 tag/commit，完整保留许可证与 attribution
infra/
  compose/               # 本地 PostgreSQL/Redis/对象存储/扫描器
  deploy/                # 环境与发布配置
tests/
  contract/
  integration/
  e2e/
  golden/
```

Web 与 API 实例不得执行 PPT 生成。所有解析、渲染、编译和重型 QA 必须进入隔离 Worker。

## 5. 核心用户旅程

### 5.1 主题创建

1. 用户登录并进入个人工作区；
2. 在首页输入主题，选择内置模板；
3. “生成大纲”在主题非空时可用；
4. 系统创建草稿与初始意图版本；
5. AI 生成结构化意图、故事线和大纲 revision；
6. 用户编辑并批准大纲；
7. 系统展示生成确认摘要并创建不可变 snapshot；
8. 异步生成、QA、编译和发布；
9. 用户审核、轻编辑并导出 PPTX。

### 5.2 文档创建

1. 用户创建上传会话并将单个文件直传隔离区；
2. API 完成对象大小、MIME 和校验和复核；
3. 扫描通过后移入 clean 区；
4. Worker 解析为 Markdown、素材清单和 conversion profile；
5. 后续流程与主题创建一致；
6. 解析失败时允许替换文件或重试，不丢失草稿主题和配置。

### 5.3 失败恢复

1. 单页失败不得阻塞其他页面；
2. 任务结束为 `partially_succeeded`，失败槽位保留；
3. 用户可按稳定 `slideId` 重试、删除失败页或明确接受缺页；
4. 新 attempt 通过 QA 后才切换当前可用版本；
5. 默认禁止静默导出缺页结果。

### 5.4 刷新与离页恢复

1. 页面首先获取 PostgreSQL 中的 job snapshot；
2. 使用 snapshot 的最后事件序号订阅 SSE；
3. 服务端依据 `Last-Event-ID` 回放缺失事件，再衔接实时事件；
4. 重复事件按 `seq` 去重，客户端状态不得倒退；
5. Redis 丢失或重启不影响最终任务状态恢复。

## 6. 功能需求

### 6.1 身份、工作区与租户隔离

#### FR-ID-001 登录与 personal organization

- 用户必须登录后访问草稿、模板、任务、演示文稿和工件；
- 首次登录自动创建 personal organization；
- P1 不开放团队成员管理，但数据模型必须保留 `organizations`、`memberships`；
- 开发环境可使用显式本地测试身份，生产环境不得启用绕过开关。

#### FR-ID-002 授权

- 所有业务查询必须显式绑定 `organization_id`；
- 跨租户资源返回 `404`，避免枚举；
- 对象存储 key、下载签名、SSE 和后台任务都必须再次校验租户；
- 审计记录必须包含 actor、organization、resource、action、requestId 和结果。

#### 验收

- 两个测试组织不能通过猜 ID、对象 key、下载 URL 或 SSE job ID 访问对方数据；
- API、Worker 和对象存储集成测试覆盖跨租户拒绝；
- 退出登录后旧下载 URL 按策略失效或在过期前仍受短时签名边界约束，具体由 ADR 固定。

### 6.2 首页与草稿创建

#### FR-DRAFT-001 首页

- 显示品牌“即刻AI-PPT”和已确认口号；
- 支持主题输入、文档入口、内置模板筛选、历史入口和额度占位；
- 主 CTA 固定为“生成大纲”；
- 主题与主文档至少存在一个；
- 非 P1 功能不得呈现为可执行按钮，可隐藏或明确标注“即将支持”。

#### FR-DRAFT-002 草稿

- 草稿保存原始主题、sourceId、mode、templateVersionId 和当前 intent/outline 指针；
- 自动保存采用乐观锁；
- UI 展示“保存中 / 已保存 / 保存失败”；
- 保存失败不得清空本地输入，必须允许重试。

#### 验收

- 空主题且无主文档时 CTA 禁用；
- 创建成功返回稳定 draftId，并能刷新恢复；
- 相同 `Idempotency-Key` 重试不会创建第二个草稿；
- 历史项目按自身 ID 加载数据，不复用当前页面内存状态。

### 6.3 上传、扫描与解析

#### FR-SOURCE-001 上传会话

- 客户端通过 `POST /v1/upload-sessions` 获取短时预签名信息；
- 上传签名固定 method、key、大小范围、声明 MIME、checksum 与过期时间；
- 直传完成后调用 `:complete`，服务端必须 HEAD 并复核真实大小和 SHA-256；
- 用户文件名仅存元数据，不直接构成对象 key。

#### FR-SOURCE-002 安全流水线

- 状态必须区分 upload、scan 与 parse；
- 扩展名、声明 MIME、嗅探 MIME 和 magic bytes 不一致时隔离或拒绝；
- 仅 `scanStatus=clean` 的对象能进入解析 Worker；
- Office/ZIP 限制解压总大小、文件数、嵌套深度和压缩比；
- HTML 默认禁用脚本和外部资源抓取；
- 解析容器非 root、只读根文件系统、无宿主目录挂载，并限制 CPU、内存、临时盘和时间。

#### FR-SOURCE-003 解析工件

- 解析输出至少包含 Markdown、素材清单、conversion profile、解析器版本和 source hash；
- 工件不可变并写入对象存储；
- 解析失败保存稳定错误码、可重试性和用户可读说明。

#### 验收

- 覆盖合法文件、伪造 MIME、损坏/加密文档、病毒、ZIP bomb、路径穿越和超限文件；
- 网络重试不得创建重复 source 或重复扣费；
- 解析期间离页、刷新或 API 重启后状态可恢复；
- 前端不获得永久公开对象 URL。

### 6.4 创作意图

#### FR-INTENT-001 IntentSpec

IntentSpec 必须版本化，至少包含：

| 字段 | 类型 | 规则 |
|---|---|---|
| `title` | string | 必填，去除首尾空白 |
| `audience` | enum/string | 必填；允许标准项与自定义项 |
| `goal` | enum/string | 必填，如策略决策、经营复盘、培训、客户提案 |
| `targetSlideCount` | integer | P1 默认 12，范围见 12.2 |
| `language` | enum | `zh-CN`、`en-US`；P1 默认 `zh-CN` |
| `contentDepth` | enum | `conclusion_first`、`balanced`、`research` |
| `visualPreference` | enum | `data_first`、`photo_illustration`、`minimal_visual` |
| `notes` | string | 可选，受长度限制 |
| `sourceRefs` | array | 引用已 clean/parsed 的 source artifact |
| `schemaVersion` | integer | 必填 |

#### FR-INTENT-002 推断与编辑

- AI 输出必须通过 JSON Schema；
- Schema 不合法时自动修复次数受限，失败后允许手工填写；
- 人工或 AI 修改都创建不可变 revision；
- 页数改变时必须显式提示重新生成或调整大纲，不能静默不一致。

#### 验收

- 每次修改均有 revision ID、basedOnRevisionId、actor 和时间；
- 刷新恢复最新 revision；
- 并发冲突返回统一 `409/412`，不得覆盖他人版本；
- 语言字段在 UI、API 和 Worker 合同中一致存在。

### 6.5 故事线、大纲与批准

#### FR-OUTLINE-001 OutlineSpec

- 包含故事线摘要、目标页数和有序 outline slides；
- 每个 outline slide 使用稳定 `outlineSlideId`，不得把数组下标当身份；
- 每页至少包含 `type`、`title`、`body/keyPoints` 和可选 source citations；
- 支持编辑、增页、删除、移动、单页重写和整纲优化。

#### FR-OUTLINE-002 版本与撤销

- 每次人工或 AI 修改创建新 revision；
- 撤销/恢复通过切换或复制历史 revision 实现，不原地改写旧版本；
- 至少保留一页；首尾移动越界必须禁用；
- AI 助手不能只返回聊天文案，必须产生可比较的 revision 或明确失败。

#### FR-OUTLINE-003 批准与快照

- 用户批准明确的 outline revision；
- 生成前展示 intent、outline、mode、template version 和来源摘要；
- 创建 `generationSnapshot` 后，所有引用和配置不可变；
- 后续编辑创建新 revision，不影响已运行任务。

#### 验收

- 同时编辑同一基准 revision 时只有合法版本能提交；
- 删除后可从历史恢复，稳定 ID、顺序与内容一致；
- 运行任务的 snapshot hash 不因用户继续编辑草稿而改变；
- 生成监控显示真实 mode/template，不使用硬编码。

### 6.6 内置模板与模式

#### FR-TEMPLATE-001 内置模板

- 模板是不可变 version，包含名称、分类、主题 token、字体、页面角色、可编辑性说明和引擎兼容版本；
- 草稿保存 `templateVersionId`；
- 已被 snapshot 引用的模板版本不可删除或覆盖；
- 模板不可用时生成必须失败在排队前，并提供替代选择。

#### FR-MODE-001 原生专业

- P1 唯一可执行模式为 `native`；
- 优先输出原生可编辑文本、形状和支持范围内的图表；
- 不得将整页截图伪装为原生可编辑；
- 任何不可编辑元素必须在 QA 报告中标记。

#### 验收

- UI 只允许选择后端声明可用的模式；
- 任务记录 `modeId`、templateVersionId、engineVersion 和 schemaVersion；
- 模板升级不会改变历史 snapshot 和导出结果。

### 6.7 生成编排

#### FR-JOB-001 生成任务

- 创建任务必须引用 approved outline revision、intent revision、template version 和 mode；
- API 在同一事务创建 generation snapshot、job、初始事件和 outbox；
- 异步创建返回 `202`、jobId 与 `Location`；
- PostgreSQL 是任务与进度真相源。

#### FR-JOB-002 阶段

任务 `status` 与 `stage` 必须分离：

```text
status: queued → running → succeeded | partially_succeeded | failed
          └──────────┴→ cancel_requested → cancelled

stage: deck_planning → slide_generation → deck_qa → compiling
       → package_qa → publishing
```

单页：

```text
status: pending → running → ready | failed | cancelled
                    failed → retrying → running

stage: content_generation → rendering → qa
```

导出任务独立：

```text
queued → running → succeeded | failed | cancelled
```

Draft、source、generation job、presentation revision 和 export job 不得复用一个总状态字段。

终态判定必须固定为：

- `succeeded`：所有 required slide 均为 ready，且 package/publish 成功；
- `partially_succeeded`：至少一个 required slide ready，至少一个 required slide 在重试耗尽后 failed；
- `failed`：没有任何 required slide ready，或 deck/package/publish 发生不可恢复失败；
- `cancelled`：queued 或 running 状态下用户取消事务先于其他终态成功提交；
- `cancel_requested` 不是终态，queued 和 running 都允许进入；
- 仅 `succeeded` 与 `partially_succeeded` 创建 initial presentation revision；partial revision 必须保留失败槽位；
- `failed` 不创建 presentation；`cancelled` 可保留已发布的恢复工件，但不创建可导出的 presentation。

事件与状态映射：

| 事件 | 任务状态 |
|---|---|
| `job.queued` | `queued` |
| `job.started` | `running` |
| `job.cancel.requested` | `cancel_requested` |
| `job.completed` | `succeeded` |
| `job.partially_completed` | `partially_succeeded` |
| `job.failed` | `failed` |
| `job.cancelled` | `cancelled` |

#### FR-JOB-003 幂等与恢复

逻辑任务键为：

```text
organization_id + snapshot_id + stage + stable_slide_id(optional)
```

`attempt` 仅是执行元数据，不得进入逻辑幂等键。

- API 幂等记录绑定 organization、actor、route、key 和 request hash；
- 相同 key/相同 body 返回首次响应；相同 key/不同 body 返回 `409 idempotency_key_reused`；
- Worker 输出先写 immutable 临时 key，QA 通过后原子发布 manifest；
- Worker 崩溃重投不得发布第二份当前工件或重复结算用量；
- 两个 Worker 竞争同一步骤时只有持有合法 lease/version 的一方能提交。

#### FR-JOB-004 取消

- 取消流程为 `running → cancel_requested → cancelled`；
- Worker 在页面/阶段安全边界检查取消标志；
- 强杀只作为失控兜底；
- 已进入终态后取消是幂等 no-op；
- cancel 与 publish 竞争时，以数据库中第一个合法终态事务为准。

#### FR-JOB-005 Agent 创作与显式降级

- `default-agentic` 必须由同一 Main Presentation Agent 完成 Strategist→Executor 顺序创作；每页 SVG 必须能追溯到真实模型 turn、工具调用、观察与终止原因。
- Supervisor 强制 turn/token/cost/soft-hard timeout/tool allowlist/最多 5 次阶段尝试；恢复不得重复计费、双写或发布旧 hash。
- 正式 Agent 成功结果必须通过最多两轮多模态视觉审阅；二轮仍有 blocking 则进入 `needs_manual` 且不发布完整结果。
- `deterministic-template` 不得请求文本 Provider、不得写 Agent 作者 receipt，且必须在用户界面、清单、SSE/job snapshot、下载提示和文件名显式披露。
- 安全、跨租户、来源支持、取消/恢复、PowerPoint/WPS 兼容或发布一致性失败会触发 canary 回退；单纯视觉偏好下降进入人工复核，不覆盖已批准 revision。

#### 验收

- Worker kill、重复投递、API 超时重试和并发提交均不产生重复任务、工件或扣费；
- Redis 重启后可从 PostgreSQL 恢复；
- 单页失败不阻塞其余页，最终状态为 `partially_succeeded`；
- 输入错误不自动无限重试，可重试错误采用指数退避并受最大次数限制；
- 取消后临时工件不作为正式结果，已发布且通过 QA 的页面可保留。

### 6.8 事件与 SSE

#### FR-EVENT-001 事件 envelope

```json
{
  "eventId": "01...",
  "jobId": "01...",
  "seq": 42,
  "type": "slide.ready",
  "schemaVersion": 1,
  "occurredAt": "2026-08-15T12:00:00Z",
  "snapshotId": "01...",
  "slideId": "01...",
  "attempt": 2,
  "stage": "slideQa",
  "status": "ready",
  "progress": { "completed": 6, "total": 10 },
  "data": {},
  "traceId": "..."
}
```

P1 事件类型至少包含：

- `job.queued`、`job.started`、`job.stage.changed`；
- `job.cancel.requested`、`job.cancelled`；
- `job.completed`、`job.partially_completed`、`job.failed`；
- `slide.started`、`slide.stage.changed`、`slide.ready`、`slide.failed`、`slide.retrying`；
- `qa.completed`、`artifact.published`。

#### FR-EVENT-002 传输与回放

- 每个 job 的 `seq` 单调递增且唯一；
- 业务状态、job event 与 outbox 在同一事务提交；
- SSE 支持 `Last-Event-ID`，先读取 snapshot，再回放 DB 事件并衔接 Redis 实时流；
- 15–30 秒发送 heartbeat，heartbeat 不占业务 seq；
- 事件超出保留窗口时返回明确 reset/snapshot 语义；
- 慢客户端必须有连接数与发送缓冲上限。

#### 验收

- 浏览器刷新、休眠、代理断连和重复连接后无状态倒退、重复副作用或事件遗漏；
- Redis 清空后历史事件仍可从数据库回放；
- 用户只能订阅自己组织的 job；
- 终态事件后连接可以关闭，重连仍能取得终态 snapshot。

### 6.9 结果预览、轻编辑与重生成

#### FR-PRES-001 Presentation Revision

- 首次成功发布创建 presentation 与不可变 revision；
- 页面使用稳定 `slideId`，排序变化不改变身份；
- 文本修改、排序、删除形成新 presentation revision；
- 编辑结果不得反向覆盖 approved outline 或 generation snapshot；
- 至少保留一页。

#### FR-PRES-002 单页重生成

- 重试/重生成接口使用 `slideId`，不得使用会随排序变化的 `{n}`；
- 新版本 QA 通过前，旧 ready 版本继续可见；
- 成功后产生新的 slide version，由 presentation revision 显式引用；
- 失败页必须显示占位、错误和可操作动作，不得伪装 ready。

#### FR-PRES-003 Partial 守卫

- `partially_succeeded` 结果保留失败槽位；
- 导出前用户必须完成以下之一：重试成功、删除失败页、或显式接受缺页；
- 接受缺页必须写审计事件并在导出 QA 报告中说明。

#### 验收

- 排序后按 slideId 重试的是正确页面；
- 刷新恢复相同 presentation revision；
- 两个并发编辑基于同一 revision 时产生冲突，不静默覆盖；
- 删除、修改和重生成均可追溯到 actor、基准 revision 和操作集合。

### 6.10 导出与下载

#### FR-EXPORT-001 导出任务

- 导出必须显式引用 presentationRevisionId；
- 导出包含 compile、package QA、publish 三步；
- QA 至少检查包结构、页数、关系、媒体引用、可打开性和预览生成；
- 成功工件使用不可变 key，并记录 SHA-256、MIME、大小、engine/schema/font 版本和 snapshot/revision ID。

生成与导出工件必须区分：

| 工件类型 | 生产阶段 | 内容与用途 | 幂等绑定 |
|---|---|---|---|
| `generation_source_bundle` | G06 generation publish | 每页 canonical SVG、预览、QA、sidecar、失败槽位和 generation manifest | generationSnapshotId + engine/schema version |
| `generation_baseline_pptx` | G06 package QA | 未经结果编辑的基线 PPTX，仅用于兼容验证和初始结果下载候选 | generationJobId + baseline revision |
| `presentation_revision_manifest` | G07 编辑 | 当前顺序、删除标记、文本覆盖和 slideVersion 引用 | presentationRevisionId |
| `export_pptx` | G07 export job | 将明确 presentation revision 重新编译/打包后的用户下载文件 | presentationRevisionId + export options + compiler version |

若 presentation revision 与 baseline 完全相同，导出服务可以复用已验证字节，但仍必须创建独立 ExportManifest，记录复用来源和权限/保留期。

#### FR-EXPORT-002 下载

- Bucket 全部 private，禁止 public ACL；
- 下载 URL 短时有效并重新校验租户权限；
- URL 过期后可以为同一 artifact 重新签发；
- 敏感预览不得进入公共 CDN 缓存。

#### 验收

- 导出的 PPTX 在约定版本 PowerPoint 与 WPS 中打开且无修复提示；
- 标题、正文与约定形状在原生专业模式下可编辑；
- 导出期间继续编辑不会改变该 export 绑定的 revision；
- DB 成功/对象发布失败与对象成功/DB 失败均由 reconciliation job 修复或告警。

### 6.11 历史与恢复

#### FR-HISTORY-001 历史列表

- 展示草稿、解析中、生成中、需处理、失败和已完成项目；
- 显示更新时间、页数、模式、模板与失败摘要；
- 使用 cursor pagination；
- 提供加载、空、失败和重试状态。

#### FR-HISTORY-002 路由恢复

- 草稿恢复工作台；
- 解析中恢复 source 状态；
- 生成中恢复监控；
- 部分成功/失败恢复处理页；
- 已完成恢复结果 revision。

#### FR-HISTORY-003 项目删除与数据导出

- 用户可以请求导出单个项目的结构化元数据、版本记录和工件清单；
- 用户可以删除自己组织内的项目；API 先软删除并撤销后续访问，再由异步清理任务删除对象和派生数据；
- 删除必须覆盖 source、临时/已发布工件、事件、索引和可控 Provider 缓存，并产生可审计清理结果；
- 正在运行的项目必须先进入取消/删除编排，不得留下继续写入的孤儿任务。

#### 验收

- 打开历史项按 ID 加载真实持久数据；
- 离开页面不停止任务；
- 删除或无权限项目不能通过旧路由恢复；
- 项目删除后 API、SSE、旧下载 URL 与对象 key 都不能继续访问；
- 数据导出绑定明确项目快照，且只能由有权用户下载；
- UI 状态词典与 API 状态映射有单一实现，不散落硬编码。

### 6.12 配额与用量

#### FR-QUOTA-001

- P1 不实现支付，但必须有 `entitlements`、`usage_reservations`、`usage_ledger`；
- 创建生成任务前在组织级锁内预占预计页数、图片数、图片费用/Worker 资源；
- 终态按实际消耗结算，取消释放未使用预占；
- 相同幂等任务不得重复预占或结算；
- 用量记录页数、模型 token/微单位费用、图片次数（当前每稿 0 或 1）、图片微单位费用、Worker 秒数和导出次数。
- Agent 按每页/整套记录 turn、token、cost、耗时、工具失败与修复次数；fallback 单独记录并不占用 Agent 成功分母。

#### 验收

- 额度不足在排队前返回明确错误；
- Worker 重试不重复计费；
- 取消和 partial 的结算可审计；
- 前端展示的额度来自 API，不使用原型硬编码数字。

## 7. API 合同

### 7.1 通用规则

- 前缀 `/v1`；JSON 命名在 Goal 0 统一，默认 `camelCase`；
- 写接口接受 `Idempotency-Key`；
- 可变资源更新接受 `If-Match` 或明确 base revision；
- 异步操作返回 `202 Accepted`、资源 ID 与 `Location`；
- 错误使用 RFC 7807，并扩展 `code`、`retryable`、`requestId`、`fieldErrors`；
- 所有列表使用 cursor pagination；
- 跨租户资源统一返回 `404`；
- OpenAPI 是 HTTP 合同真相源，前端与客户端类型由合同生成。
- job snapshot/SSE completion data 必须提供 `engineProfile`、`authoringMode`、`authoringDisclosure` 和可选 `fallbackReason`，且该信息来自冻结 snapshot 而非前端推断。

### 7.2 P1 端点基线

```text
POST   /v1/drafts
GET    /v1/drafts/{draftId}
PATCH  /v1/drafts/{draftId}
DELETE /v1/drafts/{draftId}
POST   /v1/drafts/{draftId}:export-data
GET    /v1/data-exports/{dataExportId}

POST   /v1/upload-sessions
POST   /v1/upload-sessions/{uploadSessionId}:complete
POST   /v1/drafts/{draftId}/sources
GET    /v1/sources/{sourceId}
POST   /v1/sources/{sourceId}:retry-parse

POST   /v1/drafts/{draftId}/intent:infer
POST   /v1/drafts/{draftId}/intent-revisions
GET    /v1/drafts/{draftId}/intent-revisions
GET    /v1/intent-revisions/{intentRevisionId}
POST   /v1/drafts/{draftId}/outline:generate
POST   /v1/drafts/{draftId}/outline-revisions
GET    /v1/drafts/{draftId}/outline-revisions
GET    /v1/outline-revisions/{outlineRevisionId}
POST   /v1/outline-revisions/{outlineRevisionId}:approve

GET    /v1/templates
GET    /v1/templates/{templateId}/versions/{templateVersionId}

POST   /v1/drafts/{draftId}/generation-jobs
GET    /v1/jobs/{jobId}
GET    /v1/jobs/{jobId}/events
POST   /v1/jobs/{jobId}:cancel
POST   /v1/jobs/{jobId}/slides/{slideId}:retry

GET    /v1/presentations/{presentationId}
POST   /v1/presentations/{presentationId}/revisions
GET    /v1/presentations/{presentationId}/revisions
GET    /v1/presentations/{presentationId}/revisions/{presentationRevisionId}
POST   /v1/presentations/{presentationId}/slides/{slideId}:regenerate
POST   /v1/presentations/{presentationId}/exports
GET    /v1/exports/{exportId}
POST   /v1/artifacts/{artifactId}:authorize-download

GET    /v1/history
GET    /v1/me/entitlements
GET    /v1/me/usage
```

具体 request/response 必须在 `packages/contracts/openapi.yaml` 与 JSON Schema 中定义；本节不替代机器可读合同。

### 7.3 必备机器可读 Schema

G00 至少必须为以下对象建立有正反 fixtures 的版本化 Schema：

- `SourcePackage`、`SourceArtifact`；
- `IntentSpec`、`OutlineSpec`；
- `ThemeSpec`、`TemplateBinding`；
- `GenerationSnapshot`；
- `DeckPlan`、`SlidePlan`；
- `JobEvent`、`ProblemDetails`；
- `QaReport`、`ArtifactManifest`；
- `PresentationRevision`、`ExportManifest`。

## 8. 数据模型与不变量

### 8.1 通用字段

- 主键使用 UUIDv7 或 ULID，Goal 0 通过 ADR 统一；
- 业务表包含 `organization_id`、`created_at`、`updated_at`；
- 可变聚合包含 `lock_version`；
- 用户可见资源采用 `deleted_at` 软删除，对象清理由异步任务执行；
- 所有时间为 UTC，API 使用 ISO 8601。

### 8.2 核心表

```text
users, organizations, memberships
drafts
upload_sessions, sources, source_artifacts
intent_revisions, outline_revisions, outline_slides
templates, template_versions, template_layouts
generation_snapshots, generation_jobs, generation_job_slides
job_events, outbox_events, idempotency_records
presentations, presentation_revisions, slide_versions
artifacts, export_jobs
entitlements, usage_reservations, usage_ledger
provider_calls, audit_logs
```

### 8.3 关键不变量

1. `intent_revisions`、`outline_revisions`、`template_versions`、`generation_snapshots` 与已发布 artifacts 不可变；
2. `generation_snapshot` 固定 source hash、intent/outline/template 版本、模式、prompt/schema/engine/container/font/provider 配置版本；
3. `outlineSlideId` 和 `slideId` 稳定，不因排序变化；
4. `job_events(job_id, seq)` 唯一且只追加；
5. 业务状态、事件与 outbox 在同一事务提交；
6. 对象表只存 key、hash、MIME、大小、状态和保留期，不存永久公开 URL；
7. `idempotency_records` 唯一键为 organization + actor + route + key；
8. 导出绑定明确 presentation revision，不使用隐式“最新版本”；
9. Redis 丢失不能改变业务终态；
10. 任何跨租户查询和对象访问必须失败。

## 9. UI、响应式与无障碍

### 9.1 信息架构

P1 必须包含：

1. 首页；
2. Source 上传/解析状态；
3. 意图与大纲工作台；
4. 生成前确认摘要；
5. 生成监控；
6. 结果预览与轻编辑；
7. 历史列表/抽屉；
8. 登录与通用错误/空状态。

私有模板上传弹窗由 P1.1 feature flag 控制。

### 9.2 响应式

- `>=1200px`：约 70/30 双栏工作台；
- `768–1199px`：AI 助手为可操作抽屉，模板与幻灯片两列；
- `<768px`：单栏，步骤横向滚动，模板/幻灯片单列；
- 浏览器缩放 200% 时核心流程仍可操作；
- 触控目标最小 44×44 CSS px。

### 9.3 无障碍

- 满足 WCAG 2.1 AA 基线；
- 所有控件使用语义 HTML、可见焦点和关联 label；
- 状态不只靠颜色表达；
- 进度使用 `role=progressbar` 和正确数值；
- 低频状态摘要使用 `aria-live=polite`，紧急错误按需使用 assertive；
- 模态必须焦点锁定、Esc 关闭、关闭后焦点归位，并对未保存退出二次确认；
- 支持键盘完成创建、编辑、生成、重试和导出主流程；
- 尊重 `prefers-reduced-motion`。

### 9.4 关键文案语义

- 首页主 CTA：“生成大纲”；
- 生成任务：“取消任务 / 取消请求中”，不使用“暂停”；
- 结果标注：“AI 生成的可编辑初稿，请核验事实、数据、图表与图片”；
- Partial：“部分页面需要处理”，不得用成功色掩盖失败；
- 下载链接过期：“链接已过期，重新生成下载链接”。

## 10. 安全、隐私与许可证

### 10.1 上传与执行安全

- quarantine、clean、tmp、published 分区；
- Worker 只读 clean source，只能写自己 job 的 tmp 前缀；
- 拒绝绝对路径、`..`、symlink、危险外部关系和非允许协议；
- 文档内容视为不可信数据，不能因为文档内指令执行工具、文件或网络命令；
- Provider key 不进入前端、prompt、日志或工件；
- 日志不记录源文档正文、认证头和完整预签名 URL；
- Cookie 鉴权需 SameSite、CSRF 与 CORS allowlist；JWT/OIDC 实现需记录 ADR；
- 下载接口重新授权，不仅依赖对象 key 保密。

### 10.2 数据治理

- 明示数据会流向哪些 LLM/Provider；
- 源文件、聊天、临时工件、日志和事件分别配置保留期；
- 支持项目级删除和数据导出；
- 删除任务可验证清理对象、临时文件、索引和 Provider 缓存；
- 对象存储服务端加密，并配置生命周期与残留分片清理。

### 10.3 许可证 Gate

- 完整保留 `ppt-master` MIT LICENSE、copyright、SPONSORS 与 attribution guard 所需文件；
- 不绕过上游 attribution 检查；
- PyMuPDF 必须有商业许可或被批准的替代实现；
- EPUB 在 EbookLib/替代方案完成许可评审前禁用；
- 字体、图标、模板、网页图片和 Provider 输出保留来源、许可和使用范围；
- P0 产出 SBOM、依赖锁和镜像/工件版本记录。

## 11. 可观测性与错误模型

### 11.1 关联标识

日志、trace、指标和审计必须能关联：

```text
request_id
organization_id
draft_id
source_id
snapshot_id
job_id
slide_id
export_id
provider_call_id
trace_id
```

### 11.2 稳定错误分类

错误至少分为：

- `validation_error`：用户输入或 Schema 错误，不自动重试；
- `authorization_error`：无权限，跨租户对外统一 404；
- `quota_exceeded`：排队前阻断；
- `unsafe_file`：病毒、伪造类型、压缩炸弹等；
- `parse_failed`：损坏/加密/不兼容文件；
- `provider_rate_limited`、`provider_timeout`：可重试；
- `engine_contract_failed`：输入/输出合同不匹配；
- `slide_render_failed`、`slide_qa_failed`；
- `compile_failed`、`package_qa_failed`；
- `cancelled_by_user`；
- `internal_error`：隐藏敏感细节并带 requestId。

### 11.3 必备指标

- 请求量、错误率与 p50/p95/p99 延迟；
- 上传、扫描、解析成功率与耗时；
- 排队延迟、首张预览时间、整套生成时间；
- 每阶段/每页失败率和重试率；
- SSE 活跃连接、重连、回放和丢弃；
- Worker 运行数、队列深度、崩溃和超时；
- Provider token/调用/成本与限流；
- Agent/fallback 整套数、Strategist/Executor/review/repair turn 与耗时、input/output token、cost、allowlisted tool 成败、逐页写入和修复次数；
- Agent canary 终态失败率、`needs_manual` 和模板 fallback 率，标签不得包含租户、页面 ID、prompt 或文件名；
- PPTX 包 QA、打开成功率和用户重生成率；
- 跨租户拒绝、安全扫描和审计异常。

## 12. 非功能要求

### 12.1 性能与可靠性

| 指标 | P1 目标/门禁 |
|---|---|
| 普通 JSON GET p95 | <= 300 ms（同区域、非外部 Provider） |
| 普通 JSON 写请求 p95 | <= 500 ms（不含异步任务） |
| 自动保存 | 800 ms 左右 debounce，网络正常时 2 s 内持久化并反馈 |
| 任务状态传播 | DB 提交后 2 s 内到达在线客户端 p95 |
| SSE heartbeat | 默认 20 s，可配置 |
| 生成总时长 | P0/P1 只记录分阶段 SLI，不承诺“5–8 分钟”统一 SLA |
| API 幂等记录保留 | 默认 7 天 |
| job event 回放窗口 | 默认 7 天 |
| 临时工件保留 | 默认 24 小时 |
| 下载 URL | 默认 15 分钟 |
| 自动重试 | 每个可重试阶段最多 2 次，指数退避 |
| personal organization 并发生成 | 默认 1 个，配置化 |

### 12.2 产品限制默认值

| 配置 | P1 默认值 |
|---|---|
| 主文档大小 | 50 MiB |
| 私有模板大小（P1.1） | 50 MiB |
| 生成页数 | 4–30 页 |
| 默认页数 | 12 页 |
| Source 解析硬超时 | 10 分钟 |
| Generation 硬超时 | 30 分钟 |
| Export 硬超时 | 10 分钟 |

所有数值必须集中配置，不得散落为前后端魔法常量。P0 性能数据可通过 ADR 调整。

### 12.3 P0 金样本门槛

- 10/10 金样本在目标 PowerPoint 与 WPS 版本中打开且无修复提示；
- 标题和正文文本在原生专业模式下 100% 可编辑；
- 关键页面无裁切、越界、缺字和不可解释的整页位图回退；
- 自动 package QA 100% 通过；
- 视觉回归无 Sev-1，Sev-2 必须有已接受基线和原因；
- Worker kill 后可恢复，重复投递不重复发布；
- Redis 重启和 SSE 重连测试通过；
- 恶意样本不能进入 clean 或解析阶段。

### 12.4 验证证据协议

为避免“通过”无法复现，P1 默认使用以下证据协议；需要调整时通过 ADR：

#### 性能基线

- 使用与生产相同的构建模式，不使用开发热重载；
- 数据库预置至少 100 个 organizations、1,000 个 drafts、10,000 个 job events 和 1,000 个 artifacts；
- 普通 API 延迟测试使用 20 个并发虚拟用户，预热 2 分钟，连续测量 10 分钟；
- 同步 API 测试不包含外部 Provider 时间，Provider/生成阶段分别记录 SLI；
- 报告包含硬件/容器资源、镜像 digest、数据库版本、样本量、错误率与 p50/p95/p99；
- 结果必须保存到 `docs/evidence/performance/`。

#### 恢复与竞态

- Worker kill、Redis restart、SSE reconnect、cancel/publish race 和对象 reconciliation 各连续运行 10 次；
- 10 次均满足状态、事件、工件和用量不变量才算通过；
- 随机种子、故障注入点和每次结果保存到 `docs/evidence/recovery/`。

#### 无障碍

- 对核心页面运行 axe 自动检查，不能存在未豁免 critical/serious 问题；
- 使用键盘完成 E2E-001、E2E-006、E2E-009；
- 在目标 Chromium 浏览器和 200% zoom 下验证 390/768/1440px 布局；
- 至少使用一种 Windows 屏幕阅读器（默认 NVDA）人工完成登录后主流程的关键步骤；
- 人工检查记录检查人、日期、浏览器/辅助技术精确版本和问题结果。

#### 严重级别与依赖风险

- Sev-1：跨租户、任意代码/文件执行、不可恢复数据损坏、密钥泄露或主链路全量不可用；不得豁免；
- Sev-2：主流程稳定失败、PPTX 需修复、关键内容不可编辑/裁切或恢复机制失效；仅限期 ADR 可豁免；
- CVSS >= 7.0 或 High/Critical 依赖风险必须修复、证明不可达或有负责人/到期日/补偿措施的 ADR；
- 证据清单必须列出每项 required check 的状态、命令或人工报告、负责人和时间。

## 13. 测试与验收

### 13.1 测试层级

1. **Contract**：OpenAPI、JSON Schema、事件 fixtures、错误码；
2. **Unit**：领域规则、状态机、幂等、权限、版本操作；
3. **Integration**：PostgreSQL、Redis、对象存储、扫描器、Celery、Provider fake；
4. **Golden**：parse → plan → SVG → QA → PPTX；
5. **E2E**：浏览器完整用户旅程；
6. **Security**：恶意上传、跨租户、SSRF（若未来开启）、日志脱敏；
7. **Compatibility**：PowerPoint/WPS 实机打开与截图回归；
8. **Recovery**：Worker kill、Redis restart、SSE reconnect、对象/DB reconciliation。

### 13.2 P1 关键场景

| ID | 场景 | 预期结果 |
|---|---|---|
| E2E-001 | 主题 → 意图 → 大纲 → 生成 → 导出 | 获得绑定明确 revision 的可打开 PPTX |
| E2E-002 | DOCX/PDF/PPTX/HTML 上传 | clean 后解析，失败有稳定错误和恢复动作 |
| E2E-003 | 大纲编辑与批准后继续修改 | 运行 snapshot 不变，新修改形成新 revision |
| E2E-004 | Worker 在单页渲染后崩溃 | 任务恢复且不重复发布/扣费 |
| E2E-005 | Redis 重启 + SSE 重连 | PostgreSQL snapshot + seq 回放恢复完整状态 |
| E2E-006 | 单页失败 | 其他页继续，任务 partial，按 slideId 重试正确页面 |
| E2E-007 | 取消与 publish 竞态 | 仅一个合法终态，无半发布工件 |
| E2E-008 | 结果排序后重生成 | slideId 稳定，旧版本在新版本通过前可见 |
| E2E-009 | Partial 导出 | 默认被守卫；处理或明确接受后才可导出 |
| E2E-010 | 跨租户访问 | API、SSE、对象和下载均拒绝且不泄露存在性 |
| E2E-011 | 移动端与键盘 | 390px、768px、1440px 和键盘主流程可完成 |
| E2E-012 | 历史恢复 | 草稿、运行中、partial、完成分别回到正确状态 |

### 13.3 Release Gate

P1 发布前必须具备：

- 全套 lint、typecheck、unit、contract、integration、golden 与 E2E 通过；
- 无未接受的 Sev-1/Sev-2 安全与数据隔离缺陷；
- PDF 许可证/替代栈决策已签字；
- SBOM、依赖锁、镜像 digest 和上游 attribution 完整；
- PowerPoint/WPS 实机兼容报告；
- 备份恢复、队列恢复、对象 reconciliation 与回滚演练记录；
- 生产 Provider、数据保留和隐私披露完成；
- 监控、告警、值班/故障处理和降级说明可用。

## 14. P1 Definition of Done

只有同时满足以下条件，才可将 P1 标记为完成：

1. E2E-001 至 E2E-012 全部通过；
2. P0 金样本和许可证 Gate 通过；
3. 用户可从真实持久数据完成闭环，不依赖本地计时器、硬编码历史或假 Toast；
4. 生成任务刷新可恢复，单页失败可处理，取消语义一致；
5. 生成、编辑和导出都绑定明确不可变版本；
6. 跨租户、上传安全、日志脱敏和短时下载通过验证；
7. 响应式与 WCAG 2.1 AA 基线通过自动和人工检查；
8. `docs/release-gate-report.md` 已记录全部发布门禁证据、人工兼容检查结果与审批状态；
9. 所有偏离本 SPEC 的实现都有批准 ADR、风险说明和替代验证证据。

## 15. P1.1 可选：私有模板上传

P1 Core 通过后才可启动。范围包括：

- 仅 PPTX 上传、扫描和解析；
- 真实预览；
- 封面、目录、章节、正文、结束五类角色识别；
- 用户可修正、忽略和确认映射；
- 字体、尺寸、可编辑性和兼容性报告；
- 保存不可变 template version 并绑定草稿；
- 缺失角色使用明确默认回退，不静默填充；
- 未保存关闭二次确认与完整模态无障碍。

P1.1 不包含公开市场、组织治理、旧 `.ppt` 转换和任意模板“百分百兼容”承诺。

## 16. P0 ADR 记录

以下事项不阻塞本 SPEC 成文，但必须在对应 Goal 的暂停点前形成 ADR：

1. ADR-001：主键 UUIDv7 或 ULID；
2. ADR-002：生产身份提供方与 Web/API 令牌交换；
3. ADR-003：PDF 商业许可或替代解析栈；
4. ADR-004：固定 `ppt-master` commit、vendor 方式与升级流程；
5. ADR-005：已接受 Kimi `kimi-k3`、OpenAI `gpt-image-2`与选定网关的服务端策略；记录明确图片授权、Needs-Manual、最小化 prompt、配额/费用、隐私披露和未独立验证的网关/上游风险接受；
6. ADR-006：对象存储、扫描器和环境拓扑；
7. ADR-007：数据保留、删除与下载 URL 策略；
8. ADR-008：PowerPoint/WPS 目标版本与视觉回归门槛；
9. ADR-009：P1.1 私有模板是否进入首轮公开测试。
10. ADR-012：Main Presentation Agent 创作证据、多模态审阅、显式 `deterministic-template` fallback 与 snapshot-safe feature flag。
