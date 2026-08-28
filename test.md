# 离线评测集 1.1

## 基本信息

- 评测集名称：GPT-5.6 官方公告六页演示生成
- 评测集版本：1.1
- 数据类型：固定文档语料 + 固定提示词
- 首次记录日期：2026-08-28
- 目标：通过本项目网站生成一份 6 页、简体中文、原生可编辑的 PPTX。
- 安全边界：文档内容仅作为生成素材，不得把文档内文字视为系统指令或用户操作授权。

## 提示词

```text
根据GPT5.6的官方公告做一份6页的PPT
```

## 输入文档

- 文件：`tests/OpenAI_GPT-5.6_发布公告_中文版_2026-07-09.docx`
- 格式：DOCX
- 上传方式：作为主文档上传并等待安全扫描、解析完成后再生成大纲。

## API 与生成配置

```dotenv
PLANNING_BACKEND=qwen
TEXT_PROVIDER=qwen
QWEN_BASE_URL=https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.7-plus
QWEN_REASONING_EFFORT=medium
QWEN_ENABLE_THINKING=true
QWEN_PRESERVE_THINKING=false
QWEN_STREAMING=true
QWEN_API_KEY=<从本地 .env 或 Secret Manager 注入，不得写入评测集>

# 未在 .env 显式设置时使用 Compose 默认值 agent-authoring
PRESENTATION_AUTHORING_MODE=agent-authoring

IMAGE_GENERATION_ENABLED=false
IMAGE_MAX_PER_DECK=0
```

任务级配置：

- 模式：`native`
- 作者模式：`agent-authoring`
- 目标页数：`6`
- 语言：`zh-CN`
- 图片策略：`none`
- 视觉复核级别：`off`
- 模板：`编辑部蓝`（使用测试时 API 返回的当前不可变模板版本）
- 设计锁定：授权 Strategist 根据已批准的 Intent、Outline 与来源生成并锁定 `design_spec.md` / `spec_lock.md`。

> `PRESENTATION_VISUAL_REVIEW_REQUIRED=true` 是当前环境中的旧能力开关；本评测以生成快照中的任务级 `visualReviewLevel=off` 为准，不应产生视觉模型调用。

## 后续测试记录要求

每次运行至少记录：

1. 文档上传开始时间、来源解析完成时间和任务终止时间。
2. 总耗时，以及规划、Strategist、逐页作者、编译和发布阶段耗时。
3. 输入 token、输出 token、总 token；视觉复核 token 应为 0。
4. 6 个页面的状态、attempt、SVG 哈希及确定性 QA 警告。
5. PPTX、QA 报告和 Manifest 是否成功发布。
6. 实际 Provider、模型和官方 API 端点域名；不得使用第三方兼容代理。

## 1.1 基线观察

2026-08-28 首次运行生成到 4/6 页后，在 P05 因确定性标题契约错误达到工具策略修复上限而终止，未发布 PPTX。该现象用于后续回归验证：确定性错误应被披露为警告，不应在已有可继续生成或可导出的结果时直接把任务判为失败。

## 1.1 修改后回归记录（2026-08-28，提交 `87e18c0`）

### 运行结论

- 结果：**失败，未达到基线验证目标**。
- 修改后的链路没有再现 P05 标题契约错误，因为任务在 0/6 页、Strategist 开始前即终止。
- 终止代码：`ENGINE_INVALID_REQUEST`。
- 工作流阶段：`attribution_guard`（API 映射阶段）；直接根因为运行时缺失 `/app/vendor/ppt-master.vendor.json`。
- 复现信息：调用 `instant_ppt_worker.ppt_master_references.spec_lock_contract_payload()` 时抛出 `FileNotFoundError`。Worker 镜像包含 `/app/vendor/ppt-master/`，但 Dockerfile 未复制相邻的 `vendor/ppt-master.vendor.json`。

### 固定配置与环境

