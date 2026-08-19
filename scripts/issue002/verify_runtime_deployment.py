from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

SERVICES = ("api", "worker", "agent-worker", "outbox", "provider-gateway")
WORKER_FAMILY = ("worker", "agent-worker", "outbox", "provider-gateway")
RUNTIME_CONTRACT = "instant-ppt-runtime@v2"


def _run(*args: str) -> str:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _container_id(service: str) -> str:
    value = _run("docker", "compose", "--profile", "runtime", "ps", "-q", service)
    if not value:
        raise RuntimeError(f"runtime service is not running: {service}")
    return value


def _inspect(container_id: str) -> dict[str, Any]:
    return json.loads(_run("docker", "inspect", container_id))[0]


def _health(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def verify(expected_revision: str) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    for service in SERVICES:
        container_id = _container_id(service)
        inspected = _inspect(container_id)
        labels = inspected["Config"].get("Labels") or {}
        environment = {
            item.split("=", 1)[0]: item.split("=", 1)[1]
            for item in inspected["Config"].get("Env") or []
            if "=" in item
        }
        row = {
            "containerId": container_id,
            "imageId": inspected["Image"],
            "buildRevision": labels.get("org.opencontainers.image.revision"),
            "runtimeContractVersion": labels.get("io.instant-ppt.runtime-contract"),
            "environmentRevision": environment.get("APP_BUILD_REVISION"),
            "environmentContract": environment.get("RUNTIME_CONTRACT_VERSION"),
        }
        if row["buildRevision"] != expected_revision:
            raise RuntimeError(f"{service} image revision does not match {expected_revision}")
        if row["environmentRevision"] != expected_revision:
            raise RuntimeError(f"{service} environment revision is inconsistent")
        if row["runtimeContractVersion"] != RUNTIME_CONTRACT:
            raise RuntimeError(f"{service} image runtime contract is inconsistent")
        if row["environmentContract"] != RUNTIME_CONTRACT:
            raise RuntimeError(f"{service} environment runtime contract is inconsistent")
        rows[service] = row

    worker_images = {rows[service]["imageId"] for service in WORKER_FAMILY}
    if len(worker_images) != 1:
        raise RuntimeError("worker, agent-worker, outbox, and provider-gateway differ")

    api_health = _health("http://127.0.0.1:8000/healthz")
    if api_health.get("runtime", {}).get("buildRevision") != expected_revision:
        raise RuntimeError("API health build revision does not match deployed containers")
    if api_health.get("runtime", {}).get("runtimeContractVersion") != RUNTIME_CONTRACT:
        raise RuntimeError("API health runtime contract is inconsistent")

    provider_health = json.loads(
        _run(
            "docker",
            "exec",
            rows["provider-gateway"]["containerId"],
            "python",
            "-c",
            (
                "import json,urllib.request;"
                "print(json.dumps(json.load(urllib.request.urlopen("
                "'http://127.0.0.1:8090/healthz',timeout=5))))"
            ),
        )
    )
    if provider_health.get("runtime") != api_health.get("runtime"):
        raise RuntimeError("API and Provider Gateway runtime identities differ")

    task_probe = _run(
        "docker",
        "exec",
        rows["worker"]["containerId"],
        "python",
        "-c",
        (
            "from instant_ppt_worker.tasks import process_export_task;"
            "from instant_ppt_domain.runtime_contract import PROCESS_EXPORT_TASK;"
            "assert process_export_task.name==PROCESS_EXPORT_TASK;"
            "print(process_export_task.name)"
        ),
    )
    if task_probe != "instant_ppt.v2.process_export":
        raise RuntimeError("ordinary worker did not register the v2 exact-export task")

    return {
        "schemaVersion": 1,
        "status": "passed",
        "expectedRevision": expected_revision,
        "runtimeContractVersion": RUNTIME_CONTRACT,
        "workerFamilyImageId": next(iter(worker_images)),
        "services": rows,
        "apiHealth": api_health,
        "providerHealth": provider_health,
        "registeredExportTask": task_probe,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.expected_revision.lower())
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
