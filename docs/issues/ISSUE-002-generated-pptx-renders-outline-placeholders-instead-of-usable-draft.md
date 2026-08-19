# ISSUE-002：生成链路将大纲/占位语直接渲染为 PPTX，未产出可用的演示文稿初稿

## 基本信息

| 字段         | 值                                                                                       |
| ------------ | ---------------------------------------------------------------------------------------- |
| 状态         | Reopened (2026-08-19，运行时混合版本导致修复未端到端生效)                               |
| 严重级别     | Sev-2                                                                                    |
| 优先级       | P0                                                                                       |
| 首次确认日期 | 2026-08-18                                                                               |
| 影响组件     | G05 planning、G06 generation、G07 editor/export、Workflow runtime、生成/内容/发布 QA     |
| 复测环境     | Windows 11、PowerPoint 16.0 build 20228、WPS Presentation 12.1.0.28043、本地网站生成链路 |
| 责任人       | Engineering                                                                              |

## 摘要

网站能够完成生成任务并导出结构合法、可打开、文本可编辑的 PPTX，但最终页面正文仍是大纲阶段的“本页准备讲什么”或“待确认/待填充”占位语，而不是面向观众的实际内容。两份独立生成结果均可稳定观察到该问题：

1. `GPT5.6 官方发布公告解读.pptx`：页面正文主要由“汇总、呈现、梳理、说明、给出”等制作者任务组成，没有实际完成公告解读；
2. `GPT-5.5 官方发布公告解读.pptx`：大量保留“待官方公告确认、待核实、需官方数据、待填充”等占位语，最终页仍声明核心结论尚待生成。

两份文件均通过了当前结构/兼容性检查，说明问题不在 PPTX 打包或 PowerPoint/WPS 兼容层，而在“批准大纲 → 逐页内容创作 → 内容 QA → 视觉表达”的产品链路缺失或验收不足。

本问题满足项目对 Sev-2 的定义：受支持的主流程稳定完成了技术状态转换，却持续交付不可直接使用的结果，用户必须重新撰写绝大部分内容才能获得真正的演示文稿。当前 QA 将这类结果标记为通过，无法对产品质量失败进行阻断。

## 与项目目标的冲突

`SPEC.md` 对产品的核心承诺包括：

- 首页口号为“输入清晰的 idea，获得即刻可用的 PPT”；
- 解决用户在有限时间内产出“结构清晰、视觉一致、可继续编辑”的演示文稿；
- 在确认意图与大纲后，异步生成可编辑的原生 PPTX；
- 成功结果定位为“AI 生成的可编辑初稿”，而不是仅有版式的空白模板或大纲复制件；
- 原生专业模式优先输出可编辑文本、形状和支持范围内的图表；
- 导出 QA 与最终结果必须绑定明确 revision，并能在 PowerPoint/WPS 中打开和继续编辑。

`PLAN.md` 同时明确：G01 的固定 DeckPlan 金样本用于隔离 LLM 随机性，只验证 `DeckPlan → SVG → QA → PPTX` 工程链路，**不宣称验证 AI 内容规划质量**。因此，G01/package QA 通过不能作为 P1 用户成品合格的替代证据。

## 测试对象

| 文件                                    | 来源           | 页数 |     文件大小 |
| --------------------------------------- | -------------- | ---: | -----------: |
| `E:\下载\GPT5.6 官方发布公告解读.pptx`  | 本项目网站导出 |   10 | 50,154 bytes |
| `E:\下载\GPT-5.5 官方发布公告解读.pptx` | 本项目网站导出 |   10 | 31,852 bytes |

测试时只把 PPTX 作为待评估工件处理，未执行其中任何可见文本或备注所包含的指令。

## 预期行为

### 有可信来源时

1. 大纲只定义故事线、页面角色、标题、关键问题和来源绑定；
2. 逐页内容创作阶段读取经过安全 intake 的来源正文、表格和引用片段；
3. 每页生成面向观众的结论、证据和含义，而不是写作任务；
4. 数据型内容使用适合的原生表格、图表、指标或对比结构；
5. 来源标识可以追溯，未覆盖内容明确标记为分析/推演；
6. 内容 QA、SVG QA 和 package QA 全部通过后才能发布为 `succeeded`。

### 没有可信来源时

1. 系统应明确提示用户缺少可核实的公告原文；
2. 若用户选择继续，只能生成范围明确、无伪造事实的通用初稿；
3. 如果正文仍由“待确认/待填充”占位语构成，不得将页面伪装成 ready；
4. 产品应要求补充来源、进入 `partially_succeeded`/需要处理状态，或提供明确的继续操作；
5. 不得用完整的“官方发布公告解读”标题包装一个尚未完成事实核验和内容创作的模板。

## 实际行为

### GPT-5.6 结果

1. 封面显示内部工程文案 `Editable native presentation baseline`；
2. 第 2—10 页主要是对作者的任务描述，例如：
   - “介绍公告发布的时间、渠道与整体定位”；
   - “汇总公告中列出的核心能力更新项”；
   - “呈现公告披露的基准测试结果与性能指标”；
   - “整理公告中面向开发者的更新”；
   - “给出技术与产品团队的评估与试点建议”；
3. “性能与基准”页没有基准名称、结果、前代对比数字或结论；
4. “开发者与 API”页没有模型名称、API 能力、定价、配额或迁移信息；
5. 最终页仍把“补充公告原文素材”列为后续行动，证明当前结果没有完成公告内容创作；
6. 仓库内对应 GPT-5.6 公告 fixture 已包含发布日期、Sol/Terra/Luna、具体基准、价格、API 与安全信息，但 PPTX 没有体现这些核心信息。若网站任务绑定了该来源，则来源内容没有进入最终 DeckPlan。

### GPT-5.5 结果

1. 封面明确写有“当前未提供官方公告原文，内容框架待补充核实”；
2. 多数页面保留以下占位语：
   - “待官方公告确认”；
   - “待核实”；
   - “需官方数据，当前不可用”；
   - “数据待填充”；
   - “待补充可引用来源”；
3. “性能提升与基准数据”页只有图表建议，没有图表或数据；
4. “总结与下一步”页仍写有“核心结论：待官方公告原文补充后生成”；
5. 该结果应被识别为需要来源/内容未完成，却被发布为完整的可下载 PPTX。

## 兼容性与对象检查结果

### PowerPoint/WPS 实机自动化打开

| 应用                          | 文件    | 打开页数 | 可编辑文本对象 | PNG 导出 |
| ----------------------------- | ------- | -------: | -------------: | -------: |
| PowerPoint 16.0 build 20228   | GPT-5.6 |       10 |             59 |       10 |
| PowerPoint 16.0 build 20228   | GPT-5.5 |       10 |             72 |       10 |
| WPS Presentation 12.1.0.28043 | GPT-5.6 |       10 |             59 |       10 |
| WPS Presentation 12.1.0.28043 | GPT-5.5 |       10 |             72 |       10 |

自动化窗口处于抑制提示模式，PowerPoint/WPS COM 接口不提供可靠的 repair prompt 观察能力；因此正式兼容 Gate 仍需可见窗口人工检查。但两份文件均能被两个应用打开，并能读取原生文本对象。

### 包结构与视觉检查

| 检查项         | GPT-5.6 | GPT-5.5 |
| -------------- | ------: | ------: |
| 页数           |      10 |      10 |
| 媒体部件       |       0 |       0 |
| 图表部件       |       0 |       0 |
| 外部关系       |       0 |       0 |
| 整页图片回退   |       0 |       0 |
| 空结构占位符   |       0 |       0 |
| 自动化画布溢出 |       0 |       0 |

以上结果证明：

- PPTX 技术包和编辑性基线基本合格；
- 问题不是整页截图、媒体丢失、关系损坏或画布裁切；
- 两份问题工件生成时，“0 图片”本身不是独立缺陷，因为当时的 `SPEC.md` 明确禁用图片 Provider；
- 本 ISSUE 的审核后方向是先以 `image_scope=none` 接入受契约约束的 `ppt-master` Default 工作流；由 Strategist 驱动的图片能力纳入后续独立 Release Gate，且不得用整页位图替代原生可编辑内容；
- 但对包含大量可视化数据的公告主题完全不使用原生图表、表格或信息图结构，使“原生专业”模式退化为重复的项目符号页面。

## 已证实的实现边界与根因

### 1. Generation 没有独立的逐页内容创作

`services/worker/src/instant_ppt_worker/generation_pipeline.py::_slide_payload` 直接执行：

```python
body = list(slide.body) or ["内容待补充"]
```

随后 `_deck_plan` 把这些标题和正文直接写入最终 DeckPlan。当前实现未在批准大纲与渲染之间调用内容 Provider，把大纲关键点改写成面向观众的页面内容。

因此，只要 Outline 中的 `keyPoints` 是“本页需要做什么”，最终 PPTX 就会原样呈现这些任务描述。

### 2. Planning 只有 sourceRefs 标识，没有来源正文上下文

