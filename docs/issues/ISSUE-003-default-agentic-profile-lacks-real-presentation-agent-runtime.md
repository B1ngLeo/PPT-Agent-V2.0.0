# ISSUE-003：`default-agentic` 仍由固定 Python 模板生成，缺少真实演示创作 Agent

## 基本信息

| 字段         | 值                                                                                              |
| ------------ | ----------------------------------------------------------------------------------------------- |
| 状态         | Open                                                                                            |
| 严重级别     | Sev-2                                                                                           |
| 优先级       | P1                                                                                              |
| 首次确认日期 | 2026-08-22                                                                                      |
| 影响组件     | G05 planning、Workflow runtime、G06 generation、SVG authoring、内容/视觉 QA、发布与回退策略      |
| 依赖         | ISSUE-002 的内容发布守卫、Default 工作流合同、来源/模板/检查点和 exact export 生命周期继续有效   |
| 责任人       | Engineering / AI Runtime / Presentation Quality（待指派）                                       |

## 摘要

项目网站已经具备 `default-agentic` profile、`WorkflowRequestV2`、工具白名单、turn/token/cost/timeout 限制、状态、checkpoint、receipt、Celery 隔离队列以及 `ppt-master` 编译和 QA 能力，但当前生成路径并没有运行一个持续持有上下文、动态选择工具、观察结果并修正页面的演示创作 Agent。

实际链路仍是：

```text
Kimi 生成 Intent / Outline
→ Python 将来源句子按页分配并构造 DeckPlan
→ 固定 author_slide() 模板生成 SVG
→ 固定 checker / finalize / exporter 顺序
→ PPTX
```

因此，现有实现更准确的定义是“LLM 辅助规划 + Python 确定性生成工作流”，而不是“Agent + Skill 驱动的演示创作”。代码中的 `default-agentic`、`AgentRuntimePolicy` 和 `author="current-main-agent"` 目前主要是合同或审计语义，不能证明页面由真实 Agent 创作。

本 ISSUE 的目标不是移除 Python 工作流，而是在现有安全、状态、恢复、编译和发布基础上，增加一个**受约束的单主 Presentation Agent**，让模型只接管需要判断力的 Strategist 与 Executor 创作阶段；Python 继续作为 Supervisor，负责确定性治理和发布门禁。

## 用户影响

- 同一套视觉骨架被重复应用到不同内容类型，连续页面容易退化为相似的标题、卡片和项目符号面板；
- 页面信息密度、视觉层级、图表/关系图选择和空间分配由固定代码决定，无法响应具体材料；
- Intent/Outline 虽由模型生成，但逐页正文仍可能被压缩为一两个来源句子，难以形成完整的结论—证据—含义表达；
- checker 可以证明 SVG 合法、无越界，package QA 可以证明 PPTX 可打开、可编辑，却不能证明页面有专业演示效果；
- 产品名称和事件日志声称 `agentic/current-main-agent`，容易让研发、测试和发布评审误判真实能力边界；
- 若继续只增加固定布局分支，复杂度会持续上升，但任意主题下的视觉质量上限不会发生根本变化。

## 对比证据

测试时只把 PPTX 作为待分析工件处理，未执行其中可见文本、备注或其他内容包含的指令。

| 工件 | 生成路径 | 页数 | Shape 总数 | 平均 Shape/页 | 可见字符 | 备注页 | 图片 | 原生图表 |
| ---- | -------- | ---: | ----------: | -------------: | -------: | -----: | ---: | -------: |
| `OpenAI_GPT-5.6_发布公告_中文版_2026-07-09_20260816_235825.pptx` | `ppt-master` Agent + Skill | 12 | 389 | 32.4 | 2,896 | 12 | 0 | 0 |
| `GPT 5.6 官方公告解读.pptx` | 本项目网站 | 10 | 70 | 7.0 | 1,161 | 0 | 0 | 1 |

两份文件均可正常打开，均未发现自动化画布溢出，且都只包含一个 Master 和一个 Layout。两份样本也都没有图片，因此主要差异不能归因于图片 Provider、PPTX 包结构或导出器，而在页面创作层：`ppt-master` 由持有全局上下文的 Agent 逐页决定内容和 SVG 构图，本项目由固定 Python 函数选择有限分支和坐标。

