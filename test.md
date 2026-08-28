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
QWEN_MODEL=qwen3.8-flash
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

## 1.1 Qwen3.8 Flash 复测（2026-08-28）

### 运行结论

- 结果：**失败；六页 SVG 作者完成，但原生 PPTX 编译失败，未发布 PPTX**。
- Qwen3.8 Flash 成功完成 Intent、Outline、Strategist、Spec Lock 与 P01–P06；六页均为 `attempt=1`，并留下稳定 SVG SHA-256。
- Final SVG QA 共 6 页：0 页 fully passed、2 页 passed-with-warnings、4 页 failed，累计 13 个 blocking findings、23 个 advisory findings。
- 编译器在 P02 遇到未注册的继承文本属性 `text-transform`，为避免原生 PPTX 静默丢失样式而抛出 `SvgNativeConversionError`；终止代码为 `ENGINE_RENDER_FAILED`。
- 图片调用、视觉复核调用与视觉 Token 均为 0。
- Generation Job：`01M13RYFM9APWXPZ45382HMXDZ`。
- Workflow Run：`01BQ5E9NN8Q71J5A215Q2H5J35`。

### 固定配置与环境

- Runtime 镜像：`instant-ppt-runtime:dev-uncommitted`，镜像 ID `sha256:b3924b32a0caf08ccaee711a74815b379144ae914946925ee3eb95f5c76a19b8`。
- API 镜像：`instant-ppt-api:dev-uncommitted`，镜像 ID `sha256:68feb2fe5bb8cd3b3f729ceb68c093a2f713946e050354a3e93451feb6645517`。
- Provider：`qwen`；模型：`qwen3.8-flash`；`reasoning_effort=medium`；`enable_thinking=true`；`preserve_thinking=false`。
- 官方 API 端点：`token-plan.cn-beijing.maas.aliyuncs.com`。
- Provider 配置版本：`qwen3.8-flash-openai-token-plan-v1`。
- 图片策略：`none`；视觉复核：`off`。
- 模板：`编辑部蓝`，不可变模板版本 `01ARZ3NDEKTSV4RRFFQ69G5FB5`。
- 作者模式：`agent-authoring`；披露：`agent-authored-editable-draft`。

> 环境预检发现 Codex 宿主进程注入的旧代理 URL 与 51 字符代理密钥覆盖了 `.env` 中的官方 Token Plan 配置。第一次 Intent 请求发往官方 URL 时因密钥不匹配返回 401；随后同时以 `.env` 的官方 URL 和 115 字符官方密钥重建容器，并复用同一可恢复草稿开始下列有效调用。401 未产生有效 Provider 用量，但计入上传至终止的总墙钟时间。

### 时间记录（Asia/Shanghai）

- 文档上传开始：2026-08-28 16:45:53.937。
- 来源解析完成：2026-08-28 16:45:58.243；安全扫描与解析约 4.31 秒，状态 `clean/succeeded`，生成 2 个来源工件。
- Intent Provider：16:48:08.727–16:48:15.085，约 6.36 秒。
- Outline Provider：16:48:17.040–16:48:34.257，约 17.22 秒；一次成功生成 6 页，无 repair。
- 六页大纲批准：16:49:24.576；真实生成入队：16:49:25.059；Worker 开始：16:49:25.511。
- Strategist：16:49:28.937–16:53:44.285，约 4 分 15.35 秒。
- Spec Lock：16:53:44.316–16:58:08.644，约 4 分 24.33 秒；首次 `canvas.format` 不合约后完成自修复。
- P01：16:58:09.960–17:05:33.884，约 7 分 23.92 秒；首次首页门禁发现 2 个 blocking finding，修复后通过。
- P02：17:05:33.908–17:10:32.665，约 4 分 58.76 秒。
- P03：17:10:32.688–17:13:41.697，约 3 分 09.01 秒。
- P04：17:13:41.720–17:17:42.973，约 4 分 01.25 秒。
- P05：17:17:43.001–17:19:18.456，约 1 分 35.46 秒。
- P06：17:19:18.479–17:21:59.334，约 2 分 40.86 秒。
- Final SVG QA：约 1.34 秒；SVG finalize：约 1.21 秒；失败的 PPTX 编译：约 1.37 秒。
- 任务终止：2026-08-28 17:22:05.938；真实生成阶段约 32 分 40.88 秒。
- 官方有效 Intent 开始至终止约 33 分 57.21 秒；上传至终止总墙钟约 36 分 12.00 秒。