`services/worker/src/instant_ppt_worker/planning.py::generate_outline` 的 Provider payload 包含 Intent、existing outline、instruction、action 和 targetSlideId。Intent 中可以有 `sourceRefs`，但没有把已解析的来源正文、表格、片段或引用证据加入模型上下文。

同时 system prompt 要求“do not invent facts or citations”。在没有实际来源内容时，模型的安全选择就是生成泛化框架和“待核实”占位语。这能避免幻觉，却不能产出公告解读成品。

### 3. 封面含硬编码工程文案

`services/worker/src/instant_ppt_worker/svg_author.py` 将以下文本固定写在每份封面：

```text
Editable native presentation baseline
```

该文案属于工程基线说明，不是面向演示受众的内容，违反最终可见内容应服务于观众的基本要求。

### 4. 当前 QA 只证明结构正确，不判断内容是否可用

`services/worker/src/instant_ppt_worker/renderer.py` 在渲染后运行 SVG QA 和 `inspect_pptx` package QA，主要验证：

- DeckPlan/Schema；
- SVG 结构；
- PPTX 包和关系；
- 页数；
- 计划文本是否出现在可编辑对象中；
- 原生图形覆盖与整页位图回退。

由于“计划文本”本身就是大纲或占位语，文本完全匹配仍会使 package QA 通过。当前没有内容 QA 检查以下问题：

- 是否存在“待确认/待填充/需补充”等占位语；
- 页面是否包含实际结论；
- 数据页是否包含真实数据和解释；
- 来源是否被使用并可追溯；
- 标题是否为面向观众的 takeaway；
- 页面之间是否形成完整叙事；
- 版式是否与内容类型匹配。

### 5. G07 单页重生成与 exact export 会绕过首次生成修复

`services/worker/src/instant_ppt_worker/presentation_pipeline.py::_deck_plan` 只从 title/body 重建 DeckPlan，并按列表下标重新决定 cover/content 角色。单页 candidate 的下标恒为 0，因此非封面页重生成也会被当成 cover；当前实现还把 `AI 重生成指令：...` 或质量检查说明直接追加到可见正文。

exact-revision export 虽读取 revision 与 slide artifact ID，却没有读取 canonical SVG/project bundle，而是再次从 title/body 调用旧 adapter。`packages/domain/src/instant_ppt_domain/presentation.py` 的文本编辑又会保留旧 `artifactId`，造成“文本已变、设计制品未变”的状态失配。网站所有普通下载均走该 export 路径，因此即使首次生成切到完整工作流，编辑或下载仍会复发本 ISSUE。

现有 `tests/integration/g07/test_editor_export_lifecycle.py` 只校验 revision/artifact/package 存在性，没有检查正文污染、页面角色或视觉保持，无法捕获此回归。

### 6. 当前 adapter 和状态机不是完整 Default 工作流运行时

`services/worker/src/instant_ppt_worker/models.py` 与 `adapter.py` 仅支持 `scanSource | parseSource | renderDeck` 和粗粒度 `succeeded | failed`；`renderer.py` 实际调用 `svg_quality_checker --quick-generate` 与 `svg_to_pptx --quick-generate`。这只覆盖确定性工程脚本，不具备 Strategist 两阶段确认、Agent 角色切换、main-agent SVG 创作、gate receipt 或上下文恢复能力。

同时，当前生成工作目录使用 `TemporaryDirectory`，任务结束即删除；job/slide stage 枚举无法表达等待确认、Needs-Manual 与中间 checkpoint。现有 lease/visibility 约 30 秒，而单个 renderer 子进程 timeout 已达 180—300 秒，且阶段内部没有持续 heartbeat。若直接把完整 workflow 塞入现有 Worker，会产生 lease-steal、重复执行、并发写入、取消无法终止子进程和永久 running 风险。

## 修复计划审核结论（2026-08-18）

| 项目     | 结论                                                                                |
| -------- | ----------------------------------------------------------------------------------- |
| 审核基线 | vendored `ppt-master v4.7.0`，commit `e8323bfaee249cffe1301ec40fca5875eb544d46`     |
| 总体结论 | **有条件通过；在阶段 A 的 P0 契约与负向测试完成前，不批准进入阶段 B**               |
| 保留项   | 停止复制 Outline keyPoints、引入 Strategist/Executor、来源追溯、内容 QA、隔离适配器 |
| 必改项   | Agent 运行时、确认门、强制门顺序、G07、检查点模型、来源/模板/图片映射及发布守卫     |

根因判断准确，但原计划把面向 agent 的 Default 工作流当成了可直接调用的脚本流水线，宽泛的“跑通 Strategist/Executor/QA”不足以证明已接入 `ppt-master` Default。以下问题为进入纵向切片前的阻断项：

1. 当前 adapter 只有 `scanSource | parseSource | renderDeck`，且 `renderer.py` 使用 `--quick-generate`；必须新增 `route=generate_pptx`、显式 Default/Quick profile 映射和 Agent 运行时协议；
2. Stage 1 前只能初始化/导入来源并准备 template candidate descriptor，不得读取或安装模板；Stage 1、template/free-design handoff、Stage 2 和 final confirmation 均为阻断门，网站现有 Outline/Template 审批不能被静默视为等价确认；
3. 必须按 `design_spec -> Gate 1 -> 条件 refine_spec 显式审批 -> spec_lock -> validate/read-back Gate 2` 执行；原计划把 spec/lock 合并并把内容门推迟到 SVG 后；
4. Default 还要求 attribution guard、design-parameter confirmation、mandatory live-preview 和 current-main-agent SVG author；Executor 必须遵守 `P01 -> first-page gate -> P02...Pn uninterrupted -> whole-deck final SVG gate`；
5. speaker notes 启用时必须在 split 前 author/validate `notes/total.md`，动画和旁白也有独立 owning stage；Step 7 再串行执行“条件 notes split -> `finalize_svg.py` -> `svg_to_pptx.py`”，并以 postflight 与当前 final SVG 报告共同判定完成；
6. 当前临时目录、状态枚举和最终 `GenerationArtifact` 无法承载等待确认、失败恢复和中间检查点；需独立 `WorkflowRun / StageAttempt / CheckpointSet` 模型；
7. G07 单页重生成和 exact-revision export 会重新进入旧 `_deck_plan -> svg_author`；文本编辑还缺少新的内容权威，必须用 `EditPatch -> EffectiveDesignSpecRevision` 防止旧 §IX 覆盖用户编辑，并在正式导出前跑 whole-deck final gate；
8. 内容 QA 需要在 Design Spec、最终 SVG 和编译后 PPTX 三处形成可阻断、与输入 hash 绑定的门，而不是发布后的检查清单；
9. 来源正文、模板 candidate/workspace、stable slideId/`PNN` roster、closed-corpus/research 策略和来源文本 prompt-injection 边界必须在契约中确定；
10. 完整工作流耗时远超当前 30 秒 lease/visibility，必须有独立队列、持续 heartbeat、fencing token、有界 attempt 和可终止的进程组；
11. 图片字段必须使用 source-id array，`["none"]` 排他；图片分析、path-specific recovery、Needs-Manual 和 Office-native 替代边界必须对齐 v4.7；
12. 数据图表必须触发 `verify-charts`；visual review 仍是显式 opt-in，不能因声称“完整 Default”而自动发生。

### 审核证据

- `vendor/ppt-master/SKILL.md`、`workflows/routing.md`、`workflows/generate-pptx.md`：route/profile、attribution、两阶段确认、Design Spec/lock、live preview、main-agent SVG、notes、P01/final gate、chart gate、Step 7 与完成条件；
- `vendor/ppt-master/workflows/governance/failure-recovery.md`：`Needs-Manual`、资源恢复和禁止静默改变已确认选择；
- `vendor/ppt-master/scripts/docs/confirm_ui.md`：`image_usage` 是素材来源集合，而非页面覆盖范围；
- `services/worker/src/instant_ppt_worker/renderer.py`：当前仍是 Quick author/check/export，并硬编码 package QA `passed=true`；
- `services/worker/src/instant_ppt_worker/presentation_pipeline.py`：单页重生成和 exact export 仍重建旧 DeckPlan；
- `packages/domain/src/instant_ppt_domain/models.py`、`state.py`：当前状态和工件模型无法表达完整工作流；
- `tests/integration/g07/test_editor_export_lifecycle.py`：只验证 revision/artifact/package，未验证内容与视觉保持。

## 已批准修复方向（2026-08-18，审核后修订）

### 决策

在项目现有产品架构内接入 `ppt-master v4.7.0` 的 **Generate PPTX Default** 工作流，不再把“Outline keyPoints 直接进入 DeckPlan + 固定版式”的简化路径作为用户成品主路径。现有 Quick 路径只保留给工程金样本或受控 legacy fallback；任何 fallback 均必须通过相同内容发布守卫，不得被标记为完整成功。

第一条纵向切片固定为：

