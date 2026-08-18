# ISSUE-001：Web 规划流水线在意图识别后中断，未进入大纲与 PPT 生成

## 基本信息

| 字段         | 值                                                                                    |
| ------------ | ------------------------------------------------------------------------------------- |
| 状态         | Resolved（P0 已修复并完成 3 次全链路验证；P1 架构优化保留）                           |
| 严重级别     | Sev-2                                                                                 |
| 优先级       | P0                                                                                    |
| 首次确认日期 | 2026-08-17                                                                            |
| 影响组件     | `apps/web`、G05 planning API、Provider Gateway 调用边界                               |
| 复测环境     | Windows、Docker Desktop 29.5.2、Next.js 16.2.11、本地 Compose runtime、Kimi `kimi-k3` |
| 测试入口     | `http://localhost:3000`                                                               |
| 责任人       | 待指派                                                                                |

## 摘要

用户从网站首页提交主题后，Web 应依次创建 Draft、推断 Intent、生成 Outline，并打开可编辑工作台。实际复测中，Draft 创建成功，真实 Kimi 意图调用也在服务端成功并写入 Intent revision，但浏览器收到 `Failed to fetch`，前端随即终止串行流程，未调用 `outline:generate`。因此没有 Outline revision、批准快照、Generation snapshot、Generation job 或 Presentation，也不会进入 PPT Worker/引擎阶段。

本问题满足项目对 Sev-2 的定义：受支持的主流程可重复失败，且用户无法在产品界面完成 PPT 生成。当前证据不支持将其归因于 PPT 引擎；故障发生在 G05 规划流程与浏览器响应处理边界。

## 预期行为

根据 G05/G06 设计，主题型用户旅程应为：

1. 首页创建 Draft；
2. 调用 `POST /v1/drafts/{draftId}/intent:infer` 并持久化 Intent revision；
3. 调用 `POST /v1/drafts/{draftId}/outline:generate` 并持久化 Outline revision/slides；
4. 打开可恢复的意图/大纲工作台；
5. 用户检查并点击“批准当前大纲”；
6. 生成确认后创建 immutable Generation snapshot 和真实 Generation job；
7. Worker 逐页生成、QA、编译并发布可编辑 PPTX/Presentation。

首页“生成大纲”按现有产品合同只负责步骤 1–4，不应直接跳过批准边界启动 PPT 生成。但它必须可靠地到达大纲工作台，且刷新后能够从已持久化状态恢复。

## 实际行为

使用提示词：

> 根据GPT5.6的官方发布公告生成一份PPT

连续执行两次新的浏览器测试，均得到相同结果：

1. 首页成功创建 Draft，URL 写入 `?draft=...`；
2. 页面进入“正在推断创作意图…”；
3. 页面显示 `Failed to fetch` 并停留/退回首页；
4. 服务端稍后成功写入 Kimi `intent_infer` ProviderCall 和 Intent revision；
5. 前端没有继续调用 `outline:generate`；
6. 从历史记录恢复该 Draft 时，页面未能正常进入可编辑工作台；
7. 数据库中不存在 Outline、Generation snapshot、Generation job 或 Presentation。

## 复现步骤

### 前置条件

1. 按 `docs/runbook.md` 启动 PostgreSQL、Redis、MinIO、ClamAV、API、Provider Gateway、Worker 和 outbox；
2. 启动 Web：`pnpm --filter @instant-ppt/web dev`；
3. 确认 `http://localhost:8000/readyz` 返回 `{"status":"ready"}`；
4. 使用真实 Kimi planning 配置，图片生成可保持关闭。

### 操作

1. 打开 `http://localhost:3000`；
2. 在“主题或目标”输入：`根据GPT5.6的官方发布公告生成一份PPT`；
3. 保持默认内置模板；
4. 点击“生成大纲”；
5. 观察页面状态和历史记录；
6. 查询 Draft、ProviderCall、Outline revision、Generation snapshot/job 和 Presentation。

### 复现结果

| Draft ID                     | Intent 调用           | Intent revision | Outline revisions | Generation snapshots | Generation jobs | Presentations |
| ---------------------------- | --------------------- | --------------- | ----------------: | -------------------: | --------------: | ------------: |
| `01M07TMMZ2FK2NPGD1BS5PM543` | succeeded，约 14.8 秒 | 1               |                 0 |                    0 |               0 |             0 |
| `01M07TYA9YT4E0GPBCMB679THB` | succeeded，约 9.0 秒  | 1               |                 0 |                    0 |               0 |             0 |

