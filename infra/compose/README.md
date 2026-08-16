# Local service topology

The stable entry point is the repository-root `compose.yaml`.

- PostgreSQL is the future business truth source.
- Redis is limited to queues, short-lived cache, and event fan-out.
- MinIO represents a private S3-compatible object store.
- ClamAV is the fail-closed malware scanner used by later source-ingestion goals.

Run `docker compose config` before starting services. G00 validates configuration only; service-level integration begins in G01/G02.