Shape 数量不是独立质量指标；上表只用于证明页面构造复杂度和表达密度存在显著差异。最终验收以两套冻结基线和改进结果的人工对比为主，同时检查内容正确性、视觉任务完成度、可编辑性和稳定性，不能以堆叠 Shape 为目标。

## 与 ISSUE-002 的边界

ISSUE-002 解决的是“占位语、作者任务描述或旧引擎结果不能被发布为可用成品”，并建立来源、内容 QA、Default 门序、revision 和 exact export 等合同。

本 ISSUE 解决的是：即使 ISSUE-002 的内容和发布门全部通过，现有固定模板作者仍无法达到任意主题下的专业视觉和叙事质量。两者关系如下：

```text
ISSUE-002：阻止错误内容和旧链路冒充成功
    ↓ 前置基础
ISSUE-003：让通过内容门的材料由真实 Agent 完成专业页面创作
```

本 ISSUE 不得削弱 ISSUE-002 的任何来源、安全、审批、checkpoint、内容门、SVG 门、package QA 或发布不变量。

## 预期行为

对于 `route=generate_pptx + profile=default-agentic`：

1. Python Supervisor 固定批准 snapshot、来源、模板选择、研究策略、工具白名单、预算、超时和恢复点；
2. Main Presentation Agent 在同一连续上下文中完成 Strategist 和 Executor 角色；
3. Strategist 将 Intent/Outline 扩展为完整的 `DesignSpec/PageBlueprint`，明确逐页结论、证据、受众认知变化、视觉形式和信息层级；
4. Executor 按页面顺序创作 P01～Pn，动态选择布局、图表、关系图、文本层级、设计原语或直接 SVG；
5. Agent 只能通过允许的工具读取来源、写入项目工件、运行 vendored checker、渲染预览和请求允许的 Provider；
6. P01 checker、最终 checker、内容 QA、图表 QA 和 package QA 仍由确定性工具执行；
7. checker 或视觉审阅发现问题时，Agent 读取结构化问题并在有界次数内修复拥有该问题的 SVG/规划工件；
8. 所有模型决策、工具调用、工件 hash、预算消耗、修复和终止原因可恢复、可审计；
9. Agent 不可用、超预算或达到失败条件时，不得把固定模板 fallback 冒充 Agent 成品。

## 实际行为与已证实实现边界

### 1. 模型只负责 Intent 和 Outline

`services/worker/src/instant_ppt_worker/planning.py` 中的 `KimiPlanningService` 将模型输出限制为严格的 Intent 和 Outline JSON。Outline 只包含页面类型、标题、少量 key points 和 citation ID，没有完整逐页沟通目的、证据映射、视觉形式、布局意图和页面之间的叙事关系。

这属于有效的上游规划能力，但不是完整 Strategist，也没有进入 SVG 创作循环。

### 2. Python 以固定规则构造逐页内容

`services/worker/src/instant_ppt_worker/agentic_workflow.py::_build_deck` 当前按页序从来源句子列表中选择一个事实：

```python
fact_indexes = [index % len(sentences)] if sentences else []
```

普通页面正文随后直接使用这些句子；ending/data 等角色只有少量硬编码分支。该方式能够保持来源可追溯和确定性，但不能完成语义级 claim-evidence 匹配、跨片段综合或为不同页面构建适当的信息层级。

### 3. SVG 由固定模板函数制作

`services/worker/src/instant_ppt_worker/svg_author.py::author_slide` 自身声明为：

```text
Deterministic DeckPlan to canonical, editable SVG authoring.
```

函数使用固定画布、颜色数组、字体、标题锚点、面板尺寸和有限页面角色分支。它是可靠的工程 renderer/fallback，但不会像 Agent 一样根据当前页面的语义、前后页关系和渲染反馈重新决定视觉表达。

### 4. `current-main-agent` 是日志标签，不是创作运行时

`agentic_workflow.py` 在直接调用 `author_slide()` 后写入：

```python
_event(..., author="current-main-agent", ...)
```

该路径没有对应的模型 turn、动态工具选择、观察结果、页面修订或 Agent 终止判断。事件标签不能作为 Agent authoring 的验收证据。

