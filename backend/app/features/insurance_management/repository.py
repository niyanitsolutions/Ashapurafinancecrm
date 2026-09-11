from app.features.insurance_management.models import (
    InsuranceCaseAdditionalDocument,
    InsurancePaymentTransaction,
)
from app.shared.base_repository import BaseRepository


class InsurancePaymentTransactionRepository(BaseRepository[InsurancePaymentTransaction]):
    collection_name = "insurance_payment_transactions"
    model = InsurancePaymentTransaction

    async def find_for_case(self, insurance_case_id: str) -> list[InsurancePaymentTransaction]:
        """Oldest first — matches the "Payment History" table's expected reading order."""
        return await self.find_many({"insurance_case_id": insurance_case_id}, limit=500, sort=[("created_at", 1)])


class InsuranceCaseAdditionalDocumentRepository(BaseRepository[InsuranceCaseAdditionalDocument]):
    collection_name = "insurance_case_additional_documents"
    model = InsuranceCaseAdditionalDocument

    async def find_for_case(self, insurance_case_id: str) -> list[InsuranceCaseAdditionalDocument]:
        """Current versions only — a superseded (re-uploaded-over) row is hidden here and
        surfaced only by `history_for`."""
        return await self.find_many(
            {"insurance_case_id": insurance_case_id, "is_current": {"$ne": False}}, limit=200, sort=[("created_at", 1)]
        )

    async def history_for(self, insurance_case_id: str, name: str) -> list[InsuranceCaseAdditionalDocument]:
        """Every version of one Other Document (by its free-text name), newest first."""
        return await self.find_many(
            {"insurance_case_id": insurance_case_id, "name": name}, limit=200, sort=[("created_at", -1)]
        )
