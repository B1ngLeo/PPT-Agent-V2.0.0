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
| API and Domain                     | 35 passed; Ruff passed                                                       |
| Worker and engine boundary         | 64 passed; Ruff, attribution and direct-engine allowlist passed              |
| Web                                | ESLint, TypeScript and Next.js 16.2.11 production build passed               |
| G03 tenant/migration/object matrix | 8 passed; head downgrade/upgrade and zero drift                              |
| G06 generation/image matrix        | 11 passed                                                                    |
| G07 edit/exact-export matrix       | 5 passed                                                                     |
| G01 golden                         | 10/10 source and 10/10 render chains; 40 schema-bound artifacts              |
| Long-title no-source regression    | 8/8 final SVG files, 0 errors, 0 warnings; PPTX/package/content gates passed |

The image matrix includes provided-image analysis, a real subprocess calling a controlled
Fake HTTP image endpoint, independent picture/media embedding, idempotent quota/cost
settlement, explicit-path `needs_manual`, approved native fallback and provider-secret
scoping. The content matrix includes prompt-injection isolation, semantic citation support,
conflicting chart facts, stale reports, placeholder/author-task rejection, ending closure
and G07 effective-revision preservation.

## Final user journey

Using the production Web build and real API/Worker/database/object-store path, the browser
journey verified:

1. an approved eight-page outline with no source cannot start until the user explicitly
   chooses the limited general draft;
2. selective image controls enforce the entitlement cap and preserve original safe-page
   PNN values;
3. a required image with no enabled controlled Provider stops as `needs_manual`, with no
   silent omission and with a Chinese recovery action;
4. the no-image path publishes 8/8 pages and eleven artifact kinds as publication v1;
5. all eight pages contain distinct role-aware copy tied to the topic and the UI prominently
   discloses the unverified no-source boundary;
6. editing page 2 creates immutable revision 2 while retaining its stable slide identity;
7. exporting that exact revision succeeds after the real engine/package checks and issues a
   short-lived private download grant.

The journey used synthetic/local data. It did not send the final user topic or slide content
to an external live Provider. Previously approved redacted live Provider checks remain
separate evidence and do not weaken the deterministic regression boundary.

## Decision

ISSUE-002's core P0 closure conditions and the independent P1 image Release Gate are
satisfied. There is no waiver or skipped required case. The current release scope remains
owner-operated local use; the production KES/KMS control reopens before any external,
shared, hosted, QA/staging or production deployment.