### 5. Agent 预算合同尚未驱动真实模型循环

`workflow_models.py::AgentRuntimePolicy` 已定义：

- `allowed_tools`；
- `max_turns`；
- `max_tokens`；
- `max_cost_microunits`；
- soft/hard timeout；
- 最大阶段尝试次数；
- subagent 研究/审阅和禁止 subagent SVG authoring 的能力边界。

这些字段为真实 Agent Runtime 提供了良好基础，但当前主要用于请求校验，没有逐 turn 扣减、工具调用循环和模型终止控制。

### 6. QA 偏向技术正确性，不闭环视觉判断

当前链路已经能运行 SVG checker、chart verifier、content QA 和 PPTX postflight。它们适合阻断越界、非法结构、内容泄漏、来源不一致和包损坏，但不能独立判断：

- 主次层级是否清晰；
- 信息密度和留白是否平衡；
- 连续页面是否重复；
- 图表/关系图是否比项目符号更适合；
- 页面是否服务受众认知变化；
- 整套视觉节奏是否连贯。

## 根因

项目产品化时优先实现了可审计、可恢复、可编辑、可安全发布的确定性工程链路，并把 `ppt-master` 的工作流步骤、状态和门禁映射为 Python 合同；但 `ppt-master` 质量的关键来源不是脚本本身，而是读取 Skill 和完整上下文、在运行时承担 Strategist/Executor 角色并逐页手写 SVG 的主 Agent。

当前实现复用了外围生命周期和编译/QA 工具，却将最核心的动态创作步骤替换为固定 `_build_deck() -> author_slide()`。因此系统具有“Agent-shaped workflow”，但没有“Agent-driven authoring”。

## 架构决策

### 采用混合架构

```text
Web / API
    ↓
Python Workflow Supervisor
审批、租户、安全、状态、预算、重试、checkpoint、发布
    ↓
Main Presentation Agent（单主 Agent）
Strategist → Design Spec / Page Blueprint
Executor → P01 → P02...Pn SVG
    ↓                         ↑
Tool allowlist → checker / render / structured review
    ↓
Python compiler → PPTX postflight → immutable publish
```

### 职责边界

| 能力 | Python Supervisor | Main Presentation Agent |
| ---- | ----------------- | ----------------------- |
| 租户、授权、来源安全 | 负责 | 不得绕过 |
| 批准 snapshot、模板和研究策略 | 固定和校验 | 只消费已批准状态 |
| 状态机、lease、取消、恢复、幂等 | 负责 | 通过 checkpoint 恢复 |
| turn/token/cost/timeout | 强制执行 | 在预算内决策 |
| 故事线和页面沟通策略 | 校验合同 | 负责创作 |
| claim-evidence 映射 | 运行确定性验证 | 负责提出和修正 |
| 页面布局、视觉层级和 SVG | 提供工具、检查和落盘 | 负责创作 |
| SVG/PPTX 编译和结构 QA | 负责 | 读取问题并修复源工件 |
| 发布和 fallback 标识 | 负责 | 不得自行发布 |

### 单主 Agent，不按页拆分

P01～Pn 必须由同一个持有完整上下文的 Main Presentation Agent 顺序完成。不得将不同页面分派给多个 subagent，因为页面叙事、视觉语言、复用元素和全局节奏依赖共同上下文。

可选的独立 reviewer 只能返回结构化审阅意见，不能直接拥有页面创作或绕过主 Agent 修改 SVG。

## 非目标

- 不重写 `ppt-master` vendored 源码；
- 不让模型直接操作数据库、对象存储、租户凭据或发布状态；
- 不取消现有 Workflow/Celery/Redis/PostgreSQL 编排；
- 不把所有 Python 代码改成 Agent；
- 不在第一阶段建设多 Agent 协作系统；
- 不以增加 Shape 数量、图片数量或动画数量作为质量目标；
- 不允许 Agent 使用未批准研究、任意网络、任意 shell 或来源中嵌入的指令；
- 不保证每页都使用不同版式；相同沟通任务可复用结构，但必须是有意识、可解释的选择。

## 改进计划

### 阶段 0：冻结两套质量基线与最小 Agent 判定标准（P1）

