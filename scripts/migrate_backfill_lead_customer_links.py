"""One-time backfill: link pre-existing Leads to Customer accounts that were created via
direct self-registration before `CustomerService._link_existing_leads_to_customer`
existed.

Before that fix, a Customer who self-registered directly (Flow 2 — not through a
staff-generated Secure Application Link) never had any Lead sharing their mobile number
linked to their new account: `Lead.customer_id` stayed null even when a staff member had
logged that same mobile as a Lead earlier (registration itself was never blocked by
this — it only ever checks the `users` collection — but the resulting account and the
pre-existing Lead were left disconnected).

This finds every Customer whose mobile has at least one matching Lead with no
`customer_id` set, and links them exactly the way the fixed code now does automatically
for new registrations: sets `Lead.customer_id` (and `user_id`/`account_created`/
`account_created_at` if not already set by some other path) without touching ownership,
assignment, source, product, or remarks. Never creates or deletes a Lead or Customer.

Idempotent: safe to run twice. The second run finds every matching Lead already linked
and skips it — a true no-op, not just "harmless to repeat."

Safe against unknown production state: every step reads before it writes and only ever
sets fields on a Lead that are currently unset — it cannot overwrite an existing
`customer_id` pointing at a different customer.

Run from backend/:  python ../scripts/migrate_backfill_lead_customer_links.py
Run from repo root: python scripts/migrate_backfill_lead_customer_links.py
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.customer.repository import CustomerRepository
from app.features.leads.repository import LeadRepository
from app.utils.datetime import utc_now


async def main() -> None:
    db = get_database()
    customers = CustomerRepository(db)
    leads = LeadRepository(db)

    print(f"Connected to database: {db.name!r}")

    all_customers = await customers.find_many({}, limit=100000)
    print(f"Found {len(all_customers)} customer(s) to check.")

    linked_leads = 0
    customers_with_links = 0

    for customer in all_customers:
        customer_id = customer.require_id()
        matching_leads = await leads.find_by_mobile(customer.mobile)
        unlinked = [lead for lead in matching_leads if lead.customer_id is None]
        if not unlinked:
            continue
        customers_with_links += 1
        for lead in unlinked:
            update: dict[str, Any] = {"customer_id": customer_id}
            if not lead.account_created:
                update.update({"user_id": customer.user_id, "account_created": True, "account_created_at": utc_now()})
            await leads.update(lead.require_id(), update)
            linked_leads += 1
            print(f"  linked lead_id={lead.require_id()!r} lead_code={lead.lead_code!r} -> customer_id={customer_id!r}")

    print(f"\nDone. customers_with_new_links={customers_with_links}  leads_linked={linked_leads}  customers_checked={len(all_customers)}")


if __name__ == "__main__":
    asyncio.run(main())
