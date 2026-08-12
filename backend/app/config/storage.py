from dataclasses import dataclass

from app.config.settings import get_settings


@dataclass(frozen=True)
class StorageConfig:
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    bucket_name: str


def get_storage_config() -> StorageConfig:
    settings = get_settings()
    return StorageConfig(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_region=settings.aws_region,
        bucket_name=settings.s3_bucket_name,
    )
