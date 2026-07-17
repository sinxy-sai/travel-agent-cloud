from dataclasses import dataclass
from io import BytesIO
from threading import Lock


class ObjectStorageError(Exception):
    pass


class ObjectStorageNotFoundError(ObjectStorageError):
    pass


@dataclass(frozen=True)
class ObjectStorageSettings:
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "travel-agent-exports"
    minio_secure: bool = False


class MinioObjectStorage:
    def __init__(self, settings: ObjectStorageSettings) -> None:
        self._bucket = settings.minio_bucket.strip()
        self.enabled = bool(
            settings.minio_endpoint.strip()
            and settings.minio_access_key.strip()
            and settings.minio_secret_key.strip()
            and self._bucket
        )
        self._client = None
        self._bucket_ready = False
        self._bucket_lock = Lock()
        self._s3_error_type = Exception
        self._network_error_types = (OSError,)

        if not self.enabled:
            return

        try:
            from minio import Minio
            from minio.error import S3Error
            from urllib3.exceptions import HTTPError as Urllib3HTTPError
        except ImportError as exc:
            raise RuntimeError("minio package is required when MinIO is configured") from exc

        self._s3_error_type = S3Error
        self._network_error_types = (OSError, Urllib3HTTPError)
        self._client = Minio(
            settings.minio_endpoint.strip(),
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def put_user_export(self, user_id: str, export_id: str, data: bytes) -> None:
        client = self._require_client()
        try:
            self._ensure_bucket()
            client.put_object(
                self._bucket,
                self._export_key(user_id, export_id),
                BytesIO(data),
                length=len(data),
                content_type="application/json",
            )
        except self._s3_error_type as exc:
            raise ObjectStorageError("Could not store export file") from exc
        except self._network_error_types as exc:
            raise ObjectStorageError("Could not connect to object storage") from exc

    def get_user_export(self, user_id: str, export_id: str) -> bytes:
        client = self._require_client()
        response = None
        try:
            response = client.get_object(self._bucket, self._export_key(user_id, export_id))
            return response.read()
        except self._s3_error_type as exc:
            if getattr(exc, "code", "") in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise ObjectStorageNotFoundError(export_id) from exc
            raise ObjectStorageError("Could not read export file") from exc
        except self._network_error_types as exc:
            raise ObjectStorageError("Could not connect to object storage") from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def delete_user_exports(self, user_id: str) -> None:
        client = self._require_client()
        try:
            if not client.bucket_exists(self._bucket):
                return
            prefix = self._user_export_prefix(user_id)
            for item in client.list_objects(self._bucket, prefix=prefix, recursive=True):
                client.remove_object(self._bucket, item.object_name)
        except self._s3_error_type as exc:
            raise ObjectStorageError("Could not delete export files") from exc
        except self._network_error_types as exc:
            raise ObjectStorageError("Could not connect to object storage") from exc

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        client = self._require_client()
        with self._bucket_lock:
            if self._bucket_ready:
                return
            if not client.bucket_exists(self._bucket):
                try:
                    client.make_bucket(self._bucket)
                except self._s3_error_type as exc:
                    if getattr(exc, "code", "") not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                        raise
            self._bucket_ready = True

    def _require_client(self):
        if not self.enabled or self._client is None:
            raise ObjectStorageError("Object storage is not configured")
        return self._client

    @staticmethod
    def _user_export_prefix(user_id: str) -> str:
        return f"users/{user_id}/exports/"

    def _export_key(self, user_id: str, export_id: str) -> str:
        return f"{self._user_export_prefix(user_id)}{export_id}.json"
