# ISSUE-004：移除 Scene Graph 作者路径并引入自适应视觉返修

## 基本信息

| 字段 | 值 |
| --- | --- |
| 状态 | In Progress：Direct SVG-only、自适应视觉返修、无 Blueprint 工作流及视觉复核 opt-in v3 核心链路已实现并通过自动化验证（2026-08-27）；人工接受基线恢复链路与真实 Qwen 对照回归待完成 |
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
12. 默认生成链路依赖 final SVG、内容、图表和 package 等确定性门禁完成发布，不调用视觉审核模型；关闭视觉复核不得削弱任何确定性门禁。
13. 标准视觉复核只运行一轮审核和最多一次逐页原子修复；只有用户明确选择“终稿复核”或等价高要求模式时，才允许修复后再执行一轮视觉验证。
14. 视觉 Hard/Soft 规则采用 PPT-Master 语义：裁切、溢出、重叠、不可读、图片损坏和明确关键元素缺失属于 Hard；留白、节奏、轻微对齐、层级和风格一致性默认属于 Soft。Soft 不得通过关键词或类别自动升级为 blocking。
15. 视觉修复不得重写页面内容、品牌决策或布局结构；每次修复必须有页级备份、受限差异和前置哈希，修复引入新 Hard 时只回滚受影响页面。
16. `needs_human` 是用户决策点而非自动整稿失败：用户可选择继续修复，或恢复复核前基线、复跑确定性门禁并接受当前版本导出；延后的视觉问题必须在报告和网站中明确披露。
17. 历史 `visual-review-adaptive@v1/v2` 快照继续按冻结轮数和旧决策解释；新 v3 策略不得改写历史证据、恢复语义或已发布 Revision。

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
→ final SVG / content / chart gates
→ SVG→DrawingML/PPTX
→ package QA
→ published
```

用户明确启用标准视觉复核：

```text
final SVG / content / chart gates passed
→ save visual-review baseline SVG roster
→ render PNG/contact sheet
→ one multimodal visual review
→ atomic page-scoped fixes only
→ page gate + final SVG gate rerun
→ export | needs_human user decision
```

用户明确启用终稿复核时，允许在原子修复后重新渲染修改页并执行一次验证；第二轮只验证改动和新增 Hard，不重新启动整稿自由优化。

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

- 网站生成设置增加“启用视觉复核”开关，默认不勾选；同时提供可选的“标准视觉复核”和“终稿视觉复核”级别。
- 用户选择必须写入不可变 Snapshot，并投影为 `visualReviewRequired`、`visualReviewMaxRounds` 和策略版本；Worker 不得根据页数、模型能力或内容自动启用。
- 新任务默认冻结 `visual-review-opt-in@v3`、`required=false`、`maxRounds=0`。标准复核冻结一次审核/一次修复预算；终稿复核才冻结第二次验证预算。
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

#### D4. 决策、导出与人工处理

- 新 v3 请求不使用 `[blockingCount, affectedPageCount, advisoryCount]` 总分、`quality-regressed` 或 `stalled-two-rounds` 驱动多轮自由返修；旧 v2 请求保留原实现。
- 标准复核完成一次安全修复并复跑确定性门禁后即结束；advisory 或单次不稳定主观 finding 写入 `passed-with-warnings` 收据并允许导出。
- 超出修复权限的视觉 Hard 写入 `needs_human_items[].suggested_fix_summary`。网站提供“继续修复”和“接受当前版本并导出”两个明确选择。
- 用户接受当前版本时恢复视觉复核前基线或已验证最佳页，重新通过 final SVG/content/chart/package 门禁后导出，并在最终报告中披露延后的视觉 finding。
- 渲染失败、确定性 SVG gate 失败、内容事实错误、图表错误或 package QA 失败不可通过用户跳过。

#### D5. 网站、预览与证据

- 视觉复核前保存 `agent/visual-reviews/baseline-svg/`，并在网站中始终提供基线预览；修复版与基线版使用明确标签，禁止静默替换。
- 网站按页展示 `ok`、`fixed`、`rolled_back`、`warning`、`needs_human`，同时展示轮次、修复属性、回滚页和剩余 Hard/Soft 数量。
- `passed-with-warnings` 提供正常下载；`needs_human` 在用户未作决定前暂停，并保留可恢复检查点和基线/最佳版本证据。
- `validation/visual-review.json` 和视觉收据记录策略版本、用户选择、作者/审核模型、审核次数、Provider 用量、耗时、基线哈希、最终哈希和延后 finding。

#### D6. 主要实现位置

- `packages/domain/src/instant_ppt_domain/generation.py`：默认关闭视觉复核，冻结 opt-in v3 策略及模型配置。
- `services/worker/src/instant_ppt_worker/default_workflow_request.py`、`workflow_models.py`：解析用户选择、级别、轮次和历史兼容。
- `services/worker/src/instant_ppt_worker/visual_review_runtime.py`：固定规则、完整页面上下文、取消关键词升级、单轮/验证轮决策和新报告证据。
- `services/worker/src/instant_ppt_worker/agentic_workflow.py`：条件进入视觉阶段、保存基线、页级修复/回滚、确定性复检和用户决定后的导出。
- `services/worker/src/instant_ppt_worker/presentation_agent_tools.py`、`presentation_agent_runtime.py`：受限视觉差异合同和 Don't-touch 强制校验。
- `apps/web/src/app/workspace-app.tsx` 及对应 API/Snapshot 合同：用户开关、复核级别、基线预览、警告和人工决定入口。

## 不变量

- 不改变批准 Outline、稳定 slide ID、来源事实、图表值或图片授权；稳定 ID 只承担持久化身份，不构成页面合同。
- 不削弱 P01 gate、final SVG gate、内容 QA、图表 QA、package QA 和 exact export。
- 不允许任意 Shell、外部 SVG 资源、脚本、事件处理器或跨租户路径。
- 崩溃恢复不得重复已确认的 Provider 调用或重复计费。
- v1/v2 历史任务继续遵守“未通过视觉 blocking 门时不得发布完整成功成品”；v3 新任务的视觉复核为用户主动启用的辅助阶段，用户可显式延后其 finding，但任何确定性 SVG、内容、图表或 package blocking 均不得跳过。
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
- [x] 默认模式完成生成和导出时，视觉审核 Provider 调用次数严格为 0，final SVG/content/chart/package 门禁保持不变。
- [x] 用户启用标准视觉复核时，只运行一轮审核和最多一次逐页原子修复，不出现 `quality-regressed` 或自动多轮整稿重画。
- [x] 用户明确启用终稿视觉复核时，第二轮只验证修改页和新增 Hard；不得重新发起不受限的整稿优化。
- [x] Reviewer 输入包含 PNG/SVG、页面角色、`design_spec.md §IX` 页面要求、`spec_lock.md` 和固定 Don't-touch 规则。
- [x] 留白、节奏、层级和风格一致性等 Soft finding 不会因关键词或类别被升级为 blocking，也不参与最佳版本评分。
- [x] 视觉修复仅允许受限属性/局部操作；正文、品牌 token、字体家族、稳定 ID、页面结构、图表类型和其他页面变化均被拒绝。
- [x] 修复导致新 Hard 或确定性 gate 失败时，只回滚受影响页面，未修改页面和已验证改善页保持不变。
- [ ] `needs_human` 时用户可以继续修复，或接受复核前基线并在重新通过全部确定性门禁后导出；延后 finding 在网站和最终报告中明确披露。
- [x] 作者模型与视觉审核模型、调用次数、用量及分阶段耗时分别记录；未启用视觉复核时不存在视觉模型费用。
- [ ] 使用 Qwen 官方 API、`qwen3.7-plus`、指定 GPT-5.6 DOCX 和提示词“根据GPT5.6的官方公告做一份6页的PPT”完成默认模式真实网站回归，生成 6 个 SVG 和 6 页 PPTX，并记录总耗时。
- [ ] 对同一输入启用标准视觉复核完成对照回归，保存基线/复核逐页截图、修改/回滚证据、视觉耗时和最终 PPTX；复核结果不得因单次主观评分恶化阻止用户接受基线版本。

## 发布策略

1. 先部署能读取旧策略、但新快照写入 v2 Direct SVG/adaptive 策略的兼容版本。
2. 排空旧 `presentation-authoring@v1` 运行任务；已发布历史工件保持不可变。
3. 运行冻结 Golden、Agent 证据、视觉闭环、恢复和 exact export 回归。
4. 灰度只影响新快照；失败时停止接纳 v2，新旧已发布 Revision 均不改写。
5. Page Blueprint 移除使用新工作流版本灰度；旧 v2 运行排空后，新任务只进入无 Blueprint 的 Strategist → Spec → Executor 链路。
6. opt-in v3 只影响新 Snapshot；先上线可同时解释历史 adaptive v1/v2 和新 opt-in v3 的兼容 Worker，再切换网站默认值。
7. 灰度期间对比默认无视觉复核与用户启用标准复核的成功率、总耗时、Provider 成本、人工介入率和页面回滚率。
8. v3 回滚时停止创建新 opt-in v3 Snapshot，恢复网站开关策略；历史运行、证据和已发布 Revision 均保持不可变。

## 完成记录

2026-08-26 已完成代码与合同实现：移除活动 Scene Graph 作者路径及 Schema；新快照冻结 `presentation-authoring@v2-direct-svg`、`visual-review-adaptive@v2`、`maxRounds=5`；旧请求缺省仍解析为三轮。视觉 finding 具备跨轮稳定指纹，每轮持久化可解释质量指标与决策证据，保留最佳 SVG，停滞/恶化/硬上限均 fail closed 到 `needs_manual`。

验证结果：Worker `179/179`、Domain `33/33`、Ruff、Schema 物化一致性和 `git diff --check` 通过。Windows 默认 pytest 临时目录及工作区中文临时路径存在既有访问/子进程编码噪声，最终全量测试使用唯一 ASCII 临时目录完成；该目录将在验证后清理。发布前仍需执行冻结 Golden 和 PowerPoint/WPS 人工兼容回归，因此 Issue 实现已完成但发布验证项保持开放。

2026-08-27 已完成 C 段修订：活动运行时、Schema、恢复、canonical bundle 和质量门中不再生成或读取 Page Blueprint，也没有引入等价页面合同。新 `instant-ppt-default@v3.0.0` 链路由 Strategist 直接读取批准的 Intent、Outline、Sources、资源和冻结策略并生成完整 `design_spec.md`；网站在大纲批准页明确展示并记录 `strategist-design-and-lock` 授权，未授权时停在 `awaiting_design_confirmation`，且不存在 `spec_lock.md` 或 Executor SVG。授权后写入 hash-bound `design-confirmation` receipt，再锁定 Spec 并进入 Direct SVG Executor。发布追踪改为后置 `release-trace.json`，只记录已经创作并通过门禁的页面，不承担前置语义合同职责。

最终验证覆盖 Worker `192/192`、Domain/API `46/46`、G06 真实 PostgreSQL/Redis/MinIO 集成 `14/14`、G07 `5/5`、Contracts `27 schemas / 39 endpoints / 171 fixtures`、Web lint/typecheck/production build、Ruff、冻结 Golden `10/10 source + 10/10 render + 40/40 artifacts`。真实六页中文 Agent 回归生成 6 个 Direct SVG 与 6 页 PPTX，P02“模型家族概览”和 P04“设计判断力”保留，包含 1 个原生可编辑图表；PowerPoint 16 与 WPS 12 均完成 6/6 打开、导出和逐页视觉检查，统计为 34 个可编辑文本形状、1 个原生图表、58 个 shape nodes，未发现裁切或结构破坏。

2026-08-27 已批准视觉复核 opt-in v3 修订计划：基于真实 Qwen 回归中“初始版本整体可接受、仅一页存在较明显问题，而后续主观复核使效果退化并阻止导出”的观察，新任务将默认关闭视觉复核，仅在用户明确要求时启用。该修订采用 PPT-Master 的固定 Hard/Soft 规则、逐页原子修复、页级备份/回滚和 `needs_human` 用户决策语义，并将作者模型与视觉审核模型解耦。该段记录批准时点的计划，后续实施状态以下方完成记录为准。

2026-08-27 已完成 opt-in v3 核心实现：网站/API 默认 `off`，用户可显式选择 `standard` 或 `final`；新 Snapshot 冻结 `visual-review-opt-in@v3`、精确轮次预算及独立作者/审核模型。Worker 默认链路不创建 Reviewer；标准模式只执行一次审核和最多一次页级原子修复，终稿模式第二轮只重新渲染和验证改动页。Reviewer 同时读取 PNG、SVG、页面角色/标题、`design_spec.md §IX` 页面要求、`spec_lock.md` 及固定 Hard/Soft/Don't-touch 规则，Soft 不再由关键词或 `deck-consistency` 类别升级。

视觉修复现在强制 `expectedBeforeSha256`、稳定目标元素、页级备份和 DOM 差异审计，仅允许几何、字号、字距、对齐与局部 transform 属性变化；正文、品牌属性、字体家族、稳定 ID、元素结构、图表和图片变化均 fail closed。修复后先跑页级生产 SVG gate，再跑 final SVG gate；失败或终稿验证出现新 Hard 时只恢复受影响页。视觉报告记录基线/最终 roster hash、修复/回滚页、作者/审核模型、真实 Provider 调用次数、Token/成本与耗时，并在 `needs_manual` 结果中提供 `needsHumanItems[].suggestedFixSummary`。

自动化验证：Worker `209/209`、Domain/API `50/50`、Ruff、Contracts `27 schemas / 39 endpoints / 171 fixtures`、Web ESLint/TypeScript/Next production build 全部通过。尚未实现网站上的“接受复核前基线并导出”恢复动作，也尚未执行本节最后两项真实 Qwen 网站对照回归；因此 opt-in v3 仍不得宣称完整发布。
