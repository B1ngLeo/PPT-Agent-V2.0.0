# G00 engineering baseline evidence

- Goal: G00 / 冻结合同与建立工程基线
- Date: 2026-08-16
- Environment: Windows, Node 24.18.1, pnpm 11.19.0, Python 3.12.4, uv 0.12.5, Docker 29.5.2, Compose 5.1.4
- Result: passed

## Reproducible restore

- `pnpm install --frozen-lockfile` passed.
- `python -m uv sync --frozen` passed and installed both API/Worker workspace members.
- `docker compose config --quiet` passed for PostgreSQL 17.6, Redis 7.4.2, MinIO `RELEASE.2025-04-22T22-12-26Z`, and ClamAV 1.4.2.
- `scripts/verify-clean-bootstrap.ps1` copied the source tree without `.git`, `node_modules`, `.venv`, `.next` or language caches, repeated frozen restore and core verification, then safely deleted the exact temporary directory. Result: passed.
- `.github/workflows/ci.yml` declares the same bootstrap and contract checks on Linux and Windows.

## Contract evidence

`pnpm verify:contracts` passed:

- 26 versioned Draft 2020-12 schemas;
- 38 P1 OpenAPI operations;
- 166 valid/invalid/request/response/error fixtures;
- OpenAPI 3.1 references and unique operation IDs;
- source, generation job, slide and export state machines;
- job event-to-status mapping and terminal rules;
- stable error categories and RFC 7807 extension;
- G01–G08 required schema/endpoint prerequisite coverage;
- TypeScript generation from OpenAPI.

## Boundary build evidence

- `pnpm verify:web`: ESLint, TypeScript and optimized Next.js 16.2.9 build passed.
- `pnpm verify:api`: Ruff and Pytest passed.
- `pnpm verify:worker`: Ruff and Pytest passed.
- `pnpm verify:links`: local Markdown targets passed.
- `pnpm verify:gates --goal G00`: 1/1 required Gate passed.
- `pnpm verify`: current-stage aggregate passed. Integration, golden, E2E and security entries explicitly report their future owning Goal and are not claimed as implemented.

## Decisions and remaining gates

ADR-001, ADR-006, ADR-010 and ADR-011 are accepted engineering decisions. Identity provider, PDF licensing, engine vendoring, production Provider policy, retention, desktop compatibility and optional private templates remain proposed for their owning Goals. Human/legal/compatibility gates remain pending and are not represented as passed.
