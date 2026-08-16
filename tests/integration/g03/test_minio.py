from __future__ import annotations

import hashlib
import io
import os
import time
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

import pytest
from instant_ppt_api.object_store import (
    MinioPrivateObjectStore,
    ObjectStoreSettings,
)
from instant_ppt_domain.artifacts import authorize_download, tenant_object_key
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import Artifact
from instant_ppt_domain.tenancy import IdentityClaims, provision_identity
from minio import Minio
from minio.error import S3Error
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("G03_RUN_MINIO") != "1",
    reason="real MinIO checks are enabled by the G03 integration runner",
)


def test_private_minio_download_is_signed_tamper_proof_and_expires(
    session_factory: sessionmaker[Session],
) -> None:
    settings = ObjectStoreSettings.from_env()
    store = MinioPrivateObjectStore(settings)
    store.ensure_private_bucket()
    client = Minio(
        "localhost:9000",
        access_key=settings.access_key,
        secret_key=settings.secret_key,
        secure=False,
        region=settings.region,
    )
    try:
        policy = client.get_bucket_policy(settings.bucket)
    except S3Error as error:
        assert error.code == "NoSuchBucketPolicy"
    else:
        pytest.fail(f"private test bucket unexpectedly has a policy: {policy}")

    with session_factory.begin() as session:
        context = provision_identity(
            session,
            IdentityClaims(
                issuer="urn:instant-ppt:local",
                subject="real-minio-user",
                email="real-minio-user@example.test",
                display_name="Real MinIO User",
            ),
        )

    artifact_id = new_ulid()
    object_key = tenant_object_key(context.organization_id, "published", artifact_id)
    content = b"real-private-object-fixture"
    client.put_object(
        settings.bucket,
        object_key,
        io.BytesIO(content),
        len(content),
        content_type="application/octet-stream",
    )
    try:
        with session_factory.begin() as session:
            session.add(
                Artifact(
                    id=artifact_id,
                    organization_id=context.organization_id,
                    artifact_type="security_fixture",
                    partition="published",
                    object_key=object_key,
                    sha256=hashlib.sha256(content).hexdigest(),
                    media_type="application/octet-stream",
                    size_bytes=len(content),
                    status="published",
                    retention_expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        with session_factory.begin() as session:
            authorization = authorize_download(
                session,
                context,
                artifact_id,
                object_store=store,
                request_id="g03-real-minio-request",
                ttl_seconds=15,
            )

        with urlopen(authorization.url, timeout=5) as response:  # noqa: S310
            assert response.status == 200
            assert response.read() == content

        unsigned_url = f"http://localhost:9000/{quote(settings.bucket)}/{quote(object_key)}"
        with pytest.raises(HTTPError) as unsigned_error:
            urlopen(unsigned_url, timeout=5)  # noqa: S310
        assert unsigned_error.value.code in {401, 403}

        replacement_id = artifact_id[:-1] + ("0" if artifact_id[-1] != "0" else "1")
        tampered_url = authorization.url.replace(artifact_id, replacement_id, 1)
        with pytest.raises(HTTPError) as tampered_error:
            urlopen(tampered_url, timeout=5)  # noqa: S310
        assert tampered_error.value.code in {403, 404}

        remaining = (authorization.expires_at - datetime.now(UTC)).total_seconds()
        time.sleep(max(0, remaining) + 1.25)
        with pytest.raises(HTTPError) as expired_error:
            urlopen(authorization.url, timeout=5)  # noqa: S310
        assert expired_error.value.code == 403
    finally:
        client.remove_object(settings.bucket, object_key)
