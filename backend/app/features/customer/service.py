"""Module 6B — Customer Onboarding & Application Flow business logic.

Reuses, read-only unless noted: Module 6A's `LeadRepository`, Module 2's
`EmployeeRepository`, Module 4's `LoanProductRepository`/`InsuranceProductRepository`/
`DocumentTypeRepository`, and Auth's `UserRepository`/`AuthService` (the latter is
actively called, not just read — see docs/decisions/DECISIONS.md #046/#049 for exactly
how Auth's invitation-only signup model is reused for both onboarding flows without a
single line changed under app/features/auth/).
"""

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.config.security import get_security_policy
from app.config.settings import get_settings
from app.constants.roles import CUSTOMER, EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.constants import OtpPurpose
from app.features.auth.exceptions import AlreadyRegisteredError
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.auth.repository import UserRepository
from app.features.auth.service import AuthService
from app.features.communication.constants import Channel, TemplateCategory
from app.features.communication.service import CommunicationService
from app.features.customer.constants import (
    ApplicationStatus,
    AuditEvent,
    DocumentVerificationStatus,
    LeadTimelineEvent,
    LinkResolution,
    SchemaStatus,
    SecureLinkStatus,
)
from app.features.customer.field_validation import (
    is_field_visible,
    normalize_field_value,
    validate_form_data,
)
from app.features.customer.mappers import field_to_response, required_document_to_response
from app.features.customer.models import (
    Address,
    Application,
    ApplicationDocument,
    ApplicationFormDefinition,
    Customer,
    FieldCondition,
    FieldValidation,
    FormFieldDefinition,
    RepeatableGroupDefinition,
    RequiredDocumentDefinition,
    SecureLink,
)
from app.features.customer.repository import (
    ApplicationDocumentRepository,
    ApplicationFormDefinitionRepository,
    ApplicationRepository,
    CustomerRepository,
    SecureLinkRepository,
)
from app.features.customer.schemas import (
    CompleteDirectRegistrationRequest,
    CompleteProfileRequest,
    ConfirmDocumentRequest,
    DocumentGroupPreview,
    DocumentPreviewItem,
    FormDefinitionCreateRequest,
    FormDefinitionUpdateRequest,
    MessageItem,
    PortalDashboardResponse,
    RaiseSupportRequestRequest,
    RelationshipManagerResponse,
    SchemaAuditEntryResponse,
    SchemaCompareResponse,
    SchemaFieldDiffEntry,
    StartApplicationRequest,
    SubmitApplicationRequest,
    SupportRequestResponse,
    TimelineEntryResponse,
    UpdateApplicationRequest,
    UpdateProfileRequest,
)
from app.features.employee.models import Employee
from app.features.employee.repository import EmployeeRepository
from app.features.leads.constants import LeadActivityType
from app.features.leads.models import Lead, LeadActivity
from app.features.leads.repository import LeadActivityRepository, LeadRepository
from app.features.reminders.constants import NotificationType
from app.features.reminders.schemas import CreateTaskRequest
from app.features.reminders.service import RemindersService
from app.features.system_settings.repository import (
    DocumentTypeRepository,
    InsuranceProductRepository,
    LoanProductRepository,
)
from app.features.workflow_engine.repository import (
    ApplicationStatusHistoryRepository,
    ApplicationWorkflowRepository,
    WorkflowDefinitionRepository,
)
from app.security.encryption import encrypt
from app.services.storage.client import (
    generate_presigned_download_url,
    generate_presigned_upload_url,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ensure_utc, utc_now
from app.utils.helpers import to_object_id
from app.utils.id_generator import IdPrefix, generate_id

_UPLOAD_URL_EXPIRE_SECONDS = 300
_DOWNLOAD_URL_EXPIRE_SECONDS = 300
_NO_ASSIGNMENT_SENTINEL = "___none___"

# Short, opaque public code — see SecureLink's own docstring for why this replaced a JWT.
# Alphabet excludes 0/O/1/I/L (easily confused when read aloud or texted); crypto-random
# via `secrets`, matching the codebase's own established convention (app/security/otp.py).
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 10


def _generate_secure_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def _date_to_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


class CustomerService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self._db = db
        self._customers = CustomerRepository(db)
        self._applications = ApplicationRepository(db)
        self._documents = ApplicationDocumentRepository(db)
        self._form_defs = ApplicationFormDefinitionRepository(db)
        self._secure_links = SecureLinkRepository(db)
        self._leads = LeadRepository(db)
        self._lead_activities = LeadActivityRepository(db)
        self._users = UserRepository(db)
        self._employees = EmployeeRepository(db)
        self._loan_products = LoanProductRepository(db)
        self._insurance_products = InsuranceProductRepository(db)
        self._document_types = DocumentTypeRepository(db)
        self._auth = AuthService(db, redis)
        # Reuses Module 9C's real send path directly rather than through its own
        # audit-log-poller trigger (the pattern every other frozen module uses) — a
        # deliberate, narrow, explicitly-requested exception for this feature only
        # ("use existing communication services, no duplicate logic"). See
        # CommunicationService.send_now's own docstring.
        self._comm = CommunicationService(db)
        # Phase 5 (Customer Portal) — read-only reuse of the frozen Workflow Engine
        # (Module 6C) and Reminder Engine (Module 6D); no line changes under either
        # feature, same composition pattern this module has always used.
        self._workflows = ApplicationWorkflowRepository(db)
        self._status_history = ApplicationStatusHistoryRepository(db)
        self._workflow_defs = WorkflowDefinitionRepository(db)
        self._reminders = RemindersService(db)

    async def _log_lead_timeline(self, lead_id: str, event_type: str, metadata: dict[str, Any] | None = None) -> None:
        await self._lead_activities.insert(LeadActivity(lead_id=lead_id, event_type=event_type, metadata=metadata))

    # ================================================================== onboarding: Flow 1 (secure link)

    async def _generate_unique_code(self) -> str:
        for _ in range(5):
            code = _generate_secure_code()
            if not await self._secure_links.code_exists(code):
                return code
        raise ValidationError("Could not generate a unique secure link right now — please try again.")

    async def generate_secure_link(
        self, lead_id: str, actor: User, *, expiry_minutes: int | None = None, one_time_use: bool = True, notify_channels: list[str] | None = None,
    ) -> SecureLink:
        lead = await self._leads.find_by_id(lead_id)
        if lead is None:
            raise NotFoundError("Lead not found.")
        if await self._customers.find_by_lead_id(lead_id) is not None:
            raise ConflictError("This lead has already been converted to a customer.")

        # Generating a link while one is already active replaces it (this is what
        # "Regenerate" on the Lead Details card does — the same endpoint, not a
        # separate one) — the old link stops working immediately.
        prior_active = await self._secure_links.find_active_for_lead(lead_id)
        for old_link in prior_active:
            await self._secure_links.update(old_link.require_id(), {"status": SecureLinkStatus.REVOKED}, updated_by=actor.require_id())

        secure_code = await self._generate_unique_code()
        minutes = expiry_minutes if expiry_minutes is not None else get_security_policy().secure_link_expire_minutes
        expires_at = utc_now() + timedelta(minutes=minutes)

        link = SecureLink(lead_id=lead_id, secure_code=secure_code, expires_at=expires_at, one_time_use=one_time_use, created_by=actor.require_id())
        link_id = await self._secure_links.insert(link)

        event_type = LeadTimelineEvent.SECURE_LINK_REGENERATED if prior_active else LeadTimelineEvent.SECURE_LINK_GENERATED
        await self._log_lead_timeline(lead_id, event_type, {"link_id": link_id})
        await write_audit_log(self._db, event_type=AuditEvent.SECURE_LINK_GENERATED, user_id=actor.require_id(), metadata={"lead_id": lead_id})

        created = await self._secure_links.find_by_id(link_id)
        assert created is not None

        if notify_channels:
            created = await self.notify_secure_link(created.require_id(), notify_channels, actor, lead=lead)

        return created

    async def get_current_secure_link(self, lead_id: str) -> SecureLink | None:
        """The Lead Details card's own read — whichever link was generated most
        recently for this lead, regardless of its current status, so the card can show
        "Disabled"/"Used" instead of silently reverting to "Not Generated"."""
        if await self._leads.find_by_id(lead_id) is None:
            raise NotFoundError("Lead not found.")
        return await self._secure_links.find_latest_for_lead(lead_id)

    async def disable_secure_link(self, link_id: str, actor: User) -> SecureLink:
        link = await self._secure_links.find_by_id(link_id)
        if link is None:
            raise NotFoundError("Link not found.")
        updated = await self._secure_links.update(link_id, {"status": SecureLinkStatus.REVOKED}, updated_by=actor.require_id())
        await self._log_lead_timeline(link.lead_id, LeadTimelineEvent.SECURE_LINK_DISABLED, {"link_id": link_id})
        await write_audit_log(self._db, event_type=AuditEvent.SECURE_LINK_REVOKED, user_id=actor.require_id(), metadata={"link_id": link_id})
        return updated or link

    async def log_secure_link_ui_event(self, link_id: str, event_type: str, actor: User) -> None:
        """Records a pure client-side interaction (Copy / staff-side Open) on the Lead's
        timeline — these never hit the resolve/claim path, so nothing else observes them
        server-side unless the frontend explicitly reports it here."""
        link = await self._secure_links.find_by_id(link_id)
        if link is None:
            raise NotFoundError("Link not found.")
        await self._log_lead_timeline(link.lead_id, event_type, {"link_id": link_id, "by": actor.require_id()})

    def build_secure_link_url(self, secure_code: str) -> str:
        base = get_settings().frontend_base_url.rstrip("/")
        return f"{base}/apply/{secure_code}"

    async def resolve_secure_link_creator_contact(self, user_id: str | None) -> dict[str, str | None] | None:
        """Staff contact info for `SecureLink.created_by` — an Employee's own record if
        the actor was an Employee, else the Owner's own mobile (Owners have no Employee
        record), else None (e.g. the actor's account was later removed). Backs both
        `resolve_secure_link_creator_name` (Lead Details display) and the public
        Expired-link "Contact your Relationship Manager" card."""
        if user_id is None:
            return None
        employee = await self._employees.find_by_user_id(user_id)
        if employee is not None:
            return {"name": employee.display_name, "mobile": employee.mobile, "email": employee.email}
        user = await self._users.find_by_id(user_id)
        if user is not None and user.role == OWNER:
            return {"name": "Owner", "mobile": user.mobile, "email": None}
        return None

    async def resolve_secure_link_creator_name(self, user_id: str | None) -> str | None:
        contact = await self.resolve_secure_link_creator_contact(user_id)
        return contact["name"] if contact else None

    async def notify_secure_link(self, link_id: str, channels: list[str], actor: User, *, lead: Lead | None = None) -> SecureLink:
        link = await self._secure_links.find_by_id(link_id)
        if link is None:
            raise NotFoundError("Link not found.")
        if lead is None:
            lead = await self._leads.find_by_id(link.lead_id)
            if lead is None:
                raise NotFoundError("The lead behind this link no longer exists.")

        variables = {"customer_name": lead.full_name, "secure_link": self.build_secure_link_url(link.secure_code)}
        status_map: dict[str, str] = dict(link.notification_status or {})
        for channel in channels:
            recipient = lead.mobile if channel in (Channel.WHATSAPP, Channel.SMS) else lead.email
            if not recipient:
                status_map[channel] = "no_recipient"
                continue
            sent = await self._comm.send_now(channel=channel, recipient=recipient, category=TemplateCategory.SECURE_LINK, variables=variables, actor=actor)
            status_map[channel] = "sent" if sent else "failed"

        updated = await self._secure_links.update(link_id, {"notification_status": status_map}, updated_by=actor.require_id())
        await self._log_lead_timeline(link.lead_id, LeadTimelineEvent.SECURE_LINK_SHARED, {"link_id": link_id, "channels": channels})
        return updated or link

    async def _load_secure_link_by_code(self, secure_code: str) -> tuple[Lead | None, SecureLink | None, str, Application | None]:
        """Never raises — every outcome (not found / expired / disabled / already used /
        already submitted / valid) is a normal, expected result the public resolve
        endpoint reports back as data (`LinkResolution`), not an HTTP error, so the
        frontend can route straight to the right dedicated page without parsing error
        codes. See docs/decisions/DECISIONS.md for why this shape was chosen."""
        link = await self._secure_links.find_by_code(secure_code)
        if link is None:
            return None, None, LinkResolution.NOT_FOUND, None
        if link.status == SecureLinkStatus.REVOKED:
            return None, link, LinkResolution.DISABLED, None
        if utc_now() >= ensure_utc(link.expires_at):
            return None, link, LinkResolution.EXPIRED, None

        lead = await self._leads.find_by_id(link.lead_id)
        if lead is None:
            return None, link, LinkResolution.NOT_FOUND, None

        submitted = await self._applications.find_many({"lead_id": link.lead_id, "status": ApplicationStatus.SUBMITTED}, limit=1)
        if submitted:
            return lead, link, LinkResolution.ALREADY_SUBMITTED, submitted[0]

        if link.one_time_use and link.status == SecureLinkStatus.USED:
            # `claim_secure_link` marks the link USED the moment a draft application
            # starts — long before submission. Re-resolving the same link later (a
            # reload, or the return trip from /login) must not dead-end a customer who
            # is simply continuing their own in-progress draft: only a link with no
            # application on this lead at all is genuinely "used up with nothing to
            # resume." `claim_secure_link` itself is idempotent (reuses the existing
            # draft), so routing back through VALID here is safe.
            has_draft = await self._applications.find_many({"lead_id": link.lead_id}, limit=1)
            if not has_draft:
                return None, link, LinkResolution.ALREADY_USED, None

        return lead, link, LinkResolution.VALID, None

    async def get_secure_link_public_status(self, secure_code: str) -> dict[str, Any]:
        lead, link, resolution, submitted_application = await self._load_secure_link_by_code(secure_code)

        if link is not None:
            was_first_open = link.last_opened_at is None
            await self._secure_links.update(link.require_id(), {"last_opened_at": utc_now()})
            if was_first_open:
                await self._log_lead_timeline(link.lead_id, LeadTimelineEvent.CUSTOMER_OPENED_LINK, {"link_id": link.require_id()})

        if resolution == LinkResolution.ALREADY_SUBMITTED and submitted_application is not None:
            return {
                "link_status": resolution,
                "application_reference": submitted_application.application_code,
                "submitted_at": submitted_application.submitted_at,
                "application_status": submitted_application.status,
            }
        if resolution == LinkResolution.EXPIRED and link is not None:
            rm = await self.resolve_secure_link_creator_contact(link.created_by)
            return {
                "link_status": resolution,
                "relationship_manager_name": rm["name"] if rm else None,
                "relationship_manager_mobile": rm["mobile"] if rm else None,
                "relationship_manager_email": rm["email"] if rm else None,
            }
        if resolution != LinkResolution.VALID or lead is None:
            return {"link_status": resolution}

        assert link is not None
        existing_user = await self._users.find_by_mobile(lead.mobile)
        has_active_account = existing_user is not None and existing_user.status == ACCOUNT_STATUS_ACTIVE
        return {
            "link_status": resolution,
            "full_name": lead.full_name,
            "mobile": lead.mobile,
            "email": lead.email,
            "product_category": lead.product_category,
            "product_id": lead.product_id,
            "product_name": await self.resolve_product_name(lead.product_category, lead.product_id),
            "has_active_account": has_active_account,
            "lead_reference": lead.lead_code,
            "created_by_name": await self.resolve_secure_link_creator_name(link.created_by),
            "link_created_at": link.created_at,
        }

    async def _resolve_valid_link(self, secure_code: str) -> tuple[Lead, SecureLink]:
        lead, link, resolution, _ = await self._load_secure_link_by_code(secure_code)
        if resolution == LinkResolution.NOT_FOUND:
            raise NotFoundError("This link is invalid.")
        if resolution == LinkResolution.EXPIRED:
            raise ValidationError("This link has expired.")
        if resolution == LinkResolution.DISABLED:
            raise ForbiddenError("This link has been disabled.")
        if resolution == LinkResolution.ALREADY_USED:
            raise ConflictError("This link has already been used.")
        if resolution == LinkResolution.ALREADY_SUBMITTED:
            raise ConflictError("This application has already been submitted.")
        assert lead is not None and link is not None
        return lead, link

    async def claim_secure_link(self, secure_code: str, actor: User) -> Application:
        lead, link = await self._resolve_valid_link(secure_code)
        if actor.mobile != lead.mobile:
            raise ForbiddenError("This application does not belong to your account.")

        lead_id = lead.require_id()
        # Under the production registration flow (CustomerService.complete_direct_registration)
        # the Customer profile already exists by the time a link is claimed — unlike the
        # older lazy-conversion path, which left this to `complete_profile` later.
        customer = await self._customers.find_by_user_id(actor.require_id())
        if not lead.account_created:
            lead_update: dict[str, Any] = {"user_id": actor.require_id(), "account_created": True, "account_created_at": utc_now()}
            if customer is not None:
                lead_update["customer_id"] = customer.require_id()
            await self._leads.update(lead_id, lead_update)

        existing = await self._applications.find_many({"lead_id": lead_id, "user_id": actor.require_id()}, limit=1)
        if existing:
            application = existing[0]
        else:
            form_def = await self._get_or_error_form_definition(lead.product_category, lead.product_id)
            application = await self._create_application(
                user_id=actor.require_id(), customer_id=customer.require_id() if customer else None, lead_id=lead_id,
                product_category=lead.product_category, product_id=lead.product_id, form_definition=form_def, actor=actor,
            )
            await self._log_lead_timeline(lead_id, LeadTimelineEvent.CUSTOMER_STARTED_APPLICATION, {"application_id": application.require_id()})

        if link.status != SecureLinkStatus.USED:
            await self._secure_links.update(
                link.require_id(), {"status": SecureLinkStatus.USED, "used_by_user_id": actor.require_id(), "used_at": utc_now()}
            )
            await write_audit_log(self._db, event_type=AuditEvent.SECURE_LINK_CLAIMED, user_id=actor.require_id(), metadata={"lead_id": lead_id})
        return application

    # ================================================================== onboarding: Flow 2 (direct portal)

    async def start_direct_registration(self, mobile: str) -> str | None:
        existing = await self._users.find_by_mobile(mobile)
        if existing is not None and existing.status == ACCOUNT_STATUS_ACTIVE:
            raise AlreadyRegisteredError("This mobile number is already registered. Please log in.")

        technical_inviter = await self._any_owner()
        dev_otp = await self._auth.send_otp(mobile=mobile, role=CUSTOMER, inviter=technical_inviter)

        # Auth's send_otp (frozen, unmodified) requires a real Owner/Employee `inviter`
        # and stamps the new pending User row's `created_by` with that inviter's id — a
        # side effect that would otherwise make a self-registered Customer look
        # attributed to/owned by that Owner. Corrected immediately: a direct-portal
        # registration is not associated with any Owner or Employee (decision 053) —
        # `created_by=None` matches BaseDocument's own documented convention for
        # "system-created, no human attribution" rather than pointing at a real Owner.
        pending_user = await self._users.find_by_mobile(mobile)
        if pending_user is not None:
            await self._users.update(pending_user.require_id(), {"created_by": None})

        return dev_otp

    async def complete_direct_registration(self, payload: CompleteDirectRegistrationRequest) -> None:
        """Production Customer self-registration — the only self-registration path in
        the system (Owner/Employee/Referral Partner accounts are always staff-created,
        see decision 011/053). Collects the full profile up front rather than deferring
        it to `complete_profile` post-login: the customer only ever completes one form.
        Reuses `AuthService.consume_otp_verified_ticket`/`activate_user_with_password`
        (the same primitives `reset_password` uses) — no duplicate password/OTP logic.
        Does not issue a session: per the production login flow, a freshly-registered
        customer always logs in explicitly afterward, exactly like everyone else."""
        mobile = await self._auth.consume_otp_verified_ticket(payload.otp_verified_token, expected_purposes=(OtpPurpose.SIGNUP,))
        if mobile != payload.mobile:
            raise ForbiddenError("This verification code does not match this mobile number.")

        user = await self._auth.activate_user_with_password(mobile=mobile, new_password=payload.password)
        profile = CompleteProfileRequest(
            full_name=payload.full_name,
            email=payload.email,
            address=AddressSchema(line1=payload.address_line1, city=payload.city, state=payload.state, pincode=payload.pincode),
        )
        await self._create_customer_from_profile(profile, user, converted_from_lead_id=None)

    async def _any_owner(self) -> User:
        # Auth's send_otp requires a real Owner/Employee User object to satisfy its
        # (frozen, unmodified) signature and role-authorization check — there is no
        # public signup entry point for any role otherwise (decision 011). Direct portal
        # registration has no actual human inviting this mobile, so any seeded Owner is
        # used purely as the technical value that satisfies that requirement; its id is
        # never allowed to persist as the resulting Customer's attribution — see
        # start_direct_registration's cleanup step and decision 053.
        owners = await self._users.find_many({"role": OWNER}, limit=1)
        if not owners:
            raise ValidationError("No Owner account exists yet to authorize registration.")
        return owners[0]

    # ================================================================== customer profile

    async def get_own_customer(self, actor: User) -> Customer | None:
        return await self._customers.find_by_user_id(actor.require_id())

    async def complete_profile(self, payload: CompleteProfileRequest, actor: User) -> Customer:
        """Unified onboarding — the one profile-completion step every customer goes
        through right after authentication, Flow 1 (secure link) and Flow 2 (direct
        portal) alike. If the caller already has a Flow-1 application they've started
        but not yet converted, this both creates their `Customer` with the correct
        `converted_from_lead_id` and links that application to it immediately — Flow 1
        no longer waits until submission to convert (see docs/decisions/DECISIONS.md
        #047's supersession note). A Flow-2 caller with no pending application behaves
        exactly as before."""
        if await self._customers.find_by_user_id(actor.require_id()) is not None:
            raise ConflictError("Your profile already exists.")
        pending = await self._applications.find_pending_conversion_for_user(actor.require_id())
        customer = await self._create_customer_from_profile(
            payload, actor, converted_from_lead_id=pending.lead_id if pending else None
        )
        if pending:
            await self._applications.update(pending.require_id(), {"customer_id": customer.require_id()}, updated_by=actor.require_id())
            # `account_created`/`user_id` were already set at claim time (see
            # `claim_secure_link`) — `customer_id` becomes known only now.
            await self._leads.update(pending.lead_id, {"customer_id": customer.require_id()})
        return customer

    async def update_own_profile(self, payload: UpdateProfileRequest, actor: User) -> Customer:
        customer = await self.get_own_customer(actor)
        if customer is None:
            raise NotFoundError("Complete your profile first.")
        updates: dict[str, Any] = {}
        for field in ("full_name", "email", "gender"):
            value = getattr(payload, field)
            if value is not None:
                updates[field] = value
        if payload.date_of_birth is not None:
            updates["date_of_birth"] = _date_to_datetime(payload.date_of_birth)
        if payload.pan_number is not None:
            updates["pan_number_encrypted"] = encrypt(payload.pan_number)
        if payload.aadhaar_number is not None:
            updates["aadhaar_number_encrypted"] = encrypt(payload.aadhaar_number)
        if payload.address is not None:
            updates["address"] = Address(**payload.address.model_dump()).model_dump()
        if not updates:
            return customer
        updated = await self._customers.update(customer.require_id(), updates, updated_by=actor.require_id())
        return updated or customer

    async def _create_customer_from_profile(self, payload: CompleteProfileRequest, actor: User, *, converted_from_lead_id: str | None) -> Customer:
        existing = await self._customers.find_by_user_id(actor.require_id())
        if existing is not None:
            return existing
        customer_code = await generate_id(self._db, IdPrefix.CUSTOMER)
        customer = Customer(
            customer_code=customer_code,
            user_id=actor.require_id(),
            full_name=payload.full_name,
            mobile=actor.mobile,
            email=payload.email,
            date_of_birth=_date_to_datetime(payload.date_of_birth),
            gender=payload.gender,
            pan_number_encrypted=encrypt(payload.pan_number) if payload.pan_number else None,
            aadhaar_number_encrypted=encrypt(payload.aadhaar_number) if payload.aadhaar_number else None,
            address=Address(**payload.address.model_dump()) if payload.address else None,
            converted_from_lead_id=converted_from_lead_id,
            created_by=actor.require_id(),
        )
        customer_id = await self._customers.insert(customer)
        event = AuditEvent.LEAD_CONVERTED if converted_from_lead_id else AuditEvent.CUSTOMER_REGISTERED
        await write_audit_log(self._db, event_type=event, user_id=actor.require_id(), metadata={"customer_id": customer_id})
        return await self._customers.find_by_id(customer_id) or customer

    # ================================================================== applications (customer side)

    async def start_application(self, payload: StartApplicationRequest, actor: User) -> Application:
        customer = await self.get_own_customer(actor)
        if customer is None:
            raise ValidationError("Complete your profile before starting an application.")
        form_def = await self._get_or_error_form_definition(payload.product_category, payload.product_id)
        return await self._create_application(
            user_id=actor.require_id(), customer_id=customer.require_id(), lead_id=None,
            product_category=payload.product_category, product_id=payload.product_id, form_definition=form_def, actor=actor,
        )

    async def _create_application(
        self, *, user_id: str, customer_id: str | None, lead_id: str | None, product_category: str, product_id: str,
        form_definition: ApplicationFormDefinition, actor: User,
    ) -> Application:
        code = await generate_id(self._db, IdPrefix.APPLICATION)
        application = Application(
            application_code=code, user_id=user_id, customer_id=customer_id, lead_id=lead_id,
            product_category=product_category, product_id=product_id, form_definition_id=form_definition.require_id(),
            created_by=actor.require_id(),
        )
        application_id = await self._applications.insert(application)
        await write_audit_log(
            self._db, event_type=AuditEvent.APPLICATION_STARTED, user_id=actor.require_id(), metadata={"application_id": application_id}
        )
        return await self._applications.find_by_id(application_id) or application

    async def _get_or_error_form_definition(self, product_category: str, product_id: str) -> ApplicationFormDefinition:
        form_def = await self._form_defs.find_by_product(product_category, product_id)
        if form_def is None:
            raise ValidationError("No application form is configured for this product yet.")
        return form_def

    async def get_form_definition(self, product_category: str, product_id: str) -> ApplicationFormDefinition:
        """Read-only entry point the router uses to preview a product's form before
        starting an application/lead — shared by every portal (Customer Application,
        Employee Create Lead, Referral Partner Add Lead), see Product Schema Engine."""
        return await self._get_or_error_form_definition(product_category, product_id)

    # ================================================================== product schema authoring (Owner)

    async def _validate_product_reference(self, product_category: str, product_id: str) -> None:
        repo = self._loan_products if product_category == "loan" else self._insurance_products
        if await repo.find_by_id(product_id) is None:
            raise ValidationError(f"Unknown product_id for category '{product_category}'.")

    async def resolve_product_name(self, product_category: str, product_id: str) -> str:
        repo = self._loan_products if product_category == "loan" else self._insurance_products
        product = await repo.find_by_id(product_id)
        return product.name if product else ""

    def _document_type_name_map_sync(self, type_ids: set[str], types: list[Any]) -> dict[str, str]:
        return {t.require_id(): t.name for t in types if t.require_id() in type_ids}

    async def resolve_document_type_name_map(self, type_ids: set[str]) -> dict[str, str]:
        if not type_ids:
            return {}
        types = await self._document_types.find_many({}, limit=500)
        return self._document_type_name_map_sync(type_ids, types)

    async def list_form_definitions(self) -> list[ApplicationFormDefinition]:
        return await self._form_defs.find_many({}, limit=500, sort=[("product_category", 1)])

    async def get_form_definition_by_id(self, form_definition_id: str) -> ApplicationFormDefinition:
        form_def = await self._form_defs.find_by_id(form_definition_id)
        if form_def is None:
            raise NotFoundError("Product schema not found.")
        return form_def

    def _fields_from_payload(self, fields: list[Any]) -> list[FormFieldDefinition]:
        """Used only by `create_form_definition`, where there's no existing schema to
        diff against — every field is necessarily brand new, `source="custom"`.
        `update_form_definition` uses `_merge_fields` instead."""
        return [
            FormFieldDefinition(
                key=f.key,
                label=f.label,
                field_type=f.field_type,
                required=f.required,
                options=f.options,
                section=f.section,
                visible_when=FieldCondition(**f.visible_when.model_dump()) if f.visible_when else None,
                validation=FieldValidation(**f.validation.model_dump()) if f.validation else None,
                options_source=f.options_source,
                options_endpoint=f.options_endpoint,
                placeholder=f.placeholder,
                hidden=f.hidden,
            )
            for f in fields
        ]

    def _required_documents_from_payload(self, required_documents: list[Any]) -> list[RequiredDocumentDefinition]:
        """See `_fields_from_payload` docstring — create-only, no master/custom diff."""
        return [
            RequiredDocumentDefinition(
                document_type_id=d.document_type_id, section=d.section, note=d.note, name_override=d.name_override,
                required=d.required, allowed_types=d.allowed_types, max_size_mb=d.max_size_mb,
                multiple_upload=d.multiple_upload, preview_enabled=d.preview_enabled, hidden=d.hidden,
            )
            for d in required_documents
        ]

    def _merge_fields(self, incoming: list[Any], existing: list[FormFieldDefinition]) -> list[FormFieldDefinition]:
        """The Owner permission model (governance round): a field whose *current*
        `source == "master"` may have every attribute changed except `key`/`field_type`
        (enforced below) and may never be omitted from the payload (enforced after the
        loop) — hiding it via `hidden=True` is the only way to remove it from the live
        form. A field not currently tracked as master-sourced (brand new key, or an
        existing Owner-added custom field) is fully free, `source="custom"`."""
        existing_by_key = {f.key: f for f in existing}
        seen_keys: set[str] = set()
        merged: list[FormFieldDefinition] = []
        for f in incoming:
            seen_keys.add(f.key)
            current = existing_by_key.get(f.key)
            is_master = current is not None and current.source == "master"
            if is_master and current is not None and f.field_type != current.field_type:
                raise ValidationError(f'"{current.label}" is a master field — its type cannot be changed.')
            merged.append(
                FormFieldDefinition(
                    key=f.key,
                    label=f.label,
                    field_type=current.field_type if is_master and current is not None else f.field_type,
                    required=f.required,
                    options=f.options,
                    section=f.section,
                    visible_when=FieldCondition(**f.visible_when.model_dump()) if f.visible_when else None,
                    validation=FieldValidation(**f.validation.model_dump()) if f.validation else None,
                    options_source=f.options_source,
                    options_endpoint=f.options_endpoint,
                    source="master" if is_master else "custom",
                    master_key=current.master_key if is_master and current is not None else None,
                    placeholder=f.placeholder,
                    hidden=f.hidden,
                )
            )
        missing_master = [f for f in existing if f.source == "master" and f.key not in seen_keys]
        if missing_master:
            names = ", ".join(f'"{f.label}"' for f in missing_master)
            raise ValidationError(f"{names} — master field(s) cannot be removed. Hide them instead.")
        return merged

    def _merge_documents(self, incoming: list[Any], existing: list[RequiredDocumentDefinition]) -> list[RequiredDocumentDefinition]:
        """Same master/custom split as `_merge_fields`, matched by `document_type_id`
        instead of `key`."""
        existing_master_ids = {d.document_type_id for d in existing if d.source == "master"}
        seen_ids: set[str] = set()
        merged: list[RequiredDocumentDefinition] = []
        for d in incoming:
            seen_ids.add(d.document_type_id)
            is_master = d.document_type_id in existing_master_ids
            merged.append(
                RequiredDocumentDefinition(
                    document_type_id=d.document_type_id,
                    section=d.section,
                    note=d.note,
                    name_override=d.name_override,
                    required=d.required,
                    allowed_types=d.allowed_types,
                    max_size_mb=d.max_size_mb,
                    multiple_upload=d.multiple_upload,
                    preview_enabled=d.preview_enabled,
                    source="master" if is_master else "custom",
                    hidden=d.hidden,
                )
            )
        missing_master = existing_master_ids - seen_ids
        if missing_master:
            raise ValidationError("Master-required document(s) cannot be removed. Hide them instead.")
        return merged

    def _repeatable_groups_from_payload(self, groups: list[Any]) -> list[RepeatableGroupDefinition]:
        return [
            RepeatableGroupDefinition(
                key=g.key, label=g.label, add_button_label=g.add_button_label, min_count=g.min_count, max_count=g.max_count,
                fields=self._fields_from_payload(g.fields),
            )
            for g in groups
        ]

    def _validate_schema_status(self, status: str) -> None:
        if status not in SchemaStatus.ALL:
            raise ValidationError(f"Unknown status '{status}' — must be one of {', '.join(SchemaStatus.ALL)}.")

    async def create_form_definition(self, payload: FormDefinitionCreateRequest, actor: User) -> ApplicationFormDefinition:
        await self._validate_product_reference(payload.product_category, payload.product_id)
        self._validate_schema_status(payload.status)
        if await self._form_defs.find_any_by_product(payload.product_category, payload.product_id) is not None:
            raise ConflictError("A product schema already exists for this product — edit it instead of creating another.")
        form_def = ApplicationFormDefinition(
            product_category=payload.product_category,
            product_id=payload.product_id,
            fields=self._fields_from_payload(payload.fields),
            required_documents=self._required_documents_from_payload(payload.required_documents),
            repeatable_groups=self._repeatable_groups_from_payload(payload.repeatable_groups),
            status=payload.status,
            created_by=actor.require_id(),
        )
        form_def_id = await self._form_defs.insert(form_def)
        return await self._form_defs.find_by_id(form_def_id) or form_def

    def _diff_fields(self, old: list[FormFieldDefinition], new: list[FormFieldDefinition]) -> list[SchemaFieldDiffEntry]:
        old_by_key = {f.key: f for f in old}
        new_by_key = {f.key: f for f in new}
        diffs: list[SchemaFieldDiffEntry] = []
        for key, nf in new_by_key.items():
            of = old_by_key.get(key)
            if of is None:
                diffs.append(SchemaFieldDiffEntry(key=key, attribute="added", new_value=nf.label))
            elif of.model_dump() != nf.model_dump():
                diffs.append(SchemaFieldDiffEntry(key=key, attribute="field", old_value=of.model_dump(), new_value=nf.model_dump()))
        for key, of in old_by_key.items():
            if key not in new_by_key:
                diffs.append(SchemaFieldDiffEntry(key=key, attribute="removed", old_value=of.label))
        return diffs

    def _diff_documents(self, old: list[RequiredDocumentDefinition], new: list[RequiredDocumentDefinition]) -> list[SchemaFieldDiffEntry]:
        old_by_id = {d.document_type_id: d for d in old}
        new_by_id = {d.document_type_id: d for d in new}
        diffs: list[SchemaFieldDiffEntry] = []
        for doc_id, nd in new_by_id.items():
            od = old_by_id.get(doc_id)
            if od is None:
                diffs.append(SchemaFieldDiffEntry(key=doc_id, attribute="added", new_value=nd.name_override or doc_id))
            elif od.model_dump() != nd.model_dump():
                diffs.append(SchemaFieldDiffEntry(key=doc_id, attribute="document", old_value=od.model_dump(), new_value=nd.model_dump()))
        for doc_id, od in old_by_id.items():
            if doc_id not in new_by_id:
                diffs.append(SchemaFieldDiffEntry(key=doc_id, attribute="removed", old_value=od.name_override or doc_id))
        return diffs

    async def update_form_definition(self, form_definition_id: str, payload: FormDefinitionUpdateRequest, actor: User) -> ApplicationFormDefinition:
        form_def = await self.get_form_definition_by_id(form_definition_id)
        wants_content_change = payload.fields is not None or payload.required_documents is not None or payload.repeatable_groups is not None
        if form_def.is_locked and wants_content_change:
            raise ConflictError("This schema is frozen — create a new version to make changes.")

        updates: dict[str, Any] = {}
        field_diff: list[SchemaFieldDiffEntry] = []
        document_diff: list[SchemaFieldDiffEntry] = []
        if payload.fields is not None:
            merged_fields = self._merge_fields(payload.fields, form_def.fields)
            field_diff = self._diff_fields(form_def.fields, merged_fields)
            updates["fields"] = [f.model_dump() for f in merged_fields]
        if payload.required_documents is not None:
            merged_documents = self._merge_documents(payload.required_documents, form_def.required_documents)
            document_diff = self._diff_documents(form_def.required_documents, merged_documents)
            updates["required_documents"] = [d.model_dump() for d in merged_documents]
        if payload.repeatable_groups is not None:
            updates["repeatable_groups"] = [g.model_dump() for g in self._repeatable_groups_from_payload(payload.repeatable_groups)]
        if payload.status is not None:
            self._validate_schema_status(payload.status)
            updates["status"] = payload.status
        if not updates:
            return form_def
        updated = await self._form_defs.update(form_definition_id, updates, updated_by=actor.require_id())
        if field_diff or document_diff:
            await write_audit_log(
                self._db,
                event_type=AuditEvent.SCHEMA_FIELD_UPDATED,
                user_id=actor.require_id(),
                metadata={
                    "product_category": form_def.product_category,
                    "product_id": form_def.product_id,
                    "form_definition_id": form_definition_id,
                    "field_changes": [d.model_dump() for d in field_diff],
                    "document_changes": [d.model_dump() for d in document_diff],
                },
            )
        return updated or form_def

    async def freeze_form_definition(self, form_definition_id: str, confirmed_checklist: list[str], actor: User) -> ApplicationFormDefinition:
        """Ask #6 — locks the schema against further field/document edits. The only way
        to change a frozen schema afterwards is `create_new_version`."""
        form_def = await self.get_form_definition_by_id(form_definition_id)
        if form_def.is_locked:
            raise ConflictError("This schema version is already frozen.")
        updated = await self._form_defs.update(
            form_definition_id, {"is_locked": True, "frozen_at": utc_now(), "frozen_by": actor.require_id()}, updated_by=actor.require_id()
        )
        await write_audit_log(
            self._db,
            event_type=AuditEvent.SCHEMA_FROZEN,
            user_id=actor.require_id(),
            metadata={
                "product_category": form_def.product_category,
                "product_id": form_def.product_id,
                "form_definition_id": form_definition_id,
                "schema_version": form_def.schema_version,
                "confirmed_checklist": confirmed_checklist,
            },
        )
        return updated or form_def

    async def create_new_version(self, form_definition_id: str, actor: User) -> ApplicationFormDefinition:
        """Ask #6 — only valid on a frozen schema. Clones fields/documents/groups
        (`source`/`master_key`/`hidden` preserved) into a brand new DRAFT, bypassing
        `create_form_definition`'s one-schema-per-product uniqueness guard (the one
        deliberate exception to it). Uses `schema_version`, not `BaseDocument.version`
        (see that field's docstring) — freeze/ordinary edits never inflate it."""
        form_def = await self.get_form_definition_by_id(form_definition_id)
        if not form_def.is_locked:
            raise ConflictError("Only a frozen schema can be used to start a new version.")
        new_def = ApplicationFormDefinition(
            product_category=form_def.product_category,
            product_id=form_def.product_id,
            fields=[f.model_copy() for f in form_def.fields],
            required_documents=[d.model_copy() for d in form_def.required_documents],
            repeatable_groups=[g.model_copy(deep=True) for g in form_def.repeatable_groups],
            status=SchemaStatus.DRAFT,
            is_locked=False,
            schema_version=form_def.schema_version + 1,
            source_schema_version=form_def.schema_version,
            created_by=actor.require_id(),
        )
        new_id = await self._form_defs.insert(new_def)
        await write_audit_log(
            self._db,
            event_type=AuditEvent.SCHEMA_DRAFT_CREATED,
            user_id=actor.require_id(),
            metadata={
                "product_category": form_def.product_category,
                "product_id": form_def.product_id,
                "form_definition_id": new_id,
                "source_schema_version": form_def.schema_version,
            },
        )
        return await self._form_defs.find_by_id(new_id) or new_def

    async def publish_form_definition(self, form_definition_id: str, actor: User) -> ApplicationFormDefinition:
        """Ask #6 — only valid on a DRAFT. Archives the product's current ACTIVE
        definition (if any — its own `is_locked` value is untouched, so a previously
        frozen version stays frozen as a permanent historical record for Compare) and
        activates this draft. Not auto-locked — Freeze stays an explicit, separate
        action the Owner takes after review."""
        draft = await self.get_form_definition_by_id(form_definition_id)
        if draft.status != SchemaStatus.DRAFT:
            raise ConflictError("Only a draft schema can be published.")
        current_active = await self._form_defs.find_by_product(draft.product_category, draft.product_id)
        archived_schema_version: int | None = None
        if current_active is not None and current_active.require_id() != form_definition_id:
            await self._form_defs.update(current_active.require_id(), {"status": SchemaStatus.ARCHIVED}, updated_by=actor.require_id())
            archived_schema_version = current_active.schema_version
        updated = await self._form_defs.update(form_definition_id, {"status": SchemaStatus.ACTIVE}, updated_by=actor.require_id())
        await write_audit_log(
            self._db,
            event_type=AuditEvent.SCHEMA_PUBLISHED,
            user_id=actor.require_id(),
            metadata={
                "product_category": draft.product_category,
                "product_id": draft.product_id,
                "form_definition_id": form_definition_id,
                "schema_version": draft.schema_version,
                "archived_schema_version": archived_schema_version,
            },
        )
        return updated or draft

    async def compare_form_definitions(
        self, product_category: str, product_id: str, schema_version_a: int, schema_version_b: int
    ) -> SchemaCompareResponse:
        """Ask #8 — pure computation over already-stored versions (no new storage): the
        product's schema history is exactly its `application_form_definitions` rows
        (an old ACTIVE becomes ARCHIVED on publish, never deleted), so any two
        `schema_version`s are already sitting in the collection to diff."""
        versions = await self._form_defs.find_all_versions_by_product(product_category, product_id)
        by_schema_version = {v.schema_version: v for v in versions}
        def_a, def_b = by_schema_version.get(schema_version_a), by_schema_version.get(schema_version_b)
        if def_a is None or def_b is None:
            raise NotFoundError("One or both schema versions were not found for this product.")

        fields_a, fields_b = {f.key: f for f in def_a.fields}, {f.key: f for f in def_b.fields}
        modified_fields: list[SchemaFieldDiffEntry] = []
        unchanged_field_count = 0
        for key, fb in fields_b.items():
            fa = fields_a.get(key)
            if fa is None:
                continue
            if fa.model_dump() != fb.model_dump():
                modified_fields.append(SchemaFieldDiffEntry(key=key, attribute="field", old_value=fa.model_dump(), new_value=fb.model_dump()))
            else:
                unchanged_field_count += 1

        docs_a = {d.document_type_id: d for d in def_a.required_documents}
        docs_b = {d.document_type_id: d for d in def_b.required_documents}
        modified_documents: list[SchemaFieldDiffEntry] = []
        unchanged_document_count = 0
        for doc_id, db_ in docs_b.items():
            da = docs_a.get(doc_id)
            if da is None:
                continue
            if da.model_dump() != db_.model_dump():
                modified_documents.append(SchemaFieldDiffEntry(key=doc_id, attribute="document", old_value=da.model_dump(), new_value=db_.model_dump()))
            else:
                unchanged_document_count += 1

        name_map = await self.resolve_document_type_name_map(set(docs_a) | set(docs_b))
        return SchemaCompareResponse(
            product_name=await self.resolve_product_name(product_category, product_id),
            schema_version_a=schema_version_a,
            schema_version_b=schema_version_b,
            added_fields=[field_to_response(f) for k, f in fields_b.items() if k not in fields_a],
            removed_fields=[field_to_response(f) for k, f in fields_a.items() if k not in fields_b],
            modified_fields=modified_fields,
            added_documents=[required_document_to_response(d, name_map) for k, d in docs_b.items() if k not in docs_a],
            removed_documents=[required_document_to_response(d, name_map) for k, d in docs_a.items() if k not in docs_b],
            modified_documents=modified_documents,
            unchanged_field_count=unchanged_field_count,
            unchanged_document_count=unchanged_document_count,
        )

    async def list_schema_audit_entries(self, product_category: str, product_id: str) -> list[SchemaAuditEntryResponse]:
        """Ask #9 — reuses the existing generic `audit_logs` collection rather than
        building the still-empty `app/features/audit/` feature. Filtered by
        `metadata.product_category`/`metadata.product_id` so history survives a
        `create_new_version` clone (a new `form_definition_id` each time)."""
        cursor = (
            self._db["audit_logs"]
            .find(
                {
                    "event_type": {"$in": [AuditEvent.SCHEMA_FIELD_UPDATED, AuditEvent.SCHEMA_DRAFT_CREATED, AuditEvent.SCHEMA_PUBLISHED, AuditEvent.SCHEMA_FROZEN]},
                    "metadata.product_category": product_category,
                    "metadata.product_id": product_id,
                }
            )
            .sort("created_at", -1)
            .limit(200)
        )
        docs = [doc async for doc in cursor]
        actor_ids = {doc.get("user_id") for doc in docs if doc.get("user_id")}
        name_map = await self._resolve_actor_names(actor_ids)
        entries: list[SchemaAuditEntryResponse] = []
        for doc in docs:
            metadata = doc.get("metadata") or {}
            changes = [SchemaFieldDiffEntry(**c) for c in metadata.get("field_changes", [])] + [
                SchemaFieldDiffEntry(**c) for c in metadata.get("document_changes", [])
            ]
            entries.append(
                SchemaAuditEntryResponse(
                    id=str(doc["_id"]),
                    event_type=doc["event_type"],
                    changed_by=doc.get("user_id"),
                    changed_by_name=name_map.get(doc.get("user_id") or "", None),
                    changed_at=doc["created_at"],
                    changes=changes,
                    metadata=metadata,
                )
            )
        return entries

    def compute_progress(self, form_def: ApplicationFormDefinition, form_data: dict[str, Any]) -> int:
        """% of currently-visible required Basic Information fields that have a value —
        a Customer Portal display indicator only (see ApplicationDetailResponse
        docstring), never a gate on Save/Submit. Repeatable-group blocks aren't factored
        in (no seeded product uses one yet — see Phase 3.1 report)."""
        required_visible = [f for f in form_def.fields if f.required and is_field_visible(f, form_data)]
        if not required_visible:
            return 100
        filled = sum(1 for f in required_visible if not _is_blank(form_data.get(f.key)))
        return round(filled / len(required_visible) * 100)

    async def compute_progress_for_application(self, application: Application) -> int:
        """Same `compute_progress` used by the Detail response, applied to any Application
        in a list — used by `list_own_applications` so My Applications cards can show a
        real Progress % (previously only available on the single-Application Detail
        fetch). `0`, not `compute_progress`'s own "no required fields -> 100" default, for
        an application with no schema at all — a card can't claim 100% complete against
        nothing to fill in."""
        if not application.form_definition_id:
            return 0
        form_def = await self._form_defs.find_by_id(application.form_definition_id)
        if form_def is None:
            return 0
        return self.compute_progress(form_def, application.form_data)

    async def get_own_application(self, application_id: str, actor: User) -> Application:
        application = await self._applications.find_by_id(application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        if application.user_id != actor.require_id():
            raise ForbiddenError("This isn't your application.")
        return application

    async def list_own_applications(self, actor: User, *, status: str | None) -> list[Application]:
        return await self._applications.find_for_user(actor.require_id(), status=status)

    async def update_application(self, application_id: str, payload: UpdateApplicationRequest, actor: User) -> Application:
        application = await self.get_own_application(application_id, actor)
        if application.status != ApplicationStatus.DRAFT:
            raise ConflictError("Only draft applications can be edited.")
        updates: dict[str, Any] = {}
        if payload.form_data is not None:
            form_data = dict(payload.form_data)
            form_def = await self._form_defs.find_by_id(application.form_definition_id)
            if form_def is not None:
                for field in form_def.fields:
                    if field.key in form_data:
                        form_data[field.key] = normalize_field_value(field, form_data[field.key])
            updates["form_data"] = form_data
        if payload.pending_profile is not None:
            updates["pending_profile"] = payload.pending_profile
        if not updates:
            return application
        updated = await self._applications.update(application_id, updates, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.APPLICATION_UPDATED, user_id=actor.require_id(), metadata={"application_id": application_id}
        )
        if application.lead_id:
            await self._log_lead_timeline(application.lead_id, LeadTimelineEvent.CUSTOMER_SAVED_DRAFT, {"application_id": application_id})
        return updated or application

    async def submit_application(self, application_id: str, payload: SubmitApplicationRequest, actor: User) -> Application:
        application = await self.get_own_application(application_id, actor)
        if application.status != ApplicationStatus.DRAFT:
            raise ConflictError("This application has already been submitted.")

        form_def = await self._form_defs.find_by_id(application.form_definition_id)
        if form_def is None:
            raise ValidationError("This application's form definition no longer exists.")

        errors = validate_form_data(form_def.fields, application.form_data)
        for group in form_def.repeatable_groups:
            blocks = application.form_data.get(group.key) or []
            if len(blocks) < group.min_count:
                errors.append(f"{group.label}: at least {group.min_count} required.")
            for block in blocks:
                errors.extend(validate_form_data(group.fields, block))
        if errors:
            raise ValidationError(" ".join(errors))

        documents = await self._documents.find_for_application(application_id)
        uploaded_type_ids = {d.document_type_id for d in documents}
        missing_docs = [t for t in form_def.required_document_type_ids if t not in uploaded_type_ids]
        if missing_docs:
            raise ValidationError("Please upload all required documents before submitting.")

        customer_id = application.customer_id
        if customer_id is None:
            if payload.profile is None:
                raise ValidationError("Profile details are required to submit this application.")
            customer = await self._create_customer_from_profile(payload.profile, actor, converted_from_lead_id=application.lead_id)
            customer_id = customer.require_id()

        updated = await self._applications.update(
            application_id,
            {"status": ApplicationStatus.SUBMITTED, "submitted_at": utc_now(), "customer_id": customer_id, "pending_profile": None},
            updated_by=actor.require_id(),
        )
        await write_audit_log(
            self._db, event_type=AuditEvent.APPLICATION_SUBMITTED, user_id=actor.require_id(), metadata={"application_id": application_id}
        )
        if application.lead_id:
            await self._log_lead_timeline(application.lead_id, LeadTimelineEvent.CUSTOMER_SUBMITTED_APPLICATION, {"application_id": application_id})

        # Deferred import: loan_management/insurance_management both import this module's
        # Application model/repository at module level, so importing them back at module
        # level here would be circular. Case creation used to be entirely lazy (a
        # submitted application had no case — and was invisible to every dashboard/report/
        # notification keyed on cases — until a staff member happened to open the case
        # list); `ensure_case_for_application` is idempotent, so calling it eagerly here is
        # safe even alongside the existing lazy sync paths.
        final_application = updated or application
        if final_application.product_category == "loan":
            from app.features.loan_management.service import LoanCaseService

            await LoanCaseService(self._db).ensure_case_for_application(application_id)
        elif final_application.product_category == "insurance":
            from app.features.insurance_management.service import InsuranceCaseService

            await InsuranceCaseService(self._db).ensure_case_for_application(application_id)

        return final_application

    # ================================================================== documents

    async def get_document_upload_url(self, application_id: str, document_type_id: str, file_name: str, actor: User, content_type: str | None) -> tuple[str, str]:
        application = await self.get_own_application(application_id, actor)
        if await self._document_types.find_by_id(document_type_id) is None:
            raise ValidationError("Unknown document_type_id.")
        s3_key = f"application-documents/{application.application_code}/{document_type_id}/{file_name}"
        url = generate_presigned_upload_url(s3_key, expires_in=_UPLOAD_URL_EXPIRE_SECONDS, content_type=content_type)
        return url, s3_key

    async def confirm_document(self, application_id: str, payload: ConfirmDocumentRequest, actor: User) -> ApplicationDocument:
        # `s3_key` is never trusted from the client (see the request schema's own
        # docstring on this field): a caller could otherwise point this at ANY key in the
        # shared bucket (e.g. another customer's document, or an employee-documents key)
        # and immediately read it back via `document_download_url`. Re-derive it
        # server-side with the exact same expression `get_document_upload_url` used to
        # mint the presigned PUT, so the only key ever persisted is the one this
        # application's own upload flow actually issued.
        application = await self.get_own_application(application_id, actor)
        if await self._document_types.find_by_id(payload.document_type_id) is None:
            raise ValidationError("Unknown document_type_id.")
        s3_key = f"application-documents/{application.application_code}/{payload.document_type_id}/{payload.file_name}"
        document = ApplicationDocument(
            application_id=application_id, document_type_id=payload.document_type_id, file_name=payload.file_name,
            s3_key=s3_key, content_type=payload.content_type, created_by=actor.require_id(),
        )
        document_id = await self._documents.insert(document)
        await write_audit_log(self._db, event_type=AuditEvent.DOCUMENT_UPLOADED, user_id=actor.require_id(), metadata={"application_id": application_id})
        return await self._documents.find_by_id(document_id) or document

    async def list_own_documents(self, application_id: str, actor: User) -> list[ApplicationDocument]:
        await self.get_own_application(application_id, actor)
        return await self._documents.find_for_application(application_id)

    async def list_documents_for_staff(self, application_id: str, actor: User) -> list[ApplicationDocument]:
        await self.get_application_for_staff(application_id, actor)
        return await self._documents.find_for_application(application_id)

    def document_download_url(self, document: ApplicationDocument) -> str:
        return generate_presigned_download_url(document.s3_key, expires_in=_DOWNLOAD_URL_EXPIRE_SECONDS)

    async def _get_document_for_staff(self, application_id: str, document_id: str, actor: User) -> ApplicationDocument:
        await self.get_application_for_staff(application_id, actor)
        document = await self._documents.find_by_id(document_id)
        if document is None or document.application_id != application_id:
            raise NotFoundError("Document not found.")
        return document

    async def verify_document(self, application_id: str, document_id: str, actor: User) -> ApplicationDocument:
        await self._get_document_for_staff(application_id, document_id, actor)
        updated = await self._documents.update(
            document_id,
            {
                "verification_status": DocumentVerificationStatus.VERIFIED,
                "verified_by": actor.require_id(), "verified_at": utc_now(), "rejection_reason": None,
            },
            updated_by=actor.require_id(),
        )
        assert updated is not None
        await write_audit_log(
            self._db, event_type=AuditEvent.DOCUMENT_VERIFIED, user_id=actor.require_id(),
            metadata={"application_id": application_id, "document_id": document_id},
        )
        return updated

    async def reject_document(self, application_id: str, document_id: str, reason: str, actor: User) -> ApplicationDocument:
        await self._get_document_for_staff(application_id, document_id, actor)
        updated = await self._documents.update(
            document_id,
            {
                "verification_status": DocumentVerificationStatus.REJECTED,
                "verified_by": actor.require_id(), "verified_at": utc_now(), "rejection_reason": reason,
            },
            updated_by=actor.require_id(),
        )
        assert updated is not None
        await write_audit_log(
            self._db, event_type=AuditEvent.DOCUMENT_REJECTED, user_id=actor.require_id(),
            metadata={"application_id": application_id, "document_id": document_id, "reason": reason},
        )
        return updated

    # ================================================================== Owner/Employee views

    async def _acting_employee_id(self, actor: User) -> str | None:
        if actor.role != EMPLOYEE:
            return None
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee else _NO_ASSIGNMENT_SENTINEL

    async def get_application_for_staff(self, application_id: str, actor: User) -> Application:
        application = await self._applications.find_by_id(application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        if actor.role == EMPLOYEE:
            employee_id = await self._acting_employee_id(actor)
            if application.assigned_to != employee_id:
                raise ForbiddenError("This application isn't assigned to you.")
        return application

    async def list_applications_for_staff(
        self, actor: User, *, search: str | None, customer_id: str | None, assigned_to: str | None,
        unassigned_only: bool = False, status: str | None = None,
        product_category: str | None = None, skip: int = 0, limit: int = 20, sort: list[tuple[str, int]] | None = None,
    ) -> tuple[list[Application], int]:
        # The "Unassigned Applications" queue is an Owner-only concept — an Employee has
        # no business seeing work nobody (including them) has been given yet, so this
        # flag is force-disabled for Employees regardless of what a request sends.
        if actor.role == EMPLOYEE:
            assigned_to = await self._acting_employee_id(actor)
            unassigned_only = False
        return await self._applications.search_and_filter(
            search=search, customer_id=customer_id, assigned_to=assigned_to, unassigned_only=unassigned_only, status=status,
            product_category=product_category, skip=skip, limit=limit, sort=sort,
        )

    async def assign_application(self, application_id: str, employee_id: str, actor: User) -> Application:
        if await self._applications.find_by_id(application_id) is None:
            raise NotFoundError("Application not found.")
        if await self._employees.find_by_id(employee_id) is None:
            raise ValidationError("Unknown employee_id.")
        updated = await self._applications.update(application_id, {"assigned_to": employee_id}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Application not found.")
        await write_audit_log(
            self._db, event_type=AuditEvent.APPLICATION_ASSIGNED, user_id=actor.require_id(),
            metadata={"application_id": application_id, "employee_id": employee_id},
        )
        return updated

    async def list_customers_for_staff(self, actor: User, *, search: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None) -> tuple[list[Customer], int]:
        if actor.role == EMPLOYEE:
            employee_id = await self._acting_employee_id(actor)
            assigned_apps = await self._applications.find_many({"assigned_to": employee_id}, limit=1000)
            customer_ids = {a.customer_id for a in assigned_apps if a.customer_id}
            if not customer_ids:
                return [], 0
            customers = await self._customers.find_many({"_id": {"$in": [to_object_id(c) for c in customer_ids]}}, limit=limit, skip=skip)
            return customers, len(customer_ids)
        return await self._customers.search_and_filter(search=search, skip=skip, limit=limit, sort=sort)

    async def get_customer_for_staff(self, customer_id: str, actor: User) -> Customer:
        customer = await self._customers.find_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found.")
        if actor.role == EMPLOYEE:
            employee_id = await self._acting_employee_id(actor)
            has_assignment = await self._applications.find_many({"customer_id": customer_id, "assigned_to": employee_id}, limit=1)
            if not has_assignment:
                raise ForbiddenError("This customer isn't assigned to you.")
        return customer

    # ================================================================== name resolution

    async def resolve_names_for_applications(self, applications: list[Application]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        customer_ids = {a.customer_id for a in applications if a.customer_id}
        loan_ids = {a.product_id for a in applications if a.product_category == "loan"}
        insurance_ids = {a.product_id for a in applications if a.product_category == "insurance"}
        employee_ids = {a.assigned_to for a in applications if a.assigned_to}

        customers = await self._customers.find_many({}, limit=1000) if customer_ids else []
        loan_products = await self._loan_products.find_many({}, limit=500)
        insurance_products = await self._insurance_products.find_many({}, limit=500)
        employees = await self._employees.find_many({}, limit=500) if employee_ids else []

        customer_map = {c.require_id(): c.full_name for c in customers if c.require_id() in customer_ids}
        product_map = {p.require_id(): p.name for p in loan_products if p.require_id() in loan_ids}
        product_map.update({p.require_id(): p.name for p in insurance_products if p.require_id() in insurance_ids})
        employee_map = {e.require_id(): e.display_name for e in employees if e.require_id() in employee_ids}
        return customer_map, product_map, employee_map

    async def resolve_document_type_names(self, documents: list[ApplicationDocument]) -> dict[str, str]:
        type_ids = {d.document_type_id for d in documents}
        if not type_ids:
            return {}
        types = await self._document_types.find_many({}, limit=500)
        return {t.require_id(): t.name for t in types if t.require_id() in type_ids}

    async def resolve_verifier_names(self, documents: list[ApplicationDocument]) -> dict[str, str]:
        # `verified_by` stores the acting user's own auth id (BaseDocument's usual
        # created_by/updated_by convention) rather than an employee_id, since an Owner
        # (no Employee record at all) can verify/reject documents too, not only an
        # assigned Employee — keyed by `Employee.user_id`, not `Employee.id`.
        verifier_ids = {d.verified_by for d in documents if d.verified_by}
        if not verifier_ids:
            return {}
        employees = await self._employees.find_many({}, limit=500)
        return {e.user_id: e.display_name for e in employees if e.user_id in verifier_ids}

    # ================================================================== Phase 5: Portal Home / Dashboard
    # Read-only composition of already-frozen modules (Leads, Applications, the Workflow
    # Engine, Communication History, Reminders/Tasks) — no line changed under any of
    # them, matching the exact pattern this service has used since Module 6B.

    _CASE_NEXT_ACTION: dict[str, str] = {
        "documents_pending": "Upload the requested documents",
        "credit_evaluation": "Your application is under credit review",
        "offer_acceptance": "Review and accept your loan offer",
        "additional_documents": "Upload the additional documents requested",
        "esign_nach_kyc": "Complete your eSign / NACH / KYC",
        "final_evaluation": "Your application is under final review",
        "send_for_disbursement": "Your loan is being processed for disbursement",
        "disbursed": "Your loan has been disbursed",
        "underwriting": "Your application is under underwriting review",
        "medical_verification": "Complete your medical verification",
        "premium_acceptance": "Review and accept your premium",
        "policy_generation": "Your policy is being generated",
        "policy_issued": "Your policy has been issued",
        "rejected": "Contact support for more information",
        "on_hold": "Your application is on hold — we'll be in touch",
    }

    async def _resolve_primary_application(self, actor: User) -> Application | None:
        # `find_for_user` is already sorted newest-first — the most recently submitted
        # application is "the" application this customer is tracking; if none has been
        # submitted yet, fall back to their most recent draft.
        applications = await self._applications.find_for_user(actor.require_id())
        if not applications:
            return None
        submitted = [a for a in applications if a.status == ApplicationStatus.SUBMITTED]
        return submitted[0] if submitted else applications[0]

    def _status_bucket(self, current_status: str) -> str:
        if current_status == "rejected":
            return "Rejected"
        if current_status in ("disbursed", "policy_issued"):
            return "Approved"
        return "Under Review"

    async def _resolve_relationship_manager(self, employee_id: str | None) -> RelationshipManagerResponse | None:
        if not employee_id:
            return None
        employee: Employee | None = await self._employees.find_by_id(employee_id)
        if employee is None:
            return None
        return RelationshipManagerResponse(id=employee.require_id(), name=employee.display_name, email=employee.email, mobile=employee.mobile)

    async def _own_messages(self, customer: Customer | None, *, limit: int) -> tuple[list[MessageItem], int]:
        # CommunicationHistory.recipient is a mobile number or email address (Module 9C
        # never stores a user_id reference) — matched against the Customer's own
        # denormalized contact fields, the only real link available.
        if customer is None:
            return [], 0
        recipients = [v for v in (customer.mobile, customer.email) if v]
        if not recipients:
            return [], 0
        query: dict[str, Any] = {"is_deleted": False, "recipient": {"$in": recipients}}
        total = await self._db["communication_history"].count_documents(query)
        cursor = self._db["communication_history"].find(query).sort("created_at", -1).limit(limit)
        history_docs = [doc async for doc in cursor]
        queue_ids = [h["queue_item_id"] for h in history_docs if h.get("queue_item_id")]
        queue_docs = (
            await self._db["communication_queue"].find({"_id": {"$in": [to_object_id(q) for q in queue_ids]}}).to_list(length=limit)
            if queue_ids
            else []
        )
        queue_map = {str(q["_id"]): q for q in queue_docs}
        items = []
        for h in history_docs:
            queue = queue_map.get(h.get("queue_item_id", ""))
            items.append(
                MessageItem(
                    channel=h["channel"],
                    template_name=h.get("template_name", ""),
                    subject=queue.get("rendered_subject") if queue else None,
                    body=queue.get("rendered_body", "") if queue else "",
                    status=h["status"],
                    sent_at=h.get("sent_at"),
                    created_at=h["created_at"],
                )
            )
        return items, total

    async def _own_recent_activity(self, actor: User, *, limit: int) -> list[dict[str, Any]]:
        cursor = self._db["audit_logs"].find({"user_id": actor.require_id()}).sort("created_at", -1).limit(limit)
        return [
            {"event_type": doc["event_type"], "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None}
            async for doc in cursor
        ]

    async def list_own_messages(self, actor: User, *, limit: int = 50) -> list[MessageItem]:
        customer = await self.get_own_customer(actor)
        items, _ = await self._own_messages(customer, limit=limit)
        return items

    async def get_portal_dashboard(self, actor: User) -> PortalDashboardResponse:
        """The Customer Portal's one landing-page summary call — avoids the home screen
        needing several round-trips just to render (perf requirement). Full detail
        (timeline, document list, full message history) are separate, lazily-fetched
        endpoints, only called once the customer actually opens that screen."""
        application = await self._resolve_primary_application(actor)
        customer = await self.get_own_customer(actor)
        recent_messages, recent_message_count = await self._own_messages(customer, limit=5)
        recent_activity = await self._own_recent_activity(actor, limit=5)

        if application is None:
            return PortalDashboardResponse(
                has_application=False, recent_messages=recent_messages, recent_message_count=recent_message_count,
                recent_activity=recent_activity,
            )

        form_def = await self._form_defs.find_by_id(application.form_definition_id)
        progress_percent = self.compute_progress(form_def, application.form_data) if form_def else 0

        pending_count = 0
        completed_count = 0
        document_groups: list[DocumentGroupPreview] = []
        if form_def is not None:
            uploaded = await self._documents.find_for_application(application.require_id())
            uploaded_type_ids = {d.document_type_id for d in uploaded}
            completed_count = sum(1 for rd in form_def.required_documents if rd.document_type_id in uploaded_type_ids)
            pending_count = len(form_def.required_documents) - completed_count

            name_map = await self.resolve_document_type_name_map({rd.document_type_id for rd in form_def.required_documents})
            sections_seen: list[str | None] = []
            grouped: dict[str | None, list[DocumentPreviewItem]] = {}
            for rd in form_def.required_documents:
                if rd.section not in grouped:
                    grouped[rd.section] = []
                    sections_seen.append(rd.section)
                grouped[rd.section].append(
                    DocumentPreviewItem(
                        document_type_id=rd.document_type_id,
                        document_type_name=name_map.get(rd.document_type_id, ""),
                        note=rd.note,
                        uploaded=rd.document_type_id in uploaded_type_ids,
                    )
                )
            document_groups = [DocumentGroupPreview(section=s, documents=grouped[s]) for s in sections_seen]

        product_name = await self.resolve_product_name(application.product_category, application.product_id)

        # Read-only lookup — never triggers the Workflow Engine's own lazy case-creation
        # (that side effect is deliberately staff-side only, decision 058); a submitted
        # Application with no case yet just means no staff member has opened it yet.
        case = await self._workflows.find_by_application_id(application.require_id())
        rm_employee_id = case.assigned_to if case is not None else application.assigned_to
        relationship_manager = await self._resolve_relationship_manager(rm_employee_id)

        if case is None:
            is_draft = application.status == ApplicationStatus.DRAFT
            status_label = "Draft" if is_draft else "Submitted"
            current_stage_label = "Application Draft" if is_draft else "Awaiting Review"
            next_action = "Continue your application" if is_draft else "Your application is being reviewed"
        else:
            status_label = self._status_bucket(case.current_status)
            definition = await self._workflow_defs.find_by_case_type_status(case.case_type, case.current_status)
            current_stage_label = definition.label if definition else case.current_status
            next_action = self._CASE_NEXT_ACTION.get(case.current_status, f"Awaiting: {current_stage_label}")

        return PortalDashboardResponse(
            has_application=True,
            has_lead=bool(application.lead_id),
            application_id=application.require_id(),
            application_code=application.application_code,
            product_name=product_name,
            product_category=application.product_category,
            status_label=status_label,
            current_stage_label=current_stage_label,
            progress_percent=progress_percent,
            next_action=next_action,
            relationship_manager=relationship_manager,
            pending_documents_count=pending_count,
            completed_documents_count=completed_count,
            document_groups=document_groups,
            recent_message_count=recent_message_count,
            recent_messages=recent_messages,
            recent_activity=recent_activity,
        )

    async def get_application_timeline(self, application_id: str, actor: User) -> list[TimelineEntryResponse]:
        """Derives the visual timeline from real data only — Lead (if this application
        came from one), Application (started/submitted), and the matching case's own
        `workflow_definitions` catalog + `application_status_history` transitions. No
        workflow stage is invented; the label/sequence always comes straight from the
        seeded `WorkflowDefinition` rows the Workflow Engine itself already uses."""
        application = await self.get_own_application(application_id, actor)
        entries: list[TimelineEntryResponse] = []

        if application.lead_id:
            lead = await self._leads.find_by_id(application.lead_id)
            if lead is not None:
                entries.append(TimelineEntryResponse(label="Lead Created", state="completed", occurred_at=lead.created_at))
                assigned_entry = await self._build_lead_assigned_entry(application.lead_id)
                if assigned_entry is not None:
                    entries.append(assigned_entry)

        if application.status == ApplicationStatus.DRAFT:
            entries.append(TimelineEntryResponse(label="Application Started", state="current", occurred_at=application.created_at))
            return entries

        entries.append(TimelineEntryResponse(label="Application Started", state="completed", occurred_at=application.created_at))
        entries.append(TimelineEntryResponse(label="Application Submitted", state="completed", occurred_at=application.submitted_at))

        case = await self._workflows.find_by_application_id(application_id)
        if case is None:
            return entries

        definitions = await self._workflow_defs.find_for_case_type(case.case_type)
        history = await self._status_history.find_for_workflow(case.require_id())
        sorted_history = sorted(history, key=lambda h: h.created_at)
        reached_at = {h.to_status: h.created_at for h in sorted_history}
        changed_by = {h.to_status: h.created_by for h in sorted_history if h.created_by}
        actor_names = await self._resolve_actor_names(set(changed_by.values()))

        for definition in definitions:
            if definition.status == "rejected":
                continue  # only appended below, and only if the case actually ended up there
            if definition.status == case.current_status:
                state = "current"
            elif definition.status in reached_at:
                state = "completed"
            else:
                state = "upcoming"
            entries.append(
                TimelineEntryResponse(
                    label=definition.label, state=state, occurred_at=reached_at.get(definition.status),
                    actor_name=actor_names.get(changed_by.get(definition.status) or ""),
                )
            )

        if case.current_status == "rejected":
            rejected_definition = next((d for d in definitions if d.status == "rejected"), None)
            entries.append(
                TimelineEntryResponse(
                    label=rejected_definition.label if rejected_definition else "Rejected",
                    state="rejected",
                    occurred_at=reached_at.get("rejected"),
                    actor_name=actor_names.get(changed_by.get("rejected") or ""),
                )
            )

        return entries

    async def _build_lead_assigned_entry(self, lead_id: str) -> TimelineEntryResponse | None:
        """Sourced from the originating Lead's own, already-timestamped `ASSIGNED`
        activity (Module 6A) — not a new field/collection, just reused here too."""
        activities = await self._lead_activities.find_for_lead(lead_id)
        assigned = [a for a in activities if a.event_type == LeadActivityType.ASSIGNED and a.metadata and a.metadata.get("employee_id")]
        if not assigned:
            return None
        latest = max(assigned, key=lambda a: a.created_at)
        employee_id = latest.metadata["employee_id"] if latest.metadata else None
        employee = await self._employees.find_by_id(employee_id) if employee_id else None
        if employee is None:
            return None
        return TimelineEntryResponse(label=f"Assigned to {employee.display_name}", state="completed", occurred_at=latest.created_at)

    async def _resolve_actor_names(self, user_ids: set[str]) -> dict[str, str]:
        user_ids.discard("")
        if not user_ids:
            return {}
        employees = await self._employees.find_many({}, limit=500)
        return {e.user_id: e.display_name for e in employees if e.user_id in user_ids}

    async def raise_support_request(self, payload: RaiseSupportRequestRequest, actor: User) -> SupportRequestResponse:
        """"Support" stays the lightweight model the brief asks for — no new ticketing
        module. Reuses `RemindersService.create_task` verbatim (which already notifies
        the assignee) when a Relationship Manager is assigned. `Task.assigned_to` is
        structurally a real Employee reference and Owner has no Employee record, so when
        no RM is assigned yet, every Owner is notified directly instead of forcing a
        fake assignment — the same "notify every Owner" mechanism Module 6D's own task
        escalation ladder already established, not a new one."""
        application = await self._resolve_primary_application(actor)
        employee_id: str | None = None
        if application is not None:
            case = await self._workflows.find_by_application_id(application.require_id())
            employee_id = (case.assigned_to if case is not None else None) or application.assigned_to

        if employee_id is not None:
            await self._reminders.create_task(
                CreateTaskRequest(
                    title=f"Support request: {payload.subject}", description=payload.message,
                    assigned_to=employee_id, due_at=utc_now() + timedelta(days=1),
                ),
                actor,
            )
            return SupportRequestResponse(created_task=True)

        customer = await self.get_own_customer(actor)
        owners = await self._db["users"].find({"role": OWNER, "is_deleted": False}).to_list(length=50)
        for owner_doc in owners:
            await self._reminders.create_notification(
                recipient_user_id=str(owner_doc["_id"]), notification_type=NotificationType.SUPPORT_REQUEST_RAISED,
                title=f"Support request: {payload.subject}", message=payload.message,
                entity_type="customer", entity_id=customer.require_id() if customer else None,
            )
        return SupportRequestResponse(created_task=False)
