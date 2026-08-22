<!-- ppt-master-schema: design-spec/v1 -->
# OpenAI GPT-5.6 发布公告中文解读 - Design Spec

## I. Project Information

| Item | Value |
| --- | --- |
| Project Name | OpenAI GPT-5.6 发布公告中文解读 |
| Canvas Format | ppt169，1280 × 720 |
| Page Count | 12 |
| Primary Language | zh-CN |
| Target Audience | 关注前沿模型能力与落地效率的技术负责人、开发者、产品负责人和知识工作团队 |
| Communication Intent | 用清晰的证据链解释 GPT-5.6 的核心跃迁，比较 Sol、Terra、Luna 的定位，并说明 max、ultra、程序化工具调用、安全与定价如何影响实际采用 |
| Desired Audience Outcome | 听众能够理解 GPT-5.6 的能力—效率主张，按任务难度、时延和预算选择合适模型与推理强度，并形成试用或迁移判断 |
| Core Message / Ask / Action | GPT-5.6 以更高的每 token 智能和每美元性能覆盖日常到最艰巨工作，并通过 Sol、Terra、Luna 与 max、ultra 提供可伸缩的能力梯度 |
| Delivery Context | 主要用于有主讲人的 15 分钟产品发布解读；次要作为会后可独立阅读的模型选型参考 |
| Artifact Afterlife | 作为团队内部的模型能力速览、选型讨论材料和后续采用评估参考 |
| Reading Mode | balanced |
| Content Strategy | balanced default：重组长篇公告为“主张—证据—能力—安全—采用”叙事，不引入文档外事实 |
| Design Style | 伸缩智能坐标系：深色科技底座结合数据新闻式证据结构 |
| Image Source Boundary | none — 不使用外部图片；以可编辑原生图表、能力阶梯、流程关系图和大数字证据页承担视觉表达 |
| AI Image Acquisition Path | not applicable |
| Generation Mode | continuous |
| Spec Refinement | disabled |
| Speaker Notes | enabled — final Stage-2 proactive policy |
| Custom Animations | disabled — final Stage-2 proactive policy |
| Narration Audio | disabled — final Stage-2 proactive policy |
| Created Date | 2026-08-16 |

## II. Canvas Specification

| Property | Value |
| --- | --- |
| Format | PowerPoint 16:9 |
| Dimensions | 1280 × 720 px |
| viewBox | `0 0 1280 720` |
| Margins | 40 px safe margin；数据来源与页码区域距底边至少 24 px |
| Content Area | x=40–1240，y=40–680；正文主体优先落在 y=112–630 |

## III. Visual Theme

### Theme Style

- **Mode**: custom
- **Mode References**: pyramid
- **Mode Behavior**: 以 pyramid 为唯一叙事基底，开场先给出“更高智能、更低总成本、按需扩展”的结论；随后用能力、效率、工具、安全与可用性五组证据逐层支撑，并以模型选择矩阵收束到试用判断。
- **Visual style**: custom
- **Visual Style References**: dark-tech, data-journalism
- **Visual Style Behavior**: 由 dark-tech 提供深色负空间、精密节点与克制光感，由 data-journalism 提供严谨列网、数据主轴、细规则和来源层级；页面避免重复卡片墙，让大数字、模型轨道和比较图成为主视觉。
- **Theme**: “能力轨道”作为跨页视觉母题：同心弧、短轨迹与节点表示智能随任务雄心逐级扩展；证据页把轨迹收敛为精确坐标轴、细规则和数据标签。
- **Tone**: 精密、可信、克制而有雄心；展示能力跃迁，但每个强主张都由来源文档中的数字或机制支撑。

### Color Scheme

