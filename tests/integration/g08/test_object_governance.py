from __future__ import annotations

import json
import os
import subprocess
from uuid import uuid4

import pytest
from instant_ppt_api.object_store import MinioPrivateObjectStore, ObjectStoreSettings
from instant_ppt_worker.source_pipeline import WorkerObjectSettings, WorkerObjectStore
from minio import Minio
from minio.error import S3Error

pytestmark = pytest.mark.skipif(
    os.environ.get("G08_RUN_MINIO") != "1",
    reason="real MinIO governance checks are enabled by the G08 integration runner",
)


def test_private_bucket_enforces_encryption_and_multipart_lifecycle() -> None:
    settings = ObjectStoreSettings.from_env()
    store = MinioPrivateObjectStore(settings)
    store.ensure_private_bucket()
    store.ensure_private_bucket()

    client = Minio(
        "localhost:9000",
        access_key=settings.access_key,
        secret_key=settings.secret_key,
        secure=False,
        region=settings.region,
    )
    _assert_governance(client, settings.bucket)

    runtime_environment = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
            "instant-ppt-minio-1",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert "MINIO_API_STALE_UPLOADS_EXPIRY=24h" in runtime_environment
    assert "MINIO_API_STALE_UPLOADS_CLEANUP_INTERVAL=1h" in runtime_environment

    object_key = "tenants/01ARZ3NDEKTSV4RRFFQ69G5FAA/published/g08-sse-canary"
    try:
        store.put_bytes(object_key, b"encrypted-at-rest-canary", "application/octet-stream")
        stat = client.stat_object(settings.bucket, object_key)
        metadata = {str(key).lower(): str(value) for key, value in stat.metadata.items()}
        assert metadata["x-amz-server-side-encryption"] == "AES256"

        try:
            policy = client.get_bucket_policy(settings.bucket)
        except S3Error as error:
            assert error.code == "NoSuchBucketPolicy"
        else:
            pytest.fail(f"private bucket unexpectedly has a public policy: {policy}")
    finally:
        client.remove_object(settings.bucket, object_key)

    suffix = uuid4().hex[:16]
    api_bucket = f"instant-ppt-g08-api-{suffix}"
    worker_bucket = f"instant-ppt-g08-worker-{suffix}"
    client.make_bucket(api_bucket)
    client.set_bucket_policy(
        api_bucket,
        json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{api_bucket}/*"],
                    }
                ],
            }
        ),
    )
    api_store = MinioPrivateObjectStore(
        ObjectStoreSettings(
            endpoint=settings.endpoint,
            public_endpoint=settings.public_endpoint,
            region=settings.region,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            bucket=api_bucket,
        )
    )
    worker_store = WorkerObjectStore(
        WorkerObjectSettings(
            endpoint=settings.endpoint,
            region=settings.region,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            bucket=worker_bucket,
        )
    )
    try:
        api_store.ensure_private_bucket()
        _assert_governance(client, api_bucket)
        _assert_no_public_policy(client, api_bucket)

        worker_store.ensure_private_bucket()
        _assert_governance(client, worker_bucket)
        _assert_no_public_policy(client, worker_bucket)
    finally:
        for bucket in (api_bucket, worker_bucket):
            try:
                client.delete_bucket_policy(bucket)
            except S3Error as error:
                if error.code != "NoSuchBucketPolicy":
                    raise
            if client.bucket_exists(bucket):
                client.remove_bucket(bucket)


def _assert_governance(client: Minio, bucket: str) -> None:
    encryption = client.get_bucket_encryption(bucket)
    assert encryption is not None
    assert encryption.rule.sse_algorithm == "AES256"

    lifecycle = client.get_bucket_lifecycle(bucket)
    assert lifecycle is not None
    matching = [
        rule
        for rule in lifecycle.rules
        if rule.rule_id == "instant-ppt-expired-delete-markers"
    ]
    assert len(matching) == 1
    assert matching[0].status == "Enabled"
    assert matching[0].rule_filter.prefix == "tenants/"
    assert matching[0].expiration is not None
    assert matching[0].expiration.expired_object_delete_marker is True


def _assert_no_public_policy(client: Minio, bucket: str) -> None:
    try:
        policy = client.get_bucket_policy(bucket)
    except S3Error as error:
        assert error.code == "NoSuchBucketPolicy"
    else:
        pytest.fail(f"private bucket unexpectedly has a public policy: {policy}")