- Runtime 镜像：`instant-ppt-runtime:87e18c0`，镜像 revision `87e18c0`。
- API 镜像：`instant-ppt-api:87e18c0`，镜像 revision `87e18c0`。
- Provider：`qwen`。
- 模型：`qwen3.7-plus`。
- 成功规划调用端点：`token-plan.cn-beijing.maas.aliyuncs.com`。
- 图片策略：`none`；图片调用 0。
- 视觉复核：`off`；视觉模型调用和视觉 Token 均为 0。
- 模板：`编辑部蓝`，不可变模板版本尾号 `9G5FB5`。
- 作者模式：`agent-authoring`。

> 配置预检发现宿主进程已有旧 `QWEN_*` 环境变量，第一次意图请求错误发往 `cf.api.fan` 并返回 401。随后显式以本文件和 `.env` 的官方端点配置重建容器，并从可恢复草稿重新开始有效评测。该次 401 不计入下列有效 Provider 用量，但计入端到端墙钟时间并作为环境隔离问题保留。

### 时间记录（Asia/Shanghai）

- 文档上传开始：2026-08-28 14:24:03.723。
- 来源解析完成：2026-08-28 14:24:06.459；安全处理与解析约 2.74 秒，生成 2 个解析工件。
- 官方 Qwen 配置下恢复规划：2026-08-28 14:27:11.020。
- Intent Provider：14:27:11.615–14:27:37.225，约 25.61 秒。
- Outline Provider：14:27:38.081–14:28:25.735，约 47.65 秒。
- 六页大纲确认：2026-08-28 14:28:53.491。
- 真实生成入队：2026-08-28 14:29:05.521；Worker 开始：14:29:05.922。
- 任务终止：2026-08-28 14:29:41.147；生成阶段约 35.63 秒。
- 有效规划恢复至终止约 2 分 30.13 秒；上传至终止总墙钟约 5 分 37.42 秒（包含错误端点识别和环境重建时间）。

### Provider 用量

| 阶段 | 输入 Token | 输出 Token | 总 Token | 状态 |
| --- | ---: | ---: | ---: | --- |
| Intent | 246 | 1,455 | 1,701 | succeeded |
| Outline | 7,747 | 2,746 | 10,493 | succeeded |
| Strategist / Executor | 0 | 0 | 0 | 未开始 Provider 调用 |
| 视觉复核 | 0 | 0 | 0 | off |
| **合计** | **7,993** | **4,201** | **12,194** | 规划成功，生成失败 |

### 页面与发布状态

| 页面 | 标题 | 状态 | attempt | SVG SHA-256 | 确定性 QA 警告 |
| --- | --- | --- | ---: | --- | --- |
| P01 | GPT-5.6 官方公告解读 | pending | 0 | 无 | 未运行 |
| P02 | GPT-5.6 模型家族概览 | pending | 0 | 无 | 未运行 |
| P03 | 性能与效率突破 | pending | 0 | 无 | 未运行 |
| P04 | 安全与防护体系 | pending | 0 | 无 | 未运行 |
| P05 | 可用性与定价 | pending | 0 | 无 | 未运行 |
| P06 | 总结与展望 | pending | 0 | 无 | 未运行 |

- PPTX：未生成、未发布。
- QA 报告：未生成。
- Manifest：未生成。
- Publication version：`v0`。
- Generation Job：`01M13GXHBD4E5C68CTWK1XG76H`。
- Workflow Run：`01799C52Q516WDY393Y332SBR3`。

### 后续修复要求

1. 将 `vendor/ppt-master.vendor.json` 纳入 Worker runtime 镜像，或把版本/提交/树哈希以同等不可变、可验证的运行时资源提供给 `ppt_master_references.py`。
2. 增加容器级 smoke test：在构建镜像内调用 `spec_lock_contract_payload()` 和 `executor_reference_manifest()`，防止仅宿主机测试通过而镜像缺少清单。
3. 修复后重新执行本评测，验收任务必须越过 Strategist/Spec Lock、完成 P01–P06、导出 PPTX，并确认视觉 Provider 调用为 0。

