import boto3
from botocore.config import Config

from backend.app.core.config import Settings
from backend.app.storage.base import ObjectStorage
from backend.app.storage.local import LocalFileStorage
from backend.app.storage.s3 import S3ObjectStorage


def create_object_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_backend == "local":
        return LocalFileStorage(settings.local_storage_root)

    return _create_s3_storage(settings, settings.s3_originals_bucket)


def create_artifact_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_backend == "local":
        return LocalFileStorage(settings.local_storage_root)

    return _create_s3_storage(settings, settings.s3_artifacts_bucket)


def _create_s3_storage(settings: Settings, bucket: str) -> ObjectStorage:

    assert settings.s3_access_key_id is not None
    assert settings.s3_secret_access_key is not None
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(
            connect_timeout=settings.s3_connect_timeout_seconds,
            read_timeout=settings.s3_read_timeout_seconds,
            retries={"mode": "standard", "total_max_attempts": 3},
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_path_style else "auto"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    return S3ObjectStorage(
        client,
        bucket,
        server_side_encryption=settings.s3_server_side_encryption,
        kms_key_id=(
            settings.s3_kms_key_id.get_secret_value()
            if settings.s3_kms_key_id is not None
            else None
        ),
    )