| Role | HEX | Purpose |
| --- | --- | --- |
| Background | #07111F | 全页深色主场，营造技术深度与负空间 |
| Secondary background | #0D1B2A | 内容分区、对比带和次级面板 |
| Primary | #49B9FF | 主模型轨迹、标题关键字、主要数据系列 |
| Accent | #B7F34A | 最高价值结论、效率优势、推荐动作 |
| Secondary accent | #7A8FFF | 第二数据系列、ultra 与并行能力 |
| Body text | #EAF2FF | 主正文与高对比标签 |
| Surface | #122439 | 数据块和图表承载面 |
| Grid | #294056 | 细网格、分隔线、坐标轴与弱连接 |
| Muted text | #A7B8CA | 注释、来源、限定条件与脚注 |

## IV. Typography System

### Font Plan

| Role | Character (Reference) | Primary | English if non-English | Fallback tail |
| --- | --- | --- | --- | --- |
| Title | 现代黑体、结论句、宽松字面 | Microsoft YaHei | Segoe UI | sans-serif |
| Body | 中性黑体、紧凑但可读 | Microsoft YaHei | Segoe UI | sans-serif |
| Data | 等宽、技术标签与数值精度 | Consolas | Consolas | monospace |
| Code | 等宽、API 与技术术语 | Consolas | Consolas | monospace |

- **Title stack**: Microsoft YaHei, Segoe UI, sans-serif
- **Body stack**: Microsoft YaHei, Segoe UI, sans-serif
- **Data stack**: Consolas, Microsoft YaHei, monospace
- **Code stack**: Consolas, Microsoft YaHei, monospace
- **Role rationale**: Data 与 Code 在多页反复承载评测数值、模型名、API 名称和推理强度，使用 Consolas 提高技术辨识度并与正文形成清晰角色差异。

### Font Size Hierarchy

| Purpose | Anchor Size (px) |
| --- | ---: |
| Body | 24 |
| Title | 42 |
| Subtitle | 32 |
| Annotation | 18 |
| Data hero | 72 |
| Footnote | 15 |

## V. Layout Principles

### Page Structure

- **Header area**: 左上角使用结论式标题；右上角可用短标签标明章节或能力域，避免全宽标题条。
- **Content area**: 以 12 列隐性网格组织；大数字、图表或能力轨道占据主轴，文字解释贴近证据而非另起等权卡片。
- **Footer area**: 左侧写来源或限定说明，右侧写 `GPT-5.6 / NN`；使用 Grid 与 Muted text，保持低注意力。

### Spacing Specification

| Element | Current Project |
| --- | --- |
| Safe margin | 40 px |
| Content block gap | 24–32 px；主证据与解释之间可放大到 40 px |
| Icon-text gap | 12 px |

## VI. Icon Usage Specification

- **Primary bundled library**: tabler-outline
- **Stroke Width**: 2

| Icon Path | Suitable Scenarios |
| --- | --- |
| tabler-outline/brain | 智能、推理、知识工作 |
| tabler-outline/code-ai | 编码模型、程序化工具调用、智能体开发 |
| tabler-outline/shield-check | 安全、防护、可信访问 |
| tabler-outline/microscope | 科学研究、生命科学、评测 |
| tabler-outline/currency-dollar | 成本、定价、每美元性能 |
| tabler-outline/chart-bar | 评测、性能对比、数据证据 |
| tabler-outline/hierarchy-3 | 模型家族、分层架构、多智能体协调 |
| tabler-outline/rocket | 发布、采用、能力跃迁 |
| tabler-outline/cpu | 算力、推理强度、max / ultra |
| tabler-outline/network | 工具编排、多智能体、连接型工作流 |

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Crop Policy | Acquire Via | Status | Reference | text_policy | page_role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## IX. Content Outline

### Part 1: 发布主张与能力梯度

#### Slide 01 - 随雄心扩展的前沿智能

