"""Module 7 — Referral Partner Portal routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.referral_partner_management import mappers
from app.features.referral_partner_management.dependencies import (
    get_referral_partner_management_service,
    require_owner,
    require_referral_partner,
)
from app.features.referral_partner_management.schemas import (
    AddReferralLeadRequest,
    CommissionEntryResponse,
    CommissionRuleResponse,
    CreateCommissionRuleRequest,
    CreateReferralPartnerRequest,
    ReferralDashboardResponse,
    ReferralLeadResponse,
    ReferralPartnerResponse,
    SettleCommissionEntryRequest,
    UpdateCommissionRuleRequest,
    UpdateReferralLeadRequest,
)
from app.features.referral_partner_management.service import ReferralPartnerManagementService
from app.features.system_settings.schemas import NamedMasterDataResponse

router = APIRouter(tags=["referral_partner_management"])

ServiceDep = Annotated[ReferralPartnerManagementService, Depends(get_referral_partner_management_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
OwnerDep = Annotated[User, Depends(require_owner)]
PartnerDep = Annotated[User, Depends(require_referral_partner)]


def _perm(action: str) -> Any:
    return require_permission("referral_partner_management", "partners", action)


# Additive to OwnerDep, not a replacement — see dependencies.py's module docstring.
PartnerViewDep = Annotated[User, _perm("view")]
PartnerCreateDep = Annotated[User, _perm("create")]


# ---------------------------------------------------------------------- Referral Partner self-service
# Registered before "/referral-partners/{partner_id}" so "me" is never captured as a partner_id.


@router.get("/referral-partners/me")
async def get_own_partner(service: ServiceDep, actor: PartnerDep) -> ApiResponse[ReferralPartnerResponse]:
    partner = await service.get_own_partner(actor)
    return ApiResponse[ReferralPartnerResponse].ok(mappers.partner_to_response(partner))


@router.get("/referral-partners/me/products")
async def list_own_add_lead_products(service: ServiceDep, actor: PartnerDep, category: str) -> ApiResponse[list[NamedMasterDataResponse]]:
    products = await service.list_products(category)
    items = [
        NamedMasterDataResponse(id=p.require_id(), name=p.name, description=p.description, status=p.status, created_at=p.created_at, updated_at=p.updated_at)
        for p in products
    ]
    return ApiResponse[list[NamedMasterDataResponse]].ok(items)


@router.post("/referral-partners/me/leads")
async def add_own_lead(payload: AddReferralLeadRequest, service: ServiceDep, actor: PartnerDep) -> ApiResponse[ReferralLeadResponse]:
    lead, _mapping = await service.add_lead(payload, actor)
    return ApiResponse[ReferralLeadResponse].ok(mappers.referral_lead_to_response(lead, "submitted", True))


@router.patch("/referral-partners/me/leads/{lead_id}")
async def update_own_lead(lead_id: str, payload: UpdateReferralLeadRequest, service: ServiceDep, actor: PartnerDep) -> ApiResponse[ReferralLeadResponse]:
    lead = await service.update_own_lead(lead_id, payload, actor)
    status, editable = await service.external_status_and_editable(lead)
    return ApiResponse[ReferralLeadResponse].ok(mappers.referral_lead_to_response(lead, status, editable))


@router.get("/referral-partners/me/leads")
async def list_own_leads(service: ServiceDep, actor: PartnerDep, page: PageParamsDep) -> ApiResponse[list[ReferralLeadResponse]]:
    results, total = await service.list_own_leads(actor, skip=page.skip, limit=page.page_size)
    items = [mappers.referral_lead_to_response(lead, status, editable) for lead, status, editable in results]
    return ApiResponse[list[ReferralLeadResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/referral-partners/me/dashboard")
async def get_own_dashboard(service: ServiceDep, actor: PartnerDep) -> ApiResponse[ReferralDashboardResponse]:
    dashboard = await service.get_own_dashboard(actor)
    return ApiResponse[ReferralDashboardResponse].ok(dashboard)


@router.get("/referral-partners/me/commission-entries")
async def list_own_commission_entries(
    service: ServiceDep, actor: PartnerDep, page: PageParamsDep, status: str | None = None
) -> ApiResponse[list[CommissionEntryResponse]]:
    entries, total = await service.list_own_commission_entries(actor, status=status, skip=page.skip, limit=page.page_size)
    items = [mappers.commission_entry_to_response(e, None) for e in entries]
    return ApiResponse[list[CommissionEntryResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


# ---------------------------------------------------------------------- Owner: partner lifecycle


@router.post("/referral-partners")
async def create_partner(payload: CreateReferralPartnerRequest, service: ServiceDep, actor: PartnerCreateDep) -> ApiResponse[ReferralPartnerResponse]:
    partner = await service.create_partner(payload, actor)
    return ApiResponse[ReferralPartnerResponse].ok(mappers.partner_to_response(partner))


@router.get("/referral-partners")
async def list_partners(
    service: ServiceDep, _actor: PartnerViewDep, page: PageParamsDep, search: str | None = None, approval_status: str | None = None
) -> ApiResponse[list[ReferralPartnerResponse]]:
    partners, total = await service.list_partners(search=search, approval_status=approval_status, skip=page.skip, limit=page.page_size, sort=page.sort)
    items = [mappers.partner_to_response(p) for p in partners]
    return ApiResponse[list[ReferralPartnerResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/referral-partners/{partner_id}")
async def get_partner(partner_id: str, service: ServiceDep, _actor: PartnerViewDep) -> ApiResponse[ReferralPartnerResponse]:
    partner = await service.get_partner(partner_id)
    return ApiResponse[ReferralPartnerResponse].ok(mappers.partner_to_response(partner))


@router.post("/referral-partners/{partner_id}/approve")
async def approve_partner(partner_id: str, service: ServiceDep, actor: OwnerDep) -> ApiResponse[ReferralPartnerResponse]:
    partner = await service.approve_partner(partner_id, actor)
    return ApiResponse[ReferralPartnerResponse].ok(mappers.partner_to_response(partner))


@router.post("/referral-partners/{partner_id}/deactivate")
async def deactivate_partner(partner_id: str, service: ServiceDep, actor: OwnerDep) -> ApiResponse[ReferralPartnerResponse]:
    partner = await service.deactivate_partner(partner_id, actor)
    return ApiResponse[ReferralPartnerResponse].ok(mappers.partner_to_response(partner))


# ---------------------------------------------------------------------- Owner: commission rules


@router.post("/commission-rules")
async def create_commission_rule(payload: CreateCommissionRuleRequest, service: ServiceDep, actor: OwnerDep) -> ApiResponse[CommissionRuleResponse]:
    rule = await service.create_commission_rule(payload, actor)
    return ApiResponse[CommissionRuleResponse].ok(mappers.commission_rule_to_response(rule))


@router.get("/commission-rules")
async def list_commission_rules(service: ServiceDep, _actor: OwnerDep) -> ApiResponse[list[CommissionRuleResponse]]:
    rules = await service.list_commission_rules()
    return ApiResponse[list[CommissionRuleResponse]].ok([mappers.commission_rule_to_response(r) for r in rules])


@router.get("/commission-rules/{rule_id}")
async def get_commission_rule(rule_id: str, service: ServiceDep, _actor: OwnerDep) -> ApiResponse[CommissionRuleResponse]:
    rule = await service.get_commission_rule(rule_id)
    return ApiResponse[CommissionRuleResponse].ok(mappers.commission_rule_to_response(rule))


@router.patch("/commission-rules/{rule_id}")
async def update_commission_rule(
    rule_id: str, payload: UpdateCommissionRuleRequest, service: ServiceDep, actor: OwnerDep
) -> ApiResponse[CommissionRuleResponse]:
    rule = await service.update_commission_rule(rule_id, payload, actor)
    return ApiResponse[CommissionRuleResponse].ok(mappers.commission_rule_to_response(rule))


@router.patch("/commission-rules/{rule_id}/activate")
async def activate_commission_rule(rule_id: str, service: ServiceDep, actor: OwnerDep) -> ApiResponse[CommissionRuleResponse]:
    rule = await service.set_commission_rule_active(rule_id, active=True, actor=actor)
    return ApiResponse[CommissionRuleResponse].ok(mappers.commission_rule_to_response(rule))


@router.patch("/commission-rules/{rule_id}/deactivate")
async def deactivate_commission_rule(rule_id: str, service: ServiceDep, actor: OwnerDep) -> ApiResponse[CommissionRuleResponse]:
    rule = await service.set_commission_rule_active(rule_id, active=False, actor=actor)
    return ApiResponse[CommissionRuleResponse].ok(mappers.commission_rule_to_response(rule))


# ---------------------------------------------------------------------- Owner: commission ledger


@router.get("/commission-entries")
async def list_commission_entries(
    service: ServiceDep, _actor: OwnerDep, page: PageParamsDep, partner_id: str | None = None, status: str | None = None
) -> ApiResponse[list[CommissionEntryResponse]]:
    entries, total = await service.list_commission_entries(partner_id=partner_id, status=status, skip=page.skip, limit=page.page_size)
    names = await service.resolve_partner_names(entries)
    items = [mappers.commission_entry_to_response(e, names.get(e.partner_id)) for e in entries]
    return ApiResponse[list[CommissionEntryResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.post("/commission-entries/{entry_id}/approve")
async def approve_commission_entry(entry_id: str, service: ServiceDep, actor: OwnerDep) -> ApiResponse[CommissionEntryResponse]:
    entry = await service.approve_commission_entry(entry_id, actor)
    return ApiResponse[CommissionEntryResponse].ok(mappers.commission_entry_to_response(entry, None))


@router.post("/commission-entries/{entry_id}/settle")
async def settle_commission_entry(
    entry_id: str, payload: SettleCommissionEntryRequest, service: ServiceDep, actor: OwnerDep
) -> ApiResponse[CommissionEntryResponse]:
    entry = await service.settle_commission_entry(entry_id, payload, actor)
    return ApiResponse[CommissionEntryResponse].ok(mappers.commission_entry_to_response(entry, None))
