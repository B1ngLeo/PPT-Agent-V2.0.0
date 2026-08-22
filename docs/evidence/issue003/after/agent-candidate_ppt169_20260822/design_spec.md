<!-- ppt-master-schema: design-spec/v1 -->
# GPT 5.6 官方公告解读 - Design Spec

## I. Project Information

| Item | Value |
| --- | --- |
| Project Name | GPT 5.6 官方公告解读 |
| Canvas Format | PPT 16:9 (1280 × 720) |
| Page Count | 10 |
| Primary Language | zh-CN |
| Target Audience | 关注大模型最新动态的产品、研发与业务决策团队 |
| Communication Intent | 基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响 |
| Desired Audience Outcome | 基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响 |
| Core Message / Ask / Action | 基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响 |
| Delivery Context | ISSUE-003 冻结输入 before/after 对照 |
| Artifact Afterlife | Editable decision-support draft with source traceability |
| Reading Mode | presentation |
| Content Strategy | Closed-corpus, conclusion-first, every claim bound to source fragments |
| Design Style | Data-journalism grid with restrained evidence hierarchy |
| AI Image Acquisition Path | not applicable |
| Generation Mode | continuous |
| Spec Refinement | disabled |
| Speaker Notes | disabled — final Stage-2 policy |
| Custom Animations | disabled — final Stage-2 policy |
| Narration Audio | disabled — final Stage-2 policy |
| Created Date | 2026-08-22 |

## II. Canvas Specification

| Property | Value |
| --- | --- |
| Format | PPT 16:9 |
| Dimensions | 1280 × 720 |
| viewBox | `0 0 1280 720` |
| Margins | 72 px safe margin |
| Content Area | 72, 64 to 1208, 656 |

## III. Visual Theme

### Theme Style

- **Mode**: pyramid
- **Visual style**: data-journalism
- **Theme**: source-led technical publication
- **Tone**: precise, restrained, decision-oriented

### Color Scheme

| Role | HEX | Purpose |
| --- | --- | --- |
| Background | #F8FAFC | publication field |
| Secondary background | #E2E8F0 | evidence bands |
| Primary | #0F172A | titles and axes |
| Accent | #2563EB | primary data series |
| Secondary accent | #0F766E | comparison series |
| Body text | #1E293B | body copy |

## IV. Typography System

### Font Plan

| Role | Character (Reference) | Primary | English if non-English | Fallback tail |
| --- | --- | --- | --- | --- |
| Title | precise publication sans | Microsoft YaHei | Arial | sans-serif |
| Body | compact evidence sans | Microsoft YaHei | Arial | sans-serif |
| Data | tabular numeric sans | Arial | Arial | sans-serif |

- **Title stack**: Microsoft YaHei, Arial, sans-serif
- **Body stack**: Microsoft YaHei, Arial, sans-serif
- **Data stack**: Arial, Microsoft YaHei, sans-serif

### Font Size Hierarchy

| Purpose | Anchor Size (px) |
| --- | ---: |
| Body | 22 |
| Title | 38 |
| Subtitle | 24 |
| Annotation | 15 |
| Data | 18 |

## V. Layout Principles

### Page Structure

- **Header area**: assertion title and one-line takeaway
- **Content area**: role-matched evidence grid; chart pages use the chart as the spine
- **Footer area**: page number and source-fragment trace

### Spacing Specification

| Element | Current Project |
| --- | --- |
| Safe margin | 72 px |
| Content block gap | 24 px |
| Icon-text gap | 12 px |

## VI. Icon Usage Specification

- **Primary bundled library**: none

| Icon Path | Suitable Scenarios |
| --- | --- |

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Crop Policy | Acquire Via | Status | Reference | text_policy | page_role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## IX. Content Outline

### Part 1: Decision briefing

#### Slide 01 / P01 - GPT 5.6 官方公告解读

- **Assertion**: GPT\-5.6 能推断演示文稿的设计系统——布局、字体、间距、颜色、重复内容模式，以及嵌入幻灯片母版的规则——并将这些约定一致地应用到新材料中。
- **Audience move**: 这组已批准证据回答“基于官方公告材料的系统梳理；面向产品、研发与业务决策团队”，据此可基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响。
- **Visual form**: mixed
- **Layout intent**: assertion-led opening with one sourced hook and generous whitespace
- **Layout**: assertion-led opening with one sourced hook and generous whitespace
- **Title**: GPT 5.6 官方公告解读
- **Core message**: 基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响
- **Content**: 基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-041
- **Content blocks**: [{"blockId":"P01-evidence","kind":"evidence","hierarchy":1,"text":"GPT\\-5.6 能推断演示文稿的设计系统——布局、字体、间距、颜色、重复内容模式，以及嵌入幻灯片母版的规则——并将这些约定一致地应用到新材料中。","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-041"]}]
- **Literal constraints**: 5.6
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-041