- **Audience move**: 从“又一次模型更新”转变为意识到这是一个以效率和按需扩展为核心的新能力体系。
- **Layout**: 封面采用深色负空间；中心是一条由三个节点扩展为多条并行轨迹的“能力轨道”，标题与发布日期沿轨道左侧排布。背景只保留低对比网格和少量节点光晕。
- **Title**: GPT-5.6：随雄心扩展的前沿智能
- **Core message**: 每个 token 带来更多智能，每一美元获得更强性能，并可为最艰巨工作按需提升能力。
- **Content**: 主标题；副标题“Sol · Terra · Luna”；发布日期“2026 年 7 月 9 日”；角标“基于 OpenAI 官方公告中文译稿”。
- **Cover impact**: 以“每个 token 更多智能”作为绑定钩子；三条能力轨道从细线汇聚为一条高亮路径，表达从日常任务到 ultra 的伸缩性。

#### Slide 02 - GPT-5.6 把性能、效率与可伸缩性合成一个系统

- **Audience move**: 从记住零散功能转变为掌握整次发布的三个核心变化。
- **Layout**: 一个中心三角坐标系：顶部“更强能力”，左下“更少 token / 更短时间”，右下“按需扩展”；Sol、Terra、Luna 沿能力轴排列，max 与 ultra 作为外层增益环。
- **Title**: 三个变化定义 GPT-5.6：更强、更省、可按需扩展
- **Core message**: GPT-5.6 的价值不只在峰值分数，而在同一模型家族中同时改善智能、成本效率与任务扩展方式。
- **Content**: ① Sol 在编码、知识工作、网络安全与科学领域达到前沿成绩；② Terra 与 Luna 把高能力扩展到更低成本层级；③ max 增加单智能体推理时间，ultra 默认协调 4 个智能体并行推进复杂工作。
- **Visualization**: 定性关系图：三条价值轴围绕模型家族，外层增益环表示 max / ultra；读取顺序为核心主张 → 三条轴 → 能力层级。

#### Slide 03 - Sol、Terra、Luna 覆盖从高频日常到最艰巨任务

- **Audience move**: 从只关注旗舰模型转变为能够按工作价值和约束理解三档模型定位。
- **Layout**: 横向能力阶梯占据页面中部；每一档不是卡片，而是相邻连通的轨道区间。下方叠加“默认 → max → ultra”的推理强度轴。
- **Title**: 三档模型提供连续能力梯度，而不是三个孤立产品
- **Core message**: Luna 优先速度与成本，Terra 平衡日常工作，Sol 承担最高难度；推理强度则在同一层级内继续向上扩展。
- **Content**: Luna：速度最快、价格最低，适合高频与成本敏感任务。Terra：成本更低、性能可与 GPT-5.5 竞争，适合日常专业工作。Sol：旗舰层级，面向最复杂编码、知识工作、安全与科研。max：比 xhigh 提供更多推理时间。ultra：默认 4 智能体并行，以更高 token 消耗换取更强结果和更短高难任务完成时间。
- **Visualization**: 定性阶梯与双轴选择图；横轴为任务难度/价值，纵向标注推理投入增加，三模型区间保持连续。
- **Native shape suggestion**: 使用 PowerPoint blockArc / chevron 类预设形成连续能力轨道，表达相邻层级而非独立卡片。

### Part 2: 证据链——效率、编码与并行

#### Slide 04 - Sol 在长时专业工作中以更低成本拉开能力差距

- **Audience move**: 从接受“更强”的宣传语转变为理解分数、成本与时延共同构成优势。
- **Layout**: 左侧用 53.6 英雄数字建立 Agents' Last Exam 结论；右侧用两条短比较轴呈现“+13.1 分”“约四分之一成本”，底部横向补充 AA Intelligence Index 的时间与成本证据。
- **Title**: 领先不再以更高消耗为代价，而是以更优效率实现
- **Core message**: GPT-5.6 Sol 在专业长时工作流中同时提高结果质量并压低预估成本与完成时间。
- **Content**: Agents' Last Exam：Sol 得分 53.6，领先 Claude Fable 5（自适应推理）13.1 分；即使使用中等推理强度仍领先 11.4 分，预估成本约为后者四分之一。Artificial Analysis Intelligence Index：Sol max 与 Fable 5 仅差 1 分，但完成时间减少 61%，预估成本约为一半。Terra 与 Luna 均以约十六分之一成本超过 Fable 5。
- **Visualization**: `professional-efficiency-evidence`：大数字 + 两组水平比较轴，不对不同评测分数做同轴混排。
- **Native-ready**: professional-efficiency-evidence=yes

