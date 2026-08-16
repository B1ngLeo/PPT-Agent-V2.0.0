# G04 secure upload and Source parsing design

## Purpose and boundary

G04 turns the G01 file-system security harness into a tenant-scoped product flow for
DOCX, PDF, PPTX, and HTML. It owns short-lived upload sessions, private quarantine,
server-side byte verification, fail-closed malware and structural scanning, clean-only
parsing, immutable `SourceArtifact` publication, retry, and browser refresh recovery.
Draft attachment, intent inference, outline generation, and presentation generation
remain outside this goal.

The implementation is split across:

- `packages/domain`: `sources`, `upload_sessions`, `source_artifacts`, completion and
  retry transactions, serializers, audit, idempotency, and outbox records;
- `services/api`: presigned POST creation, streaming HEAD/SHA verification, status and
  retry endpoints, and explicit local Web CORS policy;
- `services/worker`: ClamAV INSTREAM client, G01 structural inspection, tenant-bound
  object promotion, parser execution, and artifact publication;
- `services/clamav`: pinned Debian ClamAV 1.4.3 service with deterministic integration
  signature, non-root user, read-only root, dropped capabilities, and resource limits;
- `apps/web`: accessible upload, live processing status, persisted recovery key, and
  bounded retry entry point.

## Upload and completion transaction

The create endpoint accepts only a display filename, declared MIME type, lowercase
SHA-256, and exact byte count. The filename is reduced to a safe basename and never
forms part of an object key. Extension and MIME must be one of four exact pairs, and
size is bounded to 25 MiB. The transaction creates one `Source` plus one
`UploadSession` under:

```text
tenants/{organizationId}/quarantine/{uploadSessionId}
```

The MinIO POST policy fixes the key, content type, checksum metadata, exact content
length, and expiration. An idempotent retry before upload re-signs the same session;
completed, rejected, or expired sessions cannot be re-signed.

`:complete` does not trust POST metadata. While holding the user's idempotency lock it
performs a real object `HEAD`, streams the object through SHA-256 with a hard byte
ceiling, and compares actual length, digest, content type, and checksum metadata.
Mismatch is committed as a stable rejected source. Success creates the tenant-scoped
quarantine `Artifact`, moves the source to `uploaded`, and inserts exactly one
`instant_ppt.process_source` outbox task in the same PostgreSQL transaction.

## Scan and clean boundary

The Worker locks the source using both source ID and organization from the task. It
also rechecks that the input artifact belongs to the same organization and has the
expected digest. Duplicate delivery is a no-op while a source is running or terminal.
The object is downloaded into a fresh bounded temporary directory and hashed again;
this detects overwrite after completion and before scanning.

ClamAV receives the bytes using `zINSTREAM` with four-byte big-endian chunks and a
zero-length terminator. Connection failure, timeout, malformed response, or scanner
error persists `SOURCE_SCANNER_UNAVAILABLE` and never promotes or parses the object.
After malware scanning, the G01 inspection checks:

- extension, declared MIME, detected type, and magic consistency;
- ZIP entry count, expanded size, compression ratio, depth, traversal, and symlinks;
- Office content types, package family, active embeddings, invalid relationships, and
  external targets;
- PDF magic, encryption, corruption, and page readability through approved `pypdf`;
- UTF-8 HTML, active elements, external attributes, and external CSS URLs.

Any finding leaves the object in quarantine and records an immutable decision bound
to object key and hash. A clean decision allows server-credential copy into the
tenant `clean` partition followed by quarantine deletion. The decision is rebound to
the clean key so the parser can prove it is consuming exactly the approved bytes.

## Clean-only parsing and publication

Parsing cannot start without a persisted `decision=clean` whose key and SHA-256 match
the local bytes. PDF uses `pypdf 6.16.1` under accepted ADR-003. DOCX, PPTX, and HTML
run only through the vendored `ppt-master` converter; HTML never performs an external
fetch. Container tasks have a 150-second soft limit, 180-second hard limit, read-only
root, bounded `/tmp`, no host mount, uid 10001, dropped capabilities, and CPU, memory,
PID, archive, and file-size limits.

Every Markdown, conversion profile, and extracted asset receives a new ULID and a
tenant `published` object key. Bytes are uploaded before one database transaction
creates immutable published `Artifact` and `SourceArtifact` rows, rewrites the
`SourcePackage` to those actual IDs, and marks the source parsed. SHA-256, size, MIME,
parser version, and retention are stored for every artifact. Duplicate tasks return
without another publication once the source is parsed.

## Failure, retry, and recovery

Upload, scan, and parse have independent persistent states and attempts. Scanner or
object-store availability failures and parser failures are retryable; structural,
malware, checksum, and tenant failures are not. Celery performs bounded automatic
retry for scanner, storage, database, and adapter failures. A user retry creates one
new deduplicated outbox row and resumes at scan or parse according to the last clean
boundary. Both attempt counters are database-constrained to five.

The source status endpoint is sufficient to rebuild UI state after refresh, API
restart, or navigation. The Web client stores only the active source ID in
`sessionStorage`, polls the tenant-protected API, removes the recovery key on success,
and exposes retry only when the server marks the source retryable. It never receives
permanent public object URLs.

## Verification boundary

The [G04 evidence](../evidence/g04-secure-source-pipeline.md) maps the automated and
container checks. The real integration matrix uses PostgreSQL and MinIO with a
deterministic clamd protocol fixture for exhaustive cases. A separate container
journey uses the actual ClamAV 1.4.3 daemon, API, transactional outbox, Celery Worker,
MinIO promotion, parser, and published artifacts. The production signature updater
and operational freshness alert belong to G08; scanner unavailability remains
fail-closed in every environment.