### Provider 用量

| 阶段 | 输入 Token | 输出 Token | 总 Token | Provider 墙钟/累计回合耗时 | 状态 |
| --- | ---: | ---: | ---: | ---: | --- |
| Intent | 242 | 490 | 732 | 6.36 秒 | succeeded |
| Outline | 7,719 | 1,929 | 9,648 | 17.22 秒 | succeeded；repair 0 |
| Strategist | 193,550 | 18,469 | 212,019 | 255.32 秒 | succeeded |
| Spec Lock | 218,025 | 16,293 | 234,318 | 262.29 秒 | succeeded；含一次合约修复 |
| Executor P01 | 645,321 | 16,359 | 661,680 | 440.90 秒 | succeeded；含一次首页修复 |
| Executor P02 | 370,341 | 12,900 | 383,241 | 298.57 秒 | authored；Final QA failed |
| Executor P03 | 371,716 | 7,621 | 379,337 | 188.79 秒 | authored；Final QA failed |
| Executor P04 | 373,125 | 14,751 | 387,876 | 241.01 秒 | authored；Final QA warning |
| Executor P05 | 374,199 | 3,153 | 377,352 | 95.18 秒 | authored；Final QA failed |
| Executor P06 | 377,295 | 5,102 | 382,397 | 160.58 秒 | authored；Final QA failed |
| 视觉复核 | 0 | 0 | 0 | 0 秒 | off；0 calls |
| **合计** | **2,931,533** | **97,067** | **3,028,600** | **Agent 回合累计 1,942.65 秒** | 规划与六页作者完成，编译失败 |

### 页面与确定性 QA

终止时公开 Job 中六页均为 `running/rendering`、`attempt=1`；这是因为页面作者完成后尚未通过整稿 QA 和编译，未被提升为 `ready`。

| 页面 | 标题 | 作者结果 | attempt | SVG SHA-256 | Final SVG QA 摘要 |
| --- | --- | --- | ---: | --- | --- |
| P01 | GPT-5.6：随雄心扩展的前沿智能 | authored | 1 | `46a5e445af1bb9ce5cb3f0647c9222a551a59f11d17d0fa946a7e3fbc65c86a8` | passed-with-warnings；Roboto Mono 非 PPT-safe；一处文本 bounds 无法验证 |
| P02 | 模型家族与核心定位 | authored | 1 | `4d05adf52ba7b0d161843f3df27381467bb0159ee7435c4f9fbc8d45abcaa685` | failed；`background` inline style、`text-transform`、未声明 32px 字号重复；另有 Inter、根组 bounds、page-role 警告 |
| P03 | 性能基准：显著超越前代与竞品 | authored | 1 | `6591a50571b5faf6a4b32d25f50aba5fdbad6f0a440cf6fa26feb237f9a5b0b3` | failed；3 个图标未预置、未声明 24/48px 字号重复；另有字体、根组、文本 bounds、未分组元素和 page-role 警告 |
| P04 | Ultra 模式：多智能体加速复杂工作 | authored | 1 | `9e0f5d15700b115c778ce8bf3818f63f4c08201a88d43784e3e21dbcc55edf46` | passed-with-warnings；无 blocking finding；静态复核见非 PPT-safe 字体、2 个根组缺 bounds、缺少 root page-role |
| P05 | 同步扩展的安全与防护体系 | authored | 1 | `bc579fb3355b038ea40f21bf153233f9830171b58ac3dea53538fea5211c7640` | failed；2 个图标未预置、未声明 24px 字号重复；另有字体、根组、未分组元素和 page-role 警告 |
| P06 | 可用性与定价策略 | authored | 1 | `532cbd911c5bd6a0a0cb948d0e8772f8c3376de8f94b3cbf803262621d8afdbb` | failed；2 个图标未预置、未声明 24px 字号重复；另有字体、根组、未分组元素、page-role 和 pattern fallback 警告 |

