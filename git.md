# Git 操作记录

本文档用于集中记录本项目的 Git 操作、提交历史和 GitHub 同步情况，方便追踪“做了什么、为什么做、结果如何”。

## 记录约定

- 每次执行会改变仓库状态的操作后，在“操作日志”顶部追加一条记录。
- 重要的只读检查也应记录，例如提交历史审计、差异检查和远端状态检查。
- 每条记录应包含时间、操作者、目的、命令、结果和相关提交哈希。
- 命令中的令牌、密码、私钥、Cookie、`.env` 内容等敏感信息不得写入本文档。
- 未实际执行的命令必须标记为“计划”，不得写成已经完成。
- GitHub 仓库地址确定后，在“远端与 GitHub”一节更新。

## 当前仓库基线

截至 2026-08-23：

| 项目 | 状态 |
| --- | --- |
| 当前分支 | `codex/issue-003-presentation-agent` |
| 已验证并部署的代码提交 | `bdd1751` (`fix(runtime): complete fallback disclosure closure`) |
| 截至该代码提交的提交总数 | 29 |
| 历史结构 | 单一直线历史，无合并提交 |
| Git 远端 | 未配置 |
| Git 标签 | 无 |
| 工作区 | ISSUE-003 阶段 0–F、最终质量、生产用户旅程、fallback 修复和发布收口均已分类提交；仅保留用户的无关 Markdown 空行修改和未跟踪工作目录 |
| GitHub 状态 | 尚未关联或上传 |

注意：首次提交包含 13,213 个文件和约 40 万行新增内容。上传 GitHub 前应检查仓库体积、敏感信息、依赖目录和生成文件，避免把不适合公开或版本管理的内容推送出去。

## 已有提交历史

| 时间（Asia/Shanghai） | 提交 | 类型 | 内容 |
| --- | --- | --- | --- |
| 2026-08-16 10:52 | `5e930bf` | `chore` | 建立 G00–G01 验证基线 |
| 2026-08-16 11:42 | `90471f9` | `feat` | 完成 G02 持久化编排与 P0 Gate |
| 2026-08-16 12:31 | `3035322` | `feat` | 完成 G03 身份、租户与私有存储 |
| 2026-08-16 13:36 | `25bba5d` | `feat` | 完成 G04 安全来源管线 |
| 2026-08-16 14:35 | `1b14510` | `feat` | 完成 G05 规划工作区 |
| 2026-08-16 16:07 | `d150801` | `feat` | 完成 G06 真实生成与发布 |
| 2026-08-16 17:18 | `a596aef` | `feat` | 完成 G07 编辑、导出与历史闭环 |
| 2026-08-16 19:10 | `e9422d6` | `feat` | 完成 G08 自动化发布准备 |
| 2026-08-16 20:04 | `b515c8c` | `feat` | 加固 G08 发布治理审计 |
| 2026-08-16 20:05 | `548c4dc` | `docs` | 记录 G08 人工 Gate 阻塞项 |
| 2026-08-18 20:26 | `b690484` | `fix` | 修复意图识别后 PPT 规划流程中断，增加同源 API 代理与可恢复规划流程 |
| 2026-08-19 21:41 | `35f5084` | `fix` | ISSUE-002：强制默认工作流运行时合同 |
| 2026-08-19 21:57 | `e842fea` | `fix` | ISSUE-002：将图表事实限定在单个基准测试中 |
| 2026-08-19 22:02 | `261161c` | `fix` | ISSUE-002：居中单节点时间线内容 |
| 2026-08-19 22:32 | `72cd511` | `fix` | ISSUE-002：保留有来源的文案并增加图表多样性 |
| 2026-08-19 23:10 | `ebed9eb` | `fix` | ISSUE-002：使崩溃重放结果保持字节级确定性 |
| 2026-08-19 23:32 | `c156d90` | `docs` | ISSUE-002：记录最终生产验证结果 |
| 2026-08-22 23:50 | `e8b54ff` | `docs` | ISSUE-003：冻结 before/reference 质量基线与 Agent 证据合同 |
| 2026-08-22 23:58 | `9372959` | `fix` | 分类提交已验证的 provider timeout/retry 和质量修复 |
| 2026-08-23 00:18 | `2246ed8` | `feat` | ISSUE-003：新增语义 Page Blueprint 和 hash-bound 一致性门禁 |
| 2026-08-23 00:32 | `e22a045` | `feat` | ISSUE-003：新增受约束演示文稿设计工具 |
| 2026-08-23 00:49 | `0b29374` | `feat` | ISSUE-003：新增可恢复 Main Presentation Agent Runtime |
| 2026-08-23 01:06 | `9230485` | `feat` | ISSUE-003：同一 Main Agent 顺序创作并绑定逐页证据 |
| 2026-08-23 01:24 | `f45b8ce` | `feat` | ISSUE-003：新增有界多模态视觉审阅与反修闭环 |
| 2026-08-23 02:41 | `7de8499` | `feat` | ISSUE-003：新增显式 Agent/fallback 冻结、披露、灰度与回滚控制 |
| 2026-08-23 | `9003085` | `fix` | ISSUE-003：提升语义证据布局、可编辑性和最终同输入候选质量 |
| 2026-08-23 | `157dc2d` | `fix` | ISSUE-003：在确定性生产者和发布边界保留真实模板 fallback 披露 |
| 2026-08-23 | `4a5754c` | `test` | ISSUE-003：归档 Agent、fallback 与 rollback canary 生产用户旅程 |
| 2026-08-23 | `bdd1751` | `fix` | ISSUE-003：补齐 quick renderer 披露、根回归证据并关闭 Issue |