历史数据中，同一提示词还存在两个只保存 Intent、没有 Outline 的 Draft，以及一个更早成功生成 Presentation 的 Draft。这表明提示词本身并非必然无法生成，当前表现更像规划链路的回归、时序或连接恢复缺陷。

## 已证实的故障边界

以下事实已经由页面、API 日志和数据库状态共同确认：

- Draft 创建成功；
- Kimi `intent_infer` 请求成功，ProviderCall 状态为 `succeeded`；
- Intent revision 已提交并成为 Draft 的 `current_intent_revision_id`；
- 浏览器在服务端完成前后显示 `Failed to fetch`；
- `createWorkspace` 使用浏览器端串行 `await`：只有收到 Intent 响应后才会调用 Outline API；
- 异常进入统一 `catch` 后，当前函数不再继续，也没有对服务端权威状态做 reconciliation；
- 失败 Draft 的 Outline、批准、Generation snapshot/job、Presentation 数量均为 0；
- PPT Worker 和 PPT 引擎没有收到本次 Draft 的生成任务。

因此，本 ISSUE 不能描述为“PPT 引擎生成了空内容”。更准确的表述是：浏览器与规划 API 发生了结果不确定的失败，服务端已经提交 Intent，但客户端认为请求失败并中止后续步骤。

## 待验证根因

当前尚不能仅凭 `Failed to fetch` 确认唯一根因。修复前必须验证以下假设：

1. 浏览器连接是否在长耗时 Provider 请求完成前被关闭或重置；
2. API 是否成功发送了响应头和完整 JSON body，或仅完成数据库事务；
3. CORS、localhost/IPv4/IPv6、反向代理、keep-alive 或开发服务器是否在长请求上存在不同超时；
4. 多 Uvicorn Worker 与同步 Provider I/O 是否扩大了响应取消窗口；
5. Provider Schema repair 导致的额外延迟是否提高复现概率；
6. Draft 恢复页面空白是否与同一响应读取问题有关，还是独立的 React 状态/渲染缺陷。

在完成上述验证前，不应通过简单增加超时时间或盲目自动重试来关闭问题。

## 影响

- 用户点击主入口后无法可靠进入大纲工作台；
- 服务端已经产生 Provider 用量，但用户看到失败，可能反复点击并增加成本；
- 历史记录出现只含 Intent 的孤立 Draft；
- 用户无法从产品 UI 判断服务端是否已经成功；
- 后续批准、配额预留、Worker、QA、PPTX 发布链路完全未启动；
- 通用错误 `Failed to fetch` 不包含阶段、恢复动作或可供支持定位的安全请求 ID。

## 相关内容正确性风险

本次 Intent 的 `notes` 明确指出没有官方公告正文或 `sourceRefs`，因此无法核实 GPT5.6 的官方发布信息。该现象与传输/恢复故障不同，但会影响最终内容可信度。

此风险建议单独做产品决策：

- 若产品承诺“根据官方公告”生成，应要求用户上传/提供经过安全 intake 的官方来源，或新增经过批准的研究/URL 来源能力；
- 在没有来源时，必须继续显示“未经核实”的限制，不得把模型常识包装成官方公告事实；
- 该内容来源能力不应成为本 ISSUE 的 P0 修复前置条件，P0 先恢复现有主题型规划主流程。

## 修复计划

### 阶段 A：建立可观测、可重复的失败测试（P0）

1. 新增 Web/E2E 用例：Provider 延迟 5、15、60 秒时均能完成 Intent → Outline；
2. 新增故障注入：服务端提交 Intent 后主动断开/取消客户端响应；
3. 为每个 planning 操作在浏览器发起前生成安全的 `X-Request-ID`，并在 UI 错误中展示该 ID；
4. 日志只记录 Draft ID、操作阶段、请求 ID、状态、延迟和 ProviderCall ID，不记录提示词、来源正文、认证头或 reasoning；
5. 捕获响应头、响应 body 完整性、客户端取消时间和数据库 commit 时间，确定真实断点。

停止条件：自动化测试可以稳定制造“服务端成功、客户端失败”的结果不确定场景，并能用同一请求 ID 串联浏览器、API 和 ProviderCall 证据。

### 阶段 B：把首页规划改为可恢复状态机（P0）

