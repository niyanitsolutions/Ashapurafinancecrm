"""Owner domain model — covers both first-run Owner registration and Owner Account
Management (Primary + Secondary Owners). Login identity (mobile/password/role) stays on
Auth's shared `users` collection (decision 007's pattern) — this collection only holds
the Owner's own profile data, exactly like Employee/Customer/ReferralPartner. At most one
PRIMARY document may ever exist (see owner/indexes.py's partial unique index on
`owner_type="primary"`, which is the real, DB-level guarantee); any number of SECONDARY
documents may exist, each created by the Primary Owner."""

from pydantic import Field

from app.features.owner.constants import OwnerType
from app.shared.base_document import BaseDocument


class OwnerProfile(BaseDocument):
    user_id: str  # ref: users (Auth), unique — login identity stays there
    full_name: str
    mobile: str  # denormalized from users.mobile at creation, same pattern as Employee/Customer
    email: str
    # Defaults to PRIMARY so every OwnerProfile document written before this field
    # existed (when at most one Owner could ever exist) is read correctly without a data
    # migration — see owner/indexes.py's idempotent backfill for the on-disk equivalent,
    # needed because a partial unique index only sees fields that are actually stored.
    # New Secondary Owners always set this explicitly (see OwnerService.create_secondary_owner).
    owner_type: str = Field(default=OwnerType.PRIMARY, pattern=f"^({'|'.join(OwnerType.ALL)})$")
