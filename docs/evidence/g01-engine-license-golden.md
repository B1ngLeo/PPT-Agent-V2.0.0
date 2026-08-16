# G01 engineering evidence

## Result

All automatable G01 engineering checks pass. The project owner approved the two OSS/dependency compliance Gates and completed the named PowerPoint/WPS visible-window QA review on 2026-08-16. `pnpm verify:gates --goal G01` passes all three required Gates.

| Area                |                                                                             Result | Evidence                                                                                                         |
| ------------------- | ---------------------------------------------------------------------------------: | ---------------------------------------------------------------------------------------------------------------- |
| Vendor provenance   |           fixed v4.7.0 / `e8323bfa…`; 12,907 files; tree and protected hashes pass | `vendor/ppt-master.vendor.json`, `scripts/verify_vendor.py`                                                      |
| Adapter contracts   |                   request/response/security schemas; automated sole-boundary guard | `services/worker/contracts`, [adapter design](../design/g01-engine-adapter.md)                                   |
| Source security     |                                                        13/13 rejected before parse | [security JSON](g01-security-results.json), [security design](../security/g01-source-intake.md)                  |
| Source golden chain |                                      10/10 SourcePackages match approved baselines | [golden JSON](g01-golden-results.json)                                                                           |
| Render golden chain |                     10/10 decks, 30/30 slides, upstream SVG QA 0 errors/0 warnings | [golden JSON](g01-golden-results.json)                                                                           |
| Contract/package QA | 40 schema artifacts; 103/103 planned texts; 123 native shapes; 190 valid relations | [golden JSON](g01-golden-results.json)                                                                           |
| Supply chain        |  Python 53 / Node 213 CycloneDX components; no PyMuPDF, ebooklib, or bundled fonts | [supply-chain JSON](g01-supply-chain.json), [Python SBOM](sbom-python.cdx.json), [Node SBOM](sbom-node.cdx.json) |
| Worker container    |  fixed base digests; stable image `sha256:d3d52adf…`; non-root; attribution intact | [container JSON](g01-container.json)                                                                             |
| PowerPoint          |                                 10/10 open/editable/PNG export on 16.0 build 20228 | [PowerPoint JSON](g01-powerpoint-compatibility.json)                                                             |
| WPS                 |                                     10/10 open/editable/PNG export on 12.1.0.28043 | [WPS JSON](g01-wps-compatibility.json)                                                                           |
| Cross-app visual    |                        30/30 1280×720 pairs; observed max mean 4.2066, RMS 14.6588 | [visual JSON](g01-visual-diff.json)                                                                              |

## Reproduction

```powershell
pnpm verify:g01:automated

# Or run each stage independently:
pnpm verify:contracts
pnpm verify:worker
pnpm verify:security
pnpm verify:golden
pnpm verify:supply-chain
pnpm verify:container
pnpm verify:powerpoint
pnpm verify:wps
pnpm verify:visual
```

The PowerPoint/WPS scripts delete only prior generated PNG files below the exact `.tmp/compatibility/<application>/<case>` directory before exporting a fresh baseline.

## Gate result

See the completed [human Gate checklist](g01-human-gate-checklist.md), [approval record](g01-approval-record.md), and [manual QA deck list](g01-qa-review.md). G01 is complete and G02 may proceed.

The requirement-by-requirement status and ownership boundary are recorded in the [G01 completion audit](g01-completion-audit.md).
