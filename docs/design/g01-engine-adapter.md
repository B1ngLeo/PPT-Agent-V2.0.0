# G01 engine adapter design

## Purpose and boundary

`engine-adapter` is the only product-facing invocation boundary around the fixed `ppt-master` vendor tree. Web and API code do not import upstream modules. The adapter accepts versioned JSON plus object-like relative keys under one local fixture root; it has no database, Redis, object-store, identity, browser-session, or secret settings.

G01 proves two deterministic engineering chains:

1. `source bytes → scan decision → SourcePackage`;
2. `approved DeckPlan → canonical SVG → upstream final QA → native PPTX → package QA`.

It does not claim LLM content quality, multi-tenant orchestration, or production upload handling.

## Operations

| Operation     | Required inputs                                      | Preconditions                                                         | Outputs                                                                                |
| ------------- | ---------------------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `scanSource`  | `workspaceRoot`, `inputKey`, `outputKey`             | input key resolves below the local root                               | hash-bound `SecurityDecision`                                                          |
| `parseSource` | source key, decision key, output key, source/org IDs | decision is `clean`; decision key and SHA-256 match current bytes     | Markdown, conversion profile, `SourcePackage`, assets                                  |
| `renderDeck`  | approved DeckPlan key, output key, org ID            | DeckPlan v1 validates; orders are contiguous; all slides are editable | canonical SVGs, upstream QA, PPTX, package QA, preview, `QaReport`, `ArtifactManifest` |

The request, response, and security-decision schemas live in `services/worker/contracts`. Pydantic uses discriminated operation models with unknown fields forbidden. Stable errors include `ENGINE_INVALID_REQUEST`, `SOURCE_SECURITY_REJECTED`, `SOURCE_CLEAN_DECISION_REQUIRED`, `SOURCE_CLEAN_DECISION_MISMATCH`, `SOURCE_PARSE_FAILED`, `ENGINE_QA_FAILED`, `ENGINE_RENDER_FAILED`, and `ENGINE_PACKAGE_INVALID`.

## Render invariants

- SVG is authored at `1280×720` with canonical page roles, explicit root-module bounds, stable IDs, local fills, and no external references.
- The upstream final QA report must bind to the exact SVG roster fingerprint and contain zero errors. Golden baselines additionally require zero warnings.
- `svg_to_pptx.py --quick-generate` is invoked only after that report exists.
- PPTX ZIP timestamps are normalized to a fixed value so identical inputs have stable hashes.
- Slide DrawingML replaces shape-autofit with explicit no-autofit after compilation; text boxes retain their native positions and stay editable across PowerPoint/WPS.
- Package QA reopens the ZIP and `python-pptx` model, resolves every internal OPC relationship target, rejects missing/escaping targets, external links and orphan media, and checks slide counts, every planned title/body text instance, native editable-shape coverage, full-slide bitmap fallback, preview generation, and manifest hash.
- `scripts/g01/verify_engine_boundary.py` prevents Web, API and contract packages from importing Worker internals or referencing the vendor tree; only the allowlisted adapter implementation may invoke fixed engine scripts.

## Reproducible runtime

The Worker image pins both base images by OCI index digest, installs from `uv.lock --frozen`, runs the upstream attribution guard at build time, and runs as `10001:10001`. Dynamic BuildKit provenance is disabled only for the local reproducibility assertion; CycloneDX SBOMs are generated separately from both lockfiles. The image contains no business credential environment variables.

## Verification

```powershell
pnpm verify:worker
pnpm verify:security
pnpm verify:golden
pnpm verify:supply-chain
pnpm verify:container
```

Implementation evidence is summarized in [G01 evidence](../evidence/g01-engine-license-golden.md).
