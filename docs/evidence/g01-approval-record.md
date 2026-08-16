# G01 approval record

## Upstream and third-party distribution

- Gate: `GATE-G01-UPSTREAM-LICENSE`
- Decision: approved
- Approver: Xiaobing Li, project owner / OSS compliance owner
- Checked at: 2026-08-16T10:29:09+08:00
- Scope: fixed `ppt-master` v4.7.0 MIT subtree, retained copyright/permission text, sponsors, attribution guard, and bundled third-party notices covering icon, sound and shape-data assets.

## PDF and EPUB dependency posture

- Gate: `GATE-G01-PDF-LICENSE`
- Decision: approved
- Approver: Xiaobing Li, project owner / OSS compliance owner
- Checked at: 2026-08-16T10:29:09+08:00
- Scope: `pypdf==6.16.1` under BSD-3-Clause; PyMuPDF/`fitz` and ebooklib remain absent; EPUB remains disabled; the documented text-only PDF limitations are accepted for P1.

The preceding sections capture the project owner's two explicit compliance approvals in the Codex task.

## PowerPoint and WPS visible compatibility

- Gate: `GATE-G01-POWERPOINT-WPS`
- Decision: approved
- Approver: Xiaobing Li, project owner / QA reviewer
- Checked at: 2026-08-16T10:38:18+08:00
- Scope: all ten three-slide golden decks opened in PowerPoint 16.0 build 20228 and WPS Presentation 12.1.0.28043; no repair, recovery, unsafe-link or font-substitution prompt; visible rendering accepted; title, body and native-shape changes survived save and reopen.
