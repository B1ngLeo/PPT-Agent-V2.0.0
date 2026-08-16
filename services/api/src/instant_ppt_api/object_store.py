"""Private MinIO adapter with separate internal and public signing endpoints."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlsplit

from instant_ppt_domain.artifacts import ArtifactUnavailable, ObjectStat
from minio import Minio
from minio.error import S3Error


def _endpoint(value: str) -> tuple[str, bool]:
    parsed = urlsplit(value if "://" in value else f"http://{value}")
    if not parsed.netloc or parsed.path not in {"", "/"}:
        raise ValueError("S3 endpoint must contain only scheme, host, and port")
    return parsed.netloc, parsed.scheme == "https"


@dataclass(frozen=True, slots=True)
class ObjectStoreSettings:
    endpoint: str
    public_endpoint: str
    region: str
    access_key: str
    secret_key: str = field(repr=False)
    bucket: str = "instant-ppt-private"

    @classmethod
    def from_env(cls) -> ObjectStoreSettings:
        endpoint = os.getenv("S3_ENDPOINT", "http://localhost:9000")
        return cls(
            endpoint=endpoint,
            public_endpoint=os.getenv("S3_PUBLIC_ENDPOINT", endpoint),
            region=os.getenv("S3_REGION", "us-east-1"),
            access_key=os.getenv("S3_ACCESS_KEY", "instant-ppt-local"),
            secret_key=os.getenv("S3_SECRET_KEY", "local-development-only"),
            bucket=os.getenv("S3_BUCKET", "instant-ppt-private"),
        )


class MinioPrivateObjectStore:
    def __init__(self, settings: ObjectStoreSettings) -> None:
        endpoint, secure = _endpoint(settings.endpoint)
        public_endpoint, public_secure = _endpoint(settings.public_endpoint)
        self._bucket = settings.bucket
        self._client = Minio(
            endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=secure,
            region=settings.region,
        )
        self._signer = Minio(
            public_endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=public_secure,
            region=settings.region,
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def ensure_private_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def stat(self, object_key: str) -> ObjectStat:
        try:
            result = self._client.stat_object(self._bucket, object_key)
        except S3Error as error:
            raise ArtifactUnavailable("artifact object is unavailable") from error
        return ObjectStat(size_bytes=result.size, etag=result.etag)

    def presign_get(self, object_key: str, *, expires: timedelta) -> str:
        try:
            return self._signer.presigned_get_object(self._bucket, object_key, expires=expires)
        except S3Error as error:
            raise ArtifactUnavailable("artifact URL could not be signed") from error