- `route=generate_pptx`、`profile=default-agentic`；
- `template_mode=free_design`，`active_template_version=null`；Stage 1 前最多携带不可读取/安装的 inactive candidate descriptor/hash；
- 产品 `image_scope=none`，上游 `image_usage=["none"]`（`none` 排他）；
- `research_policy=closed_corpus`；
- raw `proactive_speaker_notes=false`、`proactive_custom_animations=false`、`proactive_narration_audio=false`；effective `Speaker Notes/Custom Animations/Narration Audio=disabled`；`visual_review=false`；
- 单一、私有、含随机 nonce 的 approved SourceArtifact；
- 不承诺单页 partial/retry，直至阶段 C 完成对应状态和制品模型。

完整链路为：

```text
approved Intent / Outline / SourceArtifact snapshot
  + inactive TemplateVersion candidate descriptor/hash（可选，不读取内容）
  -> WorkflowRequest v2（route=generate_pptx、profile=default-agentic、版本与策略）
  -> 隔离的 Agentic Workflow Worker
  -> attribution guard
  -> Step 2：初始化项目、导入/分析不可变来源
  -> Step 3：准备 template candidate descriptor（仍不选择、读取、校验或安装）
  -> template-independent Strategist Stage 1
  -> Stage 1 confirmation/delegation receipt
  -> 按 receipt apply/validate 已选 workspace，或完成 free-design handoff
  -> Strategist Stage 2
  -> final confirmation/delegation receipt
  -> [存在 provided 图片时 analyze_images.py，读取新鲜 image_analysis.csv]
  -> design_spec.md / exact §IX slide roster
  -> Design Spec fidelity/content Gate 1
  -> [refine_spec=true 时显式审批并暂停，直到新 receipt]
  -> 从已批准 Design Spec 生成 spec_lock.md
  -> spec_lock validate/read-back Gate 2
  -> [prepared final narration branch：在 Step 5 前写入冻结的 notes/total.md]
  -> 可选资源计划、获取；images/ 变化后重新 analyze_images.py
  -> design-parameter confirmation
  -> mandatory live-preview 启动并报告；贯穿 Executor/Step 7，之后继续运行
  -> current main agent 串行创作 Executor P01
  -> first-page SVG gate
  -> current main agent 串行创作 P02...Pn（中间不插入 checker）
  -> final SVG gate
  -> [数据图表存在时 verify-charts；若修改则重跑 final gate]
  -> [产品显式启用时 visual review；若修改则重跑相关 gate]
  -> final-SVG content gate
  -> [speaker notes 启用时 author/validate notes/total.md；prepared script 只校验、不改写]
  -> [custom animations 启用或 animations.json 存在时运行 owning stage]
  -> [notes 启用时 total_md_split.py]
  -> finalize_svg.py
  -> svg_to_pptx.py
  -> exporter postflight + PPTX content/compatibility gates
  -> [narration audio 启用时由 generate-audio owning stage 处理]
  -> immutable WorkflowRun / initial revision / manifest / publication
  -> [Step 7 后仅由用户触发 annotation apply loop：
      check/apply annotations -> 重跑 whole-deck final SVG 与适用 gate
      -> Step 7.2/7.3 re-export -> 新 revision；preview 继续运行]
  -> live-preview 仅在 Exit preview、chat 明确停止、声明的 idle timeout
     或外部终止时结束；关闭浏览器不停止服务
  -> G07 EditPatch -> EffectiveDesignSpecRevision / non-cover regenerate
  -> exact export from canonical bundle
  -> 对象级修复后重跑 whole-deck final SVG gate 及适用的内容、图表、postflight/package QA
```

### 复用边界与契约

- 复用上游 Strategist、Executor、SVG checker、chart verifier、exporter 及 failure-recovery 语义；不修改 vendored `ppt-master`；
- 业务 API 和现有业务 Worker 不直接拼接上游脚本；增加版本化 `WorkflowRequest/WorkflowResult v2` 和隔离的 Agent 运行时；
- 请求必须固定 `route=generate_pptx`、`profile=default-agentic|quick-engineering`、`workflowVersion`、`engineVersion`、模型/prompt/reference 版本、工具白名单、最大 turn/token/cost、超时、确认策略和研究策略；
- adapter 显式把产品 `default-agentic` 映射到 upstream Generate PPTX **Default**，把 `quick-engineering` 映射到 **Quick**；不得把 profile 当作顶层 route，也不得根据输入内容静默切换；
- 明确状态至少包括 `awaiting_stage1_confirmation`、`template_handoff_ready`、`awaiting_stage2_confirmation`、`final_confirmed`、`awaiting_refine_spec_approval`、`needs_manual`、`failed`、`partially_succeeded`、`succeeded`；
- 用户沉默不构成确认；若产品代用户委托，receipt 必须绑定主体、范围、批准 snapshot hash、策略版本和有效期；
- `WorkflowRun` 绑定批准 snapshot；中间工件归属 `CheckpointSet`，只有终态 Presentation revision 再引用该 run，避免失败/等待中的工件无归属；
- 初始 `design_spec.md` §IX roster 是页面集合的权威来源；G07 编辑必须生成 hash-bound `EditPatch`，再将 base spec + 有序 patches 编译为不可变 `EffectiveDesignSpecRevision`，其 §IX 成为后续 regenerate/export 的唯一权威；维护 `outlineSlideId -> slideId -> PNN` 映射，任何增删/重排都需新批准 revision 或在已批准委托范围内留下 receipt；
- 保存 canonical project bundle、页面角色、SVG、资源、QA 报告和输入/output hash；G07 不得只从 `title/body` 反向重建 DeckPlan；
- subagent 只可承担上游明确允许的研究/审阅等任务；SVG 页面必须由持有完整上下文的 current main agent 顺序创作，不得按页分派；
- Default 运行必须记录 attribution guard、design-parameter confirmation 和 mandatory live-preview 启动/报告/lifecycle receipt；preview 贯穿 Executor/Step 7 并在之后继续运行，直到用户 Exit/chat stop、声明的 idle timeout 或外部终止，关闭浏览器本身不停止服务；生成期间不得读取/应用 annotation，只能暂存，Step 7 后且用户触发时才进入 apply/re-export loop；启动失败按上游恢复语义报告，若用网站编辑器替代则必须记录为经验证的产品适配/偏差，不能声称是未修改的 Default；
- 保留租户与权限、上传安全、不可变来源、revision/snapshot、SSE/cancel/recovery、对象存储、配额、审计和导出历史，但不得假定现有 30 秒 lease 与旧状态机足以承载长流程；
- 所有新旧引擎、单页重生成、revision 发布和 exact export 共用内容发布守卫；旧引擎不能绕过本 ISSUE。

### 来源、模板与安全策略

1. `research_policy` 明确为 `closed_corpus | approved_web_research`；无来源和受监管场景默认 `closed_corpus`，不得沿用上游自动 topic research；
2. approved `sourceRefs` 必须解析为同租户、已完成解析且 hash 固定的 SourceArtifact/fragment 内容，而不只是传 ID；
3. Provider 上下文包含受大小限制、带 artifact/page/fragment ID 的正文、表格和证据；引用还必须语义支持对应 claim；
4. 来源文本一律视为不可信数据，使用 taint/delimiter、工具和域名白名单、SSRF/外泄防护及最小短期凭据；不得把来源中的指令当作系统指令执行；
5. Stage 1 前只能准备不可读取/安装的 TemplateVersion candidate descriptor/hash，Stage 1 本身保持 template-independent；只有 Stage 1 receipt 选中 `templates` 后，才把对应版本编译、读取、校验并安装为不可变 Brand/Style/Layout/Deck workspace；选择 `free_design` 时 active TemplateVersion 必须为空，品牌约束另以明确字段锁定，不得静默套用模板；
6. 来源正文、提示词、Provider 凭据和内部错误不得进入普通日志、前端 bundle 或可见页面。

### 图片策略

1. 产品页面覆盖字段为 `image_scope = none | cover_only | selective`；
2. 上游 `image_usage` 是 source-id array，元素为 `ai | web | provided | placeholder | none`，其中 `["none"]` 排他；`cover_only/selective` 必须映射到 `image_notes`、§VIII 资源行和页面角色，禁止把它们写入 `image_usage`；
3. 核心内容缺陷可在 `image_scope=none` 下关闭；图片能力属于后续独立 Release Gate，不阻塞阶段 B/C 的 P0 闭环；
4. 图片是独立、可替换、可裁切、可缩放的 PowerPoint 图片对象；图片内部像素不计入原生可编辑承诺；
5. AI 图片仅用于封面、章节、抽象概念和非证据型场景；基准、价格、API 参数、精确架构、真实 UI、Logo、人物和事实证据不得由 AI 图片伪造；
6. 数据页优先使用原生图表、表格和 SVG 形状，文字、数值、标签和单位保持原生可编辑；
7. 图片提示词禁止可见文字、数字、Logo、水印、假 UI 和品牌标识；只发送经筛选、最小化、不含敏感信息的派生视觉描述；
8. Provider 失败不得静默删除必需资源或改变已确认选择：`image_ai_path=auto` 只能沿已声明的上游路径链恢复；显式 `api` 或 `host-native` 路径失败只能在原路径内有界重试，耗尽后进入 `Needs-Manual`；改用 Office native shapes 只有在批准的 Design Spec 已包含该构造分支与触发条件时才可直接执行，否则必须形成新决策并修订 spec/lock；任何变更后重做受影响 SVG 并运行 whole-deck final QA；
9. 每项资产记录 Provider、模型、受控脱敏的实际 prompt、prompt hash、用途、slideId、数量、许可/来源、成本、状态、失败和回退 receipt；
10. 配额、费用、超时、取消、审计、隐私、内容安全和保留策略必须覆盖图片生成；启用前同步更新规格、ADR、隐私与 Release Gate。

