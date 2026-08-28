# ISSUE-004：移除 Scene Graph 作者路径并引入自适应视觉返修

## 基本信息

| 字段 | 值 |
| --- | --- |
| 状态 | In Progress：Direct SVG-only、无 Blueprint 工作流、视觉复核 opt-in v3、PPT-Master 页面契约对齐、三层 SVG 限制与无硬轮次上限的确定性修复循环均已实现并通过自动化验证；真实 Qwen A/B、structured 模板和 PowerPoint/WPS 发布回归待完成 |
| 严重级别 | Sev-2 |
| 优先级 | P1 |
| 首次确认日期 | 2026-08-26 |
| 影响组件 | Planning、Presentation Agent、SVG authoring、visual review、workflow contract、恢复与发布证据 |
| 依赖 | ISSUE-002 内容/发布门、ISSUE-003 Main Presentation Agent Runtime、ppt-master SVG→PPTX 工具链 |
| 责任人 | Engineering / AI Runtime / Presentation Quality（待指派） |

## 摘要

当前 `agent-authoring` 同时允许模型写 `SlideSceneGraph` 或 Direct SVG。Scene Graph 是本项目在 ISSUE-003 中加入的受约束中间表示，并非上游 `ppt-master` 的作者路径；上游以完整 SVG 作为页面设计源。随着作者模型具备更强的视觉布局与 SVG 代码生成能力，双表示增加了提示合同、修复模式、Schema、证据包和测试矩阵的复杂度，也会限制复杂视觉表达。

视觉审核当前使用固定三次审核上限，即首次审核加最多两次返修。固定轮数不能区分首轮通过、持续改善、停滞和质量恶化。ISSUE-004 将新生成流程统一为 Direct SVG，并把视觉审核改成有进展判定、最佳版本保存、恶化回滚和硬上限的自适应闭环。

2026-08-27 的真实网站回归进一步确认：本项目新增的 `Page Blueprint` 前置层会在 PPT-Master Strategist/Executor 开始自由设计之前，以中文词面相似度和不一致阈值误拒绝已批准大纲。两次同输入任务均因 P02 标题支持分为 `0.0`、P04 要点支持分为 `0.2727 < 0.30` 而在零页面产出时失败。该节点不是上游 PPT-Master Default Generate 的组成部分，因此本 Issue 增加后续修订：彻底移除 Page Blueprint 及其替代页面合同，让 PPT-Master Strategist 直接基于来源、已批准大纲和用户确认结果完成页面规划。

同日的真实 Qwen 生成回归还显示：通过全部确定性 SVG 门禁的初始版本已经具备可接受质量，仅一页存在较明显的视觉问题；后续多轮主观复核反而使页面效果变差，并因 `quality-regressed` 阻止 PPTX 导出。考虑到当前使用 `qwen3.7-plus`，未来更强作者模型可能进一步提高一次生成质量，本 Issue 再增加 opt-in v3 修订：视觉复核对新任务默认关闭，仅在用户明确要求时启用，并按 PPT-Master 的逐页、原子、可回滚策略运行，不再作为所有任务的默认发布门。

2026-08-28 的进一步审计确认：可选的多模态视觉复核与 PPT-Master 自带的确定性 SVG 质量门不是同一循环。视觉复核仍可按产品策略保持 `off` / `standard` 和一次受限修复；但 P01/final SVG checker 的 blocking error 必须按 PPT-Master 原生节奏持续执行“完整问题集 → 集中修复 → 单次复检”，不得设置固定修复轮次上限，也不得在轮次、停滞或预算耗尽后把 error 降级为 warning 并绕过导出门禁。

## 决策

1. 新的 `agent-authoring` 页面只允许 `validated-direct-svg`，不再生成或消费 `SlideSceneGraph`。
2. 已发布工件和历史对象存储中的 Scene Graph 证据不删除；发布切换前应排空使用旧策略的运行中任务。
3. Direct SVG 继续受当前页、已批准 Outline、来源事实、锁定后的 `design_spec.md` / `spec_lock.md`、项目内图片、图表/表格事实和安全 SVG 白名单约束；不再依赖批准 Blueprint。
4. 新视觉策略的 `maxRounds=5` 表示最多五次审核，即首次审核加最多四次返修。
5. 零 blocking 立即通过；连续两轮没有改善可提前进入 `needs_manual`；第五次审核仍有 blocking 必须进入 `needs_manual`。
6. 每轮按 blocking 数、影响页数和 advisory 数计算可解释的比较分数，并保留当前最佳 SVG 快照；返修恶化时恢复最佳版本。
7. Reviewer 仍为只读，所有 SVG 修改由同一 Main Presentation Agent 完成。
8. 删除 Page Blueprint 的生成、作者包装、支持性校验、收据和恢复节点，不引入 `Approved Page Contract` 或其他等价替代层。
9. 稳定 `slideId` 仅作为数据库身份、编辑和断点恢复键存在，不再承担内容或设计合同职责。
10. PPT-Master Strategist 直接读取已批准意图、Outline、来源材料及自由设计/模板选择，负责产生并锁定设计方案；Executor 依据该方案创作 Direct SVG。

### 2026-08-27 视觉复核 opt-in v3 修订决策（已批准，核心链路已实施）

11. 新任务冻结 `visual-review-opt-in@v3`；视觉复核默认 `required=false`、`maxRounds=0`，只有用户在网站或请求中明确启用时才进入视觉复核阶段。
12. 默认生成链路不调用视觉审核模型；final SVG、内容、图表和 package 等确定性检查始终运行并披露。其中 PPT-Master SVG checker 的 `error` 必须阻断并进入确定性修复循环，`warning` 才可在披露后继续；其他质量门按各自明确的 blocking/advisory 分类执行。
13. 新任务只保留 `off` 和 `standard`。标准视觉复核只运行一轮审核和最多一次逐页原子修复，不提供终稿二次验证模式。
14. 视觉 Hard/Soft 规则采用 PPT-Master 语义：裁切、溢出、重叠、不可读、图片损坏和明确关键元素缺失属于 Hard；留白、节奏、轻微对齐、层级和风格一致性默认属于 Soft。Soft 不得通过关键词或类别自动升级为 blocking。
15. 视觉修复不得重写页面内容、品牌决策或布局结构；每次修复必须有页级备份、受限差异和前置哈希，修复引入新 Hard 时只回滚受影响页面。
16. v3 不设置视觉 `needs_human` 决策点。超出自动修复权限、修复后仍存在或无法稳定判断的主观视觉问题统一写入 `passed-with-warnings`；修复引入确定性退化时自动按页回退，并在重新取得零 SVG error 的 final 报告后继续导出供用户检查。
17. 历史 `visual-review-adaptive@v1/v2` 快照继续按冻结轮数和旧决策解释；新 v3 策略不得改写历史证据、恢复语义或已发布 Revision。

