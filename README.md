# 即刻AI-PPT

即刻AI-PPT 是一个“先确认意图与大纲，再异步生成可编辑原生 PPTX”的多租户产品。用户可以从一句主题或一份文档开始，在网页中确认生成意图和逐页大纲，再由可恢复的 Main Presentation Agent 完成页面创作、视觉复核、修复、编译和发布。

当前 G00–G08、ISSUE-002 与 ISSUE-003 已完成并归档。默认演示创作模式是具备真实模型回合和工具调用证据的 `agent-authoring`；`deterministic-template` 仅作为显式、可识别的受限回退模式。规范合同、执行计划和持续状态分别见 [SPEC](SPEC.md)、[PLAN](PLAN.md) 与 [PROGRESS](PROGRESS.md)。

## 用户操作步骤

### 1. 创建项目

打开 `http://localhost:3000`。默认本地开发环境使用开发用户登录；生产环境应接入 OIDC。

用户可以选择两种入口：

- **从主题创建**：输入目标，例如“根据 GPT-5.6 的官方公告做一份 6 页的 PPT”，选择模板并生成大纲。
- **从文档创建**：上传 DOCX、PDF、PPTX 或 HTML。文件先进入隔离区，经过类型、大小、校验和与病毒扫描后再解析；文档中的提示性文字只作为不可信内容处理，不会覆盖系统指令。

### 2. 确认意图与大纲

系统会生成标题、受众、目标页数、语言、内容深度、视觉偏好和故事线。用户应：

1. 检查并修改生成意图。
2. 调整逐页标题、页面目的和核心要点。
3. 批准当前版本的大纲。

批准后会生成不可变的 `GenerationSnapshot`，冻结来源版本、模板版本、模型/作者策略、图片范围和视觉复核策略。后续环境变量变更不会悄悄改变正在运行的任务。

### 3. 生成并观察进度

点击生成后，任务在后台异步运行。浏览器通过 SSE 显示规划、逐页创作、检查、视觉复核、修复、编译和发布进度。可以离开页面或刷新；恢复时系统从 PostgreSQL 重建任务状态，并从最后一个事件序号继续回放。

默认图片范围为“无”。如管理员已经启用图片能力，用户仍需在批准页显式选择“仅封面”或指定页面；只设置服务端环境变量不会自动发送图片生成请求。

### 4. 处理失败或部分结果

每页都有稳定的 `slideId` 和独立检查点。单页失败不会覆盖其他已完成页面；界面会保留失败槽位，并提供重试、删除或接受缺页等明确操作。存在阻断性视觉问题或未确认的部分成功时，系统不会静默发布完整成品。

### 5. 编辑、版本化与导出

生成完成后，可在网页中修改文本、调整顺序、删除页面，或按 `slideId` 重新生成单页。每次修改都会创建新的不可变 `PresentationRevision`，旧版本仍可追溯。

导出时必须选择具体版本。服务端会重新执行编译与包级 QA，发布可编辑的原生 PPTX，并返回短时有效的私有下载链接。用户还可以从历史项目继续工作，或导出/删除自己的项目数据。

## 本地快速启动

### 环境要求

仓库固定的开发基线为：

- Node.js 24.18.1、pnpm 11.19.0
- Python 3.12.4、uv 0.12.5
- Docker Engine 29.5.2、Docker Compose 5.1.4

详细的 Windows/Linux 说明见 [开发文档](docs/development.md)。

### 1. 安装依赖并准备配置

```powershell
corepack enable
corepack prepare pnpm@11.19.0 --activate
pnpm install --frozen-lockfile
python -m pip install uv==0.12.5
python -m uv sync --frozen
Copy-Item .env.example .env
```

在未纳入 Git 的 `.env` 或 Secret Manager 中设置 Provider 密钥。不要把 API Key、源文档正文、预签名 URL 或完整 Provider 请求写入仓库和日志。校验 Compose 配置时使用 `docker compose config --quiet`，避免在终端展开秘密值。

### 2. 启动基础设施与运行时

```powershell
docker compose up -d postgres redis minio clamav
python -m uv run --package instant-ppt-api alembic -c packages/domain/src/instant_ppt_domain/alembic.ini upgrade head
docker compose --profile runtime up -d --build
```

`runtime` profile 会启动 `api`、普通 `worker`、`agent-worker`、私有 `provider-gateway` 和事务型 `outbox`。首次构建完成后可去掉 `--build`。

### 3. 启动 Web

```powershell
pnpm --filter @instant-ppt/web dev
```

访问 `http://localhost:3000`，不要改用 `127.0.0.1:3000`，后者不在默认 CORS 白名单。API 默认监听 `http://localhost:8000`；可用以下命令检查运行状态：

```powershell
Invoke-WebRequest http://localhost:8000/readyz
docker compose --profile runtime ps
```

停止本地服务但保留数据卷：

```powershell
docker compose --profile runtime down
```

## Provider 与作者模式

