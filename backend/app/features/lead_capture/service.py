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
from dataclasses import replace
from datetime import timedelta
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError as PydanticValidationError

from app.constants.roles import OWNER
from app.core.exceptions import NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
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
)
from app.features.lead_capture.models import CaptureFailure, CaptureReceipt, CaptureSource
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
)
from app.features.lead_capture.schemas import (
    ManualCaptureRequest,
    UpdateCaptureSourceRequest,
    WebsiteCaptureRequest,
)
from app.features.leads.models import Lead, LeadActivity
from app.features.leads.repository import LeadActivityRepository, LeadRepository
from app.features.leads.schemas import CreateLeadRequest
from app.features.leads.service import LeadService
from app.security.encryption import decrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now
from app.utils.helpers import to_object_id

logger = logging.getLogger(__name__)


class LeadCaptureService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._sources = CaptureSourceRepository(db)
        self._failures = CaptureFailureRepository(db)
        self._receipts = CaptureReceiptRepository(db)
        self._users = UserRepository(db)
        self._leads = LeadRepository(db)
        self._activities = LeadActivityRepository(db)
        self._lead_service = LeadService(db)

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

    async def _process_raw_payload(self, capture_source: str, raw_payload: dict[str, Any]) -> Lead:
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
                found = await self._leads.find_by_id(existing.lead_id)
                if found is not None:
                    return found  # already processed — idempotent no-op, not a failure

        source = await self._get_source(capture_source)
        actor = await self._system_actor()
        lead = await self._lead_service.create_lead(
            CreateLeadRequest(
                full_name=parsed.full_name, mobile=parsed.mobile, email=parsed.email, source_id=source.lead_source_id,
                product_category=parsed.product_category, product_id=parsed.product_id, remarks=parsed.remarks,
            ),
            actor,
        )
        await self._leads.update(lead.require_id(), {"created_by": None})

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
        await self._activities.insert(activity)
        await write_audit_log(
            self._db, event_type=AuditEvent.LEAD_CAPTURED, user_id=actor.require_id(), metadata={"lead_id": lead.require_id(), "capture_source": capture_source}
        )

        if external_id:
            await self._receipts.insert(CaptureReceipt(capture_source=capture_source, external_id=external_id, lead_id=lead.require_id()))

        return lead

    async def _parse_meta_entry(self, entry: dict[str, Any]) -> tuple[ParsedLead, str]:
        leadgen_id = entry.get("leadgen_id")
        if not leadgen_id:
            raise CaptureValidationError(FailureReason.MISSING_REQUIRED_FIELDS, "Meta webhook entry is missing leadgen_id.")

        config = await self._active_config("meta")
        if config is None:
            raise ValidationError("No active Meta integration configuration exists — configure one in API Management (Module 9A) first.")
        decrypted = json.loads(decrypt(config["config_encrypted"])) if config.get("config_encrypted") else {}
        access_token = decrypted.get("access_token")
        if not access_token:
            raise ValidationError("The active Meta configuration has no access_token set.")

        graph_payload = await meta_client.fetch_lead_fields(leadgen_id, access_token=access_token)
        fields = meta_client.parse_field_data(graph_payload)
        source = await self._get_source(CaptureSourceKey.META_LEAD_ADS)
        parsed = parse_meta_fields(
            fields, default_product_category=source.default_product_category, default_product_id=source.default_product_id, raw_entry=entry
        )

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
        status = FailureStatus.PENDING if reason == FailureReason.API_ERROR else FailureStatus.IGNORED
        next_retry_at = utc_now() + timedelta(minutes=RETRY_BACKOFF_MINUTES) if status == FailureStatus.PENDING else None
        failure = CaptureFailure(capture_source=capture_source, failure_reason=reason, raw_payload=raw_payload, error_detail=detail, status=status, next_retry_at=next_retry_at)
        failure_id = await self._failures.insert(failure)
        await write_audit_log(self._db, event_type=AuditEvent.CAPTURE_FAILED, user_id=None, metadata={"failure_id": failure_id, "capture_source": capture_source, "reason": reason})
        found = await self._failures.find_by_id(failure_id)
        assert found is not None
        return found

    # ================================================================== website form (public)

    async def capture_from_website(self, payload: WebsiteCaptureRequest) -> Lead:
        raw = payload.model_dump(exclude_none=True)
        try:
            return await self._process_raw_payload(CaptureSourceKey.WEBSITE_FORM, raw)
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
        except CaptureValidationError:
            # Turned out to be permanently invalid, not transient — stop retrying.
            await self._failures.update(failure.require_id(), {"status": FailureStatus.IGNORED, "next_retry_at": None})
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
        updated = await self._sources.update(source.require_id(), updates, updated_by=actor.require_id()) if updates else source
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.SOURCE_REMAPPED, user_id=actor.require_id(), metadata={"key": key})
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
