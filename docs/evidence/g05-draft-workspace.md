# G05 draft workspace evidence

## Result

G05 is complete at the generation approval boundary. A user can start from a topic or
parsed source, select an immutable built-in template, review and edit inferred Intent,
create and revise a stable-ID Outline, undo/redo, ask the deterministic AI assistant for
a real revision, approve an exact snapshot, reload, and recover history. Approval and
post-approval edits create no generation job and the P1 image-call count remains zero.

The isolated PostgreSQL matrix contains 4 passed tests, zero failed, and zero skipped.
The Provider contract suite contains 7 passed tests. The browser record covers the
desktop, tablet, and mobile journeys with zero warning/error in a clean console.

## Acceptance mapping

| PLAN G05 requirement              | Engineering evidence                                                                              | Result |
| --------------------------------- | ------------------------------------------------------------------------------------------------- | ------ |
| Immutable templates and revisions | Seeded exact template versions plus PostgreSQL update/delete rejection triggers                   | passed |
| Stable slide identity             | Move preserved both IDs; add/delete and AI edits created only intended IDs/revisions              | passed |
| Undo/redo                         | Each action appended a new revision and retained the prior rows                                   | passed |
| Optimistic conflicts              | Stale ETag/base revision returned `412` without overwriting the winner                            | passed |
| Refresh/history recovery          | URL Draft ID rebuilt Intent, Outline, approval, edits, and history from API state                 | passed |
| Safe autosave failure             | Local edit survived API loss; failure remained stable; explicit retry persisted through reload    | passed |
| Explicit approval                 | Summary binds exact revisions/template/mode/hash; later editing leaves it unchanged               | passed |
| Provider contracts                | Exact frozen request shape, secret-safe repr/errors, deterministic repair, maximum two repairs    | passed |
| No reasoning/image leakage        | Neutral contract excludes reasoning; client/API contain no provider secret names; image calls = 0 | passed |
| Responsive workspace              | 1440 three-template/70–30, 900 two-template/two-slide/drawer, 390 single-column/step scroll       | passed |
| Accessible interaction            | Native controls, labels, live state, dialog focus restoration, 44 px targets, no overflow         | passed |
| Stop boundary                     | G06 action disabled and no generation job created before or after approval                        | passed |

## Executed verification

- `pnpm verify:integration:g05`: 4/4 real PostgreSQL API/domain cases passed;
- Provider suite: 7/7 HTTPX transport, structured repair, redaction, and image adapter
  contract cases passed;
- Alembic `G04 → G05 → G04 → G05`, three deterministic seeds, trigger enforcement,
  and `alembic check` completed without drift;
- ESLint, TypeScript, Ruff, and Next.js 16.2.9 production build passed;
- `pnpm verify:security:g05`: Worker-only secret-name boundary, browser bundle scan,
  reasoning-contract scan, and zero image-call assertion passed;
- `pnpm verify:e2e`: machine-readable in-app browser assertions passed;
- clean in-app Chromium session reported zero console warnings/errors;
- [browser evidence](g05-browser-e2e.json), [Provider/security evidence](security/g05-provider-results.json),
  and [integration JUnit](g05-workspace-junit.xml) contain the machine records.

`MOONSHOT_API_KEY` and `OPENAI_API_KEY` were absent, so no real external smoke was
eligible. No secret value was printed or persisted. Current official documentation did
not establish the frozen `kimi-k3` / `gpt-image-2` names, so this evidence verifies the
adapter contract and Fake Provider behavior, not external production availability.

## Faults found and closed

| Finding                                                                          | Attempts | Resolution                                                                                                                                                           |
| -------------------------------------------------------------------------------- | -------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FastAPI rejected a `204` route with an implicit body                             |        1 | Declared the route response class explicitly.                                                                                                                        |
| Chinese text was used directly in `Idempotency-Key`                              |        1 | Replaced it with a short ASCII SHA-256 prefix while retaining Chinese request content.                                                                               |
| Browser used `127.0.0.1` while CORS allowed `localhost`                          |        1 | Standardized local Web entry on `http://localhost:3000` and documented the boundary.                                                                                 |
| Failed autosave rescheduled itself                                               |        1 | Added a stable failed state and kind-specific explicit retry; outage/reload recovery passed.                                                                         |
| Desktop assistant content had layout but was not painted inside closed `details` |        1 | Controlled the native drawer open state and force-opened it outside tablet breakpoints.                                                                              |
| In-app browser Tab/Enter injection did not emit keyboard activation              |        5 | Stopped per loop policy; recorded the harness limitation and verified native elements, keyboard text focus, dialog focus restoration, and the complete real journey. |

No G05 product defect exceeded the five-attempt limit. The keyboard-injection limitation
is confined to the test harness and remains explicitly visible in browser evidence.
