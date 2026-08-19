# G06 real generation and publication evidence

## Result

G06 is complete at the immutable generated-baseline boundary. An exact G05 approval
now creates a quota-reserved real job, executes stable pages in the Worker through the
G01 engine adapter, publishes a native PPTX and bound manifest, streams durable
progress, survives process and Redis loss, supports cancellation and failed-page
retry, and creates immutable Presentation revisions without opening G07 editing or
export UX.

The isolated real-service matrix now contains 8 passed tests, zero failed, and zero
skipped. Its JUnit SHA-256 is
`5770A2C4AB5AA3DF70FB00856648C9DFE64FCCD5D10E8E4AE758330B44A0C710`.

## Acceptance mapping

| PLAN G06 requirement              | Engineering evidence                                                                                                                           | Result |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Exact immutable snapshot          | Approval-bound payload and all frozen versions persisted; later Outline edit did not change Worker input; trigger rejected mutation            | passed |
| Real per-slide generation and QA  | Public G01 adapter compiled native PPTX; candidate/deck QA and stable render hashes persisted                                                  | passed |
| Compile, package QA, and manifest | PPTX ZIP structure inspected; manifest binds snapshot, versions, publication, revision, pages, hashes, and private keys                        | passed |
| Durable progress and refresh      | PostgreSQL stages/events drive the API; browser recovered the same job from its URL and completed at 8/8                                       | passed |
| Worker kill and redelivery        | A real child process exited via `os._exit(73)` after committed slide start; expired lease reclaim produced one publication/revision/charge     | passed |
| Upload crash replay               | Crash after deterministic MinIO upload and before DB publish left zero published rows; replay reproduced identical bytes and published once    | passed |
| Redis restart and SSE reconnect   | The Redis container restarted; `Last-Event-ID: 1` replayed through terminal `job.completed` from PostgreSQL                                    | passed |
| Partial and stable-ID retry       | Other pages continued; revision 1 retained the failed slot; retry touched only the failed ID and revision 2 reused the ready artifact          | passed |
| Cancellation semantics            | Cancel before start produced no object; cancel after upload but before transaction won the race with no half-publication rows                  | passed |
| Quota and accounting              | Tenant lock considered settled plus reserved pages; rejected quota created no job; slide/image/worker usage settled once                       | passed |
| Approved cover-image extension    | Frozen non-secret image config drove one injected Provider call, one published source image, one referenced PPTX media part and image usage 1  | passed |
| Tenant isolation                  | Foreign create, job read, and SSE returned existence-hiding `404`; private object keys remain tenant partitioned                               | passed |
| Stop boundary                     | Monitor displays generation artifacts but contains no result edit, final export, download, user-facing visual mode, or private-template action | passed |

## Executed verification

- `pnpm verify:integration:g06`: 8/8 real PostgreSQL/MinIO/Redis/engine cases passed;
- an image-enabled immutable snapshot still generated one cover after the runtime switch
  was disabled, proving the frozen configuration; the fake image Provider was called once,
  its PNG was published/embedded, ProviderCall succeeded, and image usage settled to one;
- real Worker subprocess kill, lease expiry/reclaim, duplicate terminal delivery, and
  upload-before-publish replay produced one immutable publication and one usage charge;
- actual `docker compose restart redis` followed by SSE sequence replay reached the
  persisted terminal event and rejected a foreign tenant;
- partial revision 1 and successful retry revision 2 preserved stable page IDs and
  reused the previously ready SVG artifact;
- cancellation-before-work and cancellation-at-publication-race created no
  Presentation or published Artifact row;
- Alembic `G05 → G06 → G05 → G06`, immutable trigger enforcement, and schema drift
  checking passed;
- `pnpm verify:web`: ESLint, TypeScript, and the Next.js production build passed;
- a real browser journey created and approved an eight-page outline, started the real
  Celery Worker, refreshed the monitor URL, and observed 8/8 plus publication v1 and
  the five deck-level artifact kinds;
- [browser evidence](g06-browser-e2e.json) and [integration JUnit](g06-generation-junit.xml)
  contain the machine records.

The in-app browser runtime used for the real journey does not expose viewport resize.
G06 therefore records its real desktop journey separately from responsive CSS/static
checks; the established G05 390/900/1440 interaction matrix remains the product-shell
evidence, and the G06 monitor adds explicit ≤760 px single-column rules and 44 px
controls. No mobile browser result is claimed for G06.

## Faults found and closed

| Finding                                                                                             | Attempts | Resolution                                                                                                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------- | -------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Alembic naming convention prefixed an already named Draft status constraint                         |        1 | Marked the existing name with `op.f(...)`; upgrade/downgrade and drift checks passed.                                                                                                                                                                              |
| SSE effect reconnected after every authoritative job refresh                                        |        1 | Bound the effect to job ID and terminal state, keeping one stream across ordinary state updates.                                                                                                                                                                   |
| New killed-Worker test collided with a manually running browser-test Worker lease                   |        1 | Stopped out-of-suite runtimes before isolated recovery execution; the real exit/reclaim case then passed.                                                                                                                                                          |
| SSE terminal assertion expected `job.succeeded` instead of the domain event `job.completed`         |        1 | Asserted the canonical persisted event name and reran the Redis restart matrix.                                                                                                                                                                                    |
| In-app browser exposes no viewport-resize operation                                                 |        1 | Recorded the capability limit without claiming mobile execution; production build and explicit responsive rules remain verified.                                                                                                                                   |
| A stale broker delivery referenced a job already removed by isolated database cleanup               |        1 | The real generation task now acknowledges the missing durable job as idempotent `noop_missing` instead of emitting an operational failure.                                                                                                                         |
| Long CJK page text was clipped by the SVG author and correctly rejected by editable-text package QA |        2 | The first pass fixed candidate geometry; the second traced full-deck text mismatch and replaced clipping with East-Asian-width-aware dynamic font sizing that preserves exact approved text. SVG QA, PPTX text QA, and a fresh eight-page real browser run passed. |

No G06 defect or test issue exceeded the five-attempt limit. Unreferenced deterministic
objects from upload-before-cancel/crash are intentionally outside the publication and
are a G08 reconciliation/retention concern, not a half-published user artifact.