### 发布工件与失败证据

- PPTX：未生成、未发布。
- Package QA：未运行。
- Manifest：未生成。
- Publication version：`v0`。
- 已发布失败证据 ZIP：Artifact `016E0HFP1BQA6J6XQ6NR9T9R55`，991,260 bytes，SHA-256 `296d2cdbe62fd3924f7614abf5c93e2621269b44a352b2897e527f1f58fdf087`。
- 本地留档：`tests/输出PPT记录/qwen3.8-flash-eval-1.1-failure-evidence.zip`。
- 证据包含 `design_spec.md`、Spec Lock 锁定上下文、38 个 Agent turn、24 个工具调用、147 个检查点、完整阶段回执、Final SVG QA 摘要、工作流日志和失败元数据；不包含已发布 PPTX。

### 与 Qwen3.7 Plus 成功基线对比

- Qwen3.8 Flash 的有效规划 Provider 墙钟约 23.57 秒，显著短于 Qwen3.7 Plus 基线约 115.81 秒。
- Qwen3.8 Flash 总用量 3,028,600 tokens，较 Qwen3.7 Plus 成功基线 2,922,581 增加 106,019（约 3.63%）；输出 token 增加约 34.17%。
- Qwen3.8 Flash 真实生成阶段约 32 分 40.88 秒，较 Qwen3.7 Plus 基线约 21 分 20.81 秒增加约 53.10%。
- 本次 Qwen3.8 Flash 产生 13 个 Final SVG blocking findings，并因 P02 `text-transform` 无法编译；Qwen3.7 Plus 基线则带警告成功发布。因此在评测集 1.1 的当前提示、工具合同和后处理规则下，**没有观察到 Qwen3.8 Flash 的端到端能力优于 Qwen3.7 Plus**。规划速度更快，但作者约束遵循、总耗时和可发布性更差。

## ISSUE04 阻断门禁修复后复测（离线评测集 1.1，2026-08-28）

### 结论

- 最终复测提交：`a9d71b9 fix(worker): reject decorated spec lock viewbox`；前置 ISSUE04 主修复提交：`5df47ad fix(worker): enforce blocking SVG quality gates`。
- 使用固定离线评测集 1.1 完成真实浏览器规划、批准、生成、阻断修复、编译、Package QA 与发布闭环，结果为 **succeeded / 6 of 6 ready / publication v1**。
- Final SVG QA：`errors=0`、`blocking=0`、`warnings=2`；整稿门禁为 `passed-with-warnings`。警告均为可追踪的静态检查提示，不阻断发布。
- Package QA：通过；6 页、194 个原生可编辑形状、0 个整页图片、0 个媒体部件、0 个缺失关系目标、0 个外部关系、0 个 finding。
- 本地独立核验：PPTX ZIP `testzip=None`，可由 `python-pptx` 载入；6 页、194 个原生形状、33 个形状组、114 个文本节点、0 个图片形状。

### 固定输入与配置

- Prompt：`根据GPT5.6的官方公告做一份6页的PPT`。
- 输入文档：`tests/OpenAI_GPT-5.6_发布公告_中文版_2026-07-09.docx`。
- 输入 SHA-256：`6c19f59ae1ed7153d8d07585bea8b30af7a88a19e9f21120fb64e7c05b6a5e6a`。
- 语言与页数：`zh-CN`、6 页；输出模式：`native`。
- 模板：`编辑部蓝`，版本 `01ARZ3NDEKTSV4RRFFQ69G5FB5`。
- 图片策略：`none`；视觉复核：`off`；Strategist 授权：开启。
- Provider：官方 Token Plan `token-plan.cn-beijing.maas.aliyuncs.com`；模型：`qwen3.8-flash`。
- Runtime：`instant-ppt-runtime:a9d71b9`；API：`instant-ppt-api:a9d71b9`；Readyz build revision：`a9d71b9`。
- 浏览器文件选择器在本机测试工具中反复超时，因此上传步骤改用同一网站公开的 upload-session → MinIO multipart → complete → parse API；随后所有规划、批准、生成和结果检查均在真实浏览器 UI 中完成。该限制仅属于测试驱动器，不绕过业务状态机或生成流程。

