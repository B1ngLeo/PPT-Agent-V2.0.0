# 即刻AI-PPT Codex Goal 执行计划

> 文档状态：Execution Baseline v1.0  
> 更新日期：2026-08-16  
> 规范性需求：[SPEC.md](SPEC.md)  
> 设计参考：[交互原型](designs/ppt-ai-mvp/prototype.html)  
> 架构背景：[技术方案评审稿](designs/ppt-ai-mvp/technical-solution.md)

## 0. 如何使用本计划

Codex 官方将 Goal 定位为“跨多个 turn 持续工作，直到可验证停止条件成立”的耐久目标。合适的 Goal 应只有一个目标、清楚说明不改什么、列出必读文件和验证命令，并在检查点记录进度。不要把一组无关 backlog 塞进一个 Goal。[OpenAI Codex：Follow a goal](https://learn.chatgpt.com/use-cases/follow-goals)

本计划因此采用**连续 Goal**，而不是一个覆盖全部 P0/P1 的超大 Goal：

1. 一次只启动一个 Goal；
2. 前一 Goal 的停止条件通过后再启动下一 Goal；
3. 每个 Goal 都有可复制的 `/goal` 提示、范围、非范围、产物、验证和暂停条件；
4. Goal 不得通过删除测试、弱化断言或伪造工件来“通过”；
5. 需要许可证、生产凭据、付费资源、生产部署或重大产品决策时，记录证据并暂停，等待用户授权。

如果 `/goal` 不在命令列表，可按官方说明启用：

```toml
[features]
goals = true
```

或运行：

```bash
codex features enable goals
```

本文只生成 Goal 执行合同，不会自动启动 Goal。

## 1. 全局执行合同

### 1.1 每个 Goal 的必读顺序

Codex 开始任何 Goal 前必须按顺序阅读：

1. `SPEC.md`；
2. `PLAN.md` 当前 Goal；
3. `PROGRESS.md`；
4. 当前 Goal 指定的 ADR、合同、代码和测试；
5. `designs/ppt-ai-mvp/` 中与当前页面相关的原型代码。

若实现与 `SPEC.md` 冲突，停止扩展并记录 `DECISION_REQUIRED`；不得静默选择更大范围。

### 1.2 进度日志

Goal G00 创建根目录 `PROGRESS.md`，后续 Goal 原地更新。每个检查点只保留紧凑事实：

```markdown
## 当前 Goal

- Goal：Gxx / 名称
- 状态：in_progress | blocked | complete
- 当前检查点：CP-x
- 已验证：命令 + 结果摘要
- 剩余工作：最多 5 项
- 决策/偏离：ADR 或无
- 阻塞：明确条件、已尝试方案、需要谁做什么
```

Goal 完成时追加：

- 产物路径；
- 所有停止条件及证据；
- 新增/修改的稳定验证命令；
- 未进入当前范围的后续项。

### 1.3 修改边界

- 不修改 `vendor/ppt-master` 的许可证、copyright、SPONSORS、官方元数据和 attribution guard；
- 不直接将上游脚本暴露给 Web/API；
- 不实现 `SPEC.md` 的非目标；
- 不提交、推送、开 PR、部署或创建付费云资源，除非用户明确授权；
- 不把密钥、访问令牌、个人数据、源文档正文或预签名 URL 写入仓库和日志；
- 不删除用户现有文件或无关改动；
- 依赖版本必须锁定并记录来源，不能使用浮动 `latest/main` 进入可重复构建；
- 外部 Provider 不可用时用合同一致的 Fake Provider 验证，不得伪造“生产集成已完成”。
- 2026-08-16 经 Product/Security/Legal 批准，真实产品文本 Provider 使用 Kimi `model=kimi-k3`，GPT Image 适配器使用 OpenAI Images `model=gpt-image-2`，两者均可路由 `base_url=https://cf.api.fan/v1`。Kimi 密钥仅由私有 Provider Gateway 读取；图片密钥只能在用户显式选择图片、租户配额/费用预占成功、快照冻结受控配置且运行时开关开启时按最小白名单注入 Worker 子进程。密钥不得打印或写入 `.env.example`、日志、测试快照、公开 API 或前端 bundle。默认 `image_scope=none`且环境变量不能单独开启生图；`cover_only/selective` 按 ISSUE-002 图片 Release Gate 执行严格路径、Needs-Manual、资产分析、独立 PPTX 对象和 whole-deck final QA。

### 1.4 稳定验证入口

G00 必须创建根级验证入口。后续 Goal 可以扩展，但不得改名或弱化已存在目标：

```bash
pnpm verify:contracts
pnpm verify:web
pnpm verify:api
pnpm verify:worker
pnpm verify:integration
pnpm verify:golden
pnpm verify:e2e
pnpm verify:security
pnpm verify:gates
pnpm verify
```

规则：

- 尚未进入范围的目标可以明确输出 `not-configured`，但从首次实现起必须真实运行；
- `pnpm verify` 运行当前阶段全部适用的非破坏性检查；
- Python 子项目由根脚本调用 `uv run`；
- E2E 使用受支持的浏览器自动化，测试真实 HTTP 页面，不打开 `file://`；
- PowerPoint/WPS 实机检查作为 Windows runner 或人工 Gate，不能用 LibreOffice 打开替代。

### 1.5 人工、法务与产品 Gate

G00 创建 `docs/evidence/gate-manifest.yaml` 及其 JSON Schema。每个 Gate 至少包含：

```yaml
id: GATE-ID
status: pending # pending | ready_for_review | passed | failed | waived
ownerRole: product | legal | security | qa | engineering
approver: null
checkedAt: null
targetVersions: []
evidence: []
notes: ""
```

规则：

- Codex 可以生成测试工件并把状态推进到 `ready_for_review`，但不能代替法务、产品、安全负责人或 PowerPoint/WPS 人工检查人把 Gate 标成 `passed`；
- `waived` 必须引用批准 ADR、负责人、到期日和补偿措施；
- 当前 Goal 存在 `pending`、`ready_for_review` 或 `failed` 的 required Gate 时，Goal 状态为 `waiting_for_human_gate`，不得标记 complete；
- `pnpm verify:gates --goal Gxx` 校验当前 Goal 所需 Gate 均为 `passed` 或有效 `waived`；
- 人工兼容证据必须包含检查人、日期、PowerPoint/WPS 精确版本和附件/报告路径。

严重级别和证据默认值：

- **Sev-1**：跨租户访问、任意代码/文件执行、不可恢复数据损坏、密钥泄露、主链路全量不可用；不得 waiver；
- **Sev-2**：主流程在支持环境稳定失败、PPTX 需修复才能打开、关键内容不可编辑/被裁切、恢复机制失效；仅产品/工程/安全共同批准的限期 waiver 可接受；
- **依赖高风险**：CVSS >= 7.0 或扫描器标记 High/Critical；必须修复、证明不可达或用有到期日 ADR 豁免；
- **恢复/竞态稳定性**：相关故障注入测试默认连续 10 次通过；
- **干净环境**：无项目构建缓存和依赖目录、只预装文档声明的系统工具的全新 CI worker。

### 1.6 通用完成条件

一个 Goal 只有在以下条件全部满足时才能结束：

1. 当前 Goal 所列产物存在并可读；
2. 当前 Goal 所列验证命令全部通过；
3. 之前 Goal 的验证没有回归；
4. 没有通过跳过、删除或放宽测试制造绿色结果；
5. `PROGRESS.md` 已记录证据；
6. 新增偏离有 ADR；
7. 无当前范围内仍可安全推进的必做项。

### 1.7 通用暂停条件

遇到以下情况时停止扩大修改范围，完成安全诊断和文档记录后暂停：

- 许可证、商标、生产数据流向或外部供应商条款无法确认；
- 需要用户提供生产密钥、登录或购买付费资源；
- 继续执行会覆盖/删除未知用户数据；
- SPEC 的两个规范要求互相冲突且无法用现有 ADR 解释；
- P0 门禁失败并证明不是局部实现缺陷；
- 需要改变 P1 模式、输入格式、编辑边界或租户模型；
- 安全测试发现跨租户、任意文件读取、命令执行或密钥泄露风险。

## 2. 阶段总览

```text
G00 合同与工程基线
  ↓
G01 引擎/许可/金样本/Source Security Spike
  ↓
G02 持久任务/SSE/恢复 Spike
  ↓
P0 Gate
  ↓
G03 身份、租户与存储底座
  ↓
G04 安全上传与 Source 解析
  ↓
G05 草稿、意图、大纲与 Web 工作台
  ↓
G06 真实生成、监控与工件发布
  ↓
G07 结果编辑、导出与历史闭环
  ↓
G08 安全/质量/可观测/发布门禁

可选：G09 私有模板上传（P1.1，在 G08 后）
```

P1 产品开发不得越过 P0 Gate。所有 Goal 按顺序执行并原地维护同一份 `PROGRESS.md`；本计划不授权并行 Goal。

## 3. Goal G00：冻结合同与建立工程基线

### 3.1 目标

建立可重复开发的 monorepo、机器可读合同、ADR 基线和稳定验证入口；不实现业务流程。

### 3.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G00“冻结合同与建立工程基线”。先完整阅读 SPEC.md、PLAN.md、designs/ppt-ai-mvp/technical-solution.md 和 designs/ppt-ai-mvp/prototype-spec.md。只建立 monorepo、开发环境、ADR、OpenAPI/JSON Schema、状态机/错误码合同、生成类型和稳定验证入口；不要实现业务页面、真实上传、AI 生成或 PPT 引擎。持续工作到 G00 的全部验证命令通过、PROGRESS.md 记录证据且停止条件成立；遇到 PLAN.md 的暂停条件时记录 DECISION_REQUIRED 后暂停。
```

### 3.3 范围

- 初始化 `apps/web`、`services/api`、`services/worker`、`packages/contracts`、`infra/compose`、`tests`；
- 固定 Node/pnpm、Python/uv 和容器工具链版本；
- 创建根 `package.json`、`pnpm-workspace.yaml`、`pyproject.toml`/uv workspace、lockfiles 与基础 lint/typecheck/test 配置；
- 创建根 `compose.yaml` 作为稳定入口；服务细节可以拆到 `infra/compose/`，但根目录 `docker compose config` 必须可用；
- 创建本地 PostgreSQL、Redis、S3 兼容对象存储、扫描器的 Compose 配置；
- 建立 `docs/adr/` 和 SPEC 第 16 节的 ADR 模板/状态；
- 创建 OpenAPI 基线、全部 P1 endpoint 正反 fixtures、核心 JSON Schema、RFC 7807 扩展错误模型；
- 冻结分离的 source/job/slide/export 状态机与事件 envelope；
- 生成 TypeScript/Pydantic 类型或验证生成流程；
- 创建 `PROGRESS.md`、`docs/evidence/gate-manifest.yaml`、严重级别/豁免规则与稳定验证入口；
- 建立 CI 骨架，只运行已经真实配置的检查。

### 3.4 非范围

- 登录、数据库业务表、上传、Worker 任务；
- 真实 LLM/图片 Provider；
- vendoring 或执行 `ppt-master`；
- 产品 UI 还原；
- 生产部署。

### 3.5 检查点

#### CP-00A 工具链与目录

- workspace 安装可重复；
- `docker compose config` 通过；
- 根 `uv sync --frozen` 与根 pnpm workspace 均有明确入口；
- `.env.example` 只有非敏感占位；
- Windows 与 Linux 路径不依赖硬编码用户目录；CI 至少包含 Windows 与 Linux 的 bootstrap/contract matrix。

#### CP-00B 合同

- OpenAPI 可 lint；
- `UploadSession`、`SourcePackage`、`SourceArtifact`、`IntentSpec`、`OutlineSpec`、`TemplateVersion`、`GenerationSnapshot`、`DeckPlan`、`SlidePlan`、`JobEvent`、SSE reset/snapshot envelope、`QaReport`、`ArtifactManifest`、`PresentationRevision`、`SlideVersion`、`ExportJob`、`ExportManifest`、`Entitlement`、`UsageReservation`、`UsageLedger`、`ProviderCall`、`AuditEvent` 与 `ProblemDetails` 有版本化 Schema 和正反 fixtures；
- SPEC 中全部 P1 endpoint 至少有 request/response/error fixture；
- API 命名、ID 类型、时间格式、分页和乐观锁有 ADR；
- queued cancel、任务终态判定、事件到状态映射、presentation 创建时机、generation/export artifact 区别在合同中冻结；
- 单页 retry 使用稳定 `slideId`；
- 逻辑幂等键不包含 attempt。

#### CP-00C 验证与文档

- 根验证命令存在；
- CI 和本地命令一致；
- `PROGRESS.md` 记录未决 ADR 与 P0 Gate；
- `pnpm verify:gates --goal G00` 能验证 required Gate 状态；
- Markdown 链接和合同引用无断链。

### 3.6 验证

```bash
pnpm install --frozen-lockfile
uv sync --frozen
docker compose config
pnpm verify:contracts
pnpm verify:gates --goal G00
pnpm verify
```

### 3.7 停止条件

- 工具链可在无项目缓存、仅安装声明前置工具的全新 CI worker 上恢复；
- 合同 fixtures 通过；
- 状态机转换表、事件映射和错误 fixtures 全量通过合同测试；
- G01–G08 在“必备 Schema/endpoint”清单中不存在未定义前置；
- 未决的许可证/供应商选择被记录为 ADR 状态，而非隐藏在代码常量中。

### 3.8 暂停条件

- 无法确定 `SPEC.md` 与机器可读合同的优先级；
- 选定工具链在 Windows/CI 上不可重复；
- 需要改变 P1 默认范围才能完成脚手架。

## 4. Goal G01：引擎、许可证、金样本与 Source Security Spike

### 4.1 目标

证明固定版本 `ppt-master` 能在隔离、可重复环境中分别完成 `source → parse → SourcePackage` 与 `DeckPlan → SVG → QA → PPTX`，并用最小安全 intake harness 证明恶意文件不能进入 clean/parse，同时形成许可和兼容证据。固定 DeckPlan 用于隔离 LLM 随机性，不宣称验证了 AI 内容规划质量。

### 4.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G01“引擎、许可证、金样本与 Source Security Spike”。先阅读 SPEC.md、G00 合同、相关 ADR 和上游许可证/技术文档。固定并记录 ppt-master tag/commit，完整保留 attribution，构建唯一 engine-adapter CLI、隔离 Worker 镜像和最小 quarantine/scan/clean/parse 安全 harness；用 10 份金样本分别验证 source→SourcePackage 与固定 DeckPlan→SVG→QA→PPTX。不要构建多租户 Web/API 产品流程。持续到安全样本、金样本、SBOM、包结构与 PowerPoint/WPS Gate 达到 G01 停止条件；许可证或 attribution 未通过时记录证据并暂停，不得绕过。
```

### 4.3 前置

- G00 完成；
- OpenAPI/Schema 中的 SourcePackage、DeckPlan、SlidePlan、ArtifactManifest 已有基线；
- 具备合法获取上游源码的方式。

### 4.4 范围

- 固定 `ppt-master` tag/commit 和 vendor 方式；
- 生成依赖锁、容器 digest、字体包 manifest 与 SBOM；
- 实现 `engine-adapter` CLI，只接受版本化 JSON 和对象 key/本地测试 fixture；
- Adapter 输出 canonical SVG、QA report、PPTX、预览和 artifact manifest；
- 建立 10 份中英文/长标题/表格/图表/字体/模板金样本；每份包含 source fixture、预期 SourcePackage 与已批准固定 DeckPlan；
- 建立最小 P0 intake threat harness：quarantine/clean 隔离、扫描器、扩展名/MIME/magic 校验、ZIP/Office 资源上限、损坏/加密/病毒/ZIP bomb/路径穿越 fixtures；
- 只有安全 harness 判定 clean 的样本才能进入 parse；该 harness 在 G04 中产品化，不包含多租户 HTTP API；
- 自动检查 SVG、PPTX ZIP 包结构、关系、页数、媒体、hash；
- 记录 PowerPoint/WPS 实机打开、修复提示、可编辑性和视觉结果；
- 完成 PyMuPDF 与 EPUB 许可 ADR；EPUB 默认禁用。

### 4.5 非范围

- 多租户 HTTP API、SSE、Celery 产品编排；
- LLM 真实内容生成；金样本可使用固定 DeckPlan；
- Web UI；
- 修改上游 attribution 或把 vendor 代码复制进业务模块。

### 4.6 检查点

#### CP-01A 供应链

- 固定 commit 可验证；
- LICENSE、copyright、SPONSORS、第三方声明和 attribution guard 完整；
- lockfile、SBOM、字体来源和容器 digest 可追踪。

#### CP-01B Adapter 合同

- 业务层不导入上游内部模块；
- Adapter 输入输出通过 Schema；
- 错误映射为稳定 error code；
- Adapter 无业务数据库凭据。

#### CP-01C 金样本

- 10/10 source fixture 产生符合 Schema 的 SourcePackage，恶意 fixture 全部在 clean/parse 前被阻断；
- 10/10 自动 package QA；
- PowerPoint/WPS 无修复提示；
- 标题、正文和约定图形可编辑；
- 视觉差异有基线与严重级别。

### 4.7 验证

```bash
pnpm verify:contracts
pnpm verify:worker
pnpm verify:golden
pnpm verify:security
pnpm verify:gates --goal G01
pnpm verify
```

并完成 Windows PowerPoint/WPS 实机记录。若当前环境不能自动化，生成明确的人工 Gate 清单和待填证据，不得声称已通过。

### 4.8 停止条件

- `SPEC.md` 12.3 的 P0 金样本门槛全部有证据；source 与 render 两条验证链都通过；
- P0 threat harness 证明风险样本不能进入 clean 或 parse；
- PDF 解析路径有批准 ADR；
- 引擎可从干净环境重复构建；
- Adapter 是唯一上游调用边界；
- 无 attribution 绕过和未处理高风险依赖。

### 4.9 暂停条件

- PDF 许可无法批准且替代栈不满足合同；
- 上游生成结果无法达到 PowerPoint/WPS 可打开性门槛；
- 必须修改上游版权/attribution 才能运行；
- 目标 PowerPoint/WPS 不可用或人工兼容 Gate 尚未签字；此时状态必须为 `waiting_for_human_gate`；
- 需要真实用户敏感文档才能继续验证。

## 5. Goal G02：持久任务、幂等、SSE 与恢复 Spike

### 5.1 目标

在不接真实 PPT 引擎的情况下，用确定性 Fake Worker 证明任务状态、outbox、SSE 回放、取消和崩溃恢复合同可行。

### 5.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G02“持久任务、幂等、SSE 与恢复 Spike”。先阅读 SPEC.md 的生成编排、事件和数据不变量，以及 G00 合同。实现最小 PostgreSQL+Celery+Redis 持久任务闭环，使用确定性 Fake Worker；验证幂等、outbox、Last-Event-ID、Worker kill、Redis restart、取消/publish 竞态和单页 partial。不要接入 ppt-master、产品 UI、登录或真实 Provider。持续到全部恢复测试通过并在 PROGRESS.md 记录证据。
```

### 5.3 范围

- generation snapshot/job/job slide/event/outbox/idempotency 最小表；
- 创建最小 `organizations` 与 synthetic service actor fixture，使所有 job/idempotency 行从第一版迁移起就有真实 organization 外键；G03 在此基础上增加 users/memberships，必须验证已有 Spike 数据无损升级；
- 数据库状态转换与合法性约束；
- outbox dispatcher 与 Redis 分发；
- SSE snapshot + replay + live handoff；
- job 内单调 `seq`、heartbeat、终态关闭；
- 逻辑 task key 与 attempt 分离；
- Worker lease、late ack、受限预取和指数退避；
- cancel_requested、终态竞态和幂等 no-op；
- Fake Worker 可注入单页失败、进程终止、延迟和重复投递。

### 5.4 非范围

- 真实 source、PPT engine、用户登录；
- 产品页面；
- 对象工件内容，仅可用小型 fixture 模拟 manifest。

### 5.5 检查点

#### CP-02A 状态真相

- Redis 全部清空后 job snapshot 仍正确；
- 每个状态转换在数据库事务中校验；
- draft/job/slide/export 状态未混用。

#### CP-02B 幂等与竞态

- 同 key 同 body 返回同一 job；
- 同 key 异 body 返回冲突；
- 重投不重复事件副作用、工件引用和用量预占；
- cancel 与 publish 只产生一个合法终态。

#### CP-02C SSE

- Last-Event-ID 回放无遗漏；
- DB 回放与实时流交界按 seq 去重；
- Redis restart、浏览器重连和慢客户端行为可验证。

### 5.6 验证

```bash
pnpm verify:contracts
pnpm verify:api
pnpm verify:worker
pnpm verify:integration
pnpm verify:gates --goal G02
pnpm verify
```

集成测试至少包含：

```text
test_idempotency
test_worker_crash_recovery
test_redis_restart
test_sse_resume
test_cancel_publish_race
test_partial_slide_completion
```

### 5.7 停止条件

- 所有恢复与竞态测试连续 10 次通过；
- PostgreSQL 可独立重建完整 job 状态；
- Redis 不再是唯一真相；
- attempt 不影响逻辑幂等；
- P1 Orchestrator 可以复用该实现而无需推翻合同。

### 5.8 暂停条件

- 状态只能保存在 Redis 或 Worker 内存；
- SSE 回放窗口存在无法解释的事件缺口；
- 为通过测试必须关闭 late ack、取消或幂等保障。

## 6. P0 Gate

G01 与 G02 完成后运行一次 P0 Gate 评审。只有以下条件全部满足才启动 G03：

- 引擎许可、attribution、依赖和字体来源可上线；
- 10 份金样本达到 SPEC 门槛；
- G01 最小 intake threat harness、Worker 沙箱和恶意样本门禁通过；G04 负责把同一规则产品化；
- 幂等、Worker kill、Redis restart、SSE reconnect 通过；
- OpenAPI/Schema 与 Spike 实现一致；
- P0 失败项没有被降级成“上线后再看”。

P0 Gate 结果写入 `PROGRESS.md`、`docs/p0-gate-report.md` 和 `docs/evidence/gate-manifest.yaml`。所有 required Gate 均为 `passed` 或有效 `waived` 后才可继续。

## 7. Goal G03：身份、租户与存储底座

### 7.1 目标

实现可用于后续业务模块的登录、personal organization、授权上下文、对象存储分区和审计底座。

### 7.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G03“身份、租户与存储底座”。确认 P0 Gate 已通过，阅读 SPEC.md 的身份、数据不变量、安全和对象存储要求。实现登录适配、personal organization、FastAPI 授权上下文、租户隔离、private bucket 分区、短时签名底座和审计记录；不要实现文档解析、意图大纲、生成或产品完整页面。持续到跨租户 API/SSE/对象/下载测试全部通过。
```

### 7.3 范围

- ADR-002 身份提供方与令牌交换；
- users、organizations、memberships 与迁移；
- local-only 测试身份，生产构建强制关闭绕过；
- API 认证、组织上下文和授权中间件；
- `entitlements` 基线、personal organization 默认能力和 `GET /v1/me/entitlements`/`GET /v1/me/usage` 的只读基线；不实现支付；
- private bucket 与 tenant/quarantine/clean/tmp/published key 规则；
- 基础 artifact metadata、短时下载授权；
- audit log 与日志脱敏；
- 跨租户统一 404。

### 7.4 非范围

- 团队邀请和角色管理 UI；
- 上传会话和文件解析；
- 生成、配额结算和产品工作台。

### 7.5 验证

```bash
pnpm verify:contracts
pnpm verify:api
pnpm verify:integration
pnpm verify:security
pnpm verify:gates --goal G03
pnpm verify
```

至少覆盖：

- 跨租户 API 资源；
- 猜测对象 key；
- 过期/篡改下载授权；
- 日志无 token、正文和签名 URL；
- 生产配置不能启用 dev auth bypass；
- G02 synthetic organization/job 数据升级到正式 identity 外键后保持完整。

### 7.6 停止条件

- 每个测试用户自动获得 personal organization；
- personal organization 获得可配置的 P1 默认 entitlement，前端可从 API 读取而非硬编码；
- API、对象和下载授权均按 organization 隔离；
- 审计事件含 actor/resource/requestId；
- 后续模块可以复用统一授权上下文。

### 7.7 暂停条件

- 需要生产身份供应商密钥才能继续；
- 租户隔离只能依赖前端隐藏；
- 对象存储必须公开 ACL 才能工作。

## 8. Goal G04：安全上传与 Source 解析闭环

### 8.1 目标

实现 DOCX/PDF/PPTX/HTML 的预签名上传、隔离扫描、格式校验、解析、恢复和 SourceArtifact 发布。

### 8.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G04“安全上传与 Source 解析闭环”。阅读 SPEC.md 的上传/解析、安全和对象存储合同，以及 G01 engine-adapter。实现 upload session、直传 complete 复核、quarantine→scan→clean→parse 流程和 SourceArtifact；只允许 clean 对象进入隔离 Worker。不要实现意图大纲、生成或模板上传。持续到合法格式、篡改、病毒、ZIP bomb、路径穿越、损坏/加密文件、网络重试和跨租户测试全部通过。
```

### 8.3 范围

- upload_sessions、sources、source_artifacts、idempotency；
- 预签名约束、HEAD、真实大小和 SHA-256 复核；
- 扫描器不可用时 fail closed；
- 扩展名/MIME/magic 三重校验；
- ZIP/Office 防炸弹与路径安全；
- HTML 禁脚本和外部抓取；
- 隔离解析 Worker 与超时/资源限制；
- Markdown、素材清单、conversion profile、解析版本发布；
- Web 最小上传/扫描/解析状态组件和恢复入口。

### 8.4 非范围

- DOC、PPT、MD、EPUB、URL；
- 多文档合并；
- 私有模板分析；
- 意图与 PPT 生成。

### 8.5 验证

```bash
pnpm verify:web
pnpm verify:api
pnpm verify:worker
pnpm verify:integration
pnpm verify:security
pnpm verify:gates --goal G04
pnpm verify
```

至少覆盖：

```text
test_upload_checksum_mismatch
test_upload_quarantine
test_scanner_fail_closed
test_magic_mime_mismatch
test_zip_bomb
test_path_traversal
test_encrypted_or_corrupt_source
test_source_retry_idempotency
test_source_refresh_recovery
```

### 8.6 停止条件

- 四种白名单格式有成功 fixture；
- 恶意/不合法文件不能进入 clean 或 parse；
- 解析状态可跨刷新/API 重启恢复；
- 工件不可变并有 hash/版本；
- PDF 路径符合已批准许可 ADR。

### 8.7 暂停条件

- 扫描器不可用时实现要求直接解析；
- PDF 许可未通过；
- HTML 解析需要未审计外网抓取。

## 9. Goal G05：草稿、意图、大纲与 Web 工作台

### 9.1 目标

将原型的首页和意图/大纲工作台实现为真实持久产品流程，完成版本、乐观锁、批准和生成前确认，但不启动 PPT 生成。

### 9.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G05“草稿、意图、大纲与 Web 工作台”。阅读 SPEC.md 的首页、IntentSpec、OutlineSpec、版本/批准和响应式要求，并参考 designs/ppt-ai-mvp 原型。实现真实草稿、自动保存、Provider Gateway、意图 revision、大纲 revision、撤销/恢复、乐观锁、内置模板选择和批准后的生成确认摘要；真实开发文本调用使用 Kimi API 的 kimi-k3，合同与回归测试使用 deterministic Fake Provider。密钥只从 Worker 侧 MOONSHOT_API_KEY 读取且不得输出。OpenAI gpt-image-2 仅预配置，不得在 P1 流程中调用。不要创建真实 generation job 或调用 PPT 引擎。持续到刷新恢复、并发冲突、批准后不可变、Provider 合同、键盘和三档响应式 E2E 全部通过。
```

### 9.3 范围

- drafts、intent_revisions、outline_revisions、outline_slides；
- templates、template_versions、内置 seed、模板 catalog API 与不可变版本测试；
- 首页品牌、口号、主题输入、文档入口、内置模板和历史入口骨架；
- 首页额度/能力展示读取 G03 entitlement API，不使用原型硬编码；
- mode 只开放 native；非 P1 模式隐藏或明确禁用；
- Intent 全字段，包括 language；
- Provider Gateway + Kimi `kimi-k3` 适配器 + deterministic Fake Provider，并持久化脱敏的 provider_calls/用量元数据；
- Kimi 适配器使用 OpenAI 兼容 Chat Completions 协议和可配置 base URL；不得把 Kimi 专有字段泄漏进领域合同；
- JSON Schema 输出校验和有限修复；
- AI/人工修改都产生 revision；
- 大纲增删、移动、单页重写、整纲优化、撤销/恢复；
- `If-Match`/base revision 并发冲突；
- 批准 outline revision 与生成前摘要；
- 自动保存与保存失败恢复；
- 390、768、1440px 响应式和键盘流程。

### 9.4 非范围

- generation job、SSE 生成监控；
- 真实 PPT 输出；
- 私有模板；
- 自由画布和视觉创意模式。

### 9.5 检查点

#### CP-05A 领域版本

- revision 不可变；
- 撤销/恢复不改写旧版本；
- outlineSlideId 稳定；
- 批准引用明确 revision。

#### CP-05B Provider

- Fake Provider 可重复；
- 本机存在 `MOONSHOT_API_KEY` 时，`kimi-k3` 最小 smoke test 和结构化输出合同通过；测试不得输出密钥、完整认证头或思维链；
- Kimi 适配器无密钥时明确不可用，并可切换至 Fake Provider；
- Schema 错误可恢复；
- AI 聊天必须产生真实 revision 或失败，不只显示文案。

#### CP-05C Web

- 原型视觉语言保留；
- UI 状态来自 API；
- 无硬编码历史、额度、模式或模板状态；
- 焦点、label、错误和自动保存可访问。

### 9.6 验证

```bash
pnpm verify:contracts
pnpm verify:web
pnpm verify:api
pnpm verify:integration
pnpm verify:e2e
pnpm verify:gates --goal G05
pnpm verify
```

关键 E2E：E2E-002、E2E-003、E2E-011 的当前范围部分。

### 9.7 停止条件

- 用户能从主题或 parsed source 创建并恢复草稿；
- 意图/大纲真实版本化；
- 内置模板由 catalog API/不可变 templateVersionId 驱动；
- 并发冲突不丢数据；
- 批准后生成摘要包含全部 snapshot 输入；
- Kimi K3 真实 smoke test 与 Fake Provider 回归测试各自留有脱敏证据；
- 当前尚未启动真实生成，UI 明确停在确认边界。

### 9.8 暂停条件（历史；Provider 项已于 2026-08-16 解除）

- Kimi/OpenAI 供应商条款、数据流向或生产使用尚未批准时，开发可继续使用 Fake Provider，但不得宣称生产集成完成；该项已由 ADR-005 的具名批准和风险接受解除。生产 KES/KMS 在当前仅本地范围不适用，但必须在任何对外、多人、托管、QA/预发布或生产部署前恢复为必选发布控制；
- 产品要求把 visual/template mode 提升到 P1 Core；
- 版本语义只能通过原地覆盖实现。

## 10. Goal G06：真实生成、监控与工件发布

### 10.1 目标

将 G01 的 engine-adapter 接入 G02 的持久编排，完成 generation snapshot、逐页生成、QA、编译、发布、SSE 监控、取消和失败页重试。

### 10.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G06“真实生成、监控与工件发布”。阅读 SPEC.md 的 generation snapshot、job/slide 状态、幂等、SSE、工件与 partial 守卫，并复用 G01 engine-adapter、G02 orchestrator、G05 approved revision。实现原生专业模式的真实逐页生成、QA、compile、package QA、immutable manifest publish 和生成监控；不要实现结果轻编辑、最终导出 UI、视觉创意或私有模板。持续到金样本 E2E、Worker 重投、Redis 重启、SSE 重连、取消竞态、单页 partial/retry 和跨租户测试全部通过。
```

### 10.3 范围

- generation_snapshots 固定全部版本/hash；
- generation_jobs、generation_job_slides、usage_reservations、usage_ledger 与配额预占/结算；
- deck plan、逐页 content/render/qa；
- compile、package QA、preview、`generation_source_bundle`、`generation_baseline_pptx` 和 immutable generation manifest；
- 成功/partial 时创建 initial presentation revision；失败/取消时遵守 SPEC 的 presentation 创建规则；
- 任务/页面事件和真实进度；
- 生成监控 UI 映射真实机器状态：queued、running、cancel_requested、cancelled、partially_succeeded、failed、succeeded；
- 安全取消；
- 按稳定 slideId 手动重试；
- partial 结果保留失败槽位；
- 用量结算与审计。

### 10.4 非范围

- 暂停/继续；
- 结果文本编辑、排序、删除；
- 最终 export job 和下载 UX；
- 视觉创意、AI 图片、私有模板。

### 10.5 验证

```bash
pnpm verify:contracts
pnpm verify:web
pnpm verify:api
pnpm verify:worker
pnpm verify:integration
pnpm verify:golden
pnpm verify:e2e
pnpm verify:security
pnpm verify:gates --goal G06
pnpm verify
```

必须覆盖：E2E-004、E2E-005、E2E-006、E2E-007、E2E-010。

### 10.6 停止条件

- 真实任务不依赖浏览器计时器；
- 刷新/离页恢复；
- Worker kill/重复投递不重复发布或扣费；
- partial、retry 和取消语义一致；
- 所有 published artifact 有 hash、manifest 和版本；
- generation 工件与后续 export 工件类型、manifest、保留期和幂等绑定不同；
- 金样本完整生成通过。

### 10.7 暂停条件

- 引擎需要直接访问业务数据库；
- 重试会覆盖已通过 QA 的工件；
- 进度只能从 Celery 内存或 Redis 推测；
- 生产 Provider 缺失导致无法验证时，先用 Fake Provider 完成合同，不伪报生产完成。

## 11. Goal G07：结果编辑、导出与历史闭环

### 11.1 目标

完成 presentation revision、有限编辑、单页重生成、PPTX 导出、短时下载和历史恢复，使 P1 用户旅程闭环。

### 11.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G07“结果编辑、导出与历史闭环”。阅读 SPEC.md 的 presentation revision、stable slideId、partial 守卫、export revision、短时下载和历史恢复要求，并参考结果页原型。实现文本修改、排序、删除、单页重生成、明确 revision 的 PPTX 导出、下载授权和历史状态路由；不要扩展为自由画布、多人协作、图片/PDF 导出或 P2 功能。持续到完整主题/文档用户旅程、排序后重生成、partial 导出守卫、导出并发、链接过期和历史恢复 E2E 全部通过。
```

### 11.3 范围

- presentations、presentation_revisions、slide_versions；
- 操作集合和乐观锁；
- 文本修改、排序、删除、至少一页守卫；
- 单页重生成保留旧 ready 版本；
- partial 重试/删除/显式接受缺页；
- export_jobs 绑定 presentationRevisionId；
- 从 `presentation_revision_manifest` 重新编译/打包 `export_pptx`，生成独立 ExportManifest；未编辑 baseline 可复用字节但不能省略 export manifest；
- package QA、不可变 export artifact 和短时下载；
- 历史 cursor pagination 和状态路由；
- 项目级结构化数据导出、软删除、运行任务取消、异步对象/索引/事件/Provider 缓存清理和可审计结果；
- 结果“AI 可编辑初稿”核验提示；
- 响应式、键盘和无障碍。

### 11.4 非范围

- 元素自由画布；
- 多人协作和复杂合并；
- 永久公开分享；
- PDF/图片导出；
- 私有模板分析。

### 11.5 验证

```bash
pnpm verify:web
pnpm verify:api
pnpm verify:worker
pnpm verify:integration
pnpm verify:golden
pnpm verify:e2e
pnpm verify:security
pnpm verify:gates --goal G07
pnpm verify
```

必须覆盖：E2E-001、E2E-008、E2E-009、E2E-011、E2E-012。

### 11.6 停止条件

- 导出绑定明确 revision，编辑并发不改变运行中 export；
- 排序后按 slideId 重生成正确页面；
- 旧版本在新版本 QA 通过前可见；
- partial 不会静默缺页导出；
- 历史从真实数据恢复所有主状态；
- 下载链接可过期和重签，且不能跨租户使用；
- 项目删除后 API、SSE、旧下载 URL 和对象 key 均不可访问，数据导出绑定明确项目快照。

### 11.7 暂停条件

- 编辑操作会修改 approved outline 或 generation snapshot；
- 导出依赖“当前最新”而不是 revision ID；
- 产品要求进入自由画布或多人协作。

## 12. Goal G08：P1 安全、质量、可观测与发布门禁

### 12.1 目标

只处理阻断 P1 上线的安全、质量、可访问性、性能、恢复、许可证、观测和运维问题，形成可审计发布证据。

### 12.2 可复制启动提示

```text
/goal 完成 PLAN.md 的 Goal G08“P1 安全、质量、可观测与发布门禁”。阅读 SPEC.md 的 Release Gate、Definition of Done 和 E2E-001 至 E2E-012。运行并修复全部合同、单元、集成、金样本、浏览器、安全、恢复和兼容测试；补齐指标、trace、审计、告警、备份恢复、reconciliation、SBOM、回滚与隐私/许可证证据。只修复 P1 阻断项，不增加 P1.1/P2 功能，不部署生产。持续到 SPEC 的 P1 Definition of Done 全部有证据；任何安全、许可、跨租户或恢复阻断项失败时记录并暂停发布。
```

### 12.3 范围

- 全量回归与 flaky test 清理；
- 租户隔离、恶意上传、日志脱敏、依赖扫描；
- SSE、队列、Worker、数据库和对象存储恢复演练；
- reconciliation、备份/恢复、保留期和删除测试；
- OpenTelemetry trace、结构化日志、核心指标和告警；
- 配额预占/结算审计；
- 390/768/1440px、200% zoom、axe 自动检查、键盘全流程与至少一种 Windows 屏幕阅读器人工主流程；
- 按 SPEC 12.4 的固定数据规模、并发、预热和测量窗口运行负载/长任务基线；
- PowerPoint/WPS 实机兼容；
- SBOM、镜像 digest、依赖锁、attribution；
- `docs/release-gate-report.md`、evidence manifest、release checklist、runbook 和回滚手册。

### 12.4 非范围

- 生产部署；
- 视觉创意、私有模板、多用户协作、支付；
- 为提高演示效果而改变 P1 产品边界。

### 12.5 验证

```bash
pnpm verify:contracts
pnpm verify:web
pnpm verify:api
pnpm verify:worker
pnpm verify:integration
pnpm verify:golden
pnpm verify:e2e
pnpm verify:security
pnpm verify:gates --goal G08
pnpm verify
```

另需：

```text
PowerPoint/WPS 实机检查
Worker kill 演练
Redis restart 演练
对象发布 reconciliation 演练
备份恢复演练
项目删除与保留期清理演练
```

### 12.6 停止条件

- `SPEC.md` 第 13、14 节全部满足；
- E2E-001 至 E2E-012 全部通过；
- P0 金样本无回归；
- 没有未接受的 Sev-1/Sev-2；
- `docs/release-gate-report.md` 中每个 required check 都有状态、命令/人工证据、负责人和时间，且无 pending/blocking；
- 发布证据、SBOM、兼容报告、runbook 和回滚文档完整；
- `PROGRESS.md` 标记 P1 complete，并列出明确 P1.1/P2 backlog。

### 12.7 暂停条件

- 跨租户访问、任意文件读取/执行、密钥泄露；
- 许可证或数据流向未批准；
- PowerPoint/WPS 或屏幕阅读器人工 Gate 尚未签字时，标记 `waiting_for_human_gate`，不得以自动化替代；
- PowerPoint/WPS 打开需修复或关键内容不可编辑；
- Worker/Redis/对象存储故障会丢失不可恢复业务状态；
- 发布需要生产账号、DNS、密钥或费用。

## 13. Goal G09（可选）：P1.1 私有模板上传

只有 G08 完成且 ADR-009 批准后启动。

### 13.1 可复制启动提示

```text
/goal 完成 PLAN.md 的可选 Goal G09“P1.1 私有模板上传”。确认 G08 已完成且 ADR-009 批准，阅读 SPEC.md 第 15 节。实现仅 PPTX 的私有模板上传、扫描、真实预览、五类版式角色识别、人工修正、兼容报告、不可变 template version 和草稿绑定；不得实现公开市场、旧 PPT 转换、组织治理或“百分百兼容”承诺。持续到模板安全、映射持久化、缺失角色回退、未保存退出、无障碍、生成绑定和跨租户测试通过。
```

### 13.2 范围

- PPTX 上传复用 G04 安全流水线；
- 模板 hash、字体、尺寸、主题、角色和兼容报告；
- 封面、目录、章节、正文、结束五类角色；
- 用户修正/忽略、缺失角色回退；
- 私有 template version 与草稿绑定；
- 模态焦点锁定、Esc、焦点归位、未保存确认；
- 按 templateVersionId 固定 generation snapshot。

### 13.3 验证

```bash
pnpm verify:contracts
pnpm verify:web
pnpm verify:api
pnpm verify:worker
pnpm verify:integration
pnpm verify:e2e
pnpm verify:security
pnpm verify:gates --goal G09
pnpm verify
```

### 13.4 停止条件

- 非 PPTX、损坏、风险和跨租户模板被拒绝；
- 自动映射可修正并持久化；
- 缺失角色有明确回退；
- 生成任务使用真实 templateVersionId；
- 已被 snapshot 引用的模板版本不可覆盖；
- P1 Core 全套验证无回归。

## 14. 需求—Goal 追踪矩阵

| SPEC 领域 | 主 Goal | 最终 Gate |
|---|---|---|
| 文档合同、API、Schema、错误模型 | G00 | G08 |
| 引擎、金样本、许可证 | G01 | P0 Gate、G08 |
| Job、幂等、SSE、恢复 | G02 | P0 Gate、G06、G08 |
| 身份、租户、对象授权 | G03 | G08 |
| 上传、扫描、解析 | G04 | G08 |
| 草稿、意图、大纲、批准 | G05 | G08 |
| 真实生成、监控、取消、partial | G06 | G08 |
| Presentation revision、导出、历史 | G07 | G08 |
| 安全、无障碍、观测、发布证据 | G08 | G08 |
| 私有模板（可选） | G09 | 独立 P1.1 Gate |

## 15. 推荐的首次 Goal

当前工作区只有原型与方案文档，没有产品脚手架，因此首次执行应从 G00 开始：

```text
/goal 完成 PLAN.md 的 Goal G00“冻结合同与建立工程基线”。先完整阅读 SPEC.md、PLAN.md、designs/ppt-ai-mvp/technical-solution.md 和 designs/ppt-ai-mvp/prototype-spec.md。只建立 monorepo、开发环境、ADR、OpenAPI/JSON Schema、状态机/错误码合同、生成类型和稳定验证入口；不要实现业务页面、真实上传、AI 生成或 PPT 引擎。持续工作到 G00 的全部验证命令通过、PROGRESS.md 记录证据且停止条件成立；遇到 PLAN.md 的暂停条件时记录 DECISION_REQUIRED 后暂停。
```