## 远端与 GitHub

当前没有配置远端。以下操作均为计划，只有在确认 GitHub 仓库地址、可见性和待上传内容后才能执行。

### 首次关联 GitHub 的计划流程

1. 在 GitHub 创建空仓库，并明确选择 `private` 或 `public`。
2. 上传前检查敏感信息、超大文件和不应跟踪的生成物。
3. 确认本地未提交改动如何分组，并完成必要测试。
4. 添加远端（将占位地址替换为真实地址）：

   ```powershell
   git remote add origin https://github.com/<owner>/<repository>.git
   ```

5. 核对远端配置：

   ```powershell
   git remote -v
   ```

6. 首次推送：

   ```powershell
   git push -u origin main
   ```

7. 检查 GitHub 上的默认分支、提交记录、文件可见性和安全告警，并把结果记录到本文档。

如果远端仓库并非空仓库，应先执行 `git fetch origin` 并比较双方历史，不能直接强制推送。除非明确评估影响并获得授权，不使用 `git push --force`。

### GitHub 上传前检查清单

- [ ] 已确定仓库所有者、仓库名和公开/私有属性
- [ ] `git status` 中的文件均已分类处理
- [ ] `.env`、API Key、密码、令牌、私钥等未被跟踪
- [ ] 已检查 Git 历史中是否曾提交敏感信息
- [ ] 已检查大文件以及 GitHub 单文件大小限制
- [ ] `node_modules/`、`.venv/`、构建产物和临时文件未被误提交
- [ ] 测试和发布 Gate 已达到预期状态
- [ ] 已确认开源许可证及第三方素材授权（如果仓库公开）
- [ ] 已核对远端 URL 和目标分支
- [ ] 推送后已在 GitHub 页面复核结果

## 操作日志

最新记录放在最上方。

### 2026-08-26 11:02 — 按当前实现重写项目 README

