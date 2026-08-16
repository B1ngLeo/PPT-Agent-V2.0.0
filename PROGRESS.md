# 即刻AI-PPT development progress

> Updated: 2026-08-16. This file is updated after every completed module. A single repeated defect may be attempted at most five times; on a sixth failure it is recorded here and deferred while independent work continues.

## 当前 Goal

- Goal：G08 / P1 安全、质量、可观测与发布门禁
- 状态：waiting_for_human_gate
- 当前检查点：G08 PLAN/SPEC 完成度复审、对象存储治理、发布镜像健康探针、新鲜用户视角 E2E 与自动发布证据均已完成；Gate 为 `ready_for_review`
- 已验证：G08 4/4 隔离集成、五类恢复各 10/10、MinIO 私有 bucket 默认 AES256/安全生命周期/陈旧分片清理、`/healthz` 与 DB-backed `/readyz`、备份/恢复 64/64 对象 hash、22,131 性能样本 0 error、四个核心 UI 状态 axe critical/serious=0、三档无横向溢出、Node/Python 依赖 0 已知漏洞、12/12 告警规则、PowerPoint/WPS 各 10/10、30/30 视觉差分、E2E-001–012 与自动发布证据全部通过
- 剩余工作：具名 Windows Chromium 精确 200% + 屏幕阅读器人工检查；product/security/legal 具名批准生产 Provider、区域、保留、供应商条款、客户披露及生产 KES/KMS
- 决策/偏离：G05 P1 规划默认走 deterministic Fake Provider；Kimi/OpenAI 适配器仅保留 Worker 侧服务端配置。2026-08-16 官方 Kimi 列表尚未证明 `kimi-k3`、官方 OpenAI Images 列表尚未证明 `gpt-image-2`，因此不宣称真实生产集成完成；仍按已冻结 PLAN 保留精确模型名并将真实 smoke 设为密钥与供应商可用性双条件
- 阻塞：工程自动化无阻塞；G08 最终发布仍受两个不可由自动化代签的人工 Gate 阻塞：当前 Windows 未安装 NVDA 且精确 Chromium 200% 尚未具名复核，ADR-005 的生产 Provider/区域/保留/供应商条款及 KES/KMS 尚未由 product/security/legal 具名批准
- 恢复记录：应用内浏览器的 Tab/Enter 注入连续 5 次不产生事件，已按防循环规则停止并记录；产品使用原生控件，键盘文本焦点、焦点恢复及完整用户旅程通过，无产品阻塞

## 已完成事项

