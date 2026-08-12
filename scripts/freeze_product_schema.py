"""One-product-at-a-time schema freeze — companion to `apply_product_schema.py`.

Ask #6's Freeze action normally goes through the Owner-facing UI/API (which needs a
logged-in Owner session), but this environment has no Owner password to authenticate
with — same constraint `apply_product_schema.py` already works under. This script calls
`CustomerService.freeze_form_definition` directly against the real DB, attributing the
freeze to the real seeded Owner user (`docs/RUN_LOCAL.md`'s `BOOTSTRAP_OWNER_MOBILE`),
exactly as if they'd clicked Freeze after confirming the 14-item checklist.

Usage:
    cd backend && ../.venv/Scripts/python.exe ../scripts/freeze_product_schema.py "Personal Loan"
"""

import asyncio
import sys

from redis.asyncio import Redis

from app.config.database import get_database
from app.config.redis import get_redis
from app.constants.roles import OWNER
from app.features.auth.models import User
from app.features.customer.repository import ApplicationFormDefinitionRepository
from app.features.customer.service import CustomerService
from app.features.system_settings.repository import (
    InsuranceProductRepository,
    LoanProductRepository,
)

_FREEZE_CHECKLIST = [
    "fields_verified", "field_order_verified", "labels_verified", "validation_verified",
    "required_optional_verified", "conditional_logic_verified", "documents_verified", "upload_verified",
    "database_verified", "customer_portal_verified", "employee_flow_verified", "owner_configuration_verified",
    "mobile_responsive_verified", "version_frozen",
]


async def freeze_product_schema(product_name: str) -> None:
    db = get_database()
    redis: Redis = get_redis()
    owner = await db["users"].find_one({"role": OWNER, "is_deleted": False})
    if owner is None:
        raise SystemExit("No Owner user found — cannot attribute the freeze action.")

    loan_products = LoanProductRepository(db)
    insurance_products = InsuranceProductRepository(db)
    loan_matches = await loan_products.find_many({"name": product_name}, limit=1)
    category = "loan"
    product_id = loan_matches[0].require_id() if loan_matches else None
    if product_id is None:
        insurance_matches = await insurance_products.find_many({"name": product_name}, limit=1)
        category = "insurance"
        product_id = insurance_matches[0].require_id() if insurance_matches else None
    if product_id is None:
        raise SystemExit(f"No loan or insurance product named '{product_name}'.")

    form_defs = ApplicationFormDefinitionRepository(db)
    form_def = await form_defs.find_by_product(category, product_id)
    if form_def is None:
        raise SystemExit(f"'{product_name}' has no ACTIVE schema to freeze.")
    if form_def.is_locked:
        print(f"[{category}] {product_name}: already frozen (schema_version {form_def.schema_version}) — nothing to do.")
        return

    service = CustomerService(db, redis)
    owner_user = User.model_validate(owner)
    frozen = await service.freeze_form_definition(form_def.require_id(), _FREEZE_CHECKLIST, owner_user)
    print(f"[{category}] {product_name}: frozen as schema_version {frozen.schema_version} (checklist confirmed: {len(_FREEZE_CHECKLIST)} items).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python ../scripts/freeze_product_schema.py "<Product Name>"')
    asyncio.run(freeze_product_schema(sys.argv[1]))
