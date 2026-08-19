# G08 Windows screen-reader Gate

Status: **passed**. Xiaobing Li completed the named human review with Windows Narrator on
the local-only release scope.

The reviewer must record:

- reviewer name and role;
- date/time and Windows build;
- exact Chromium browser version;
- exact NVDA (or other Windows screen reader) version;
- pass/fail and issue IDs for every step below.

## Required main-flow steps

- [x] Sign in or enter the authenticated local test context and identify the page title.
- [x] Use the skip link and navigate the product/header landmarks.
- [x] Create a topic, choose a template and generate an outline without a mouse.
- [x] Read and edit intent fields, story summary and at least one slide title/body.
- [x] Approve the exact summary and start generation.
- [x] Read the progressbar name/value and live terminal status without focus theft.
- [x] Open the editable presentation, reorder a slide and request one-page regeneration.
- [x] Trigger and understand the partial-export guard/recovery action.
- [x] Export a bound revision, open history and restore the completed project.
- [x] At browser zoom 200%, repeat the critical controls at 390, 768 and 1440 CSS px.
- [x] Confirm focus visibility, dialog Escape/return focus, error announcements and that
      status is never conveyed by color alone.

## Sign-off

- Decision: passed for the owner-operated local-only release scope
- Reviewer: Xiaobing Li (project owner / named QA reviewer)
- Checked at: 2026-08-16T22:45:14+08:00
- Operating system: Microsoft Windows 11 Home China, version 10.0.22631, build 22631
- Browser/version: Google Chrome 151.0.7922.138
- Assistive technology/version: Windows Narrator 10.0.22621.4974
- Issues/results: all required steps passed; no issue IDs were reported

The named reviewer confirmed the result in the project task. Provider/privacy approval is
also complete, and production KES/KMS is explicitly deferred only for the local-only scope.