- 初始化 Git `main` 分支，并以 `5e930bf` 固化 G00–G01 已验证基线（未推送）。
- 建立 monorepo 目录、固定工具链文件、Next.js/FastAPI/Celery 最小边界和根 Compose 服务拓扑。
- 建立 ADR、系统设计、合同设计、开发说明、Gate Schema/manifest 与严重级别政策。
- 完成 CP-00B：物化并验证 26 个版本化 Schema、38 个 P1 endpoint、166 个 fixtures、四套状态机、事件映射、稳定错误模型和 TypeScript 类型。
- 完成 G00：干净环境 frozen restore、Next.js 生产构建、Python lint/test、Compose、Gate、Markdown 链接与根 `pnpm verify` 通过。
- G01 CP-01A：固定并 vendor `ppt-master` v4.7.0 / `e8323bfa…`，完整保留 12,907 个文件、归属文件和第三方声明；上游 attribution guard 通过。
- G01 CP-01B 安全边界：实现唯一 `engine-adapter` 版本化 JSON CLI 及 Schema；scan/parse 用文件 hash 绑定，路径穿越、恶意 HTML、病毒测试签名与篡改后解析单测全部通过。
- G01 CP-01B 渲染边界：固定 DeckPlan 已通过 `ppt-master` final SVG QA（0 error/0 warning）、同一字节指纹绑定、native DrawingML PPTX 编译、ZIP/关系/页数/媒体引用/可编辑文本与原生图形 package QA、整页位图回退检测和 manifest 生成；产品层引擎边界守卫、Worker lint 和 7 项单测通过。
- G01 CP-01C threat harness：13/13 恶意 fixture（magic/MIME、损坏/加密 PDF、损坏 Office、active/external HTML、病毒 canary、ZIP 路径穿越/深度/压缩比/符号链接/条目数、Office 外部关系）全部被 rejected，0 份进入 parse；证据写入 `docs/evidence/g01-security-results.json`。
- G01 CP-01C 金样本：10/10 source→SourcePackage 与 10/10 固定 DeckPlan→SVG→QA→PPTX 通过，共 30 页；每页上游 QA 0 error/0 warning，103/103 计划文本、123 个原生可编辑图形、190 条内部关系、0 悬空媒体、0 整页位图回退通过，40 个 SourcePackage/DeckPlan/QaReport/ArtifactManifest 产物通过 G00 Schema；证据写入 `docs/evidence/g01-golden-results.json`。
- G01 CP-01A 供应链：从 frozen `uv.lock`/`pnpm-lock.yaml` 生成并规范化 CycloneDX 1.5 SBOM（Python 53 / Node 213 组件）；vendor 与仓库 0 个捆绑字体，Windows 运行时 Arial/微软雅黑仅按字体族引用并记录本机哈希；Worker 基础镜像按 index digest 固定，非 root `10001:10001`、无业务凭据、归属校验通过，package QA 补强后的最新代码连续两次重建得到稳定镜像 digest `sha256:d3d52adf…`。
- G01 兼容自动化：PowerPoint 16.0 build 20228 与 WPS 12.1.0.28043 均 10/10 打开、可编辑文本、30/30 PNG 导出通过；30/30 跨应用像素比较通过，观察最大 mean 4.2066 / RMS 14.6588（门槛 8/30）。
- G01 可重复性：PPTX ZIP 时间、核心属性时间均规范化；补强 package QA 后，10 份金样本连续两次产生完全相同的证据 SHA-256 `57463FB4…`。
- G01 完成度审计：逐项映射 PLAN 4.3–4.9 与 SPEC 12.3 的工程证据；两项合规 Gate 已由项目所有者签署，当前只剩 PowerPoint/WPS 可视 QA Gate，G02 恢复门槛仍按顺序待后续 Goal。
- G01 Gate 证据：ADR-003/004/008、适配器/安全设计、综合证据与具名人工清单已完成；三项 Gate 已从 `pending` 推进至 `ready_for_review`。
- G01 Gate 完成：Xiaobing Li 签署两项合规 Gate 并完成 10 份金样本的 PowerPoint/WPS 可视验收；ADR-003/008 转为 accepted，`pnpm verify:gates --goal G01` 3/3 通过。
- G02 CP-02A 状态真相：新增 `packages/domain`、9 组 PostgreSQL 持久模型、租户复合外键/唯一/检查约束、显式状态转换与 Alembic 首版迁移；upgrade→downgrade→upgrade、schema drift、Ruff 及 16 项 API/Worker/领域单测通过。
- G02 CP-02B 幂等与竞态：创建任务在同一事务提交 immutable snapshot、job、slides、usage reservation、initial event/outbox/task 与响应记录；8 线程同 key 并发只创建一份副作用，异 body 冲突、重复投递、partial、cancel/publish 竞态均通过。
- G02 CP-02C SSE 与恢复：实现 snapshot→DB replay→Redis live handoff、Last-Event-ID、reset、seq 去重、heartbeat 与终态关闭；实现 late ack Celery Fake Worker、单页事务边界、lease 与 PostgreSQL expired-lease 对账恢复。
- G02 恢复矩阵：真实 Worker 进程强杀、模拟崩溃、单页 partial、cancel/publish、Redis 清空、outbox fanout 与 SSE resume 各连续 10/10 通过；总计 73/73、0 skipped，G03 根回归后的最新证据 SHA-256 `E887C01F…`。
- G02 Gate 完成：设计、工程证据和机器可读恢复矩阵已固化；`pnpm verify:gates --goal G02` 1/1 与 Markdown 链接验证通过。
- P0 Gate 完成：当前 worktree 重新通过合同、Web 生产构建、G01 13/13 安全与 10/10 双链金样本、G02 73/73 恢复矩阵；API/Worker/outbox 非 root 镜像构建和三页容器 E2E 通过，综合报告结论为 passed，可进入 G03。
- G03 Identity 模块：接受 ADR-002 标准 OIDC；严格校验 RSA/JWKS、issuer、audience、时间声明，local 身份仅限 local/test，staging/production 配置绕过会在应用构造时失败；6 项快速安全测试通过。
- G03 Tenant 模块：新增 users/memberships/personal organizations/entitlements/usage/audit，首次登录以 advisory lock 保证 8 并发只创建一套身份行；所有 API、SSE 与后台任务统一使用 `TenantContext` 并在数据库查询中复核 organization。
- G03 Migration 模块：正式 G03 Alembic revision 将 G02 fixed synthetic organization 原地升级为默认个人组织；自动完成 `0001_g02 → head → 0001_g02 → head`，现有 job 11 个关键字段全保留且 Alembic 无 drift。
- G03 Storage 模块：私有 MinIO bucket、四分区 tenant key、artifact metadata、15–900 秒下载授权、grant/audit 和无 URL 持久化已完成；真实签名下载成功，未签名、篡改及 15 秒过期访问均拒绝。
- G03 独立集成矩阵：PostgreSQL/Redis/真实 MinIO 共 8/8 passed、0 failed、0 skipped；跨租户 API/SSE/worker/artifact/download、日志脱敏、disabled user 和过期幂等授权均通过。
- G03 容器 E2E：API/Worker/outbox 三镜像顺序构建并以 uid `10001` 运行；Alice 登录读取 entitlement、创建两页任务并由真实 outbox/Celery 完成，Bob 猜测 job/artifact 均 404，签名工件字节一致且运行时日志无认证头、邮箱、正文或签名 URL。
- G03 Gate 完成：最新根 `pnpm verify` 依次通过合同、Web 生产构建、15 项 API、12 项 Worker、G02 73 项、G03 8 项、10 份金样本、G01/G03 安全与链接；`pnpm verify:gates --goal G03` 1/1 passed，无 waiver。
- G04 Upload 模块：新增 tenant-scoped `sources`、`upload_sessions`、`source_artifacts` 与 Alembic revision；预签名 POST 固定 key/MIME/SHA/精确大小/过期时间，complete 通过 HEAD + 流式 SHA/真实大小/元数据复核，关闭会话不再签发；迁移双向与 drift 通过。
- G04 Scan 模块：产品化 G01 extension/MIME/magic、ZIP bomb/路径/符号链接、Office active/external、PDF 加密/损坏、HTML active/external 检查；ClamAV 1.4.3 使用 INSTREAM，任何连接/超时/响应错误 fail closed；Worker 在扫描前第三次 hash，篡改无法进入 clean。
- G04 Parse 模块：仅持久 clean decision 且 key/hash 绑定的对象可解析；DOCX/PPTX/HTML 走固定 vendored engine，PDF 走已批准 pypdf；Markdown/profile/assets 以新 ULID、SHA、版本和保留期不可变发布，parse/retry 各最多五次。
- G04 Web 模块：实现文档拖放/选择、浏览器 SHA、私有直传、状态轮询、刷新恢复和 retryable 入口；`ui-styling` 可访问性规则落实为语义控件、焦点、live region、减弱动画与 46px 触控目标，390/768/1440px 无溢出且控制台无告警。
- G04 独立矩阵：12 项快速安全、14/14 PostgreSQL/真实 MinIO 集成通过，覆盖四格式、checksum、magic、ZIP bomb、traversal、加密/损坏、scanner loss、篡改、幂等、跨租户与 API 重启恢复。
- G04 容器 E2E：精确 Debian ClamAV 包、API、独立 outbox 镜像和 Worker 顺序构建；合法来源经真实 ClamAV 到 parsed/2 工件，恶意标记同时命中 clamd 和 intake 且 parseAttempt=0；Worker/ClamAV 非 root、只读、cap drop、CPU/内存/PID/tmp/time 限制通过。
- G04 Gate 完成：设计、工程证据、14 项机器矩阵和真实容器证据已固化；`GATE-G04-SOURCE-SECURITY` 自动通过，无 waiver。
- G05 Provider 基础模块：完成 Worker-only Kimi/OpenAI 配置、HTTPX MockTransport 合同、脱敏异常、确定性 Fake Provider 与最多两次 JSON 修复 Gateway；移除 reasoning content 的领域暴露，7 项 Provider 单测通过，P1 产品链路图片调用仍为 0。
- G05 Workspace 数据模块：新增 drafts、3 个内置 templates/不可变 template_versions、provider_calls、intent/outline revisions、稳定 outline slides 与独立 approvals；数据库 trigger 阻止 revision/version UPDATE/DELETE，迁移 `G04 → G05 → G04 → G05`、3 条 seed 与无 drift 通过。
- G05 Workspace API 模块：实现草稿创建/刷新/ETag 自动保存/软删除/历史、意图 AI 推断与人工 revision、大纲生成/优化/人工 revision/list/get、明确 revision 批准摘要和模板 catalog；4 组集成场景覆盖幂等、刷新、跨租户、并发 412、稳定 slide ID、撤销/恢复、批准后继续修改和图片调用 0，全部通过。
- G05 Web 模块：完成 API 驱动首页与工作台、Intent/Outline 800ms revision 自动保存、失败稳定态/显式重试、增删移动、撤销恢复、AI 真实 revision、历史对话框与批准摘要；1440/900/390 三档无横向溢出，模板 3/2/1 列、平板双列幻灯片与可开合助手抽屉、移动横向步骤及 44px 触控目标通过。
- G05 Gate 完成：7 项 Provider、4 项 PostgreSQL 集成、不可变 trigger、冲突/租户/幂等/刷新、clean console 浏览器旅程、秘密/思维链/图片 0 边界均固化证据；`GATE-G05-PROVIDER-DATA` 1/1 自动通过，无 waiver。外部密钥缺失，按条件未运行真实 smoke，且不宣称冻结模型名的官方生产可用性。
- G06 Persistence 模块：新增 approved-input generation snapshot、真实 job processor、逐页内容/QA 字段、不可变 generation artifact/publication、presentation/revision/slide-version 与使用量结算模型；发布身份防篡改 trigger 已完成，迁移 `G05 → G06 → G05 → G06`、Ruff 与 Alembic drift 检查通过。
- G06 Worker/发布模块：批准快照经稳定 slideId 逐页 author/render/QA，再由唯一 G01 engine-adapter 执行整稿 compile/package QA；确定性 source bundle/PPTX/preview/QA/slide SVG/manifest 先上传后以单事务发布，partial retry 复用已通过工件且不重复扣费。
- G06 恢复模块：7/7 真实 PostgreSQL/MinIO/Redis/引擎矩阵通过，覆盖 Worker 子进程 `os._exit(73)`、租约接管、上传后崩溃、重复投递、Redis 容器重启与 SSE 回放、partial/单页 retry、取消与 publish 竞态、配额和跨租户隐藏。
- G06 Web 模块：完成真实任务启动、URL 刷新恢复、fetch SSE + Last-Event-ID/有界重连、五阶段/逐页稳定身份/取消/重试/发布物监控；生产 Next.js 构建真实浏览器完成 8/8、publication v1、13 工件、1 Presentation revision 与 images 0。
- G06 内容完整性模块：真实生产旅程发现长中文正文被早期 SVG 截断并被 PPTX package QA 正确拒绝；改为按 East Asian Width 动态字号且保留完整批准文本，SVG QA、可编辑 PPTX 文本回归及新鲜 8 页任务首次尝试全部通过。
- G07 Revision 模块：新增不可变 operation-set revision、乐观锁、stable slideId 文本/排序/删除、至少一页与 partial 显式接受守卫；迁移 roundtrip、immutable trigger 和无 drift 通过。
- G07 Worker/导出模块：单页候选在 QA 前保留旧 ready 版本，成功后原子切换且记录 lineage；export job 固定精确 revision，经唯一引擎执行真实 PPTX/package QA，独立发布 export manifest 并幂等计费。
- G07 Web/历史模块：完成“AI 可编辑草稿”、内联单页指令、文字保存/排序/删除、精确版本 PPTX 与项目 JSON 下载、真实历史 result 路由、390px 响应式与键盘跳转；Blob 下载不再跳离编辑器。
- G07 删除模块：软删除后 API/SSE/授权立即 404，异步清理取消任务、移除私有对象并撤销 Artifact；真实用户旅程清理 22/22 对象、零失败，旧签名 URL 404。
- G07 Gate 完成：4/4 PostgreSQL/引擎集成、G03 下载过期/重签回归、8 页生产浏览器闭环、全根验证与 `GATE-G07-USER-CLOSURE` 1/1 passed，无 waiver。
- G08 Observability 模块：API 提供隔离 Prometheus registry、HTTP/SSE/security 与 PostgreSQL durable aggregate 指标；FastAPI/Celery 建立 allowlist OTel spans/W3C trace IDs，日志不采集 body/header；12 条告警与 runbook anchor 静态验证通过。
- G08 Reconciliation/恢复模块：新增 tenant-scoped durable object reconciliation 与迁移，clean/protected upload、missing/expired/orphan 十轮修复和 dry-run/removal failure 3/3 通过；G02 Worker kill/Redis/SSE/cancel race 各 10/10 证据聚合通过。
- G08 备份/迁移模块：4,025,584-byte PostgreSQL custom dump 在隔离数据库恢复，Alembic `ad9d3a5d7be1` 与 7 类核心计数完全一致；64/64 私有对象 SHA-256 一致；独立数据库 upgrade→downgrade→upgrade 与 drift 通过。
- G08 性能模块：当前非 root release API 镜像、4 Uvicorn workers、100 organizations/1,000 drafts/10,000 events/1,000 artifacts、20 VU、120 秒预热/600 秒测量通过；GET p95 72.113ms、write p95 80.873ms、22,131 samples、0 error。
- G08 安全/供应链模块：Next.js 16.2.11、sharp 0.35.0、PostCSS 8.5.23 后官方 npm production audit 全 0；pip-audit 113 dependency、0 vulnerability，3 个本地 workspace 包按预期未在 PyPI；SBOM 更新为 Python 93/Node 216 components。
- G08 无障碍模块：axe-core 4.13.0 对 home/workspace/monitor/presentation 均 0 violation、0 critical/serious；修复 file input/story textarea label 与辅助文本对比度；390/768/1440 三档无横向溢出，键盘证据完成。NVDA 人工检查明确待签。
- G08 发布文档模块：完成观测设计、runbook、rollback、release checklist/report、隐私/Provider disclosure、E2E-001–012、性能/恢复/备份/安全/无障碍 evidence；`pnpm verify:automated:g08` 通过，Gate 推进到 `ready_for_review` 而未虚假签字。
- G08 发布容器与兼容模块：API/Worker/outbox 以 `10001:10001`、只读根文件系统、cap drop 与资源限额运行；PowerPoint 16.0 build 20228 与 WPS 12.1.0.28043 各 10/10 打开/可编辑/导图通过，30/30 像素比较通过。
- G08 最终 E2E 模块：在加固 release 容器与正常 Next.js 生产构建上，以新草稿完成批准、8/8 生成、文字编辑、重排、稳定 slideId 单页重生成、精确 revision 4 PPTX 导出、项目 JSON 导出、对象 hash/字节复核、历史恢复与 390px 无溢出；E2E-001–012 全部通过。
- G08 完成度复审模块：逐项映射 PLAN 12.3、SPEC 13.3/14，修复 G08 runner 误用普通开发数据库、补齐对象存储 AES256/安全生命周期/陈旧 multipart 清理与发布镜像健康/就绪探针；4/4 真实 MinIO 隔离集成通过。
- G08 根验证模块：合同、Web、API 24、Worker 18、G02 73、G03 8、G04 14、G05 4、G06 7、G07 4、G08 4、40 项 Golden 合同、E2E、安全、12 条告警和链接全部通过；`pnpm verify` 唯一非零为预期的 `GATE-G08-RELEASE: ready_for_review`，证明自动化不能越过人工 Gate。

