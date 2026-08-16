# Contract design and generation

`scripts/contracts/catalog.mjs` is the authoring source for the G00 contract baseline. `pnpm contracts:materialize` creates:

- versioned Draft 2020-12 JSON Schemas;
- one valid and one invalid fixture for every required domain schema;
- OpenAPI 3.1 with every P1 endpoint and request/response/problem fixture;
- separate state machines and event-to-status mappings;
- stable error codes and a G01–G08 prerequisite matrix.

`pnpm verify:contracts` first checks that generated files match the catalog, then validates every positive/negative fixture, OpenAPI references and operation IDs, endpoint fixture coverage, transition targets, terminal states, event mappings and the rule excluding `attempt` from logical idempotency. It finally regenerates TypeScript client types from OpenAPI.

Pydantic models remain service-owned because domain behavior arrives in later Goals. Python services validate shared JSON instances against the same schemas in contract/integration tests rather than maintaining a second hand-written HTTP schema authority.