### 2026-08-28 PPT-Master 页面契约对齐修订决策（已实施，外部回归待完成）

18. Vendored PPT-Master 是页面策划、跨页锁定、SVG 语义和质量检查的唯一权威；本项目不得复制、改写或另行发明标题、页码、角色、字号等页面语义合同。
19. “照搬 PPT-Master”指复用其 Default Generate 阶段边界和原始参考文件，不编辑 `vendor/ppt-master`，也不重新引入 Page Blueprint、Approved Page Contract 或其他等价逐页中间工件。
20. `design_spec.md §IX` 是唯一页面计划，`spec_lock.md` 是唯一跨页执行锁，完整 SVG 是唯一可见页面真源。Approved Sources/Outline 是 Strategist 的输入；稳定 PNN、`slideId`、租户和存储键仅属于应用持久化上下文。
21. 新 Agent 任务先对齐项目已固定的 PPT-Master `v4.7.0`；升级到其他版本必须作为独立 vendor 升级执行，不与页面契约迁移混合。
22. Executor 必须通过只读、路径白名单和哈希留痕读取 vendored Executor/shared/semantic 参考，不再依赖 Runtime 对上游规范的局部转述。
23. 本项目的 SVG 写入前校验只负责机械可解析性、当前页写入权限、资源路径和主动内容安全。标题标记、标题精确文本、统一字号下限、固定页码位置和页面布局不得作为应用自定义的写入前阻断条件。
24. PPT-Master 的原始检查报告必须完整保留。v3 编排层只能将上游 `warning` 映射为 `passed-with-warnings`，不得把 SVG checker 的 `error` 重分类、忽略或覆盖；Step 7 只接受当前 SVG roster 对应、哈希可验证且 `errorCount=0` 的 final 报告。畸形 XML、危险引用、文件缺失或实际编译/写入失败仍属于任务失败。
25. 视觉复核继续只提供 `off` 和 `standard`，默认 `off`；该产品策略独立于 PPT-Master 页面契约，不得通过视觉复核重新建立页面合同或人工接受基线步骤。

### 2026-08-28 PPT-Master 三层 SVG 限制与修复循环补充决策（已实施，外部回归待完成）

26. 三层限制按 PPT-Master 原生职责划分：第一层是 Executor 作者合同与 semantic SVG/text/CSS 兼容约束；第二层是 P01 首屏门禁和整稿 final 门禁；第三层是 `svg_to_pptx.py` 在导出前独立校验当前、final、哈希匹配且无 blocking error 的报告。
27. Vendored PPT-Master checker/converter 是唯一规则权威。Worker 可以增加路径、安全、状态编排和结构化诊断 adapter，但不得复制一份会独立演化的 SVG 标签/属性/文本样式 allow-list，也不得让本地摘要覆盖 vendored 结果。
28. P01 和 final 的确定性修复循环均不设置硬轮次上限：每次失败读取同一次未截断检查产生的完整 blocking 集合及 advisory warnings，选择需要处理的 warning，与全部 error 在一次集中编辑中修复，然后只执行一次统一复检；若仍失败，以该次完整结果开始下一轮，直至通过或出现需要用户/外部资源介入的真实 blocker。
29. 不得因达到固定轮数、连续无改善、Token/耗时预算或单页修复次数而将 SVG checker error 自动降级、返回 `passed-with-warnings` 或继续导出。任务取消、Provider/基础设施不可用、缺失必需资源等仍按所属恢复规则处理，但不得伪装为质量门通过。
30. P01 通过后必须连续生成 P02…Pn，不插入逐页 checker 或中途整稿 checker。写入前轻量预检如保留，只能复用同一兼容性实现检查当前 payload 的机械/安全问题，不能运行完整质量门或改变 P01 → 连续生成 → final 的节奏。
31. `warning` 始终是 advisory，不能触发强制修改；`error` 始终 blocking。默认 Generate 不得通过 `--allow-quality-warnings` 或应用层 receipt 绕过 error；只有一个当前、final、源哈希匹配、可验证且零 error 的报告才能进入 native PPTX export。
32. 上述无硬上限仅适用于确定性 SVG checker 修复循环，不改变 opt-in v3 的视觉 Reviewer 预算，也不取消结构化 Provider 输出、网络重试或基础设施层已有的独立保护边界。

## 目标链路

### v2 已实现历史链路

```text
Approved Snapshot
→ PPT-Master Strategist reads approved Intent / Outline / Sources
→ Stage-1 communication + free-design/template confirmation
→ Stage-2 solution and design_spec
→ design confirmation
→ spec_lock
→ Executor Direct SVG P01
→ first-page gate
→ Executor Direct SVG P02…Pn
→ final SVG/content gates
→ render PNG/contact sheet
→ multimodal visual review
→ adaptive Direct SVG repair
→ final SVG gate after every repair
→ pass | stalled | max-rounds
→ SVG→DrawingML/PPTX only on pass
```

### opt-in v3 新任务目标链路

默认模式：

```text
Approved Snapshot
→ PPT-Master Strategist / design confirmation / spec_lock
→ Executor Direct SVG P01…Pn
→ final SVG gate (0 errors; warnings disclosed) / content / chart checks
→ SVG→DrawingML/PPTX
→ package QA
→ published
```

用户明确启用标准视觉复核：

```text
final SVG / content / chart checks recorded
→ save visual-review baseline SVG roster
→ render PNG/contact sheet
→ one multimodal visual review
→ atomic page-scoped fixes only
→ page check + final SVG checker 无硬上限集中修复循环，直至 0 errors
→ retain repair or automatically roll back affected pages
→ export with disclosed warnings
```

## 实施范围

### A. Direct SVG-only