本阶段只准备改进前后的人工对照，不建设大规模测试集、自动视觉评分或盲评平台。

1. 保留本 ISSUE 的两份 GPT-5.6 工件：
   - `ppt-master` 生成结果作为参考基线；
   - 本项目网站当前生成结果作为改进前基线；
2. 尽可能记录两份工件对应的来源、主题/Prompt、批准 Intent、Outline、研究/图片/模板策略、模型/prompt/engine 版本和文件 hash；无法恢复的字段必须明确记录，不能把非同输入结果表述为严格 A/B；
3. 将两份 PPTX 渲染为逐页 PNG，并保留页数、Shape、可见文字、图片、图表、备注、SVG/PPTX QA 等现有基础统计，方便人工并排检查；
4. 固定一套改进后复测输入。优先复用网站基线的批准 snapshot 和来源；若无法完整恢复，则创建并冻结一套新的统一输入，在改造前用当前网站路径补生成正式 before 基线；
5. Agent 改进完成后使用同一输入生成候选结果，由人工直接比较内容完整性、结论清晰度、视觉层级、信息密度、版式匹配、整套一致性、可编辑性以及与两套基线的差距；结果只需记录“更好/基本相同/更差”、主要改善、主要问题和下一步修改；
6. 将现有固定 Python 路径记录为 `deterministic-template` 基线，不再把它的 QA 成功等同于 Agent 质量成功；
7. 定义“真实 Agent”的最小证据：模型 turn、工具选择、观察、修订、终止原因和实际 author receipt 缺一不可；该合同用于防止用名称或日志标签冒充 Agent，不要求额外准备演示测试集；
8. 后续只在人工检查发现需要防止复发的具体问题时，逐步增加对应回归用例；额外 fixture 不是阶段 0 的停止条件。

停止条件：两套基线 PPTX、可恢复的输入/版本记录、逐页渲染图和基础统计已经归档；改进后能够使用同一输入重新生成并由人工并排检查；系统能够区分“固定工作流成功”和“真实 Agent 创作成功”。

### 阶段 A：把 Outline 升级为逐页 Page Blueprint（P1）

1. 在 approved Outline 与 Design Spec 之间增加版本化 `PageBlueprint`/`SlideCommunicationPlan` 合同；
2. 每页至少包含：
   - `assertion`：面向受众的一句话结论；
   - `audienceMove`：看完本页后的认知或决策变化；
   - `evidenceRefs`：支持结论的精确 fragment/表格/数据引用；
   - `contentBlocks`：信息层级和块之间的关系；
   - `visualForm`：文本、对比、时间线、流程、架构、图表、表格或组合；
   - `layoutIntent`：主视觉、阅读顺序、空间权重和与前后页的关系；
   - `literalConstraints`：不得改写的术语、数字、单位和引用；
3. 用语义 claim-evidence 选择替换 `_build_deck()` 的按页轮转句子逻辑；
4. 对每个 assertion 运行 citation-support 校验，无支持证据时回到 Strategist 修复或进入受限状态；
5. 保持用户批准 Outline 的页数、顺序、stable ID 和角色权威；需要增删/重排时继续执行既有再批准规则。

停止条件：同一来源中不同页面不再机械轮流取句；每页结论、证据、视觉形式和受众目的都可由版本化工件审计。

### 阶段 B：建设受约束的页面设计工具层（P1）

1. 将当前 `author_slide()` 降级为 fallback 和工程金样本 renderer；
2. 提供 Agent 可调用的语义工具，而不是仅暴露任意文件写入：
   - 读取批准来源、Design Spec、spec lock 和当前页面上下文；
   - 创建/更新文本、形状、分组、图片、原生图表和表格；
   - 使用字体、颜色、间距、栅格和组件 token；
   - 读取版式/图表/关系图原语索引；
   - 写入或 patch 当前页面 SVG；
   - 运行 P01/final checker、chart verifier、render 和结构化视觉审阅；
3. 设计工具优先输出安全的 Scene Graph/语义 SVG 操作，同时保留经过校验的直接 SVG escape hatch，避免组件库重新形成新的固定模板上限；
4. 所有写入必须限制在当前隔离项目、当前页面或明确拥有的规划工件；
5. 每次写入产生 subject hash、tool call ID、author attempt 和 stale 传播。