#### Slide 05 - 编码优势来自模型能力，也来自更高效的工具工作流

- **Audience move**: 从把编码能力理解为“写代码更准”转变为理解其长时任务、工具调用和流程协调能力。
- **Layout**: 上半部是 AA Coding Agent Index 的原生横向条形图；下半部是一条从“编写轻量程序”到“筛选中间结果”再到“动态调整工作流”的工具编排链。
- **Title**: GPT-5.6 把编码、工具编排与长时执行合成同一能力
- **Core message**: Sol 刷新编码智能体指标，整个家族则用更少 token、更短时间完成工具密集型任务。
- **Content**: AA Coding Agent Index：Sol 80.0、Terra 77.4、GPT-5.5 76.4、Luna 74.6；Sol 比 Fable 5 高 2.8 分，同时输出 token 不到一半、用时不到一半，成本约低三分之一。Terminal-Bench 2.1：Sol 88.8，Sol Ultra 91.9；DeepSWE：Sol 72.7。Responses API 的程序化工具调用可在内存中编写并运行程序，协调工具、处理中间结果并减少模型往返。
- **Visualization**: `coding-agent-index`：四系列横向条形图；另有定性工具链，按执行顺序从左向右读取。
- **Native-ready**: coding-agent-index=yes

#### Slide 06 - max 深挖单条路径，ultra 并行探索多条路径

- **Audience move**: 从把推理强度看成抽象档位转变为理解何时增加时间、何时增加并行智能体。
- **Layout**: 页面从左至右由单轨变为四轨；左侧 xhigh / max 共用一条加深路径，右侧 ultra 展开 4 条并行工作流并重新汇总。底部用小型比较显示 Terminal-Bench 2.1 的 88.8 → 91.9。
- **Title**: 两种扩展方式：让一个智能体想得更久，或让多个智能体并行推进
- **Core message**: max 增加推理深度；ultra 默认协调 4 个智能体，以更高 token 投入换取更强结果和更短高难任务完成时间。
- **Content**: max：比 xhigh 提供更多时间探索备选方案、执行检查并修订方法。ultra：默认 4 智能体并行处理不同工作流；在 BrowseComp、SEC-Bench Pro、Terminal-Bench 2.1 上，多智能体使得分—延迟前沿向左上方移动。BrowseComp 与 SEC-Bench Pro 还展示了 16 智能体配置。Responses API 的多智能体能力以 beta 提供。
- **Visualization**: 定性分叉—汇总流程图；`terminal-bench-scaling` 为两点对比，避免把不同基准混在同一图中。
- **Native-ready**: terminal-bench-scaling=yes

### Part 3: 从软件开发扩展到知识工作、安全与科研

#### Slide 07 - GPT-5.6 从生成内容升级为检查并交付成果

- **Audience move**: 从把模型视为内容生成器转变为理解其端到端知识工作与设计判断力。
- **Layout**: 中央是一条“提取杂乱上下文 → 形成专家成果 → 检查渲染结果 → 修正并交付”的闭环；右侧悬浮 92.2% 和 62.6% 两个证据数字，左下方列出演示文稿、文档和电子表格三类成果。
- **Title**: 更强的设计判断与计算机操作，让知识工作走向端到端交付
- **Core message**: GPT-5.6 不只生成底层代码或内容，还能检查渲染结果、发现问题并完成最后打磨。
- **Content**: Sol Ultra 在 BrowseComp 达 92.2%；Sol 在 OSWorld 2.0 达 62.6%，并以少 85% 的输出 token 超过 Opus 4.8。模型能从文档、Slack、Notion、Microsoft 365、Google Drive 等杂乱上下文提取信息，生成可分享成果；还能推断演示文稿中的布局、字体、间距、颜色、重复内容模式和母版规则，并一致应用到新材料。
- **Visualization**: 端到端闭环关系图 + 两个独立英雄指标；三类成果作为闭环输出分支。

