"""Freeze company images at issue time using the existing S3 bucket/client."""

from uuid import uuid4

from app.config.storage import get_storage_config
from app.services.storage.client import get_s3_client


def snapshot_image(source_key: str, invoice_id: str) -> str:
    bucket = get_storage_config().bucket_name
    key = f"invoice-assets/{invoice_id}/{uuid4().hex}.png"
    get_s3_client().copy_object(
        Bucket=bucket, Key=key, CopySource={"Bucket": bucket, "Key": source_key}
    )
    return key