#### Slide 02 / P02 - 公告概览与解读框架

- **Assertion**: 在有限预览之后，我们正式全面推出 GPT\-5.6 模型家族：全新旗舰模型 Sol、适合日常工作的均衡型模型 Terra，以及成本效率最高的模型 Luna。
- **Audience move**: 这组已批准证据回答“官方公告的核心信息一览；本次解读的结构与评估维度”，据此可基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响。
- **Visual form**: mixed
- **Layout intent**: assertion title above a structured evidence grid
- **Layout**: assertion title above a structured evidence grid
- **Title**: 公告概览与解读框架
- **Core message**: 在有限预览之后，我们正式全面推出 GPT\-5.6 模型家族：全新旗舰模型 Sol、适合日常工作的均衡型模型 Terra，以及成本效率最高的模型 Luna。
- **Content**: 在有限预览之后，我们正式全面推出 GPT\-5.6 模型家族：全新旗舰模型 Sol、适合日常工作的均衡型模型 Terra，以及成本效率最高的模型 Luna。
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-008
- **Content blocks**: [{"blockId":"P02-evidence","kind":"evidence","hierarchy":1,"text":"在有限预览之后，我们正式全面推出 GPT\\-5.6 模型家族：全新旗舰模型 Sol、适合日常工作的均衡型模型 Terra，以及成本效率最高的模型 Luna。","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-008"]}]
- **Literal constraints**: 5.6
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-008

#### Slide 03 / P03 - 发布时间线与版本节奏

- **Assertion**: 发布日期：2026 年 7 月 9 日
- **Audience move**: Use the approved milestones to answer '官方公布的发布节点与时间线；各阶段可用范围与里程碑安排'.
- **Visual form**: timeline
- **Layout intent**: ordered milestones with evidence bound to each step
- **Layout**: ordered milestones with evidence bound to each step
- **Title**: 发布时间线与版本节奏
- **Core message**: 发布日期：2026 年 7 月 9 日
- **Content**: 发布日期：2026 年 7 月 9 日；2026 年 7 月 30 日更新：OpenAI 将 GPT\-5.6 Luna 的价格下调 80%，将 GPT\-5.6 Terra 的价格下调 20%。；个人成员须在 9 月 1 日前启用采用硬件支持通行密钥的高级账户安全功能，才能继续使用网络安全能力最强的前沿模型
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-003, 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-007, 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-057
- **Content blocks**: [{"blockId":"P03-milestone-1","kind":"sequence","hierarchy":1,"text":"发布日期：2026 年 7 月 9 日","relationship":"precedes","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-003"]},{"blockId":"P03-milestone-2","kind":"sequence","hierarchy":2,"text":"2026 年 7 月 30 日更新：OpenAI 将 GPT\\-5.6 Luna 的价格下调 80%，将 GPT\\-5.6 Terra 的价格下调 20%。","relationship":"precedes","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-007"]},{"blockId":"P03-milestone-3","kind":"sequence","hierarchy":3,"text":"个人成员须在 9 月 1 日前启用采用硬件支持通行密钥的高级账户安全功能，才能继续使用网络安全能力最强的前沿模型","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-057"]}]
- **Literal constraints**: 2026 | 7 | 9 | 30 | 5.6 | 80% | 20% | 1
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-003, 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-007, 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-057

#### Slide 04 / P04 - 核心能力解析

- **Assertion**: Responses API 中，程序化工具调用让 GPT\-5.6 能在内存中编写并运行程序，以协调工具、处理中间结果，并兼容零数据保留（ZDR）。
- **Audience move**: 这组已批准证据回答“官方披露的核心能力与新特性；能力边界的官方表述”，据此可基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响。
- **Visual form**: mixed
- **Layout intent**: assertion title above a structured evidence grid
- **Layout**: assertion title above a structured evidence grid
- **Title**: 核心能力解析
- **Core message**: Responses API 中，程序化工具调用让 GPT\-5.6 能在内存中编写并运行程序，以协调工具、处理中间结果，并兼容零数据保留（ZDR）。
- **Content**: Responses API 中，程序化工具调用让 GPT\-5.6 能在内存中编写并运行程序，以协调工具、处理中间结果，并兼容零数据保留（ZDR）。
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-078
- **Content blocks**: [{"blockId":"P04-evidence","kind":"evidence","hierarchy":1,"text":"Responses API 中，程序化工具调用让 GPT\\-5.6 能在内存中编写并运行程序，以协调工具、处理中间结果，并兼容零数据保留（ZDR）。","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-078"]}]
- **Literal constraints**: 5.6
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-078

