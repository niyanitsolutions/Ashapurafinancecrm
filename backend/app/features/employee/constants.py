"""Employee-module-local constants. Employment status/type are fixed enums (not
DB-driven) because the spec only requires Department/Designation/Branch to be
configurable — these have a small, stable set of values.
"""


class EmploymentStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    ON_LEAVE = "on_leave"
    RESIGNED = "resigned"

    ALL = (ACTIVE, INACTIVE, SUSPENDED, ON_LEAVE, RESIGNED)

    # Statuses under which login is blocked (users.status is set to disabled to match).
    # ON_LEAVE deliberately does not block login — an employee on leave may still need
    # portal access. This is a judgment call, not specified in the brief; documented in
    # docs/KNOWN_LIMITATIONS.md.
    LOGIN_BLOCKED = frozenset({INACTIVE, SUSPENDED, RESIGNED})


class EmploymentType:
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"

    ALL = (FULL_TIME, PART_TIME, CONTRACT, INTERN)


class Gender:
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

    ALL = (MALE, FEMALE, OTHER)


class DocumentType:
    PAN = "pan"
    AADHAAR = "aadhaar"
    OFFER_LETTER = "offer_letter"
    JOINING_LETTER = "joining_letter"
    EXPERIENCE_CERTIFICATE = "experience_certificate"
    OTHER = "other"

    ALL = (PAN, AADHAAR, OFFER_LETTER, JOINING_LETTER, EXPERIENCE_CERTIFICATE, OTHER)


class AuditEvent:
    EMPLOYEE_CREATED = "employee_created"
    EMPLOYEE_UPDATED = "employee_updated"
    EMPLOYEE_ACTIVATED = "employee_activated"
    EMPLOYEE_DEACTIVATED = "employee_deactivated"
    EMPLOYEE_PASSWORD_RESET_TRIGGERED = "employee_password_reset_triggered"
    EMPLOYEE_FORCE_LOGOUT = "employee_force_logout"
    EMPLOYEE_SELF_UPDATED = "employee_self_updated"
    EMPLOYEE_PHOTO_UPDATED = "employee_photo_updated"
    DEPARTMENT_CREATED = "department_created"
    DESIGNATION_CREATED = "designation_created"
    BRANCH_CREATED = "branch_created"
