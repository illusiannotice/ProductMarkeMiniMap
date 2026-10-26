import logging
from datetime import timedelta
from typing import BinaryIO, Protocol

from minio import Minio
from minio.error import S3Error

from app.config import Settings

logger = logging.getLogger(__name__)


class ImageStorage(Protocol):
    def ensure_bucket(self) -> None: ...
    def is_ready(self) -> bool: ...
    def put(self, key: str, data: BinaryIO, length: int, content_type: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def presign(self, key: str) -> str: ...


class MinioStorage:
    """Uploads through the internal endpoint and signs URLs for the public one."""

    def __init__(self, settings: Settings) -> None:
        access_key = settings.minio_access_key.get_secret_value()
        secret_key = settings.minio_secret_key.get_secret_value()
        self._bucket = settings.minio_bucket
        self._ttl = timedelta(seconds=settings.presign_ttl_seconds)
        self._internal = Minio(
            settings.minio_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=settings.minio_secure,
            region=settings.minio_region,
        )
        
        self._public = Minio(
            settings.minio_public_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=settings.minio_public_secure,
            region=settings.minio_region,
        )

    def ensure_bucket(self) -> None:
        try:
            if not self._internal.bucket_exists(self._bucket):
                self._internal.make_bucket(self._bucket)
        except S3Error as exc:
            if exc.code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise

    def is_ready(self) -> bool:
        return self._internal.bucket_exists(self._bucket)

    def put(self, key: str, data: BinaryIO, length: int, content_type: str) -> None:
        self._internal.put_object(
            self._bucket,
            key,
            data,
            length=length,
            content_type=content_type,
            metadata={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    def delete(self, key: str) -> None:
        self._internal.remove_object(self._bucket, key)

    def presign(self, key: str) -> str:
        return self._public.presigned_get_object(self._bucket, key, expires=self._ttl)
