"""System Settings (Master Data) constants. Resource names (lead_sources, loan_products,
status master `category`, notification `channel`, API `provider`, ...) are deliberately
NOT enumerated here — they're free text, following the same data-driven philosophy as
Access Control's `module`/`resource` (see docs/decisions/DECISIONS.md #021). Weekday is
a genuine fixed set (the calendar doesn't need to be configurable) and MasterDataStatus
mirrors Access Control's RoleStatus convention (active/inactive, not the richer employment
status vocabulary Module 2 uses).
"""


class MasterDataStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"

    ALL = (ACTIVE, INACTIVE)


class Weekday:
    MONDAY = "mon"
    TUESDAY = "tue"
    WEDNESDAY = "wed"
    THURSDAY = "thu"
    FRIDAY = "fri"
    SATURDAY = "sat"
    SUNDAY = "sun"

    ALL = (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY)


class AuditEvent:
    """Most master-data resources share one CRUD shape, so their audit events are
    generated (`system_settings_{resource}_{action}`) instead of enumerating every
    resource x action combination by hand. Company Settings is the one singleton
    resource, so it gets its own named constants."""

    COMPANY_SETTINGS_UPDATED = "company_settings_updated"
    COMPANY_LOGO_UPDATED = "company_logo_updated"

    @staticmethod
    def master_data(resource: str, action: str) -> str:
        return f"system_settings_{resource}_{action}"