- 删除 `SceneContract`、`SceneNode`、`SlideSceneGraph` 及 Scene Graph 渲染/自动布局代码。
- `write_or_patch_slide_svg` 只接受 `mode=direct-svg`。
- 初次创作、SVG gate 修复和视觉修复均保持 Direct SVG。
- 视觉预览只渲染 `svg_output/*.svg`。
- 删除活动合同中的 `slide-scene-graph.v1.schema.json` 和 canonical bundle 的 `agent/scene-graphs` 收集逻辑。
- 更新 Fixture Provider、Agent prompt、Schema 生成器和相关测试。

### B. 自适应视觉审核

- 新快照冻结 `visual-review-adaptive@v2` 与 `maxRounds=5`；旧 v1 快照保留其冻结轮数。
- Worker 请求携带 `visualReviewMaxRounds`，禁止运行时使用与快照无关的全局常量决定轮数。
- 为 finding 生成跨轮稳定指纹：`category + scope + pnn + normalized region`。
- 每轮写入 decision evidence：blocking/advisory/affected pages、score、best round、stagnation count、SVG hash、decision 和 reason。
- 质量改善才继续；连续两轮无改善提前停止；恶化时恢复最佳 SVG 并重跑 final gate。
- 硬上限第五次只作最终验收，不再启动第六次审核。

### C. 移除 Page Blueprint，恢复 PPT-Master 自由设计主链路（已实施）

#### C1. 删除 Page Blueprint 运行时

- 删除或停用 `PageBlueprintArtifact`、`_build_page_blueprint()`、`_author_blueprint_with_agent()` 和 `validate_page_blueprint()`。
- 不再生成 `page-blueprint.proposal.v1.json`、`page-blueprint.v1.json`、`page-blueprint-support.json`。
- 删除所有 `BLUEPRINT_*` 错误码、支持分阈值、`page-blueprint-gate` 收据和对应检查点。
- 从 Workflow Model、请求合同、Agent Tool Context、canonical bundle 和恢复逻辑中移除 Blueprint 字段与哈希绑定。
- 不建立 `Approved Page Contract`、页面内容合同或其他语义等价的替代中间层。

#### C2. Strategist 直接规划

- `read_approved_context` 直接向 Strategist 提供用户提示词、已确认 Intent/Outline、来源文档及解析结果、模板或 `free_design` 选择、图片/图表策略和视觉审核策略。
- Strategist 自主完成整体叙事、视觉语言、逐页沟通目标、内容组织、布局、图表/表格/图片建议，并生成 `design_spec.md`。
- 不再向 Strategist 注入预先计算的 `visualForm`、`layoutIntent`、`contentBlocks`、`assertion` 或自动组合的证据片段。
- 设计方案经用户确认后生成 `spec_lock.md`；未确认不得启动 Executor。

#### C3. 网站与状态机

目标状态流调整为：

```text
outline_approved
→ strategizing
→ awaiting_design_confirmation
→ design_confirmed
→ spec_locked
→ executing
→ deck_qa
→ visual_review
→ compiling
→ published
```

- 网站增加设计方案摘要与确认入口；拒绝时回到 Strategist 重新规划。
- 若分阶段交付 UI，过渡版本必须在 Outline 批准页明确展示并记录对 Strategist 设计和锁定的授权，不得以隐藏的服务端默认代替确认。
- 新任务写入新的工作流版本；旧运行和已发布 Revision 保持不可变。

#### C4. Executor 与工具门禁去 Blueprint 化

- `write_or_patch_slide_svg` 仅依据 `design_spec.md`、`spec_lock.md`、已批准 Outline、来源材料和当前页身份工作。
- 删除对 `page.role`、`page.assertion`、`page.contentBlocks`、`page.visualForm`、`page.chartSpec` 及 Blueprint 标题/要点支持分的依赖。
- Direct SVG 工具门禁只校验安全 SVG、画布、页面归属、标题/页码等必要结构、资源路径、图表/表格来源事实和锁定的关键数字。
- `slideId` 保留为持久化与恢复键，但不得反向决定页面内容、布局或视觉形式。

#### C5. 质量门与事实校验重新定位

- 删除生成前的 `page-blueprint-support` 阻断门。
- P01 仅执行 PPT-Master 首屏方法门禁；通过后连续生成 P02…Pn，不插入 Blueprint 或中途整稿检查。
- 全页完成后运行 final SVG gate，统一检查缺页、越界、重叠、文本溢出、必要标题/页码、图表数据和明确事实。
- 内容 QA 只对来源引用、关键数字、价格、基准成绩、明显矛盾和批准 Outline 的实质缺失进行阻断；中文词面相似度不得作为单独发布阻断条件。
- 视觉审核、返修、最终 SVG 复检、PPTX 编译和 package QA 保持串行，并且只有通过全部 blocking 门才能发布。

#### C6. 恢复、版本与迁移

- 新流程建议冻结为 `instant-ppt-default@v3`，旧 v2 快照继续按其历史合同只读解释。
- 新检查点序列为：`source-ready → strategist-complete → design-confirmed → spec-locked → p01-passed → p02…pn-complete → final-svg-passed → visual-review-passed → pptx-published`。
- 删除 Blueprint 检查点后，从最近的 Strategist、Spec、页面或最终门禁检查点恢复，不重新执行已确认的 Provider 调用。
- 部署前排空旧 Blueprint 运行；历史 Blueprint 工件可按保留策略留存，但新工作流不得读取或生成。

### D. 视觉复核 opt-in v3（核心链路已实施）

#### D1. 用户触发与策略冻结

- 网站生成设置只提供 `off` 和 `standard`，默认 `off`。
- 用户选择必须写入不可变 Snapshot，并投影为 `visualReviewRequired`、`visualReviewMaxRounds` 和策略版本；Worker 不得根据页数、模型能力或内容自动启用。
- 新任务默认冻结 `visual-review-opt-in@v3`、`required=false`、`maxRounds=0`；标准复核冻结一次审核/一次修复预算。
- 作者模型和视觉审核模型分别记录为 `authoringModel` 与 `visualReviewModel`；未启用视觉复核时不得初始化或调用视觉审核 Provider。

#### D2. 审核输入与固定规则

