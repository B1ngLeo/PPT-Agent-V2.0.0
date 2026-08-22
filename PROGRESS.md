# 即刻AI-PPT development progress

> Updated: 2026-08-23. This file is updated after every completed module. A single repeated defect may be attempted at most five times; on a sixth failure it is recorded here and deferred while independent work continues.

## 当前 Goal

- Goal：ISSUE-003 / 为 `default-agentic` 建立真实 Main Presentation Agent Runtime
- 状态：in progress（2026-08-22 启动）
- 当前阶段：最终用户旅程中的 fallback 编辑器披露修复与根回归
- 已完成：阶段 0–F；冻结同一 10 页 snapshot 的最终 Agent after；PowerPoint/WPS 双应用 10/10 无修复；before/after 人工偏好与机器证据归档
- 进行中：提交 fallback 不可变修订披露修复，从固定 Git revision 重建运行时，重新执行 fallback 编辑器/精确导出/下载、canary/rollback 与 snapshot 不变量，并跑根回归
- 后续模块：ISSUE-003 最终验收对照、release checklist/Issue 状态收口
- 既有改动隔离：切分支前工作区已有 18 个已跟踪文件修改及 `projects/`、ISSUE-003、`git.md` 等未跟踪内容；全部保留，不覆盖。与 ISSUE-003 重叠的文件会在理解并验证既有差异后继续编辑，提交时按模块精确暂存
- 当前验证：Contracts 26 schemas/38 endpoints/166 fixtures；API/Domain 40/40；Worker 127/127；G06 12/12（新增模板回退不可变修订披露回归）；G07 5/5；Web lint/typecheck/生产构建；Ruff；14/14 告警；Markdown links；Compose config；Alembic head/drift；最终候选 Agent 38 turns/26 tools/视觉首轮 0 blocking、package QA、PowerPoint/WPS 各 10/10 全部通过
- 问题与解决方案：生产浏览器 E2E 首次发现模板回退监控页正确、编辑器却误标为 Agent 初稿；第 1 次定位为旧确定性管线的 generation manifest 未携带 authoring/disclosure/filename，已在生产者补齐真实 0-turn/0-tool 模板作者证据，并在领域发布边界从批准 snapshot 防御性回填不可变修订字段。新增端到端集成回归后 G06 12/12 通过。最终候选迭代中的其他门禁缺陷均在 1–2 次内定位，未有同一问题达到 5 次；失败/旧候选均可恢复移动至 `.codex-tmp/`，没有覆盖用户数据
- 阻塞：当前无
- 防循环：同一问题最多修复 5 次；第 6 次失败将记录问题、尝试与可恢复方案并跳过，继续其他独立模块

## ISSUE-003 模块状态

| 模块 | 状态 | 验证/停止条件 |
| --- | --- | --- |
| 0 基线与 Agent 证据合同 | completed | 两套基线、渲染、统计、输入/version/hash 已归档；Agent/模板最小证据合同已冻结 |
| A Page Blueprint | completed | 每页 assertion/audienceMove/evidenceRefs/contentBlocks/visualForm/layoutIntent/literalConstraints；100% claim support |
| B 受约束设计工具 | completed | allowlist、路径隔离、Scene Graph/直接 SVG、hash/tool call/attempt/stale |
| C Main Presentation Agent Runtime | completed | 实际模型 turn→工具→观察→修订→终止；预算/超时/恢复/持久化 |
| D Agent 顺序创作 | completed | P01 gate 后 P02–Pn；每页 SVG 追溯到 Agent turn/tool call；模板不再是 default-agentic 作者 |
| E 有界视觉闭环 | completed | contact sheet、结构化 reviewer、最多两轮、blocking 清零或非成功 |
| F 灰度、回退与发布 | completed | feature flag、manifest/UI/文件名披露、监控、文档与 rollback |
| E2E 与最终回归 | in progress | 同输入用户旅程、PPTX/WPS/PowerPoint、恢复/取消/安全/发布不变量 |

## 已完成事项

