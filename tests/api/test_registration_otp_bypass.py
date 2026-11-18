"""The retired registration bypass must not grant mobile ownership."""
import pytest
from app.config.settings import get_settings


@pytest.mark.parametrize("enabled", [False, True])
async def test_retired_bypass_never_grants_verification(client, mock_db, monkeypatch, enabled):
    monkeypatch.setattr(get_settings(), "registration_otp_bypass", enabled)
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": "9000000088"})
    assert r.status_code == 404
    assert "otp_verified_token" not in r.text
    assert await mock_db.users.count_documents({}) == 0