- 操作者：Codex
- 目的：根据项目当前进展更新面向用户与维护者的入口文档，补齐网站操作步骤、完整本地启动、当前技术栈、系统架构、Main Presentation Agent 设计、恢复/安全原则和验证入口。
- 操作前状态：`codex/issue-003-presentation-agent@9d5ab39c208a`；`README.md` 无工作区差异，`git.md` 已包含同日 ISSUE-003 真实 Provider 复核记录，其他大量用户/项目未提交改动均保持原状。
- 执行命令：读取 `SPEC.md`、`PROGRESS.md`、系统设计、ADR-012、开发/运行文档、Compose、环境样例和各 workspace 依赖清单；按项目约定使用 Context7 核对 Next.js、FastAPI 与 Celery 当前官方架构说明；通过 `apply_patch` 重写 README，并使用 Prettier 格式化。
- 变更范围：更新 `README.md` 与本条 `git.md` 日志；将过时的 Kimi 默认说明纠正为当前 Qwen `qwen3.7-plus` + `agent-authoring`，新增主题/文档入口、意图与大纲批准、异步生成、失败恢复、版本编辑/导出、Provider/回退模式及 Agent/Supervisor/Reviewer 职责说明。
- 验证结果：`pnpm exec prettier --check README.md`、`git diff --check -- README.md` 与 `docker compose --profile runtime config --quiet` 均通过；README 的 21 个相对链接均已逐一确认存在。文档变更未运行完整 `pnpm verify`。
- 相关提交：无；本次未执行 `git commit`。
- 远端结果：未涉及；未执行推送或部署。
- 回退方式：恢复本条日志，并将 `README.md` 恢复为操作前版本；不触碰其他已有工作区改动。
- 状态：成功。

### 2026-08-26 10:48 — 记录 ISSUE-003 真实 Provider 六页产物复核

- 操作者：Codex
- 目的：将 `qwen3.8max` 与 `qwen3.7plus` 基于同一 GPT-5.6 官方公告生成的两份 6 页 PPT 人工复核结果写回 ISSUE-003，并明确 Issue 关闭与持续质量优化的边界。
- 操作前状态：`codex/issue-003-presentation-agent@9d5ab39c208a`；工作区已有大量用户/项目未提交改动，但目标 Issue 文档和 `git.md` 在本次编辑前没有差异。
- 执行命令：读取 ISSUE-003 完成定义和既有 after 证据；使用演示文稿工具逐页渲染两份 PPTX、生成联系表、运行 `slides_test.py`，并以只读 Open XML 统计页数、Shape、可见字符、图片、图表和备注。
- 变更范围：仅更新 `docs/issues/ISSUE-003-default-agentic-profile-lacks-real-presentation-agent-runtime.md` 与 `git.md`；记录两份真实 Provider 产物的量化结构、人工优缺点和“保持 Resolved、质量增强另立 Issue”的决定。
- 验证结果：两份文件均为 6 页，逐页渲染成功且自动检测无画布溢出；`qwen3.8max` 为 192 Shapes / 1,681 可见字符，`qwen3.7plus` 为 121 Shapes / 989 可见字符；两者均无整页图片。`git diff --check` 通过；`pnpm verify:links` 已尝试，但被既有且无访问权限的 `.codex-tmp/pytest-native-fallback-repro` 目录以 `EPERM` 阻断，未发现与本次两个 Markdown 变更相关的链接错误。
- 相关提交：无；本次未执行 `git commit`。
- 远端结果：未涉及；未执行推送。
- 回退方式：仅恢复本条日志和 ISSUE-003 新增的“2026-08-26 真实 Provider 六页产物复核”小节。
- 状态：成功；未覆盖或暂存其他既有工作区改动。

### 2026-08-23 — 从最终代码提交重建并核验五服务运行时

