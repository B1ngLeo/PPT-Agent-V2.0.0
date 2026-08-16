from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from instant_ppt_domain.config import DEFAULT_DATABASE_URL
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    Draft,
    GenerationJob,
    GenerationSnapshot,
    JobEvent,
    TemplateVersion,
)
from instant_ppt_domain.tenancy import LOCAL_ISSUER, IdentityClaims, provision_identity
from instant_ppt_domain.workspace import seed_builtin_templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return round(ordered[index], 3)


def _memory_bytes() -> int | None:
    if platform.system() != "Windows":
        with suppress(OSError, ValueError, AttributeError):
            return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
        return None
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong),
            ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong),
            ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(MemoryStatus)
    return int(status.total_physical) if ctypes.windll.kernel32.GlobalMemoryStatusEx(  # type: ignore[attr-defined]
        ctypes.byref(status)
    ) else None


def _container_images() -> dict[str, str]:
    names = (
        "instant-ppt-api:latest",
        "instant-ppt-worker:latest",
        "postgres:17.6-alpine",
    )
    result: dict[str, str] = {}
    for name in names:
        completed = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", name],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            result[name] = completed.stdout.strip()
    return result


def _seed(factory: sessionmaker[Session]) -> list[dict[str, str]]:
    now = datetime.now(UTC)
    users: list[dict[str, str]] = []
    with factory.begin() as session:
        seed_builtin_templates(session)
        session.flush()
        template_version_id = session.scalar(
            select(TemplateVersion.id).order_by(TemplateVersion.created_at)
        )
        assert template_version_id is not None

        for user_index in range(100):
            subject = f"g08-perf-{new_ulid().lower()}-{user_index:03d}"
            context = provision_identity(
                session,
                IdentityClaims(
                    issuer=LOCAL_ISSUER,
                    subject=subject,
                    email=f"{subject}@local.invalid",
                    display_name=f"G08 Perf {user_index:03d}",
                ),
            )
            draft_ids: list[str] = []
            for draft_index in range(10):
                draft_id = new_ulid()
                draft_ids.append(draft_id)
                session.add(
                    Draft(
                        id=draft_id,
                        organization_id=context.organization_id,
                        owner_user_id=context.user_id,
                        title=f"Performance draft {draft_index:02d}",
                        topic=f"Fixed performance dataset {user_index:03d}-{draft_index:02d}",
                        mode="native",
                        template_version_id=template_version_id,
                        status="draft",
                        lock_version=1,
                    )
                )
            session.flush()

            snapshot_id = new_ulid()
            job_id = new_ulid()
            snapshot_payload = {
                "schemaVersion": 1,
                "performanceDataset": True,
                "organizationIndex": user_index,
            }
            session.add(
                GenerationSnapshot(
                    id=snapshot_id,
                    organization_id=context.organization_id,
                    draft_id=draft_ids[0],
                    intent_revision_id=new_ulid(),
                    outline_revision_id=new_ulid(),
                    template_version_id=template_version_id,
                    mode_id="native",
                    source_hashes=[],
                    prompt_version="g08-performance",
                    engine_version="ppt-master-v4.7.0-e8323bfa",
                    container_version="g08-performance",
                    font_pack_version="windows-baseline",
                    provider_config_version="fake-v1",
                    snapshot_sha256=hashlib.sha256(
                        f"g08-performance-{context.organization_id}".encode()
                    ).hexdigest(),
                    payload=snapshot_payload,
                )
            )
            session.flush()
            session.add(
                GenerationJob(
                    id=job_id,
                    organization_id=context.organization_id,
                    snapshot_id=snapshot_id,
                    processor="fake",
                    status="succeeded",
                    stage="publishing",
                    latest_seq=100,
                    attempt=1,
                    publication_version=1,
                    progress_completed=1,
                    progress_total=1,
                    terminal_at=now,
                )
            )
            session.flush()
            session.add_all(
                [
                    JobEvent(
                        id=new_ulid(),
                        organization_id=context.organization_id,
                        job_id=job_id,
                        seq=seq,
                        event_type="job.progress" if seq < 100 else "job.succeeded",
                        snapshot_id=snapshot_id,
                        attempt=1,
                        stage="publishing",
                        status="succeeded" if seq == 100 else "running",
                        progress_completed=1 if seq == 100 else 0,
                        progress_total=1,
                        data={"performanceDataset": True},
                        trace_id=hashlib.sha256(f"{job_id}:{seq}".encode()).hexdigest()[:32],
                        occurred_at=now,
                    )
                    for seq in range(1, 101)
                ]
            )
            session.add_all(
                [
                    Artifact(
                        id=new_ulid(),
                        organization_id=context.organization_id,
                        artifact_type="performance_fixture",
                        partition="tmp",
                        object_key=(
                            f"tenants/{context.organization_id}/tmp/performance/{index:02d}"
                        ),
                        sha256=hashlib.sha256(
                            f"{context.organization_id}:{index}".encode()
                        ).hexdigest(),
                        media_type="application/octet-stream",
                        size_bytes=0,
                        status="deleted",
                        retention_expires_at=now + timedelta(days=1),
                        revoked_at=now,
                        deleted_at=now,
                    )
                    for index in range(10)
                ]
            )
            users.append(
                {
                    "subject": subject,
                    "draftId": draft_ids[0],
                    "organizationId": context.organization_id,
                }
            )
    return users


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    headers: dict[str, str],
    **kwargs: Any,
) -> tuple[int, float, httpx.Response]:
    started = time.perf_counter()
    response = await client.request(method, path, headers=headers, **kwargs)
    return response.status_code, (time.perf_counter() - started) * 1000, response