- 每个审核批次必须包含页面 PNG/SVG、PNN、页面角色、标题、`design_spec.md §IX` 对应页面要求、`spec_lock.md` 的画布/字体/颜色/锚点约束，以及固定 Hard/Soft/Don't-touch 规则。
- Reviewer 保持只读，只返回结构化 finding；运行时负责稳定 ID、指纹、最终 severity、所有权和哈希证据。
- Hard 仅限明确影响交付的问题：越界、文字裁切/溢出/重叠、关键元素碰撞、明显不可读、图片损坏或严重变形、已声明标题/页码/关键元素缺失。
- Soft 包括留白、节奏、轻微对齐、卡片间距、视觉层级、图文关系和风格一致性；采用“明显有问题才报告/处理”的阈值，不参与发布阻断或最佳版本评分。
- 删除 `_MATERIAL_ADVISORY_MARKERS` 等基于词语的 severity 提升；`deck-consistency` 不得默认提升为 blocking。

#### D3. 逐页原子修复边界

- 新增专用受限视觉修复能力，或在 `visual-repair` 阶段对完整 SVG 提交执行严格 DOM 差异审计；不得继续把合法的整页 SVG 重写等同于安全视觉修复。
- 自动修复必须同时满足：`severity=blocking`、`autoFixEligible=true`、`scope=page`、目标元素稳定 ID 明确、规则属于许可集合。
- 允许修改位置、尺寸、字号、字距、对齐、局部间距、必要换行和可读性遮罩；禁止修改正文事实、品牌颜色、字体家族、元素语义/稳定 ID、栏目数量、页面结构、图表类型、图片资源及其他页面。
- 每次修改携带 `expectedBeforeSha256`，并在首次编辑前保存 `.review/backup/<page>.iter<N>.svg`；证据记录修改元素、属性、前后哈希、解决/新增指纹和回滚原因。
- 修复后先运行当前页 SVG gate，再运行 final SVG gate；新增 Hard 或确定性 gate 失败时只恢复对应页备份，不恢复整套 SVG。

#### D4. 决策、警告与导出

- 新 v3 请求不使用 `[blockingCount, affectedPageCount, advisoryCount]` 总分、`quality-regressed` 或 `stalled-two-rounds` 驱动多轮自由返修；旧 v2 请求保留原实现。
- 标准复核完成一次安全修复后即结束视觉 Reviewer 循环；advisory 或单次不稳定主观 finding 写入 `passed-with-warnings` 收据。随后确定性 SVG 门禁必须独立达到 0 errors 才允许导出。
- 超出修复权限、修复后仍存在或未能稳定判断的 finding 写入 `deferredFindings[]`，任务以 `passed-with-warnings` 继续导出，不增加人工恢复分支。
- 修复版触发页级或整稿确定性退化时自动恢复对应页的审查前基线；未受影响页面保持不变。
- SVG、内容、图表、postflight 与 package QA 报告始终保留；SVG checker error 必须进入无硬轮次上限的集中修复循环，不能作为警告导出。其他检查只在其所属合同明确分类为 advisory 时允许随成功产物披露；无法生成 PPTX、文件缺失或写入失败仍属于机械性交付失败。

#### D5. 网站、预览与证据

- 视觉复核前保存 `agent/visual-reviews/baseline-svg/`，并在网站中始终提供基线预览；修复版与基线版使用明确标签，禁止静默替换。
- 网站按页展示 `ok`、`fixed`、`rolled_back`、`warning`，同时展示修复属性、回滚页和剩余 Hard/Soft 数量。
- `passed-with-warnings` 在 final SVG 报告零 error 时始终提供正常下载；基线、修复备份和检查报告保留为用户核查证据。
- `validation/visual-review.json` 和视觉收据记录策略版本、用户选择、作者/审核模型、审核次数、Provider 用量、耗时、基线哈希、最终哈希和延后 finding。

#### D6. 主要实现位置

- `packages/domain/src/instant_ppt_domain/generation.py`：默认关闭视觉复核，冻结 opt-in v3 策略及模型配置。
- `services/worker/src/instant_ppt_worker/default_workflow_request.py`、`workflow_models.py`：解析用户选择、级别、轮次和历史兼容。
- `services/worker/src/instant_ppt_worker/visual_review_runtime.py`：固定规则、完整页面上下文、取消关键词升级、单轮决策和新报告证据。
- `services/worker/src/instant_ppt_worker/agentic_workflow.py`：条件进入视觉阶段、保存基线、页级修复/自动回滚、确定性检查披露和导出。
- `services/worker/src/instant_ppt_worker/presentation_agent_tools.py`、`presentation_agent_runtime.py`：受限视觉差异合同和 Don't-touch 强制校验。
- `apps/web/src/app/workspace-app.tsx` 及对应 API/Snapshot 合同：`off`/`standard` 用户开关、基线预览和警告展示。

### E. PPT-Master 页面契约对齐实施计划

#### E1. 冻结契约边界与版本

- 新增页面契约权威 ADR，并在 ADR-012、ADR-004 和本 Issue 中交叉引用：Approved Sources/Outline 提供输入，`design_spec.md §IX` 提供页面计划，`spec_lock.md` 提供跨页约束，SVG 提供最终页面表达。
- 新契约版本只应用于新 Snapshot；旧任务继续按其冻结合同恢复和解释。迁移期间不得改写历史设计方案、SVG、检查报告或已发布 Revision。
- 第一阶段以仓库固定的 PPT-Master `v4.7.0` 为准；对 `v4.8.0` 或后续版本的升级另建提交和回归矩阵，避免把 vendor 差异与应用契约迁移混在一起。
- 本项目只保留租户/鉴权、对象存储、任务取消、幂等、PNN/`slideId` 映射、来源隔离、Token/耗时审计、主动内容安全和产品审核策略，不再拥有页面设计语义。

#### E2. 原样采用 Design Spec 与 Spec Lock

- `design_spec_contract.py` 恢复 PPT-Master 原生页标题格式 `Slide NN - <page name>`，移除本项目增加的 `Slide NN / PNN - <title>` 语法。
- PNN、`slideId` 和数据库身份继续由批准页面 roster 按页序映射，不写入 `design_spec.md`，也不形成新的页面合同文件。
- 保持页数和页序稳定，但取消“§IX 标题必须与 Outline 标题逐字相同”的本地限制。用户明确提供的标题按原文保留；模型生成的策划标题允许 Strategist 按 PPT-Master 规则在不改变主题与事实的前提下优化。
- Agent 路径不再由硬编码 `_spec_lock()` 注入统一 48/64px 标题下限或固定 flat 设置。新增 `read_spec_lock_contract`，由 Strategist 根据已确认 Design Spec 和 vendored `spec_lock_reference.md` 生成 `spec_lock.md`，随后调用 vendored `project_manager.py validate`。
- 确定性模板回退如继续保留 `_design_spec()` / `_spec_lock()`，必须明确限定在 template fallback，并保证输出符合未修改的上游模板，不能反向成为 Agent 页面的契约权威。