- 操作者：Codex
- 目的：确保最终发布候选不只通过测试，也由同一已提交代码构建并以生产形态运行。
- 操作前状态：`codex/issue-003-presentation-agent@bdd1751`；运行时代码干净，工作区仅有用户无关改动和待生成的部署证据。
- 执行命令：以本地确定性 Provider、`agent-authoring` 和空线上 Provider 凭据运行 `python scripts/issue002/deploy_runtime.py --output docs/evidence/issue003/runtime-deployment-release.json`。
- 验证结果：`dirtyRuntimeInputs=[]`；API/Provider health 为 `ok`；API、Worker、Agent Worker、outbox、Provider Gateway 均报告 `bdd175114255…` 与 `instant-ppt-runtime@v2`；Worker 家族共享镜像 `sha256:20a06e59…`；`instant_ppt.v2.process_export` 已注册。
- 相关提交：`bdd1751142554c8c424d62dabceb10109bf31ecd`
- 证据：`docs/evidence/issue003/runtime-deployment-release.json`。
- 状态：成功；没有执行线上 Kimi 调用，也不作相应能力或费用声明。

### 2026-08-23 — 提交 ISSUE-003 fallback 披露与最终根回归收口

- 操作者：Codex
- 目的：让 engineering quick renderer 也满足阶段 F 的不可冒充合同，并据完整根验证关闭 ISSUE-003。
- 操作前状态：`codex/issue-003-presentation-agent@4a5754c`；生产用户旅程已归档，根回归暴露两个测试/工程 manifest 同步缺口。
- 执行命令：精确暂存 quick renderer、G07 fixture、测试、根验证证据、Issue/release/progress 文档后执行 `git commit -m "fix(runtime): complete fallback disclosure closure"`。
- 变更范围：quick renderer 写入 `deterministic-template`、limited disclosure、engineering fallback reason 和强制文件名；G07 fixture 使用不可变 revision 建议文件名；更新全量证据和关闭清单。
- 验证结果：根 `pnpm verify` exit 0；Contracts 26/38/166、API/Domain 40/40、Worker 127/127、G02 73/73、G03 8/8、G04 14/14、G05 4/4、G06 12/12、G07 5/5、G08 4/4、Golden 20/20 + 40 Schema artifacts，以及 Web、安全、恢复、E2E、Gate、链接全部通过。
- 相关提交：`bdd1751142554c8c424d62dabceb10109bf31ecd`
- 远端结果：未涉及；仓库仍无远端。
- 状态：成功；未纳入用户的无关 Markdown 空行和未跟踪工作目录。

### 2026-08-23 — 归档 ISSUE-003 生产用户旅程

- 操作者：Codex
- 目的：用用户视角验证 Agent 编辑/精确导出、修复后模板披露和开关回滚不改写旧 revision。
- 执行命令：精确暂存浏览器 E2E 与运行时部署证据后执行 `git commit -m "test(issue003): record production authoring journeys"`。
- 验证结果：Agent 8/8、32 turns/22 tools、revision 2 精确下载；fallback 8/8、0 turns/tools、monitor/editor/文件名均披露；回滚 canary 恢复 Agent 且旧 fallback 身份不漂移；浏览器 warning/error 0。
- 相关提交：`4a5754caa80eaf1ed42827523ddefcf36beb1751`
- 状态：成功。

### 2026-08-23 — 修复模板 fallback 不可变发布披露

- 操作者：Codex
- 目的：修复生产 E2E 发现的“监控页正确、编辑器误标 Agent”问题。
- 执行命令：在 legacy/template manifest 补齐真实 0-turn/0-tool 作者信息，并在领域发布边界从批准 snapshot 防御性回填，随后执行 `git commit -m "fix(agent): preserve template fallback disclosure"`。
- 验证结果：G06 12/12；新模板 revision 在 monitor/editor/export 一致披露，强制 `-模板化受限初稿.pptx`，切回 Agent 后旧 revision 仍不可变。
- 相关提交：`157dc2d22bf46fcf08fcacb51ffe22c7c55a21e0`
- 状态：成功。

### 2026-08-23 — 提交最终同输入语义与视觉质量候选

