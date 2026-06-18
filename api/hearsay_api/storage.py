"""Storage abstraction for audio blobs.

All audio is addressed by an opaque ``ref`` string and accessed only through a
:class:`StorageBackend`. Two backends ship: local disk (default) and an
S3/MinIO-compatible backend. Paths are never hardcoded by callers.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from hearsay_api.config import Settings, StorageBackendKind
from hearsay_api.logging import get_logger

log = get_logger(__name__)


class StorageBackend(ABC):
    """Abstract content-addressed-ish blob store keyed by ``ref``."""

    @abstractmethod
    async def put(self, ref: str, data: bytes) -> str:
        """Store ``data`` under ``ref`` and return the canonical ref."""

    @abstractmethod
    async def get(self, ref: str) -> bytes:
        """Return the bytes stored under ``ref``."""

    @abstractmethod
    async def delete(self, ref: str) -> None:
        """Delete the blob stored under ``ref`` if it exists."""

    @abstractmethod
    async def exists(self, ref: str) -> bool:
        """Return whether a blob exists under ``ref``."""


class LocalDiskBackend(StorageBackend):
    """Store blobs as files beneath a configured root directory."""

    def __init__(self, root: str) -> None:
        """Create the backend rooted at ``root`` (created if missing)."""
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, ref: str) -> Path:
        """Resolve ``ref`` to a safe path inside the storage root."""
        safe = ref.lstrip("/")
        path = (self.root / safe).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError(f"ref escapes storage root: {ref}")
        return path

    async def put(self, ref: str, data: bytes) -> str:
        """Write ``data`` to the file for ``ref``."""
        path = self._path(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return ref

    async def get(self, ref: str) -> bytes:
        """Read the file for ``ref``."""
        return self._path(ref).read_bytes()

    async def delete(self, ref: str) -> None:
        """Remove the file for ``ref`` if present."""
        path = self._path(ref)
        if path.exists():
            os.remove(path)

    async def exists(self, ref: str) -> bool:
        """Return whether the file for ``ref`` exists."""
        return self._path(ref).exists()


class S3Backend(StorageBackend):
    """Store blobs in an S3/MinIO-compatible bucket via boto3."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        access_key: str | None,
        secret_key: str | None,
        region: str,
        client: Any | None = None,
    ) -> None:
        """Create the backend, building a boto3 client if one isn't injected."""
        self.bucket = bucket
        if client is not None:
            self._client = client
        else:  # pragma: no cover - exercised only with real boto3/credentials
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )

    async def put(self, ref: str, data: bytes) -> str:
        """Upload ``data`` to ``bucket/ref``."""
        self._client.put_object(Bucket=self.bucket, Key=ref, Body=data)
        return ref

    async def get(self, ref: str) -> bytes:
        """Download ``bucket/ref`` and return its bytes."""
        obj = self._client.get_object(Bucket=self.bucket, Key=ref)
        body = obj["Body"].read()
        return bytes(body)

    async def delete(self, ref: str) -> None:
        """Delete ``bucket/ref``."""
        self._client.delete_object(Bucket=self.bucket, Key=ref)

    async def exists(self, ref: str) -> bool:
        """Return whether ``bucket/ref`` exists via a HEAD request."""
        try:
            self._client.head_object(Bucket=self.bucket, Key=ref)
            return True
        except Exception:
            return False


def build_storage(settings: Settings) -> StorageBackend:
    """Construct the configured storage backend."""
    if settings.storage_backend is StorageBackendKind.S3:
        log.info("using S3 storage backend", extra={"extra": {"bucket": settings.s3_bucket}})
        return S3Backend(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        )
    log.info("using local disk storage backend")
    return LocalDiskBackend(settings.storage_local_root)