#### E3. 向 Executor 暴露原始 PPT-Master 规范

- 在 `presentation_agent_tools.py`、`presentation_agent_runtime.py` 和 `workflow_models.py` 增加只读 `read_ppt_master_reference` 工具；仅允许访问 vendored 白名单文件并记录路径、版本和 SHA-256。
- Executor P01 必须完整读取 `executor-base.md`、`shared-standards-core.md`、`semantic-svg.md`、`svg-effects.md`、`native-shape-authoring.md` 及 Spec Lock 触发的专项参考；后续页面复用哈希绑定的阅读收据，恢复、上下文失效或参考哈希变化时重新读取。
- 删除 Runtime 中“唯一标题 ID、固定字号、精确 Outline 标题、右下角 PNN”等本地摘要，避免摘要与 vendored 规范形成两个真源。
- 更新 Agent required-tools 证据：Strategist 必须读取 Design Spec/Spec Lock 原始合同，Executor 必须读取执行参考、批准上下文和设计目录，缺少阅读收据时不得进入对应创作阶段。

#### E4. 收窄 Direct SVG 写入前校验

- 将 `_validate_direct_svg_against_page()` 收窄为应用边界校验：当前 PNN/目标路径、payload 大小、XML 可解析、禁止脚本/事件处理器/`foreignObject`、禁止未批准外部引用、限制项目内图片和跨租户路径。
- 删除以下本地阻断：必须存在 `id="title"` 或 `data-pptx-role="title"`、标题与 Outline 逐字相等、封面 64px/普通页 48px 下限、固定右下角 PNN、Outline 业务角色必须等于根 `data-pptx-page-role`。
- 应用安全层采用主动内容 deny-list 和 URI/路径限制，不再用一个比 PPT-Master 更窄的展示标签 allow-list 代替上游兼容性检查；`use`、`symbol`、链接等能力按上游参考和转换器实际支持处理。
- 来源、数字、图表和表格事实在 SVG 完成后由其所属内容/图表质量门检查并披露，不在写文件之前以标题或词面相似度触发工具失败。
- 作者合同明确采用 vendored `shared-standards-core.md` 的封闭 visual-property grammar：inline style 仅允许其声明的 paint/line、text、alpha/definition paint、literal geometry 和 preview-only 属性；条件属性必须使用上游规定的直接 XML 形式，未知或未映射声明由 checker/native export 阻断。
- 文本样式遵循上游精确语义和值域：`font-family`、`font-size`、`font-weight`、`font-style`、`text-anchor`、`letter-spacing`、`text-decoration`；`text-anchor` 不得用于 `<tspan>`，普通上下标只允许 `<tspan baseline-shift="super|sub">`。从视觉修复许可属性中删除未受支持的 `dominant-baseline`，避免修复器生成作者合同外语法。
- 新增的 `ppt_master_svg_contract.py`（或等价 adapter）只负责调用/归一化 vendored 规则并返回稳定诊断，例如 `SVG_TEXT_PROPERTY_UNSUPPORTED`、`SVG_NATIVE_PREFLIGHT_ESCAPE`；诊断码属于应用观测接口，不构成另一份语义规则表。

#### E5. 对齐 flat / structured SVG 语义

- flat 页面根角色只使用 PPT-Master 定义的 `cover`、`toc`、`section`、`content`、`ending`；本项目的 `data`、`comparison`、`timeline`、`risk_action` 只作为策划/UI 元数据，不直接写入根页面角色。
- `data-pptx-role` 只使用上游结构角色；普通标题不再标记为 `data-pptx-role="title"`，标题是否存在和如何布局由页面设计与上游检查器判断。
- structured 模式按 `spec_lock.pptx_structure.mode` 省略根 page-role，改用 Master/Layout、layer atoms 和 slots。先完成当前默认 flat 迁移，再启用 structured/template 回归。
- 不直接修改 vendored `semantic_markers.py` 或其他 PPT-Master 文件；应用通过 adapter 调用原始 checker/converter，并保留原始输出。

#### E6. 对齐生成节奏、检查与发布语义

- 采用 PPT-Master Default Generate 节奏：P01 写入后运行一次未截断的首屏门禁；门禁通过后连续生成 P02…Pn，期间不运行逐页或中途整稿 checker；整稿完成后运行一次未截断的 final SVG gate，再按顺序运行内容、图表和 package 检查。
- 实现三层限制：作者层直接读取并遵守 vendored Executor/shared/semantic/text-CSS 规范；门禁层复用 vendored `svg_quality_checker.py` 的 P01/final 报告；导出层由 vendored `svg_to_pptx.py` 独立验证当前 final 报告、SVG roster 哈希和零 blocking error。
- 删除 `FINAL_SVG_REPAIR_HARD_MAX_ROUNDS` 及所有“达到固定轮数即失败/警告导出”的确定性 SVG gate 分支。`repairRound` 可以继续作为单调递增的审计字段，但不得成为终止条件。
- 每轮修复严格执行：读取该次检查的完整 blocking issue set 和 advisory warnings → 决定需处理的 warning → 一次集中修改全部 error 与所选 warning → 一次统一复检。复检仍失败时使用新报告进入下一轮；不得在单个问题修复之间反复运行 checker，也不得按“下一条错误”逐个发现。
- 修复循环不以固定轮数、停滞分数或质量评分退出。只有 final report `errorCount=0` 才通过；若必需资源缺失、Provider/基础设施不可用或用户取消，则按 owning-source recovery 暂停/失败，并保留最近完整报告，不得伪造通过。
- 写入前预检如保留，应集中到 `ppt_master_svg_contract.py`（或等价 adapter），并复用 vendored 解析/兼容规则。该预检只处理当前页 XML、资源、安全及可确定的转换兼容错误，不能复制本地页面语义 allow-list，也不能替代或额外触发完整 checker。
- 原始 PPT-Master 报告不可篡改或丢弃。`workflow_state.py` 和 export receipt 必须明确区分 `passed`、`passed-with-warnings` 与 `blocking`；其中 `passed-with-warnings` 只能包含 advisory warning，不能包含任何 SVG checker error。
- Production Worker 移除默认 `--allow-quality-warnings` 绕过路径。导出前若报告缺失、损坏、非 final、与当前 SVG 哈希不匹配、过期、不可验证或包含 blocking error，返回 SVG final gate 修复循环；转换本身失败时修复 owning source 后只重跑受影响的 gate 与 Step 7 下游步骤。
- `off` 模式不调用视觉 Reviewer；`standard` 仅执行一次审核和最多一次页级原子修复。修复退化时自动按页恢复复核前基线，不新增人工接受基线、手动恢复或额外导出分支。

