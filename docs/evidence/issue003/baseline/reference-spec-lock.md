<!-- ppt-master-schema: spec-lock/v1 -->
# Execution Lock

## canvas
- viewBox: 0 0 1280 720
- format: PPT 16:9

## communication
- primary_language: zh-CN
- audience: 关注前沿模型能力与落地效率的技术负责人、开发者、产品负责人和知识工作团队
- objective: 用清晰证据解释 GPT-5.6 的能力、效率与扩展机制，使听众能按任务难度、时延和预算选择模型与推理强度并形成试用判断。
- core_message: GPT-5.6 以更高的每 token 智能和每美元性能覆盖日常到最艰巨工作，并通过 Sol、Terra、Luna 与 max、ultra 提供可伸缩的能力梯度。
- consumption_mode: balanced

## mode
- mode: custom
- mode_references: pyramid
- mode_behavior: 以 pyramid 为唯一叙事基底，开场先给出“更高智能、更低总成本、按需扩展”的结论；随后用能力、效率、工具、安全与可用性五组证据逐层支撑，并以模型选择矩阵收束到试用判断。

## visual_style
- visual_style: custom
- visual_style_references: dark-tech, data-journalism
- visual_style_behavior: 由 dark-tech 提供深色负空间、精密节点与克制光感，由 data-journalism 提供严谨列网、数据主轴、细规则和来源层级；页面避免重复卡片墙，让大数字、模型轨道和比较图成为主视觉。

## colors
- background: #07111F
- secondary_bg: #0D1B2A
- primary: #49B9FF
- accent: #B7F34A
- secondary_accent: #7A8FFF
- body_text: #EAF2FF
- surface: #122439
- grid: #294056
- muted_text: #A7B8CA

## typography
- font_family: Microsoft YaHei, Segoe UI, sans-serif
- title_family: Microsoft YaHei, Segoe UI, sans-serif
- body_family: Microsoft YaHei, Segoe UI, sans-serif
- data_family: Consolas, Microsoft YaHei, monospace
- code_family: Consolas, Microsoft YaHei, monospace
- body: 24
- title: 42
- subtitle: 32
- annotation: 18
- data_hero: 72
- footnote: 15

## icons
- library: tabler-outline
- stroke_width: 2
- inventory: tabler-outline/brain, tabler-outline/code-ai, tabler-outline/shield-check, tabler-outline/microscope, tabler-outline/currency-dollar, tabler-outline/chart-bar, tabler-outline/hierarchy-3, tabler-outline/rocket, tabler-outline/cpu, tabler-outline/network

## page_rhythm
- P01: anchor
- P02: dense
- P03: dense
- P04: anchor
- P05: dense
- P06: breathing
- P07: dense
- P08: dense
- P09: breathing
- P10: dense
- P11: dense
- P12: anchor

## pptx_structure
- mode: flat

## forbidden
- `mask`, `<style>`, `class`, external CSS, `<foreignObject>`, `textPath`, `@font-face`, `<animate*>`, `<set>`, `<script>` / event attributes, `<iframe>`
- HTML named entities in text; write typography as raw Unicode and escape XML reserved characters