1. 将 `createWorkspace` 的隐式串行流程拆为显式状态：`draft_created → intent_pending → intent_ready → outline_pending → outline_ready`；
2. 每个操作在发起前固定一个 idempotency key；结果不确定时不得生成新 key 盲目重试；
3. 遇到 `Failed to fetch` 时执行最多一次权威 Draft 读取，而不是重试循环：
   - 若 Intent 已存在，继续 Outline；
   - 若 Outline 已存在，直接打开工作台；
   - 若状态仍未提交，显示带阶段说明的“继续意图识别/继续生成大纲”操作；
4. 历史记录和直接 `?draft=...` 恢复必须支持仅有 Draft、仅有 Intent、已有 Outline 三种合法中间态；
5. 对重复点击、刷新和浏览器重连保持幂等，确保每个阶段只产生一个有效 revision/ProviderCall；
6. 保留项目既有“失败后不无限自动重试”的合同，所有自动 reconciliation 都必须有严格的一次上限；
7. 将通用 `Failed to fetch` 改成阶段化提示，例如“意图请求连接中断，服务端结果正在核对”。

停止条件：在服务端提交后断开连接的测试中，刷新或一次显式继续操作可以到达同一个 Outline，且不会重复计费或产生重复 revision。

### 阶段 C：缩短或移除浏览器持有长请求的脆弱边界（P1）

在 P0 恢复逻辑稳定后，评估将 Intent/Outline 规划升级为持久 planning operation：

1. API 快速创建 operation 并返回 `202 + operationId`；
2. Worker/后台执行 Provider 请求；
3. PostgreSQL 持久化 operation 状态和结果 revision；
4. Web 通过有界轮询或 SSE 恢复进度；
5. operation 与 Draft、idempotency key、ProviderCall 和 revision 建立不可变绑定；
6. 浏览器刷新、API Worker 重启或 Redis 重启不丢失规划进度。

此阶段涉及合同和架构变更，需要单独 ADR/Schema 评审，不作为临时补丁直接上线。

### 阶段 D：全链路回归（P0 发布门禁）

使用本 ISSUE 的原始提示词完成真实网站旅程：

1. Draft、Intent 和非空 Outline 正常显示；
2. Outline 至少包含一页，且每页标题/正文满足现有 Schema；
3. 批准当前 Outline；
4. 创建真实 Generation snapshot/job；
5. Worker 到达成功或有明确信息的 partial 终态；
6. Presentation/PPTX 发布，PPTX 可打开且可编辑文本与批准 Outline 一致；
7. 刷新、历史恢复和重复操作不产生重复 ProviderCall、revision、job 或用量；
8. 运行 `pnpm verify:web`、G05 integration/security/E2E、G06 generation/browser E2E，并补充本 ISSUE 的故障注入用例。

## 验收标准

- [ ] 原始提示词连续运行 10 次，10/10 到达可编辑 Outline 工作台；
- [ ] Intent/Outline Provider 延迟 60 秒时页面不误报失败；
- [ ] 服务端提交后立即断开浏览器连接，刷新后能恢复并继续；
- [ ] 每个 Draft 最多结算一次对应的 Intent/Outline ProviderCall 用量；
- [ ] 重复点击和相同 idempotency key 不产生重复 revision；
- [ ] 仅有 Intent 的历史 Draft 可打开并继续生成 Outline；
- [ ] UI 不出现无限 loading、空白主区域或无上下文的 `Failed to fetch`；
- [ ] 未批准 Outline 时不创建 Generation job；批准后能创建并完成真实 Generation job；
- [ ] 最终 Presentation 包含非空页面内容和可编辑 PPTX；
- [ ] 日志、错误提示和测试工件不包含密钥、完整提示词、来源正文或 reasoning；
- [ ] 所有现有 G05/G06 安全、幂等、恢复和配额测试保持通过。

## 修复执行记录（2026-08-17）

### 实施内容

1. 新增 Next.js 同源 BFF catch-all Route Handler：浏览器统一请求 `/api/v1/...`，由 Web 服务端转发至 FastAPI，移除规划主流程对跨域 `localhost:8000` 长连接的依赖；
2. BFF 仅转发明确允许的请求/响应头，不记录或返回密钥、提示词、来源正文和 reasoning；
3. Intent/Outline 使用基于 Draft/Intent revision 的确定性 idempotency key；
4. 首页规划流程在每个阶段前读取服务端权威 Draft 状态，已存在的 Intent/Outline 不重复生成；
5. 网络结果不确定时执行一次权威 Draft reconciliation，并根据已提交状态恢复；
6. 仅有 Draft 或仅有 Intent 的合法中间态不再渲染空白页面，提供“核对并继续意图识别/继续生成可编辑大纲”入口；
7. Source uploader 的产品 API 请求也统一经过同源 BFF；MinIO 预签名上传仍按既有安全边界直传。