#### E7. 测试、真实回归与迁移

- 单元测试覆盖：上游原生 Design Spec 标题、Spec Lock 生成与校验、标题无需固定 ID、非固定标题字号/页码、canonical page-role、flat/structured 分支和主动内容安全阻断。
- 单元测试新增：P01/final 完整问题集集中修复、warning 非阻断、error 必阻断、`repairRound` 不参与终止判定、过期/错哈希/非 final 报告拒绝导出，以及写入前 adapter 与 vendored validator 不产生第二份规则表。
- 集成测试覆盖：构造超过旧四轮上限后才通过的 SVG repair fixture，证明第五轮及后续轮次仍可继续并最终导出；构造持续 blocking 的可取消 fixture，证明系统不会因轮数自动降级或导出；畸形 XML、危险外链和实际 PPTX 编译/写入失败必须失败。
- 回归测试确认 P01 通过后 P02…Pn 之间没有 checker 调用，final 每个失败批次仅有一次检查和一次集中修复，最后一次通过报告与导出输入 SVG roster 哈希一致；页数、页序、PNN/`slideId`、数据库映射和恢复检查点保持稳定。
- 使用官方 Qwen API、同一模型、同一 GPT-5.6 DOCX 和提示词执行迁移前后 A/B。计时从文档上传开始，分别记录总耗时、各阶段耗时、输入/输出/总 Token、工具失败/修复次数、检查警告、6 个 SVG、6 页 PPTX 和 PowerPoint/WPS 打开结果。
- 回归必须证明此前 P05 的标题契约错误不再出现，生成能够继续进入 P06 和导出阶段；不得通过放宽主动内容安全或伪造通过报告达成。
- 建议按以下提交拆分：`docs: define ppt-master as page contract authority`、`refactor(worker): adopt upstream design spec and spec lock`、`refactor(worker): remove local svg page semantics`、`feat(worker): expose vendored executor references`、`test(worker): add contract and real-qwen regression coverage`。

## 不变量

- 不改变批准 Outline、稳定 slide ID、来源事实、图表值或图片授权；稳定 ID 只承担持久化身份，不构成页面合同。
- P01、final SVG、内容、图表、postflight 与 package QA 检查不得省略；PPT-Master SVG checker 的 error 是成功导出的前置阻断条件，warning 才可随产物披露。其他检查严格遵守各自合同声明的 blocking/advisory 分类。
- 不允许任意 Shell、外部 SVG 资源、脚本、事件处理器或跨租户路径。
- 崩溃恢复不得重复已确认的 Provider 调用或重复计费。
- v1/v2 历史任务继续遵守其冻结的 blocking 语义；v3 新任务的可选视觉复核是辅助检查，但不得弱化 PPT-Master 确定性 SVG error 的 blocking 语义。只有 final SVG 报告零 error 且 native export 成功时才允许下载，并完整披露 advisory finding。
- 未启用视觉复核时不得调用视觉审核 Provider；启用后也不得借视觉修复修改批准 Outline、来源事实、品牌锁或页面结构。

## 验收标准

- [x] 新 Agent 任务只生成 Direct SVG，canonical bundle 中无新 Scene Graph 工件。
- [x] 非法/外部/跨页 SVG 和不受支持的图表数据继续 fail closed。
- [x] 首轮零 blocking 时只调用一次 Reviewer。
- [x] 返修改善时可继续至最多第五次审核。
- [x] 连续两轮无改善时提前停止并保留最佳 SVG。
- [x] 返修恶化时恢复最佳 SVG 并重跑 final SVG gate。
- [x] 第五次审核仍有 blocking 时返回 `needs_manual`，不导出 PPTX。
- [x] 历史视觉策略仍按冻结轮数解释；新请求显式冻结 v2/max 5。
- [x] Worker 179/179、Domain 33/33、定向端到端与 Ruff 回归通过。
- [x] 发布前补跑冻结 Golden 与 PowerPoint/WPS 双应用兼容回归。
- [x] 新任务不再创建或读取 Page Blueprint、Blueprint gate、Blueprint receipt 或等价页面合同。
- [x] Strategist 能直接根据已批准 Intent/Outline/Sources 生成 `design_spec.md`，确认后生成 `spec_lock.md`。
- [x] 网站支持 `awaiting_design_confirmation`，未确认设计方案时不得启动 Executor。
- [x] Executor 和 `write_or_patch_slide_svg` 不再依赖任何 Blueprint 字段。
- [x] 同一 GPT-5.6 DOCX/六页中文大纲可完成真实生成，不再出现 `BLUEPRINT_*` 错误。
- [x] P02“模型家族概览”和 P04“设计判断力”作为真实中文回归用例，不得因词面支持分被阻断。
- [x] P01 门禁、P05 工具失败恢复、final SVG 返修哈希变化、视觉审核和 exact export 均有真实链路回归。
- [x] PowerPoint/WPS 可打开最终六页 PPTX，文字、基础图形和原生图表保持可编辑。

### opt-in v3 新增验收标准

