from app.features.loan_management.models import LoanCaseBankOffer
from app.shared.base_repository import BaseRepository


class LoanCaseBankOfferRepository(BaseRepository[LoanCaseBankOffer]):
    collection_name = "loan_case_bank_offers"
    model = LoanCaseBankOffer

    async def find_for_case(self, loan_case_id: str) -> list[LoanCaseBankOffer]:
        return await self.find_many({"loan_case_id": loan_case_id}, limit=200, sort=[("created_at", 1)])