- 操作者：Codex
- 目的：在冻结十页输入上完成可比较的真实 Agent runtime 候选和人工质量结论。
- 执行命令：提交语义证据/布局/兼容性修复和 after 证据，提交说明为 `fix(agent): improve semantic evidence layouts`。
- 验证结果：38 turns/26 tools、视觉首轮 0 blocking；PowerPoint/WPS 各 10/10；23/23 可编辑文本、32 个原生形状、0 整页图片；人工结论 After 明显优于 Before。
- 相关提交：`900308568ba2524ac91c1d07d7e00c5a40272f9d`
- 状态：成功；本地使用 `fake-agent@v1`，不虚报线上 Kimi。

### 2026-08-23 02:41 — 提交 ISSUE-003 阶段 F 灰度与显式回退

- 操作者：Codex
- 目的：冻结新 generation snapshot 的 Agent/模板回退模式，并把 authoring 披露、canary、监控告警与回滚控制贯穿 API、Worker、Web 和发布文档。
- 操作前状态：`codex/issue-003-presentation-agent` 位于 `f45b8ce`；阶段 F 代码、合同、迁移、测试和文档已完成验证，工作区另有用户无关改动。
- 执行命令：按模块精确 `git add`，检查 `git diff --cached --check` 与暂存清单后执行 `git commit -m "feat(agent): add explicit authoring fallback and canary controls"`。
- 变更范围：57 个文件；authoring policy snapshot、fallback/canary、manifest/revision/export/SSE/UI 披露、Agent 指标与 14 条告警、迁移、ADR、runbook/privacy/release/rollback 文档及纵向回归。
- 验证结果：Contracts 26/38/166、API/Domain 40/40、Worker 119/119、G06 11/11、G07 5/5、Web、Ruff、告警、链接、Compose 与 Alembic 均通过。
- 相关提交：`7de849950adb87f99d63691f73a08fee68bdc6f9`
- 远端结果：未涉及；仓库仍无远端。
- 回退方式：`git revert 7de8499`；运行时紧急回退另可对新 snapshot 切换 `deterministic-template`，不改写既有 snapshot。
- 状态：成功；未纳入用户的无关 Markdown 空行和未跟踪工作目录。

### 2026-08-23 01:24 — 提交 ISSUE-003 阶段 E 有界视觉审阅闭环

- 操作者：Codex
- 目的：让只读 Visual Review Agent 以 contact sheet 和逐页渲染给出 hash-bound 结构化评审，并将 blocking finding 有界返回同一 Main Agent 反修。
- 操作前状态：`codex/issue-003-presentation-agent@9230485`；阶段 D 已验证提交。
- 执行命令：`git add <stage-e files>`；`git diff --cached --check`；`git commit -m "feat(agent): add bounded visual review loop"`。
- 变更范围：1280×720 逐页渲染与联系表、VisualReviewReport v1、最多两轮复审、page/deck ownership 反修、stale gate 与 `needs_manual` 停止语义。
- 验证结果：Ruff 和 Agentic Workflow/Visual Review/Runtime/Tool/Contract/Provider 合并回归 73/73 通过，成功/一轮修复/二轮仍阻断均有覆盖，contact sheet 人工检查通过。
- 相关提交：`f45b8ceb7b0965ad210891337885a1e82f2ad5c1`
- 远端结果：未涉及，未推送。
- 回退方式：`git revert f45b8ce`。
- 状态：成功。

### 2026-08-23 01:06 — 提交 ISSUE-003 阶段 D Main Agent 顺序 SVG 创作