停止条件：Agent 可以在不执行任意 shell/网络的前提下表达 ppt-master Default 所需的文本、图形、图表、图片和组合布局，并保持 SVG/PPTX 可编辑合同。

### 阶段 C：实现真实 Main Presentation Agent Runtime（P1）

1. 新增独立 `MainPresentationAgent` 运行时，执行有界循环：

   ```text
   恢复上下文/阶段
   → 模型决定下一动作或工具调用
   → Supervisor 校验权限和预算
   → 执行工具并记录观察
   → 模型继续、修复、暂停或完成
   ```

2. 将现有 `AgentRuntimePolicy` 字段接入真实执行：逐 turn 扣减 token/cost、检查 soft/hard timeout、限制工具和最大阶段尝试；
3. 持久化 Agent turn、结构化消息、工具调用、观察摘要、工件 hash、模型/prompt/reference 版本和终止原因；
4. 支持 Worker kill、lease 恢复和进程重启后从同一 checkpoint 继续，不重复 Provider 计费或发布；
5. 对长上下文实施受控压缩：来源事实、批准决策、Design Spec、spec lock 和 stable ID 不得只保留为有损摘要；
6. 来源正文始终作为不可信数据，通过分隔、taint 和最小上下文进入模型；来源中的指令不能改变系统策略或工具权限；
7. 角色切换使用同一 Agent 上下文中的 `Strategist → Executor`，不是启动两个互相丢失上下文的 Agent；
8. 未发生模型 turn 和工具循环时，禁止写入 `author=current-main-agent`。

停止条件：测试能够证明工具选择由模型在运行时完成，Agent 会依据真实工具观察修改后续动作，并且预算、权限、取消和恢复由 Supervisor 强制执行。

### 阶段 D：由 Agent 接管顺序 SVG 创作（P1）

1. 将 `agentic_workflow.py` 中直接调用 `author_slide()` 的主路径替换为 Agent Executor；
2. 保持 `P01 → first-page gate → P02...Pn uninterrupted → final gate` 门序；
3. P01 checker 返回问题后，由 Agent 对问题分类为 method-level/page-local/not-exercised，并修复拥有该问题的 SVG 或上游计划；
4. P02～Pn 复用 P01 得出的设计/测量规则，但每页仍根据其 Blueprint 动态构图；
5. Agent 必须持续读取当前整套页面 roster、全局设计 token、已完成页面摘要和复用对象状态，避免风格漂移；
6. chart/table/diagram 页面必须选择与数据关系匹配的表达，不得为了通过版式多样性指标随机换布局；
7. 保留 `author_slide()` 作为显式 `deterministic-template` fallback；fallback 产物必须标记为受限模板初稿，不能写入 Agent author receipt。

停止条件：主路径的每个 SVG 都能追溯到实际 Agent turn/tool call；固定模板函数不再是 `default-agentic` 页面作者。

### 阶段 E：增加有界视觉反馈闭环（P1）

1. 在全套 SVG 完成后渲染页面 PNG/联系表；
2. 使用支持视觉输入的 reviewer 或同一主 Agent 的视觉检查能力，返回严格 Schema 的问题列表：
   - 主次层级；
   - 文本密度和留白；
   - 对齐、节奏和视觉重心；
   - 连续页面重复；
   - 图表/关系图与内容匹配；
   - 图像裁切、对比度和可读性；
   - 全套颜色、字体和组件一致性；
3. reviewer 只提出问题，不直接修改工件；Main Presentation Agent 按所有权修复；
4. 每套最多两轮视觉修复，达到预算或仍有 blocking 问题时转 `needs_manual/partially_succeeded`；
5. 任意修复使旧 final SVG、chart、content 和 postflight 报告 stale，并重跑适用门；
6. 若产品将视觉审阅设为默认必经门，必须新增版本化产品 profile/策略和容量预算，不得把它描述为未修改的上游默认行为。

停止条件：测试可以注入明显的层级、重复、拥挤和图文不匹配问题，reviewer 能稳定报告，主 Agent 能修复并生成新的 hash-bound 质量证据。

### 阶段 F：灰度、回退与发布（P1）