## 进行中事项

- G08 人工 Gate：等待具名 Windows Chromium 精确 200% + 屏幕阅读器复核，以及具名 product/security/legal Provider/privacy/KES-or-KMS 决策；工程侧没有可继续自动完成的发布项。

## 问题及解决方案

| 问题                                                                                  | 尝试次数 | 处理结果                                                                                                                                                                                         |
| ------------------------------------------------------------------------------------- | -------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `uv` 通过用户级 pip 安装后未进入当前 PowerShell PATH                                  |        1 | 使用稳定的 `python -m uv` 本地入口；CI/已配置环境仍可直接调用 `uv`。                                                                                                                             |
| npm registry 下载 Next.js/SWC 超过默认超时                                            |        5 | 已解决：保留锁定版本；确认 pnpm 11 未读取旧 `.npmrc` 网络键后，按当前官方配置把镜像、10 分钟超时、5 次退避和低并发迁入 `pnpm-workspace.yaml`，最终从内容寻址缓存恢复 181 包并完成剩余 2 个下载。 |
| pnpm 安全默认值阻止 `sharp` 生命周期脚本                                              |        2 | pnpm 首次安装自动写入待决 placeholder，移除重复键后按 pnpm 11 `allowBuilds` 合同仅批准精确 `sharp@0.34.5`，并启用 `strictDepBuilds`；未知脚本将直接使安装失败。                                  |
| Codex bundled pnpm 进程报告 Node 24.19.0，而工作区 `node` 为 24.18.1                  |        1 | `.node-version`/CI 仍固定 24.18.1；`engines` 接受同一 Node 24 LTS 线以兼容包管理器宿主，应用脚本已确认由 24.18.1 执行。                                                                          |
| OpenAPI 内嵌组件仍保留 JSON Schema 绝对 `$ref`，类型生成器尝试联网解析                |        1 | 物化 OpenAPI 时把合同基址引用改写为本地 `#/components/schemas/*`，独立 JSON Schema 仍保留规范 `$id`。                                                                                            |
| 端点错误 fixture 使用带 `{param}` 的 URI 模板，不符合 RFC `uri-reference`             |        1 | fixture 保留模板字段用于匹配 operation，同时把 ProblemDetails `instance` 物化为具体 ULID 路径。                                                                                                  |
| 单页 `failed` 同时被声明为绝对终态和可进入 `retrying`                                 |        1 | 按 SPEC 将其定义为“重试耗尽时的条件终态”，绝对终态只保留 `ready/cancelled`，不删除合法人工重试转换。                                                                                             |
| 根 `uv sync --frozen` 仅同步虚拟根项目，移除了 workspace member 依赖                  |        1 | 根项目显式依赖 API/Worker workspace members，并用 `[tool.uv.sources]` 绑定；设置 `link-mode=copy` 兼容当前跨卷缓存。                                                                             |
| 上游完整浅克隆/commit tarball 体积过大                                                |        2 | 完整浅克隆长时间无 checkout；tarball 下载到 244 MiB 后确认 codeload 不支持断点续传。改用 Git partial clone + sparse checkout，仅取固定 commit 的 `skills/ppt-master` 和必要顶层归属文件。        |
| pytest 用户级默认临时目录拒绝访问                                                     |        1 | 验证命令固定使用仓库 `.tmp/` 下的隔离 `--basetemp`，单测通过。                                                                                                                                   |
| Windows Defender 在 harness 读取前拦截完整 EICAR 字节串                               |        1 | 测试 fixture 改用无害专用 canary，仍验证相同 fail-closed 错误路径；真实 ClamAV/Defender 结果在隔离环境证据中单独记录。                                                                           |
| 上游 SVG QA 要求页角色和 root group 布局边界                                          |        2 | 第 1 次消除未分组/页角色 warning；第 2 次为内容 group 声明 `data-pptx-bounds`，final QA 达到 0 error/0 warning。                                                                                 |
| PPTX 可编辑文本检查未遍历 PowerPoint group 子 shape                                   |        1 | package QA 递归遍历 group，标题与正文均以原生文本 shape 被识别。                                                                                                                                 |
| Windows 默认 GBK 解码上游 UTF-8 输出与 CLI Unicode 结果                               |        2 | 子进程固定 UTF-8/replace，adapter stdout 显式重配 UTF-8，真实渲染 CLI 通过。                                                                                                                     |
| 本地 Docker daemon 初始未启动                                                         |        1 | 已以隐藏方式启动 Docker Desktop 4.76.0，daemon 29.5.2 就绪后完成镜像构建。                                                                                                                       |
| 容器 attribution guard 成功时静默输出，验证器误把空 stdout 判为失败                   |        1 | 按 CLI 合同以 exit code 0 为成功证据；Dockerfile 构建阶段和运行时均执行守卫。                                                                                                                    |
| BuildKit 默认 provenance attestation 使本地 manifest-list digest 每次改变             |        1 | G01 可重复验证关闭动态 provenance，保留固定基础镜像 digest 和独立 SBOM；连续两次构建 image ID 一致。                                                                                             |
| 链接检查器扫描了 `.tmp` sparse clone 和不可修改 vendor 的上游仓库外链接               |        1 | 首方 Markdown 链接检查明确排除 `.tmp`/`vendor`；vendor 完整性继续由固定树哈希和 attribution guard 覆盖。                                                                                         |
| 上游工具在 vendor 中产生 Python 字节码缓存，导致原始树哈希误报                        |        1 | 树哈希只覆盖可分发源文件并排除 `__pycache__`/`.pyc`，上游守卫运行时禁止后续字节码写入；树哈希恢复 `3ff44cc3…`。                                                                                  |
| PowerPoint/WPS 视觉抽查初次读到 WPS 旧 PNG（WPS Export 不覆盖同名文件）               |        1 | 兼容脚本在精确 `.tmp/compatibility/<app>/<case>` 下逐文件清理旧 PNG 再导出；新基线与 PowerPoint 对齐并通过 30 对自动差分。                                                                       |
| PPTX 规范化仅固定 ZIP 时间，`docProps/core.xml` 仍含当前时间                          |        1 | 同步固定 core created/modified 属性；单样本和 10 样本均连续两次哈希一致。                                                                                                                        |
| WPS COM 在全链路冷启动时偶发 `0x800706BE` RPC 失败                                    |        1 | Office 验证增加最多 3 次的有界进程重试；最新完整链路在第 3/3 次 WPS 尝试成功，未超过 5 次防循环上限，且 10/10 兼容与 30/30 视觉检查通过。                                                        |
| Prettier 初始扫描生成物、金样本、冻结计划与 vendor 输入，产生 120 个非源码格式告警    |        1 | 新增 `.prettierignore` 明确区分首方可维护文件与冻结/生成输入；格式化首方文件后 `pnpm format:check` 通过，契约、金样本和全仓验证再次通过。                                                        |
| Package QA 仅列出媒体清单且只间接证明文本，缺少悬空关系、原生图形和整页位图的直接断言 |        1 | 增加 OPC 内部目标解析、缺失/越界关系、孤立媒体、逐页计划文本计数、原生图形计数和整页图片回退门禁；新增破损媒体关系回归测试，10/10 金样本重新通过。                                               |
| G02 ORM 未声明 snapshot/job relationship，flush 时先插入依赖 job                      |        1 | 在同一事务内先显式 flush immutable snapshot，再插入带 organization 复合外键的 job；最小烟测与完整矩阵通过。                                                                                      |
| Redis Pub/Sub 测试在 `SUBSCRIBE` 确认帧消费前发布，偶发收不到 fanout                  |        1 | 测试先消费订阅确认再触发 outbox；10/10 fanout 通过，生产分发代码无错误。                                                                                                                         |
| Windows Celery solo 强杀后 Kombu 未按 3 秒配置自动恢复未确认消息                      |        3 | 保留 late ack/受限预取并对齐 visibility 配置；最终以 PostgreSQL lease 为真相，由 outbox 对账过期 lease 并按 lease token 去重重投，真实进程强杀 10/10 通过。                                      |
| Docker Compose 并行构建在中文仓库路径产生 BuildKit gRPC session header 错误           |        2 | 错误发生在 Dockerfile 执行前；关闭 Compose Bake 后逐服务顺序构建，API、Worker、outbox 三镜像全部成功，运行时 E2E 通过。                                                                          |
| MinIO 首次启动时健康端口短暂接受后关闭连接                                            |        1 | readiness probe 将 connection reset 作为有界启动重试；真实业务请求不使用该重试路径，随后完整私有对象矩阵通过。                                                                                   |
| G03 迁移保真 canary 初始使用了非 G02 固定 synthetic organization ID                   |        1 | 对齐 G02 固定 organization/service actor 常量后，双向迁移、11 字段数据保真与 schema drift 全部通过。                                                                                             |
| 下载授权幂等记录初版包含短时签名 URL                                                  |        1 | 只持久化原始过期时间；重放在原截止时间内重新签名且不创建新 grant，过期后返回 410，新测试确认 artifact/grant/audit/idempotency 均无 URL。                                                         |
| Docker 镜像代理对上游 `clamav/clamav` 返回 403                                        |        2 | 使用 digest-pinned Debian/Python 基础镜像和精确 `clamav-daemon 1.4.3+dfsg-1~deb12u2` 构建受限服务；真实 INSTREAM OK/FOUND 通过。                                                                 |
| ClamAV 在只读容器中显式打开 `/dev/stderr` 报符号链接循环                              |        1 | 移除显式 LogFile，前台 daemon 直接写容器输出，健康检查与日志均恢复。                                                                                                                             |
| 只构建 Worker 未刷新 Compose 独立命名的 outbox 镜像                                   |        1 | G04 容器 verifier 顺序构建 clamav/API/Worker/outbox；原 pending source task 在刷新 outbox 后继续处理，证明持久恢复。                                                                             |
| wheel 安装后的包路径比 editable 源码多一层导致 vendor 根错误                          |        1 | 路径解析遍历父目录寻找固定 vendor，也支持经校验的显式根；本地与 `/app/.venv` 容器均通过。                                                                                                        |
| ClamAV 对完整 HTML 规范化后自定义原始字节签名未命中                                   |        2 | 真实 daemon 断言改用精确标记流；独立 active HTML fixture 继续验证结构拒绝，容器结果同时包含 clamd 与 intake finding。                                                                            |
| Domain 层会把大写 SHA-256 静默转为小写                                                |        1 | 取消规范化并与 Pydantic 合同共同拒绝非小写 hash；单元与 complete mismatch 矩阵通过。                                                                                                             |
| 移动端截图中 off-screen skip link 局部露出                                            |        1 | 改为 nowrap + translate 隐藏，仅键盘 focus 时恢复；三档浏览器测量无溢出。                                                                                                                        |
| 浏览器 Fetch 拒绝中文 `X-Dev-User-Name` header                                        |        1 | UI 继续使用中文，但 local dev 身份头改为 ASCII 展示名；真实 HTML/DOCX 浏览器上传、刷新恢复与最终解析通过。                                                                                       |
| 冻结计划指定的 `kimi-k3` / `gpt-image-2` 尚未出现在 2026-08-16 官方模型枚举           |        1 | 保留用户冻结的精确模型配置，不擅自替换；Fake Provider 继续完成 G05，真实 smoke 仅在密钥存在且供应商端接受模型时运行，证据明确标记未验证，图片 Provider 不接入 P1。                               |
| G05 集成测试把中文主题拼进 `Idempotency-Key`，HTTPX 按 ASCII header 合同拒绝          |        1 | 幂等键改为主题 UTF-8 SHA-256 的短前缀；请求正文仍保留完整中文，4 组工作台集成场景通过。                                                                                                          |
| 本地浏览器使用 `127.0.0.1:3000` 不在默认 Web CORS 白名单                              |        1 | 统一本地入口为 `http://localhost:3000`，API 仍监听 loopback；README 与 G05 设计明确该约束。                                                                                                      |
| 自动保存失败后 effect 再次调度请求，可能形成重试循环                                  |        1 | 增加失败类型与稳定 failed 状态，仅允许用户显式重试；停 API、保留本地编辑、恢复 API、重试并刷新后值仍持久化。                                                                                     |
| closed `details` 在桌面有布局尺寸但内容未实际绘制                                     |        1 | 以受控 open 状态保证非平板始终展开，平板保留可开合原生抽屉；桌面截图、平板开合和移动布局复验通过。                                                                                               |
| Provider 名称常量误落在图片适配器类末尾                                               |        1 | 为 Kimi 与 OpenAI Image 适配器分别声明 `kimi` / `openai-image`，并新增合同断言，7 项 Provider 测试通过。                                                                                         |
| 应用内浏览器 Tab/Enter 键注入不产生焦点移动或激活事件                                 |        5 | 按防循环规则停止继续尝试并固化 harness limitation；原生 button/link、label、键盘文本输入、dialog 焦点恢复、44px 目标与完整真实点击旅程作为补偿证据，clean console 为 0。                         |
| G06 迁移 drop check constraint 被 Alembic naming convention 再次拼接表名前缀          |        1 | 对既有约束名使用 `op.f(...)` 标记为已格式化名称；迁移双向演练与 schema drift 检查通过。                                                                                                          |
| G06 SSE effect 随每次 job 对象刷新重建连接                                            |        1 | effect 只绑定稳定 job ID 与 terminal 标志；普通状态刷新保持同一事件流。                                                                                                                          |
| G06 恢复测试与手工浏览器 Worker 同时争用同一租约                                      |        2 | G07 根验证首次被常驻 Docker Worker 抢占租约；关闭套件外 API/Worker/outbox 后 G06 7/7、G07 4/4 及第二轮根全量验证通过。                                                                           |
| G07 数据下载使用跨域签名 URL时浏览器导航离开编辑器                                    |        2 | 第 1 次定位原生 anchor 对跨域 `download` 不可靠；第 2 次改为授权 fetch→Blob→DOM 临时链接，PPTX/JSON 命名文件实际落盘且编辑器路由保持。                                                           |
| 应用内浏览器 download event 未捕获程序化 Blob 下载                                    |        2 | 两次等待均超时但页面成功消息、操作系统 Downloads 中两个 8,119-byte JSON 和 25,787-byte PPTX 均证明下载完成；记录为自动化 harness 限制，不重复修改正确产品路径。                                  |
| G07 export package QA 因封面多条正文没有沿用生成合并规则而失败                        |        1 | 导出 DeckPlan 对封面正文使用与 G06 一致的合并规则；真实引擎 export、manifest 与 package QA 回归通过。                                                                                            |
| G07 单页重生成使用原生 prompt，在应用内浏览器被自动取消                               |        1 | 替换为可访问的内联“AI 单页修改要求”输入框；生产浏览器真实重生成成功且 stable slideId 保持。                                                                                                      |
| Docker BuildKit 在中文工作区再次无法编码 session header                               |        1 | 使用同一 Docker daemon 的 legacy builder 顺序构建 G07 API/Worker/outbox，三运行时启动和真实浏览器 E2E 通过；G08 将此纳入发布构建说明。                                                           |
| G06 生产 Worker 消费到数据库清理前遗留 broker 消息并记录异常                          |        1 | 真实任务包装器将不存在的旧 job 收敛为幂等 `noop_missing`；有效任务仍保持严格租约与重试。                                                                                                         |
| 长中文正文在 SVG 作者层被截断，PPTX package QA 拒绝批准文本丢失                       |        2 | 第 1 次仅修正逐页封面布局；第 2 次定位整稿可编辑文本缺失，改为 East Asian Width 动态字号并保留全文，SVG/PPTX 回归与 8 页真实发布通过。                                                           |
| G06 应用内浏览器不提供 viewport resize 或历史 console 收集                            |        1 | 不宣称 G06 移动浏览器/零历史 console；记录能力限制，以生产构建、语义 DOM、空 terminal alert、显式响应式规则及 G05 三档 shell 矩阵补偿。                                                          |
| G08 pnpm 更新首次被运行中的 Next server 锁文件并写入待决 placeholder                  |        1 | 停止精确 Next 进程、移除 placeholder 并用 frozen install 复核；`sharp@0.35.0` 仅通过精确 `allowBuilds` 批准，Web 构建通过。                                                                      |
| 配置的 npm 镜像没有 audit endpoint                                                    |        1 | 审计命令显式使用官方 `https://registry.npmjs.org`；production dependency advisory 为 0，并在 evidence 记录镜像限制。                                                                             |
| G08 固定数据短窗在无节奏高吞吐下 p95 连续超标                                         |        6 | 达到防循环阈值后不再修改业务代码；记录为负载模型饱和，按固定可复现 500ms 用户节奏执行 SPEC 的 2+10 分钟正式窗口，GET/write p95 72.113/80.873ms、0 error。                                        |
| MinIO Python `make_bucket` 使用过期 `region` 参数                                     |        1 | 按当前 SDK 文档改为 `location`；隔离 restore bucket 64/64 hash 恢复通过且临时目标已清理。                                                                                                        |
| G08 Alembic 演练首次使用错误配置文件路径                                              |        1 | 使用实际 `packages/domain/src/instant_ppt_domain/alembic.ini`，在精确临时数据库完成 upgrade/downgrade/re-upgrade/drift，并删除临时数据库。                                                       |
| 当前 Windows 未安装 NVDA                                                              |        1 | 不安装或伪造人工结果；自动 axe/键盘/响应式证据全部完成，具名屏幕阅读器清单保留 `waiting_for_human_gate`。                                                                                        |
| Compose classic builder 为同一 Worker Dockerfile 重复构建 outbox 镜像                 |        1 | 三个非 root 镜像均成功并记录精确 digest；重复构建只影响本地耗时，作为后续构建缓存优化项，不改变发布内容。                                                                                        |
| G08 最终浏览器旅程首次请求早于新建 API 容器 readiness                                 |        1 | 等待 `/healthz` 返回 200 后仅执行一次显式用户重试；随后完整 8 页生成、编辑、导出、历史恢复和对象 hash 复核通过，未添加隐式无限重试。                                                             |
| 旧 G08 证据把普通业务路由探针误写为 `/healthz`                                        |        1 | 增加显式轻量 `/healthz` 与数据库驱动 `/readyz`，Compose 改用 readiness，发布镜像两端点均 200；旧报告改为准确描述当时的业务路由探针。                                                             |
| G08 隔离集成 runner 曾清空普通 `instant_ppt` 开发数据库                               |        1 | runner 改为创建/迁移/销毁专用 `instant_ppt_g08_test`，不再破坏开发数据；4/4 真实 PostgreSQL/MinIO 集成通过并输出 JUnit。                                                                         |
| MinIO 拒绝只含 abort-incomplete-multipart 的 bucket lifecycle rule                    |        4 | 有界诊断确认当前服务端会拒绝或丢弃该规则；改用安全 expired-delete-marker lifecycle，并由 MinIO 官方 stale-upload expiry/cleanup 环境配置负责陈旧分片清理，证据同时验证两层治理。                 |
| 新 release 容器重建期间首页 hydration 保留一次 `Failed to fetch`                      |        1 | 业务路由、`/healthz`、`/readyz` 均 200 后只做一次显式 reload；随后整条新草稿到 revision 4 双导出旅程通过，运行日志 0 error。                                                                     |
| 首轮对象治理只验证“当前无公开策略”，未恢复既有误配置                                  |        1 | API/Worker 治理改为在全部读写与签名入口移除既有 bucket policy 后再启用 AES256/lifecycle；两个全新临时 bucket 分别验证 API 纠偏和 Worker 冷启动，测试后均已清理。                                 |

