# ADR-012: Main Presentation Agent authoring and explicit template fallback

- Status: accepted
- Date: 2026-08-23; amended by ISSUE-004 on 2026-08-26, 2026-08-27 and 2026-08-28
- Decision owners: Product and Engineering

## Context

The historical `default-agentic` label described an orchestration profile, but its pages were authored by a fixed Python renderer. Logs could therefore imply Agent authorship without a model turn, tool decision, observation, revision, and termination record. ISSUE-003 requires those facts to be provable and requires a reliable fallback without misrepresenting it as Agent output.

## Decision

1. New generation snapshots freeze a server-owned `authoringPolicy`. `PRESENTATION_AUTHORING_MODE=agent-authoring` is the default; `deterministic-template` is the rollback flag. A running or published snapshot is never changed by a later flag update.
2. `agent-authoring` uses one resumable Main Presentation Agent session: Strategist first, then sequential Executor phases. The supervisor enforces tool allowlists, turn/token/cost/time budgets, attempts, cancellation, fencing, and hash-bound checkpoints. Every authored page must bind to persisted model-turn and tool-call evidence.
3. A read-only multimodal reviewer may return structured observations. The Main Agent owns repairs. ISSUE-004 replaces the fixed two-round loop with adaptive review: zero blocking passes immediately; stable finding fingerprints and lexicographic quality metrics detect progress; two stagnant rounds or a regression restore the best Direct SVG snapshot and hand off to humans; five review calls is the hard limit.
4. `deterministic-template` uses the retained `author_slide()` renderer without Provider or Agent tool calls. It has its own workflow profile, state, manifest fields, UI copy, metrics, and filename suffix `-模板化受限初稿.pptx`. It never produces an Agent author receipt and is excluded from Agent success rates.
5. Both modes retain attribution, approved-source isolation, content/SVG/chart/package gates, immutable revisions, exact export, and tenant controls. Usage settlement includes model tokens and configured micro-unit cost without duplicate charging on replay.
6. Canary safety failures involving security, tenant isolation, grounding, cancellation/recovery, compatibility, or publication consistency require admission rollback to `deterministic-template`. A visual preference regression alone enters human review and never rewrites an approved revision.
7. ISSUE-004 makes validated Direct SVG the sole page authoring representation. New runs neither generate nor consume Scene Graph artifacts; historical published evidence remains immutable and old frozen requests retain their recorded review limit.
8. ISSUE-004 workflow v3 removes Page Blueprint and all equivalent page contracts. The Strategist directly reads the approved Intent, Outline, complete source boundary, template/image/review policy and authors `design_spec.md`. A recorded `strategist-design-and-lock` authorization and hash-bound `design-confirmation` receipt are mandatory before `spec_lock.md` and Executor; absent confirmation, the run stops at `awaiting_design_confirmation` with no page SVG.
9. ADR-013 makes pinned PPT Master `v4.7.0` the sole page-contract authority for
   new `presentation-authoring@v3-ppt-master-authority` snapshots. Strategist
   authors the native Design Spec and Spec Lock from the complete vendored
   references; Executor P01 records hash-bound reads of the complete required
   upstream references. Local title markers, fixed title sizes, exact Outline-title
   matching, footer placement, and application-specific root roles are removed from
   the new write-time gate. Legacy frozen snapshots retain their recorded behavior.

## Consequences

- Agent output is less deterministic and may cost more, so inputs, versions, budgets, observations, artifacts, and outcomes are persisted.
- The fallback remains available and operationally useful, but users always see its limited-draft identity.
- Rolling back the feature flag affects only new snapshots. Existing revisions and their exact downloads remain immutable.
- Provider/privacy disclosure now covers approved source fragments and rendered review images sent to the configured text Provider.
- The workflow relies on final content/fact/SVG/chart/package gates instead of a pre-generation lexical-support score, avoiding false rejection of approved Chinese outlines while retaining fail-closed numeric and source checks.