1. 通过 feature flag 同时保留 `agent-authoring` 与 `deterministic-template`；
2. 使用阶段 0 冻结的同一输入生成 Agent 候选结果，并与两套基线进行人工并排检查；生产用户请求只能发布一个明确标识的结果，避免重复计费和工件混淆；
3. 记录每页/每套 turn、token、费用、耗时、工具失败、修复次数、人工偏好和 fallback 率；
4. 建立 canary 和自动回退条件：安全、跨租户、内容来源、取消/恢复、PPTX 兼容和发布一致性失败立即回退；单纯视觉分数下降进入人工评审，不静默替换用户已批准 revision；
5. fallback 文件名、manifest、UI 状态和下载提示必须显示“模板化受限初稿”，不得继续使用 Agent 成品标签；
6. 同步 `SPEC.md`、`PLAN.md`、system design、Provider/Agent runtime ADR、OpenAPI/SSE、隐私披露、配额、runbook、release checklist 和 rollback 文档。

停止条件：灰度数据达到本 ISSUE 的质量、稳定性、安全和成本门槛，且可在不丢失 revision/审计链的情况下回退。

## 建议代码边界

| 文件/模块 | 改造方向 |
| --------- | -------- |
| `planning.py` | 保留 Intent/Outline；增加或调用 Strategist 生成 Page Blueprint，不承担 SVG 创作 |
| `workflow_models.py` | 扩展 Agent turn/tool/termination、Blueprint、review 和 fallback 状态合同 |
| `default_workflow_request.py` | 固定 agent-authoring 策略、模型/prompt/reference 版本、工具和预算，不用名称推断能力 |
| 新 `presentation_agent_runtime.py` | 模型—工具循环、角色、预算、上下文、终止和 checkpoint 恢复 |
| 新 `presentation_agent_tools.py` | 受约束的来源、规划、SVG、渲染、checker 和 review 工具注册表 |
| `agentic_workflow.py` | 保留 Supervisor/门序；将直接页面生成替换为真实 Agent 调用 |
| `svg_author.py` | 保留为 deterministic fallback/金样本；不再宣称 current-main-agent author |
| `content_quality.py` | 验证 Blueprint assertion/evidence 与最终可见 SVG/PPTX 一致 |
| `workflow_state.py` / runtime supervisor | 持久化 turn、tool call、usage、stale、resume 和 fencing 状态 |
| 新视觉评测模块 | PNG/contact sheet、结构化审阅、最大修复轮数和 hash 绑定 |

具体文件名可在实现 ADR 中调整，但能力和所有权边界不得合并回一个不可恢复的长函数。

## Agent 工具白名单建议

| 工具 | 权限 | 禁止事项 |
| ---- | ---- | -------- |
| `read_approved_context` | 读取批准 snapshot、来源 fragments、Design Spec、lock 和当前 roster | 读取其他租户、未批准来源或任意文件 |
| `write_planning_artifact` | 写入当前 run 拥有的 Blueprint/Design Spec 修订 | 修改批准 Outline、伪造用户 receipt |
| `read_design_catalog` | 读取允许的 token、组件、布局、图表和关系图索引 | 扫描未注册模板或动态加载任意代码 |
| `write_or_patch_slide_svg` | 写入当前页面 SVG/Scene Graph | 写出项目目录、修改 vendor、运行脚本 |
| `run_svg_gate` | 运行声明阶段的 vendored checker | 跳过门序、过滤隐藏错误 |
| `render_slide_or_deck` | 生成隔离 PNG/联系表 | 外部上传或访问任意 URL |
| `run_chart_gate` | 校验有数据图表的页面 | 发明数据或改变来源值 |
| `request_visual_review` | 对当前 hash 的渲染结果请求结构化审阅 | 让 reviewer 直接写 SVG |
| `complete_or_pause_stage` | 以声明原因完成、暂停或失败 | 自行发布 Presentation/PPTX |

任意 shell、任意网络、任意数据库和通用文件系统访问不得作为默认 Agent 工具。

## 失败与降级策略

