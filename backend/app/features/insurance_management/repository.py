from app.features.insurance_management.models import InsuranceCaseAdditionalDocument
from app.shared.base_repository import BaseRepository


class InsuranceCaseAdditionalDocumentRepository(BaseRepository[InsuranceCaseAdditionalDocument]):
    collection_name = "insurance_case_additional_documents"
    model = InsuranceCaseAdditionalDocument

    async def find_for_case(self, insurance_case_id: str) -> list[InsuranceCaseAdditionalDocument]:
        return await self.find_many({"insurance_case_id": insurance_case_id}, limit=200, sort=[("created_at", 1)])
