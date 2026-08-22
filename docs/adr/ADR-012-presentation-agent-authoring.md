# ADR-012: Main Presentation Agent authoring and explicit template fallback

- Status: accepted
- Date: 2026-08-23
- Decision owners: Product and Engineering

## Context

The historical `default-agentic` label described an orchestration profile, but its pages were authored by a fixed Python renderer. Logs could therefore imply Agent authorship without a model turn, tool decision, observation, revision, and termination record. ISSUE-003 requires those facts to be provable and requires a reliable fallback without misrepresenting it as Agent output.

## Decision

1. New generation snapshots freeze a server-owned `authoringPolicy`. `PRESENTATION_AUTHORING_MODE=agent-authoring` is the default; `deterministic-template` is the rollback flag. A running or published snapshot is never changed by a later flag update.
2. `agent-authoring` uses one resumable Main Presentation Agent session: Strategist first, then sequential Executor phases. The supervisor enforces tool allowlists, turn/token/cost/time budgets, attempts, cancellation, fencing, and hash-bound checkpoints. Every authored page must bind to persisted model-turn and tool-call evidence.
3. A read-only multimodal reviewer may return structured observations. The Main Agent owns repairs. At most two visual-review rounds are allowed; unresolved blocking findings produce a non-success state and no complete publication.
4. `deterministic-template` uses the retained `author_slide()` renderer without Provider or Agent tool calls. It has its own workflow profile, state, manifest fields, UI copy, metrics, and filename suffix `-模板化受限初稿.pptx`. It never produces an Agent author receipt and is excluded from Agent success rates.
5. Both modes retain attribution, approved-source isolation, content/SVG/chart/package gates, immutable revisions, exact export, and tenant controls. Usage settlement includes model tokens and configured micro-unit cost without duplicate charging on replay.
6. Canary safety failures involving security, tenant isolation, grounding, cancellation/recovery, compatibility, or publication consistency require admission rollback to `deterministic-template`. A visual preference regression alone enters human review and never rewrites an approved revision.

## Consequences

- Agent output is less deterministic and may cost more, so inputs, versions, budgets, observations, artifacts, and outcomes are persisted.
- The fallback remains available and operationally useful, but users always see its limited-draft identity.
- Rolling back the feature flag affects only new snapshots. Existing revisions and their exact downloads remain immutable.
- Provider/privacy disclosure now covers approved source fragments and rendered review images sent to the configured text Provider.
