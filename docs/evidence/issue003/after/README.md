# ISSUE-003 最终同输入 Before / After 结论

## 结论

人工偏好结论：**After 明显优于 Before**。本结论只针对冻结的同一批准快照、同一 10 页大纲与同一来源字节；`reference-ppt-master.pptx` 仅作为非严格视觉参考，不参与同输入胜负判定。

After 保留 10 个稳定 `slideId` / `outlineSlideId`，由真实 Main Presentation Agent turn/tool/reviewer 运行时生成。当前环境没有 `MOONSHOT_API_KEY`，因此文本 Provider 明确使用可复现的本地 `fake-agent@v1`；这不是“已接入线上 Kimi”的证据。候选仍是 `agent-authoring`，不是模板回退，包含 38 个 Agent turn、26 次工具调用、首轮视觉审阅通过且 blocking 为 0。

## 冻结权威

- 批准快照：`01M0KZ2JRMZHFH5CG2RQTBRDC3`
- 快照 SHA-256：`fdb0cd6f714baf0e5af838617de3519f1295e8565e764c6f61a678544f4d4ffe`
- 来源 SHA-256：`811333418f1cf5b69330c0812781a82fa89467a403049c51e211653656ee04cf`
- Before SHA-256：`4fa9901f9c4a38c2d41fd98e60cd65c56999caa4050be4c8f37cb73aeba4fe6e`
- After SHA-256：`57ea3e5414779b1e0a81da78ac403bd1a80bed3c18fe92056b253c27396cbf75`

## 用户视角对比

| 维度 | Before | After | 判断 |
| --- | --- | --- | --- |
| 内容完整性 | 多页只复述单句，发布、能力、定价、影响之间缺少结构 | 形成概览、3 节点时间线、能力、原生图表、对比、定价、风险/行动、总结闭环 | Better |
| 结论清晰度 | 标题经常直接截取来源或显示元数据 | 使用批准大纲短标题，正文承载来源事实，结尾同时给出结论与行动 | Better |
| 信息层级 | 81 个递归形状、1,168 个可见字符，页面语义角色弱 | 90 个递归形状、1,421 个可见字符、7 种语义角色 | Better |
| 密度与留白 | 留白大但信息不足 | 信息量提升 21.7%，仍保留清晰标题区、证据区和来源页脚 | Better |
| 布局适配 | 可打开但叙事与页面角色不匹配 | 时间线、双栏对比/行动卡、原生柱状图按角色编排；视觉门禁 0 blocking | Better |
| 一致性 | 模板页之间一致，但内容质量不稳定 | 统一栅格、色彩、字号、来源披露；PowerPoint/WPS 画面接近 | Better |
| 可编辑性 | 可编辑 | 79 个可编辑文本形状，23/23 预期文本匹配，32 个可编辑原生形状，0 张整页截图 | Better |

## 兼容性与质量证据

- PowerPoint：10/10 页无修复打开并渲染。
- WPS：10/10 页无修复打开并渲染。
- 两应用逐页归一化像素差最大值：`0.026957`。
- 原生图表：1；整页图片：0；PPTX package QA：passed。
- 使用量：输入 380,199 tokens，输出 5,973 tokens，图片 0；本地确定性 Provider 的成本记为 0，不代表线上模型价格。

## 已知限制

- 该证据证明 Agent 编排、工具调用、页面写入、视觉审阅、PPTX 编译和 Office 兼容链路；它不证明线上 Kimi 的视觉偏好或真实费用。
- 当前样例使用无图片策略，视觉丰富度来自原生文本、形状和图表；后续真实 Provider / 图片策略仍需各自 canary。
- 参考 deck 与冻结快照并非同一批准输入，因此只做方向性参考，不用于严格 A/B。

机器可读明细见 `candidate-evidence.json`、`after-comparison-metrics.json`、`office-powerpoint.json`、`office-wps.json` 与候选项目的 `validation/` 证据。
