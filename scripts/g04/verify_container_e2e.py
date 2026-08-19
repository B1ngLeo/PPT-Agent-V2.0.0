"""Exercise the real G04 API/outbox/Worker/ClamAV/MinIO container chain."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from instant_ppt_api.object_store import MinioPrivateObjectStore, ObjectStoreSettings
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.migrations import upgrade

ROOT = Path(__file__).resolve().parents[2]
API = "http://localhost:8000"
EVIDENCE = ROOT / "docs/evidence/security/g04-container-e2e.json"
DATABASE_URL = (
    "postgresql+psycopg://instant_ppt:local-development-only@127.0.0.1:5432/instant_ppt"
)


def _run(*arguments: str) -> str:
    environment = {**os.environ, "COMPOSE_BAKE": "false"}
    result = subprocess.run(
        list(arguments),
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _headers() -> dict[str, str]:
    return {
        "X-Dev-User-Subject": "g04-container-user",
        "X-Dev-User-Email": "g04-container-user@example.test",
        "X-Dev-User-Name": "G04 Container User",
    }


def _wait_api() -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{API}/openapi.json", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("container API did not become ready")


def _upload(name: str, content: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    key = f"g04-container-{name}-{digest[:12]}-{new_ulid()}"
    created = httpx.post(
        f"{API}/v1/upload-sessions",
        headers={**_headers(), "Idempotency-Key": key},
        json={
            "schemaVersion": 1,
            "data": {
                "filename": name,
                "declaredMimeType": "text/html",
                "expectedSha256": digest,
                "sizeBytes": len(content),
            },
            "baseRevisionId": None,
        },
        timeout=10,
    )
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    stored = httpx.post(
        data["uploadUrl"],
        data=data["formFields"],
        files={"file": (name, content, "text/html")},
        timeout=30,
    )
    assert stored.status_code in {200, 204}, stored.text
    completed = httpx.post(
        f"{API}/v1/upload-sessions/{data['uploadSessionId']}:complete",
        headers={
            **_headers(),
            "Idempotency-Key": f"complete-{key}",
        },
        json={"schemaVersion": 1, "data": {}, "baseRevisionId": None},
        timeout=30,
    )
    assert completed.status_code == 202, completed.text
    return data["sourceId"], data["objectKey"]


def _wait_source(source_id: str, expected: str) -> dict[str, object]:
    deadline = time.monotonic() + 150
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{API}/v1/sources/{source_id}", headers=_headers(), timeout=5
        )
        assert response.status_code == 200, response.text
        last = response.json()["data"]
        if last["status"] == expected:
            return last
        if last["status"] in {"rejected", "parse_failed"} and expected != last["status"]:
            raise AssertionError(last)
        time.sleep(0.5)
    raise TimeoutError(f"source did not reach {expected}: {last}")


def _inspect(container: str) -> dict[str, object]:
    return json.loads(_run("docker", "inspect", container))[0]


def main() -> None:
    for service in ("clamav", "api", "worker", "outbox"):
        _run("docker", "compose", "--profile", "runtime", "build", service)
    upgrade(DATABASE_URL)
    store = MinioPrivateObjectStore(ObjectStoreSettings.from_env())
    store.ensure_private_bucket()
    _run(
        "docker",
        "compose",
        "--profile",
        "runtime",
        "up",
        "-d",
        "--no-build",
        "--force-recreate",
        "api",
        "worker",
        "outbox",
    )
    try:
        _wait_api()
        valid_id, quarantine_key = _upload(
            "container-valid.html", b"<html><body>Container source</body></html>"
        )
        valid = _wait_source(valid_id, "parsed")
        assert valid["scanStatus"] == "clean"
        assert valid["parseStatus"] == "succeeded"
        assert len(valid["artifacts"]) >= 2  # type: ignore[arg-type]

        threat_id, _ = _upload(
            "container-threat.html",
            b"INSTANT-PPT-EICAR-TEST-SIGNATURE",
        )
        threat = _wait_source(threat_id, "rejected")
        assert threat["scanStatus"] == "rejected"
        assert threat["parseAttempt"] == 0
        assert threat["artifacts"] == []
        finding_codes = {
            finding["code"]
            for finding in threat["scanDecision"]["findings"]  # type: ignore[index]
        }
        assert "SOURCE_MALWARE_DETECTED" in finding_codes

        worker = _inspect("instant-ppt-worker-1")
        clamav = _inspect("instant-ppt-clamav-1")
        outbox = _inspect("instant-ppt-outbox-1")
        api = _inspect("instant-ppt-api-1")
        assert worker["Config"]["User"] == "10001:10001"
        assert api["Config"]["User"] == "10001:10001"
        assert outbox["Config"]["User"] == "10001:10001"
        assert clamav["Config"]["User"] == "clamav:clamav"
        assert worker["HostConfig"]["ReadonlyRootfs"] is True
        assert worker["HostConfig"]["CapDrop"] == ["ALL"]
        assert clamav["HostConfig"]["ReadonlyRootfs"] is True
        assert clamav["HostConfig"]["CapDrop"] == ["ALL"]
        assert clamav["State"]["Health"]["Status"] == "healthy"
        evidence = {
            "schemaVersion": 1,
            "goal": "G04",
            "gate": "GATE-G04-SOURCE-SECURITY",
            "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "result": "passed",
            "validSource": {
                "sourceId": valid_id,
                "status": valid["status"],
                "scanStatus": valid["scanStatus"],
                "parseStatus": valid["parseStatus"],
                "artifactCount": len(valid["artifacts"]),  # type: ignore[arg-type]
                "quarantineKey": quarantine_key,
            },
            "threatSource": {
                "sourceId": threat_id,
                "status": threat["status"],
                "errorCode": threat["errorCode"],
                "parseAttempt": threat["parseAttempt"],
                "findingCodes": sorted(finding_codes),
            },
            "containers": {
                "apiUser": api["Config"]["User"],
                "workerUser": worker["Config"]["User"],
                "outboxUser": outbox["Config"]["User"],
                "clamavUser": clamav["Config"]["User"],
                "workerReadOnly": worker["HostConfig"]["ReadonlyRootfs"],
                "workerCapDrop": worker["HostConfig"]["CapDrop"],
                "clamavReadOnly": clamav["HostConfig"]["ReadonlyRootfs"],
                "clamavCapDrop": clamav["HostConfig"]["CapDrop"],
                "clamavHealth": clamav["State"]["Health"]["Status"],
                "clamavImage": clamav["Config"]["Image"],
            },
        }
        EVIDENCE.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("G04 real container source and threat journeys passed")
    finally:
        subprocess.run(
            [
                "docker",
                "compose",
                "--profile",
                "runtime",
                "stop",
                "api",
                "worker",
                "outbox",
            ],
            cwd=ROOT,
            check=False,
        )


if __name__ == "__main__":
    main()
