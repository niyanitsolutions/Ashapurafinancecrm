"""Role key constants. Role *definitions* (labels, default permission sets) live in the
access_control feature's DB-driven roles collection — these are just the stable keys
referenced in code so role checks never depend on a magic string.
"""

OWNER = "owner"
EMPLOYEE = "employee"
CUSTOMER = "customer"
REFERRAL_PARTNER = "referral_partner"
SUPER_ADMIN = "super_admin"  # future

ALL_ROLES = (OWNER, EMPLOYEE, CUSTOMER, REFERRAL_PARTNER, SUPER_ADMIN)