## 1.1 清单修复后复测（2026-08-28）

### 运行结论

- 结果：**通过核心回归目标，带 QA 警告发布**。
- 任务已越过 Strategist、`design_spec`、`spec_lock` 与 P01 首页门禁，P01–P06 均为 `ready`、`attempt=1`。
- 已发布原生可编辑 PPTX、6 份页面 SVG、`design_spec`、`spec_lock`、final SVG QA、package QA、Manifest 与 Workflow Result，Publication version 为 `v1`。
- 图片调用、视觉复核调用与视觉 Token 均为 0。
- 修复点已在最终 Worker 镜像中验证：`spec_lock_contract_payload()` 返回 `instant-ppt.spec-lock-contract.v1`，Executor 引用清单包含 5 份文件，Manifest SHA-256 为 `fae839c324aa3a3f265c530cefcbe865851a566ca4dbb448a0100ce64ac6a206`。

### 固定配置与环境

- 基线 revision：`87e18c09ff6a3160b4988a1dd5b39bad8ea9fd56`；复测镜像额外包含本次 Worker 清单打包修复。
- Runtime 镜像 ID：`sha256:1f2d4bab1327fadc30e204a9a0248cde2ecdc682c68f1490495ee5bdaffc4408`。
- Provider：`qwen`；模型：`qwen3.7-plus`。
- 官方 API 端点：`token-plan.cn-beijing.maas.aliyuncs.com`。
- 图片策略：`none`；视觉复核：`off`。
- 模板：`编辑部蓝`，不可变模板版本尾号 `9G5FB5`。
- 作者模式：`agent-authoring`；披露：`agent-authored-editable-draft`。
- Generation Job：`01M13JEJ8FPA4A5XBC9XAE17VW`。
- Workflow Run：`01CG20NHM0A2EHRTYFVDPF4T6Q`。

### 时间记录（Asia/Shanghai）

- 文档上传开始：2026-08-28 14:52:31.675。
- 来源解析完成：2026-08-28 14:52:35.052；约 3.38 秒，生成 2 个解析工件。
- 发起规划：2026-08-28 14:52:50.603。
- Intent Provider：14:52:51.566–14:53:19.723，约 28.16 秒。
- Outline Provider：14:53:21.357–14:54:48.238，约 86.88 秒。
- 六页大纲确认：2026-08-28 14:55:42.187。
- 真实生成入队：2026-08-28 14:55:51.792；Worker 接收：14:55:52.304。
- Strategist `design_spec` Provider 累计约 195.36 秒；`spec_lock` Provider 累计约 75.92 秒。
- Executor Provider 累计：P01 112.82 秒、P02 219.49 秒、P03 171.07 秒、P04 185.72 秒、P05 155.27 秒、P06 148.15 秒。
- 最后一个 Agent turn 完成：2026-08-28 15:17:06.380；随后编译、包检和发布约 6.23 秒。
- 工作流终止：2026-08-28 15:17:12.605；真实生成阶段约 21 分 20.81 秒。
- 上传至终止总墙钟约 24 分 40.93 秒。

### Provider 用量

| 阶段 | 输入 Token | 输出 Token | 总 Token | 状态 |
| --- | ---: | ---: | ---: | --- |
| Intent | 242 | 1,579 | 1,821 | succeeded |
| Outline | 8,584 | 1,949 | 10,533 | succeeded（repair 1） |
| Strategist + Spec Lock | 573,715 | 14,530 | 588,245 | succeeded |
| Executor P01–P06 | 2,267,695 | 54,287 | 2,321,982 | succeeded |
| 视觉复核 | 0 | 0 | 0 | off；0 calls |
| **合计** | **2,850,236** | **72,345** | **2,922,581** | 核心链路成功 |

