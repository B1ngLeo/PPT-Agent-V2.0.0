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

截至 2026-08-22：

| 项目 | 状态 |
| --- | --- |
| 当前分支 | `codex/issue-003-presentation-agent` |
| 当前提交 | `c156d90` (`docs(issue002): record final production verification`) |
| 提交总数 | 17 |
| 历史结构 | 单一直线历史，无合并提交 |
| Git 远端 | 未配置 |
| Git 标签 | 无 |
| 工作区 | 从 ISSUE-002 分支保留 18 个已跟踪文件修改及多组未跟踪内容；ISSUE-003 开发尚未提交 |
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
