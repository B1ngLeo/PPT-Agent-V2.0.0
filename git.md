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
| 当前提交 | `9230485` (`feat(agent): author slides through main agent`) |
| 提交总数 | 23 |
| 历史结构 | 单一直线历史，无合并提交 |
| Git 远端 | 未配置 |
| Git 标签 | 无 |
| 工作区 | ISSUE-003 阶段 0–D 已分类提交；阶段 E 正在开发，保留用户的无关 Markdown 空行修改和未跟踪工作目录 |
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
