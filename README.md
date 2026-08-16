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

真实文本规划使用 Kimi K3，AI 生图使用 OpenAI GPT Image 2。Worker 仅从服务端环境读取以下配置：

```dotenv
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_MODEL=kimi-k3
KIMI_REASONING_EFFORT=max
IMAGE_BACKEND=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-image-2
```

`MOONSHOT_API_KEY` 与 `OPENAI_API_KEY` 必须通过未纳入 Git 的本地 `.env` 或 Secret Manager 提供。不要运行会展开环境值的 `docker compose config`；使用 `docker compose config --quiet` 校验配置。当前 P1 产品流程不调用图片 Provider，该后端仅作为后续生图流程的服务端能力预配置。

环境版本、Windows/Linux 说明和合同变更流程见 [开发文档](docs/development.md)。尚未进入对应 Goal 的测试入口会明确报告 `not-configured`；从首次实现起必须运行真实检查。

G05 本地工作台使用 `http://localhost:3000`（不要改用 `127.0.0.1:3000`，后者不在默认 CORS 白名单）。启动 PostgreSQL/MinIO 并升级迁移后，可分别启动 API 与 Web：

```powershell
$env:PYTHONPATH='services/api/src;packages/domain/src'
python -m uv run --package instant-ppt-api uvicorn instant_ppt_api.main:app --host 127.0.0.1 --port 8000
pnpm --filter @instant-ppt/web dev
```

G00–G05 与 P0 Gate 已通过；身份/租户/私有对象、安全来源流水线，以及草稿/意图/大纲/批准工作台均已形成独立验证证据，当前按 PLAN 进入 G06 真实生成。详见 [G04 证据](docs/evidence/g04-secure-source-pipeline.md)与 [G05 设计](docs/design/g05-draft-workspace.md)、[G05 证据](docs/evidence/g05-draft-workspace.md)。

## Repository policy

本地仓库使用 Git `main` 分支管理。除非得到明确授权，不创建提交、不推送、不部署，也不把密钥、源文档正文或预签名 URL 写入仓库与日志。