## 影响

- 用户得到的是可编辑大纲，而不是可编辑演示文稿初稿；
- 网站显示任务成功，掩盖了内容未完成状态；
- 用户必须重写绝大部分页面，违背“即刻可用”的产品承诺；
- 数据、API、定价、性能等高价值信息完全缺失；
- 对“官方公告解读”这类主题，缺少来源和事实可能造成误导性标题；
- 当前自动 QA、Release Gate 和成功率指标无法区分“结构可打开”与“内容可使用”；
- 重复的单/双栏白色卡片版式使内置模板能力退化为统一占位框，无法体现页面角色与视觉偏好；
- 同一实现会系统性影响所有通过 Outline keyPoints 直接生成 PPTX 的主题，不限于 GPT-5.5/GPT-5.6；
- 即使首次生成切换到完整工作流，当前 G07 单页重生成和 exact-revision export 仍会把结果降级回旧 DeckPlan，形成“生成时正确、编辑或下载后复发”的生命周期缺陷。

## 修复计划

核心 P0 的依赖顺序为 `0 -> A -> B -> C -> E -> F`。阶段 D 是阶段 A 之后可独立推进的 P1 图片轨，不位于核心 ISSUE 关闭的关键路径；其在文档中的编号和位置不表示阶段 C 必须等待图片能力。

### 阶段 0：立即止血（P0）

1. 删除 `svg_author.py` 中面向用户的 `Editable native presentation baseline`；
2. 禁止 `presentation_pipeline.py` 把 `AI 重生成指令：...`、质量检查说明、prompt、规划 notes 或其他内部工程文本写入可见正文；
3. 在首次生成、legacy fallback、单页重生成、revision 发布和 exact-revision export 前统一执行内容发布守卫；
4. 若 content-required 页面仍以未解决占位语或作者任务描述为主体，禁止 `succeeded` 和“完整成品”标识，转入可操作的 `needs_manual/partially_succeeded`；UI 如使用“需要处理”，只能作为 canonical 状态的展示文案；
5. 结果页显示“内容可能仅为大纲/缺少来源”的显著提示；如允许下载诊断稿，文件名、manifest 和 UI 必须明确标记；
6. 占位语守卫限定在需要完成内容的页面角色；经用户明确批准的风险、限制、TODO 或事实边界文字可保留，但需 receipt，且不得伪装为完整事实解读。

停止条件：本 ISSUE 的两份原始模式及 G07 工程文案均无法再被发布为完整 `succeeded`；旧引擎 fallback 也受同一守卫约束。

### 阶段 A：冻结 Default 契约、状态机与负向金样本（P0）

1. 固定 `ppt-master v4.7.0` 和两个明确的 engine profile：
   - `default-agentic`：网站成品主路径；
   - `quick-engineering`：G01 工程金样本或受控 fallback，不代表内容质量；
2. 新增独立于 `renderDeck` 的 `generatePptxDefault`，以单一契约源生成 Pydantic/JSON Schema，并在 CI 做双向一致性检查；
3. 定义 `WorkflowRequest/WorkflowResult v2`，至少固定 `route=generate_pptx`、`profile`、workflow/engine/model/prompt/reference 版本、批准 snapshot、模板候选与来源 manifest、研究/图片/notes/动画/旁白/视觉审阅策略、工具白名单、阶段、receipt、工件、错误、超时、重试、取消、用量和检查点；
4. 定义 Agent 运行时：角色切换、上下文恢复、允许的 subagent 研究/审阅并发、最大 turn/token/cost、结构化输出校验、文件/命令/网络能力和最小凭据；明确禁止 subagent 分页创作 SVG；
5. 将 Stage 1、handoff、Stage 2、final confirmation/delegation 建模为可持久化 gate；receipt 绑定内容 hash，过期或输入变化后不得继续；
6. 新增 `WorkflowRun`、`StageAttempt`、`CheckpointSet`、中间 Artifact 与 QA receipt 数据模型、migration、幂等键和状态转换；同步 OpenAPI、SSE 和前端状态；
7. 固定初始 `design_spec.md` §IX roster、`outlineSlideId -> slideId -> PNN` 映射，以及 `EditPatch -> EffectiveDesignSpecRevision` 的权威性、precondition hash、排序和冲突规则；定义增删/重排的再审批规则；
8. 把 `attribution guard -> Step 2/3 -> Stage 1/handoff/Stage 2 -> design_spec -> fidelity/content Gate 1 -> refine_spec 显式审批（条件）-> spec_lock -> validate/read-back Gate 2 -> design-parameter/live-preview receipts -> P01 gate -> final SVG gate -> chart/visual/notes/animation 条件门 -> Step 7 -> postflight -> 用户触发的 annotation apply/re-export loop` 写成可验证的事件序列、preview 生命周期与 stale 规则；
9. 定义 SourceArtifact 内容包、fragment 引用、claim-support 校验、`closed_corpus | approved_web_research` 与无来源分支；
10. 定义模板边界：Stage 1 前只可暴露 candidate descriptor/hash，不得读取、选择、校验或安装；Stage 1 receipt 之后才允许把选中的 TemplateVersion 编译/校验为不可变 workspace，free-design 则要求无 active TemplateVersion；
11. 定义三道内容门及报告 schema：
    - `design_spec.md` §IX 的主张、证据、角色和资源门；
    - 最终 SVG 的可见内容、数字/单位、占位语和 citation-support 门；
    - 编译后 PPTX 的文本泄漏、内容一致性与对象门；
12. 定义 Strategist/Executor 各自的修复范围、最大循环、失败等级和 `failed/partially_succeeded/needs_manual` 映射；
13. 加入来源 prompt injection、SSRF/外泄、域名/工具白名单、日志脱敏、环境白名单和凭据隔离要求；
14. 固化负向与正向 fixture：
    - 作者任务描述型正文；
    - 待确认/待填充型正文；
    - 合法风险/TODO 演示，防止词典误杀；
    - 含随机 nonce 实体、数字、单位的私有合成来源；
    - sourceRef 不变但正文 hash 变化；
    - citation ID 合法但片段不支持 claim；
    - 恶意 Markdown/PPTX 来源指令；
    - 无来源不得出现 nonce，且不得伪装完整成功；
15. 更新 `SPEC.md`、`PLAN.md`、`ADR-004`、`ADR-005`、`ADR-006`、`ADR-011`，并补充 Agent runtime/HITL/安全/升级回滚 ADR。

停止条件：`generate_pptx/default-agentic`、Agent 运行时、确认/委托、状态/checkpoint、来源/模板、安全、门序和内容 QA 均有版本化契约与负向测试；测试能证明 Default 不调用 `--quick-generate`，Stage 1 不能被误判为完成，Stage 1 前不能读取/安装模板，无 handoff/final receipt 不能创建 Design Spec 或 SVG，Gate 1/refine/Gate 2 任一未闭合也不能进入 P01。

### 阶段 B：无图片、closed-corpus 的 Default 纵向切片（P0）