async def _window(
    base_url: str,
    users: list[dict[str, str]],
    duration_seconds: int,
    *,
    collect: bool,
    virtual_users: int,
    think_time_ms: int,
) -> dict[str, list[float] | int]:
    reads: list[float] = []
    writes: list[float] = []
    errors = 0
    deadline = time.perf_counter() + duration_seconds
    limits = httpx.Limits(max_connections=60, max_keepalive_connections=40)
    async with httpx.AsyncClient(
        base_url=base_url, timeout=10, limits=limits, trust_env=False
    ) as client:

        async def virtual_user(user: dict[str, str]) -> None:
            nonlocal errors
            sequence = 0
            headers = {
                "X-Dev-User-Subject": user["subject"],
                "X-Dev-User-Email": f"{user['subject']}@local.invalid",
                "X-Dev-User-Name": "G08 Performance User",
            }
            while time.perf_counter() < deadline:
                sequence += 1
                try:
                    if sequence % 10:
                        status, latency, _ = await _request(
                            client, "GET", "/v1/me/entitlements", headers
                        )
                        if collect:
                            reads.append(latency)
                    else:
                        status, _, current = await _request(
                            client, "GET", f"/v1/drafts/{user['draftId']}", headers
                        )
                        if status == 200:
                            write_headers = {**headers, "If-Match": current.headers["ETag"]}
                            status, latency, _ = await _request(
                                client,
                                "PATCH",
                                f"/v1/drafts/{user['draftId']}",
                                write_headers,
                                json={
                                    "schemaVersion": 1,
                                    "data": {"topic": f"performance-update-{sequence}"},
                                    "baseRevisionId": None,
                                },
                            )
                            if collect:
                                writes.append(latency)
                    if not 200 <= status < 300:
                        errors += 1
                except (httpx.HTTPError, KeyError):
                    errors += 1
                await asyncio.sleep(think_time_ms / 1000)

        await asyncio.gather(*(virtual_user(user) for user in users[:virtual_users]))
    return {"reads": reads, "writes": writes, "errors": errors}


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "samples": len(values),
        "meanMs": round(statistics.fmean(values), 3) if values else 0.0,
        "p50Ms": _percentile(values, 0.50),
        "p95Ms": _percentile(values, 0.95),
        "p99Ms": _percentile(values, 0.99),
        "maxMs": round(max(values), 3) if values else 0.0,
    }


