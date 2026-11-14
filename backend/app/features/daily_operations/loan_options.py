"""Loan types share Daily Update option permissions, normalization and CAS history."""

from typing import Any

from app.features.daily_operations.bank_options import BankOptions


class LoanOptions(BankOptions):
    collection_name = "daily_loan_type_options"
    audit_prefix = "daily_loan_type_option_"


async def install(db: Any) -> None:
    await db.daily_loan_type_options.create_index(
        [("company_id", 1), ("normalized_name", 1)],
        unique=True,
        partialFilterExpression={"is_active": True},
        name="active_company_loan_type_name",
    )
    await db.daily_loan_type_options.create_index(
        [("company_id", 1), ("is_active", 1), ("name", 1)]
    )