#### Slide 08 - 网络安全提升最陡峭，科学能力同步前移

- **Audience move**: 从只看到通用评测转变为认识高风险、高价值专业领域的能力边界与提升幅度。
- **Layout**: 左侧 7 列区域用于三组网络安全条形对比；右侧 5 列区域用科学能力轨道概括生命科学、化学和真实研究工作流的帕累托改进，二者在底部汇入“双重用途”提示。
- **Title**: GPT-5.6 在网络安全上大幅跃迁，同时推进科学研究前沿
- **Core message**: 安全领域的能力提升最显著，但它同时增强防御价值与潜在双重用途风险。
- **Content**: SEC-Bench Pro：Sol 71.2%，GPT-5.5 45.8%。ExploitBench：Sol 73.5%，GPT-5.5 47.9%。ExploitGym：Sol 六小时通过率 33.7%，GPT-5.5 为 15.1%。Sol 还在真实生物学、生命科学研究工作流与化学方面相对 GPT-5.5 实现帕累托改进；系统支持安全代码审查、补丁、威胁建模与蓝队防御。
- **Visualization**: `cybersecurity-gains`：三组双系列横向条形图；科学部分为不带虚构数值的定性轨道。
- **Native-ready**: cybersecurity-gains=yes

#### Slide 09 - 能力越强，安全控制越需要分层并动态校准

- **Audience move**: 从把安全理解为单一拒绝策略转变为掌握模型内生防护、实时监控与可信访问的组合机制。
- **Layout**: 同心防护环从内到外依次标注模型内生防护、推理监控器、实时检查、持续监控、账户级执行与可信访问；右下角用两个数字锚定评估强度。
- **Title**: GPT-5.6 用分层防护保护合法工作，同时提高对严重滥用的控制
- **Core message**: 防护系统通过多层冗余与按可信度、风险校准的访问控制，在保留防御用途的同时限制高风险行为。
- **Content**: GPT-5.6 的生物学与网络安全能力均未跨越“关键（Critical）”阈值。全面开放前开展人工红队与大规模自动化测试，包括约 70 万个 NVIDIA A100 Tensor Core GPU 等效小时。与此前模型相比，Sol 的网络安全防护拦截潜在有害活动约多 10 倍。个人与机构可通过 Daybreak 网络安全可信访问计划申请更强防御能力。
- **Visualization**: 分层同心防护架构；读取顺序由模型内核向账户与访问层扩展。
- **Native shape suggestion**: 使用 PowerPoint 圆环/块弧预设构成五层防护圈，保持各层可编辑。

### Part 4: 采用、可用性与选择行动

#### Slide 10 - GPT-5.6 已开始改变 OpenAI 自身的研究生产函数

- **Audience move**: 从把评测提升视为实验室数字转变为看到模型在真实研究流程中的采用与递归改进信号。
- **Layout**: 一条从“研究人员日常任务”到“研究系统优化”再到“改进下一代模型”的递归环；环外放置三个增长指标：>2×、100×、约22×，底部用 +16.2 分收束。
- **Title**: 内部采用增长显示 AI 辅助研究正从工具变成工作方式
- **Core message**: GPT-5.6 在诊断、训练系统优化、实验与结果解释中形成闭环，并加速对下一代模型的改进。
- **Content**: 每位活跃研究人员的日均输出 token 超过 GPT-5.5 最高水平的两倍；过去六个月，用于内部编码推理的研究算力份额增长 100 倍，内部智能体 token 使用量约增长 22 倍。面向真实 AI 研究任务的内部递归式自我改进评测中，Sol 比 GPT-5.5 综合提升 16.2 分。公告明确指出采用指标本身并不直接等同于研究进展。
- **Visualization**: 递归改进闭环 + 四个证据锚点；注释明确区分“采用信号”和“研究进展”。