| 场景 | 处理 |
| ---- | ---- |
| Provider 暂时失败 | 按 Provider/StageAttempt 策略有界重试，从同一 checkpoint 恢复 |
| Agent 输出不符合 Schema | 有界结构化 repair；超过次数后失败，不继续猜测 |
| 工具权限不允许 | 记录 policy violation，禁止扩大权限，返回拥有该决策的阶段 |
| P01/final checker 失败 | Agent 按完整问题集集中修复；超过尝试转 `needs_manual` |
| 视觉审阅仍有 blocking | `partially_succeeded/needs_manual`，不得发布完整成功 |
| 超 turn/token/cost/timeout | 以明确终止原因暂停或受限 fallback；不追加隐藏预算 |
| Agent Runtime 不可用 | 可生成 `deterministic-template` 受限初稿，但必须显式标识 |
| Worker kill/lease 过期 | fencing 后从相同 snapshot/checkpoint 恢复，禁止并发双写 |
| 来源或批准输入变化 | 旧上下文、Blueprint、SVG 和 QA 全部 stale，创建新批准 revision/run |

## 验收标准

### 真实 Agent Runtime

- [ ] `default-agentic` 主路径存在至少一个真实模型 turn，并由模型选择允许的下一工具或终止动作；
- [ ] 每次工具调用都绑定 workflow run、stage、attempt、输入/输出 hash、模型/prompt/reference 版本和 usage；
- [ ] checker/render/reviewer 的观察会进入后续模型上下文，并能触发可验证的 SVG/规划修订；
- [ ] 未发生模型创作循环时不会记录 `author=current-main-agent`；
- [ ] `AgentRuntimePolicy` 的 turn/token/cost/timeout/tool allowlist 在运行时强制执行，而不只是 Schema 校验；
- [ ] Strategist 与 Executor 由同一 Main Presentation Agent 上下文顺序执行；subagent 不按页创作；
- [ ] Worker kill、取消、Redis 重启和 lease 恢复不会重复计费、双写或发布旧工件；
- [ ] 来源 prompt injection 无法改变系统指令、工具权限、研究策略或读取凭据。

### 内容与页面规划

- [ ] 每页都有 assertion、audienceMove、evidenceRefs、visualForm、layoutIntent 和 literal constraints；
- [ ] 来源型页面的可见事实、数字和单位全部能追溯到支持该 claim 的批准 fragment；
- [ ] 不再使用页序取模方式将单个来源句子机械分配为主要正文；
- [ ] Design Spec/Page Blueprint、最终 SVG 和编译后 PPTX 的标题、结论、数据和引用存在 hash-bound 一致性报告；
- [ ] 需要增删、合并、拆分或重排页面时继续遵守批准 revision/委托 receipt 边界。

### 视觉质量

- [ ] 阶段 0 的同一输入重新生成后，人工检查结论为相对当前网站 `deterministic-template` 基线整体更好，并记录与 `ppt-master` 参考基线仍存在的差距；
- [ ] 人工对比记录至少覆盖内容完整性、结论清晰度、视觉层级、信息密度、版式匹配、整套一致性、可编辑性和主要后续问题；
- [ ] 连续三页不得因固定作者分支无条件重复同一正文面板；合法模板复用必须能追溯到 Blueprint/layoutIntent；
- [ ] 图表、时间线、对比、流程、架构和表格只在与数据关系匹配时采用，不以随机多样性替代沟通目的；
- [ ] 视觉审阅发现的 blocking 问题在有界修复后清零，否则不能标记完整成功；
- [ ] 所有页面继续满足无裁切、越界、缺字和可读性要求。

### 工程、兼容与发布

- [ ] 现有 attribution、source security、tenant isolation、approval、content QA、SVG QA、chart QA、postflight、exact export 和 immutable revision 测试保持通过；
- [ ] PowerPoint/WPS 能打开 Agent 结果且无修复提示；标题、正文、形状、图表、表格和图片保持约定的独立可编辑性；
- [ ] `author_slide()` fallback 有独立 profile/state/manifest/UI 标签，不能计入 Agent 成功率；
- [ ] 灰度发布可以按 feature flag 回退，不改变已发布 revision 的内容或下载结果；
- [ ] 监控可以区分 planning、Strategist、Executor、tool、review、compile 和 publish 的耗时、失败、费用及恢复；
- [ ] `SPEC.md`、`PLAN.md`、ADR、system design、API/SSE、隐私、配额、runbook、release checklist 和 rollback 已同步。