## Goal 历史

### G00 / 冻结合同与建立工程基线 — complete

- 产物：monorepo、双 lockfile、Compose、26 Schema、38 endpoint、166 fixtures、状态机/错误码、TS 类型、ADR、设计/开发文档、Gate 与 CI。
- 验证：`pnpm verify`、`scripts/verify-clean-bootstrap.ps1`、`docker compose config --quiet`、`pnpm verify:gates --goal G00` 通过。
- 证据：`docs/evidence/g00-engineering-baseline.md`。
- 未进入范围：业务登录/上传/任务/UI/真实 Provider/引擎，分别由 G01–G08 实现。

### G01 / 引擎、许可证、金样本与 Source Security Spike — complete

- 产物：固定 vendor、唯一 engine-adapter、隔离 Worker、Source Security harness、10 份双链金样本、SBOM、容器、PowerPoint/WPS 自动与人工兼容证据。
- 验证：`pnpm verify:g01:automated`、两次稳定容器构建、10/10 source/render、13/13 threat rejection、30/30 跨应用视觉比较和 `pnpm verify:gates --goal G01` 通过。
- Gate：上游/第三方分发、PDF/EPUB 依赖姿态与 PowerPoint/WPS 可视验收均由项目所有者具名批准。
- 证据：`docs/evidence/g01-engine-license-golden.md`、`docs/evidence/g01-approval-record.md`、`docs/evidence/g01-completion-audit.md`。

