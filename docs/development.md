# Development baseline

## Pinned toolchain

- Node.js 24.18.1
- pnpm 11.19.0
- Python 3.12.4
- uv 0.12.5
- Docker Engine 29.5.2 and Compose 5.1.4 were used for the G00 local baseline

Next.js 16.2.11 requires Node.js >=20.9.0; the repository uses one fixed Node 24 line on local and CI workers. uv manages all Python workspace members with a single cross-platform `uv.lock`.

## Bootstrap

```powershell
corepack enable
corepack prepare pnpm@11.19.0 --activate
pnpm install --frozen-lockfile
python -m pip install uv==0.12.5
python -m uv sync --frozen
docker compose config
```

On systems where `uv` is already on `PATH`, `uv sync --frozen` is equivalent to the Python module invocation.

## Contract changes

Edit `scripts/contracts/catalog.mjs`, run `pnpm contracts:materialize`, inspect the generated diff, and run `pnpm verify:contracts`. Never hand-edit files under `packages/contracts/schemas`, `packages/contracts/fixtures`, or `packages/contracts/generated`.

## Stable verification commands

The root `verify:*` commands never change names. Before their owning Goal, integration/golden/E2E/security commands print `not-configured` and exit successfully. Once implemented, a command must run real checks and may not revert to a placeholder.

Run all automated G08 release checks with `pnpm verify:automated:g08`. Run the complete
repository and Gate chain with `pnpm verify`; until the two required human release decisions
are signed, that command intentionally exits non-zero only at `GATE-G08-RELEASE` with status
`ready_for_review`.
