"""Module 7 — Referral Partner Portal routes."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.referral_partner_management import mappers
from app.features.referral_partner_management.dependencies import (
    get_referral_partner_management_service,
    require_owner,
    require_referral_partner,
)
from app.features.referral_partner_management.finance import (
    AdjustmentInput,
    CommissionDecision,
    PayoutInput,
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
    partner = await service.get_own_partner(actor)
    products = await service.list_products(category)
    eligible_products = [p for p in products if not partner.applicable_product_ids or p.require_id() in partner.applicable_product_ids]
    items = [
        NamedMasterDataResponse(id=p.require_id(), name=p.name, description=p.description, status=p.status, created_at=p.created_at, updated_at=p.updated_at)
        for p in eligible_products
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
    service: ServiceDep, _actor: PartnerViewDep, page: PageParamsDep, search: str | None = None, approval_status: str | None = None, kyc_status: str | None = None
) -> ApiResponse[list[ReferralPartnerResponse]]:
    partners, total = await service.list_partners(search=search, approval_status=approval_status, skip=page.skip, limit=page.page_size, sort=page.sort, kyc_status=kyc_status)
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


# Versioned KYC is deliberately Owner-only for review and Partner-only for submission.
from app.features.referral_partner_management.kyc import PartnerKyc
from app.features.referral_partner_management.portal_models import (
    ConfirmDocument,
    DocumentTicket,
    KycConfiguration,
    KycDecision,
    KycDraft,
    PartnerSettings,
)


@router.get("/partner-portal/kyc/configuration")
async def kyc_configuration(service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    await PartnerKyc(service._db).partner(actor)
    return ApiResponse.ok(await PartnerKyc(service._db).configuration())


@router.get("/partner-portal/kyc")
async def own_kyc(service: ServiceDep, actor: PartnerDep, document_page: int = 1) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).state(actor, document_page=document_page))


@router.put("/partner-portal/kyc")
async def save_kyc(payload: KycDraft, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).draft(payload, actor))


@router.post("/partner-portal/kyc/submit")
async def submit_kyc(payload: KycDecision, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).submit(payload.version, actor))


@router.get("/partner-management/kyc/configuration")
async def owner_kyc_configuration(service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).configuration())


@router.post("/partner-management/kyc/configuration")
async def publish_kyc(payload: KycConfiguration, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).publish(payload, actor))


@router.get("/partner-management/kyc/{partner_id}")
async def review_kyc_state(partner_id: str, service: ServiceDep, actor: OwnerDep, document_page: int = 1) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).state(actor, partner_id, document_page=document_page))


@router.post("/partner-management/kyc/{partner_id}/review")
async def review_kyc(partner_id: str, payload: KycDecision, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).review(partner_id, payload, actor))


@router.post("/partner-portal/kyc/uploads")
async def kyc_upload(payload: DocumentTicket, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).upload(payload, actor))


@router.post("/partner-management/agreements/uploads")
async def agreement_upload(payload: DocumentTicket, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).upload(payload, actor, agreement=True))


@router.post("/partner-portal/kyc/uploads/confirm")
async def kyc_confirm(payload: ConfirmDocument, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).confirm(payload, actor))


@router.post("/partner-management/agreements/confirm")
async def agreement_confirm(payload: ConfirmDocument, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).confirm(payload, actor))


@router.get("/partner-portal/documents/{document_id}")
async def kyc_document(document_id: str, service: ServiceDep, actor: Annotated[User, Depends(get_current_active_user)]) -> Response:
    from fastapi.responses import Response
    data, mime = await PartnerKyc(service._db).document(document_id, actor)
    return Response(data, media_type=mime, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment; filename=partner-document"})


@router.post("/partner-management/documents/{document_id}/review")
async def review_kyc_document(document_id: str, payload: KycDecision, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerKyc(service._db).document_review(document_id, payload, actor))


@router.put("/partner-management/{partner_id}/settings")
async def partner_settings(partner_id: str, payload: PartnerSettings, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.core.exceptions import ConflictError, ValidationError
    from app.features.referral_partner_management.kyc import event, oid, public
    from app.utils.datetime import utc_now
    db = service._db
    for product_id in payload.applicable_product_ids:
        if not await db.loan_products.find_one({"_id": oid(product_id), "is_deleted": False, "status": "active"}):
            raise ValidationError("Select an active Loan Product for Partner restrictions.")
    async with await db.client.start_session() as session, session.start_transaction():
        before = await db.referral_partners.find_one({"_id": oid(partner_id), "version": payload.version, "is_deleted": False}, session=session)
        if not before:
            raise ConflictError("Partner changed; reload.")
        changes = payload.model_dump(exclude={"version"}, exclude_unset=True, mode="json")
        if "full_name" in changes and changes["full_name"] is None:
            raise ValidationError("Full name cannot be cleared.")
        if changes.get("full_name", before["full_name"]) != before["full_name"]:
            changes.update(kyc_status="reupload_required", approval_status="pending_approval")
            if before.get("current_kyc_id"):
                await db.partner_kyc_submissions.update_one({"_id": oid(before["current_kyc_id"])}, {"$set": {"status": "reupload_required"}, "$inc": {"version": 1}, "$push": {"review_history": {"decision": "reupload_required", "reason": "Owner corrected account name; KYC identity requires review", "at": utc_now(), "by": actor.require_id()}}}, session=session)
        changes.update(updated_at=utc_now(), updated_by=actor.require_id())
        result = await db.referral_partners.find_one_and_update(
            {"_id": oid(partner_id), "version": payload.version, "is_deleted": False},
            {"$set": changes, "$inc": {"version": 1}},
            return_document=True, session=session,
        )
        if not result:
            raise ConflictError("Partner changed; reload.")
        await event(db, actor, "partner_settings_updated", partner_id, session=session, detail={"before": {key: before.get(key) for key in ("account_active", "submission_mode", "applicable_product_ids")}, "after": {key: result.get(key) for key in ("account_active", "submission_mode", "applicable_product_ids")}, "account_detail_fields_changed": [key for key in ("full_name", "email", "business_name") if before.get(key) != result.get(key)]})
    return ApiResponse.ok(public(result))


@router.post("/commission-entries/{entry_id}/payouts")
async def record_payout(entry_id: str, payload: PayoutInput, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.finance import payout
    return ApiResponse.ok(await payout(service._db, entry_id, payload, actor))


@router.get("/partner-portal/payouts")
async def own_payouts(service: ServiceDep, actor: PartnerDep, page: PageParamsDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.kyc import public
    partner = await PartnerKyc(service._db).partner(actor)
    query = {"partner_id": str(partner["_id"])}
    rows = [public(r) async for r in service._db.commission_payouts.find(query, {"partner_id": 1, "entry_id": 1, "allocations": 1, "amount": 1, "status": 1, "payment_reference": 1, "payment_method": 1, "payment_date": 1, "confirmed_at": 1, "created_at": 1}).sort("confirmed_at", -1).skip(page.skip).limit(page.page_size)]
    return ApiResponse.ok(rows, meta=ResponseMeta(pagination=page.build_meta(await service._db.commission_payouts.count_documents(query))))


from app.features.referral_partner_management.referrals import (
    ClaimLink,
    LinkInput,
    PartnerReferrals,
    ReferralDraft,
    ReferralEdit,
)
from app.middleware.rate_limit import rate_limited


@router.post("/partner-portal/referrals")
async def manual_referral(payload: ReferralDraft, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerReferrals(service._db, service._redis).manual(payload, actor))


@router.get("/partner-portal/referrals")
async def own_referrals(service: ServiceDep, actor: PartnerDep, page: PageParamsDep, search: str = "", status: str = "") -> ApiResponse[Any]:
    import re
    partner = await PartnerKyc(service._db).partner(actor)
    query: dict[str, Any] = {"referral_attribution.partner_id": str(partner["_id"]), "is_deleted": False}
    if search:
        query["$or"] = [{"application_code": {"$regex": re.escape(search[:120]), "$options": "i"}}, {"form_data.full_name": {"$regex": re.escape(search[:120]), "$options": "i"}}]
    if status:
        query["status"] = status
    rows = [r async for r in service._db.applications.find(query, {"application_code": 1, "product_id": 1, "status": 1, "created_at": 1, "referral_attribution": 1, "form_data.full_name": 1}).sort("created_at", -1).skip(page.skip).limit(page.page_size)]
    from app.features.referral_partner_management.kyc import public
    statuses = {case["application_id"]: case["current_status"] async for case in service._db.application_workflows.find({"application_id": {"$in": [str(row["_id"]) for row in rows]}, "is_deleted": False}, {"application_id": 1, "current_status": 1})}
    for row in rows:
        case_status = statuses.get(str(row["_id"]))
        row["external_status"] = "Approved" if case_status in {"disbursed", "policy_issued"} else "Rejected" if case_status == "rejected" else "Under AFS review" if row["referral_attribution"].get("submitted_to_afs_at") else "Partner review required" if row["status"] == "submitted" else "Draft"
    return ApiResponse.ok([public(r) for r in rows], meta=ResponseMeta(pagination=page.build_meta(await service._db.applications.count_documents(query))))


@router.get("/partner-portal/referrals/{application_id}")
async def referral_detail(application_id: str, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerReferrals(service._db, service._redis).detail(application_id, actor))


@router.put("/partner-portal/referrals/{application_id}")
async def edit_referral(application_id: str, payload: ReferralEdit, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerReferrals(service._db, service._redis).edit(application_id, payload, actor))


@router.post("/partner-portal/referrals/{application_id}/submit")
async def submit_referral(application_id: str, payload: KycDecision, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerReferrals(service._db, service._redis).submit(application_id, payload.version, actor))


@router.get("/partner-portal/forms/{product_id}")
async def referral_form(product_id: str, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.referrals import eligible
    await eligible(service._db, actor, product_id)
    form = await PartnerReferrals(service._db, service._redis).customers._get_or_error_form_definition("loan", product_id)
    return ApiResponse.ok(await PartnerReferrals(service._db, service._redis).form_payload(form))


@router.post("/partner-portal/links")
async def create_referral_link(payload: LinkInput, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerReferrals(service._db, service._redis).link(payload, actor))


@router.get("/partner-portal/links")
async def own_referral_links(service: ServiceDep, actor: PartnerDep, page: PageParamsDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.kyc import public
    partner = await PartnerKyc(service._db).partner(actor)
    query = {"partner_id": str(partner["_id"])}
    rows = [public(r) async for r in service._db.partner_referral_links.find(query, {"token_hash": 0, "user_id": 0}).sort("created_at", -1).skip(page.skip).limit(page.page_size)]
    return ApiResponse.ok(rows, meta=ResponseMeta(pagination=page.build_meta(await service._db.partner_referral_links.count_documents(query))))


@router.post("/partner-referral/claim", dependencies=[rate_limited(10)])
async def claim_referral(payload: ClaimLink, service: ServiceDep, actor: Annotated[User, Depends(get_current_active_user)]) -> ApiResponse[Any]:
    return ApiResponse.ok(await PartnerReferrals(service._db, service._redis).redeem(payload.token, actor))


@router.post("/partner-management/links/{link_id}/revoke")
async def revoke_referral(link_id: str, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.core.exceptions import NotFoundError
    from app.features.referral_partner_management.kyc import event, oid
    async with await service._db.client.start_session() as session, session.start_transaction():
        row = await service._db.partner_referral_links.find_one_and_update({"_id": oid(link_id)}, {"$set": {"status": "revoked"}}, return_document=True, session=session)
        if not row:
            raise NotFoundError("Link not found.")
        await event(service._db, actor, "partner_referral_link_revoked", row["partner_id"], session=session, detail={"referral_id": row["referral_id"]})
    return ApiResponse.ok({"revoked": True})


@router.get("/partner-portal/referrals/{application_id}/documents")
async def own_referral_documents(application_id: str, service: ServiceDep, actor: PartnerDep) -> ApiResponse[Any]:
    from app.features.customer import mappers as customer_mappers
    referral_service = PartnerReferrals(service._db, service._redis)
    await referral_service.own(application_id, actor)
    documents = await referral_service.customers._documents.find_current_for_application(application_id)
    names = await referral_service.customers.resolve_document_type_names(documents)
    return ApiResponse.ok([customer_mappers.document_to_response(d, names.get(d.document_type_id, ""), referral_service.customers.document_download_url(d)) for d in documents])


@router.get("/partner-portal/metrics")
async def portal_metrics(service: ServiceDep, actor: PartnerDep, start: date | None = None, end: date | None = None) -> ApiResponse[Any]:
    from app.features.referral_partner_management.reporting import metrics
    return ApiResponse.ok(await metrics(service._db, actor, start=start, end=end))


@router.get("/partner-management/metrics")
async def partner_management_metrics(service: ServiceDep, actor: OwnerDep, start: date | None = None, end: date | None = None, partner_id: str | None = None, product_id: str | None = None) -> ApiResponse[Any]:
    from app.features.referral_partner_management.reporting import metrics
    return ApiResponse.ok(await metrics(service._db, actor, start=start, end=end, partner_id=partner_id, product_id=product_id))


@router.get("/partner-portal/rules")
async def own_applicable_rules(service: ServiceDep, actor: PartnerDep, page: PageParamsDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.kyc import public
    partner = await PartnerKyc(service._db).partner(actor)
    query = {"is_deleted": False, "status": "active", "partner_id": {"$in": [None, str(partner["_id"])]}}
    if partner.get("applicable_product_ids"):
        query["product_id"] = {"$in": [None, *partner["applicable_product_ids"]]}
    rows = [public(r) async for r in service._db.commission_rules.find(query, {"label": 1, "product_id": 1, "calculation_type": 1, "rate_or_amount": 1, "effective_from": 1, "effective_until": 1, "rule_version": 1, "terms": 1, "trigger_event": 1, "product_category": 1, "fixed_event_policy": 1}).sort("created_at", -1).skip(page.skip).limit(page.page_size)]
    from bson import ObjectId

    from app.features.referral_partner_management.kyc import oid
    product_ids = [oid(row["product_id"]) for row in rows if ObjectId.is_valid(row.get("product_id"))]
    names = {str(product["_id"]): product["name"] async for product in service._db.loan_products.find({"_id": {"$in": product_ids}}, {"name": 1})}
    for row in rows:
        row["product_name"] = names.get(str(row.get("product_id") or ""))
    return ApiResponse.ok(rows, meta=ResponseMeta(pagination=page.build_meta(await service._db.commission_rules.count_documents(query))))


from app.features.referral_partner_management.portal_models import SensitiveReview


@router.post("/partner-management/kyc/{partner_id}/reveal")
async def reveal_kyc_values(partner_id: str, payload: SensitiveReview, response: Response, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    import json

    from app.core.exceptions import NotFoundError
    from app.features.referral_partner_management.kyc import event
    from app.security.encryption import decrypt
    await PartnerKyc(service._db).partner(actor, partner_id)
    async with await service._db.client.start_session() as session, session.start_transaction():
        row = await service._db.partner_kyc_submissions.find_one({"partner_id": partner_id}, sort=[("created_at", -1)], session=session)
        if not row:
            raise NotFoundError("KYC submission not found.")
        await event(service._db, actor, "partner_sensitive_fields_reviewed", partner_id, session=session, detail={"submission_id": str(row["_id"]), "reason": payload.reason})
    values = json.loads(decrypt(row["values_cipher"]))
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse.ok({key: values.get(key, "") for key in ("pan_number", "account_number")})


@router.get("/partner-portal/payouts/statement")
async def payout_statement(service: ServiceDep, actor: PartnerDep, start: date | None = None, end: date | None = None) -> Response:
    from fastapi.responses import Response

    from app.core.exceptions import ValidationError
    from app.features.referral_partner_management.reporting import dates
    from app.features.reporting.schemas import ReportColumn, ReportResult
    from app.features.reporting.service import ReportingService
    partner = await PartnerKyc(service._db).partner(actor)
    query: dict[str, Any] = {"partner_id": str(partner["_id"]), "status": {"$nin": ["initiated", "cancelled"]}}
    bounds = dates(start, end)
    if bounds:
        query["confirmed_at"] = bounds
    if await service._db.commission_payouts.count_documents(query) > 10000:
        raise ValidationError("Narrow the statement date range to at most 10000 payments.")
    keys = {"payment_date": "Payment date", "amount": "Amount", "payment_method": "Method", "payment_reference": "Payment reference", "entry_id": "Commission reference"}
    rows = []
    async for row in service._db.commission_payouts.find(query, {key: 1 for key in keys}).sort("confirmed_at", -1).limit(10000):
        rows.append({key: ("'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value) for key in keys if (value := row.get(key)) is not None})
    result = ReportResult(columns=[ReportColumn(key=key, label=label) for key, label in keys.items()], rows=rows)
    csv_data = await ReportingService(service._db).export_result_csv(result, report_key="partner_payout_statement", actor=actor)
    return Response(csv_data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=partner-payout-statement.csv", "Cache-Control": "no-store"})


@router.post("/commission-entries/{entry_id}/decision")
async def commission_state_decision(entry_id: str, payload: CommissionDecision, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.finance import commission_decision
    return ApiResponse.ok(await commission_decision(service._db, entry_id, payload, actor))


@router.post("/commission-entries/{entry_id}/adjustments")
async def commission_adjustment(entry_id: str, payload: AdjustmentInput, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.finance import adjust
    return ApiResponse.ok(await adjust(service._db, entry_id, payload, actor))


@router.get("/partner-management/commission-exceptions")
async def commission_exceptions(service: ServiceDep, actor: OwnerDep, page: PageParamsDep, status: str = "open") -> ApiResponse[Any]:
    from app.features.referral_partner_management.kyc import public
    query = {"status": status} if status else {}
    rows = [public(row) async for row in service._db.commission_exceptions.find(query).sort("created_at", -1).skip(page.skip).limit(page.page_size)]
    return ApiResponse.ok(rows, meta=ResponseMeta(pagination=page.build_meta(await service._db.commission_exceptions.count_documents(query))))


@router.post("/partner-management/commission-exceptions/{exception_id}/resolve")
async def resolve_commission_exception(exception_id: str, payload: SensitiveReview, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.finance import resolve_exception
    return ApiResponse.ok(await resolve_exception(service._db, exception_id, payload.reason, actor))


from app.features.referral_partner_management.payouts import ConfirmPayment, ReservePayment


@router.post("/partner-management/payments")
async def reserve_partner_payment(payload: ReservePayment, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.payouts import reserve
    return ApiResponse.ok(await reserve(service._db, payload, actor))


@router.get("/partner-management/payments")
async def partner_payments(service: ServiceDep, actor: OwnerDep, page: PageParamsDep, status: str = "initiated") -> ApiResponse[Any]:
    from app.features.referral_partner_management.kyc import public
    query = {"status": status} if status else {}
    rows = [public(row) async for row in service._db.commission_payouts.find(query).sort("created_at", -1).skip(page.skip).limit(page.page_size)]
    return ApiResponse.ok(rows, meta=ResponseMeta(pagination=page.build_meta(await service._db.commission_payouts.count_documents(query))))


@router.post("/partner-management/payments/{payout_id}/confirm")
async def confirm_partner_payment(payout_id: str, payload: ConfirmPayment, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.payouts import finish
    return ApiResponse.ok(await finish(service._db, payout_id, actor, confirmation=payload))


@router.post("/partner-management/payments/{payout_id}/cancel")
async def cancel_partner_payment(payout_id: str, payload: SensitiveReview, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.payouts import finish
    return ApiResponse.ok(await finish(service._db, payout_id, actor, reason=payload.reason))


from app.features.referral_partner_management.management import AttributionCorrection
from app.features.referral_partner_management.models import CommissionEntry


@router.put("/partner-management/referrals/{application_id}/attribution")
async def correct_partner_attribution(application_id: str, payload: AttributionCorrection, service: ServiceDep, actor: OwnerDep) -> ApiResponse[Any]:
    from app.features.referral_partner_management.management import correct_attribution
    return ApiResponse.ok(await correct_attribution(service._db, application_id, payload, actor))


@router.get("/partner-management/referrals")
async def management_referrals(service: ServiceDep, actor: OwnerDep, page: PageParamsDep, partner_id: str | None = None, product_id: str | None = None, status: str | None = None, origin: str | None = None, start: date | None = None, end: date | None = None) -> ApiResponse[Any]:
    from app.features.referral_partner_management.kyc import public
    from app.features.referral_partner_management.reporting import dates
    query: dict[str, Any] = {"is_deleted": False, "referral_attribution.partner_id": partner_id if partner_id else {"$exists": True}}
    for key, value in (("product_id", product_id), ("status", status), ("referral_attribution.origin", origin)):
        if value:
            query[key] = value
    if bounds := dates(start, end):
        query["created_at"] = bounds
    rows = [public(row) async for row in service._db.applications.find(query, {"application_code": 1, "customer_id": 1, "product_id": 1, "status": 1, "version": 1, "created_at": 1, "form_data.full_name": 1, "referral_attribution": 1}).sort("created_at", -1).skip(page.skip).limit(page.page_size)]
    return ApiResponse.ok(rows, meta=ResponseMeta(pagination=page.build_meta(await service._db.applications.count_documents(query))))


@router.get("/partner-management/report")
async def management_report(service: ServiceDep, actor: OwnerDep, partner_id: str | None = None, product_id: str | None = None, origin: str | None = None, application_status: str | None = None, disbursement_status: str | None = None, commission_status: str | None = None, start: date | None = None, end: date | None = None, export: bool = False) -> Any:
    from app.features.referral_partner_management.reporting import owner_report
    from app.features.reporting.service import ReportingService
    report = await owner_report(service._db, actor, partner_id=partner_id, product_id=product_id, origin=origin, application_status=application_status, disbursement_status=disbursement_status, commission_status=commission_status, start=start, end=end)
    if not export:
        return ApiResponse.ok(report)
    # Formula-safe CSV values, using the existing authorized export and audit service.
    for row in report.rows:
        for key, value in row.items():
            if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                row[key] = "'" + value
    csv_data = await ReportingService(service._db).export_result_csv(report, report_key="partner_referral_finance", actor=actor)
    return Response(csv_data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=partner-referral-report.csv", "Cache-Control": "no-store"})


@router.get("/partner-management/links")
async def management_links(service: ServiceDep, actor: OwnerDep, page: PageParamsDep, partner_id: str | None = None) -> ApiResponse[Any]:
    from app.features.referral_partner_management.kyc import public
    query = {"partner_id": partner_id} if partner_id else {}
    projection = {"partner_id": 1, "referral_id": 1, "product_id": 1, "submission_mode": 1, "status": 1, "expires_at": 1, "application_id": 1, "created_at": 1}
    rows = [public(row) async for row in service._db.partner_referral_links.find(query, projection).sort("created_at", -1).skip(page.skip).limit(page.page_size)]
    return ApiResponse.ok(rows, meta=ResponseMeta(pagination=page.build_meta(await service._db.partner_referral_links.count_documents(query))))


@router.get("/partner-portal/commission-statement")
async def commission_statement(service: ServiceDep, actor: PartnerDep, start: date | None = None, end: date | None = None) -> Response:
    from app.core.exceptions import ValidationError
    from app.features.referral_partner_management.reporting import dates
    from app.features.reporting.schemas import ReportColumn, ReportResult
    from app.features.reporting.service import ReportingService
    partner = await PartnerKyc(service._db).partner(actor)
    query: dict[str, Any] = {"partner_id": str(partner["_id"]), "is_deleted": False}
    if bounds := dates(start, end):
        query["created_at"] = bounds
    if await service._db.commission_entries.count_documents(query) > 10000:
        raise ValidationError("Narrow the statement date range to at most 10000 commissions.")
    keys = {"id": "Commission", "application_id": "Application", "case_id": "Case", "base_amount": "Original eligible base", "rate_or_amount": "Original rate", "rule_version": "Original rule version", "total_earned_amount": "Total earned", "adjusted_amount": "Adjustments", "paid_amount": "Paid", "reserved_amount": "Reserved", "outstanding_amount": "Outstanding", "status": "Status"}
    rows = [mappers.commission_entry_to_response(CommissionEntry.model_validate(row), None).model_dump(include=set(keys)) async for row in service._db.commission_entries.find(query).sort("created_at", -1).limit(10000)]
    report = ReportResult(columns=[ReportColumn(key=key, label=label) for key, label in keys.items()], rows=rows)
    csv_data = await ReportingService(service._db).export_result_csv(report, report_key="partner_commission_statement", actor=actor)
    return Response(csv_data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=partner-commission-statement.csv", "Cache-Control": "no-store"})


@router.get("/commission-entries/{entry_id}/history")
async def commission_history(entry_id: str, service: ServiceDep, actor: Annotated[User, Depends(get_current_active_user)], page: PageParamsDep) -> ApiResponse[Any]:
    from app.core.exceptions import ForbiddenError, NotFoundError
    from app.features.referral_partner_management.kyc import oid, public
    query: dict[str, Any] = {"_id": oid(entry_id), "is_deleted": False}
    if actor.role == "referral_partner":
        partner = await PartnerKyc(service._db).partner(actor)
        query["partner_id"] = str(partner["_id"])
    elif actor.role != "owner":
        raise ForbiddenError("Only Owner or the owning Partner can view commission history.")
    entry = await service._db.commission_entries.find_one(query)
    if not entry:
        raise NotFoundError("Commission history not found.")
    original = {"kind": "original_earning", "amount": entry["commission_amount"], "base_amount": entry["base_amount"], "rate_or_amount": entry["rate_or_amount"], "calculation_type": entry["calculation_type"], "fixed_event_policy": entry.get("fixed_event_policy"), "rule_version": entry.get("rule_version", 1), "rule_id": entry["rule_id"], "financial_at": entry.get("financial_at"), "created_at": entry.get("created_at"), "disbursement_event_id": entry.get("disbursement_event_id")}
    # No internal adjustment reasons, actor IDs, fingerprints or unrelated Case fields.
    projection = {"kind": 1, "amount": 1, "base_amount": 1, "rate_or_amount": 1, "calculation_type": 1, "fixed_event_policy": 1, "rule_version": 1, "rule_id": 1, "financial_at": 1, "created_at": 1, "disbursement_event_id": 1}
    event_query = {"entry_id": entry_id}
    rows = [public(row) async for row in service._db.commission_entry_events.find(event_query, projection).sort("created_at", 1).skip(page.skip).limit(page.page_size)]
    return ApiResponse.ok({"original": original, "events": rows}, meta=ResponseMeta(pagination=page.build_meta(await service._db.commission_entry_events.count_documents(event_query))))
