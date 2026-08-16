"""Private MinIO adapter with separate internal and public signing endpoints."""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from instant_ppt_domain.artifacts import ArtifactUnavailable, ObjectStat
from instant_ppt_domain.sources import ObjectDigest, UploadPolicy
from minio import Minio
from minio.commonconfig import ENABLED, Filter
from minio.datatypes import PostPolicy
from minio.error import S3Error
from minio.lifecycleconfig import Expiration, LifecycleConfig
from minio.lifecycleconfig import (
    Rule as LifecycleRule,
)
from minio.sseconfig import Rule as EncryptionRule
from minio.sseconfig import SSEConfig
from urllib3.exceptions import HTTPError

_LIFECYCLE_RULE_ID = "instant-ppt-expired-delete-markers"


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
        self._governance_ready = False
        self._public_base = f"{'https' if public_secure else 'http'}://{public_endpoint}"
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
        """Provision a private bucket and fail closed unless governance is active."""
        if self._governance_ready:
            return
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
            try:
                self._client.get_bucket_policy(self._bucket)
            except S3Error as error:
                if error.code != "NoSuchBucketPolicy":
                    raise
            else:
                self._client.delete_bucket_policy(self._bucket)
            encryption = self._client.get_bucket_encryption(self._bucket)
            if encryption is None:
                self._client.set_bucket_encryption(
                    self._bucket,
                    SSEConfig(EncryptionRule.new_sse_s3_rule()),
                )
            lifecycle = self._client.get_bucket_lifecycle(self._bucket)
            rules = list(lifecycle.rules) if lifecycle is not None else []
            desired = LifecycleRule(
                ENABLED,
                rule_filter=Filter(prefix="tenants/"),
                rule_id=_LIFECYCLE_RULE_ID,
                expiration=Expiration(expired_object_delete_marker=True),
            )
            rules = [rule for rule in rules if rule.rule_id != _LIFECYCLE_RULE_ID]
            rules.append(desired)
            self._client.set_bucket_lifecycle(self._bucket, LifecycleConfig(rules))
            self._governance_ready = True
        except (S3Error, HTTPError, OSError) as error:
            raise ArtifactUnavailable("private object governance is unavailable") from error

    def stat(self, object_key: str) -> ObjectStat:
        try:
            self.ensure_private_bucket()
            result = self._client.stat_object(self._bucket, object_key)
        except (S3Error, HTTPError) as error:
            raise ArtifactUnavailable("artifact object is unavailable") from error
        return ObjectStat(size_bytes=result.size, etag=result.etag)

    def presign_get(self, object_key: str, *, expires: timedelta) -> str:
        try:
            self.ensure_private_bucket()
            return self._signer.presigned_get_object(self._bucket, object_key, expires=expires)
        except (S3Error, HTTPError) as error:
            raise ArtifactUnavailable("artifact URL could not be signed") from error

    def put_bytes(self, object_key: str, payload: bytes, media_type: str) -> None:
        """Publish canonical application output without exposing a public bucket."""
        try:
            self.ensure_private_bucket()
            self._client.put_object(
                self._bucket,
                object_key,
                io.BytesIO(payload),
                len(payload),
                content_type=media_type,
                metadata={"sha256": hashlib.sha256(payload).hexdigest()},
            )
        except (S3Error, HTTPError, OSError) as error:
            raise ArtifactUnavailable("artifact object could not be published") from error

    def remove(self, object_key: str) -> None:
        try:
            self.ensure_private_bucket()
            self._client.remove_object(self._bucket, object_key)
        except (S3Error, HTTPError) as error:
            raise ArtifactUnavailable("artifact object could not be removed") from error

    def presign_post(
        self,
        object_key: str,
        *,
        content_type: str,
        sha256: str,
        size_bytes: int,
        expires_at: datetime,
    ) -> UploadPolicy:
        policy = PostPolicy(self._bucket, expires_at)
        policy.add_equals_condition("key", object_key)
        policy.add_equals_condition("Content-Type", content_type)
        policy.add_equals_condition("x-amz-meta-sha256", sha256)
        policy.add_content_length_range_condition(size_bytes, size_bytes)
        try:
            self.ensure_private_bucket()
            fields = self._signer.presigned_post_policy(policy)
        except ArtifactUnavailable:
            raise
        except (S3Error, ValueError) as error:
            raise ArtifactUnavailable("upload policy could not be signed") from error
        fields.update(
            {
                "key": object_key,
                "Content-Type": content_type,
                "x-amz-meta-sha256": sha256,
            }
        )
        return UploadPolicy(
            url=f"{self._public_base}/{self._bucket}",
            fields={str(key): str(value) for key, value in fields.items()},
        )

    def digest(self, object_key: str, *, max_bytes: int) -> ObjectDigest:
        response = None
        try:
            self.ensure_private_bucket()
            stat = self._client.stat_object(self._bucket, object_key)
            if stat.size > max_bytes:
                return ObjectDigest(
                    size_bytes=stat.size,
                    sha256="",
                    content_type=getattr(stat, "content_type", None),
                    metadata=_object_metadata(stat),
                )
            response = self._client.get_object(self._bucket, object_key)
            digest = hashlib.sha256()
            size = 0
            for chunk in response.stream(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    return ObjectDigest(
                        size_bytes=size,
                        sha256="",
                        content_type=getattr(stat, "content_type", None),
                        metadata=_object_metadata(stat),
                    )
                digest.update(chunk)
            if size != stat.size:
                raise ArtifactUnavailable("upload object changed while it was verified")
            return ObjectDigest(
                size_bytes=size,
                sha256=digest.hexdigest(),
                content_type=getattr(stat, "content_type", None),
                metadata=_object_metadata(stat),
            )
        except ArtifactUnavailable:
            raise
        except (S3Error, HTTPError, OSError) as error:
            raise ArtifactUnavailable("upload object is unavailable") from error
        finally:
            if response is not None:
                response.close()
                response.release_conn()


def _object_metadata(stat: object) -> dict[str, str]:
    raw = getattr(stat, "metadata", None) or {}
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).lower()
        if name.startswith("x-amz-meta-"):
            name = name.removeprefix("x-amz-meta-")
        normalized[name] = str(value)
    return normalized
