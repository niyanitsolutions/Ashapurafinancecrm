"""Permission key naming convention.

Permission *values* (which roles/users have which permissions) are DB-driven, per the
access_control feature. This module only fixes the key format so every feature names
its permissions consistently: "<feature>:<action>", e.g. "leads:assign", "reports:export".
"""


def permission_key(feature: str, action: str) -> str:
    return f"{feature}:{action}"