## 质量指标

| 指标 | 含义 | 首版门槛 |
| ---- | ---- | -------- |
| Agent path coverage | 正式生成中由真实 Agent author 的页面占比 | 100%，fallback 单独统计 |
| Manual baseline comparison | 使用同一输入人工比较 Agent 候选与两套冻结基线 | 相对当前网站基线整体更好；差距与问题有记录 |
| Claim support pass | 来源型 assertion 获得证据支持的比例 | 100% |
| Visual blocking pass | 最终视觉审阅无 blocking 的套数 | 100% 正式成功结果 |
| Technical gate pass | SVG/chart/package/compatibility 门通过率 | 不低于当前基线 |
| Resume correctness | 故障恢复无重复计费、双写、旧发布 | 100% 故障注入用例 |
| Fallback disclosure | fallback 在 manifest/UI/文件名正确披露 | 100% |

成本和耗时门槛在阶段 0 基准完成后，由产品/工程根据真实数据写入版本化运行策略；不得在缺少测量时伪造固定 SLA。

## 风险与权衡

| 风险 | 影响 | 缓解 |
| ---- | ---- | ---- |
| 非确定性增加 | 同输入结果和耗时波动 | 冻结输入/版本，结构化合同，有界循环，金样本采用语义和视觉容差 |
| 成本和延迟上升 | 单套 PPT 多轮模型调用 | 分阶段预算、P01 方法复用、缓存只绑定相同 hash、最大修复轮数 |
| Agent 幻觉或越权 | 内容错误、安全泄漏 | closed-corpus 默认、claim-support、工具白名单、taint、最小凭据 |
| 上下文过长 | 遗忘全局规则或成本失控 | 分层上下文、不可压缩锁定事实、阶段 checkpoint、受控摘要 |
| 视觉 reviewer 不稳定 | 误报或漏报 | 严格 Schema、确定性技术门优先、人工检查校准、blocking 阈值版本化 |
| 组件工具限制创造力 | 重新退化为模板化页面 | 语义原语优先 + 受校验的直接 SVG escape hatch |
| 直接 SVG 过于自由 | 结构、编辑性或安全回归 | 项目目录隔离、SVG sanitizer/checker、Scene Graph 验证、PPTX postflight |
| 多 Agent 风格漂移 | 页面不一致、上下文丢失 | 单主 Agent author；reviewer 只审阅不创作 |

## 完成定义

本 ISSUE 只有在以下条件同时满足时才能关闭：

1. `default-agentic` 的主路径不再直接以固定 `author_slide()` 作为页面作者；
2. 真实 Main Presentation Agent 完成 Strategist、顺序 SVG authoring、工具观察和有界修复；
3. Agent、fallback 和 reviewer 三类责任在代码、receipt、manifest、指标和 UI 中可区分；
4. 使用阶段 0 冻结的同一输入完成 Agent 改进结果，并经人工并排检查确认相对当前网站基线整体改善；发现的发布阻断问题已经修复或进入明确的非成功状态；
5. 任意 Agent 失败、超预算、视觉 blocking 或技术门失败都不能被包装为完整 `succeeded`；
6. 相关架构与运行文档已同步，并完成可演练的 feature flag 回退。

仅新增 `agent.py` 文件、把函数改名为 Agent、在日志中写 `current-main-agent`、增加一次模型调用，或让模型只返回固定模板参数，均不满足完成定义。

## 相关文档与代码

- `docs/issues/ISSUE-002-generated-pptx-renders-outline-placeholders-instead-of-usable-draft.md`
- `docs/design/g01-engine-adapter.md`
- `docs/design/system-design.md`
- `docs/adr/ADR-004-engine-vendoring.md`
- `services/worker/src/instant_ppt_worker/planning.py`
- `services/worker/src/instant_ppt_worker/default_workflow_request.py`
- `services/worker/src/instant_ppt_worker/workflow_models.py`
- `services/worker/src/instant_ppt_worker/agentic_workflow.py`
- `services/worker/src/instant_ppt_worker/svg_author.py`
- `services/worker/src/instant_ppt_worker/content_quality.py`
- `vendor/ppt-master/workflows/generate-pptx.md`
