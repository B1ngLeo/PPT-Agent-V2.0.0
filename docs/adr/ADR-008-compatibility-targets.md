# ADR-008: PowerPoint and WPS compatibility targets

- Status: accepted
- Date: 2026-08-16
- Owners: qa, product, engineering
- Related SPEC: 12.3, 13.3

## Decision

The G01 evidence targets these installed desktop builds:

- Microsoft PowerPoint object model `16.0`, build `20228`, Office16 installation;
- WPS Presentation `12.1.0.28043` through registered `KWPP.Application` compatibility automation.

All ten golden decks must open read-only without an automation exception, expose their three slides and editable text shapes, and export 30 PNGs at 1280×720 in each application. PowerPoint/WPS pairs must remain below max-channel mean difference `8.0` and RMS difference `30.0`; the current observed maxima are recorded, not hard-coded as approval.

Suppressed COM automation cannot truthfully observe a visible repair dialog and does not replace a named human check. Xiaobing Li completed the named QA review of all ten decks in both target applications on 2026-08-16 and confirmed no repair prompt plus successful edit/save/reopen behavior. The approval is recorded in `docs/evidence/g01-approval-record.md`.

## Verification

`docs/evidence/g01-powerpoint-compatibility.json`, `docs/evidence/g01-wps-compatibility.json`, `docs/evidence/g01-visual-diff.json`, a visible-window human checklist, and G08 regression.
