"""Module 9B — Lead Capture business logic.

`_process_raw_payload` is the one shared pipeline every capture source funnels
through — parse -> validate -> resolve Source Mapping -> `LeadService.create_lead`
(Module 6A, frozen, unmodified) -> Timeline entry -> idempotency receipt. The exact same
function is called from the live Website/Meta paths and from the retry queue, so a
retried capture behaves identically to a first attempt.
"""

import hashlib
import hmac
import json
import logging
import re
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError as PydanticValidationError

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.insurance_management.schemas import CreateManualInsuranceCaseRequest
from app.features.insurance_management.service import InsuranceCaseService
from app.features.integrations import mappers as integrations_mappers
from app.features.integrations import oauth as oauth_client
from app.features.lead_capture import meta_client
from app.features.lead_capture.constants import (
    LEAD_ACTIVITY_CAPTURED,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_MINUTES,
    AuditEvent,
    CaptureSourceKey,
    FailureReason,
    FailureStatus,
    MetaDestination,
    MetaProductMode,
)
from app.features.lead_capture.models import (
    CaptureFailure,
    CaptureReceipt,
    CaptureSource,
    MetaLeadRouting,
)
from app.features.lead_capture.parsers import (
    CaptureValidationError,
    ParsedLead,
    parse_meta_fields,
    parse_website_payload,
)
from app.features.lead_capture.repository import (
    CaptureFailureRepository,
    CaptureReceiptRepository,
    CaptureSourceRepository,
    MetaLeadRoutingRepository,
)
from app.features.lead_capture.schemas import (
    ManualCaptureRequest,
    MetaLeadRoutingUpsertRequest,
    UpdateCaptureSourceRequest,
    WebsiteCaptureRequest,
)
from app.features.leads.constants import ProductCategory
from app.features.leads.models import Lead, LeadActivity
from app.features.leads.repository import LeadActivityRepository, LeadRepository
from app.features.leads.schemas import CreateLeadRequest
from app.features.leads.service import LeadService
from app.features.system_settings.constants import MasterDataStatus
from app.features.system_settings.repository import (
    InsuranceCategoryRepository,
    InsuranceProductRepository,
    LeadSourceRepository,
    LoanProductRepository,
)
from app.features.workflow_engine.constants import InsuranceStatus
from app.security.encryption import decrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now
from app.utils.helpers import is_valid_object_id, to_object_id

logger = logging.getLogger(__name__)


