# Contract verification

Contract source data lives in `scripts/contracts/catalog.mjs`. Generated JSON Schemas, OpenAPI, endpoint fixtures, transition fixtures, and required-contract coverage live under `packages/contracts/` and this directory.

Run `pnpm contracts:materialize` after intentionally changing the catalog, then `pnpm verify:contracts`.
