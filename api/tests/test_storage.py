"""Tests for the storage backends and factory."""

from __future__ import annotations

from typing import Any

import pytest

from hearsay_api.config import Settings, StorageBackendKind
from hearsay_api.storage import (
    LocalDiskBackend,
    S3Backend,
    build_storage,
)


async def test_local_disk_roundtrip(tmp_path: Any) -> None:
    """Put/get/exists/delete work on the local backend."""
    backend = LocalDiskBackend(str(tmp_path / "s"))
    ref = await backend.put("a/b/c.wav", b"data")
    assert ref == "a/b/c.wav"
    assert await backend.exists("a/b/c.wav") is True
    assert await backend.get("a/b/c.wav") == b"data"
    await backend.delete("a/b/c.wav")
    assert await backend.exists("a/b/c.wav") is False
    # Deleting a missing ref is a no-op.
    await backend.delete("a/b/c.wav")


async def test_local_disk_rejects_escape(tmp_path: Any) -> None:
    """Refs that escape the storage root are rejected."""
    backend = LocalDiskBackend(str(tmp_path / "s"))
    with pytest.raises(ValueError, match="escapes"):
        await backend.put("../../etc/passwd", b"x")


class FakeS3Client:
    """Minimal stand-in for a boto3 S3 client."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.store[Key] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        import io

        return {"Body": io.BytesIO(self.store[Key])}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.store.pop(Key, None)

    def head_object(self, *, Bucket: str, Key: str) -> None:
        if Key not in self.store:
            raise KeyError(Key)


async def test_s3_backend_roundtrip() -> None:
    """Put/get/exists/delete work on the S3 backend with a fake client."""
    client = FakeS3Client()
    backend = S3Backend(
        bucket="b",
        endpoint_url=None,
        access_key=None,
        secret_key=None,
        region="us-east-1",
        client=client,
    )
    await backend.put("k", b"v")
    assert await backend.exists("k") is True
    assert await backend.get("k") == b"v"
    await backend.delete("k")
    assert await backend.exists("k") is False


def test_build_storage_local(tmp_path: Any) -> None:
    """The factory builds a local backend by default."""
    settings = Settings(storage_local_root=str(tmp_path))
    assert isinstance(build_storage(settings), LocalDiskBackend)


def test_build_storage_s3() -> None:
    """The factory builds an S3 backend when configured (real boto3 client)."""
    settings = Settings(
        storage_backend=StorageBackendKind.S3,
        s3_endpoint_url="http://minio:9000",
        s3_access_key="a",
        s3_secret_key="b",
    )
    backend = build_storage(settings)
    assert isinstance(backend, S3Backend)
    assert backend.bucket == settings.s3_bucket