#### Slide 05 / P05 - Terminal-Bench 2.1 中，Sol Ultra 达到 91.9%，领先 Sol 3%

- **Assertion**: Terminal-Bench 2.1 中，Sol Ultra 达到 91.9%，领先 Sol 3%
- **Audience move**: Use the sourced Terminal-Bench 2.1 comparison to answer '以图表呈现官方基准测试数据；官方口径下的性能指标解读'.
- **Visual form**: chart
- **Layout intent**: full-width comparison chart spine with direct labels and a source line
- **Layout**: full-width comparison chart spine with direct labels and a source line
- **Title**: Terminal-Bench 2.1 中，Sol Ultra 达到 91.9%，领先 Sol 3%
- **Core message**: 对比结论直接来自已批准来源，未执行外部研究。
- **Content**: 对比结论直接来自已批准来源，未执行外部研究。
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-084
- **Content blocks**: [{"blockId":"P05-chart","kind":"chart","hierarchy":1,"text":"Terminal-Bench 2.1","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-084"]}]
- **Literal constraints**: Terminal-Bench 2.1 | Sol | Sol Ultra | Terra | Luna | GPT-5.5 | 88.8 | 91.9 | 87.4 | 84.7 | 85.6 | %
- **Visualization**: `throughput-comparison` column chart maps sourced labeled values to bar height with a zero baseline
- **Native-ready**: throughput-comparison=yes
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-084

#### Slide 06 / P06 - 与前代及同类模型对比

- **Assertion**: GPT\-5.6 Sol 为智能与效率树立了新标准：它在编码、知识工作、网络安全和科学领域取得最先进的成绩，同时以更少的 token、更低的预估成本超越此前及其他前沿模型。
- **Audience move**: 这组已批准证据回答“官方材料中的版本间对比；关键差异点的结构化呈现”，据此可基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响。
- **Visual form**: comparison
- **Layout intent**: two evidence columns with a shared decision criterion
- **Layout**: two evidence columns with a shared decision criterion
- **Title**: 与前代及同类模型对比
- **Core message**: GPT\-5.6 Sol 为智能与效率树立了新标准：它在编码、知识工作、网络安全和科学领域取得最先进的成绩，同时以更少的 token、更低的预估成本超越此前及其他前沿模型。
- **Content**: GPT\-5.6 Sol 为智能与效率树立了新标准：它在编码、知识工作、网络安全和科学领域取得最先进的成绩，同时以更少的 token、更低的预估成本超越此前及其他前沿模型。
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-009
- **Content blocks**: [{"blockId":"P06-evidence","kind":"evidence","hierarchy":1,"text":"GPT\\-5.6 Sol 为智能与效率树立了新标准：它在编码、知识工作、网络安全和科学领域取得最先进的成绩，同时以更少的 token、更低的预估成本超越此前及其他前沿模型。","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-009"]}]
- **Literal constraints**: 5.6
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-009

#### Slide 07 / P07 - 定价、可用性与接入方式

- **Assertion**: 2026 年 7 月 30 日更新：OpenAI 将 GPT\-5.6 Luna 的价格下调 80%，将 GPT\-5.6 Terra 的价格下调 20%。
- **Audience move**: 这组已批准证据回答“官方公布的定价与计费信息；开放范围与接入方式说明”，据此可基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响。
- **Visual form**: mixed
- **Layout intent**: assertion title above a structured evidence grid
- **Layout**: assertion title above a structured evidence grid
- **Title**: 定价、可用性与接入方式
- **Core message**: 2026 年 7 月 30 日更新：OpenAI 将 GPT\-5.6 Luna 的价格下调 80%，将 GPT\-5.6 Terra 的价格下调 20%。
- **Content**: 2026 年 7 月 30 日更新：OpenAI 将 GPT\-5.6 Luna 的价格下调 80%，将 GPT\-5.6 Terra 的价格下调 20%。
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-007
- **Content blocks**: [{"blockId":"P07-evidence","kind":"evidence","hierarchy":1,"text":"2026 年 7 月 30 日更新：OpenAI 将 GPT\\-5.6 Luna 的价格下调 80%，将 GPT\\-5.6 Terra 的价格下调 20%。","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-007"]}]
- **Literal constraints**: 2026 | 7 | 30 | 5.6 | 80% | 20%
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-007

#### Slide 08 / P08 - 对现有业务的潜在影响