### 首轮复测发现与追加修复

- 在提交 `5df47ad` 上运行时，Job `01M144Q1KCC8X1RGKJZEJ241X9`、Workflow `01F5QX3TPM3Y5TZQ0HMFYZXAGP` 于首页门禁终止，状态 `ENGINE_RENDER_FAILED`，墙钟约 686.43 秒。
- 原因：Spec Lock 将 `canvas.viewBox` 写成 `` `0 0 1280 720` ``。首页 executor 按阶段权限不能修改上游锁文件，而校验器要求四个裸 SVG 数字，导致门禁不可能通过。
- 修复：Spec Lock 提交时要求原始 `viewBox` 字段严格匹配四个裸数字；引号、反引号或 Markdown 装饰均被拒绝并回滚，锁文件不会进入 immutable 状态。
- 新增回归测试覆盖反引号输入、拒绝、回滚和证据记录。相关测试文件 27/27 通过，Ruff 通过。
- 首轮失败证据：`tests/输出PPT记录/issue04-eval-1.1-5df47ad-failure-evidence.zip`，676,227 bytes，SHA-256 `7a0924981431aaa7034830a88dc814a23dc8c241a4c63419a350b7fe3098a843`。

### 最终成功运行

- Source：`01M1463WMXWGK2R225DBAXAZFJ`；Draft：`01M14645QQCN0SJB72SV7Z1E7P`。
- Intent Job：`01M1464HDACH5X0MTDQJ7KY79Y`；Outline Job：`01M1465T053EXQQ761Q670E8R5`。
- Generation Job：`01M14679MGY23AGYVQX7EEFH67`。
- Workflow Run：`0128BMBQ32DRWXN63Y2V910XRX`；Snapshot：`01M14679MAMEQ09YWFGP952A0D`。
- Publication：`01M147MM6Q7074QB6V5XF66B7J`，版本 `v1`。

### 时间记录（Asia/Shanghai）

- 上传开始：2026-08-28 20:39:31.576；解析完成：20:39:41.019，约 9.44 秒。
- Intent：20:39:55.158–20:40:35.440，约 40.28 秒。
- Outline：20:40:36.663–20:40:51.119，约 14.46 秒；一次成功生成 6 页，repair 0。
- Workflow：20:41:25.787–21:06:10.915，约 24 分 45.13 秒。
- 上传开始至 Workflow 终止：约 26 分 39.34 秒。
- Strategist 累计回合耗时约 165.86 秒；Spec Lock 约 151.50 秒。
- 六页首轮作者累计约 596.39 秒；两轮自适应修复累计约 546.26 秒。
- 工作流报告 `renderSeconds=1466`；视觉复核关闭，0 次视觉调用。

### Provider 用量

| 范围 | 输入 Token | 输出 Token | 总 Token |
| --- | ---: | ---: | ---: |
| Intent + Outline | 7,944 | 2,138 | 10,082 |
| Agent 工作流 | 5,421,365 | 98,689 | 5,520,054 |
| **总计** | **5,429,309** | **100,827** | **5,530,136** |

Agent 工作流共 60 个 turn、40 个工具调用、2 个工具失败、`repairCount=15`。图片数量与视觉 Token 均为 0。

### 阻断门禁与自适应修复证据

- Spec Lock 首次提交被拒绝一次；最终锁文件写入严格裸值 `- viewBox: 0 0 1280 720`，证明新增校验在首页执行前生效。
- P01 首次门禁发现 1 个 blocking 类别（两个根 `<g>` 缺少 bounds）；页面内修复后，以当前 SVG hash 重新检查并通过。
- 首次整稿检查发现 P03/P04/P05/P06 共 26 个 blocking finding。
- Repair batch r1 依次修复四页，批次完成后仅执行一次整稿复查；错误页由 4 降为 1、blocking 由 26 降为 2。
- 自适应 r2 仅修复仍失败的 P06；最终整稿复查为 0 error、0 blocking，未受固定四轮上限约束。
- 最终回执：first-page gate `passed-with-warnings`；final SVG gate `passed-with-warnings`；final SVG content、PPTX content、Step 7 finalize/export 与 publication 均为 `passed`。

