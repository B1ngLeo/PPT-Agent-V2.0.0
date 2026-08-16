# Test layout

- `contract/`: JSON Schema, OpenAPI, state-machine, event, and error fixtures.
- `integration/`: PostgreSQL/Redis/object-store/worker tests from G02 onward.
- `golden/`: source and presentation golden samples from G01 onward.
- `e2e/`: browser user journeys from G05 onward.
- `security/`: malicious-input and tenant-boundary tests from G01 onward.

Root `pnpm verify:*` commands are stable. Tests outside the active Goal report `not-configured` until their owning Goal implements them.