- [x] 新任务默认冻结 `visual-review-opt-in@v3`、`required=false`、`maxRounds=0`；网站默认不勾选视觉复核。
- [x] 默认模式完成生成和导出时，视觉审核 Provider 调用次数严格为 0；final SVG/content/chart/package 检查仍运行并生成报告。
- [x] 用户启用标准视觉复核时，只运行一轮审核和最多一次逐页原子修复，不出现 `quality-regressed` 或自动多轮整稿重画。
- [x] API、网站和新 v3 Worker 合同只接受 `off`/`standard`，拒绝已移除的 `final`。
- [x] Reviewer 输入包含 PNG/SVG、页面角色、`design_spec.md §IX` 页面要求、`spec_lock.md` 和固定 Don't-touch 规则。
- [x] 留白、节奏、层级和风格一致性等 Soft finding 不会因关键词或类别被升级为 blocking，也不参与最佳版本评分。
- [x] 视觉修复仅允许受限属性/局部操作；正文、品牌 token、字体家族、稳定 ID、页面结构、图表类型和其他页面变化均被拒绝。
- [x] 修复导致新 Hard 或确定性 gate 失败时，只回滚受影响页面，未修改页面和已验证改善页保持不变。
- [x] v3 不产生视觉 `needs_human`；未修复的主观视觉 finding 写入 warning/报告，修复退化自动按页回退。确定性 SVG error 返回无硬轮次上限的修复循环，不得降级后导出。
- [x] 作者模型与视觉审核模型、调用次数、用量及分阶段耗时分别记录；未启用视觉复核时不存在视觉模型费用。
- [ ] 使用 Qwen 官方 API、`qwen3.7-plus`、指定 GPT-5.6 DOCX 和提示词“根据GPT5.6的官方公告做一份6页的PPT”完成默认模式真实网站回归，生成 6 个 SVG 和 6 页 PPTX，并记录总耗时。
- [ ] 对同一输入启用标准视觉复核完成对照回归，保存基线/复核逐页截图、修改/回滚证据、视觉耗时和最终 PPTX；主观视觉 warning 不阻止下载，确定性 SVG error 必须修复至零后才可生成最终 PPTX。

### PPT-Master 页面契约对齐新增验收标准

- [x] `design_spec.md` 使用未修改的 PPT-Master §IX 页面格式；PNN/`slideId` 只存在于应用 roster、持久化与恢复上下文中。
- [x] Agent 路径的 `spec_lock.md` 由 Strategist 依据 vendored reference 生成并通过原始 validator，不再由本地硬编码 48/64px 规则主导。
- [x] Executor 的必读证据包含 vendored 执行/共享/语义参考及 SHA-256；Runtime 不再维护标题、页码、字号和页面角色的第二份摘要合同。
- [x] Direct SVG 写入前校验不要求标题固定 ID、精确 Outline 标题、统一字号下限或右下角 PNN，同时继续拒绝畸形 XML、主动内容、危险引用和跨租户路径。
- [ ] flat 根角色和 structured Master/Layout 语义均通过原始 PPT-Master checker；普通标题不使用未定义的 `data-pptx-role="title"`。
- [x] 原始质量报告完整保留；`passed-with-warnings` 只包含 advisory warning，任何 SVG checker error 都阻止导出并进入无硬轮次上限的集中修复循环；实际编译、文件写入或安全失败仍使任务失败。
- [x] 已删除 `FINAL_SVG_REPAIR_HARD_MAX_ROUNDS` 及等价固定终止条件；超过旧四轮阈值后仍能继续修复，直至 final SVG report 为零 error。
- [x] 每个失败批次只执行一次完整 checker、一次集中修复和一次统一复检；P01 通过后至 final gate 前无中途 checker 调用。
- [x] 导出器只接受当前、final、SVG roster 哈希匹配、可验证且零 blocking error 的质量报告；Production Worker 不使用覆盖参数绕过错误。
- [x] 可选视觉 Reviewer 仍保持 `off`/`standard` 和一次受限修复，其预算与确定性 SVG gate 的无硬上限循环相互独立。
- [ ] 官方 Qwen 六页真实回归从文档上传开始记录时间与 Token；P05 不再因标题契约失败，任务完成 P06、PPTX 导出和 PowerPoint/WPS 打开验证。

## 发布策略

1. 先部署能读取旧策略、但新快照写入 v2 Direct SVG/adaptive 策略的兼容版本。
2. 排空旧 `presentation-authoring@v1` 运行任务；已发布历史工件保持不可变。
3. 运行冻结 Golden、Agent 证据、视觉闭环、恢复和 exact export 回归。
4. 灰度只影响新快照；失败时停止接纳 v2，新旧已发布 Revision 均不改写。
5. Page Blueprint 移除使用新工作流版本灰度；旧 v2 运行排空后，新任务只进入无 Blueprint 的 Strategist → Spec → Executor 链路。
6. opt-in v3 只影响新 Snapshot；先上线可同时解释历史 adaptive v1/v2 和新 opt-in v3 的兼容 Worker，再切换网站默认值。
7. 灰度期间对比默认无视觉复核与用户启用标准复核的成功率、总耗时、Provider 成本、警告率和页面回滚率。
8. v3 回滚时停止创建新 opt-in v3 Snapshot，恢复网站开关策略；历史运行、证据和已发布 Revision 均保持不可变。

## 完成记录

2026-08-26 已完成代码与合同实现：移除活动 Scene Graph 作者路径及 Schema；新快照冻结 `presentation-authoring@v2-direct-svg`、`visual-review-adaptive@v2`、`maxRounds=5`；旧请求缺省仍解析为三轮。视觉 finding 具备跨轮稳定指纹，每轮持久化可解释质量指标与决策证据，保留最佳 SVG，停滞/恶化/硬上限均 fail closed 到 `needs_manual`。

验证结果：Worker `179/179`、Domain `33/33`、Ruff、Schema 物化一致性和 `git diff --check` 通过。Windows 默认 pytest 临时目录及工作区中文临时路径存在既有访问/子进程编码噪声，最终全量测试使用唯一 ASCII 临时目录完成；该目录将在验证后清理。发布前仍需执行冻结 Golden 和 PowerPoint/WPS 人工兼容回归，因此 Issue 实现已完成但发布验证项保持开放。

2026-08-27 已完成 C 段修订：活动运行时、Schema、恢复、canonical bundle 和质量门中不再生成或读取 Page Blueprint，也没有引入等价页面合同。新 `instant-ppt-default@v3.0.0` 链路由 Strategist 直接读取批准的 Intent、Outline、Sources、资源和冻结策略并生成完整 `design_spec.md`；网站在大纲批准页明确展示并记录 `strategist-design-and-lock` 授权，未授权时停在 `awaiting_design_confirmation`，且不存在 `spec_lock.md` 或 Executor SVG。授权后写入 hash-bound `design-confirmation` receipt，再锁定 Spec 并进入 Direct SVG Executor。发布追踪改为后置 `release-trace.json`，只记录已经创作并通过门禁的页面，不承担前置语义合同职责。

