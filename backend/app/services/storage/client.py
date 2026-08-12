"""Thin S3 wrapper. Files are never stored in MongoDB — only the S3 key/URL is persisted
on the owning document (e.g. a document_management record).
"""

from functools import lru_cache

import boto3
from botocore.client import BaseClient

from app.config.storage import get_storage_config


@lru_cache
def get_s3_client() -> BaseClient:
    config = get_storage_config()
    return boto3.client(
        "s3",
        aws_access_key_id=config.aws_access_key_id,
        aws_secret_access_key=config.aws_secret_access_key,
        region_name=config.aws_region,
    )


def generate_presigned_upload_url(key: str, *, expires_in: int = 300, content_type: str | None = None) -> str:
    config = get_storage_config()
    params: dict[str, str] = {"Bucket": config.bucket_name, "Key": key}
    if content_type:
        params["ContentType"] = content_type
    url = get_s3_client().generate_presigned_url("put_object", Params=params, ExpiresIn=expires_in)
    return str(url)


def generate_presigned_download_url(key: str, *, expires_in: int = 300) -> str:
    config = get_storage_config()
    url = get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": config.bucket_name, "Key": key},
        ExpiresIn=expires_in,
    )
    return str(url)