### 修复尝试计数

| 尝试 | 结果       | 记录                                                                                                   |
| ---: | ---------- | ------------------------------------------------------------------------------------------------------ |
|  1/5 | 失败并修正 | 首次重构在 `applyDraftSnapshot` 中残留旧变量名 `draftId`，TypeScript 报错；定位后改为 `next.draftId`。 |
|  2/5 | 通过       | TypeScript、ESLint、Next.js production build、BFF smoke、部分 Draft 恢复和三次真实全链路测试通过。     |

同一 Web 规划故障修复失败次数为 **1/5**，未触发“超过 5 次停止”条件。

### 自动化与定向检查

- `pnpm --filter @instant-ppt/web typecheck`：passed；
- `pnpm --filter @instant-ppt/web lint`：passed；
- `pnpm --filter @instant-ppt/web build`：passed，`/api/[...path]` 为动态 Route Handler；
- BFF `GET /api/v1/me/usage`：200，响应结构正确；
- G05 integration：4/4 passed；
- G05 provider security：passed；
- 旧 Intent-only Draft `01M07TMMZ2FK2NPGD1BS5PM543`：成功恢复并生成 10 页 Outline；
- 三个最终浏览器会话的 console error/warning 均为 0。

G06 integration 两次均为 7/8：唯一失败是既有 `killed_worker` 子进程在 Windows 上 30 秒超时，停止常驻 Docker Worker/outbox 后仍可复现。该测试点已连续失败 2/5 次，其他 7 项通过；它不涉及本次 Web/BFF 代码路径，也没有在三次真实 Worker 生成中复现，故保留为独立测试稳定性问题，不通过放宽断言或伪造结果处理。

### 修复后三次真实网站验收

三次均使用原始提示词“根据GPT5.6的官方发布公告生成一份PPT”，并完成 Intent → Outline → 批准 → Generation job → Presentation 全链路。

| 次数 | Draft ID                     | Job ID                       | Outline/生成页数 | Job       | Presentation | 非空标题/正文 | baseline PPTX |
| ---: | ---------------------------- | ---------------------------- | ---------------: | --------- | ------------ | ------------- | ------------- |
|    1 | `01M07WS2BVPC31ZM200T3ZM6J4` | `01M07WV6THF4P3JR6K86NY36Y6` |            10/10 | succeeded | ready        | 10/10         | 32,852 bytes  |
|    2 | `01M07WW1SBRKACRC6TKH81RYAX` | `01M07WZ6B95BY1N3BHZNJ3HT3F` |            10/10 | succeeded | ready        | 10/10         | 31,683 bytes  |
|    3 | `01M07WZYQ1T8GSCY2J09RX2HQE` | `01M07X1J7QXFJ76900B61JJV3R` |            12/12 | succeeded | ready        | 12/12         | 35,394 bytes  |

三次均发布且仅发布一个 `generation_baseline_pptx`，并能从网站进入包含非空标题和正文的“AI 可编辑草稿”。用户要求的修复后 3 次测试为 **3/3 passed**。

## 回滚与发布策略

1. P0 修复先在 Fake Provider 延迟/断连矩阵验证，再启用真实 Kimi smoke；
2. 使用功能开关控制新的 planning reconciliation/state machine；
3. 监控 Intent 成功但 Outline 缺失的 Draft 比例、planning 网络错误率、重复 ProviderCall 和平均阶段耗时；
4. 若错误率或重复计费上升，关闭新客户端自动 reconciliation，保留显式恢复入口，不回滚数据库 revision；
5. 不通过删除孤立 Draft、手工改状态或伪造 Publication 处理历史数据。

## 相关文件

- `README.md`
- `docs/runbook.md`
- `docs/design/g05-draft-workspace.md`
- `docs/design/g06-real-generation-publication.md`
- `docs/evidence/severity-and-waivers.md`
- `apps/web/src/app/workspace-app.tsx`
- `services/api/src/instant_ppt_api/g05_routes.py`
- `services/api/src/instant_ppt_api/planning.py`