- ISSUE-003 fallback 编辑器披露修复：生产用户旅程发现旧确定性模板管线发布的 generation manifest 缺少 `engineProfile/contentMode/authoring/suggestedFilename`，导致 monitor 依据 snapshot 正确披露、editor 依据 immutable revision 却误标为 Agent。旧管线现发布 `deterministic-template`、`template-limited-editable-draft`、fallback reason、0 Agent turns/tools、模板页数和强制 `-模板化受限初稿.pptx` 文件名；Domain 发布层还会从批准 snapshot 防御性回填旧生产者缺失字段。新增从 feature flag 到真实生成、发布和 presentation API 的集成回归；停掉同库常驻消费者消除测试租约争用后 G06 12/12 通过。
- ISSUE-003 crash replay 不可变请求修复：G06 在“工件已上传、数据库尚未发布”恢复时，从已被首次发布流程改写的 `GenerationJobSlide.title` 重建工作流请求，导致 hash-bound recovery 正确拒绝请求漂移。请求映射现强制从批准 snapshot outline 取标题，缺少批准 roster 直接失败；新增“运行时标题已变化但同 workflowRunId 请求完全相等”的回归，单元 3/3、真实 PostgreSQL/MinIO crash replay 聚焦 1/1 及 G06 全量 11/11 通过，未放宽 request hash 或对象字节一致性校验。
- ISSUE-003 最终纵向恢复回归：在 crash replay 修复和语义质量改动后，G06 11/11 与 G07 5/5 均使用真实 PostgreSQL/Redis/MinIO、真实 Agent turn/tool/reviewer runtime 及本地确定性 Provider 通过；编辑、单页重生成、精确 revision 导出、恢复、取消与幂等发布不变量全部保持。
- ISSUE-003 同输入最终 Agent 候选与人工偏好：以冻结 snapshot `fdb0cd6f…`、来源 `81133341…` 和同一 10 页 stable ID roster 重放真实 Agent turn/tool/reviewer 运行时；因本机无 `MOONSHOT_API_KEY` 明确使用本地 `fake-agent@v1`，不虚报线上 Kimi。最终 PPTX SHA-256 `57ea3e54…`，38 turns/26 tools、视觉首轮 0 blocking；内容形成概览、3 节点时间线、Programmatic Tool Calling、Terminal-Bench 原生图表、模型对比、定价、风险/行动与结尾闭环。PowerPoint/WPS 各 10/10 无修复，23/23 预期可编辑文本匹配、79 个文本形状、32 个原生形状、0 张整页图片；人工判定 After 明显优于 Before，证据见 `docs/evidence/issue003/after/README.md`。
- ISSUE-003 阶段 F / 灰度、显式 fallback 与发布：新 generation snapshot 在服务端冻结 `agent-authoring` 或 `deterministic-template`，开关切换不改写已有 snapshot/revision；模板路径不创建 Agent turn/tool/author receipt，在 job/SSE/manifest/revision/export/UI/下载名统一披露“模板化受限初稿”且精确导出拒绝错误 fallback 文件名。Agent token/费用/阶段/工具/写页/修复、Agent canary 失败与 fallback 率已入库指标和 14 条告警；增加 ADR-012、隐私披露、runbook、release/rollback 文档和 Alembic 约束迁移。上传后崩溃会从 hash-bound manifest/canonical bundle 恢复同一字节产物，不重复调用 Agent；G06 11/11、G07 5/5、Worker 119/119、API/Domain 40/40、Contracts/Web/迁移/指标/链接全部通过。
- ISSUE-003 阶段 E / 有界视觉反馈闭环：对每页当前 Scene Graph 渲染 1280×720 PNG 和 deck contact sheet，将联系表+逐页图像作为真实多模态输入交给只读 Visual Review Agent；strict `VisualReviewReport` v1 覆盖层级、密度/留白、对齐/节奏/平衡、连续重复、内容-视觉匹配、图片裁切/对比度/可读性和整稿一致性，且绑定 workflow/SVG roster/render/contact hash。阻断 finding 按 page/deck ownership 映射回同一 Main Agent，只重写所有页，标记旧 gate stale，重跑 final checker 并最多复审两轮；二轮仍有 blocking 则 `needs_manual` 且不导出。Reviewer 用量纳入同一 runtime 预算，报告、图像和 provider evidence 进入 canonical bundle。Ruff 及 73/73 纵向回归通过，联系表人工检查通过。
- ISSUE-003 阶段 D / Agent 顺序接管 SVG 创作：`agentic_workflow.py` 主路径已删除对固定 `author_slide()` 的页面写入，先由真实 Strategist 读取批准上下文/设计目录并落盘策略，再在同一 session 以 Executor 严格执行 P01→首屏 checker observation→P02…Pn。每页 Scene Graph 写入绑定实际 model turn/tool call/current SVG hash，P01 gate 只有当前 hash 通过才可进入后续页；Blueprint 由真实 strategistTurnId 升级为 `agent-strategist`，结果 usage 记录真实 turn/token/cost/time，canonical bundle 包含 turn/tool/phase/scene/checkpoint 证据。历史 phase 只保留不可变 hash/receipt 和小型策略观察，当前页事实/Design Spec/spec lock 每次精确读取，避免重复 token 计费。2 页 native chart、8 页多角色、AI/provided 图片和完整兼容/内容门合并回归通过。
- ISSUE-003 阶段 C / 真实 Main Presentation Agent Runtime：新增 strict `AgentDecision` 和同一会话 `Strategist → Executor` 有界模型—工具循环；Provider 决定下一工具/终止，Supervisor 强制 role/allowlist/attempt、turn/token/cost/soft/hard timeout 与取消。每次 Provider 前先写 pending checkpoint，每次工具前写确定性 pending call；崩溃恢复复用已完成 turn/幂等 tool，未知 Provider 结果则暂停而不重复计费。批准来源、Design Spec、spec lock/stable ID 作为不可有损压缩的 locked context，tainted 来源指令不能扩权。新增 tenant-scoped `workflow_agent_turns`/`workflow_agent_tool_calls`、Alembic migration、文件证据→数据库幂等桥、Agent decision Schema 和严格 Kimi 子进程环境白名单。Ruff、45/45 合并回归及真实 PostgreSQL migration roundtrip/drift 通过。
- ISSUE-003 阶段 B / 受约束语义设计工具：新增 9 个精确 Agent 工具的闭包注册表，只读当页批准 Blueprint/来源/Design Spec/lock/roster，只写当页 SVG 或 run 拥有的 planning JSON；新增物化 `SlideSceneGraph` v1，可表达文本、图形、分组、项目内图片、可编辑原生 chart/table 和自由组合排版，同时保留拒绝 active/external content 的直接 SVG escape hatch。图表/表格值必须与当页 Blueprint 完全相等，直接 SVG 也不能绕过；每次工具调用绑定 workflow/stage/PNN/attempt/input/arguments/output/subject hash，幂等重放且写入传播后续 gate stale。Agent 无 shell、网络、数据库或通用文件系统工具。Ruff、42/42 回归及 vendored SVG final checker 0 blocking 通过。
- ISSUE-003 阶段 A / Page Blueprint 与语义一致性：新增 strict Pydantic `PageBlueprintArtifact` v1 及物化 JSON Schema，严格冻结 approved roster 的 outlineSlideId/slideId/PNN/order/role；以 page title、audience question、deck intent 的语义相关性选择来源句/图表序列，删除页序取模轮转。每页保存 assertion、audienceMove、evidenceRefs、contentBlocks、visualForm、layoutIntent、literalConstraints 和可选 native chartSpec；蓝图按 workflow/snapshot/source/claim/literal/chart/hash fail-closed，后续 Design Spec、final SVG、compiled PPTX 报告均绑定同一 Blueprint hash，并生成总一致性报告。Ruff 及 33/33 定向/纵向测试通过。
- ISSUE-003 阶段 0 / 基线与 Agent 证据合同：从 PostgreSQL/私有 MinIO 恢复网站 canonical 10 页 before（SHA-256 `4fa9901f…`）、批准 snapshot `fdb0cd6f…`、Markdown `81133341…` 与转换配置 `48189255…`；归档 `ppt-master` 12 页 reference（`5e22b233…`）及用户下载谱系副本。PowerPoint 逐页导出 10/10/12 PNG 且 Repairs=0；统计确认 before 递归 Shape 81、可见字符 1,168、备注 0，reference 递归 Shape 450、可见字符 2,903、备注 12；contact sheet 人工盘点记录 before 的单一正文面板退化和 reference 的语义构图差距。新增可重放封存、渲染、分析脚本及真实 Agent 最小证据合同，明确 reference 非严格 A/B，后续以冻结 10 页 snapshot 做严格 before/after。
- ISSUE-002 最终干净部署与生产用户 E2E：从 Git 提交 `ebed9eb…` 重建并校验 API/Worker/Agent Worker/outbox/Provider Gateway，Worker 家族共享镜像 `sha256:2d98d9ad…` 且 `instant-ppt.v2.process_export` 注册通过；浏览器从已批准事实来源启动任务 `01M0DA1AM1MGYVF41XRWQ6K85Q`，首次尝试 12/12 发布。编辑器显示完整 `GPT-5.6`、`91.9`、`92.2`、`74.3`、`2.8` 与三组不同图表；Web 导出及独立真实队列导出均复用 canonical artifact，下载文件 54,086 bytes / SHA-256 `c617bd0c…`，61 条可见文本无 legacy 命中；12 页逐页渲染、montage 人工检查与 `slides_test.py` 无越界通过。
- ISSUE-002 最终受影响回归：Contracts 26 schemas/38 endpoints/166 fixtures、Web lint/typecheck/生产构建、API/Domain 38/38、Worker 71/71、G02 73/73、G03 8/8、G04 14/14、G05 4/4、G06 11/11、G07 5/5、G08 4/4、G01 10/10 source + 10/10 render + 40 schema artifacts、E2E 证据、安全、链接与 G00–G08 Gate 全部通过；无 waiver。
- ISSUE-002 crash-replay 确定性模块：定位到 Default workflow 的二级 Python 工具未继承固定 `PYTHONHASHSEED`，导致 vendored SVG flatten pass 通过 `set` 复制 XML 属性时顺序随机；视觉相同但 `svg_final`/bundle 字节哈希不同，幂等对象存储因此正确拒绝覆盖并将重放收敛为 `ENGINE_RENDER_FAILED`。顶层监督器与嵌套工具环境现均强制 `PYTHONHASHSEED=0`；监督器/Agentic 单测 14/14 及真实 PostgreSQL+MinIO 的“上传后崩溃→第二次重放→单一不可变 revision”聚焦集成通过。
- ISSUE-002 内容质量补闭环：修正 ASCII 句点的无条件拆分，保留 `GPT-5.6`、`53.6`、`2.8` 等版本与小数，并排除 heading/table 和来源处理说明；长标题只从完整来源句按语义标点收束，不回退到已污染的旧大纲；图表改为按页绑定不同 benchmark 系列，多行文本以原生可编辑 tspan 换行且 package QA 按字符级核对。Ruff、`test_agentic_workflow.py` 11/11、同一冻结快照 12/12 页全流程复现、逐页渲染检查与 `slides_test.py` 全部通过；PPTX 54,294 bytes。
- ISSUE-002 R3 / 单一提交部署：停止占用 8000 端口的宿主机 API，从干净 Git 提交 `35f5084…` 构建 API 与唯一共享 Worker 镜像，强制重建 API/Worker/Agent Worker/outbox/Provider Gateway；五服务 OCI label、env、health runtime identity 均一致，四个 Worker 家族 image ID 一致，`instant_ppt.v2.process_export` 注册通过。证据：`docs/evidence/issue002-runtime-deployment.json`。
- ISSUE-002 R2 / 真实 exact export 队列 Gate：通过对外 HTTP 新建导出任务 `01M0D48BRDVZJW4MCRJWW47HQX`，经真实 outbox/Redis/Celery 完成；export artifact ID 与 EffectiveDesignSpecRevision canonical PPTX 均为 `01JTDVMY6PVRNRZPCVV8SMQ32V`，数据库/下载 SHA-256 均为 `255ef97203d9b10bec338dbdc03cb9abf15bd3cd736b34cf18a00612d7191a94`，证明 exact export 不再重建或污染 PPTX；47 条可见文本中 legacy 工程占位文案命中 0。证据：`docs/evidence/issue002-runtime-exact-export.json`。
- ISSUE-002 R1B / 可重复部署与验证工具：新增 `scripts/issue002/deploy_runtime.py`、`verify_runtime_deployment.py` 与 `verify_exact_export_queue.py`；正式构建默认拒绝未提交的运行时输入，诊断性脏构建只能使用 `dev-<sha>-dirty` 身份；部署后强制校验 API/Worker/Agent Worker/outbox/Provider Gateway 的 Git revision、runtime contract、OCI label、共享 Worker image ID 和 v2 exact-export 任务注册；真实导出脚本强制 canonical artifact ID/SHA 复用且扫描 legacy 工程文案泄漏。Ruff、Python compile、Compose config 与 dirty-build fail-closed 负向验证通过。
- ISSUE-002 R1 / 运行时身份与 fail-closed：新增共享 `instant-ppt-runtime@v2` 身份、Git build revision/container/workflow/engine 元数据及 API/Provider health 暴露；Default generation、single-slide regeneration、exact export 改用 `instant_ppt.v2.*` 任务名并强制 `runtimeContractVersion` 参数，旧 Worker 无法注册新任务或接受新签名；generation snapshot 冻结实际 container/runtime/workflow version；Worker 家族 Compose 统一引用同一 `instant-ppt-runtime:<revision>` 镜像，API/Worker 镜像写入 OCI revision/contract label。Ruff、Compose config、Domain + Worker 全量 91 项及 API health 定向测试通过。
- ISSUE-002 运行时回归审计：将用户文件 `E:\下载\GPT5.6的官方发布公告.pptx` 与 export job/artifact/hash 精确关联；确认宿主机新 API、新 `agent-worker`/`outbox` 与旧普通 `worker` 混用，旧 export 再次执行 legacy DeckPlan；对照新 canonical generation PPTX 与被污染 export PPTX 的 artifact/hash/可见文本，撤销 Issue 的 `Resolved` 状态并写入重新关闭条件。
- ISSUE-002 阶段 0 / 发布止血：新增 hash-bound 内容发布守卫，识别工程文案、未解决占位语和作者任务主导页；精确风险/TODO receipt 可审计豁免。守卫接入 legacy 首次/候选/整稿/G07 导出共同 renderer，删除封面 `Editable native presentation baseline`，重生成 instruction 仅保存 SHA-256 审计而不进入可见正文；8 项定向测试与 Ruff 通过。
- ISSUE-002 阶段 A / 契约与状态：新增 `generatePptxDefault`、WorkflowRequest/Result v2、严格 route/profile/来源/模板/图片/研究/notes/动画/旁白/visual-review/Agent runtime 合同和物化 Schema；新增持久 WorkflowRun、StageAttempt、CheckpointSet、gate receipt、中间工件、EffectiveDesignSpecRevision、EditPatch 与有界状态机。阶段/receipt/hash 门序负向测试、19 项 Domain、37 项 Worker、隔离 migration roundtrip/drift 与 engine boundary 均通过。
- ISSUE-002 阶段 B / Default Agentic 纵向切片：实现 free-design、无图片、closed-corpus 的独立 `generatePptxDefault` 执行器；批准 fragment 正文和随机 nonce 进入 Provider 请求，来源内提示注入按 tainted data 隔离；完整生成 Design Spec I–X（条件跳过 §VII、§VIII 空表）、spec lock、门禁 receipt/checkpoint、live preview 报告、current-main-agent P01→first-page→P02..Pn→final 顺序、原生 chart metadata 与 position calculator 校验、`finalize_svg.py`→`svg_to_pptx.py --no-notes --native-charts-and-tables` 严格串行、postflight/package/content gate、确定性 bundle/result。真实两页 PPTX 验证通过，Worker 38/38、Ruff、attribution 与 engine boundary 通过。
- ISSUE-002 阶段 C / canonical revision 与来源边界：实现不可变 effective Design Spec revision、ordered/hash-bound EditPatch 编译、结构操作审批 hash、spec lock 重新派生、stale canonical 工件失效与精确 revision 导出/重生成；批准来源冻结 artifact descriptor 并在 Worker 重新校验 tenant/state/retention/hash/bytes，模板只冻结未读取/未安装的候选描述符，无来源必须由用户显式选择受限通用初稿。Domain 23/23、Worker 41/41、G05 4/4、G06 8/8、G07 5/5、Web 生产构建、迁移 roundtrip/drift 全部通过。
- ISSUE-002 阶段 E1 / 生产 Agent Worker 与恢复：Default 作业已从生产入口进入独立 `agentic` queue/container，具备 3900s 硬超时、4500s visibility、有界 attempt、持续 job/workflow heartbeat、fencing token、取消进程树终止与最小环境白名单；WorkflowRun/stage attempt/checkpoint/receipt/intermediate artifact 持久化，canonical PPTX/bundle/Design Spec/spec lock/QA/SVG/manifest 原子发布，上传后崩溃恢复保持字节级确定性且不重复发布。修复 Windows stdout/stderr 管道背压死锁后，G06 8/8、G07 5/5、Compose 配置、Ruff 和监督器单测全部通过。
- ISSUE-002 阶段 E2 / 条件能力：notes disabled 保持零工件与 `--no-notes`；notes enabled 在 final SVG 后由 Logic Construction 编写/可视支撑校验，再严格 split→finalize→export；prepared narration 在 Gate 2 后/P01 前冻结且后置只读校验；custom animation 在 notes 后创建稀疏真实 SVG group sidecar 并经上游 validator；narration 必须由 `generate-audio` 拥有且缺少一次性音色决策时收敛到 `needs_manual`，基础 exporter 不冒领成功；visual-review 仅显式 opt-in，渲染后等待有权审阅 Agent。新 workflow stage 迁移 roundtrip/drift、E2 定向 12/12、G06 8/8、G07 5/5 和 Ruff 全部通过。
- ISSUE-002 阶段 F / 内容、视觉、兼容与发布守卫：新增不可变 evidence map，逐 claim 绑定来源 artifact/fragment/text hash，拒绝“合法 ID 但语义不支持”、来源核心遗漏、图表标签/数值/单位/零基线冲突、结尾不闭环和连续模板化角色；Design Spec、final SVG、compiled PPTX 三层报告均绑定当前 artifact hash，缺失/失败/stale 阻断发布。G07 编辑/再生成/精确导出已改走非 Quick role-aware renderer，用户修改标为带 EditPatch 审计的 user-authored analysis，未修改事实继续受来源语义门约束；legacy fallback 取消 `passed=true` 硬编码；无来源结果以 `limited-general-draft` 写入 API、generation/export manifest 并在结果页显示明确警示。Stage F 单测 17/17、Worker 48/48、G01 10/10 双链、G06 8/8、G07 5/5、Web lint/typecheck/build 与 Ruff 全部通过。
- ISSUE-002 阶段 D / 图片资源 Release Gate：完成 `none|cover_only|selective` 到 source-id array、`image_notes`、页面角色和 Design Spec §VIII 的严格映射；provided/acquired 资产安全拷贝、hash/media 验证、`image_analysis.csv` 新鲜度守卫；AI `auto/api/host-native` 有界路径、已批准 Office-native fallback 和 Needs-Manual 停止语义；图片以独立 PPTX media/picture 对象嵌入，关键文字/图表保持原生可编辑，无整页位图；prompt 最小化、Provider 审计、manifest、组织级图片数量/费用 reservation 与幂等结算已闭环。provided、真实子进程 Fake HTTP AI、Needs-Manual、native fallback 端到端用例通过；Worker 全套、Domain/API 35/35、Web lint/typecheck/build 与合同格式验证通过。
- ISSUE-002 最终用户 E2E：既保留既有无来源授权、Needs-Manual 图片、编辑/重生成/下载旅程，也新增批准 GPT-5.6 事实来源的 12 页生产旅程；旧附件作为来源时因没有标签化数据被发布守卫拒绝，审计事实副本则成功生成不同 benchmark 图表并精确导出。
- ISSUE-002 最终回归/发布证据：Issue 状态更新为 Resolved，44 项验收清单全部勾选；本轮最新验证与运行时/队列证据记录在 `docs/evidence/issue002-default-agentic-release.md`、`docs/evidence/issue002-runtime-deployment.json`、`docs/evidence/issue002-runtime-exact-export.json`。
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
- G06 恢复模块：8/8 真实 PostgreSQL/MinIO/Redis/引擎矩阵通过，覆盖 Worker 子进程 `os._exit(73)`、租约接管、上传后崩溃、重复投递、Redis 容器重启与 SSE 回放、partial/单页 retry、取消与 publish 竞态、配额、跨租户隐藏，以及冻结图片配置驱动的一次封面 Provider/嵌入/计费闭环。
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
- G08 无障碍模块：axe-core 4.13.0 对 home/workspace/monitor/presentation 均 0 violation、0 critical/serious；修复 file input/story textarea label 与辅助文本对比度；390/768/1440 三档无横向溢出，键盘证据完成。Xiaobing Li 使用 Windows Narrator 完成 Chrome 200% 具名人工检查并通过。
- G08 发布文档模块：完成观测设计、runbook、rollback、release checklist/report、隐私/Provider disclosure、E2E-001–012、性能/恢复/备份/安全/无障碍 evidence；`pnpm verify:automated:g08` 通过，Gate 推进到 `ready_for_review` 而未虚假签字。
- G08 发布容器与兼容模块：API/Worker/outbox 以 `10001:10001`、只读根文件系统、cap drop 与资源限额运行；PowerPoint 16.0 build 20228 与 WPS 12.1.0.28043 各 10/10 打开/可编辑/导图通过，30/30 像素比较通过。
- G08 最终 E2E 模块：在加固 release 容器与正常 Next.js 生产构建上，以新草稿完成批准、8/8 生成、文字编辑、重排、稳定 slideId 单页重生成、精确 revision 4 PPTX 导出、项目 JSON 导出、对象 hash/字节复核、历史恢复与 390px 无溢出；E2E-001–012 全部通过。
- G08 完成度复审模块：逐项映射 PLAN 12.3、SPEC 13.3/14，修复 G08 runner 误用普通开发数据库、补齐对象存储 AES256/安全生命周期/陈旧 multipart 清理与发布镜像健康/就绪探针；4/4 真实 MinIO 隔离集成通过。
- G08 根验证模块：合同、Web、API、Worker、G02–G08 集成、Golden 合同、E2E、安全、12 条告警和链接全部通过；自动化曾正确停在 `ready_for_review`，具名人工签署后 `pnpm verify:gates --goal G08` 通过。