class LeadCaptureService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._sources = CaptureSourceRepository(db)
        self._failures = CaptureFailureRepository(db)
        self._receipts = CaptureReceiptRepository(db)
        self._meta_routings = MetaLeadRoutingRepository(db)
        self._users = UserRepository(db)
        self._leads = LeadRepository(db)
        self._activities = LeadActivityRepository(db)
        self._lead_service = LeadService(db)
        self._lead_sources = LeadSourceRepository(db)
        self._loan_products = LoanProductRepository(db)
        self._insurance_categories = InsuranceCategoryRepository(db)
        self._insurance_products = InsuranceProductRepository(db)

    # ================================================================== system actor (no human in the loop)

    async def _system_actor(self) -> User:
        # Same precedent as CustomerService._any_owner() (Module 6B, decision 053) — a
        # real, persisted Owner is required to satisfy LeadService.create_lead's
        # actor.require_id() call; the resulting Lead's created_by is nulled out
        # immediately afterward so it never looks like that Owner personally created it.
        owners = await self._users.find_many({"role": OWNER}, limit=1)
        if not owners:
            raise ValidationError("No Owner account exists yet to attribute a system capture to.")
        return owners[0]

    async def _get_source(self, key: str) -> CaptureSource:
        source = await self._sources.find_by_key(key)
        if source is None:
            raise ValidationError(f"Capture source '{key}' is not configured. Run the seed script.")
        return source

    # ================================================================== the shared pipeline

    async def _process_raw_payload(self, capture_source: str, raw_payload: dict[str, Any]) -> Any:
        if capture_source == CaptureSourceKey.WEBSITE_FORM:
            parsed = parse_website_payload(raw_payload)
            external_id = None
        elif capture_source == CaptureSourceKey.META_LEAD_ADS:
            parsed, external_id = await self._parse_meta_entry(raw_payload)
        else:
            raise ValidationError(f"'{capture_source}' has no retry/processing pipeline.")

        if external_id:
            existing = await self._receipts.find_existing(capture_source, external_id)
            if existing is not None:
                if existing.destination_module == MetaDestination.INSURANCE_POLICY_LEADS:
                    record_id = existing.destination_record_id or ""
                    found = await self._db["application_workflows"].find_one(
                        {"_id": to_object_id(record_id)}
                    ) if is_valid_object_id(record_id) else None
                else:
                    found = await self._leads.find_by_id(existing.lead_id) if existing.lead_id else None
                if found is not None:
                    logger.info(
                        "Capture delivery already processed: source=%s external_id=%s lead_id=%s",
                        capture_source, external_id,
                        str(found["_id"]) if isinstance(found, dict) else found.require_id(),
                    )
                    return found  # already processed — idempotent no-op, not a failure

        source = await self._get_source(capture_source)
        actor = await self._system_actor()
        lead: Any
        if parsed.destination_module == MetaDestination.INSURANCE_POLICY_LEADS:
            product = await self._insurance_products.find_by_id(parsed.product_id)
            if product is None or not product.category_id:
                raise CaptureValidationError(FailureReason.INVALID_PRODUCT, "Configured insurance product is unavailable.")
            lead = await InsuranceCaseService(self._db).create_manual_case(
                CreateManualInsuranceCaseRequest(
                    full_name=parsed.full_name, mobile=parsed.mobile, email=parsed.email,
                    insurance_category_id=product.category_id, product_id=parsed.product_id,
                    remarks=parsed.remarks, stage=InsuranceStatus.FRESH_LEAD,
                ), actor,
            )
        else:
            lead = await self._lead_service.create_lead(
                CreateLeadRequest(
                    full_name=parsed.full_name, mobile=parsed.mobile, email=parsed.email, source_id=source.lead_source_id,
                    product_category=parsed.product_category, product_id=parsed.product_id, remarks=parsed.remarks,
                ),
                actor,
            )
            await self._leads.update(lead.require_id(), {"created_by": None})
        logger.info(
            "Capture created destination record: source=%s external_id=%s record_id=%s destination=%s",
            capture_source, external_id, lead.require_id(), parsed.destination_module,
        )

        activity = LeadActivity(
            lead_id=lead.require_id(), event_type=LEAD_ACTIVITY_CAPTURED,
            metadata={
                "capture_source": capture_source, "imported_by": f"system:{capture_source}", "external_id": external_id,
                # Campaign/ad set/ad/form/UTM — reserved per the user's own
                # recommendation, captured only when the source's own payload actually
                # supplies it (never fabricated). See parsers.py:extract_source_metadata.
                "source_metadata": parsed.source_metadata,
            },
        )
        if parsed.destination_module == MetaDestination.LEADS:
            await self._activities.insert(activity)
        await write_audit_log(
            self._db, event_type=AuditEvent.LEAD_CAPTURED, user_id=actor.require_id(), metadata={"lead_id": lead.require_id(), "capture_source": capture_source}
        )

        if external_id:
            await self._receipts.insert(CaptureReceipt(
                capture_source=capture_source, external_id=external_id,
                lead_id=lead.require_id() if parsed.destination_module == MetaDestination.LEADS else None,
                destination_module=parsed.destination_module, destination_record_id=lead.require_id(),
            ))

        logger.info(
            "Capture processing completed: source=%s external_id=%s lead_id=%s activity_recorded=true audit_recorded=true receipt_recorded=%s",
            capture_source, external_id, lead.require_id(), bool(external_id),
        )

        return lead

    @staticmethod
    def _normalize_match(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    async def _validate_routing_product(self, category: str, product_id: str) -> None:
        if not is_valid_object_id(product_id):
            raise CaptureValidationError(FailureReason.INVALID_PRODUCT, "Configured product ID is invalid.")
        if category == ProductCategory.LOAN:
            loan_product = await self._loan_products.find_by_id(product_id)
            if loan_product is None:
                if await self._insurance_products.find_by_id(product_id) is not None:
                    raise CaptureValidationError(FailureReason.CATEGORY_PRODUCT_MISMATCH, "Configured product belongs to Insurance, not Loan.")
                raise CaptureValidationError(FailureReason.INVALID_PRODUCT, "Configured Loan product does not exist.")
            if loan_product.status != MasterDataStatus.ACTIVE:
                raise CaptureValidationError(FailureReason.INACTIVE_PRODUCT, "Configured Loan product is inactive.")
            return
        if category == ProductCategory.INSURANCE:
            insurance_product = await self._insurance_products.find_by_id(product_id)
            if insurance_product is None:
                if await self._loan_products.find_by_id(product_id) is not None:
                    raise CaptureValidationError(FailureReason.CATEGORY_PRODUCT_MISMATCH, "Configured product belongs to Loan, not Insurance.")
                raise CaptureValidationError(FailureReason.INVALID_PRODUCT, "Configured Insurance product does not exist.")
            if insurance_product.status != MasterDataStatus.ACTIVE:
                raise CaptureValidationError(FailureReason.INACTIVE_PRODUCT, "Configured Insurance product is inactive.")
            category_doc = await self._insurance_categories.find_by_id(insurance_product.category_id or "") if insurance_product.category_id else None
            if category_doc is None or category_doc.status != MasterDataStatus.ACTIVE:
                raise CaptureValidationError(FailureReason.CATEGORY_PRODUCT_MISMATCH, "Insurance product is not in an active category.")
            return
        raise CaptureValidationError(FailureReason.INVALID_CATEGORY, "Routing category must be loan or insurance.")

    async def _resolve_meta_routing(self, form_id: str, graph_payload: dict[str, Any]) -> tuple[MetaLeadRouting, str]:
        routing = await self._meta_routings.find_by_form_id(form_id)
        answer_values = meta_client.parse_custom_answer_values(graph_payload)
        questions = list(answer_values)
        if routing is None:
            routing_id = await self._meta_routings.insert(MetaLeadRouting(
                meta_form_id=form_id, form_name=form_id, status="unconfigured", discovered_questions=questions,
            ))
            routing = await self._meta_routings.find_by_id(routing_id)
        elif questions and set(questions) != set(routing.discovered_questions):
            routing = await self._meta_routings.update(routing.require_id(), {"discovered_questions": questions})
        assert routing is not None
        if routing.status != MasterDataStatus.ACTIVE or not routing.category or not routing.product_mode or not routing.destination_module:
            raise CaptureValidationError(FailureReason.UNCONFIGURED_FORM, f"Meta form {form_id} needs routing configuration.")
        if routing.category == ProductCategory.LOAN and routing.destination_module != MetaDestination.LEADS:
            raise CaptureValidationError(FailureReason.INVALID_DESTINATION, "Loan routes must use the Leads destination.")
        if routing.category == ProductCategory.INSURANCE and routing.destination_module != MetaDestination.INSURANCE_POLICY_LEADS:
            raise CaptureValidationError(FailureReason.INVALID_DESTINATION, "Insurance routes must use Insurance Policy Leads.")

        if routing.product_mode == MetaProductMode.DEFAULT:
            product_id = routing.default_product_id or ""
            if not product_id:
                raise CaptureValidationError(FailureReason.INVALID_PRODUCT, "Default-product route has no product.")
        elif routing.product_mode == MetaProductMode.CUSTOMER_ANSWER:
            configured = routing.product_question_key or routing.product_question_label
            if not configured:
                raise CaptureValidationError(FailureReason.QUESTION_NOT_FOUND, "Customer-answer route has no configured question.")
            wanted = self._normalize_match(configured)
            matches = [(key, answer) for key, answer in answer_values.items() if self._normalize_match(key) == wanted]
            if not matches:
                raise CaptureValidationError(FailureReason.QUESTION_NOT_FOUND, "Configured product question was not present in Meta field_data.")
            raw_answer = matches[0][1]
            if raw_answer is None or not raw_answer.strip():
                raise CaptureValidationError(FailureReason.ANSWER_NOT_FOUND, "Configured product question had no answer.")
            answer = raw_answer.strip()
            mappings = {self._normalize_match(key): value for key, value in routing.answer_mappings.items()}
            product_id = mappings.get(self._normalize_match(answer), "")
            if not product_id:
                raise CaptureValidationError(FailureReason.ANSWER_NOT_MAPPED, "Meta product answer has no configured product mapping.")
        else:
            raise CaptureValidationError(FailureReason.INVALID_DATA, "Unknown Meta product mode.")
        await self._validate_routing_product(routing.category, product_id)
        return routing, product_id

    async def _parse_meta_entry(self, entry: dict[str, Any]) -> tuple[ParsedLead, str]:
        leadgen_id = entry.get("leadgen_id")
        if not leadgen_id:
            raise CaptureValidationError(FailureReason.MISSING_REQUIRED_FIELDS, "Meta webhook entry is missing leadgen_id.")
        logger.info("Meta lead retrieval starting: leadgen_id=%s form_id=%s", leadgen_id, entry.get("form_id"))

        config = await self._active_config("meta")
        if config is None:
            raise ValidationError("No active Meta integration configuration exists — configure one in API Management (Module 9A) first.")
        decrypted = json.loads(decrypt(config["config_encrypted"])) if config.get("config_encrypted") else {}
        access_token = decrypted.get("access_token")
        if not access_token:
            raise ValidationError("The active Meta configuration has no access_token set.")

        preserved_fields = entry.get("_retrieved_field_data")
        graph_payload = (
            {"field_data": preserved_fields}
            if isinstance(preserved_fields, list)
            else await meta_client.fetch_lead_fields(leadgen_id, access_token=access_token)
        )
        entry["_retrieved_field_data"] = graph_payload.get("field_data", [])
        fields = meta_client.parse_field_data(graph_payload)
        logger.info(
            "Meta lead fields retrieved: leadgen_id=%s has_name=%s has_mobile=%s has_email=%s",
            leadgen_id, bool(fields.get("full_name")), bool(fields.get("mobile")), bool(fields.get("email")),
        )
        form_id = str(entry.get("form_id") or "").strip()
        if not form_id:
            raise CaptureValidationError(FailureReason.UNCONFIGURED_FORM, "Meta webhook entry has no form_id; routing cannot be resolved.")
        routing, product_id = await self._resolve_meta_routing(form_id, graph_payload)
        logger.info(
            "Meta routing resolved: leadgen_id=%s form_id=%s category=%s product_mode=%s product_id=%s destination=%s",
            leadgen_id, form_id, routing.category, routing.product_mode, product_id, routing.destination_module,
        )
        parsed = parse_meta_fields(
            fields, default_product_category=routing.category, default_product_id=product_id, raw_entry=entry
        )
        parsed = replace(parsed, destination_module=routing.destination_module or MetaDestination.LEADS)

        # Resolves the webhook envelope's bare `ad_id` into readable Campaign/Ad Set/Ad
        # names — best-effort (needs `ads_read` + access to the ad's own ad account);
        # `fetch_ad_campaign_details` itself never raises, an empty dict just means "not
        # resolvable," same as Meta never having supplied `ad_id` in the first place.
        ad_id = entry.get("ad_id")
        if ad_id:
            campaign_details = await oauth_client.fetch_ad_campaign_details(access_token=access_token, ad_id=str(ad_id))
            if campaign_details:
                parsed = replace(parsed, source_metadata={**parsed.source_metadata, **campaign_details})

        return parsed, str(leadgen_id)

    async def _active_config(self, integration_type: str) -> dict[str, Any] | None:
        doc = await self._db["integration_configs"].find_one({"integration_type": integration_type, "is_active": True, "is_deleted": False})
        return doc

    # ================================================================== failure recording

    async def _record_failure(self, capture_source: str, reason: str, raw_payload: dict[str, Any], detail: str | None) -> CaptureFailure:
        routing_reasons = {
            FailureReason.UNCONFIGURED_FORM, FailureReason.QUESTION_NOT_FOUND,
            FailureReason.ANSWER_NOT_FOUND, FailureReason.ANSWER_NOT_MAPPED,
            FailureReason.INVALID_CATEGORY, FailureReason.INVALID_PRODUCT,
            FailureReason.INACTIVE_PRODUCT, FailureReason.CATEGORY_PRODUCT_MISMATCH,
            FailureReason.INVALID_DESTINATION,
        }
        status = (
            FailureStatus.PENDING if reason == FailureReason.API_ERROR
            else FailureStatus.NEEDS_ROUTING_CONFIGURATION if reason in routing_reasons
            else FailureStatus.IGNORED
        )
        next_retry_at = utc_now() + timedelta(minutes=RETRY_BACKOFF_MINUTES) if status == FailureStatus.PENDING else None
        failure = CaptureFailure(capture_source=capture_source, failure_reason=reason, raw_payload=raw_payload, error_detail=detail, status=status, next_retry_at=next_retry_at)
        failure_id = await self._failures.insert(failure)
        await write_audit_log(self._db, event_type=AuditEvent.CAPTURE_FAILED, user_id=None, metadata={"failure_id": failure_id, "capture_source": capture_source, "reason": reason})
        logger.warning(
            "Capture processing failed: source=%s external_id=%s failure_id=%s reason=%s",
            capture_source, raw_payload.get("leadgen_id"), failure_id, reason,
        )
        found = await self._failures.find_by_id(failure_id)
        assert found is not None
        return found

    # ================================================================== website form (public)

    async def capture_from_website(self, payload: WebsiteCaptureRequest) -> Lead:
        raw = payload.model_dump(exclude_none=True)
        try:
            return cast(Lead, await self._process_raw_payload(CaptureSourceKey.WEBSITE_FORM, raw))
        except CaptureValidationError as exc:
            await self._record_failure(CaptureSourceKey.WEBSITE_FORM, exc.reason, raw, exc.detail)
            raise ValidationError(exc.detail) from exc
        except ValidationError as exc:
            await self._record_failure(CaptureSourceKey.WEBSITE_FORM, FailureReason.INVALID_DATA, raw, str(exc))
            raise
        except PydanticValidationError as exc:
            # E.g. a malformed email from a website visitor — `CreateLeadRequest`'s own
            # pydantic validation, distinct from the app's `ValidationError` above, was
            # previously uncaught here and reached the generic 500 handler: the visitor's
            # typo became a server error AND the lead was lost with no CaptureFailure
            # record at all, contradicting this module's own "never lose inbound
            # requests" contract. Recorded and converted the same way.
            await self._record_failure(CaptureSourceKey.WEBSITE_FORM, FailureReason.INVALID_DATA, raw, str(exc))
            raise ValidationError(str(exc)) from exc

    # ================================================================== manual API (staff, controlled)

    async def capture_manual(self, payload: ManualCaptureRequest, actor: User) -> Lead:
        source = await self._get_source(CaptureSourceKey.MANUAL_API)
        return await self._lead_service.create_lead(
            CreateLeadRequest(
                full_name=payload.full_name, mobile=payload.mobile, email=payload.email, source_id=source.lead_source_id,
                product_category=payload.product_category, product_id=payload.product_id, remarks=payload.remarks,
            ),
            actor,
        )

    # ================================================================== Meta webhook (public, signature-verified)

    async def verify_meta_challenge(self, *, mode: str | None, verify_token: str | None) -> bool:
        """Meta's webhook GET verification handshake (`hub.mode=subscribe`).

        ROOT-CAUSE FIX: this used to look up `_active_config("meta")` — i.e. only the one
        `IntegrationConfig` currently flagged `is_active=True` for live lead processing.
        But a brand-new Meta config is *never* active until an Owner has completed OAuth
        Connect *and* a successful Test Connection *and* Activate — while pasting the
        Callback URL + Verify Token into Meta's own App Dashboard and clicking "Verify and
        Save" is normally the very first step, done before any of that. `_active_config`
        therefore always returned `None` at exactly the moment Meta calls this endpoint,
        so every real-world verification attempt got a 403 — reproduced directly against
        the old code (a config created via the normal API, using its own freshly-generated
        `webhook_verify_token`, got HTTP 403 from this exact handshake).

        The fix: verification is "does the received token match *any* configured Meta
        credential set," full stop — it has nothing to do with which config is currently
        live for processing. That's a separate, correct use of `is_active` and stays
        unchanged in `handle_meta_webhook`/`_active_config` below, since exactly one
        config may ever actually process leads at a time.
        """
        matched_config_id: str | None = None
        async for doc in self._db["integration_configs"].find({"integration_type": "meta", "is_deleted": False}):
            decrypted = json.loads(decrypt(doc["config_encrypted"])) if doc.get("config_encrypted") else {}
            expected = decrypted.get("webhook_verify_token")
            matched = meta_client.verify_challenge(mode=mode, verify_token=verify_token, expected_token=expected or "")
            logger.info(
                "Meta webhook verify_token check: config_id=%s mode=%s configured=%s received=%s match=%s",
                doc["_id"], mode,
                integrations_mappers.mask_secret(expected) if expected else "(not set)",
                integrations_mappers.mask_secret(verify_token) if verify_token else "(none)",
                matched,
            )
            if matched:
                matched_config_id = str(doc["_id"])
                break

        if matched_config_id is None:
            logger.warning("Meta webhook verification failed — no configured Meta integration's webhook_verify_token matched the received value.")
            return False

        # The one genuine signal available for "Webhook Status" on the Connection Health
        # panel (Module 9A) — recorded on whichever config actually matched, not
        # necessarily "the active one."
        await self._db["integration_configs"].update_one({"_id": to_object_id(matched_config_id)}, {"$set": {"webhook_verified_at": utc_now()}})
        return True

    async def handle_meta_webhook(self, raw_body: bytes, signature_header: str | None) -> bool:
        # TEMPORARY diagnostics below (investigating the 403 on POST despite a
        # confirmed-working Page subscription) — every `logger.info`/`logger.error` call
        # tagged [TEMP DIAGNOSTIC:webhook_post] is purely observational. The two `if`
        # checks that follow (`config is None` / `not secret or not verify_signature`)
        # are UNCHANGED in what they test and UNCHANGED in what they return — only split
        # into separately-logged branches so the two previously-indistinguishable causes
        # of the same 403 can be told apart from the logs alone. Safe to delete every
        # line tagged [TEMP DIAGNOSTIC:webhook_post] once the root cause is confirmed.
        active_query = {"integration_type": "meta", "is_active": True, "is_deleted": False}
        logger.info("[TEMP DIAGNOSTIC:webhook_post] active-config query on 'integration_configs': %s", active_query)
        config = await self._active_config("meta")
        if config is None:
            logger.error(
                "[TEMP DIAGNOSTIC:webhook_post] NO ACTIVE META CONFIG — query %s returned no document. "
                "Either no Meta config exists, or one exists but is_active=False/is_deleted=True. "
                "This alone is enough to cause the reported 403, independent of the webhook signature.",
                active_query,
            )
            return False
        logger.info(
            "[TEMP DIAGNOSTIC:webhook_post] active config found: _id=%s integration_code=%s is_enabled=%s is_active=%s",
            config.get("_id"), config.get("integration_code"), config.get("is_enabled"), config.get("is_active"),
        )

        decrypted = json.loads(decrypt(config["config_encrypted"])) if config.get("config_encrypted") else {}
        # ROOT-CAUSE FIX: Meta signs every webhook POST body with HMAC-SHA256 keyed by
        # the App's own App Secret (App Dashboard -> App Settings -> Basic) — confirmed
        # against Meta's documented webhook contract, not assumed. There is no separate,
        # user-configurable "webhook signing secret" anywhere in Meta's Webhooks product;
        # the only thing you paste into that dashboard is a Verify Token (used solely for
        # the one-time GET handshake, a completely different value). This code used to
        # compare against `webhook_secret` — a random string this app generates for
        # itself and that Meta has never seen or used — which made every single
        # X-Hub-Signature-256 comparison fail deterministically, 100% of the time, no
        # matter what was pasted anywhere. `app_secret` is the value OAuth already proved
        # correct (it's required for the token-exchange calls that already succeeded).
        secret = decrypted.get("app_secret")
        logger.info(
            "[TEMP DIAGNOSTIC:webhook_post] config_encrypted decrypted OK=%s app_secret_present=%s app_secret_masked=%s",
            bool(config.get("config_encrypted")), bool(secret), integrations_mappers.mask_secret(secret) if secret else "(empty)",
        )
        if not secret:
            logger.error("[TEMP DIAGNOSTIC:webhook_post] APP SECRET NOT CONFIGURED on the active config — signature can never match.")
            return False

        # Redundant, logging-only HMAC recomputation — the real pass/fail decision below
        # still comes exclusively from the unmodified `meta_client.verify_signature`.
        received_masked = integrations_mappers.mask_secret(signature_header) if signature_header else "(none)"
        calculated_signature = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        calculated_masked = integrations_mappers.mask_secret(calculated_signature)
        signature_matches = meta_client.verify_signature(raw_body=raw_body, signature_header=signature_header, secret=secret)
        logger.info(
            "[TEMP DIAGNOSTIC:webhook_post] signature check: received=%s calculated=%s match=%s raw_body_length=%s",
            received_masked, calculated_masked, signature_matches, len(raw_body),
        )
        if not signature_matches:
            logger.error(
                "[TEMP DIAGNOSTIC:webhook_post] SIGNATURE VERIFICATION FAILED — received %s vs calculated %s using the active "
                "config's app_secret. This is the OTHER possible cause of the reported 403, independent of active-config lookup.",
                received_masked, calculated_masked,
            )
            return False

        # OAuth Connect (Module 9A) lets the Owner pick specific Lead Forms on the
        # connected Page — an empty selection means "every form on this Page" (the
        # original, pre-OAuth behavior), so this only narrows intake, never widens it.
        selected_forms = {f for f in decrypted.get("selected_forms", "").split(",") if f}

        body = json.loads(raw_body)
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if not value.get("leadgen_id"):
                    continue
                if selected_forms and str(value.get("form_id")) not in selected_forms:
                    logger.info("Ignoring Meta lead %s — form_id %s is not in the selected forms.", value.get("leadgen_id"), value.get("form_id"))
                    continue
                try:
                    await self._process_raw_payload(CaptureSourceKey.META_LEAD_ADS, value)
                except CaptureValidationError as exc:
                    await self._record_failure(CaptureSourceKey.META_LEAD_ADS, exc.reason, value, exc.detail)
                except ConflictError as exc:
                    await self._record_failure(CaptureSourceKey.META_LEAD_ADS, FailureReason.DUPLICATE, value, str(exc))
                # `PydanticValidationError` added alongside the app's own `ValidationError`
                # — e.g. a malformed email in a Meta form field previously escaped both
                # this and the app-level catch, reaching the generic 500 handler with no
                # CaptureFailure recorded: Meta then retries, gets 500 again, and can
                # eventually disable the whole webhook subscription over one bad email.
                except (httpx.HTTPError, ValidationError, PydanticValidationError) as exc:
                    # A Graph API failure caused by Meta's Lead Ads Testing Tool sending a
                    # synthetic, permanently non-retrievable id (see
                    # meta_client.looks_like_test_tool_id) can never succeed no matter how
                    # many times it's retried — classified as INVALID_DATA (not retried,
                    # per FailureStatus's own "not retryable by nature" bucket) instead of
                    # API_ERROR (retried every 15 minutes forever), so it doesn't sit in
                    # the Capture Failures "Pending Retry" view looking like an ongoing
                    # production incident. A genuine transient Graph failure on a
                    # real-looking id is completely unaffected — still API_ERROR, still
                    # retried exactly as before.
                    reason = (
                        FailureReason.INVALID_DATA
                        if meta_client.looks_like_test_tool_id(str(value.get("leadgen_id") or ""))
                        else FailureReason.API_ERROR
                    )
                    await self._record_failure(CaptureSourceKey.META_LEAD_ADS, reason, value, str(exc))
        return True

    # ================================================================== retry queue (worker-driven)

    async def _attempt_retry(self, failure: CaptureFailure) -> None:
        try:
            lead = await self._process_raw_payload(failure.capture_source, failure.raw_payload)
            await self._failures.update(failure.require_id(), {"status": FailureStatus.RESOLVED, "resolved_lead_id": lead.require_id(), "next_retry_at": None})
            await write_audit_log(self._db, event_type=AuditEvent.CAPTURE_RETRIED, user_id=None, metadata={"failure_id": failure.require_id(), "outcome": "resolved"})
        except CaptureValidationError as exc:
            # Turned out to be permanently invalid, not transient — stop retrying.
            routing_reasons = {
                FailureReason.UNCONFIGURED_FORM, FailureReason.QUESTION_NOT_FOUND,
                FailureReason.ANSWER_NOT_FOUND, FailureReason.ANSWER_NOT_MAPPED,
                FailureReason.INVALID_CATEGORY, FailureReason.INVALID_PRODUCT,
                FailureReason.INACTIVE_PRODUCT, FailureReason.CATEGORY_PRODUCT_MISMATCH,
                FailureReason.INVALID_DESTINATION,
            }
            await self._failures.update(failure.require_id(), {
                "status": FailureStatus.NEEDS_ROUTING_CONFIGURATION if exc.reason in routing_reasons else FailureStatus.IGNORED,
                "failure_reason": exc.reason, "error_detail": exc.detail, "next_retry_at": None,
            })
        except ConflictError as exc:
            await self._failures.update(
                failure.require_id(),
                {"status": FailureStatus.IGNORED, "next_retry_at": None, "failure_reason": FailureReason.DUPLICATE, "error_detail": str(exc)},
            )
        except (httpx.HTTPError, ValidationError, PydanticValidationError) as exc:
            retry_count = failure.retry_count + 1
            if retry_count >= MAX_RETRY_ATTEMPTS:
                await self._failures.update(failure.require_id(), {"status": FailureStatus.EXHAUSTED, "retry_count": retry_count, "error_detail": str(exc)})
            else:
                next_retry_at = utc_now() + timedelta(minutes=RETRY_BACKOFF_MINUTES * (2**retry_count))
                await self._failures.update(failure.require_id(), {"retry_count": retry_count, "next_retry_at": next_retry_at, "error_detail": str(exc)})

    async def retry_due_failures(self) -> None:
        due = await self._failures.find_due_for_retry(now=utc_now())
        for failure in due:
            await self._attempt_retry(failure)

    # ================================================================== admin: sources + failures

    async def list_sources(self) -> list[CaptureSource]:
        return await self._sources.list_all()

    async def update_source(self, key: str, payload: UpdateCaptureSourceRequest, actor: User) -> CaptureSource:
        source = await self._get_source(key)
        updates = payload.model_dump(exclude_unset=True)
        await self._validate_source_mapping(source, updates)
        updated = await self._sources.update(source.require_id(), updates, updated_by=actor.require_id()) if updates else source
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.SOURCE_REMAPPED, user_id=actor.require_id(), metadata={"key": key})
        return updated

    async def _validate_source_mapping(self, source: CaptureSource, updates: dict[str, Any]) -> None:
        lead_source_id = updates.get("lead_source_id", source.lead_source_id)
        if not lead_source_id or not is_valid_object_id(lead_source_id):
            raise ValidationError("Select a valid Lead Source.")
        lead_source = await self._lead_sources.find_by_id(lead_source_id)
        if lead_source is None or lead_source.status != MasterDataStatus.ACTIVE:
            raise ValidationError("The selected Lead Source must exist and be active.")

        category = updates.get("default_product_category", source.default_product_category)
        product_id = updates.get("default_product_id", source.default_product_id)
        if category is None and product_id is None:
            return
        if not category or not product_id:
            raise ValidationError("Product Category and Product must be selected together.")
        if not is_valid_object_id(product_id):
            raise ValidationError("Select a valid Product.")

        if category == ProductCategory.LOAN:
            loan_product = await self._loan_products.find_by_id(product_id)
            if loan_product is None or loan_product.status != MasterDataStatus.ACTIVE:
                raise ValidationError("The selected Loan Product must exist and be active.")
            return

        if category == ProductCategory.INSURANCE:
            insurance_product = await self._insurance_products.find_by_id(product_id)
            if insurance_product is None or insurance_product.status != MasterDataStatus.ACTIVE:
                raise ValidationError("The selected Insurance Product must exist and be active.")
            if not insurance_product.category_id or not is_valid_object_id(insurance_product.category_id):
                raise ValidationError("The selected Insurance Product must belong to an active Insurance Category.")
            insurance_category = await self._insurance_categories.find_by_id(insurance_product.category_id)
            if insurance_category is None or insurance_category.status != MasterDataStatus.ACTIVE:
                raise ValidationError("The selected Insurance Product must belong to an active Insurance Category.")
            return

        raise ValidationError("Product Category must be loan or insurance.")

    # ================================================================== admin: Meta form routing

    async def list_meta_routings(self) -> list[MetaLeadRouting]:
        return await self._meta_routings.list_all()

    async def sync_meta_routings(self) -> list[MetaLeadRouting]:
        config = await self._active_config("meta")
        if config is None:
            raise ValidationError("No active Meta integration configuration exists.")
        decrypted = json.loads(decrypt(config["config_encrypted"])) if config.get("config_encrypted") else {}
        access_token, page_id = decrypted.get("access_token"), decrypted.get("page_id")
        if not access_token or not page_id:
            raise ValidationError("The active Meta integration has no connected Page.")
        forms = await oauth_client.fetch_lead_forms(page_access_token=access_token, page_id=page_id)
        for form in forms:
            form_id, form_name = str(form["id"]), str(form.get("name") or form["id"])
            existing = await self._meta_routings.find_by_form_id(form_id)
            if existing is None:
                await self._meta_routings.insert(MetaLeadRouting(
                    meta_form_id=form_id, form_name=form_name, status="unconfigured",
                ))
            elif existing.form_name != form_name:
                await self._meta_routings.update(existing.require_id(), {"form_name": form_name})
        return await self._meta_routings.list_all()

    async def _validate_meta_routing_payload(self, payload: MetaLeadRoutingUpsertRequest) -> None:
        if payload.category == ProductCategory.LOAN and payload.destination_module != MetaDestination.LEADS:
            raise ValidationError("Loan routes must use the Leads destination.")
        if payload.category == ProductCategory.INSURANCE and payload.destination_module != MetaDestination.INSURANCE_POLICY_LEADS:
            raise ValidationError("Insurance routes must use Insurance Policy Leads.")
        if payload.product_mode == MetaProductMode.DEFAULT:
            if not payload.default_product_id:
                raise ValidationError("Select a default product.")
            product_ids = [payload.default_product_id]
        else:
            if not (payload.product_question_key or payload.product_question_label):
                raise ValidationError("Select or enter the Meta product question.")
            if not payload.answer_mappings:
                raise ValidationError("Add at least one answer-to-product mapping.")
            normalized_answers = [self._normalize_match(answer) for answer in payload.answer_mappings]
            if any(not answer for answer in normalized_answers) or len(set(normalized_answers)) != len(normalized_answers):
                raise ValidationError("Answer mappings must be non-empty and unique after normalization.")
            product_ids = list(payload.answer_mappings.values())
        for product_id in set(product_ids):
            try:
                await self._validate_routing_product(payload.category, product_id)
            except CaptureValidationError as exc:
                raise ValidationError(exc.detail) from exc

    async def upsert_meta_routing(self, form_id: str, payload: MetaLeadRoutingUpsertRequest, actor: User) -> MetaLeadRouting:
        form_id = form_id.strip()
        if not form_id:
            raise ValidationError("Meta Form ID is required.")
        await self._validate_meta_routing_payload(payload)
        existing = await self._meta_routings.find_by_form_id(form_id)
        updates = payload.model_dump(exclude={"active"}, exclude_none=False)
        form_name = updates.pop("form_name", None) or form_id
        updates["answer_mappings"] = {key.strip(): value for key, value in payload.answer_mappings.items()}
        updates["status"] = MasterDataStatus.ACTIVE if payload.active else MasterDataStatus.INACTIVE
        if existing is None:
            routing_id = await self._meta_routings.insert(MetaLeadRouting(
                meta_form_id=form_id, form_name=form_name,
                created_by=actor.require_id(), **updates,
            ))
            updated = await self._meta_routings.find_by_id(routing_id)
        else:
            if payload.form_name is not None:
                updates["form_name"] = form_name
            updated = await self._meta_routings.update(existing.require_id(), updates, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(
            self._db, event_type=AuditEvent.META_ROUTING_CONFIGURED, user_id=actor.require_id(),
            metadata={"meta_form_id": form_id, "status": updated.status},
        )
        return updated

    async def create_meta_routing(self, form_id: str, payload: MetaLeadRoutingUpsertRequest, actor: User) -> MetaLeadRouting:
        if await self._meta_routings.find_by_form_id(form_id.strip()) is not None:
            raise ConflictError("A routing configuration already exists for this Meta Form ID.")
        return await self.upsert_meta_routing(form_id, payload, actor)

    async def set_meta_routing_status(self, form_id: str, active: bool, actor: User) -> MetaLeadRouting:
        routing = await self._meta_routings.find_by_form_id(form_id)
        if routing is None:
            raise NotFoundError("Meta form routing was not found.")
        if active:
            if not routing.category or not routing.product_mode or not routing.destination_module:
                raise ValidationError("Configure Category, Product Mode, and Destination before activation.")
            payload = MetaLeadRoutingUpsertRequest.model_validate({
                "form_name": routing.form_name, "category": routing.category,
                "product_mode": routing.product_mode, "default_product_id": routing.default_product_id,
                "destination_module": routing.destination_module, "destination_type": routing.destination_type,
                "product_question_key": routing.product_question_key,
                "product_question_label": routing.product_question_label,
                "answer_mappings": routing.answer_mappings, "active": True, "priority": routing.priority,
            })
            await self._validate_meta_routing_payload(payload)
        updated = await self._meta_routings.update(
            routing.require_id(), {"status": MasterDataStatus.ACTIVE if active else MasterDataStatus.INACTIVE},
            updated_by=actor.require_id(),
        )
        assert updated is not None
        return updated

    async def list_failures(
        self, *, capture_source: str | None, status: str | None, failure_reason: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CaptureFailure], int]:
        return await self._failures.search_and_filter(capture_source=capture_source, status=status, failure_reason=failure_reason, skip=skip, limit=limit, sort=sort)

    async def retry_failure_now(self, failure_id: str) -> CaptureFailure:
        failure = await self._failures.find_by_id(failure_id)
        if failure is None:
            raise NotFoundError("Capture failure not found.")
        await self._attempt_retry(failure)
        updated = await self._failures.find_by_id(failure_id)
        assert updated is not None
        return updated
