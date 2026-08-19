# 即刻AI-PPT

即刻AI-PPT 是一个“先确认意图与大纲，再异步生成可编辑原生 PPTX”的多租户产品。当前实施以 [SPEC](SPEC.md) 为规范合同、[PLAN](PLAN.md) 为顺序执行计划、[PROGRESS](PROGRESS.md) 为持续状态记录。

## Architecture

- `apps/web` — Next.js Web/BFF，不执行解析或 PPT 生成。
- `services/api` — FastAPI 业务与 SSE 边界。
- `services/worker` — Celery、隔离解析/生成和 Provider Gateway 边界。
- `packages/contracts` — OpenAPI、JSON Schema、fixtures、状态机和生成类型。
- `infra/compose` — PostgreSQL、Redis、MinIO、ClamAV 本地拓扑。

详细边界见 [系统设计](docs/design/system-design.md)、[合同设计](docs/design/contract-design.md) 和 [G01 引擎适配器设计](docs/design/g01-engine-adapter.md)。

## Bootstrap and verification

```powershell
pnpm install --frozen-lockfile
python -m uv sync --frozen
docker compose config --quiet
pnpm verify
```

## Provider configuration

真实文本规划使用 Kimi K3；受控图片生成使用 GPT Image 2。公开 API 只持有内部
Gateway token，私有 Provider Gateway 持有 Kimi 密钥；图片密钥只在明确图片任务子进程中按白名单传入：

```dotenv
PLANNING_BACKEND=kimi
KIMI_BASE_URL=https://cf.api.fan/v1
KIMI_MODEL=kimi-k3
KIMI_PROTOCOL=anthropic
KIMI_REASONING_EFFORT=max
IMAGE_BACKEND=openai
IMAGE_GENERATION_ENABLED=false
IMAGE_MAX_PER_DECK=0
IMAGE_COST_MICROUNITS=100000
OPENAI_BASE_URL=https://cf.api.fan/v1
OPENAI_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1536x1024
OPENAI_IMAGE_QUALITY=low
```

`MOONSHOT_API_KEY`、`OPENAI_API_KEY` 与独立的 `PROVIDER_GATEWAY_TOKEN` 必须通过未纳入 Git 的本地 `.env` 或 Secret Manager 提供。不要运行会展开环境值的 `docker compose config`；使用 `docker compose config --quiet` 校验配置。图片默认仍关闭；要启用必须同时设置 `IMAGE_GENERATION_ENABLED=true`、`IMAGE_MAX_PER_DECK=1`、非负的单图成本和本地密钥，并由用户在批准页显式选择“仅封面”或一个“选定页”。只设置环境变量不会更改默认 `image_scope=none`。Provider 或已确认路径失败时任务进入 `Needs-Manual`，不会静默丢图。

环境版本、Windows/Linux 说明和合同变更流程见 [开发文档](docs/development.md)。尚未进入对应 Goal 的测试入口会明确报告 `not-configured`；从首次实现起必须运行真实检查。

G05 本地工作台使用 `http://localhost:3000`（不要改用 `127.0.0.1:3000`，后者不在默认 CORS 白名单）。启动 PostgreSQL/MinIO 并升级迁移后，可分别启动 API 与 Web：

```powershell
docker compose --profile runtime up -d provider-gateway
$env:PYTHONPATH='services/api/src;packages/domain/src'
python -m uv run --package instant-ppt-api uvicorn instant_ppt_api.main:app --host 127.0.0.1 --port 8000
pnpm --filter @instant-ppt/web dev
```

G00–G08 与 ISSUE-002 Default Agentic 内容/图片链路已形成独立验证证据。详见 [ISSUE-002](docs/issues/ISSUE-002-generated-pptx-renders-outline-placeholders-instead-of-usable-draft.md)、[G06 设计](docs/design/g06-real-generation-publication.md) 和 [发布 Gate](docs/release-gate-report.md)。

## Repository policy

本地仓库使用 Git `main` 分支管理。除非得到明确授权，不创建提交、不推送、不部署，也不把密钥、源文档正文或预签名 URL 写入仓库与日志。
