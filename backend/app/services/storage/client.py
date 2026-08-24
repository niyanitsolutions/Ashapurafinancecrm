"""Thin S3 wrapper. Files are never stored in MongoDB — only the S3 key/URL is persisted
on the owning document (e.g. a document_management record).
"""

from functools import lru_cache
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.config.storage import get_storage_config


@lru_cache
def get_s3_client() -> BaseClient:
    config = get_storage_config()
    # Root cause of the production "AuthorizationQueryParametersError ... non-empty
    # Access Key (AKID) must be provided" error: this used to pass
    # aws_access_key_id/aws_secret_access_key to boto3.client(...) unconditionally, even
    # when they were empty strings (Settings' own default when AWS_ACCESS_KEY_ID/
    # AWS_SECRET_ACCESS_KEY aren't set in the environment). Explicitly passing empty
    # credentials forces boto3 into a "static creds" provider with a blank AKID/secret,
    # signing every presigned URL with nothing — it never falls through to boto3's
    # normal credential chain (env vars, shared config file, or — the production EC2
    # deployment's actual setup — the instance's IAM role via the metadata service).
    # Only pass explicit credentials when both are genuinely configured (e.g. local/
    # staging using access keys directly); otherwise omit the kwargs entirely so
    # boto3/botocore resolves credentials itself, including from an EC2 instance
    # profile. Region is always passed — it's required for SigV4 presigning regardless
    # of where the credentials come from.
    client_kwargs: dict[str, Any] = {"region_name": config.aws_region}
    if config.aws_access_key_id and config.aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = config.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = config.aws_secret_access_key
    return boto3.client("s3", **client_kwargs)


def generate_presigned_upload_url(key: str, *, expires_in: int = 300, content_type: str | None = None) -> str:
    config = get_storage_config()
    params: dict[str, str] = {"Bucket": config.bucket_name, "Key": key}
    if content_type:
        params["ContentType"] = content_type
    url = get_s3_client().generate_presigned_url("put_object", Params=params, ExpiresIn=expires_in)
    return str(url)


def generate_presigned_download_url(key: str, *, expires_in: int = 300, response_content_disposition: str | None = None) -> str:
    config = get_storage_config()
    params: dict[str, str] = {"Bucket": config.bucket_name, "Key": key}
    # Omitted by every existing caller — inline/viewable, the current "Preview" behavior.
    # Passed by CustomerService.document_attachment_url with an "attachment; filename=..."
    # value so the browser actually saves the file instead of rendering it, for a real
    # "Download" action.
    if response_content_disposition:
        params["ResponseContentDisposition"] = response_content_disposition
    url = get_s3_client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)
    return str(url)


def get_object_size(key: str) -> int | None:
    """Actual uploaded size straight from S3 (never the client-reported one) — the only
    way to enforce a Product Schema's `max_size_mb` for real, since the presigned-PUT flow
    never routes the file bytes through this backend. `None` means the object isn't there
    yet (e.g. the client's PUT to S3 never completed)."""
    config = get_storage_config()
    try:
        response = get_s3_client().head_object(Bucket=config.bucket_name, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            return None
        raise
    return int(response["ContentLength"])