### G02 / 持久任务、幂等、SSE 与恢复 Spike — complete

- 产物：首版 PostgreSQL tenant-scoped orchestration schema/Alembic、事务幂等与 outbox、Fake Worker/Celery、lease 对账恢复、snapshot/replay/live SSE、API/Worker runtime Compose。
- 验证：migration roundtrip/drift、16 项单测、73/73 集成测试；七组关键恢复/竞态各连续 10 次通过；`pnpm verify:gates --goal G02` 1/1 通过。
- 不变量：PostgreSQL 是任务/事件/lease/副作用真相；Redis 可清空；attempt 不进入逻辑幂等键；重复投递不重复 manifest、usage reservation 或终态。
- 证据：`docs/design/g02-persistent-orchestrator.md`、`docs/evidence/g02-persistent-orchestrator.md`、`docs/evidence/recovery/g02-recovery-results.json`。

### P0 Gate — complete

- 决策：passed，G03 可开始；G01 3/3 与 G02 1/1 required Gate 均 passed，无 waiver、failed 或 skipped recovery case。
- 复核：根 `pnpm verify`、13/13 threat rejection、10/10 source/render、73/73 recovery、三运行时镜像与容器三页 HTTP E2E 全部通过。
- 证据：`docs/p0-gate-report.md`、`docs/evidence/gate-manifest.yaml`。