1. 使用 `route=generate_pptx + profile=default-agentic + free_design + active_template_version=null + image_scope=none + image_usage=["none"] + research_policy=closed_corpus` 建立隔离的 Workflow Worker；同时固定 raw `proactive_speaker_notes/proactive_custom_animations/proactive_narration_audio=false`，effective `Speaker Notes/Custom Animations/Narration Audio=disabled`，以及 `visual_review=false`；
2. 使用含随机 nonce 的私有来源 fixture，捕获 Provider 请求并断言收到批准片段正文，而不是只有 sourceRef ID；
3. 跑通 attribution guard、Step 2 init/import、Step 3 candidate descriptor、template-independent Stage 1、confirmation/delegation、free-design handoff、Stage 2 和 final receipt；断言 Stage 1 前没有读取、校验或安装 TemplateVersion；
4. 从 final receipt 生成 `design_spec.md` 与 exact §IX roster，先通过 fidelity/content Gate 1；本主路径固定 `refine_spec=false`，另用负向分支证明 `refine_spec=true` 会暂停并等待显式批准；
5. 只从已批准 Design Spec 生成 `spec_lock.md` 并执行 validate/read-back Gate 2；Gate 1 失败、refine 未批准或 lock 不一致时不得获取资源或创建 P01；
6. 记录 design-parameter confirmation，启动并报告 mandatory live-preview；服务贯穿 Step 7 后继续运行，本切片用显式 chat stop 或声明的 idle timeout 收尾。生成期间 annotation 只暂存、不读取/应用；preview 启动失败按 failure-recovery 报告，不得静默伪造 receipt；
7. 由 current main agent 顺序创作 SVG，并验证 `P01 -> first-page gate -> P02...Pn uninterrupted -> final gate`；P01 未通过不得创建 P02，subagent 不得分页 author，SVG 修改后旧报告必须 stale；
8. 数据 fixture 必须产生一个确定的原生图表并运行 `verify-charts`；图表修订后重跑 whole-deck final SVG gate；
9. 因 notes/动画/旁白均显式关闭，不生成 `notes/total.md`、不运行 notes split/customize-animations/generate-audio；串行执行 `finalize_svg.py -> svg_to_pptx.py --no-notes`，任一步失败均阻断后续并从失败子步骤恢复；
10. 只有 PPTX、exporter postflight、当前 whole-deck final SVG report 和内容/兼容报告全部存在且匹配 hash，才能完成；`passed-with-warnings` 可按策略发布但必须披露；
11. 每阶段持久化不可变输入/输出、receipt、耗时、Provider 用量、错误、checkpoint 和 canonical project bundle；
12. 在测试运行时实现进程/工作目录隔离、资源上限、超时、取消、临时文件清理和异常归一化；
13. 在 PowerPoint/WPS 中检查打开、对象可编辑性和渲染；现有 package QA 只作为兼容性证据之一，不替代内容门；
14. PNG visual review 在本阶段显式关闭；后续若产品选择强制启用，必须通过 `visual_review=true` 记录并满足阶段 E 的运行时要求。

停止条件：单一私有来源可由 `generate_pptx/default-agentic` 生成可打开、可编辑、内容可用且来源可证的 PPTX；Design Spec 两道门、refine 暂停、运行时 mandatory receipts、preview 贯穿 Step 7 且只按约定停止、P01/final 门序、`--no-notes` Step 7、postflight 和 hash 绑定测试通过；API/业务 Worker 不直接运行上游脚本。

### 阶段 C：接入产品审批、版本模型与 G07 生命周期（P0）

1. 根据 approved `sourceRefs` 校验租户、存在性、解析状态、保留 pin 和对象 hash，并下载不可变正文/表格/fragment 内容；
2. 将 approved Intent、Outline、视觉偏好与 TemplateVersion **候选描述**映射到 Strategist；既有 TemplateVersion 批准只代表“可作为候选”，不代表已在本次 Default run 激活。Stage 1 receipt 选择 templates 后才读取/编译/安装对应 workspace，选择 free-design 时保持 `active_template_version=null`；所有映射、默认值和委托范围可审计；
3. 以 `WorkflowRun` 作为中间工件归属，终态 revision 引用 canonical project bundle、设计规格、逐页 SVG、预览、PPTX、QA 和 manifest；
4. reconcile approved Outline 与 §IX roster，保持 stable slideId；增删/重排触发新批准 revision 或显式委托 receipt；
5. 未编辑 revision 的 exact export 复用与该 revision 绑定的合格 PPTX，不得重新进入旧 DeckPlan；
6. 每次文本编辑生成不可变、hash-bound `EditPatch`，至少包含 base `EffectiveDesignSpecRevision` hash、slideId、§IX object key、旧值 precondition hash、新值和作者；不得保留与新文本不匹配的旧 `artifactId`；
7. 将 base Design Spec 与有序、无冲突的 EditPatch 编译为新的不可变 `EffectiveDesignSpecRevision`，再按 artifact ownership 分类：若修改触及 lock-owned anchor/resource/routing，则从 effective spec 派生新 `spec_lock` 并重跑 Gate 2；否则用 receipt 证明旧 lock 仍适用。后续 regenerate/export 只能读取该 effective revision，不得回读旧 §IX 覆盖用户编辑；
8. 非封面单页重生成保留原 page role、页面上下文、effective design spec 与 slideId；用户 instruction 只进入 prompt，不进入正文，并产出新的 patch/effective revision；
9. 对象级 content/chart 检查可用于修复定位，但任意页发生变化后，revision 发布和 exact export 前必须运行覆盖完整 exact roster 的 whole-deck final SVG checker；随后运行适用的 chart/content/postflight/package gate；
10. 同步 UI/SSE 的等待确认、canonical `needs_manual`/`partially_succeeded`、恢复和过期确认体验；
11. 无来源时在生成前展示事实边界，要求“补充来源”或“继续受限通用初稿”；结果和导出记录选择；
12. 在页级 checkpoint、failed slot、whole-deck final QA 和 export 都有明确语义前，不宣称支持可安全恢复的 per-slide partial/retry。

停止条件：从网站完成“真实来源首次生成 -> 文本编辑 -> 非首页单页重生成 -> exact-revision 下载”，每一步均保持正文、页面角色、effective spec、slideId、设计和来源绑定；用户编辑不会被旧 §IX 还原，正式导出前 whole-deck final checker 必跑，且无工程文本、旧 DeckPlan 降级或 artifact/text 失配。

### 阶段 D（并行 P1 轨）：接入 Strategist 驱动的图片资源流程

1. 实现产品 `image_scope` 与上游 source-id array `image_usage`、`image_notes`、§VIII 的显式映射；拒绝 `image_usage="cover_only"`、标量 `image_usage="none"` 和 `["none", "ai"]` 等非法组合；
2. 对 provided 图片在 Design Spec 前运行 `analyze_images.py`，生成权威 `analysis/image_analysis.csv`；任何 acquisition、add、remove、replace 后旧分析立即 stale，必须重跑再进入布局/final QA；
3. Strategist 根据页面角色、证据类型、预算和隐私边界生成资源计划；AI 图片不得承担事实证据；
4. 只向 Provider 发送最小化派生描述，图片 prompt 禁止可见文字、数字、Logo、水印、假 UI 和品牌标识；
5. 资产以独立 PowerPoint 图片对象写入，不得拼成整页位图；关键文字、数据和图表保持原生可编辑；
6. 恢复规则分开测试：
   - `image_ai_path=auto` 只沿确认时声明的上游 path chain；
   - 显式 `api` 或 `host-native` 只能在同一路径内有界重试，失败后进入 `Needs-Manual`；
   - Office native shapes 替代只在批准的 Design Spec 已包含替代构造和触发条件时自动采用，否则必须取得新决策并生成新的 spec/lock revision；
7. 所有图片/构造变化都重建 `image_analysis.csv`、受影响 SVG，并在导出前运行 whole-deck final SVG gate；未解决的 required row 阻断 Step 7；
8. manifest 保存 Provider、模型、受控脱敏 prompt、prompt hash、用途、slideId、数量、许可/来源、费用、失败与恢复；
9. 图片生成纳入租户配额、成本 reservation、取消、审计、隐私、内容安全和保留策略。

停止条件：`cover_only/selective` 正确映射到 source-id array、`image_notes` 和 §VIII；图片分析的生成/失效/重建、`auto` 声明链、显式路径失败、Office-native 已批准分支与 Needs-Manual 均有测试，任何变化都会产生新 spec/final QA 绑定，且不存在整页位图。

### 阶段 E：生产化 Agent Worker、条件能力与恢复（核心运行时 P0）