def _wait_for_api(base_url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/internal/metrics", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.25)
    raise RuntimeError("performance API did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warmup-seconds", type=int, default=120)
    parser.add_argument("--measurement-seconds", type=int, default=600)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-workers", type=int, default=4)
    parser.add_argument("--virtual-users", type=int, default=20)
    parser.add_argument("--think-time-ms", type=int, default=500)
    args = parser.parse_args()
    if (
        args.warmup_seconds < 0
        or args.measurement_seconds < 1
        or not 1 <= args.api_workers <= 32
        or not 1 <= args.virtual_users <= 100
        or args.think_time_ms < 0
    ):
        raise SystemExit("invalid performance window")

    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_domain_engine(database_url)
    factory = create_session_factory(engine)
    users = _seed(factory)
    api_process: subprocess.Popen[str] | None = None
    base_url = args.base_url.rstrip("/") or "http://127.0.0.1:8010"
    if not args.base_url:
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENVIRONMENT": "test",
                "AUTH_MODE": "local",
                "DATABASE_URL": database_url,
                "OTEL_TRACES_EXPORTER": "none",
            }
        )
        api_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "instant_ppt_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8010",
                "--workers",
                str(args.api_workers),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=environment,
            text=True,
        )
    try:
        _wait_for_api(base_url)
        asyncio.run(
            _window(
                base_url,
                users,
                args.warmup_seconds,
                collect=False,
                virtual_users=args.virtual_users,
                think_time_ms=args.think_time_ms,
            )
        )
        measured = asyncio.run(
            _window(
                base_url,
                users,
                args.measurement_seconds,
                collect=True,
                virtual_users=args.virtual_users,
                think_time_ms=args.think_time_ms,
            )
        )
        reads = measured["reads"]
        writes = measured["writes"]
        assert isinstance(reads, list) and isinstance(writes, list)
        with factory() as session:
            database_version = session.scalar(select(func.version()))
            totals = {
                "organizations": len(users),
                "drafts": session.scalar(
                    select(func.count(Draft.id)).where(
                        Draft.organization_id.in_([user["organizationId"] for user in users])
                    )
                ),
                "jobEvents": session.scalar(
                    select(func.count(JobEvent.id)).where(
                        JobEvent.organization_id.in_(
                            [user["organizationId"] for user in users]
                        )
                    )
                ),
                "artifacts": session.scalar(
                    select(func.count(Artifact.id)).where(
                        Artifact.organization_id.in_(
                            [user["organizationId"] for user in users]
                        )
                    )
                ),
            }
        report = {
            "schemaVersion": 1,
            "goal": "G08",
            "generatedAt": datetime.now(UTC).isoformat(),
            "result": "passed",
            "profile": {
                "server": (
                    "Uvicorn production mode without reload in release container"
                    if args.base_url
                    else "Uvicorn production mode without reload"
                ),
                "apiWorkers": args.api_workers,
                "readEndpoint": "GET /v1/me/entitlements",
                "writeEndpoint": "PATCH /v1/drafts/{draft_id}",
                "virtualUsers": args.virtual_users,
                "warmupSeconds": args.warmup_seconds,
                "measurementSeconds": args.measurement_seconds,
                "requestThinkTimeMs": args.think_time_ms,
                "externalProviderTimeIncluded": False,
            },
            "dataset": totals,
            "latency": {"read": _summary(reads), "write": _summary(writes)},
            "errors": measured["errors"],
            "errorRate": round(
                int(measured["errors"]) / max(1, len(reads) + len(writes)), 8
            ),
            "targets": {"readP95Ms": 300, "writeP95Ms": 500},
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "cpuCount": os.cpu_count(),
                "memoryBytes": _memory_bytes(),
                "database": database_version,
                "containerImageIds": _container_images(),
            },
        }
        read_p95 = float(report["latency"]["read"]["p95Ms"])  # type: ignore[index]
        write_p95 = float(report["latency"]["write"]["p95Ms"])  # type: ignore[index]
        if int(measured["errors"]) or read_p95 > 300 or write_p95 > 500:
            report["result"] = "failed"
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["result"] == "passed" else 1
    finally:
        if api_process is not None:
            if platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/PID", str(api_process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                api_process.terminate()
                with suppress(subprocess.TimeoutExpired):
                    api_process.wait(timeout=10)
                if api_process.poll() is None:
                    api_process.kill()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