#### Slide 11 - 可用性覆盖 ChatGPT、Codex 与 API，定价呈三档梯度

- **Audience move**: 从理解能力转变为明确可以在哪里使用、首发价格如何分层以及发布后价格如何更新。
- **Layout**: 左侧为 Chat / ChatGPT Work 与 Codex / API 三条可用性通道；右侧为首发价格原生表格；顶部放置“7 月 30 日更新”窄条，避免与首发价格混淆。
- **Title**: 三个模型层级已经进入主流产品入口，成本梯度与能力梯度对应
- **Core message**: GPT-5.6 自发布日起进入 ChatGPT、Codex 与 API；Sol、Terra、Luna 以不同价格覆盖不同任务价值。
- **Content**: Chat：Plus、Pro、Business、Enterprise 可使用 Sol；Pro 与 Enterprise 可选 Sol Pro。ChatGPT Work 与 Codex：Free、Go 可使用 Terra；Plus 及以上可在 Sol、Terra、Luna 中选择，Codex ultra 面向 Plus 及以上。API：Sol、Terra、Luna 均可用，并支持程序化工具调用与 beta 多智能体。2026-07-09 首发价格（每 100 万 token）：Sol 输入 $5 / 输出 $30；Terra $2.50 / $15；Luna $1 / $6。2026-07-30 更新：Terra 价格下调 20%，Luna 下调 80%；本页表格保留首发价格。缓存写入按未缓存输入费率 1.25 倍计费，缓存读取相对输入价格折扣 90%。
- **Visualization**: `launch-pricing-table`：模型 × 输入/输出的纯文本原生表格；顶部更新条作为独立限定信息。
- **Native-ready**: launch-pricing-table=yes

#### Slide 12 - 从默认高效开始，只在任务价值值得时增加计算

- **Audience move**: 从被大量能力信息淹没转变为获得一套可执行的模型与推理强度选择规则。
- **Layout**: 2×2 选择矩阵占页面主体：横轴“任务复杂度/风险”，纵轴“允许的成本与时延”；Luna、Terra、Sol 分布在三个递进区域，max / ultra 作为右上角的额外计算层。底部是一条三步试用动作。
- **Title**: 选择 GPT-5.6 的原则：模型层级决定基线，推理强度决定投入
- **Core message**: 高频、成本敏感任务从 Luna 开始；日常专业工作优先 Terra；最高难度和高价值任务使用 Sol，并仅在收益值得时启用 max 或 ultra。
- **Content**: 选择规则：① 先按任务复杂度、失败代价与预算选择 Luna / Terra / Sol；② 再按是否需要更深检查或并行工作流选择默认 / max / ultra；③ 用一组真实任务比较质量、完成时间、token 与总成本，而不是只看单项基准。建议试用动作：选取高频、标准专业、复杂长时三类代表任务；记录现有基线；逐层提升模型与推理强度，找到边际收益停止点。
- **Visualization**: 定性 2×2 选择矩阵 + 三步验证路径；不添加文档外成本或回报数字。
- **Closing impact**: 以“从默认高效开始，只在任务价值值得时增加计算”作为绑定收束语；模型轨道在右上角汇聚成一个高亮选择点，形成真正的行动结束。

## X. Speaker Notes Requirements

- **Generation**: enabled
- **Filename**: match each SVG filename under `notes/`
- **Content**: 以用户提供的中文译稿为唯一事实来源；每页先讲结论，再解释指标含义、限定条件和与前后页的关系。不要把脚注或完整表格逐字朗读；对“预估成本”“内部评测”“首发价格”等限定语必须口头保留。
- **Total duration**: 15 minutes
- **Notes style**: 专业、清晰、证据驱动，使用短过渡句帮助技术与业务听众共享同一理解路径
- **Presentation purpose**: 解释发布主张、建立可信证据链，并支持模型选型与试用判断
