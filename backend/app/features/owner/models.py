"""Owner first-run registration domain model. Login identity (mobile/password/role)
stays on Auth's shared `users` collection (decision 007's pattern) — this collection
only holds the Owner's own profile data, exactly like Employee/Customer/ReferralPartner.
There is at most ever one document here (see auth/indexes.py's partial unique index on
`users.role="owner"`, which is the real, DB-level guarantee)."""

from app.shared.base_document import BaseDocument


class OwnerProfile(BaseDocument):
    user_id: str  # ref: users (Auth), unique — login identity stays there
    full_name: str
    mobile: str  # denormalized from users.mobile at creation, same pattern as Employee/Customer
    email: str