- 操作者：Codex
- 目的：让 `default-agentic` 的真实 Strategist/Executor 会话接管逐页 SVG 写入，并把当前页 hash 绑定到实际 turn/tool evidence。
- 操作前状态：`codex/issue-003-presentation-agent@0b29374`；阶段 C 已验证提交。
- 执行命令：`git add <stage-d files>`；`git diff --cached --check`；`git commit -m "feat(agent): author slides through main agent"`。
- 变更范围：Strategist 策略落盘、P01→first-page gate→P02…Pn Executor 循环、Scene Graph 逐页 author evidence、上下文压缩、可编辑文本分形和 production/fake Provider 边界。
- 验证结果：Ruff/compile 和 Agentic Workflow/Runtime/Tool/Contract/Source/Image/Provider 合并回归通过，含 2 页 native chart、8 页、AI/provided 图片路径。
- 相关提交：`923048537afd5e42303152c6053b1cbefeb242e0`
- 远端结果：未涉及，未推送。
- 回退方式：`git revert 9230485`。
- 状态：成功。

### 2026-08-23 00:49 — 提交 ISSUE-003 阶段 C 可恢复 Main Agent Runtime

- 操作者：Codex
- 目的：建立由模型选择工具、由 Supervisor 强制预算/权限/取消且可从 checkpoint 无重复计费恢复的单主 Agent 运行时。
- 操作前状态：`codex/issue-003-presentation-agent@e22a045`；阶段 B 已验证提交。
- 执行命令：`git add <stage-c files>`；`git diff --cached --check`；`git commit -m "feat(agent): add resumable main runtime"`。
- 变更范围：AgentDecision/MainPresentationAgent、turn/tool/checkpoint evidence、tenant-scoped 数据表与 migration、持久化桥、Kimi 环境白名单、预算/取消/taint/恢复测试及物化 Schema。
- 验证结果：Ruff、45/45 合并回归和真实 PostgreSQL upgrade/downgrade/re-upgrade/drift 通过。
- 相关提交：`0b29374591b3d8e70e5035fa979dbfdeabfe1c73`
- 远端结果：未涉及，未推送。
- 回退方式：`git revert 0b29374`。
- 状态：成功。

### 2026-08-23 00:32 — 提交 ISSUE-003 阶段 B 受约束设计工具

- 操作者：Codex
- 目的：为 Main Presentation Agent 提供安全、可审计且足以表达可编辑演示文稿的语义工具层。
- 操作前状态：`codex/issue-003-presentation-agent@2246ed8`；阶段 A 已验证提交。
- 执行命令：`git add <stage-b files>`；`git diff --cached --check`；`git commit -m "feat(agent): add constrained presentation design tools"`。
- 变更范围：9 个精确工具、Scene Graph v1、可编辑文本/形状/分组/图片/native chart/table、受校验直接 SVG escape hatch、项目/页面/证据权限和 hash/attempt/stale tool evidence。
- 验证结果：Ruff、42/42 合并回归和 vendored SVG final checker 0 blocking/exit 0 通过。
- 相关提交：`e22a04544b240265c2dbeb221e2f81e19653d169`
- 远端结果：未涉及，未推送。
- 回退方式：`git revert e22a045`。
- 状态：成功。

### 2026-08-23 00:18 — 提交 ISSUE-003 阶段 A Page Blueprint

- 操作者：Codex
- 目的：以版本化、可审计的逐页沟通蓝图取代按页序取模的来源句分配。
- 操作前状态：`codex/issue-003-presentation-agent@9372959`；阶段 0 和已验证 runtime 修复已分类提交。
- 执行命令：`git add <stage-a files>`；`git diff --cached --check`；`git commit -m "feat(agent): add semantic page blueprint gate"`。
- 变更范围：PageBlueprint strict 合同/Schema、语义 evidence 选择、snapshot/roster/claim/literal/chart 门禁、Design Spec 投影与 Blueprint→SVG→PPTX 一致性报告。
- 验证结果：Ruff、33/33 Agentic Workflow/合同测试和 Markdown 链接检查通过，含有来源/无来源纵向切片、语义错绑及不支持 assertion 负向门禁。
- 相关提交：`2246ed864562a02b7a92b862f440c94ee9ee9bef`
- 远端结果：未涉及，未推送。
- 回退方式：`git revert 2246ed8`。
- 状态：成功。

