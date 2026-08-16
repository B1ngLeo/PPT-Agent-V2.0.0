# ADR-003: PDF parser licensing

- Status: accepted
- Date: 2026-08-16
- Owners: legal, engineering
- Related SPEC: 1, 10.3, 16

## Context

PyMuPDF is dual licensed and its open-source option is not presumed compatible with proprietary SaaS distribution.

## Decision

Use `pypdf==6.16.1` as the P1 text-oriented PDF parser. Its installed package metadata declares the SPDX expression `BSD-3-Clause`. Do not install or invoke PyMuPDF/`fitz`; the normalized Python SBOM asserts that neither name is present.

The source-security boundary rejects encrypted and corrupt PDFs before parsing. The adapter invokes `PdfReader(..., strict=False)`, rejects any encrypted reader, and extracts page text only. This baseline does not claim visual-layout, OCR, complex-table, or scanned-document fidelity; those capabilities need a separate approved design and license decision.

EPUB remains disabled. `ebooklib` is absent from the lockfile/SBOM, the adapter accepts no EPUB extension, and no release UI may advertise EPUB support.

The project owner and OSS compliance owner accepted this decision on 2026-08-16. The approval is recorded in `docs/evidence/g01-approval-record.md` and `GATE-G01-PDF-LICENSE`.

## Verification

- `services/worker/pyproject.toml` and `uv.lock` pin `pypdf==6.16.1`.
- `docs/evidence/sbom-python.cdx.json` and `docs/evidence/g01-supply-chain.json` record the dependency boundary.
- Golden case `09-pdf-baseline` passes source parsing and render chains.
- Security fixtures `encrypted.pdf` and `corrupt.pdf` are rejected before parse.