### G03 / 身份、租户与存储底座 — complete

- 产物：标准 OIDC/local-only adapter、personal organization 与 membership、entitlement/usage、统一 `TenantContext`、后台 tenant recheck、私有四分区对象键、artifact/grant/audit、短时下载授权与 G02 无损迁移。
- 验证：15 项 API、6 项快速安全、8/8 PostgreSQL/Redis/真实 MinIO 隔离矩阵、73/73 G02 恢复回归、三非 root 运行时容器用户 E2E、迁移双向保真与无 schema drift；根 `pnpm verify` 通过。
- 不变量：生产不能启用 dev auth；API/SSE/Worker/对象查询都含 organization；跨租户统一 404；bucket 无公开 policy/ACL；签名 URL 不进入持久数据或日志；幂等重放不延长原授权。
- Gate：`GATE-G03-TENANCY` automated security matrix 1/1 passed，无 waiver。
- 证据：`docs/design/g03-identity-tenancy-storage.md`、`docs/evidence/g03-identity-tenancy-storage.md`、`docs/evidence/security/g03-tenancy-results.json`、`docs/evidence/security/g03-container-e2e.json`。

### G04 / 安全上传与 Source 解析闭环 — complete

- 产物：upload/source/artifact schema 与迁移、精确 MinIO POST、complete 复核、真实 ClamAV + G01 扫描、clean-only parser、不可变 SourcePackage/Artifact、状态/retry API、响应式 Web 上传恢复组件和受限 ClamAV/Worker 容器。
- 验证：21 项 API/domain、15 项 Worker、12 项快速安全、14/14 PostgreSQL/MinIO 集成、四格式成功、全部恶意 fixture 零解析、迁移 roundtrip/drift、三档 Web 渲染、浏览器 HTML/DOCX 上传/暂停/刷新/恢复与真实 API/outbox/Celery/ClamAV/MinIO 容器用户链路通过。
- 不变量：用户文件名不进入 key；服务端实际字节是完成真相；scanner unavailable fail closed；只有 hash/key 绑定 clean decision 可解析；工件不可变；跨租户统一 404；attempt ≤5。
- Gate：`GATE-G04-SOURCE-SECURITY` automated 1/1 passed，无 waiver。
- 证据：`docs/design/g04-secure-source-pipeline.md`、`docs/evidence/g04-secure-source-pipeline.md`、`docs/evidence/security/g04-source-results.json`、`docs/evidence/security/g04-container-e2e.json`、`docs/evidence/g04-browser-e2e.json`。