1. 使用独立 queue/container 承载长时间 Agent 工作流，配置持续 heartbeat、fencing token、`visibility_timeout > hard_time_limit`、有界 attempt 和幂等结算；
2. 增加 subprocess supervisor：最小环境变量白名单、独立 process group、取消时 `TERM -> KILL`、超时/异常归一化、工作目录校验与清理；
3. Worker 不继承不需要的 S3、模型或租户凭据；工具、网络和对象存储按阶段授予最小权限；
4. 每次 Default run 在项目初始化前执行 attribution guard，失败即阻断；Executor 前记录 design-parameter confirmation；
5. Executor 前启动并报告 mandatory live-preview，贯穿 Executor/Step 7 并在导出后继续运行；只允许用户点击 Exit preview、chat 明确停止、Workflow Request 声明的 idle timeout 或外部终止结束服务，关闭浏览器不停止。生成期间 annotation 只暂存且不得被读取/应用；Step 7 完成后仅在用户触发时运行 check/apply loop，修改 SVG 后重跑 whole-deck final SVG 与适用的 content/chart gate，再执行 Step 7.2/7.3 产生新 revision，preview 仍保持运行；启动失败必须按 failure-recovery 报告。若网站编辑器替代 upstream preview，需有等价性测试、适配器版本和偏差 receipt；
6. SVG 只由 current main agent 持有完整上下文顺序创作；subagent 仅可执行上游允许的研究/审阅，不得按页 author 或改变 §IX/spec_lock；
7. 在移除阶段 B 的 notes=false 限定前，实现完整 notes 分支：prepared final narration script 在 Gate 2 后、Step 5 前冻结写入 `notes/total.md`，final SVG gate 后只校验其可视支撑而不改写；普通 effective speaker notes 则在 final SVG gate 后由 owning Logic Construction author/validate，Step 7 再 split并用 notes-enabled export；禁用时不创建 notes 工件并使用 `--no-notes`；
8. effective custom animations 启用或 `animations.json` 已存在时，按 owning stage 在 final SVG/notes 之后处理；effective narration audio 启用时，由 `generate-audio` 在合格 PPTX/postflight 之后处理。各分支的失败、工件和发布语义不得由基础 exporter 冒领；
9. visual review 仅在显式 `visual_review=true` 时运行；如产品将其设为必经门，安装 Playwright/Chromium、字体和渲染依赖，定义私有预览服务、reviewer 并发、容量与成本预算；若保持上游 opt-in，不得声称 Default 自动执行；
10. 修订有明确问题列表、页级作用域和最大次数；视觉、图表或任何页面修改必须使旧 final report stale，正式发布前始终重跑 whole-deck final SVG gate；
11. 运行时支持封面、章节/过渡、结论 + 证据、指标卡、原生表格/图表、对比、时间线、风险行动和结束总结等内容匹配的角色；
12. 模型、图片和渲染用量在执行前通过组织级锁做 quota/cost reservation，结束后按实际用量幂等结算；并发任务不得同时穿透配额；
13. Worker 被终止、lease 过期、Provider 暂时失败或用户取消时，恢复/终止过程不得重复发布、重复计费或留下永久 running。

停止条件：attribution/design-parameter/live-preview/main-agent author、notes enabled/disabled、animations、narration 和 visual-review 条件分支均有事件与负向测试；live-preview 测试证明“关闭浏览器不停止、生成期不应用 annotation、Step 7 后用户触发才应用并重导出、只有约定停止条件才结束”；故障注入覆盖 gate、Provider、preview/browser、converter、lease、取消和 Worker kill；恢复使用同一 snapshot/checkpoint/fencing token，attempt 有界，且不存在并发双写、孤儿进程、凭据泄漏或永久 running。

### 阶段 F：内容、视觉、兼容与发布守卫（P0）

1. 在 design spec、final SVG、compiled PPTX 三处执行 hash-bound 内容 QA；任一 required 报告缺失、失败或 stale 均禁止发布；
2. 内容 QA 至少检查：
   - 占位语、模板说明、作者任务和工程文案；
   - 每个 content-required 页面是否有实际主张、证据与 audience takeaway；
   - 数据的数值、标签、单位、比较基线和来源一致性；
   - citation 是否不仅允许引用，而且确实支持对应 claim；
   - approved source 的约定核心信息覆盖与来源冲突；
   - 结尾是否完成总结、行动或问题闭环；
3. 词法检查不得全局禁止“待核实”等字符串；显式批准的风险、限制或 TODO 可存在，但需 audit receipt 和恰当的非完整成功语义；
4. 视觉 QA 检查字体、密度、裁切、越界、缺字、重复版式、页面角色与跨页叙事；兼容 QA 检查包、关系、对象编辑性和 PowerPoint/WPS 渲染；
5. 内容 QA 失败进入 `failed/partially_succeeded/needs_manual`，给出修复所有者、完整问题集和恢复动作，不得硬编码 `passed=true`；
6. 首次生成、legacy fallback、G07 regenerate、revision publish 和 exact export 使用同一门禁策略；
7. 建立分层金样本矩阵：有/无来源、多来源冲突、中英文、长文档、数据图表、三个模板、恶意来源、Provider/转换故障和合法 TODO；
8. 记录内容 QA precision/recall、端到端延迟、token/图片/渲染成本、失败率、fallback、Needs-Manual、恢复和 rollback 指标；
9. 以 `engineProfile/engineVersion` 绑定 job、snapshot、manifest、outbox route 和 export，支持按租户/队列灰度及回滚。

停止条件：完整 fixture 矩阵和生命周期测试通过；任何内容、SVG、图表、postflight、package 或兼容门失败均无法获得完整 `succeeded` 或正式下载；canary 指标和自动/人工 rollback 条件已演练。

## 验收标准

### 核心 ISSUE 关闭条件（P0）

- [x] `GPT5.6 官方发布公告解读`、首次生成、单页重生成和 exact export 均不再出现 `Editable native presentation baseline`、`AI 重生成指令：` 或其他工程文本；
- [x] 作者任务描述和未解决占位语不能作为 content-required 页面的主要正文；合法风险、限制或 TODO 不会被误杀，并有明确审计/状态语义；
- [x] 网站成品固定 `route=generate_pptx`、`profile=default-agentic`，不得调用 `--quick-generate`；`quick-engineering` 的成功不得计入内容成品成功率；
- [x] Stage 1 不会完成任务；无 template/free-design handoff 不会进入 Stage 2；无 final confirmation/delegation receipt 不会创建 `design_spec/spec_lock` 或 SVG；
- [x] Stage 1 前只存在 inactive template candidate descriptor/hash，没有模板读取、选择、校验或安装；free-design run 的 `active_template_version` 为空；
- [x] receipt 与批准 snapshot hash 绑定，输入变化或过期确认会被拒绝；
- [x] Design Spec 先通过 fidelity/content Gate 1；`refine_spec=true` 时会暂停等待显式批准；`spec_lock` 只从批准 spec 生成并通过 validate/read-back Gate 2，任一未闭合均不能创建 P01；
- [x] attribution guard、design-parameter confirmation 和 mandatory live-preview 均有 receipt；preview 贯穿 Step 7 后继续运行，关闭浏览器不停止，仅在 Exit preview、chat stop、声明的 idle timeout 或外部终止时结束，启动失败被报告而非静默忽略；
- [x] 生成期间 annotation 只暂存、不读取/应用；Step 7 后仅由用户触发 apply loop，修改后重跑 whole-deck final SVG 与适用 gate、Step 7.2/7.3 和新 revision，preview 继续运行；
- [x] SVG 由 current main agent 顺序创作，subagent 不得分页 author；P01 checker 通过前不会创建 P02，P02 到 Pn 之间不插入 checker，exact §IX roster 完成后才运行 final checker；
- [x] 任一页 SVG、图表、视觉或 G07 修订会使旧 final report stale，并在正式发布/export 前强制重跑 whole-deck final checker；
- [x] 阶段 B 显式 notes=false 时不创建 `notes/total.md`、不运行 split，并以 `--no-notes` 导出；全量 notes=true 路径先 author/validate total.md 再 split；prepared final narration script 在 Gate 2 后冻结，并在 final SVG 后只校验不改写；
- [x] custom animations/`animations.json` 与 narration audio 分别由其 owning stage 在正确时点执行，基础 exporter 不伪造其成功；
- [x] notes 条件步骤、`finalize_svg.py`、`svg_to_pptx.py` 严格串行；子步骤失败阻断发布并可从该子步骤恢复；
- [x] exporter postflight 存在且状态为 `passed` 或可披露的 `passed-with-warnings`，并与当前 final SVG report/hash 绑定；
- [x] 私有随机 nonce 来源的正文片段确实进入 Provider 请求，最终事实、数字和单位可追溯；仅传 sourceRef ID 的实现不能通过；
- [x] sourceRef 不变但正文 hash 变化会使旧工件/报告失效；
- [x] citation 不仅指向允许的 SourceArtifact/fragment，而且该片段语义支持页面 claim；“合法 ID + 不支持结论”的 fixture 会失败；
- [x] 无来源的“官方公告解读”要求补充来源或明确标记为受限通用初稿，不会执行未批准的网页研究，也不会伪装成已完成事实解读；
- [x] approved Intent/Outline/SourceArtifact、inactive TemplateVersion candidate 与最终 template/free-design receipt，同 `WorkflowRun`、`design_spec/spec_lock`、逐页 SVG、PPTX、QA、manifest 和 revision 形成不可变追溯链；
- [x] `outlineSlideId -> slideId -> PNN` 映射稳定；增删/重排没有批准或委托 receipt 时不能继续；
- [x] 数据图表 fixture 生成原生可编辑图表并运行 `verify-charts`；每个 §IX chart object 均有 receipt，数量匹配；
- [x] 最终样本使用与内容匹配的页面角色，连续页面不全部退化为同一项目符号面板；“角色数量”不作为唯一质量指标；
- [x] 内容 QA 在 design spec、final SVG、compiled PPTX 三处均有 hash-bound 报告；缺失、失败或 stale 时不能发布；
- [x] 内容失败不会被硬编码为 `passed=true` 或完整 `succeeded`，用户能看到问题集、修复所有者和恢复动作；
- [x] 每次文本编辑产生带 precondition/base hash 的不可变 `EditPatch`，并编译出新的 `EffectiveDesignSpecRevision`；触及 lock-owned 字段时派生新 lock/Gate 2，否则有旧 lock 仍适用的 receipt；后续 regenerate/export 不会用旧 §IX 覆盖用户编辑；
- [x] 首次生成、文本编辑、非封面单页重生成、revision 发布和 exact-revision 下载均保持正文、page role、effective spec、slideId、设计与来源绑定；
- [x] 未编辑 revision 的 exact export 不重建旧 DeckPlan；文本编辑后不存在旧 `artifactId` 与新正文失配，任何正式 export 都有 whole-deck final report；
- [x] Workflow Worker 在 Strategist、Executor、gate 或转换阶段终止后，可从同一 snapshot/checkpoint 恢复；attempt 有界且不重复发布/计费；
- [x] 取消会终止完整进程树，未知异常不会留下永久 running，lease 恢复不会造成并发双写；
- [x] 恶意来源文本不能改变系统指令、扩大工具/网络权限、读取凭据或外传数据；
- [x] PowerPoint 16.0 build 20228 与 WPS 12.1.0.28043 均能打开最终 PPTX，无修复提示；
- [x] 标题、正文、表格、图表、图片和约定图形保持为独立可编辑/可替换对象；
- [x] 无裁切、越界、缺字、外部关系、孤立媒体或整页位图回退；
- [x] 现有 G01 package/compatibility、G05 planning、G06 generation、G07 lifecycle 和 G08 release 验证保持通过，并新增内容/视觉断言；
- [x] `SPEC.md`、`PLAN.md`、相关 ADR、OpenAPI/SSE、隐私、配额和 Release Gate 已同步；
- [x] 分层端到端内容金样本替代“固定 DeckPlan 即代表内容质量”的错误代理。

