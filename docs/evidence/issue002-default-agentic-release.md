# ISSUE-002 Default Agentic release evidence

- Date: 2026-08-19
- Result: passed
- Branch: `codex/issue-002-default-workflow`
- Scope: approved input through Default Agentic generation, image-resource handling,
  immutable publication, editing, exact-revision export and user-visible recovery

## Product outcome

The website no longer publishes outline instructions, unresolved placeholders or internal
engineering copy as a completed presentation. The product path is fixed to
`route=generate_pptx` and `profile=default-agentic`; Quick remains an engineering-only
profile guarded by the same visible-content release policy.

Approved source fragments are re-read from tenant-scoped immutable artifacts, hash checked
and passed as tainted data to the Provider boundary. Claims, citations, data labels, units
and source coverage are checked at Design Spec, final SVG and compiled PPTX stages. With no
approved source, generation requires explicit user consent and authors a clearly labelled
`limited-general-draft` containing role-aware, topic-specific decision copy without
invented facts.

The lifecycle retains stable `outlineSlideId -> slideId -> PNN`, immutable WorkflowRun and
checkpoint ownership, effective Design Spec revisions and hash-bound EditPatch history.
Initial generation, non-cover regeneration and exact-revision export all run the applicable
whole-deck content/SVG/chart/postflight/package gates.

## Image Release Gate

`image_scope=none|cover_only|selective` is mapped separately from the exclusive upstream
source-id array. Provided assets are byte/media checked and analyzed against a fresh image
inventory. AI acquisition follows only the confirmed `auto|api|host-native` path, is capped
by organization-level count and micro-unit cost reservation, and receives only a minimized
text-free visual prompt. An unresolved required image stops before export as
`needs_manual`; the UI displays its safe error code, stage and recovery action. An
Office-native substitute is used only when its exact trigger was approved in the Design
Spec.

Every accepted image is an independently replaceable PPTX media/picture object. Text,
charts, factual labels and evidence stay native editable, and full-slide bitmap fallback is
rejected. Image source, inventory analysis, sanitized attempt audit, prompt hash, usage and
cost are included in immutable publication evidence.

## Automated verification

| Boundary                           | Result                                                                       |
| ---------------------------------- | ---------------------------------------------------------------------------- |
| Contract materialization/OpenAPI   | 26 schemas, 38 endpoints, 166 fixtures passed                                |
| API and Domain                     | 38 passed; Ruff passed                                                       |
| Worker and engine boundary         | 71 passed; Ruff, attribution and direct-engine allowlist passed              |
| Web                                | ESLint, TypeScript and Next.js 16.2.11 production build passed               |
| G02 recovery matrix                | 73 passed                                                                    |
| G03 tenant/migration/object matrix | 8 passed; head downgrade/upgrade and zero drift                              |
| G04 source-security matrix         | 14 passed                                                                    |
| G05 workspace matrix               | 4 passed                                                                     |
| G06 generation/image matrix        | 11 passed                                                                    |
| G07 edit/exact-export matrix       | 5 passed                                                                     |
| G08 release integration matrix     | 4 passed                                                                     |
| G01 golden                         | 10/10 source and 10/10 render chains; 40 schema-bound artifacts              |
| Long-title no-source regression    | 8/8 final SVG files, 0 errors, 0 warnings; PPTX/package/content gates passed |
| Crash replay determinism           | Upload-then-crash replay published one immutable revision byte-identically   |

The image matrix includes provided-image analysis, a real subprocess calling a controlled
Fake HTTP image endpoint, independent picture/media embedding, idempotent quota/cost
settlement, explicit-path `needs_manual`, approved native fallback and provider-secret
scoping. The content matrix includes prompt-injection isolation, semantic citation support,
conflicting chart facts, stale reports, placeholder/author-task rejection, ending closure
and G07 effective-revision preservation.

## Final user journey

Using the production Web build and real API/outbox/Redis/Celery/Worker/database/object-store
path, the browser journey verified:

1. the attached `GPT5.6的官方发布公告.pptx` was identified as the old eight-page generated
   placeholder deck rather than a factual announcement source; when deliberately supplied
   to three data pages, the content guard stopped before publication because it contained no
   labelled benchmark values;
2. the audited factual announcement copy was uploaded, parsed, attached to a new draft and
   approved with a 12-page outline;
3. job `01M0DA1AM1MGYVF41XRWQ6K85Q` completed on its first attempt with 12/12 stable pages,
   event sequence 31 and publication v1;
4. `GPT-5.6`, `91.9`, `92.2`, `74.3` and `2.8` remained intact, while the three data pages
   bound distinct Terminal-Bench 2.1, BrowseComp and SEC-Bench Pro series;
5. presentation `01CP2C9R1N5FDCT3XP8XWBK41B` opened in the editor as immutable revision
   `011M8VGBKSA0K4H5CVWQV8MVG6`, with all twelve pages editable and ready;
6. the Web export and a second independent HTTP→outbox→Redis→Celery exact-export request
   both reused canonical artifact `01EFM3NAY8GJ1XVT2Z66T6V6XJ` rather than rebuilding it;
7. the downloaded 54,086-byte PPTX matched canonical SHA-256
   `c617bd0c4d0e3e05fea829f9b575839cdb045e499f2fdd577d5b89293e6c13af`, contained 61
   visible strings with zero forbidden legacy matches, rendered all 12 pages, and passed the
   no-overflow check.

The final runtime deployment was built from clean Git commit
`ebed9ebb884b2196842ddc4d0a5ca6a2077c55c8`. API and all Worker-family containers expose
`instant-ppt-runtime@v2`; Worker, Agent Worker, outbox and Provider Gateway share image
`sha256:2d98d9ad3f5839052ee42fd93555ee3cd471bb3a04bac8f53e1b92b92e79234a`.

The journey used synthetic/local data. It did not send the final user topic or slide content
to an external live Provider. Previously approved redacted live Provider checks remain
separate evidence and do not weaken the deterministic regression boundary.

## Decision

ISSUE-002's core P0 closure conditions and the independent P1 image Release Gate are
satisfied. There is no waiver or skipped required case. The current release scope remains
owner-operated local use; the production KES/KMS control reopens before any external,
shared, hosted, QA/staging or production deployment.