### 页面结果

| 页面 | 标题 | 状态 | attempt | 最终 SVG SHA-256 |
| --- | --- | --- | ---: | --- |
| P01 | GPT-5.6：随雄心扩展的前沿智能 | ready | 1 | `706683f40ef344318f7736f8cc4215dcca339ffbce3ea050a7b3df45211dcc15` |
| P02 | 模型家族概览：Sol, Terra, Luna | ready | 1 | `d21e7811b474a6fb896ddfffc471078c55b134cc1017b091c68e6f64412a5112` |
| P03 | 性能突破：每美元更强性能 | ready | 1 | `515d31f207aa790f336eec4c0b1a53417d60ec3123593afd461bde0a7078dc88` |
| P04 | 应用飞跃：编码、设计与知识工作 | ready | 1 | `33fc46e6ce2fe533e0a9ffbef62faab7892a7e9cec990b01eb6036955423b091` |
| P05 | 安全增强与商业化定价 | ready | 1 | `87cc2ceffcc4db3d9d37baccda009b63336683bd1fc93ac9c3cd69f2ec4bc14a` |
| P06 | 总结与展望 | ready | 1 | `84b48dd2f471e5a6fc0b09dceeff9996ccca51fe8793d43e7bd4b29fd95fca35` |

Final SVG QA 的两项非阻断警告：P01 有一处不支持文本几何而无法验证根 viewBox bounds；P02 的参考 SVG 带有根组 bounds、未分组装饰和 page-role 提示。P03–P06 修复后无 error。

### 发布工件

- PPTX：`tests/输出PPT记录/issue04-eval-1.1-a9d71b9.pptx`，29,816 bytes，SHA-256 `61d850042854359692cbaf85124c166cff4ecb1f263e87694c7dc0ab340ec0dd`。
- Final SVG QA：`tests/输出PPT记录/issue04-eval-1.1-a9d71b9-final-svg-qa.json`。
- QA Report：`tests/输出PPT记录/issue04-eval-1.1-a9d71b9-qa-report.json`。
- Package QA：`tests/输出PPT记录/issue04-eval-1.1-a9d71b9-package-qa.json`。
- Workflow Result：`tests/输出PPT记录/issue04-eval-1.1-a9d71b9-workflow-result.json`。
- Spec Lock 与 Design Spec：`tests/输出PPT记录/issue04-eval-1.1-a9d71b9-spec-lock.md`、`tests/输出PPT记录/issue04-eval-1.1-a9d71b9-design-spec.md`。

## ISSUE04 稳定性追加生成测试（2 次，2026-08-28）

### 测试边界

- 提交与镜像保持为 `a9d71b9`，Readyz build revision、Runtime 与 API 均为 `a9d71b9`。
- 复用离线评测集 1.1 已批准的同一 Source、Intent、6 页 Outline、模板 `编辑部蓝` 与 Strategist 授权，避免上传和规划随机性干扰生成稳定性判断。
- 两次 Generation Job 严格串行；均为 `native`、`agent-authoring`、图片 `none`、视觉复核 `off`、Provider `qwen/qwen3.8-flash`。
- 本节中的“成功率”只统计本次追加的 2 个独立 Generation Job；上一节最终成功运行作为固定提交的既有基线单列比较。

### 结果总览

| 运行 | Generation Job | Workflow Run | 结果 | 页面 | Workflow 墙钟 | Publication |
| --- | --- | --- | --- | ---: | ---: | --- |
| 追加运行 1 | `01M148DMMDECGQFYZ73PNGHKH7` | `012CX9JN6071KFFNCMAEAM72QN` | succeeded | 6/6 ready | 2,585.91 秒（43:05.91） | v1 |
| 追加运行 2 | `01M14AXPF27K34C0MJ0973GEDW` | `01FBJ5FKEEEBFNM3S3J6RN521P` | failed | 0/6 | 428.28 秒（07:08.28） | v0 |

