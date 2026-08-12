"""SMS provider client interface. Credentials/enable-per-provider come from the
system_settings integrations config (owner-managed, with test-connection support) once
that feature is built — this stub just fixes the call signature other features code
against, so e.g. auth's OTP delivery doesn't need to change when a provider is wired in.
"""

from typing import Protocol


class SmsClient(Protocol):
    async def send_sms(self, mobile: str, message: str) -> bool: ...


class NotConfiguredSmsClient:
    async def send_sms(self, mobile: str, message: str) -> bool:
        raise NotImplementedError("SMS provider not configured yet — see system_settings integrations.")