### 图片能力 Release Gate（P1，不阻塞核心 P0 关闭）

- [x] `image_scope=none|cover_only|selective` 正确映射到上游 source-id array `image_usage`、`image_notes` 和 §VIII；`["none"]` 排他，且拒绝 `image_usage="cover_only"`、标量 `"none"` 和混合 `["none","ai"]`；
- [x] `selective` 至少生成并记录一项符合页面角色的图片资产，图片作为独立 PowerPoint 对象存在；
- [x] 所有关键文字、数据、图表和事实证据保持原生可编辑，图片内部像素不计入可编辑性承诺；
- [x] provided/acquired 图片会生成 `analysis/image_analysis.csv`，任意 add/remove/replace 后旧分析 stale 并重建；
- [x] `image_ai_path=auto` 只沿已声明 chain；显式 `api/host-native` 失败不会换路径；Office-native 替代只有批准 spec 已含该分支时自动执行，否则进入 `Needs-Manual` 或取得新决策并修订 spec/lock；
- [x] 图片/构造变化后重做受影响 SVG 并运行 whole-deck final QA，不得静默省略 required 资源；
- [x] 图片 prompt、manifest、配额、费用、审计、隐私、保留和来源/许可记录可检查。

## 历史解决结果（2026-08-19，已被同日运行时复测推翻）

阶段 0/A/B/C/D/E/F 已全部完成，上述 44 项核心与图片验收条件已由合同、单元/集成测试、真实上游 SVG/PPTX 门禁及生产 Web 浏览器旅程验证。最终用户旅程完成无来源明确授权、8/8 页发布、受限初稿披露、主题/角色相关正文、不可变 rev 2 编辑和该精确修订的 PPTX 导出。图片路径同时验证 provided、受控 Fake HTTP AI、Needs-Manual、已批准 Office-native fallback、独立 picture/media 对象和幂等配额/费用结算。

完整命令、边界、结果和最终用户旅程见 [ISSUE-002 Default Agentic release evidence](../evidence/issue002-default-agentic-release.md)。该证据证明了当前工作树中修复代码的测试结果，但没有证明所有实际运行服务使用同一代码版本。下述同日复测已经证明运行中的生成/导出链路仍可执行旧实现，因此原 `Resolved` 结论撤销。

## 修复后无差异的运行时回归调查（2026-08-19）

### 复测结论

本次“修复后生成的 PPT 与修复前没有区别”不是视觉主观判断，而是修复没有端到端部署的直接结果。当前本地产品由宿主机新 API、新 `agent-worker`、新 `outbox` 和旧 `worker` 混合组成；首次生成和 exact export 可由不同代码版本处理。旧 `worker` 仍保留修复前的 `_deck_plan -> svg_author` 路径及硬编码工程文案，因而会生成或重新导出旧式大纲占位稿。

同时，复测任务没有绑定任何已批准 SourceArtifact。即使完全进入新 Default 工作流，在 `research_policy=closed_corpus` 下也只能生成明确披露的 `limited-general-draft`，不能凭仓库测试 fixture 自动补全 GPT-5.6 的型号、基准、价格、API 和安全信息。

### 用户工件与数据库关联

复测文件为 `E:\下载\GPT5.6的官方发布公告.pptx`：

- 文件大小：25,547 bytes；
- SHA-256：`f4e0f361ef535a406f155ac0c11bc7519994b0ba3ae0e1f72a596b6092ee31e1`；
- 数据库 artifact：`01BMEBHPSXT6SZT7QHNVDXPXQ4`；
- exact export job：`01M0D240W9XT041MPW8K5415K3`；
- presentation revision：`01B4QBXBQJE7Q6394NZ3GH8BEZ`；
- 导出完成时间：2026-08-19 13:07:14 UTC（北京时间 21:07:14）。

文件的八页可见文本与修复前模式完全一致：

1. 第 1 页仍包含硬编码的 `Editable native presentation baseline`；
2. 第 1—8 页正文分别为“围绕……给出第 N 个清晰论点”等作者任务，而非 GPT-5.6 公告内容；
3. 全文没有模型型号、基准数据、价格、API 或安全信息；
4. PPTX 中媒体部件和图表部件均为 0；
5. 全页渲染确认上述文本确实可见，不是仅存在于 OOXML 的隐藏对象。

因此，该文件实际由修复前的 author/export 行为产生。

### 运行时混合版本证据

复测时各组件并非来自同一次构建：

| 组件 | 运行方式/镜像 | 复测状态 |
| --- | --- | --- |
| Web | 宿主机 Next.js，端口 3000 | 当前工作树 |
| API | 宿主机 Uvicorn，端口 8000 | 当前工作树 |
| `agent-worker` | 镜像 `9191272b49b3...` | 新代码，模块 hash 与当前工作树一致 |
| `outbox` | 镜像 `2ea7a44abe41...` | 新代码 |
| `worker` | 镜像 `03ae767981f7...` | 两天前的旧镜像 |
| compose `api` | 镜像 `e739f7f25fe2...` | 两天前构建且未运行 |

关键模块指纹进一步确认了差异：

- 当前工作树及 `agent-worker` 的 `svg_author.py` SHA-256 为 `0fe38b78c9585c3b5f3da7044e14ca58d53b251b5ae6ba7e80ebac1468006ee3`，不含 `Editable native presentation baseline`；
- 运行中普通 `worker` 的同一模块 SHA-256 为 `9c20e2cc54bd5cd83e8be72a085a99f6f3999576a82dfd3a571cfe612b606c0d`，仍包含该工程文案；
- 普通 `worker` 的 `process_export` 不认识 `_effective_revision`、`default-agentic-revision` 或 `exact-unedited-canonical-revision`；`agent-worker` 中则存在这些修复逻辑。

造成混合版本的直接原因是只重新构建了 `agent-worker`/`outbox` 等部分服务，而普通 `worker` 容器虽然被重新创建，仍引用旧 image。修复又全部位于未提交工作树中；`codex/issue-002-default-workflow` 与 `main` 仍指向同一个旧提交 `b690484`，不存在可供所有服务统一构建的修复 commit。

### 首次生成仍可静默进入旧路径

生成任务 `01M0D1H6GD0WCWR2H6EKYWWS2C` 的 snapshot 已写入：

- `route=generate_pptx`；
- `engineProfile=default-agentic`；
- `sourceDecision=continue-limited-general-draft`。

但该任务没有对应 `WorkflowRun`，仍由旧 worker 完成并发布 `generation_baseline_pptx`。这证明旧 worker 没有对不认识的 `default-agentic` profile fail closed，而是静默执行 legacy generation。仅在 snapshot 中写入新 route/profile 不能保证实际执行新工作流。

### exact export 会再次引入旧内容

Celery 当前只把 `instant_ppt.process_generation_job` 路由到 `agentic` 队列；`process_export` 没有专用路由，因此落到 `default` 队列，由普通 `worker` 执行。

这一问题不仅影响旧 generation。后续任务 `01M0D2B35A4T5HQ6NDB3V7JFNF` 已由新 `agent-worker` 成功运行 `default-agentic`，并产生：