当前 `.env.example` 的默认文本规划与创作 Provider 为 Qwen，默认模型为 `qwen3.8-flash`。Kimi 仍是可配置的替代文本 Provider；OpenAI GPT Image 2 仅用于受控图片任务，且默认关闭。

```dotenv
PLANNING_BACKEND=qwen
TEXT_PROVIDER=qwen
QWEN_MODEL=qwen3.8-flash
QWEN_REASONING_EFFORT=medium
QWEN_ENABLE_THINKING=true
QWEN_PRESERVE_THINKING=false
PRESENTATION_AUTHORING_MODE=agent-authoring
PRESENTATION_VISUAL_REVIEW_REQUIRED=true
PRESENTATION_NATIVE_CHARTS_ENABLED=false
IMAGE_GENERATION_ENABLED=false
IMAGE_MAX_PER_DECK=0
```

真实 Qwen 运行需要通过秘密注入提供 `QWEN_API_KEY`。公开 API 只持有内部 `PROVIDER_GATEWAY_TOKEN`；外部 Provider 密钥只存在于私有 Gateway 或明确授权的图片任务进程中。

若只需无外部模型的本地回归，可保留 `TEXT_PROVIDER=qwen`，并显式设置 `PLANNING_BACKEND=fake` 和 `PRESENTATION_AUTHORING_MODE=deterministic-template`。Fake 规划与模板作者均不会调用外部文本 Provider；该模式的 UI、事件、Manifest 与下载文件名都会标明“模板化受限初稿”，其结果不计为 Agent 生成。

## 技术栈

| 层级         | 当前实现                                                                               |
| ------------ | -------------------------------------------------------------------------------------- |
| Web / BFF    | Next.js 16.2.11 App Router、React 19.2.8、TypeScript 6.0.3                             |
| API          | FastAPI 0.141.1、Pydantic 2.13.4、Uvicorn 0.41.0                                       |
| 领域与持久化 | PostgreSQL 17.6、SQLAlchemy 2.0.52、Alembic 1.19.1、psycopg 3.3.4                      |
| 异步任务     | Celery 5.6.3、Redis 7.4.2、事务型 Outbox、SSE 事件回放                                 |
| 对象与安全   | MinIO/S3 私有对象存储、ClamAV 1.4.3、短期签名下载 URL                                  |
| PPT 引擎     | 仓库内置 `ppt-master` 适配器、SVG/Scene Graph、`python-pptx`、Pillow、PDF/字体渲染工具 |
| 合同         | OpenAPI、JSON Schema、AJV、`openapi-typescript`、版本化 fixtures 与状态机              |
| 可观测性     | OpenTelemetry、Prometheus 指标、结构化事件与审计记录                                   |
| 工程工具     | pnpm workspace、uv workspace、pytest、Ruff、ESLint、TypeScript、Docker Compose         |

## 系统架构

```text
浏览器
  │
  ▼
Next.js Web/BFF ──► FastAPI ──► PostgreSQL + Outbox
                         │               │
                         │               ▼
                         │          Redis / Celery
                         │           ├─ worker
                         │           └─ agent-worker
                         │                  │
                         │                  ▼
                         └────────── Provider Gateway
                                            │
                                            ▼
                               SVG / PPTX / QA / MinIO
```

主要边界如下：

- `apps/web` 只负责用户界面与 BFF，不解析源文档，也不执行 PPT 生成。
- `services/api` 负责认证、租户隔离、领域 API、任务状态和 SSE，不运行重型渲染。
- `services/worker` 负责隔离解析、工作流编排、Agent 运行、检查、渲染和 Provider Gateway。
- `packages/contracts` 是前后端共享的 OpenAPI、JSON Schema、fixtures、状态机和生成类型来源。
- PostgreSQL 是业务事实来源；Redis 只承担队列、缓存与事件扇出，Redis 丢失不能改变最终任务状态。
- MinIO 使用 `quarantine`、`clean`、`tmp`、`published` 等私有分区；扫描或解析异常按 fail-closed 处理。

详细设计见 [系统设计](docs/design/system-design.md)、[合同设计](docs/design/contract-design.md) 与 [G01 引擎适配器设计](docs/design/g01-engine-adapter.md)。

## Agent 设计

默认 `agent-authoring` 不是“模型生成文字后套固定模板”，而是由一个可恢复的 Main Presentation Agent 连续完成策略规划和逐页执行：

```text
Approved Snapshot
  → Strategist：直接读取批准的 Intent / Outline / Sources
  → design_spec.md 设计确认 → spec_lock.md
  → Executor：P01 门禁 → P02…Pn 顺序创作
  → 每页 Direct SVG（唯一作者格式）
  → 内容/SVG/图表/包级检查
  → 只读多模态视觉复核
  → Main Agent 自适应定点修复（最多审核 5 轮）
  → 编译、发布、创建不可变 Revision
```

### Main Agent 与 Supervisor

