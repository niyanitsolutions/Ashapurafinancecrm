from typing import Any, TypeVar

from app.features.system_settings.models import (
    ApiSetting,
    CompanySettings,
    DocumentType,
    InsuranceProduct,
    LeadSource,
    LoanProduct,
    NamedMasterData,
    NotificationTemplate,
    StatusMaster,
)
from app.shared.base_repository import BaseRepository
from app.utils.helpers import to_object_id

TNamed = TypeVar("TNamed", bound=NamedMasterData)


class _NamedMasterDataRepository(BaseRepository[TNamed]):
    """Shared `find_by_name` (with `exclude_id`, needed for edit-time uniqueness checks)
    for the four resources that are just name+description+status. Department/Designation
    (Module 2, frozen) predate `exclude_id` support and can't be changed — this module's
    own repositories don't have that limitation."""

    async def find_by_name(self, name: str, *, exclude_id: str | None = None) -> TNamed | None:
        query: dict[str, Any] = {"name": name, "is_deleted": False}
        if exclude_id:
            query["_id"] = {"$ne": to_object_id(exclude_id)}
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None


class LeadSourceRepository(_NamedMasterDataRepository[LeadSource]):
    collection_name = "lead_sources"
    model = LeadSource


class LoanProductRepository(_NamedMasterDataRepository[LoanProduct]):
    collection_name = "loan_products"
    model = LoanProduct


class InsuranceProductRepository(_NamedMasterDataRepository[InsuranceProduct]):
    collection_name = "insurance_products"
    model = InsuranceProduct


class DocumentTypeRepository(_NamedMasterDataRepository[DocumentType]):
    collection_name = "document_types"
    model = DocumentType


class StatusMasterRepository(BaseRepository[StatusMaster]):
    collection_name = "status_masters"
    model = StatusMaster

    async def find_by_category_and_name(self, category: str, name: str, *, exclude_id: str | None = None) -> StatusMaster | None:
        query: dict[str, Any] = {"category": category, "name": name, "is_deleted": False}
        if exclude_id:
            query["_id"] = {"$ne": to_object_id(exclude_id)}
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None


class NotificationTemplateRepository(BaseRepository[NotificationTemplate]):
    collection_name = "notification_templates"
    model = NotificationTemplate

    async def find_by_channel_and_key(self, channel: str, key: str, *, exclude_id: str | None = None) -> NotificationTemplate | None:
        query: dict[str, Any] = {"channel": channel, "key": key, "is_deleted": False}
        if exclude_id:
            query["_id"] = {"$ne": to_object_id(exclude_id)}
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None


class ApiSettingRepository(BaseRepository[ApiSetting]):
    collection_name = "api_settings"
    model = ApiSetting

    async def find_by_provider_and_label(self, provider: str, label: str, *, exclude_id: str | None = None) -> ApiSetting | None:
        query: dict[str, Any] = {"provider": provider, "label": label, "is_deleted": False}
        if exclude_id:
            query["_id"] = {"$ne": to_object_id(exclude_id)}
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None


class CompanySettingsRepository(BaseRepository[CompanySettings]):
    collection_name = "company_settings"
    model = CompanySettings

    async def get_or_create(self) -> CompanySettings:
        doc = await self.collection.find_one({"singleton_key": "default", "is_deleted": False})
        if doc:
            return self.model.model_validate(doc)
        settings = CompanySettings(company_name="Ashapura Financial Services")
        settings_id = await self.insert(settings)
        created = await self.find_by_id(settings_id)
        assert created is not None
        return created