### 2026-08-22 23:58 — 提交已验证的 runtime/provider 修复

- 操作者：Codex
- 目的：将切分 ISSUE-003 模块前已存在且完成验证的 provider timeout/retry、内容质量和 Web 修复单独归档，避免与新 Agent Runtime 混为一个提交。
- 操作前状态：`codex/issue-003-presentation-agent@e8b54ff`；保留一个无关测试 Markdown 空行修改和未跟踪目录。
- 执行命令：`git add <verified runtime files>`；`git commit -m "fix(runtime): checkpoint verified provider and quality fixes"`。
- 变更范围：provider 超时/重试、grounding/content/SVG 质量及 Web 交互修复。
- 验证结果：Ruff、53 项 Worker 定向测试、2 项 API planning 测试、Web lint/typecheck/build 及 `docker compose config --quiet` 通过。
- 相关提交：`9372959bd4f92c3eac8d5dcc6122a000e1c95952`
- 远端结果：未涉及，未推送。
- 回退方式：`git revert 9372959`。
- 状态：成功。

### 2026-08-22 23:50 — 提交 ISSUE-003 基线与证据合同

- 操作者：Codex
- 目的：在修改默认工作流前冻结可重放的 before/reference 输入、PowerPoint 渲染和最小 Agent 证据合同。
- 操作前状态：`codex/issue-003-presentation-agent@c156d90`，工作区含分支创建前保留的改动。
- 执行命令：`git add <issue003 baseline files>`；`git commit -m "docs(issue003): freeze presentation quality baselines"`。
- 变更范围：ISSUE-003 文档、基线封存/渲染/分析脚本、before/reference/user-lineage PPTX/PNG/contact sheet/指标和 Agent 证据合同。
- 验证结果：3 份 PPTX 经 PowerPoint 逐页渲染 10/10/12 页，Repairs=0；Ruff、ZIP/JSON/hash 校验和 Markdown 链接通过。
- 相关提交：`e8b54ff749372a6bd52c037b01b0216d5a9ed3ff`
- 远端结果：未涉及，未推送。
- 回退方式：`git revert e8b54ff`。
- 状态：成功。

### 2026-08-22 23:27 — 创建 ISSUE-003 独立开发分支

- 操作者：Codex
- 目的：在不丢弃既有工作区改动的前提下，将真实 Main Presentation Agent Runtime 开发与 ISSUE-002 已提交历史隔离。
- 操作前状态：`codex/issue-002-default-workflow@c156d90`；18 个已跟踪文件修改及 ISSUE-003、`projects/`、`git.md` 等未跟踪内容。
- 执行命令：`git switch -c codex/issue-003-presentation-agent`
- 变更范围：仅新增并切换本地分支引用；工作区内容原样保留。
- 验证结果：`git status --short --branch` 显示当前分支为 `codex/issue-003-presentation-agent`，既有修改与未跟踪文件仍在。
- 相关提交：`c156d90878509c78e94aef59cf5cc0f2d010f759`（分支起点）
- 远端结果：未涉及；仓库仍无远端。
- 回退方式：在提交或保存新增变更后切回原分支；不删除包含工作成果的分支。
- 状态：成功；本次未执行 `git commit`。

### 2026-08-22 15:17 — 同步当前 Git 提交基线

- 操作者：Codex
- 目的：将 `git.md` 中的分支、HEAD、提交总数和提交历史更新到当前项目状态。
- 操作前状态：文档记录停留在 `main@b690484`；实际仓库位于 `codex/issue-002-default-workflow@c156d90`。
- 执行命令：

  ```powershell
  git status --short --branch
  git log -1 --date=iso-strict --pretty=fuller
  git log --reverse b690484..HEAD
  git rev-list --count HEAD
  git remote -v
  git tag --list
  git log --merges --oneline --all
  git diff --stat
  ```

