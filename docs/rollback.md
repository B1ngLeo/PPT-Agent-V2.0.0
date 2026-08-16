# P1 rollback procedure

## Preconditions

Declare the incident, freeze new releases, capture current image digests, Alembic head,
alert state and a database/object backup. A rollback never authorizes destructive repair
or cross-tenant access.

## Application-first rollback

1. Stop admission of new generation/export work while allowing safe reads.
2. Set API, Worker and outbox images to the last approved immutable digests.
3. Recreate API first, then outbox and Worker. Confirm non-root users and read-only
   Worker filesystem controls are unchanged.
4. Require `/healthz` and `/readyz` 200, then run authentication, history, job recovery,
   export download, private-bucket encryption/lifecycle and metrics smoke checks.
5. Resume admission only after outbox age and running-job recovery stabilize.

G08 adds only `object_reconciliation_runs`; the preceding G07 application ignores this
table, so an application rollback may leave the G08 schema in place. This is the default
and safest path.

## Schema rollback

Schema downgrade is exceptional. Drain API/Worker/outbox, take a fresh backup, prove no
G08 reconciliation task is running, and restore-test the backup first. In an isolated
target, validate:

```powershell
python -m uv run --package instant-ppt-api alembic -c packages/domain/src/instant_ppt_domain/alembic.ini downgrade -1
python -m uv run --package instant-ppt-api alembic -c packages/domain/src/instant_ppt_domain/alembic.ini upgrade head
python -m uv run --package instant-ppt-api alembic -c packages/domain/src/instant_ppt_domain/alembic.ini check
```

Do not execute the downgrade against production until engineering and incident command
approve the exact database target and accept loss of G08 reconciliation-run audit rows.

## Roll-forward and closeout

Prefer a fixed roll-forward after service stability. Re-run the affected E2E, recovery,
security and compatibility checks, reconcile objects, compare usage settlements, and
record the incident timeline plus exact digests in the release report.