最终验证覆盖 Worker `192/192`、Domain/API `46/46`、G06 真实 PostgreSQL/Redis/MinIO 集成 `14/14`、G07 `5/5`、Contracts `27 schemas / 39 endpoints / 171 fixtures`、Web lint/typecheck/production build、Ruff、冻结 Golden `10/10 source + 10/10 render + 40/40 artifacts`。真实六页中文 Agent 回归生成 6 个 Direct SVG 与 6 页 PPTX，P02“模型家族概览”和 P04“设计判断力”保留，包含 1 个原生可编辑图表；PowerPoint 16 与 WPS 12 均完成 6/6 打开、导出和逐页视觉检查，统计为 34 个可编辑文本形状、1 个原生图表、58 个 shape nodes，未发现裁切或结构破坏。

2026-08-27 已批准视觉复核 opt-in v3 初始修订计划：基于真实 Qwen 回归中“初始版本整体可接受、仅一页存在较明显问题，而后续主观复核使效果退化并阻止导出”的观察，新任务默认关闭视觉复核，仅在用户明确要求时启用。初始计划中的 `final` 与视觉 `needs_human` 语义已被 2026-08-28 决策替代。

2026-08-27 已完成 opt-in v3 核心实现：网站/API 默认 `off`；新 Snapshot 冻结 `visual-review-opt-in@v3`、精确轮次预算及独立作者/审核模型。Reviewer 同时读取 PNG、SVG、页面角色/标题、`design_spec.md §IX` 页面要求、`spec_lock.md` 及固定 Hard/Soft/Don't-touch 规则，Soft 不再由关键词或 `deck-consistency` 类别升级。2026-08-28 进一步收敛为只接受 `off`/`standard`，标准模式只执行一次审核和最多一次页级原子修复。

视觉修复强制 `expectedBeforeSha256`、稳定目标元素、页级备份和 DOM 差异审计，仅允许几何、字号、字距、对齐与局部 transform 属性变化；正文、品牌属性、字体家族、稳定 ID、元素结构、图表和图片变化均 fail closed。修复后运行页级及 final SVG 检查；退化时只恢复受影响页。视觉报告记录基线/最终 roster hash、修复/回滚页、作者/审核模型、真实 Provider 调用次数、Token/成本与耗时，未处理问题写入 `deferredFindings[]`。

2026-08-27 自动化验证：Worker `209/209`、Domain/API `50/50`、Ruff、Contracts `27 schemas / 39 endpoints / 171 fixtures`、Web ESLint/TypeScript/Next production build 全部通过。2026-08-28 的语义收敛移除了“接受复核前基线并导出”恢复动作需求；真实 Qwen 网站对照回归仍待执行，因此 opt-in v3 仍不得宣称完整发布。

2026-08-28 已按当时产品决策完成 v3 收敛：新任务只接受 `off`/`standard`，默认 `off`；标准模式仅一次 Reviewer 调用和最多一次受限修复，不再产生视觉 `needs_human`。该版本曾将未修复视觉 finding 及 final SVG、内容、postflight、package QA 的确定性检查问题统一写入 `passed-with-warnings` 并在 PPTX 可生成时继续发布；底层导出器仅验证报告为当前、final 且哈希匹配。验证结果为已跟踪 Worker `210/210`、Domain/API `51/51`、Ruff、Contracts `27 schemas / 39 endpoints / 171 fixtures`、Web ESLint/TypeScript/Next production build 全部通过。此处作为历史实现记录保留，其中“SVG checker error 可警告导出”的语义已被后续三层 SVG 限制与无硬上限修复循环决策废止；真实 Qwen A/B 网站回归仍待执行。

2026-08-28 已完成 PPT-Master 页面契约对齐代码：新 Snapshot 冻结 `presentation-authoring@v3-ppt-master-authority`，默认工作流升级为 `instant-ppt-default@v3.2.0`。Strategist 使用 vendored 原生 Design Spec 格式并在同一 Agent 会话中生成 `spec_lock.md`，写入前调用未修改的 `project_manager.py validate`；Executor 按锁定分支读取 PPT-Master 原始参考并保存版本、路径和 SHA-256 回执。Direct SVG 写入前只保留 XML、主动内容、引用边界、画布及稳定 ID 等机械/安全检查，标题措辞、字号、页码和页面角色语义交还上游 checker；旧策略快照继续按历史合同解释。

自动化验证覆盖 Worker、Domain 与 API 全量测试、PPT-Master authority 端到端、Ruff 和 Python Schema 生成一致性。当前 Windows 工作区的 pnpm junction 无法读取已安装包，供应商树校验也因非受保护文件树摘要与清单不一致而未完成；受保护的上游文件哈希均匹配。真实 Qwen A/B、structured 模板原始 checker 以及 PowerPoint/WPS 打开验证仍作为发布证据保持开放，不将其误记为本地自动化通过。

2026-08-28 已批准并补充 PPT-Master 三层 SVG 限制与确定性修复循环计划：作者合同、P01/final checker 和导出器独立报告验证分别构成三层门禁；确定性 SVG repair 不设固定轮次上限，按完整问题集集中修复并单次复检，直至零 error 或出现真实外部 blocker。

2026-08-28 已完成三层 SVG 限制与确定性修复循环实现：P01/final error 始终 blocking，`passed-with-warnings` 只承载 advisory；每次失败批次把完整 page-owned error 与 advisory 交给集中修复，页内只运行机械/安全预检，所有受影响页完成后才统一复检。删除 `FINAL_SVG_REPAIR_HARD_MAX_ROUNDS` 及 `maxStageAttempts` 对该循环的等价终止，保留 `repairRound` 单调审计；无变化、超过旧四轮、Provider 取消等路径都不会把 error 降级或继续导出。每次 vendored 原始报告按内容哈希留存，新增薄适配器只验证 report schema、final stage、SVG roster fingerprint、error/blocking count，不复制 SVG 标签、属性或 CSS 规则。

生产导出已移除 `--allow-quality-warnings`，Worker 在 Step 7 前重新验证当前报告，vendored `svg_to_pptx.py` 仍独立执行 final/hash/zero-blocking 校验。自动化验证结果为 Worker `231/231`、Domain/API `51/51`、Ruff 通过；覆盖 P01 blocking、两页完整问题集单批集中修复、warning 非阻断、第五轮后继续修复并导出、持续 blocking 后取消不导出、报告缺失/非 final/错哈希拒绝及视觉 `off`/`standard` 预算独立。Contracts 校验仍被当前 Windows `node_modules` junction 的既有读取错误阻断；真实 Qwen A/B、structured 模板和 PowerPoint/WPS 发布回归继续保持开放，不记为已通过。