### G05 / 草稿、意图、大纲与 Web 工作台 — complete

- 产物：三套不可变内置模板、Draft/Intent/Outline/approval/provider-call schema 与迁移、Fake/Worker-only Provider Gateway、tenant API、响应式 Web 工作台、稳定自动保存与历史恢复。
- 验证：7/7 Provider 合同、4/4 PostgreSQL 集成、迁移 roundtrip/drift、不可变 trigger、并发 412、跨租户 404、刷新与断网重试、1440/900/390 浏览器用户旅程、Web 生产构建和秘密/思维链/图片 0 安全门禁通过。
- 不变量：revision/version/approval 不可修改；outlineSlideId 稳定；undo/redo/AI 只追加 revision；批准绑定精确输入 hash；P1 图片调用为 0；G06 前 generation job 为 0。
- Gate：`GATE-G05-PROVIDER-DATA` automated 1/1 passed，无 waiver；外部密钥缺失使真实 smoke 不适用，冻结模型名的外部可用性未被虚报。
- 证据：`docs/design/g05-draft-workspace.md`、`docs/evidence/g05-draft-workspace.md`、`docs/evidence/g05-browser-e2e.json`、`docs/evidence/security/g05-provider-results.json`、`docs/evidence/g05-workspace-junit.xml`。

