from dataclasses import dataclass

from app.config.settings import get_settings

# The committed placeholder in every shipped .env* template (mirrors
# Settings._PLACEHOLDER_JWT_SECRET's own "change-me" convention). A deployment that
# never overrides this must be treated identically to leaving the variable unset —
# never as a real, usable credential — so `get_s3_client()` correctly falls through to
# boto3's normal credential chain (env vars, shared config, or an EC2 instance role)
# instead of signing every request with a literal, invalid "change-me" access key.
_PLACEHOLDER_AWS_CREDENTIAL = "change-me"


@dataclass(frozen=True)
class StorageConfig:
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    bucket_name: str


def _real_credential(value: str) -> str:
    return "" if value == _PLACEHOLDER_AWS_CREDENTIAL else value


def get_storage_config() -> StorageConfig:
    settings = get_settings()
    return StorageConfig(
        aws_access_key_id=_real_credential(settings.aws_access_key_id),
        aws_secret_access_key=_real_credential(settings.aws_secret_access_key),
        aws_region=settings.aws_region,
        bucket_name=settings.s3_bucket_name,
    )
