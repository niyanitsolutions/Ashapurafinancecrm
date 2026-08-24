"""Production bug: presigned Preview/Download URLs came back invalid
(`AuthorizationQueryParametersError — a non-empty Access Key (AKID) must be
provided`). Root cause: `get_s3_client()` used to pass
`aws_access_key_id`/`aws_secret_access_key` to `boto3.client(...)` unconditionally,
even when both were empty strings (Settings' own default when AWS_ACCESS_KEY_ID/
AWS_SECRET_ACCESS_KEY aren't set) — explicit empty credentials permanently blank out
boto3's normal credential chain instead of deferring to it, so the production EC2
deployment's IAM instance role was never consulted. Fixed by only passing explicit
credentials when both are genuinely configured; otherwise the kwargs are omitted so
boto3/botocore resolves credentials itself (env vars, shared config, or an EC2
instance profile)."""

import boto3
import pytest
from app.config.settings import get_settings
from app.config.storage import StorageConfig, get_storage_config
from app.services.storage import client as storage_client


@pytest.fixture(autouse=True)
def _clear_caches():
    # Both `get_s3_client` and `get_settings` are `@lru_cache`d — a test that changes
    # AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY via monkeypatch.setenv must clear
    # `get_settings`'s cache too, or it silently keeps returning whatever `Settings()`
    # was first constructed with earlier in the test session.
    storage_client.get_s3_client.cache_clear()
    get_settings.cache_clear()
    yield
    storage_client.get_s3_client.cache_clear()
    get_settings.cache_clear()


def _spy_on_boto3_client(monkeypatch):
    captured: dict[str, object] = {}
    real_client = boto3.client

    def spy(service_name, **kwargs):
        captured.update(kwargs)
        return real_client(service_name, **kwargs)

    monkeypatch.setattr(storage_client.boto3, "client", spy)
    return captured


def test_defers_to_boto3s_credential_chain_when_no_explicit_credentials_configured(monkeypatch):
    """The production EC2 case: AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY are
    intentionally left unset so the instance's IAM role provides credentials. boto3
    must be allowed to resolve them itself — never handed blank strings."""
    monkeypatch.setattr(
        storage_client, "get_storage_config",
        lambda: StorageConfig(aws_access_key_id="", aws_secret_access_key="", aws_region="ap-south-1", bucket_name="afs-crm-test-bucket"),
    )
    captured = _spy_on_boto3_client(monkeypatch)

    storage_client.get_s3_client()

    assert "aws_access_key_id" not in captured
    assert "aws_secret_access_key" not in captured
    assert captured["region_name"] == "ap-south-1"


def test_uses_explicit_credentials_when_both_are_configured(monkeypatch):
    """Local/staging deployments that do configure real access keys must keep working
    exactly as before this fix."""
    monkeypatch.setattr(
        storage_client, "get_storage_config",
        lambda: StorageConfig(
            aws_access_key_id="AKIDEXAMPLE123", aws_secret_access_key="secretExampleValue",
            aws_region="ap-south-1", bucket_name="afs-crm-test-bucket",
        ),
    )
    captured = _spy_on_boto3_client(monkeypatch)

    storage_client.get_s3_client()

    assert captured["aws_access_key_id"] == "AKIDEXAMPLE123"
    assert captured["aws_secret_access_key"] == "secretExampleValue"
    assert captured["region_name"] == "ap-south-1"


@pytest.mark.parametrize(
    "access_key,secret_key",
    [("AKIDEXAMPLE123", ""), ("", "secretExampleValue")],
)
def test_a_partially_configured_credential_pair_is_never_passed_half_blank(monkeypatch, access_key, secret_key):
    """Defense in depth: one set, one blank must never reach boto3 as a half-empty
    static-credentials pair (which would fail the exact same way as both-empty) —
    it must fall through to the credential chain entirely, same as both-empty."""
    monkeypatch.setattr(
        storage_client, "get_storage_config",
        lambda: StorageConfig(aws_access_key_id=access_key, aws_secret_access_key=secret_key, aws_region="ap-south-1", bucket_name="afs-crm-test-bucket"),
    )
    captured = _spy_on_boto3_client(monkeypatch)

    storage_client.get_s3_client()

    assert "aws_access_key_id" not in captured
    assert "aws_secret_access_key" not in captured


def test_no_aws_secret_ever_appears_in_a_generated_presigned_url(monkeypatch):
    """Defense in depth for the "never expose/log AWS secrets" requirement — the
    Access Key ID is a legitimate, non-secret part of a valid presigned URL (SigV4
    embeds it as X-Amz-Credential), but the secret key itself must never appear in
    the URL string."""
    monkeypatch.setattr(
        storage_client, "get_storage_config",
        lambda: StorageConfig(
            aws_access_key_id="AKIDEXAMPLE123", aws_secret_access_key="TopSecretValueNeverInUrl",
            aws_region="ap-south-1", bucket_name="afs-crm-test-bucket",
        ),
    )
    url = storage_client.generate_presigned_download_url("some/key.pdf")
    assert "TopSecretValueNeverInUrl" not in url


# ---------------------------------------------------------------------- "change-me" placeholder (shipped in every .env* template)


def test_placeholder_aws_credentials_are_normalized_to_not_configured(monkeypatch):
    """The literal, shipped `.env.production` value: a deployment that never
    overrides it must be treated the same as leaving the variable unset, not signed
    into every request as a real (but invalid) access key."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "change-me")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "change-me")

    config = get_storage_config()

    assert config.aws_access_key_id == ""
    assert config.aws_secret_access_key == ""


def test_real_configured_aws_credentials_pass_through_unchanged(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE123")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "realSecretValueNotAPlaceholder")

    config = get_storage_config()

    assert config.aws_access_key_id == "AKIDEXAMPLE123"
    assert config.aws_secret_access_key == "realSecretValueNotAPlaceholder"


def test_end_to_end_placeholder_env_vars_fall_through_to_credential_chain(monkeypatch):
    """The exact production scenario: `.env.production` still has the shipped
    `AWS_ACCESS_KEY_ID=change-me`/`AWS_SECRET_ACCESS_KEY=change-me` placeholders (an
    EC2 deployment intentionally relying on its IAM instance role instead). This must
    resolve all the way through to `get_s3_client()` never handing boto3 the literal
    string "change-me" as a real credential."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "change-me")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "change-me")
    captured = _spy_on_boto3_client(monkeypatch)

    storage_client.get_s3_client()

    assert "aws_access_key_id" not in captured
    assert "aws_secret_access_key" not in captured


def test_download_url_sets_attachment_content_disposition(monkeypatch):
    monkeypatch.setattr(
        storage_client, "get_storage_config",
        lambda: StorageConfig(
            aws_access_key_id="AKIDEXAMPLE123", aws_secret_access_key="secretExampleValue",
            aws_region="ap-south-1", bucket_name="afs-crm-test-bucket",
        ),
    )
    preview_url = storage_client.generate_presigned_download_url("some/key.pdf")
    download_url = storage_client.generate_presigned_download_url(
        "some/key.pdf", response_content_disposition='attachment; filename="key.pdf"'
    )
    assert preview_url != download_url
    assert "response-content-disposition" not in preview_url.lower()
    assert "attachment" in download_url.lower()
