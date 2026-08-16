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
docker compose config
pnpm verify
```

环境版本、Windows/Linux 说明和合同变更流程见 [开发文档](docs/development.md)。尚未进入对应 Goal 的测试入口会明确报告 `not-configured`；从首次实现起必须运行真实检查。

G00–G02 与 P0 Gate 已通过；G03 身份、租户、私有对象和下载授权已完成独立安全矩阵，当前执行全仓回归后按 PLAN 进入 G04。详见 [G03 证据](docs/evidence/g03-identity-tenancy-storage.md)。

## Repository policy

本地仓库使用 Git `main` 分支管理。除非得到明确授权，不创建提交、不推送、不部署，也不把密钥、源文档正文或预签名 URL 写入仓库与日志。