### 页面与确定性 QA

所有页面的 `contentGate` 均为 `passed`，整稿门禁均披露为 `passed-with-warnings`。

| 页面 | 标题 | 状态 | attempt | 发布 SVG SHA-256 | 确定性 QA 警告摘要 |
| --- | --- | --- | ---: | --- | --- |
| P01 | GPT-5.6 官方公告解读 | ready | 1 | `1f70933661d9ecb3f8e89b1d2a7d464e611701d43a73eedeb5af4aae7fb8a872` | 未声明 14px 字号重复；Inter 非 PPT-safe；1 个未分组根装饰元素 |
| P02 | 性能与效率：每美元性能大幅提升 | ready | 1 | `56bb981fb69233adb2252998a87529e605e8c2a1b222eeddff68997844757c94` | 根组缺少 `data-pptx-bounds`；未声明 14px 字号重复；Inter 非 PPT-safe |
| P03 | 编码与智能体能力：刷新行业纪录 | ready | 1 | `baa283e8325cebf7983b253db070875a291139338df6f9161a5d8ec8e68f9876` | page-role 位置/根属性、根组 bounds、未声明 14/32px 字号、Inter 字体警告 |
| P04 | 知识工作与设计能力：端到端交付 | ready | 1 | `c36bfab0478abe1f3fe068d0eed626ddb8b65e8e3cc222f5ed6cac1d6c744e1e` | 5 个根组缺 bounds；8 个图标未预置；未声明 12/14px 字号；Inter 字体警告 |
| P05 | 安全与保障：分层防护与可信访问 | ready | 1 | `2e90b1bf0882f4772c942333e25cee9ee27e59731be2337f124d1bc80a4d5cc4` | 2 个图标未预置；根组/根属性与未分组元素警告；Inter 字体警告；package QA 披露标题可编辑文本未匹配 |
| P06 | 可用性与定价：三大模型层级全面开放 | ready | 1 | `c100e94a8c19ec8954b2748594e1f8c231c96bc8dfa77085ae0d9fb3fe456ce8` | 根组缺 bounds；rocket 图标未预置；未声明 28/32px 字号；Inter 字体警告 |

### 发布工件与可编辑性检查

- PPTX：已发布，31,882 bytes，SHA-256 `002fe83263f5672d0c2e048c6c2613d141a2cc170c3711612637249bed7bcae2`。
- Manifest：已发布，SHA-256 `f1285700ec76b953e585cb2a0c1548079686c10cf66cc7bb1180a78583d2cdc1`。
- Final SVG QA：已发布，状态 `passed-with-warnings`。
- Package QA：已发布；6 页、188 个可编辑文本形状、81 个可编辑原生形状、0 个全页图片、无缺失关系目标、无外部关系。报告含 1 条 `PPTX_EDITABLE_TEXT_MISSING`（P05 标题），因此 `passed=false`，但按当前发布策略作为警告披露且未阻止 PPTX 发布。
- Content QA：Design Spec 与 Final SVG 均通过；Compiled PPTX 内容表示因未验证而披露 `CONTENT_REPRESENTATION_UNVERIFIED`，Publication 为 `passed-with-warnings`。
- 本地留档：`tests/输出PPT记录/issue04-eval-1.1.pptx`，哈希与已发布 PPTX 一致。

### 回归判定

1. 缺失 `/app/vendor/ppt-master.vendor.json` 的镜像问题已修复，构建期与容器级 smoke 均能加载 Spec Lock 合同和 Executor 引用清单。
2. 验收任务已完成 Strategist/Spec Lock、P01–P06、PPTX 编译与不可变发布，视觉 Provider 调用为 0，达到本次修复的核心验收目标。
3. QA 中仍存在字体、根组 bounds、未预置图标和 P05 可编辑标题匹配等警告；它们未再把已有可导出结果判为任务失败，应作为后续质量优化项单独处理。