- **Main Agent**：同一会话中先担任 Strategist，再担任 Executor；读取已批准快照和允许的设计上下文，逐页产出 canonical SVG，并根据工具观察主动修复。
- **设计确认**：Strategist 不再接收或生成 Page Blueprint/等价页面合同；它直接产出 `design_spec.md`。用户未明确授权设计与锁定时，状态停在 `awaiting_design_confirmation`，Executor 不会启动。
- **Supervisor**：不替 Agent 设计页面，只负责工具白名单、令牌/成本/时间预算、每阶段最多 5 次尝试、取消与 fencing、防重放计费、检查点和终止条件。
- **视觉 Reviewer**：只读地观察渲染图并返回带稳定指纹的结构化问题；它不能直接改稿，所有修复仍由 Main Agent 完成。零 blocking 立即通过，连续两轮无改善或质量恶化会恢复最佳 SVG 并进入人工处理，最多执行 5 次审核（首次审核 + 最多 4 次返修）。

### 工具与证据

Agent 只能调用面向演示创作的受控工具，例如读取批准上下文、读取设计目录、写入策略/当前页面 Direct SVG、运行内容与 SVG 检查、渲染页面、执行视觉复核以及暂停/完成任务。它没有任意 Shell、数据库凭据、浏览器会话或跨租户对象访问能力。

每页发布收据都会把 SVG 哈希绑定到模型回合、工具调用、工具观察、预算消耗和终止原因。检查点支持同一幂等键恢复，已确认的 Provider 使用量不会因 Worker 重试而重复计费或重复写入。

### 回退与灰度

`deterministic-template` 是独立运行剖面，不调用文本 Provider 或 Agent 工具，也不会伪造 Agent 收据。Agent 安全指标在 canary 中越过阈值时，只影响新的生成快照；已运行任务和已发布版本保持不可变。回退由明确配置触发，不会因 Provider 失败而静默降级。

完整决策见 [ADR-012：Presentation Agent Authoring](docs/adr/ADR-012-presentation-agent-authoring.md) 与 [ISSUE-003](docs/issues/ISSUE-003-default-agentic-profile-lacks-real-presentation-agent-runtime.md)。

## 数据、恢复与安全原则

- 所有业务对象带租户边界；生产认证、对象键、SSE 和下载路径均需通过租户校验。
- 批准的意图、大纲、模板版本、生成快照、演示版本和已发布产物不可变；编辑会创建新版本。
- 状态变更、领域事件和 Outbox 在同一事务中提交；刷新或 Worker 重启后可从 PostgreSQL 恢复。
- 源文件、抽取文本和页面截图按最小必要原则传给 Provider；日志只记录哈希、标识符和脱敏元数据。
- 防病毒扫描、内容解析、视觉门禁、PPTX 包检查或发布检查失败时默认拒绝继续，不产生“看似成功”的下载。
- Provider 或明确图片路径失败时进入 `Needs-Manual`，不会静默丢图或替换为不相关素材。

安全与恢复操作见 [运行手册](docs/runbook.md) 和 [发布检查清单](docs/release-checklist.md)。

## 验证

提交代码前可按风险运行分层检查；完整 Gate 链为：

```powershell
docker compose config --quiet
pnpm verify
```

`pnpm verify` 覆盖合同、Web、API/领域、Worker、集成、Golden、恢复、E2E、安全、链接与 G08 自动发布 Gate。发布候选还需要人工完成 PowerPoint/WPS 兼容性、可编辑性和视觉回归复核。

最近一次归档的完整基线（2026-08-23）中，合同、API/领域、Worker、G02–G08、Golden、恢复、E2E、安全和发布 Gate 全部通过。2026-08-26 对 Qwen 真实 Provider 生成的两份 6 页成品复核均成功渲染且无画布溢出；具体证据和质量边界记录在 [ISSUE-003](docs/issues/ISSUE-003-default-agentic-profile-lacks-real-presentation-agent-runtime.md)。

## 仓库结构

```text
apps/web/             Next.js Web/BFF
services/api/         FastAPI 业务 API 与 SSE
services/worker/      Celery、Agent、解析、渲染、Provider Gateway
packages/contracts/   OpenAPI、Schema、fixtures、生成类型
packages/domain/      SQLAlchemy 领域模型、仓储与迁移
services/worker/contracts/ 引擎适配器请求/响应合同
infra/compose/        本地基础设施配置
docs/                 设计、ADR、Issue、Runbook 与发布证据
scripts/              验证、合同物化和运行辅助脚本
```

## 文档索引

- [产品与验收规范](SPEC.md)
- [实施计划](PLAN.md)
- [当前进展](PROGRESS.md)
- [系统设计](docs/design/system-design.md)
- [合同设计](docs/design/contract-design.md)
- [开发环境](docs/development.md)
- [运行手册](docs/runbook.md)
- [发布 Gate 报告](docs/release-gate-report.md)
- [Git 操作记录](git.md)

## 仓库策略

仓库使用 Git 管理。除非得到明确授权，不创建提交、不推送、不部署，也不清理或覆盖用户已有的未提交改动。合同生成目录不得手工修改；需要先更新合同目录源并运行物化与验证命令。
