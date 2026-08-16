# G04 secure upload and Source parsing evidence

## Result

G04 is complete. Four allow-listed formats traverse a private
`quarantine → scan → clean → parse → published` flow, while byte changes, checksum or
magic mismatch, malicious archives, active/external HTML, encrypted/corrupt PDF,
malware, scanner loss, and cross-tenant access cannot enter parse. Processing state,
attempts, decisions, errors, parser version, source package, and immutable artifact
metadata survive API restart and browser refresh.

The isolated PostgreSQL/MinIO matrix contains 14 passed tests, zero failed, and zero
skipped. Its evidence SHA-256 is
`24EED61DA84996EDECC1AD9670228850767DAD6F714B7136FFC6B61B8CB6DCF4`.
The real container journey passed with evidence SHA-256
`67EC35E03AFF397B7FD0AF04CF00FD133DFB640568D84F9B852833BBE460C9E4`.
The browser upload and refresh journey has evidence SHA-256
`CFF07447DF7C70D8D0B0EC5443AA8A2B77EC2783C470A4327005C930620F15E7`.

## Acceptance mapping

| PLAN G04 requirement                  | Engineering evidence                                                                                         | Result |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------ |
| Upload session and private quarantine | Exact POST policy; safe basename metadata; ULID-only tenant key; completion HEAD/stream/SHA                  | passed |
| Network retry idempotency             | Create and complete replay use one source/task; a closed session cannot be re-signed                         | passed |
| Four successful formats               | Real DOCX, PDF, PPTX, and HTML fixtures parse and publish Markdown/profile/assets                            | passed |
| Scanner fail closed                   | Socket loss persists failed/retryable state, publishes no artifact, and allows one idempotent retry          | passed |
| Malware scanner                       | Actual non-root ClamAV 1.4.3 INSTREAM returns `OK` for valid input and `FOUND` for the container threat      | passed |
| MIME, magic, and hostile containers   | Mismatch, ratio bomb, traversal, encrypted/corrupt PDF, and active HTML remain rejected with parse attempt 0 | passed |
| Post-complete tamper                  | Worker re-hash detects changed quarantine bytes before scan and rejects permanently                          | passed |
| Clean-only parser                     | Decision key/hash binding is rechecked; only clean partition enters parser                                   | passed |
| Immutable artifacts                   | Every published object has unique ULID key, SHA-256, size, MIME, parser version, and 30-day retention        | passed |
| Cross-tenant isolation                | Foreign source read and upload completion return the same `404` as unknown IDs                               | passed |
| Refresh/API restart recovery          | A newly constructed API reads the same persistent source status; Web resumes by source ID                    | passed |
| Parser isolation                      | Worker uid 10001, read-only root, no capabilities/host mount, bounded tmp/CPU/memory/PIDs/time               | passed |
| PDF license path                      | `pypdf 6.16.1` BSD-3-Clause path remains the accepted ADR-003 implementation                                 | passed |
| Responsive accessible Web state       | lint/typecheck/build plus 390/768/1440 browser checks, keyboard focus, live status, reduced motion           | passed |

## Executed verification

- `pnpm verify:api`: Ruff and 21 API/domain tests passed;
- `pnpm verify:worker`: vendor/engine boundary, Ruff, and 15 Worker tests passed;
- `pnpm verify:web`: ESLint, TypeScript, and Next.js 16.2.9 production build passed;
- `pnpm verify:security:g04`: 12 upload, clamd protocol, and fail-closed checks passed;
- `pnpm verify:integration:g04`: 14 real PostgreSQL/MinIO cases passed;
- `pnpm verify:container:g04`: actual API/outbox/Celery/ClamAV/MinIO valid and threat
  journeys passed under restricted containers;
- Alembic `5d3890b5cbb8 → 9e9a61eff690 → 5d3890b5cbb8 → head` and drift check passed;
- browser render at 390, 768, and 1440 px had no horizontal overflow, ≥46 px primary
  target, no console warning/error, and a fixed initially-hidden skip link;
- browser user journey uploaded HTML to parsed/2 artifacts, then paused Worker/outbox,
  uploaded DOCX, reloaded while queued, recovered the same filename/status, resumed
  services, and reached parsed/2 artifacts without console errors;
- [machine-readable integration matrix](security/g04-source-results.json) and
  [container evidence](security/g04-container-e2e.json) contain individual results,
  versions, identities, restrictions, and security decisions; the
  [browser E2E record](g04-browser-e2e.json) records responsive and refresh journeys.

The [G04 design](../design/g04-secure-source-pipeline.md),
[ADR-003](../adr/ADR-003-pdf-parser-license.md), and
[ADR-007](../adr/ADR-007-retention-download.md) document the boundary.

## Faults found and closed

| Finding                                                                                     | Attempts | Resolution                                                                                                                                                |
| ------------------------------------------------------------------------------------------- | -------: | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Docker proxy returned 403 for the upstream `clamav/clamav` repository                       |        2 | Built exact Debian `clamav-daemon 1.4.3+dfsg-1~deb12u2` on the existing digest-pinned base, with deterministic signature and no network updater in tests. |
| ClamAV could not open `/dev/stderr` as a log file under the read-only image                 |        1 | Removed the explicit log file; foreground daemon logs to container stdout and became healthy.                                                             |
| Building Worker did not refresh Compose's separately named outbox image                     |        1 | Container verifier now builds clamav, API, Worker, and outbox sequentially before running; the original pending task recovered after outbox recreation.   |
| Wheel installation moved the package one ancestor deeper than editable source               |        1 | Vendored-engine root discovery now walks ancestors (or validates an explicit environment root), covering both local and `/app/.venv` installs.            |
| Full HTML normalization prevented the deterministic raw-byte ClamAV signature from matching |        2 | The actual daemon assertion uses the exact marker stream; a separate active-HTML case still validates structural rejection.                               |
| Domain validation silently normalized uppercase hash input                                  |        1 | Removed normalization and enforced the lowercase contract in both Pydantic and domain tests.                                                              |
| Mobile screenshot showed the off-screen skip link partially exposed                         |        1 | Switched to a translated, no-wrap link that returns only on keyboard focus.                                                                               |
| Browser Fetch rejected the Chinese local development display-name header                    |        1 | Kept the visible Chinese UI but sent an ASCII-only development header value; real browser upload then completed.                                          |

No issue exceeded the five-attempt limit. There are no deferred G04 defects or SPEC
deviations. Production signature freshness monitoring remains an explicit G08
operations responsibility, not a relaxation of the G04 fail-closed gate.