- 变更范围：更新当前仓库基线，补录 `35f5084` 至 `c156d90` 共 6 个 ISSUE-002 相关提交，并记录未提交工作区摘要。
- 验证结果：确认 HEAD 为 `c156d90878509c78e94aef59cf5cc0f2d010f759`，共 17 个线性提交，无合并提交、无标签、无 Git 远端。
- 相关提交：`c156d90878509c78e94aef59cf5cc0f2d010f759`
- 远端结果：未涉及，未推送。
- 回退方式：恢复本次对 `git.md` 的文档编辑。
- 状态：成功；本次未执行 `git commit`。

### 2026-08-18 20:26 — 提交 PPT 规划流程中断修复

- 操作者：Codex
- 目的：提交经自动化重跑与人工检查确认通过的 Web 端 PPT 规划流程修复，并记录对应 ISSUE。
- 操作前状态：`main` 位于 `548c4dc`；工作区存在本次修复和其他未提交改动，Git 远端未配置。
- 执行命令：

  ```powershell
  git add -- 'apps/web/src/app/api/[...path]/route.ts' 'apps/web/src/app/workspace-app.tsx' 'apps/web/src/app/source-uploader.tsx' 'apps/web/src/app/globals.css' 'docs/issues/ISSUE-001-web-planning-pipeline-stops-after-intent.md'
  git diff --cached --check
  git commit -m "fix(web): resume PPT planning after intent recognition"
  ```

- 变更范围：同源 API 代理、规划状态核对与断点恢复、上传请求 API 路径、恢复界面样式、ISSUE 故障及修复计划文档，共 5 个文件。
- 验证结果：暂存差异检查通过；此前完成 3 次浏览器端到端重跑，用户人工检查确认无问题。
- 相关提交：`b6904845fa5ae009d80f010bb4eb542d26280c53`
- 远端结果：未涉及，未推送。
- 回退方式：在保留后续提交的前提下执行 `git revert b690484`。
- 状态：成功；其他既有未提交改动未纳入本次提交。

### 2026-08-17 — 创建 Git 操作记录文档

- 操作者：Codex
- 目的：建立统一的 Git/GitHub 操作审计记录。
- 操作：读取当前分支、工作区状态、远端、标签和完整提交历史；新增 `git.md`。
- 使用的只读命令：

  ```powershell
  git status --short --branch
  git log --graph --decorate --oneline --all
  git log --reverse --date=iso-strict
  git rev-list --count HEAD
  git branch -vv
  git remote -v
  git tag --list
  git log --merges --oneline --all
  ```

- 结果：确认 `main` 有 10 个线性提交，无远端、标签或合并提交；工作区存在大量未提交修改和未跟踪文件。
- 状态：文档已创建，但尚未提交。

## 后续日志模板

复制以下内容到“操作日志”顶部，并填写实际信息：

```markdown
### YYYY-MM-DD HH:mm — 操作标题

- 操作者：
- 目的：
- 操作前状态：
- 执行命令：

  ```powershell
  git <command>
  ```

- 变更范围：
- 验证结果：
- 相关提交：`<commit>` / 无
- 远端结果：`<remote>/<branch>` / 未涉及
- 回退方式：
- 状态：成功 / 失败 / 部分完成 / 计划
```

## 常用检查命令

```powershell
# 当前状态
git status --short --branch

# 最近提交与分支图
git log --graph --decorate --oneline --all -n 30

# 提交前检查差异
git diff
git diff --cached

# 查看远端
git remote -v

# 获取远端状态但不合并
git fetch --prune

# 比较本地 main 与远端 main
git log --oneline --left-right main...origin/main
git diff --stat main...origin/main
```

这些命令仅供参考。实际执行结果，尤其是提交、变基、合并、标签、远端变更和推送，应追加到“操作日志”。