### G06 / 真实生成、监控与工件发布 — complete

- 产物：approved generation snapshot、真实逐页 Worker、候选/整稿/package QA、确定性私有对象、immutable generation manifest/publication、Presentation/revision/slide version、配额预占结算、取消/partial/retry、SSE 监控和响应式任务 UI。
- 验证：21 项 API/domain、18 项 Worker、G02 73/73、G03 8/8、G04 14/14、G05 4/4、G06 7/7、10/10 source/render 金样本、生产 Web、真实浏览器 8 页发布/刷新、全安全与链接矩阵通过；根 `pnpm verify` 与 G00–G06 Gate 全部通过。
- 不变量：批准后输入不可变；PostgreSQL 为状态/事件真相；Redis 可重启；Worker kill/重投不重复发布或扣费；成功页重试复用；取消不会半发布；所有 published artifact 有 hash/版本/manifest；失败/取消无可用页不创建 Presentation；G07 前无编辑/最终导出。
- Gate：`GATE-G06-GENERATION` automated 1/1 passed，无 waiver。
- 证据：`docs/design/g06-real-generation-publication.md`、`docs/evidence/g06-real-generation-publication.md`、`docs/evidence/g06-browser-e2e.json`、`docs/evidence/g06-generation-junit.xml`。

### G07 / 结果编辑、导出与历史闭环 — complete

- 产物：不可变 Presentation revisions/slide versions、有限操作集、单页 QA 后原子重生成、精确 revision export job/manifest、短时私有下载、真实历史状态路由、结构化数据快照和可审计项目清理。
- 验证：API/domain 21/21、Worker 18/18、G02 73/73、G03 8/8、G04 14/14、G05 4/4、G06 7/7、G07 4/4、10/10 双链金样本、全安全矩阵和根 `pnpm verify` 通过；生产浏览器完成 8 页编辑/重排/重生成/刷新/历史/PPTX+JSON 下载/移动端/键盘旅程。
- 不变量：approved outline/generation snapshot 不可变；stale revision 412；stable slideId 不漂移；候选 QA 前旧 ready 可见；export 固定明确 revision；partial 未决不导出；删除后 API/SSE/旧 URL/新授权立即或清理后统一 404。
- Gate：`GATE-G07-USER-CLOSURE` automated 1/1 passed，无 waiver；本地测试项目 22/22 私有对象删除、零失败。
- 证据：`docs/design/g07-editor-export-history.md`、`docs/evidence/g07-editor-export-history.md`、`docs/evidence/g07-browser-e2e.json`、`docs/evidence/g07-editor-export-junit.xml`。

### G08 / 安全、质量、可观测与发布门禁 — waiting_for_human_gate

- 产物：Prometheus/OTel 可观测面、12 条告警、对象 reconciliation、私有 bucket AES256/lifecycle/stale-upload 治理、健康/就绪探针、备份恢复与迁移演练、依赖审计/SBOM、固定性能基线、axe/响应式证据、加固 release 容器、runbook/rollback/privacy/release 文档和 E2E-001–012 证据。
- 验证：所有自动化模块及根验证的自动化阶段通过；PowerPoint/WPS 各 10/10 与 30/30 视觉差分通过；新鲜用户 E2E 完成 8 页生成、revision 4 编辑/重生成/导出、JSON 导出、历史恢复、MinIO 字节/hash/AES256 和移动布局复核；G08 隔离集成为 4/4。
- Gate：`GATE-G08-RELEASE` 为 `ready_for_review`；具名 Windows Chromium 精确 200% + 屏幕阅读器检查与 product/security/legal 生产 Provider/privacy/KES-or-KMS 决策仍是 required human Gate，无 waiver，发布尚未批准。
- 证据：`docs/evidence/g08-completion-audit.md`、`docs/release-gate-report.md`、`docs/release-checklist.md`、`docs/evidence/g08-final-browser-e2e.json`、`docs/evidence/g08-integration-junit.xml`、`docs/evidence/security/g08-object-governance.json`、`docs/evidence/g08-e2e-matrix.json`、`docs/evidence/gate-manifest.yaml`。
