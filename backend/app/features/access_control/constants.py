"""Access Control constants. `module`/`resource` are deliberately NOT enumerated here —
they're free-text, data-driven fields on the `permissions` catalog (per the user's
explicit instruction: don't hardcode module names into the permission system, so future
modules are added by creating new permission records, not by changing this engine).
`PermissionAction` IS a fixed set — given as a closed vocabulary in the brief, unlike
module names.
"""


class PermissionAction:
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    ASSIGN = "assign"
    APPROVE = "approve"
    REJECT = "reject"
    EXPORT = "export"
    IMPORT = "import"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    PRINT = "print"
    SHARE = "share"

    ALL = (VIEW, CREATE, EDIT, DELETE, ASSIGN, APPROVE, REJECT, EXPORT, IMPORT, UPLOAD, DOWNLOAD, PRINT, SHARE)


class AccessGrantStatus:
    ACTIVE = "active"
    REVOKED = "revoked"

    ALL = (ACTIVE, REVOKED)


class RoleStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"

    ALL = (ACTIVE, INACTIVE)


class AuditEvent:
    ROLE_CREATED = "role_created"
    ROLE_UPDATED = "role_updated"
    ROLE_ACTIVATED = "role_activated"
    ROLE_DEACTIVATED = "role_deactivated"
    ROLE_DUPLICATED = "role_duplicated"
    ROLE_PERMISSIONS_UPDATED = "role_permissions_updated"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    PERMISSION_CREATED = "permission_created"
    TEMPORARY_ACCESS_GRANTED = "temporary_access_granted"
    TEMPORARY_ACCESS_REVOKED = "temporary_access_revoked"
    GEO_EXCEPTION_GRANTED = "geo_exception_granted"
    GEO_EXCEPTION_REVOKED = "geo_exception_revoked"
