# G07 editor, export, history, and deletion evidence

## Result

G07 passed. The bounded editor preserves immutable lineage and stable slide IDs;
single-slide regeneration keeps the old ready version until candidate QA; exports
bind an exact revision; private downloads stay on the editor route; history
restores persisted result state; and deletion fails closed before audited object
cleanup completes.

## Automated matrix

`pnpm verify:integration:g07` passes 4/4 PostgreSQL/engine lifecycle scenarios:

- immutable optimistic text/move/delete operations, stale-write `412`, minimum one
  page, stable identities, and tenant `404`;
- old-ready visibility, candidate QA, stable-ID regeneration, lineage, and atomic
  revision switch;
- concurrent edit after export queueing, exact revision manifest, real native PPTX
  structure, package QA, tenant-scoped download authorization, and usage;
- partial export rejection, explicit missing-page acceptance, project snapshot,
  history result routing, immediate API/SSE denial, and idempotent object cleanup.

The shared G03 download suite remains part of root verification and covers
15-second real MinIO expiry, tampering, retention expiry, idempotent authorization
expiry (`410`), re-signing without persisted URLs, and cross-tenant denial.

## Production browser journey

An eight-page real generation was opened from its result route. The user edited the
cover title/body, moved another stable slide ahead of it, reloaded, and observed
the same values and order. The first stable slide was regenerated with an inline
instruction: revision 3 stayed visible until QA, then revision 4 switched to a new
slide version while retaining the slide ID.

The exact revision exported to a 25,787-byte named PPTX; the structured project
snapshot exported to an 8,119-byte named JSON file. Both downloads used Blob URLs
and retained the Presentation route. History showed `结果 · ready` and reopened
revision 4. At 390×844 all editor/export/history controls remained present; the
semantic regions, labels, native controls, and keyboard skip link were verified.

## Deletion and audit

Before deletion the export URL returned 200 and 25,787 bytes. Deleting the exact
test Draft returned 204. The cleanup Worker reported 22 artifacts, 22 removed
objects, and zero failures; all 22 Artifact rows became revoked/deleted. The
Presentation API, generation-job API, SSE endpoint, old signed URL, and a new
download-grant request all returned 404 afterward.

Machine-readable browser evidence is in
[`g07-browser-e2e.json`](g07-browser-e2e.json), and the integration report is in
[`g07-editor-export-junit.xml`](g07-editor-export-junit.xml).