## 进行中事项

- ISSUE-003 用户旅程：重建最终运行时，覆盖创建/监控/编辑/精确导出/下载、fallback 披露、canary 切换与 snapshot 不变量。
- ISSUE-003 发布收口：安全/取消/恢复/指标/告警/根 `pnpm verify` 回归、证据与 checklist/Issue 更新。

## 问题及解决方案

| 问题                                                                                    | 尝试次数 | 处理结果                                                                                                                                                                                                         |
| --------------------------------------------------------------------------------------- | -------: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G06 crash replay 从首次流程已改写的 `GenerationJobSlide.title` 重建 immutable workflow request，恢复时 request hash 漂移 | 1 | 请求标题改为只读批准 snapshot outline；缺失批准 roster fail-closed，并新增 runtime title 改写前后请求完全相等回归。单元 3/3、真实 PostgreSQL/MinIO 聚焦 crash replay 1/1、G06 全量 11/11 通过。 |
| ISSUE-003 冻结 snapshot JSON 带 UTF-8 BOM，首次 after 重放在 Agent 启动前失败 | 1 | 证据脚本按 `utf-8-sig` 读取；批准 ID/hash/来源字节不变，随后重放成功。 |
| 首版 after 出现 8px 文本、0.9% 溢出和可见工程提示/blueprint 哈希 | 2 | 实现 East Asian Width 语义换行与最小 15px、保留全文；内容门同时扫描最终可见工件，页脚改为受众可读来源披露；PowerPoint/WPS 双渲染人工复核无泄漏。 |
| Markdown 转义在来源、SVG 与 PPTX 可编辑文本之间表示不同，Blueprint/package QA 先后 fail-closed | 2 | 底层证据保留原始 `GPT\-5.6`，渲染为 `GPT-5.6`；SVG 表示门和 package QA 对 Markdown escape 做字符等价比较，缺字仍阻断，新增双层回归。 |
| 页面相关性被整稿目标稀释，导致 timeline/核心能力/定价误选安全段落或处理注记 | 4 | 处理注记先过滤；topic expansion 只由当前页标题与 audience question 触发；时间线优先真实日期/可用性信号并按来源顺序排列，内容页允许复用更相关的已批准事实。最终 3 个真实时间节点、Programmatic Tool Calling 与官方降价信息均正确落页。 |
| Stage F 真实 G06 集成作业被未停止的 Compose outbox/worker 抢占 lease |        1 | 精确查明 lease owner，可逆停止 API/Worker/outbox/provider-gateway 业务容器，保留 PostgreSQL/Redis/MinIO/ClamAV 依赖；随后 G06 全套通过。 |
| Agent 在“上传完、数据库发布前崩溃”后重跑会因时间/耗时证据产生不同 bundle hash |        4 | 改为根据确定性 manifest key 下载并验证 manifest/bundle/workflow result/PPTX，有界防路径穿越解包，恢复 `workflow-events` 后直接发布原字节；聚焦与 G06 11/11 均通过。 |
| G07 内存存储用 `ArtifactUnavailable`、生产 MinIO 用 `SourceObjectError` 表示未上传恢复清单 |        2 | 恢复入口兼容两种协议异常，集成 runner 固定为真实 Agent runtime + 确定性 Provider；G07 5/5 通过。 |
| G07 修订/导出仍断言已废弃的 `default-agentic-revision` 派生 profile |        1 | 保持 snapshot 冻结 `engineProfile=default-agentic`，另断言 `authoringMode=agent-authoring`，避免编辑后伪造新 profile；精确导出通过。 |
| Stage E 成功路径初次写入新 `visual-review` receipt 时被严格 kind 合同拒绝 |        1 | 在 `WorkflowReceipt` 显式增加该 kind，重生 workflow-result/visual-review JSON Schema，成功与二轮阻断路径均通过。 |
| P01 视觉反修 fixture 在不允许 `run_svg_gate` 的 repair phase 反复请求该工具并用尽 token 预算 |        1 | 将 P01 首页 gate 决策限定在初始 `executor` stage；`visual-repair` 只需精确读取+当页 hash-bound write，修复后工作流统一重跑 final SVG checker。 |
| 批准来源的 12 页稿中，只含一个长事实的 timeline 节点被固定在左端导致 SVG 水平越界 |        1 | 保留完整事实文本与引擎质量门，将单节点 timeline 改为安全区正中；定向 SVG QA 与基于同一冻结快照/批准来源的保留工作目录复现均通过，12 页 PPTX 53,738 bytes 成功编译。 |
| ASCII 句点被无条件当作句号，将 `GPT-5.6`、`53.6`、`2.8` 拆成残句并泄漏 Markdown heading |        1 | 只在 ASCII 终止符后是空白/文末时拆句，中文标点保持独立规则，跳过 heading/table 且清理列表标记；新增版本/小数/标题回归用例并通过。 |
| `_build_deck` 只选取一组全局 chart values，所有 data 页因而生成相同图表与标题 |        1 | 提取去重后的多 benchmark 系列，按 data 页顺序绑定 Terminal-Bench/BrowseComp/SEC-Bench 等不同上下文；渲染和 chart gate 均从逐页 roster 取值，新增三页三系列回归用例并通过。 |
| 旧 generation snapshot 中的大纲标题已经含有 `6：…`、`##`、`2.`、`8 分…` 等修复前污染数据 |        1 | 非图表标题改为只从已批准来源的完整句子生成，长文按语义标点收束，禁止用旧 outline title 兜底；同时过滤“本地安全测试版本”等处理说明，最终逐页检查无残句、Markdown 或工程文案。 |
| 完整事实文本在 comparison/risk/timeline/ending 单行布局中触发 12px、越界或截断 |        5 | 保持不放宽 SVG/content/package 门禁；实现不拆版本与小数的语义换行，正文最小 16px，为各角色扩展安全行数/面板，并让 SVG 内容核对和 PPTX package QA 正确忽略布局换行空白；第 5 次内收敛，12 页无截断/越界。 |
| 图表来源校验只按系列标签全局合并，将 GPT-5.5 在不同基准中的 47.9/45.8 误判为冲突 |        2 | 第 1 次改为分句上下文后破坏了分号分隔的单图表 fixture；第 2 次改为“单行/单基准选取一组完整系列，跨基准不合并，同一上下文内重复冲突仍 fail-closed”；8/8 工作流测试与真实解析 GPT-5.6 数据系列通过。 |
| 原 GPT-5.6 DOCX 含 Office 外部关系，来源安全扫描 fail-closed 且无解析工件       |        1 | 保留安全拒绝，不放宽外部关系策略；从同一公告构建无外链、有限事实、可审计的 HTML 受控来源，真实上传后成功发布 2 个解析工件。 |
| 应用内浏览器文件选择事件前 4 种直接激活方式超时                         |        5 | 第 5 次使用可见拖放区域的 DOM 节点成功捕获 chooser 并上传；未改动正确的产品上传链路，未超过防循环上限。 |
| ISSUE-002 修复代码通过测试但运行时仍由旧普通 Worker 生成/导出相同占位稿                 |        1 | 根因已确认：不同服务来自不同构建，G07 测试又直接调用函数绕过真实队列；Issue 已重新打开。正在增加 build revision 一致性、fail-closed 与真实容器队列 Gate，之后统一重建全部服务。                                  |
| ISSUE-002 开发前 API 全套基线运行停在第 21 项且长时间无输出                             |        1 | 主动终止该次基线，避免无界等待；Worker 25/25 与阶段 0 定向测试通过。阶段 A 后将 API 测试按文件/模块运行以定位，最终仍要求全量回归。                                                                              |
| Needs-Manual 真实任务首次被前端泛化为“生成失败”                                         |        1 | API 返回 WorkflowRun 的安全状态/阶段/错误码，仅在 `needs_manual` 暴露可恢复动作；Web 明确显示“等待人工补充图片”和中文恢复建议，G06 与浏览器复验通过。                                                            |
| 受限通用初稿初次仅重复大纲目标，长主题又使时间轴 SVG 文本越界                           |        3 | 实现按 cover/content/comparison/timeline/risk/ending 角色的非事实文案，长主题使用可识别紧凑标签，时间轴节点收入安全区；精确 8 页浏览器输入纳入 0 error/0 warning 回归。                                          |
| 新图片分析模块首次未进入 Worker 直连上游脚本允许清单                                    |        1 | 只将 `image_resources.py` 加入已有 Worker 适配层 allowlist，不扩大 API/Web/产品层边界；attribution、engine-boundary 与 Worker 64/64 全量通过。                                                                   |
| 全仓 Prettier 扫描命中用户未跟踪 `git.md`、`projects/` 和 OpenAI 输入 fixture           |        1 | 未改写或删除用户文件；本次所有可维护首方文件精确 Prettier check 通过，`git diff --check` 与 Markdown 链接门禁也通过。                                                                                            |
| 隔离迁移/API TestClient 使用 `localhost` 时 psycopg 在当前 Windows/Docker IPv6 路径等待 |        3 | faulthandler 确认停在 psycopg socket wait；直连 `127.0.0.1` 后 2.7s 通过。将本地默认/验证脚本收敛到 IPv4 loopback，显式 `DATABASE_URL` 仍可覆盖；可观测性 3/3 与 Domain/API 35/35 通过。                         |
| Default 子进程最小环境遗漏 Windows home 定位变量，vendored `Path.home()` 失败           |        1 | 仅补入 `USERPROFILE/HOMEDRIVE/HOMEPATH` 等非凭据运行时变量，继续拒绝 API key/密码/认证环境；真实引擎链路通过。                                                                                                   |
| 原生图表 metadata 的 title 只在导出后可见，被 final SVG QA 拒绝                         |        1 | 删除不可见 title metadata，保留 `name` 作对象命名；断言标题在 marker 外真实可见，fallback/native 内容对齐后 final QA 通过。                                                                                      |
| Default 项目路径被改名后丢失 `_ppt169_YYYYMMDD`，完整 project validation 拒绝           |        1 | 保留 vendored `project_manager init` 的规范目录名并通过响应工件 key 返回实际路径；Design Spec 标题保持 `Slide NN` 可解析并附带精确 PNN，完整 validate 通过。                                                     |
| 当前 PowerShell 未暴露 `uv`，首次 Python 验证命令无法启动                               |        1 | 使用仓库现有 `.venv\\Scripts\\python.exe` 执行 Ruff/pytest；工作区代码与依赖均未改变，随后 Domain/Worker 全套通过。                                                                                              |
| pytest 用户临时目录 `AppData\\Local\\Temp\\pytest-of-*` 权限拒绝                        |        1 | 所有新验证固定到仓库 `.tmp/pytest-*` 唯一 `--basetemp`；来源与工作流合同 10/10 通过。                                                                                                                            |
| G06 完整回归的两项真实对象测试因 MinIO 容器停止失败                                     |        1 | 启动仓库 Compose `minio` 并等待 health=healthy；两项定点复跑通过，随后完整 G06 8/8 通过，未修改产品代码掩盖环境错误。                                                                                            |
| Default 崩溃恢复中 canonical bundle/PPTX 因时间、尝试路径与嵌入 XLSX 属性不一致         |        3 | 依次将 receipt 时间锚定到不可变 approval、QA 绝对路径规范化为 `$PROJECT`、递归规范化 PPTX 内嵌 XLSX 属性/ZIP 时间；第 3 次后同 snapshot 恢复的 12 件工件字节级稳定，未达防循环上限。                             |
| 三页 Default 稿件因 SVG 标题 42px 未在 Design Spec 字体锚点声明而被拒绝                 |        1 | 将通用 SVG 作者标题统一到 spec lock 的 38px；两页“稀疏例外”不再掩盖多页字体漂移，G07 真实三页生成通过。                                                                                                          |
| 监督器只轮询但不读取 PIPE，适配器写满 stdout/stderr 后结果已完成但无法退出              |        1 | 中止精确卡住的测试进程树，改为由临时文件承接子进程输出，退出后再读取；取消/超时/心跳语义保持，监督器单测与 G07 5/5 通过。                                                                                        |
| 条件 stage 迁移 drop check 时被 Alembic naming convention 二次加前缀                    |        1 | 将既有完整约束名用 `op.f(...)` 标记为已格式化；事务回滚后重跑 upgrade→downgrade→upgrade 通过，metadata drift 为空。                                                                                              |
| G07 非 Quick 修订渲染首次缺少 `spec_lock.md`                                            |        1 | 在 Effective Design Spec revision renderer 中生成哈希绑定的 flat execution lock；随后完整 SVG QA 进一步指出主题字段缺失，补齐 colors 与 font/title/body family 后再生成与 exact export 真实门禁通过。            |
| G07 修订内容最初只有词法/对象表示检查，未延续首次生成的来源语义门                       |        1 | 从冻结 snapshot 重新解析同租户批准来源，按 effective revision 链汇总 EditPatch；未改事实重建 citation 语义支持，用户修改显式分类为带 actor/patch hash 的 user-authored analysis，三层报告绑定新的 evidence map。 |
| `uv` 通过用户级 pip 安装后未进入当前 PowerShell PATH                                    |        1 | 使用稳定的 `python -m uv` 本地入口；CI/已配置环境仍可直接调用 `uv`。                                                                                                                                             |
| npm registry 下载 Next.js/SWC 超过默认超时                                              |        5 | 已解决：保留锁定版本；确认 pnpm 11 未读取旧 `.npmrc` 网络键后，按当前官方配置把镜像、10 分钟超时、5 次退避和低并发迁入 `pnpm-workspace.yaml`，最终从内容寻址缓存恢复 181 包并完成剩余 2 个下载。                 |
| pnpm 安全默认值阻止 `sharp` 生命周期脚本                                                |        2 | pnpm 首次安装自动写入待决 placeholder，移除重复键后按 pnpm 11 `allowBuilds` 合同仅批准精确 `sharp@0.34.5`，并启用 `strictDepBuilds`；未知脚本将直接使安装失败。                                                  |
| Codex bundled pnpm 进程报告 Node 24.19.0，而工作区 `node` 为 24.18.1                    |        1 | `.node-version`/CI 仍固定 24.18.1；`engines` 接受同一 Node 24 LTS 线以兼容包管理器宿主，应用脚本已确认由 24.18.1 执行。                                                                                          |
| OpenAPI 内嵌组件仍保留 JSON Schema 绝对 `$ref`，类型生成器尝试联网解析                  |        1 | 物化 OpenAPI 时把合同基址引用改写为本地 `#/components/schemas/*`，独立 JSON Schema 仍保留规范 `$id`。                                                                                                            |
| 端点错误 fixture 使用带 `{param}` 的 URI 模板，不符合 RFC `uri-reference`               |        1 | fixture 保留模板字段用于匹配 operation，同时把 ProblemDetails `instance` 物化为具体 ULID 路径。                                                                                                                  |
| 单页 `failed` 同时被声明为绝对终态和可进入 `retrying`                                   |        1 | 按 SPEC 将其定义为“重试耗尽时的条件终态”，绝对终态只保留 `ready/cancelled`，不删除合法人工重试转换。                                                                                                             |
| 根 `uv sync --frozen` 仅同步虚拟根项目，移除了 workspace member 依赖                    |        1 | 根项目显式依赖 API/Worker workspace members，并用 `[tool.uv.sources]` 绑定；设置 `link-mode=copy` 兼容当前跨卷缓存。                                                                                             |
| 上游完整浅克隆/commit tarball 体积过大                                                  |        2 | 完整浅克隆长时间无 checkout；tarball 下载到 244 MiB 后确认 codeload 不支持断点续传。改用 Git partial clone + sparse checkout，仅取固定 commit 的 `skills/ppt-master` 和必要顶层归属文件。                        |
| pytest 用户级默认临时目录拒绝访问                                                       |        1 | 验证命令固定使用仓库 `.tmp/` 下的隔离 `--basetemp`，单测通过。                                                                                                                                                   |
| Windows Defender 在 harness 读取前拦截完整 EICAR 字节串                                 |        1 | 测试 fixture 改用无害专用 canary，仍验证相同 fail-closed 错误路径；真实 ClamAV/Defender 结果在隔离环境证据中单独记录。                                                                                           |
| 上游 SVG QA 要求页角色和 root group 布局边界                                            |        2 | 第 1 次消除未分组/页角色 warning；第 2 次为内容 group 声明 `data-pptx-bounds`，final QA 达到 0 error/0 warning。                                                                                                 |
| PPTX 可编辑文本检查未遍历 PowerPoint group 子 shape                                     |        1 | package QA 递归遍历 group，标题与正文均以原生文本 shape 被识别。                                                                                                                                                 |
| Windows 默认 GBK 解码上游 UTF-8 输出与 CLI Unicode 结果                                 |        2 | 子进程固定 UTF-8/replace，adapter stdout 显式重配 UTF-8，真实渲染 CLI 通过。                                                                                                                                     |
| 本地 Docker daemon 初始未启动                                                           |        1 | 已以隐藏方式启动 Docker Desktop 4.76.0，daemon 29.5.2 就绪后完成镜像构建。                                                                                                                                       |
| 容器 attribution guard 成功时静默输出，验证器误把空 stdout 判为失败                     |        1 | 按 CLI 合同以 exit code 0 为成功证据；Dockerfile 构建阶段和运行时均执行守卫。                                                                                                                                    |
| BuildKit 默认 provenance attestation 使本地 manifest-list digest 每次改变               |        1 | G01 可重复验证关闭动态 provenance，保留固定基础镜像 digest 和独立 SBOM；连续两次构建 image ID 一致。                                                                                                             |
| 链接检查器扫描了 `.tmp` sparse clone 和不可修改 vendor 的上游仓库外链接                 |        1 | 首方 Markdown 链接检查明确排除 `.tmp`/`vendor`；vendor 完整性继续由固定树哈希和 attribution guard 覆盖。                                                                                                         |
| 上游工具在 vendor 中产生 Python 字节码缓存，导致原始树哈希误报                          |        1 | 树哈希只覆盖可分发源文件并排除 `__pycache__`/`.pyc`，上游守卫运行时禁止后续字节码写入；树哈希恢复 `3ff44cc3…`。                                                                                                  |
| PowerPoint/WPS 视觉抽查初次读到 WPS 旧 PNG（WPS Export 不覆盖同名文件）                 |        1 | 兼容脚本在精确 `.tmp/compatibility/<app>/<case>` 下逐文件清理旧 PNG 再导出；新基线与 PowerPoint 对齐并通过 30 对自动差分。                                                                                       |
| PPTX 规范化仅固定 ZIP 时间，`docProps/core.xml` 仍含当前时间                            |        1 | 同步固定 core created/modified 属性；单样本和 10 样本均连续两次哈希一致。                                                                                                                                        |
| WPS COM 在全链路冷启动时偶发 `0x800706BE` RPC 失败                                      |        1 | Office 验证增加最多 3 次的有界进程重试；最新完整链路在第 3/3 次 WPS 尝试成功，未超过 5 次防循环上限，且 10/10 兼容与 30/30 视觉检查通过。                                                                        |
| Prettier 初始扫描生成物、金样本、冻结计划与 vendor 输入，产生 120 个非源码格式告警      |        1 | 新增 `.prettierignore` 明确区分首方可维护文件与冻结/生成输入；格式化首方文件后 `pnpm format:check` 通过，契约、金样本和全仓验证再次通过。                                                                        |
| Package QA 仅列出媒体清单且只间接证明文本，缺少悬空关系、原生图形和整页位图的直接断言   |        1 | 增加 OPC 内部目标解析、缺失/越界关系、孤立媒体、逐页计划文本计数、原生图形计数和整页图片回退门禁；新增破损媒体关系回归测试，10/10 金样本重新通过。                                                               |
| G02 ORM 未声明 snapshot/job relationship，flush 时先插入依赖 job                        |        1 | 在同一事务内先显式 flush immutable snapshot，再插入带 organization 复合外键的 job；最小烟测与完整矩阵通过。                                                                                                      |
| Redis Pub/Sub 测试在 `SUBSCRIBE` 确认帧消费前发布，偶发收不到 fanout                    |        1 | 测试先消费订阅确认再触发 outbox；10/10 fanout 通过，生产分发代码无错误。                                                                                                                                         |
| Windows Celery solo 强杀后 Kombu 未按 3 秒配置自动恢复未确认消息                        |        3 | 保留 late ack/受限预取并对齐 visibility 配置；最终以 PostgreSQL lease 为真相，由 outbox 对账过期 lease 并按 lease token 去重重投，真实进程强杀 10/10 通过。                                                      |
| Docker Compose 并行构建在中文仓库路径产生 BuildKit gRPC session header 错误             |        2 | 错误发生在 Dockerfile 执行前；关闭 Compose Bake 后逐服务顺序构建，API、Worker、outbox 三镜像全部成功，运行时 E2E 通过。                                                                                          |
| MinIO 首次启动时健康端口短暂接受后关闭连接                                              |        1 | readiness probe 将 connection reset 作为有界启动重试；真实业务请求不使用该重试路径，随后完整私有对象矩阵通过。                                                                                                   |
| G03 迁移保真 canary 初始使用了非 G02 固定 synthetic organization ID                     |        1 | 对齐 G02 固定 organization/service actor 常量后，双向迁移、11 字段数据保真与 schema drift 全部通过。                                                                                                             |
| 下载授权幂等记录初版包含短时签名 URL                                                    |        1 | 只持久化原始过期时间；重放在原截止时间内重新签名且不创建新 grant，过期后返回 410，新测试确认 artifact/grant/audit/idempotency 均无 URL。                                                                         |
| Docker 镜像代理对上游 `clamav/clamav` 返回 403                                          |        2 | 使用 digest-pinned Debian/Python 基础镜像和精确 `clamav-daemon 1.4.3+dfsg-1~deb12u2` 构建受限服务；真实 INSTREAM OK/FOUND 通过。                                                                                 |
| ClamAV 在只读容器中显式打开 `/dev/stderr` 报符号链接循环                                |        1 | 移除显式 LogFile，前台 daemon 直接写容器输出，健康检查与日志均恢复。                                                                                                                                             |
| 只构建 Worker 未刷新 Compose 独立命名的 outbox 镜像                                     |        1 | G04 容器 verifier 顺序构建 clamav/API/Worker/outbox；原 pending source task 在刷新 outbox 后继续处理，证明持久恢复。                                                                                             |
| wheel 安装后的包路径比 editable 源码多一层导致 vendor 根错误                            |        1 | 路径解析遍历父目录寻找固定 vendor，也支持经校验的显式根；本地与 `/app/.venv` 容器均通过。                                                                                                                        |
| ClamAV 对完整 HTML 规范化后自定义原始字节签名未命中                                     |        2 | 真实 daemon 断言改用精确标记流；独立 active HTML fixture 继续验证结构拒绝，容器结果同时包含 clamd 与 intake finding。                                                                                            |
| Domain 层会把大写 SHA-256 静默转为小写                                                  |        1 | 取消规范化并与 Pydantic 合同共同拒绝非小写 hash；单元与 complete mismatch 矩阵通过。                                                                                                                             |
| 移动端截图中 off-screen skip link 局部露出                                              |        1 | 改为 nowrap + translate 隐藏，仅键盘 focus 时恢复；三档浏览器测量无溢出。                                                                                                                                        |
| 浏览器 Fetch 拒绝中文 `X-Dev-User-Name` header                                          |        1 | UI 继续使用中文，但 local dev 身份头改为 ASCII 展示名；真实 HTML/DOCX 浏览器上传、刷新恢复与最终解析通过。                                                                                                       |
| 冻结计划指定的 `kimi-k3` / `gpt-image-2` 初次审计时尚未出现在官方模型枚举               |        1 | OpenAI 官方文档已确认 `gpt-image-2`；Kimi 官方文档仍未列出 `kimi-k3`，但所有者选择的 `cf.api.fan` 凭据限定模型目录与 Anthropic Messages 真实 smoke 已确认精确 ID 可用，不把代理结果冒充上游官方声明。            |
| G05 集成测试把中文主题拼进 `Idempotency-Key`，HTTPX 按 ASCII header 合同拒绝            |        1 | 幂等键改为主题 UTF-8 SHA-256 的短前缀；请求正文仍保留完整中文，4 组工作台集成场景通过。                                                                                                                          |
| 本地浏览器使用 `127.0.0.1:3000` 不在默认 Web CORS 白名单                                |        1 | 统一本地入口为 `http://localhost:3000`，API 仍监听 loopback；README 与 G05 设计明确该约束。                                                                                                                      |
| 自动保存失败后 effect 再次调度请求，可能形成重试循环                                    |        1 | 增加失败类型与稳定 failed 状态，仅允许用户显式重试；停 API、保留本地编辑、恢复 API、重试并刷新后值仍持久化。                                                                                                     |
| closed `details` 在桌面有布局尺寸但内容未实际绘制                                       |        1 | 以受控 open 状态保证非平板始终展开，平板保留可开合原生抽屉；桌面截图、平板开合和移动布局复验通过。                                                                                                               |
| Provider 名称常量误落在图片适配器类末尾                                                 |        1 | 为 Kimi 与 OpenAI Image 适配器分别声明 `kimi` / `openai-image`，并新增合同断言，7 项 Provider 测试通过。                                                                                                         |
| 应用内浏览器 Tab/Enter 键注入不产生焦点移动或激活事件                                   |        5 | 按防循环规则停止继续尝试并固化 harness limitation；原生 button/link、label、键盘文本输入、dialog 焦点恢复、44px 目标与完整真实点击旅程作为补偿证据，clean console 为 0。                                         |
| G06 迁移 drop check constraint 被 Alembic naming convention 再次拼接表名前缀            |        1 | 对既有约束名使用 `op.f(...)` 标记为已格式化名称；迁移双向演练与 schema drift 检查通过。                                                                                                                          |
| G06 SSE effect 随每次 job 对象刷新重建连接                                              |        1 | effect 只绑定稳定 job ID 与 terminal 标志；普通状态刷新保持同一事件流。                                                                                                                                          |
| G06 恢复测试与手工浏览器 Worker 同时争用同一租约                                        |        4 | fallback 回归期间常驻 outbox/Worker 再次抢占 crash-recovery 测试任务；停止套件外 Worker/Agent Worker/outbox 后 G06 12/12 通过，保留基础 PostgreSQL/Redis/MinIO 继续执行隔离回归。                                  |
| Default crash replay 的 `svg_final` XML 属性顺序跨进程漂移                              |        2 | 第 1 次只固定监督器子进程种子，发现二级工具会重建白名单环境并丢弃该值；第 2 次同时固定顶层与嵌套 `PYTHONHASHSEED=0`，相同快照 bundle 字节一致，真实崩溃重放测试通过。                                                |
| 最终 E2E 来源选择误用旧生成 PPT 与带内部 taint 包装的 workflow-input                    |        3 | 第 1 次旧 8 页占位 PPT 无 benchmark，内容门禁正确拒绝 data 页；第 2 次包装后的诊断输入把 taint 标记当普通来源文字；第 3 次改用已审计的纯事实来源工件，12/12 生产生成、exact export 与视觉检查全部通过。             |
| G07 数据下载使用跨域签名 URL时浏览器导航离开编辑器                                      |        2 | 第 1 次定位原生 anchor 对跨域 `download` 不可靠；第 2 次改为授权 fetch→Blob→DOM 临时链接，PPTX/JSON 命名文件实际落盘且编辑器路由保持。                                                                           |
| 应用内浏览器 download event 未捕获程序化 Blob 下载                                      |        2 | 两次等待均超时但页面成功消息、操作系统 Downloads 中两个 8,119-byte JSON 和 25,787-byte PPTX 均证明下载完成；记录为自动化 harness 限制，不重复修改正确产品路径。                                                  |
| G07 export package QA 因封面多条正文没有沿用生成合并规则而失败                          |        1 | 导出 DeckPlan 对封面正文使用与 G06 一致的合并规则；真实引擎 export、manifest 与 package QA 回归通过。                                                                                                            |
| G07 单页重生成使用原生 prompt，在应用内浏览器被自动取消                                 |        1 | 替换为可访问的内联“AI 单页修改要求”输入框；生产浏览器真实重生成成功且 stable slideId 保持。                                                                                                                      |
| Docker BuildKit 在中文工作区再次无法编码 session header                                 |        1 | 使用同一 Docker daemon 的 legacy builder 顺序构建 G07 API/Worker/outbox，三运行时启动和真实浏览器 E2E 通过；G08 将此纳入发布构建说明。                                                                           |
| G06 生产 Worker 消费到数据库清理前遗留 broker 消息并记录异常                            |        1 | 真实任务包装器将不存在的旧 job 收敛为幂等 `noop_missing`；有效任务仍保持严格租约与重试。                                                                                                                         |
| 长中文正文在 SVG 作者层被截断，PPTX package QA 拒绝批准文本丢失                         |        2 | 第 1 次仅修正逐页封面布局；第 2 次定位整稿可编辑文本缺失，改为 East Asian Width 动态字号并保留全文，SVG/PPTX 回归与 8 页真实发布通过。                                                                           |
| G06 应用内浏览器不提供 viewport resize 或历史 console 收集                              |        1 | 不宣称 G06 移动浏览器/零历史 console；记录能力限制，以生产构建、语义 DOM、空 terminal alert、显式响应式规则及 G05 三档 shell 矩阵补偿。                                                                          |
| G08 pnpm 更新首次被运行中的 Next server 锁文件并写入待决 placeholder                    |        1 | 停止精确 Next 进程、移除 placeholder 并用 frozen install 复核；`sharp@0.35.0` 仅通过精确 `allowBuilds` 批准，Web 构建通过。                                                                                      |
| 配置的 npm 镜像没有 audit endpoint                                                      |        1 | 审计命令显式使用官方 `https://registry.npmjs.org`；production dependency advisory 为 0，并在 evidence 记录镜像限制。                                                                                             |
| G08 固定数据短窗在无节奏高吞吐下 p95 连续超标                                           |        6 | 达到防循环阈值后不再修改业务代码；记录为负载模型饱和，按固定可复现 500ms 用户节奏执行 SPEC 的 2+10 分钟正式窗口，GET/write p95 72.113/80.873ms、0 error。                                                        |
| MinIO Python `make_bucket` 使用过期 `region` 参数                                       |        1 | 按当前 SDK 文档改为 `location`；隔离 restore bucket 64/64 hash 恢复通过且临时目标已清理。                                                                                                                        |
| G08 Alembic 演练首次使用错误配置文件路径                                                |        1 | 使用实际 `packages/domain/src/instant_ppt_domain/alembic.ini`，在精确临时数据库完成 upgrade/downgrade/re-upgrade/drift，并删除临时数据库。                                                                       |
| 当前 Windows 未安装 NVDA                                                                |        1 | 不安装或伪造人工结果；使用系统已安装的 Windows Narrator 10.0.22621.4974 完成具名人工验收，精确 Chrome 200% 主流程通过。                                                                                          |
| Compose classic builder 为同一 Worker Dockerfile 重复构建 outbox 镜像                   |        1 | 三个非 root 镜像均成功并记录精确 digest；重复构建只影响本地耗时，作为后续构建缓存优化项，不改变发布内容。                                                                                                        |
| G08 最终浏览器旅程首次请求早于新建 API 容器 readiness                                   |        1 | 等待 `/healthz` 返回 200 后仅执行一次显式用户重试；随后完整 8 页生成、编辑、导出、历史恢复和对象 hash 复核通过，未添加隐式无限重试。                                                                             |
| 旧 G08 证据把普通业务路由探针误写为 `/healthz`                                          |        1 | 增加显式轻量 `/healthz` 与数据库驱动 `/readyz`，Compose 改用 readiness，发布镜像两端点均 200；旧报告改为准确描述当时的业务路由探针。                                                                             |
| G08 隔离集成 runner 曾清空普通 `instant_ppt` 开发数据库                                 |        1 | runner 改为创建/迁移/销毁专用 `instant_ppt_g08_test`，不再破坏开发数据；4/4 真实 PostgreSQL/MinIO 集成通过并输出 JUnit。                                                                                         |
| MinIO 拒绝只含 abort-incomplete-multipart 的 bucket lifecycle rule                      |        4 | 有界诊断确认当前服务端会拒绝或丢弃该规则；改用安全 expired-delete-marker lifecycle，并由 MinIO 官方 stale-upload expiry/cleanup 环境配置负责陈旧分片清理，证据同时验证两层治理。                                 |
| 新 release 容器重建期间首页 hydration 保留一次 `Failed to fetch`                        |        1 | 业务路由、`/healthz`、`/readyz` 均 200 后只做一次显式 reload；随后整条新草稿到 revision 4 双导出旅程通过，运行日志 0 error。                                                                                     |
| 首轮对象治理只验证“当前无公开策略”，未恢复既有误配置                                    |        1 | API/Worker 治理改为在全部读写与签名入口移除既有 bucket policy 后再启用 AES256/lifecycle；两个全新临时 bucket 分别验证 API 纠偏和 Worker 冷启动，测试后均已清理。                                                 |

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

