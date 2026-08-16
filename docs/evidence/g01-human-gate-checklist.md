# G01 human Gate checklist

Automated evidence is complete. A named reviewer must perform and sign each item; do not change Gate status to `passed` without the approver and timestamp.

## Legal: upstream distribution

- [x] Review `vendor/ppt-master/LICENSE`, copyright, `SPONSORS.md`, `SPONSORS_CN.md`, bundled third-party notices, and fixed provenance.
- [x] Confirm the planned proprietary SaaS/container distribution may retain this unmodified vendor subtree and its attribution.
- [x] Record approver and time on `GATE-G01-UPSTREAM-LICENSE`.

## Legal: PDF/EPUB

- [x] Accept ADR-003 and its `pypdf==6.16.1` BSD-3-Clause path.
- [x] Confirm PyMuPDF/`fitz` and ebooklib are absent from the normalized SBOM.
- [x] Confirm EPUB remains disabled and PDF limitations are acceptable for P1.
- [x] Record approver and time on `GATE-G01-PDF-LICENSE`.

## QA: visible compatibility

- [x] Open all ten generated decks in visible Microsoft PowerPoint 16.0 build 20228 and WPS 12.1.0.28043 windows.
- [x] Confirm neither application displays a repair, recovery, font-substitution, or unsafe-link prompt.
- [x] Edit a title, body line, and agreed geometric shape; save a copy; reopen it.
- [x] Review Chinese, English, long-title, dense-content, font-fallback, template, PDF, and multilingual cases at 100% zoom.
- [x] Compare against the 30 automated PNG pairs and classify any variance using the severity policy.
- [x] Record named reviewer and time on `GATE-G01-POWERPOINT-WPS`.

The two compliance approvals and the completed QA review were explicitly provided by Xiaobing Li on 2026-08-16. See [approval record](g01-approval-record.md) and [manual QA deck list](g01-qa-review.md).

If any item fails, set the Gate to `failed`, link the finding, and do not cross the G01/P0 boundary.