- 本次追加成功率：**1/2 = 50%**。
- 固定提交 `a9d71b9` 连同上一节成功基线共运行 3 次：**2/3 = 66.67%**。
- 两个能够进入完整作者/门禁链路的运行均成功发布；失败运行在 Strategist 的 Provider 连接阶段终止，未进入 Spec Lock、P01 或 Final SVG QA。

### 追加运行 1：成功但存在明显长尾

- Workflow：2026-08-28 21:19:50.864–22:02:56.771（Asia/Shanghai），约 43 分 05.91 秒；API 最终发布事件于约 22:03:07 可见。
- 任务尝试：1；6 页均 `ready`、页面 attempt 1；Manifest SHA-256 `e8216d2688418b47937768689052b155d3548f80742fcd28e5e5aaf44d3811ac`。
- Agent：88 turns、53 tool calls、1 tool failure、`repairCount=30`。
- Token：输入 7,293,957、输出 163,172、合计 **7,457,129**；`renderSeconds=2561`；图片与视觉模型调用均为 0。
- 自适应整稿修复：r1 修复 P02–P06；r2 修复 P02/P04/P05；r3、r4 继续仅修复 P05，最终通过。说明失败页收敛机制可以超过固定四页批次持续工作，但也产生显著长尾成本。
- Final SVG QA：`errors=0`、`blocking=0`、`warnings=2`。警告位于 P02 页脚 3% 水平 bounds overflow，以及 P05 一处不支持文本几何的 viewBox bounds 可验证性提示。
- Package QA：通过；6 页、166 个可编辑文本形状、60 个原生可编辑形状、0 个整页图片、0 个媒体部件、0 个 missing target/external relationship/finding。
- 本地独立 PPTX 核验：ZIP `testzip=None`，6 页、166 个原生 `<p:sp>`、35 个组、107 个文本节点、0 个 `<p:pic>`。
- 相比上一节成功基线（约 24:45.13、5,530,136 tokens、repair 15），本轮成功墙钟增加约 74%，Token 增加约 34.85%，repair 翻倍。功能结果稳定，但耗时与成本波动显著。

产物：

- `tests/输出PPT记录/issue04-stability-run1-a9d71b9.pptx`，29,743 bytes，SHA-256 `6b8a94a883d077b59a6b38ecfe64793d747d09eac87fe2b0479fb8446f267a30`。
- `tests/输出PPT记录/issue04-stability-run1-a9d71b9-final-svg-qa.json`。
- `tests/输出PPT记录/issue04-stability-run1-a9d71b9-package-qa.json`。
- `tests/输出PPT记录/issue04-stability-run1-a9d71b9-qa-report.json`。
- `tests/输出PPT记录/issue04-stability-run1-a9d71b9-workflow-result.json`。

### 追加运行 2：Provider 连接失败

- Workflow：2026-08-28 22:03:33.930–22:10:42.211（Asia/Shanghai），约 7 分 08.28 秒。
- 状态：`failed / attribution_guard / ENGINE_RENDER_FAILED`；0/6；publication v0；无 PPTX、Final SVG QA 或 Package QA。
- 精确错误：`Main Presentation Agent Strategist failed: qwen request failed: status=transport_error failure_kind=ConnectError`。
- 端点：官方 `token-plan.cn-beijing.maas.aliyuncs.com`；模型 `qwen3.8-flash`。
- 失败前证据包含 3 个 Strategist turn（2 个 `tool-observed`、1 个 `provider-failed`）与 2 个工具调用；Provider 未返回可计费 token，因此 Workflow usage 为空。
- 错误发生在 Spec Lock 之前，不能归因于 ISSUE04 SVG 阻断门禁或 viewBox 修复回归。
- 失败证据：Artifact `016JRJAM25540P2EMDS7PE4VAR`，21 个成员；本地 `tests/输出PPT记录/issue04-stability-run2-a9d71b9-failure-evidence.zip`，108,264 bytes，SHA-256 `949dae7f0c0098765a278df6dbb46922c10720d3316bb5c85842ad4e73b36a4b`。

### 稳定性判断