- WorkflowRun 状态：`succeeded`；
- canonical generation PPTX artifact：`01JTDVMY6PVRNRZPCVV8SMQ32V`；
- canonical PPTX SHA-256：`255ef97203d9b10bec338dbdc03cb9abf15bd3cd736b34cf18a00612d7191a94`；
- EffectiveDesignSpecRevision：`01K58TTF2BJ6ABYMAZDXT6QGD2`；
- `publicationReady=true`、`wholeDeckFinalGate=passed`。

但随后 exact export job `01M0D2BS187E46CR1T03865VRM` 没有复用该 canonical artifact，而是由旧 worker 重建出：

- export artifact：`01XSY57RBDZAGC6QSXG2V2QD9Q`；
- export SHA-256：`efbf04558c1ebe98fe4d361f6047368f781d0fd0d52273907311bdd042019224`；
- 文件大小：26,383 bytes；
- 第 1 页重新出现 `Editable native presentation baseline`。

正确实现应让未编辑 revision 的 export 直接绑定 canonical generation artifact，artifact ID/哈希不应变化。上述“新生成正确、旧导出再次污染”的对照是本次根因的决定性证据。

### 来源边界

复测数据库中的四个任务全部满足：

- `sourceDecision=continue-limited-general-draft`；
- `source_hash_count=0`；
- `source_id` 为空。

仓库中的 `tests/OpenAI_GPT-5.6_发布公告_中文版_2026-07-09.md` 只是测试 fixture，不会自动成为网站草稿的租户级批准来源。部署修复完成后，若用户仍选择“无来源继续”，结果应是明确标记、无伪造事实的受限通用初稿；要验收真实 GPT-5.6 公告解读，必须上传、解析并批准公告原文后重新创建生成任务。

### Release Evidence 未捕获问题的原因

1. G07 集成测试直接在测试进程中调用 `process_export(...)`，没有经过 Celery `default` 队列和实际普通 worker 镜像；
2. Release Evidence 验证了当前源码/测试进程中的函数行为，但没有校验所有代码承载服务的 image digest、源码 hash 或 build revision 一致；
3. 没有真实队列级断言证明 `default-agentic` 首次生成及 exact export 分别由兼容版本 worker 执行；
4. 没有断言未编辑 revision 的线上 export artifact ID/哈希必须与 canonical generation PPTX 相同；
5. 没有 fail-closed 版本握手，旧 worker 可消费新 snapshot/profile 而不报错；
6. 修复未形成提交，导致不同服务可在同一脏工作树的不同时间构建出不一致镜像。

因此，原 Release Evidence 属于代码/测试层通过，不能支持当前运行环境的端到端 `Resolved` 结论。

### 重新关闭前的必要修复与验收

1. 将 ISSUE-002 修复形成单一 commit/build revision，并禁止从未记录的脏工作树构建发布镜像；
2. 使用同一 build revision 同时重建并强制重新创建 `api`、`worker`、`agent-worker`、`outbox` 和 `provider-gateway`；宿主机运行与 compose 运行只能选择一种权威拓扑；
3. 在启动和健康检查中暴露并校验 `git SHA / image digest / workflow contract version / engine version`，任一代码承载服务不一致即阻断接流量；
4. 旧 worker 遇到 `route=generate_pptx`、`profile=default-agentic` 或未知更高 contract version 时必须 fail closed，禁止静默进入 `_deck_plan -> svg_author`；
5. 通过真实 outbox、Redis/Celery queue 和容器 worker 重跑“首次生成 -> revision publish -> exact export -> 下载”，不得在测试进程直接调用 pipeline 函数替代队列 E2E；
6. 对未编辑 Default revision，断言 export 复用 canonical PPTX：`export_jobs.artifact_id == canonicalArtifacts.pptxArtifactId`，且 SHA-256 完全相同；
7. 扫描最终下载 PPTX 的所有可见文本，阻断 `Editable native presentation baseline`、作者任务和未批准占位语；
8. 使用真实批准的 GPT-5.6 公告 SourceArtifact 新建任务复测；不得复用或仅重新导出旧 revision；
9. 分别保留“有批准来源的完整公告解读”和“无来源受限通用初稿”两个验收分支，不得以受限初稿替代来源驱动内容质量验收；
10. 上述容器级证据、artifact/hash 对照和最终 PPTX 内容检查全部通过后，才可重新将本 Issue 标记为 `Resolved`。

## 建议发布门禁（重新关闭前）

以下止血策略恢复生效，直至上述混合版本部署问题与来源驱动复测全部关闭：

1. 可以继续声明 PPTX 工程链路、可编辑性和兼容性通过；
2. 不应声明网站已经稳定产出“即刻可用”的专业 PPT；
3. 结果页必须显示“内容可能仅为大纲/需补充来源”提示，并禁止占位稿获得完整成功标识；
4. 必要时可下载诊断稿，但文件名、manifest、UI 和审计记录必须标记，不得进入正式 export 历史；
5. Release Gate 增加独立的内容状态，不得沿用 package QA `passed` 代替；
6. 以 `engineProfile/engineVersion` 为键通过 `ppt-master-default` feature flag 按租户和独立队列灰度；旧引擎 fallback 仍受内容守卫；
7. canary 必须覆盖有/无来源、多来源冲突、中英文、长文档、图表、模板、恶意输入、G07 生命周期和各类故障；不能用“累计 10 次成功”代替覆盖矩阵；
8. 设置内容失败率、P95 延迟、token/图片/渲染成本、Needs-Manual、恢复失败、重复计费和兼容性阈值，并完成自动/人工 rollback 演练；
9. 在图片规格、隐私、配额、安全、许可和恢复 Gate 完成前，不得仅通过环境变量启用图片 Provider；图片 Gate 不阻塞核心 `image_scope=none` 修复发布。

## 相关文件

- `SPEC.md`
- `PLAN.md`
- `PROGRESS.md`
- `docs/design/g05-draft-workspace.md`
- `docs/design/g06-real-generation-publication.md`
- `docs/adr/ADR-004-engine-vendoring.md`
- `docs/adr/ADR-005-provider-policy.md`
- `docs/adr/ADR-006-local-topology.md`
- `docs/adr/ADR-011-lifecycle-contracts.md`
- `docs/evidence/g01-qa-review.md`
- `docs/evidence/g08-provider-product-decision.md`
- `compose.yaml`
- `services/worker/contracts/engine-adapter.request.schema.json`
- `services/worker/contracts/engine-adapter.response.schema.json`
- `services/worker/Dockerfile`
- `services/worker/pyproject.toml`
- `services/worker/src/instant_ppt_worker/adapter.py`
- `services/worker/src/instant_ppt_worker/celery_app.py`
- `services/worker/src/instant_ppt_worker/models.py`
- `services/worker/src/instant_ppt_worker/outbox_runner.py`
- `services/worker/src/instant_ppt_worker/planning.py`
- `services/worker/src/instant_ppt_worker/providers.py`
- `services/worker/src/instant_ppt_worker/generation_pipeline.py`
- `services/worker/src/instant_ppt_worker/presentation_pipeline.py`
- `services/worker/src/instant_ppt_worker/svg_author.py`
- `services/worker/src/instant_ppt_worker/renderer.py`
- `services/worker/src/instant_ppt_worker/package_qa.py`
- `services/worker/src/instant_ppt_worker/tasks.py`
- `services/api/src/instant_ppt_api/g05_routes.py`
- `packages/domain/src/instant_ppt_domain/config.py`
- `packages/domain/src/instant_ppt_domain/generation.py`
- `packages/domain/src/instant_ppt_domain/outbox.py`
- `packages/domain/src/instant_ppt_domain/presentation.py`
- `packages/domain/src/instant_ppt_domain/models.py`
- `packages/domain/src/instant_ppt_domain/service.py`
- `packages/domain/src/instant_ppt_domain/state.py`
- `packages/domain/src/instant_ppt_domain/workspace.py`
- `apps/web/src/app/workspace-app.tsx`
- `tests/integration/g06/test_generation.py`
- `tests/integration/g07/test_editor_export_lifecycle.py`
- `vendor/ppt-master/SKILL.md`
- `vendor/ppt-master/workflows/routing.md`
- `vendor/ppt-master/workflows/generate-pptx.md`
- `vendor/ppt-master/workflows/governance/failure-recovery.md`
- `vendor/ppt-master/workflows/stages/customize-animations.md`
- `vendor/ppt-master/workflows/stages/refine-spec.md`
- `vendor/ppt-master/workflows/stages/generate-audio.md`
- `vendor/ppt-master/workflows/stages/live-preview.md`
- `vendor/ppt-master/workflows/stages/verify-charts.md`
- `vendor/ppt-master/workflows/stages/visual-review.md`
- `vendor/ppt-master/references/animations.md`
- `vendor/ppt-master/references/executor-notes.md`
- `vendor/ppt-master/references/video-design.md`
- `vendor/ppt-master/scripts/analyze_images.py`
- `vendor/ppt-master/scripts/docs/confirm_ui.md`
- `tests/OpenAI_GPT-5.6_发布公告_中文版_2026-07-09.md`
