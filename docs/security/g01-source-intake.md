# G01 source intake security spike

## Fail-closed rule

A source begins in an untrusted local fixture location. `scanSource` computes SHA-256 and writes a decision without moving or parsing the file. `parseSource` accepts only a readable `clean` decision whose `sourceKey` and `sourceSha256` still match the current bytes. Rejected, missing, stale, or malformed decisions fail before any parse output directory is created.

G04 will productize this contract using private `quarantine`/`clean` object partitions and a network scanner. G01 intentionally has no upload HTTP endpoint or tenant workflow.

## Checks

- extension, magic, and supported MIME family agree;
- text/HTML is UTF-8; HTML has no active elements or external URL-bearing attributes;
- PDFs open, are not encrypted, and remain below size limits;
- Office packages are valid ZIP containers with content types and expected root parts;
- ZIP entry count, expanded size, nesting depth, per-entry compression ratio, traversal, and symbolic links stay within limits;
- Office relationship XML is parseable and contains no external targets;
- embedded/active Office payloads are rejected;
- the harmless antivirus canary follows the same fail-closed error route without triggering endpoint protection before the test can run.

The 13-fixture matrix covers corrupt and encrypted files, active/external HTML, magic mismatch, antivirus canary, ZIP traversal/depth/ratio/symlink/count, and external Office relationships. [Machine evidence](../evidence/g01-security-results.json) records `13/13 rejected` and `0 reached parse`.

## Known boundary

The deterministic canary is not a substitute for ClamAV signature coverage. Compose already fixes the ClamAV service for G04; production promotion will require unavailable/scanner-error fail-closed tests and quarantine-to-clean object moves. G01 proves the decision binding and parser exclusion invariant independently of that orchestration.