- **Assertion**: 随着模型能力不断增强，安全工作仍将继续：新的薄弱点与绕过现有防护的新越狱方式都会被发现，每一代新模型也可能带来新的攻击和滥用途径。
- **Audience move**: 这组已批准证据回答“基于公告内容识别机会与风险；对现有产品与研发的潜在影响点”，据此可基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响。
- **Visual form**: mixed
- **Layout intent**: risk-to-mitigation rows ending in a named owner action
- **Layout**: risk-to-mitigation rows ending in a named owner action
- **Title**: 对现有业务的潜在影响
- **Core message**: 随着模型能力不断增强，安全工作仍将继续：新的薄弱点与绕过现有防护的新越狱方式都会被发现，每一代新模型也可能带来新的攻击和滥用途径。
- **Content**: 随着模型能力不断增强，安全工作仍将继续：新的薄弱点与绕过现有防护的新越狱方式都会被发现，每一代新模型也可能带来新的攻击和滥用途径。
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-073
- **Content blocks**: [{"blockId":"P08-evidence","kind":"evidence","hierarchy":1,"text":"随着模型能力不断增强，安全工作仍将继续：新的薄弱点与绕过现有防护的新越狱方式都会被发现，每一代新模型也可能带来新的攻击和滥用途径。","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-073"]}]
- **Literal constraints**: 随着模型能力不断增强，安全工作仍将继续：新的薄弱点与绕过现有防护的新越狱方式都会被发现，每一代新模型也可能带来新的攻击和滥用途径。
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-073

#### Slide 09 / P09 - 评估建议与后续行动

- **Assertion**: 全面开放前，我们进行了迄今最密集的安全评估，包括大规模红队测试、与外部专家合作开展的严格能力与防护测试，以及约 70 万个 NVIDIA A100 Tensor Core GPU 等效小时的黑盒自动化红队测试。
- **Audience move**: 这组已批准证据回答“建议开展的验证与评估动作；需要持续跟踪的官方后续信息”，据此可基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响。
- **Visual form**: mixed
- **Layout intent**: risk-to-mitigation rows ending in a named owner action
- **Layout**: risk-to-mitigation rows ending in a named owner action
- **Title**: 评估建议与后续行动
- **Core message**: 全面开放前，我们进行了迄今最密集的安全评估，包括大规模红队测试、与外部专家合作开展的严格能力与防护测试，以及约 70 万个 NVIDIA A100 Tensor Core GPU 等效小时的黑盒自动化红队测试。
- **Content**: 全面开放前，我们进行了迄今最密集的安全评估，包括大规模红队测试、与外部专家合作开展的严格能力与防护测试，以及约 70 万个 NVIDIA A100 Tensor Core GPU 等效小时的黑盒自动化红队测试。
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-072
- **Content blocks**: [{"blockId":"P09-evidence","kind":"evidence","hierarchy":1,"text":"全面开放前，我们进行了迄今最密集的安全评估，包括大规模红队测试、与外部专家合作开展的严格能力与防护测试，以及约 70 万个 NVIDIA A100 Tensor Core GPU 等效小时的黑盒自动化红队测试。","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-072"]}]
- **Literal constraints**: 70 | 100
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-072

#### Slide 10 / P10 - 总结与讨论

- **Assertion**: GPT\-5.6 能编写并运行轻量程序，用于协调工具、处理中间结果、监控进度，并随着工作推进选择下一步行动。
- **Audience move**: 这组已批准证据回答“核心结论回顾；开放讨论与下一步安排”，据此可基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响。
- **Visual form**: mixed
- **Layout intent**: conclusion and next action in two asymmetric bands
- **Layout**: conclusion and next action in two asymmetric bands
- **Title**: 总结与讨论
- **Core message**: 结论：GPT\-5.6 能编写并运行轻量程序，用于协调工具、处理中间结果、监控进度，并随着工作推进选择下一步行动。
- **Content**: 结论：GPT\-5.6 能编写并运行轻量程序，用于协调工具、处理中间结果、监控进度，并随着工作推进选择下一步行动。；行动：基于官方公告材料，系统梳理 GPT 5.6 的核心能力、关键更新点与发布时间线，帮助团队快速理解新特性并评估其对现有业务的潜在影响
- **Evidence refs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-018
- **Content blocks**: [{"blockId":"P10-evidence","kind":"evidence","hierarchy":1,"text":"GPT\\-5.6 能编写并运行轻量程序，用于协调工具、处理中间结果、监控进度，并随着工作推进选择下一步行动。","relationship":"supports","evidenceRefs":["01M0KT5WFWQT6Z89JVS6XMXT13:fragment-018"]}]
- **Literal constraints**: 5.6
- **Fact IDs**: 01M0KT5WFWQT6Z89JVS6XMXT13:fragment-018

## X. Speaker Notes Requirements

- **Generation**: disabled
- **Narration preparation**: not requested