- **ISSUE04 功能修复保持有效**：两个进入 Spec Lock/P01/Final SVG 链路的 `a9d71b9` 运行均达到 0 blocking 并成功发布，没有再次出现带反引号 `viewBox` 或固定修复轮数提前终止。
- **项目端到端稳定性仍不达标**：追加测试只有 50% 成功率；固定提交三次总成功率为 66.67%。本次失败根因是外部 Qwen 连接错误，当前工作流在约 7 分钟等待后直接任务级失败，没有 Provider 连接重试或可恢复状态。
- **性能稳定性偏弱**：两次成功生成的 Workflow 墙钟从约 24:45 增至 43:06，Token 从约 5.53M 增至 7.46M；repair 从 15 增至 30。建议后续单独建立 Provider 连接重试/退避测试，并为 Agent 回合、总 Token 与 repair 数设置可观测的稳定性阈值。

### 测试 2 网络恢复后重跑（2026-08-28）

- 重跑前验证 `token-plan.cn-beijing.maas.aliyuncs.com` 域名解析成功、TCP 443 可连接；本地 API/Worker Readyz 仍为 `a9d71b9`。
- 新 Generation Job：`01M14BK7G3HJ1EF23W25J47TRM`；Workflow Run：`01PM3VV9617JTRGZYJA8HKK9KA`。
- Workflow：2026-08-28 22:15:19.716–22:49:30.820（Asia/Shanghai），约 2,051.10 秒（34:11.10）。
- 结果：`succeeded`、6/6 ready、页面 attempt 1、publication v1；Manifest SHA-256 `19c09bfaf9125960eeb8cd5262c78d59a5118a59cc9a94f35401e609762ad797`。
- Agent：73 turns、48 tool calls、2 tool failures、`repairCount=21`。
- Token：输入 7,151,692、输出 132,389、合计 **7,284,081**；`renderSeconds=2030`；图片和视觉调用均为 0。
- 自适应修复：r1 修复 P01/P02/P03/P05/P06，r2、r3 仅继续修复 P06，最终收敛。
- Final SVG QA：`errors=0`、`blocking=0`、`warnings=5`。
- Package QA：通过；6 页、200 个可编辑文本形状、80 个原生可编辑形状、0 个整页图片、0 个 finding。
- 本地 PPTX 独立核验：ZIP `testzip=None`，6 页、200 个 `<p:sp>`、37 个组、131 个文本节点、0 个 `<p:pic>`。

重跑产物：

- `tests/输出PPT记录/issue04-stability-run2-rerun-a9d71b9.pptx`，31,360 bytes，SHA-256 `b1d89ea94b6cfafde5aa31321ac43a06a03148b07471100b98e308848d6fc5de`。
- `tests/输出PPT记录/issue04-stability-run2-rerun-a9d71b9-final-svg-qa.json`。
- `tests/输出PPT记录/issue04-stability-run2-rerun-a9d71b9-package-qa.json`。
- `tests/输出PPT记录/issue04-stability-run2-rerun-a9d71b9-qa-report.json`。
- `tests/输出PPT记录/issue04-stability-run2-rerun-a9d71b9-workflow-result.json`。

更新后的稳定性判断：

- 原测试 2 的 `ConnectError` 在本地网络恢复后未复现，重跑完整通过，因此该失败归类为**已知本地网络中断样本**，不作为 ISSUE04 功能失败。
- 按用户要求的两个有效追加生成样本（追加运行 1 + 测试 2 重跑）统计，成功率为 **2/2 = 100%**。
- 固定提交 `a9d71b9` 的三个网络有效完整生成样本（上一节成功基线 + 两个追加有效样本）为 **3/3 = 100%**，均达到 0 blocking 并成功发布。
- 若不剔除已确认的本地网络中断，`a9d71b9` 总 Job 尝试为 3/4 成功，即 75%。
- 功能稳定性结论由“整体不达标”修正为：**ISSUE04 生成与阻断门禁链路在三个网络有效样本中稳定通过；性能成本仍有明显波动**。三个成功 Workflow 耗时约 24:45、43:06、34:11，Token 约 5.53M、7.46M、7.28M。
