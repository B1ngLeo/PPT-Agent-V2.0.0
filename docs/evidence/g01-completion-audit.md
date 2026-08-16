# G01 completion audit

This audit maps the current worktree to PLAN 4.3–4.9 and the G01-owned portion of SPEC 12.3. An automated pass does not represent legal or named QA approval.

| Requirement                                                                | Status                      | Authoritative evidence                                                                | Remaining condition                     |
| -------------------------------------------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------- |
| G00 contracts and engineering baseline                                     | automated pass              | `pnpm verify`, `docs/evidence/g00-engineering-baseline.md`                            | none                                    |
| Fixed engine version and immutable attribution                             | approved                    | vendor manifest, canonical tree verifier, upstream attribution guard, approval record | none                                    |
| Locks, SBOM, font provenance and reproducible container                    | automated pass              | `uv.lock`, `pnpm-lock.yaml`, CycloneDX evidence, stable container image ID            | none                                    |
| Versioned JSON adapter with stable errors and no business credentials      | automated pass              | adapter schemas, seven Worker tests, non-root container inspection                    | none                                    |
| Adapter is the only product-facing upstream boundary                       | automated pass              | `scripts/g01/verify_engine_boundary.py` plus vendor reference scan                    | none                                    |
| Clean decision is key/hash-bound before parse                              | automated pass              | tamper regression and 13-sample threat harness                                        | none                                    |
| 10 approved source fixtures produce exact SourcePackages                   | automated pass              | `docs/evidence/g01-golden-results.json`                                               | none                                    |
| 10 approved DeckPlans produce canonical SVG, pristine upstream QA and PPTX | automated pass              | 30/30 slides, zero upstream errors/warnings                                           | none                                    |
| Package structure, slide count, relations and media references             | automated pass              | 190 internal targets resolved; zero missing/escaping targets or orphan media          | none                                    |
| Planned text and agreed native shapes remain editable                      | approved                    | 103/103 planned text instances, 123 native shapes and completed edit/save/reopen QA   | none                                    |
| Preview and immutable artifact manifest                                    | automated pass              | preview SVG hashes and PPTX SHA-256 manifest checks for all ten cases                 | none                                    |
| PowerPoint/WPS open, export and cross-application visual thresholds        | approved                    | 10/10 in each application, 30/30 PNG comparisons and named visible-window QA          | none                                    |
| PDF parser and EPUB licensing posture                                      | approved                    | accepted ADR-003, pypdf 6.16.1 SBOM, PDF golden/security cases, approval record       | none                                    |
| P0 worker-kill, duplicate-delivery, Redis and SSE recovery                 | deferred by sequential PLAN | contracts are frozen; G02 owns executable recovery evidence                           | G01 required Gates must pass before G02 |

## Blocking audit

The worktree contains no remaining G01 item. All three required Gates are `passed`; `pnpm verify:gates --goal G01` succeeds. PLAN's sequential boundary is satisfied and G02 implementation may start.
