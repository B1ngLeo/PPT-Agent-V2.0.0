# 即刻AI-PPT development progress

> Updated: 2026-08-16. This file is updated after every completed module. A single repeated defect may be attempted at most five times; on a sixth failure it is recorded here and deferred while independent work continues.

## 当前 Goal

- Goal：G04 / 安全上传与 Source 解析闭环
- 状态：in_progress
- 当前检查点：G03 Gate 与根验证完成，读取 G04 上传/扫描/解析合同并设计产品化安全流水线
- 已验证：G00–G03 complete；P0 Gate passed；G01 required Gate 3/3、G02 1/1、G03 1/1 均通过且无 waiver；最新根 `pnpm verify` 通过
- 剩余工作：G04 上传会话、直传复核、quarantine→scan→clean→parse、恢复/安全矩阵、容器沙箱与 Gate
- 决策/偏离：G03 采用标准 OIDC 和私有 MinIO，完整保留 G02 数据；G04 复用 G01 threat rules 并产品化，不降低既有 fail-closed 门槛；无 SPEC 偏离
- 阻塞：无
- 恢复记录：无当前恢复项；全部重复问题均在 3 次以内解决

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

## 进行中事项

- G04：读取 PLAN 8 与 SPEC FR-SOURCE、数据治理、安全边界，盘点 G01 可复用 intake harness，冻结上传会话/对象状态/扫描解析事务设计。

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