### G08 / 安全、质量、可观测与发布门禁 — complete

- 产物：Prometheus/OTel 可观测面、12 条告警、对象 reconciliation、私有 bucket AES256/lifecycle/stale-upload 治理、健康/就绪探针、备份恢复与迁移演练、依赖审计/SBOM、固定性能基线、axe/响应式证据、加固 release 容器、runbook/rollback/privacy/release 文档和 E2E-001–012 证据。
- 验证：所有自动化模块及根验证的自动化阶段通过；PowerPoint/WPS 各 10/10 与 30/30 视觉差分通过；新鲜用户 E2E 完成 8 页生成、revision 4 编辑/重生成/导出、JSON 导出、历史恢复、MinIO 字节/hash/AES256 和移动布局复核；G08 隔离集成为 4/4。
- Gate：`GATE-G08-RELEASE` 为 `passed`；product 已具名选择 `cf.api.fan` 路由的 `kimi-k3`/`gpt-image-2` 且脱敏真实 smoke 通过，Provider/privacy/成本决策已批准，Windows Chrome 200% + Narrator 具名人工检查已通过，无 waiver。生产 KES/KMS 对当前仅本地范围记为不适用/延后，不代表技术通过；范围扩展前必须重新打开门禁。
- 证据：`docs/evidence/g08-completion-audit.md`、`docs/release-gate-report.md`、`docs/release-checklist.md`、`docs/evidence/g08-final-browser-e2e.json`、`docs/evidence/g08-integration-junit.xml`、`docs/evidence/security/g08-object-governance.json`、`docs/evidence/g08-e2e-matrix.json`、`docs/evidence/gate-manifest.yaml`。
