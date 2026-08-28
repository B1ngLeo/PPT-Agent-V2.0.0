# ADR-013: PPT Master is the page contract authority

- Status: accepted
- Date: 2026-08-28
- Decision owners: Product, Engineering, Presentation Quality
- Related: ADR-004, ADR-012, ISSUE-004

## Context

The application had accumulated local page rules around PPT Master's authoring
flow: a non-upstream `Slide NN / PNN - title` Design Spec heading, a locally
generated Spec Lock, fixed title markers and sizes, exact Outline-title matching,
fixed page-number placement, and application-specific root roles. These rules
could reject an otherwise valid page before the pinned upstream checker and
converter evaluated it, creating two competing sources of page semantics.

## Decision

For new `presentation-authoring@v3-ppt-master-authority` snapshots, the vendored
PPT Master `v4.7.0` references and machine schemas are the only page-authoring
authority:

1. Approved Sources and Outline are Strategist inputs. `design_spec.md` §IX is
   the sole page plan, `spec_lock.md` is the sole cross-page execution lock, and
   complete SVG is the visible page source.
2. Design Spec uses the upstream `Slide NN - <page name>` form. PNN, `slideId`,
   tenant identity, storage keys, and recovery identity remain application data
   and are not serialized into the Design Spec.
3. The Strategist reads the complete pinned Design Spec and Spec Lock references,
   authors both artifacts, and submits the lock to the original
   `project_manager.py validate` command. The local deterministic lock builder is
   retained only for the explicitly disclosed template fallback and legacy frozen
   snapshots.
4. Executor P01 reads a read-only allowlisted set of complete vendored Executor,
   shared, semantic SVG, effects, and native-shape references plus lock-triggered
   branches. Each read records path, pinned version, SHA-256, and tool-call evidence;
   later pages reuse the hash-bound receipt.
5. The application SVG write boundary enforces page ownership, payload size,
   well-formed XML, exact canvas, project-local images, safe URI schemes, and an
   active-content deny-list. Title markers/text, title size, footer position,
   layout, and page roles are not application write-time blockers.
6. Flat and structured SVG semantics, original checker results, and converter
   behavior remain owned by PPT Master. The product may publish a mechanically
   generated PPTX with disclosed deterministic warnings, but malformed XML,
   dangerous references, missing files, and actual compile/write failures remain
   failures.

This policy is frozen only into new workflow `instant-ppt-default@v3.2.0`
snapshots. Older snapshots retain their recorded authoring policy and legacy
validation behavior; no historical artifact or receipt is rewritten.

## Consequences

- Runtime prompt summaries no longer duplicate title, page-number, font-size, or
  application-role rules.
- Upstream reference hashes become required Executor evidence and detect vendor
  drift before P01 authorship can be accepted.
- Page titles may be refined by the Strategist while page count/order, user-explicit
  wording, topic, approved facts, and persistent page identity remain protected.
- A PPT Master upgrade is a separate vendor decision and regression matrix, not an
  implicit page-contract change.

## Verification

Worker contract/unit/integration tests cover native §IX headings, Strategist lock
authorship and upstream validation, reference allowlisting and SHA-256 receipts,
flat canonical roles, structured reference branching, permissive title/footer
layout, and fail-closed active content. The official Qwen/PowerPoint/WPS release
comparison remains a deployment evidence activity recorded by ISSUE-004.
