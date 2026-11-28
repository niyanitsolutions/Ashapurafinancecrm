# ruff: noqa: F811
"""Partner portal regression tests; disposable local MongoDB, no external sends."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.auth.models import User
from app.features.referral_partner_management.accounts import create_account
from app.features.referral_partner_management.finance import (
    PayoutInput,
    money,
    payout,
    save_rule,
)
from app.features.referral_partner_management.indexes import (
    ensure_referral_partner_management_indexes,
)
from app.features.referral_partner_management.kyc import PartnerKyc
from app.features.referral_partner_management.portal_models import (
    KycConfiguration,
    KycDraft,
)
from app.features.referral_partner_management.schemas import (
    CreateCommissionRuleRequest,
    CreateReferralPartnerRequest,
)
from app.security.password import verify_password
from bson import ObjectId
from test_daily_handover_enhancement import environment  # noqa: F401
from test_pin_mongo_integration import pin_mongo  # noqa: F401


@pytest.fixture
async def portal(pin_mongo):
    await ensure_referral_partner_management_indexes(pin_mongo)
    owner = User(id=str(ObjectId()), mobile="9000000001", role="owner")
    return pin_mongo, owner


def account(**updates):
    return CreateReferralPartnerRequest(
        full_name="Synthetic Partner",
        mobile="9000000011",
        initial_password="SyntheticPass1!",
        confirm_password="SyntheticPass1!",
        request_id=uuid4().hex,
        **updates,
    )


async def test_owner_account_hash_and_idempotency_no_otp(portal):
    db, owner = portal
    payload = account(temporary_password=True)
    partner = await create_account(db, payload, owner)
    repeated = await create_account(db, payload, owner)
    assert repeated.id == partner.id
    user = await db.users.find_one({"user_id": partner.user_id})
    assert user is None
    user = await db.users.find_one({"_id": ObjectId(partner.user_id)})
    assert user["must_change_password"] and verify_password(
        "SyntheticPass1!", user["password_hash"]
    )
    assert partner.kyc_status == "pending"
    assert (
        await db.users.count_documents({})
        == await db.referral_partners.count_documents({})
        == 1
    )
    audit = await db.audit_logs.find_one({"event_type": "referral_partner_created"})
    assert "SyntheticPass1!" not in str(audit)
    assert await db.otp_challenges.count_documents({}) == 0
    with pytest.raises(ConflictError):
        await create_account(db, account(), owner)


async def test_existing_customer_identity_not_duplicated_or_overwritten(portal):
    db, owner = portal
    user = User(
        mobile="9000000011",
        role="customer",
        password_hash="preserved",
        pin_hash="preserved-pin",
    )
    await db.users.insert_one(user.model_dump(exclude={"id"}))
    with pytest.raises(ConflictError):
        await create_account(db, account(), owner)
    assert await db.users.count_documents({}) == 1
    assert await db.referral_partners.count_documents({}) == 0
    saved = await db.users.find_one({})
    assert (
        saved["password_hash"] == "preserved" and saved["pin_hash"] == "preserved-pin"
    )


async def test_employee_cannot_provision_partner(portal):
    db, owner = portal
    with pytest.raises(ForbiddenError):
        await create_account(
            db, account(), owner.model_copy(update={"role": "employee"})
        )


async def test_kyc_config_is_immutable_and_controls_are_protected(portal):
    db, owner = portal
    service = PartnerKyc(db)
    first = await service.configuration()
    payload = KycConfiguration.model_validate(first)
    payload.fields[0].required = False
    with pytest.raises(ValidationError):
        await service.publish(payload, owner)
    agreement = await db.partner_kyc_documents.insert_one(
        {"partner_id": "agreement", "status": "available"}
    )
    payload = KycConfiguration.model_validate(first)
    payload.required_agreement_ids = [str(agreement.inserted_id)]
    payload.fields[0].label = "Birth date"
    result = await service.publish(payload, owner)
    assert result["version"] == 2
    assert (await service.configuration(1))["fields"][0]["label"] == "Date of Birth"
    with pytest.raises(ConflictError):
        await service.publish(payload, owner)


async def test_kyc_sensitive_values_encrypted_and_partner_isolation(portal):
    db, owner = portal
    partner = await create_account(db, account(), owner)
    actor = User.model_validate(
        await db.users.find_one({"_id": ObjectId(partner.user_id)})
    )
    service = PartnerKyc(db)
    await service.draft(
        KycDraft(
            version=0,
            form_version=1,
            values={"pan_number": "ABCDE1234F", "account_number": "1234567890"},
            confirm_account_number="1234567890",
        ),
        actor,
    )
    saved = await db.partner_kyc_submissions.find_one({})
    assert "ABCDE1234F" not in str(saved) and "1234567890" not in str(saved)
    result = await service.state(actor)
    assert result["values"]["account_number"] == "******7890"
    with pytest.raises(ValidationError):
        await service.submit(1, actor)
    unrelated = actor.model_copy(update={"id": str(ObjectId())})
    with pytest.raises(Exception, match="Partner not found"):
        await service.state(unrelated, partner.id)


async def test_rule_overlap_and_version_snapshot(portal):
    db, owner = portal
    payload = CreateCommissionRuleRequest(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        label="Default percentage",
        calculation_type="percentage",
        rate_or_amount=2,
        trigger_event="loan_disbursed",
    )
    with pytest.raises(ValidationError, match="category|trigger"):
        await save_rule(
            db, payload.model_copy(update={"product_category": "insurance"}), owner
        )
    first = await save_rule(db, payload, owner)
    with pytest.raises(ConflictError):
        await save_rule(db, payload, owner)
    second = await save_rule(
        db, payload.model_copy(update={"rate_or_amount": 3}), owner, first
    )
    assert second.rule_version == 2 and second.previous_rule_id == first.id
    original = await db.commission_rules.find_one({"_id": ObjectId(first.id)})
    assert original["rate_or_amount"] == 2


async def test_partial_payout_retry_and_overpayment_guard(portal):
    db, owner = portal
    entry_id = ObjectId()
    await db.commission_entries.insert_one(
        {
            "_id": entry_id,
            "case_id": str(ObjectId()),
            "partner_id": str(ObjectId()),
            "commission_amount": 100,
            "paid_amount": 0,
            "status": "approved",
            "is_deleted": False,
            "version": 1,
        }
    )
    payload = PayoutInput(
        request_id=uuid4().hex,
        amount=40,
        payment_reference="SYNTHETIC-PAYMENT",
        payment_method="bank_transfer",
        payment_date="2026-11-26",
        confirmed=True,
    )
    first = await payout(db, str(entry_id), payload, owner)
    repeated = await payout(db, str(entry_id), payload, owner)
    assert repeated["id"] == first["id"]
    assert (await db.commission_entries.find_one({"_id": entry_id}))[
        "outstanding_amount"
    ] == 60
    with pytest.raises(ValidationError):
        await payout(
            db,
            str(entry_id),
            payload.model_copy(update={"amount": 61, "request_id": uuid4().hex}),
            owner,
        )
    with pytest.raises(ConflictError, match="reference"):
        await payout(
            db,
            str(entry_id),
            payload.model_copy(update={"amount": 60, "request_id": uuid4().hex}),
            owner,
        )
    await payout(
        db,
        str(entry_id),
        payload.model_copy(
            update={
                "amount": 60,
                "request_id": uuid4().hex,
                "payment_reference": "SYNTHETIC-PAYMENT-2",
            }
        ),
        owner,
    )
    assert (await db.commission_entries.find_one({"_id": entry_id}))["status"] == "paid"
    assert await db.commission_payouts.count_documents({}) == 2


async def test_grouped_payment_reserves_confirms_and_cancels_atomically(portal):
    from app.features.referral_partner_management.payouts import (
        ConfirmPayment,
        ReservePayment,
        finish,
        reserve,
    )

    db, owner = portal
    partner_id = str(ObjectId())
    entries = []
    for amount in (100, 200):
        entry_id = ObjectId()
        entries.append(str(entry_id))
        await db.commission_entries.insert_one(
            {
                "_id": entry_id,
                "case_id": str(ObjectId()),
                "partner_id": partner_id,
                "commission_amount": amount,
                "paid_amount": 0,
                "status": "approved",
                "is_deleted": False,
                "version": 1,
            }
        )
    payload = ReservePayment(
        request_id=uuid4().hex,
        allocations=[
            {"entry_id": entries[0], "amount": 60},
            {"entry_id": entries[1], "amount": 150},
        ],
    )
    reserved = await reserve(db, payload, owner)
    assert (await reserve(db, payload, owner))["id"] == reserved["id"]
    assert reserved["amount"] == 210 and reserved["status"] == "initiated"
    with pytest.raises(ValidationError, match="available"):
        await reserve(db, payload.model_copy(update={"request_id": uuid4().hex}), owner)
    assert (await db.commission_entries.find_one({"_id": ObjectId(entries[0])}))[
        "reserved_amount"
    ] == 60
    with pytest.raises(ValidationError, match="exceeds"):
        await payout(
            db,
            entries[0],
            PayoutInput(
                request_id=uuid4().hex,
                amount=41,
                payment_reference="NO-OVERLAP",
                payment_method="bank_transfer",
                payment_date="2026-11-26",
                confirmed=True,
            ),
            owner,
        )
    confirmation = ConfirmPayment(
        payment_reference="SYN-GROUP-1",
        payment_method="bank_transfer",
        payment_date="2026-11-26",
        confirmed=True,
    )
    assert (await finish(db, reserved["id"], owner, confirmation=confirmation))[
        "status"
    ] == "confirmed"
    await finish(db, reserved["id"], owner, confirmation=confirmation)
    assert (await db.commission_entries.find_one({"_id": ObjectId(entries[0])}))[
        "paid_amount"
    ] == 60
    remaining = await reserve(
        db,
        ReservePayment(
            request_id=uuid4().hex, allocations=[{"entry_id": entries[0], "amount": 40}]
        ),
        owner,
    )
    await finish(db, remaining["id"], owner, reason="Synthetic cancelled transfer")
    assert (await db.commission_entries.find_one({"_id": ObjectId(entries[0])}))[
        "reserved_amount"
    ] == 0
    with pytest.raises(ConflictError):
        await finish(db, remaining["id"], owner, confirmation=confirmation)
    other = await reserve(
        db,
        ReservePayment(
            request_id=uuid4().hex, allocations=[{"entry_id": entries[0], "amount": 40}]
        ),
        owner,
    )
    with pytest.raises(ConflictError, match="reference"):
        await finish(db, other["id"], owner, confirmation=confirmation)
    # Duplicate confirmation rolls back every allocation and leaves reservation intact.
    unchanged = await db.commission_entries.find_one({"_id": ObjectId(entries[0])})
    assert unchanged["paid_amount"] == 60 and unchanged["reserved_amount"] == 40
    with pytest.raises(ForbiddenError):
        await reserve(
            db, payload, owner.model_copy(update={"role": "referral_partner"})
        )


async def test_payment_group_rejects_mixed_partner_and_rolls_back(portal):
    from app.features.referral_partner_management.payouts import ReservePayment, reserve

    db, owner = portal
    entries = []
    for _ in range(2):
        entry_id = ObjectId()
        entries.append(str(entry_id))
        await db.commission_entries.insert_one(
            {
                "_id": entry_id,
                "case_id": str(ObjectId()),
                "partner_id": str(ObjectId()),
                "commission_amount": 100,
                "status": "approved",
                "version": 1,
                "is_deleted": False,
            }
        )
    with pytest.raises(ValidationError, match="one Partner"):
        await reserve(
            db,
            ReservePayment(
                request_id=uuid4().hex,
                allocations=[{"entry_id": entry, "amount": 50} for entry in entries],
            ),
            owner,
        )
    assert (
        await db.commission_entries.count_documents({"reserved_amount": {"$gt": 0}})
        == 0
    )
    assert await db.commission_payouts.count_documents({}) == 0


async def test_concurrent_reservations_cannot_overcommit_balance(portal):
    import asyncio

    from app.core.exceptions import AppError
    from app.features.referral_partner_management.payouts import ReservePayment, reserve

    db, owner = portal
    entry_id = ObjectId()
    await db.commission_entries.insert_one(
        {
            "_id": entry_id,
            "case_id": str(ObjectId()),
            "partner_id": str(ObjectId()),
            "commission_amount": 100,
            "status": "approved",
            "version": 1,
            "is_deleted": False,
        }
    )

    async def attempt():
        try:
            return await reserve(
                db,
                ReservePayment(
                    request_id=uuid4().hex,
                    allocations=[{"entry_id": str(entry_id), "amount": 60}],
                ),
                owner,
            )
        except AppError as error:
            return error

    results = await asyncio.gather(attempt(), attempt())
    assert sum(isinstance(result, dict) for result in results) == 1
    assert (await db.commission_entries.find_one({"_id": entry_id}))[
        "reserved_amount"
    ] == 60
    assert await db.commission_payouts.count_documents({"status": "initiated"}) == 1


async def test_adjustments_preserve_original_earning_and_protect_reserved_payment(
    portal,
):
    from app.features.referral_partner_management.finance import (
        AdjustmentInput,
        CommissionDecision,
        adjust,
        commission_decision,
    )
    from app.features.referral_partner_management.payouts import (
        ConfirmPayment,
        ReservePayment,
        finish,
        reserve,
    )

    db, owner = portal
    entry_id = ObjectId()
    await db.commission_entries.insert_one(
        {
            "_id": entry_id,
            "case_id": str(ObjectId()),
            "partner_id": str(ObjectId()),
            "commission_amount": 100,
            "status": "approved",
            "version": 1,
            "is_deleted": False,
        }
    )
    reservation = await reserve(
        db,
        ReservePayment(
            request_id=uuid4().hex,
            allocations=[{"entry_id": str(entry_id), "amount": 60}],
        ),
        owner,
    )
    adjustment = AdjustmentInput(
        request_id=uuid4().hex,
        amount=-80,
        reason="Synthetic contractual correction",
        kind="adjustment",
    )
    first = await adjust(db, str(entry_id), adjustment, owner)
    assert (await adjust(db, str(entry_id), adjustment, owner))["id"] == first["id"]
    with pytest.raises(ConflictError, match="approval|review"):
        await finish(
            db,
            reservation["id"],
            owner,
            confirmation=ConfirmPayment(
                payment_reference="NOT-PAID",
                payment_method="bank_transfer",
                payment_date="2026-11-26",
                confirmed=True,
            ),
        )
    await finish(
        db, reservation["id"], owner, reason="Cancel outdated payment reservation"
    )
    entry = await db.commission_entries.find_one({"_id": entry_id})
    assert (
        entry["commission_amount"] == 100
        and entry["outstanding_amount"] == 20
        and entry["paid_amount"] == 0
    )
    assert entry["status"] == "on_hold" and entry["reserved_amount"] == 0
    with pytest.raises(ValidationError, match="real authorized"):
        await adjust(
            db,
            str(entry_id),
            AdjustmentInput(
                request_id=uuid4().hex,
                amount=-20,
                reason="No fabricated reversal",
                kind="reversal",
                financial_audit_id=str(ObjectId()),
            ),
            owner,
        )
    await adjust(
        db,
        str(entry_id),
        adjustment.model_copy(update={"request_id": uuid4().hex, "amount": -50}),
        owner,
    )
    entry = await db.commission_entries.find_one({"_id": entry_id})
    assert entry["recovery_due_amount"] == 30 and entry["outstanding_amount"] == 0
    with pytest.raises(ValidationError):
        await commission_decision(
            db,
            str(entry_id),
            CommissionDecision(
                version=entry["version"],
                action="resume",
                reason="Cannot resume recovery balance",
            ),
            owner,
        )


async def test_reserved_customer_activation_preserves_identity_and_requires_exact_proof(
    portal,
):
    from types import SimpleNamespace

    from app.features.referral_partner_management.referrals import (
        activate_reserved_identity,
    )
    from app.security.pin import verify_pin

    db, _owner = portal
    user = User(
        mobile="9000000044",
        role="customer",
        status="pending_password",
        provisioning_source="partner_manual_referral",
    )
    result = await db.users.insert_one(user.model_dump(exclude={"id"}))
    user_id = str(result.inserted_id)
    await db.applications.insert_one(
        {
            "user_id": user_id,
            "is_deleted": False,
            "referral_attribution": {"origin": "manual"},
        }
    )
    challenge = await db.auth_pin_challenges.insert_one(
        {
            "challenge_id": uuid4().hex,
            "state": "verified",
            "user_id": user_id,
            "authorization_hash": "synthetic-only",
        }
    )
    proof = await db.auth_pin_challenges.find_one({"_id": challenge.inserted_id})
    payload = SimpleNamespace(mobile=user.mobile, pin="7392")
    query = {"_id": challenge.inserted_id, "state": "verified"}
    with pytest.raises(ConflictError):
        await activate_reserved_identity(
            db, payload, {**proof, "user_id": str(ObjectId())}, query
        )
    assert await activate_reserved_identity(db, payload, proof, query)
    saved = await db.users.find_one({"_id": result.inserted_id})
    assert saved["status"] == "active" and verify_pin("7392", saved["pin_hash"])
    assert saved["password_hash"] is None and await db.users.count_documents({}) == 1
    assert (await db.applications.find_one({}))["user_id"] == user_id
    assert not await activate_reserved_identity(db, payload, proof, query)


async def test_normal_otp_registration_can_complete_exact_manual_reservation(
    portal, mock_redis
):
    from datetime import timedelta

    from app.features.auth.pin_service import PinService, Verify, digest, otp_digest
    from app.features.auth.service import AuthService, RequestContext
    from app.features.customer.schemas import CompleteDirectRegistrationRequest
    from app.features.customer.service import CustomerService
    from app.features.referral_partner_management.referrals import (
        PartnerReferrals,
        ReferralDraft,
    )
    from app.utils.datetime import utc_now

    db, owner = portal
    _partner, actor = await approved_partner(db, owner)
    referral = await PartnerReferrals(db, mock_redis).manual(
        ReferralDraft(
            product_id=await product_form(db),
            full_name="Synthetic registered customer",
            mobile="9000000067",
            request_id=uuid4().hex,
        ),
        actor,
    )
    original = await db.users.find_one({"mobile": "9000000067"})
    challenge_id = "s" * 43
    await db.auth_pin_challenges.insert_one(
        {
            "_id": digest("9000000067:REGISTRATION"),
            "challenge_id": challenge_id,
            "mobile": "9000000067",
            "purpose": "REGISTRATION",
            "user_id": str(original["_id"]),
            "state": "issued",
            "otp_hash": otp_digest(challenge_id, "8621"),
            "expires_at": utc_now() + timedelta(minutes=5),
            "attempts": 0,
        }
    )
    # A verified, locally seeded provider response; no transport or real SMS.
    proof = await PinService(AuthService(db, mock_redis)).verify(
        Verify(
            mobile="9000000067",
            purpose="REGISTRATION",
            challenge_id=challenge_id,
            otp="8621",
        ),
        RequestContext(ip_address="127.0.0.1", user_agent="synthetic"),
    )
    assert proof["next_action"] == "register" and proof["authorization"]
    await CustomerService(db, mock_redis).complete_direct_registration(
        CompleteDirectRegistrationRequest(
            mobile="9000000067",
            authorization=proof["authorization"],
            pin="7392",
            confirm_pin="7392",
        )
    )
    saved = await db.users.find_one({"_id": original["_id"]})
    assert saved["status"] == "active" and saved["is_mobile_verified"]
    assert await db.users.count_documents({"mobile": "9000000067"}) == 1
    assert (await db.applications.find_one({"_id": ObjectId(referral["id"])}))[
        "user_id"
    ] == str(original["_id"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, "0.001", None])
def test_money_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        money(value)


async def approved_partner(db, owner):
    from app.utils.datetime import utc_now

    partner = await create_account(db, account(), owner)
    submission = await db.partner_kyc_submissions.insert_one(
        {
            "partner_id": partner.id,
            "status": "approved",
            "form_version": 1,
            "accepted_agreement_ids": [],
            "values_cipher": __import__(
                "app.security.encryption", fromlist=["encrypt"]
            ).encrypt("{}"),
            "consent": False,
            "document_ids": [],
            "version": 1,
            "created_at": utc_now(),
        }
    )
    await db.referral_partners.update_one(
        {"_id": ObjectId(partner.id)},
        {
            "$set": {
                "kyc_status": "approved",
                "approval_status": "active",
                "current_kyc_id": str(submission.inserted_id),
            }
        },
    )
    actor = User.model_validate(
        await db.users.find_one({"_id": ObjectId(partner.user_id)})
    )
    return partner, actor


async def product_form(db):
    from app.features.customer.models import (
        ApplicationFormDefinition,
        FormFieldDefinition,
    )
    from app.features.system_settings.models import LoanProduct

    product = LoanProduct(name="Synthetic Partner Loan")
    result = await db.loan_products.insert_one(product.model_dump(exclude={"id"}))
    form = ApplicationFormDefinition(
        product_category="loan",
        product_id=str(result.inserted_id),
        status="active",
        fields=[
            FormFieldDefinition(
                key="full_name", label="Customer name", field_type="text", required=True
            )
        ],
    )
    await db.application_form_definitions.insert_one(form.model_dump(exclude={"id"}))
    return str(result.inserted_id)


async def test_manual_referral_reuses_customer_and_always_requires_review(portal):
    from app.features.customer.indexes import ensure_customer_indexes
    from app.features.customer.models import Application, Customer
    from app.features.referral_partner_management.referrals import (
        PartnerReferrals,
        ReferralDraft,
        customer_submission_updates,
    )
    from app.utils.datetime import utc_now

    db, owner = portal
    await ensure_customer_indexes(db)
    partner, actor = await approved_partner(db, owner)
    await db.referral_partners.update_one(
        {"_id": ObjectId(partner.id)}, {"$set": {"submission_mode": "direct_to_afs"}}
    )
    user = User(mobile="9000000022", role="customer", password_hash="keep-credentials")
    result = await db.users.insert_one(user.model_dump(exclude={"id"}))
    customer = Customer(
        customer_code="SYN-CUSTOMER",
        user_id=str(result.inserted_id),
        full_name="Original verified name",
        mobile=user.mobile,
    )
    await db.customers.insert_one(customer.model_dump(exclude={"id"}))
    service = PartnerReferrals(db)
    payload = ReferralDraft(
        product_id=await product_form(db),
        full_name="Entered customer",
        mobile=user.mobile,
        request_id=uuid4().hex,
    )
    first = await service.manual(payload, actor)
    repeated = await service.manual(payload, actor)
    assert repeated["id"] == first["id"]
    assert first["referral"]["submission_mode"] == "partner_review"
    assert not first["referral"]["submitted_to_afs_at"]
    assert await db.customers.count_documents({}) == 1
    assert (await db.customers.find_one({}))["full_name"] == "Original verified name"
    row = await db.applications.find_one({"_id": ObjectId(first["id"])})
    with pytest.raises(ForbiddenError):
        await customer_submission_updates(
            db, Application.model_validate(row), user, utc_now()
        )
    with pytest.raises(Exception, match="Partner not found|Referral not found"):
        await service.detail(
            first["id"], actor.model_copy(update={"id": str(ObjectId())})
        )


async def test_secure_link_binding_retry_and_snapshot_mode(portal):
    from app.features.referral_partner_management.referrals import (
        LinkInput,
        PartnerReferrals,
    )

    db, owner = portal
    partner, actor = await approved_partner(db, owner)
    service = PartnerReferrals(db)
    product = await product_form(db)
    payload = LinkInput(product_id=product, request_id=uuid4().hex)
    first = await service.link(payload, actor)
    repeated = await service.link(payload, actor)
    assert first["path"] == repeated["path"]
    assert await db.partner_referral_links.count_documents({}) == 1
    token = first["path"].split("#")[-1]
    stored = await db.partner_referral_links.find_one({})
    assert token not in str(stored)
    await db.referral_partners.update_one(
        {"_id": ObjectId(partner.id)}, {"$set": {"submission_mode": "direct_to_afs"}}
    )
    customer = User(id=str(ObjectId()), mobile="9000000033", role="customer")
    await db.users.insert_one(
        {**customer.model_dump(exclude={"id"}), "_id": ObjectId(customer.id)}
    )
    claimed = await service.redeem(token, customer)
    assert await service.redeem(token, customer) == claimed
    row = await db.applications.find_one({"_id": ObjectId(claimed["application_id"])})
    assert row["referral_attribution"]["submission_mode"] == "partner_review"
    with pytest.raises(Exception, match="already used"):
        await service.redeem(token, customer.model_copy(update={"id": str(ObjectId())}))
    assert await db.applications.count_documents({}) == 1


async def test_real_disbursement_creates_commission_in_same_transaction(environment):
    from app.features.loan_management.schemas import DisburseRequest
    from app.features.loan_management.service import LoanCaseService
    from app.utils.datetime import utc_now
    from test_daily_handover_enhancement import loan

    db, owner, _employees, _customer, application = environment
    await ensure_referral_partner_management_indexes(db)
    partner, _actor = await approved_partner(db, owner)
    await db.applications.update_one(
        {"_id": ObjectId(application.id)},
        {
            "$set": {
                "referral_attribution": {
                    "partner_id": partner.id,
                    "referral_id": str(ObjectId()),
                    "submitted_to_afs_at": utc_now(),
                }
            }
        },
    )
    await save_rule(
        db,
        CreateCommissionRuleRequest(
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            label="Default",
            calculation_type="percentage",
            rate_or_amount=2,
            trigger_event="loan_disbursed",
        ),
        owner,
    )
    case = await loan(environment)
    await LoanCaseService(db).disburse(
        case.id,
        DisburseRequest(
            disbursed_amount=50000, disbursed_reference="SYNTHETIC-DISBURSE"
        ),
        owner,
    )
    entry = await db.commission_entries.find_one({"case_id": case.id})
    assert entry["base_amount"] == 50000 and entry["commission_amount"] == 1000
    notices = [
        row
        async for row in db.notifications.find(
            {"title": "Referral application updated"}
        )
    ]
    assert len(notices) == 1 and notices[0]["recipient_user_id"] == partner.user_id
    assert (
        "50000" not in notices[0]["message"]
        and partner.mobile not in notices[0]["message"]
    )

    history = await db.application_status_history.find_one(
        {"_id": ObjectId(entry["disbursement_event_id"])}
    )
    assert (
        history["application_workflow_id"] == case.id
        and history["to_status"] == "disbursed"
    )
    with pytest.raises(ConflictError):
        await LoanCaseService(db).disburse(
            case.id,
            DisburseRequest(
                disbursed_amount=50000, disbursed_reference="SYNTHETIC-DISBURSE"
            ),
            owner,
        )
    assert await db.commission_entries.count_documents({}) == 1


@pytest.fixture
def private_storage(monkeypatch):
    import io
    from types import SimpleNamespace

    from app.features.employee import hr_documents
    from app.features.referral_partner_management import kyc

    class Storage:
        def __init__(self):
            self.objects = {}

        def head_object(self, **kwargs):
            return {"ContentLength": len(self.objects[kwargs["Key"]])}

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}

        def put_object(self, **kwargs):
            self.objects[kwargs["Key"]] = kwargs["Body"]

        def delete_object(self, **kwargs):
            self.objects.pop(kwargs["Key"], None)

    storage = Storage()
    for module in (kyc, hr_documents):
        monkeypatch.setattr(module, "get_s3_client", lambda: storage)
        monkeypatch.setattr(
            module,
            "get_storage_config",
            lambda: SimpleNamespace(bucket_name="synthetic-private-kyc"),
        )
    monkeypatch.setattr(
        kyc,
        "generate_presigned_upload_url",
        lambda key, **_kwargs: "https://synthetic-storage.invalid/" + key,
    )
    return storage


@pytest.mark.parametrize("house,aadhaar", [("own", "pdf"), ("rented", "images")])
async def test_complete_private_kyc_review_reupload_and_activation(
    portal, private_storage, house, aadhaar
):
    import io

    import pymupdf
    from app.features.referral_partner_management.portal_models import (
        ConfirmDocument,
        DocumentTicket,
        KycDecision,
    )
    from app.features.referral_partner_management.service import (
        ReferralPartnerManagementService,
    )
    from PIL import Image

    db, owner = portal
    service = PartnerKyc(db)
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf_bytes = pdf.tobytes()
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(stream, format="PNG")
    image_bytes = stream.getvalue()

    async def upload(
        actor,
        category,
        content=pdf_bytes,
        mime="application/pdf",
        part="file",
        agreement=False,
    ):
        ticket = await service.upload(
            DocumentTicket(
                category=category, part=part, content_type=mime, size=len(content)
            ),
            actor,
            agreement=agreement,
        )
        private_storage.objects[
            ticket["upload_url"].removeprefix("https://synthetic-storage.invalid/")
        ] = content
        return await service.confirm(
            ConfirmDocument(ticket=ticket["ticket"], consent=True), actor
        )

    agreement = await upload(owner, "partner_agreement", agreement=True)
    config = KycConfiguration.model_validate(await service.configuration())
    config.required_agreement_ids = [agreement["id"]]
    await service.publish(config, owner)
    partner = await create_account(db, account(), owner)
    actor = User.model_validate(
        await db.users.find_one({"_id": ObjectId(partner.user_id)})
    )
    values = {
        "date_of_birth": "1990-01-01",
        "pan_number": "ABCDE1234F",
        "account_holder": "Synthetic Partner",
        "bank_name": "Synthetic Bank",
        "account_number": "1234567890",
        "ifsc": "SYNB0001234",
        "bank_mobile": "9000000011",
        "current_address": "Synthetic address",
        "permanent_address": "Synthetic address",
        "house_type": house,
        "aadhaar_type": aadhaar,
    }
    await service.draft(
        KycDraft(
            version=0,
            form_version=2,
            values=values,
            confirm_account_number="1234567890",
            consent=True,
            accepted_agreement_ids=[agreement["id"]],
        ),
        actor,
    )
    for category in [
        "bank_passbook",
        "pan_document",
        "own_house_proof" if house == "own" else "rental_agreement",
    ]:
        await upload(actor, category)
    for category in ["selfie", "signature"]:
        await upload(actor, category, image_bytes, "image/png")
    if aadhaar == "images":
        for side in ["front", "back"]:
            await upload(actor, "aadhaar", image_bytes, "image/png", side)
    else:
        await upload(actor, "aadhaar")
    await service.document(agreement["id"], actor)
    submitted = await service.submit(1, actor)
    assert submitted["partner"]["kyc_status"] == "submitted"
    with pytest.raises(ValidationError, match="approved first"):
        await service.review(
            partner.id,
            KycDecision(version=2, decision="approved", fields_verified=True),
            owner,
        )
    rejected = submitted["documents"][0]
    await service.document_review(
        rejected["id"],
        KycDecision(
            version=1, decision="reupload_required", reason="Synthetic unclear document"
        ),
        owner,
    )
    state = await service.state(actor)
    assert state["partner"]["kyc_status"] == "reupload_required"
    for doc in state["documents"]:
        if doc["id"] != rejected["id"]:
            await service.document_review(
                doc["id"], KycDecision(version=1, decision="approved"), owner
            )
    # Replacement is immutable: the rejected object remains readable in history.
    replacement_content = (
        image_bytes
        if rejected["category"] in {"signature", "selfie"} or rejected["part"] != "file"
        else pdf_bytes
    )
    replacement_mime = (
        "image/png" if replacement_content == image_bytes else "application/pdf"
    )
    replacement = await upload(
        actor,
        rejected["category"],
        replacement_content,
        replacement_mime,
        rejected["part"],
    )
    await service.draft(
        KycDraft(
            version=0,
            form_version=2,
            values=values,
            confirm_account_number="1234567890",
            consent=True,
            accepted_agreement_ids=[agreement["id"]],
        ),
        actor,
    )
    await service.submit(1, actor)
    await service.document_review(
        replacement["id"], KycDecision(version=1, decision="approved"), owner
    )
    approved = await service.review(
        partner.id,
        KycDecision(version=2, decision="approved", fields_verified=True),
        owner,
    )
    assert approved["partner"]["kyc_status"] == "approved"
    assert approved["partner"]["approval_status"] == "pending_approval"
    activated = await ReferralPartnerManagementService(db).approve_partner(
        partner.id, owner
    )
    assert activated.approval_status == "active"
    with pytest.raises(ConflictError, match="locked"):
        await service.upload(
            DocumentTicket(
                category="bank_passbook",
                content_type="application/pdf",
                size=len(pdf_bytes),
            ),
            actor,
        )
    # An unused ticket cannot bypass a later overall approval, even before S3 access.
    import hashlib
    from datetime import timedelta

    from app.utils.datetime import utc_now

    prior_ticket = await db.partner_kyc_uploads.find_one(
        {"partner_id": partner.id, "category": "bank_passbook"}
    )
    unused_token = "z" * 43
    await db.partner_kyc_uploads.insert_one(
        {
            **prior_ticket,
            "_id": ObjectId(),
            "ticket_hash": hashlib.sha256(unused_token.encode()).hexdigest(),
            "used": False,
            "expires_at": utc_now() + timedelta(minutes=10),
            "s3_key": "synthetic-unused-staging",
        }
    )
    with pytest.raises(ConflictError, match="locked"):
        await service.confirm(ConfirmDocument(ticket=unused_token, consent=True), actor)
    old = await db.partner_kyc_documents.find_one({"_id": ObjectId(rejected["id"])})
    assert (
        not old["current"]
        and old["review_history"][0]["reason"] == "Synthetic unclear document"
    )
    assert (
        await db.partner_kyc_submissions.count_documents({"partner_id": partner.id})
        == 2
    )
    assert all(
        key.startswith("partner-kyc/encrypted/") for key in private_storage.objects
    )
    unrelated = User(id=str(ObjectId()), role="referral_partner", mobile="9000000088")
    with pytest.raises(Exception, match="Partner not found"):
        await service.document(replacement["id"], unrelated)

    next_agreement = await upload(owner, "partner_agreement", agreement=True)
    next_form = KycConfiguration.model_validate(await service.configuration())
    next_form.required_agreement_ids = [next_agreement["id"]]
    next(
        field for field in next_form.fields if field.key == "bank_passbook"
    ).mime_types = ["image/png"]
    await service.publish(next_form, owner)
    assert (await service.state(actor))["requires_agreement_acceptance"]
    await service.document(next_agreement["id"], actor)
    await service.draft(
        KycDraft(
            version=0,
            form_version=3,
            values=values,
            confirm_account_number="1234567890",
            consent=True,
            accepted_agreement_ids=[next_agreement["id"]],
        ),
        actor,
    )
    # Previously approved PDFs cannot bypass the next form's image-only policy.
    from app.features.referral_partner_management.referrals import eligible

    assert (await service.state(actor))["partner"]["kyc_status"] == "pending"
    with pytest.raises(ForbiddenError):
        await eligible(db, actor)
    with pytest.raises(ValidationError, match="accepted file format"):
        await service.submit(1, actor)
    assert (await service.state(actor))["submission"]["status"] == "draft"


async def test_multiple_disbursements_keep_original_rate_and_one_case_ledger(
    environment,
):
    from datetime import date

    from app.features.loan_management.disbursement_events import record
    from app.features.loan_management.schemas import (
        AdditionalDisbursementRequest,
        DisburseRequest,
        ScheduleTopUpRequest,
    )
    from app.features.loan_management.service import LoanCaseService
    from app.utils.datetime import utc_now
    from test_daily_handover_enhancement import loan

    db, owner, _employees, _customer, application = environment
    await ensure_referral_partner_management_indexes(db)
    partner, _actor = await approved_partner(db, owner)
    await db.applications.update_one(
        {"_id": ObjectId(application.id)},
        {
            "$set": {
                "referral_attribution": {
                    "partner_id": partner.id,
                    "referral_id": str(ObjectId()),
                    "submitted_to_afs_at": utc_now(),
                }
            }
        },
    )
    payload = CreateCommissionRuleRequest(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        label="Default",
        calculation_type="percentage",
        rate_or_amount=2,
        trigger_event="loan_disbursed",
    )
    original_rule = await save_rule(db, payload, owner)
    case = await loan(environment)
    service = LoanCaseService(db)
    await service.disburse(
        case.id,
        DisburseRequest(
            disbursed_amount=50000,
            disbursed_reference="SYNTHETIC-FIRST",
            disbursement_date=date(2026, 11, 26),
            final_disbursement=False,
        ),
        owner,
    )
    with pytest.raises(ValidationError, match="tranches"):
        await service.schedule_top_up(
            case.id, ScheduleTopUpRequest(period="3_months"), owner
        )
    await save_rule(
        db, payload.model_copy(update={"rate_or_amount": 3}), owner, original_rule
    )
    second = AdditionalDisbursementRequest(
        request_id=uuid4().hex,
        amount=30000,
        disbursement_date=date(2026, 11, 26),
        reference="SYNTHETIC-SECOND",
        remarks="Synthetic second tranche",
        final_disbursement=False,
    )
    await record(service, case.id, second, owner)
    await record(service, case.id, second, owner)
    third = second.model_copy(
        update={
            "request_id": uuid4().hex,
            "amount": 20000,
            "reference": "SYNTHETIC-THIRD",
            "final_disbursement": True,
        }
    )
    await record(service, case.id, third, owner)
    current = await db.application_workflows.find_one({"_id": ObjectId(case.id)})
    assert current["loan_details"]["disbursed_amount"] == 100000
    assert len(current["loan_details"]["disbursement_events"]) == 3
    entry = await db.commission_entries.find_one({"case_id": case.id})
    assert entry["commission_amount"] == 1000 and entry["rate_or_amount"] == 2
    assert (
        entry["additional_earned_amount"] == 1500
        and entry["outstanding_amount"] == 2500
    )
    assert await db.commission_entries.count_documents({}) == 1
    lines = [
        r
        async for r in db.commission_entry_events.find({"kind": "disbursement_earning"})
    ]
    assert len(lines) == 2 and {r["rate_or_amount"] for r in lines} == {3}
    assert {r["base_amount"] for r in lines} == {30000, 20000}
    for line in lines:
        event = await db.audit_logs.find_one(
            {"_id": ObjectId(line["disbursement_event_id"])}
        )
        assert event["event_type"] == "loan_additional_disbursement_confirmed"
    with pytest.raises(ConflictError, match="pending"):
        await record(
            service,
            case.id,
            third.model_copy(update={"request_id": uuid4().hex}),
            owner,
        )


async def test_missing_rule_exception_resolution_and_scoped_financial_report(
    environment,
):
    from datetime import date

    from app.features.loan_management.schemas import DisburseRequest
    from app.features.loan_management.service import LoanCaseService
    from app.features.referral_partner_management.finance import resolve_exception
    from app.features.referral_partner_management.reporting import metrics, owner_report
    from app.utils.datetime import utc_now
    from test_daily_handover_enhancement import loan

    db, owner, _employees, _customer, application = environment
    await ensure_referral_partner_management_indexes(db)
    partner, actor = await approved_partner(db, owner)
    await db.applications.update_one(
        {"_id": ObjectId(application.id)},
        {
            "$set": {
                "referral_attribution": {
                    "partner_id": partner.id,
                    "partner_name": partner.full_name,
                    "referral_id": str(ObjectId()),
                    "submitted_to_afs_at": utc_now(),
                    "origin": "manual",
                    "submission_mode": "partner_review",
                }
            }
        },
    )
    case = await loan(environment)
    await LoanCaseService(db).disburse(
        case.id,
        DisburseRequest(
            disbursed_amount=50000,
            disbursement_date=date(2026, 11, 26),
            disbursed_reference="SYN-EXCEPTION",
        ),
        owner,
    )
    exception = await db.commission_exceptions.find_one({})
    assert (
        exception["reason"] == "missing_rule"
        and await db.commission_entries.count_documents({}) == 0
    )
    with pytest.raises(ValidationError, match="rule"):
        await resolve_exception(
            db, str(exception["_id"]), "Synthetic rule review", owner
        )
    await save_rule(
        db,
        CreateCommissionRuleRequest(
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            label="Confirmed retrospective contract",
            calculation_type="percentage",
            rate_or_amount=2,
            trigger_event="loan_disbursed",
        ),
        owner,
    )
    resolved = await resolve_exception(
        db, str(exception["_id"]), "Verified original agreed contract", owner
    )
    assert resolved["status"] == "resolved"
    await resolve_exception(db, str(exception["_id"]), "Retry exact resolution", owner)
    assert await db.commission_entries.count_documents({}) == 1
    own = await metrics(db, actor, start=date(2026, 11, 26), end=date(2026, 11, 26))
    assert own["eligible_disbursed_amount"] == 50000 and own["disbursed_loans"] == 1
    assert "total_partners" not in own
    unrelated = actor.model_copy(update={"id": str(ObjectId())})
    with pytest.raises(Exception, match="Partner not found"):
        await metrics(db, unrelated)
    report = await owner_report(
        db, owner, partner_id=partner.id, commission_status="pending"
    )
    assert len(report.rows) == 1 and report.rows[0]["commission_earned"] == 1000
    assert not (await owner_report(db, owner, partner_id=str(ObjectId()))).rows
    with pytest.raises(ForbiddenError):
        await owner_report(db, actor)


async def test_account_audit_failure_rolls_back_identity(portal, monkeypatch):
    db, owner = portal
    collection_type = type(db.audit_logs)
    original = collection_type.insert_one

    async def fail(collection, *args, **kwargs):
        if collection.name == "audit_logs" and collection.database.name == db.name:
            raise RuntimeError("Synthetic audit outage")
        return await original(collection, *args, **kwargs)

    monkeypatch.setattr(collection_type, "insert_one", fail)
    with pytest.raises(RuntimeError, match="Synthetic"):
        await create_account(db, account(), owner)
    monkeypatch.setattr(collection_type, "insert_one", original)
    assert await db.users.count_documents({}) == 0
    assert await db.referral_partners.count_documents({}) == 0
    assert await db.notifications.count_documents({}) == 0


async def test_duplicate_referral_rejected_without_disclosure_or_partial_identity(
    portal,
):
    from app.features.referral_partner_management.referrals import (
        PartnerReferrals,
        ReferralDraft,
    )

    db, owner = portal
    _partner, actor = await approved_partner(db, owner)
    service = PartnerReferrals(db)
    payload = ReferralDraft(
        product_id=await product_form(db),
        full_name="Synthetic Customer",
        mobile="9000000033",
        request_id=uuid4().hex,
    )
    first = await service.manual(payload, actor)
    with pytest.raises(ConflictError, match="duplicate review") as caught:
        await service.manual(
            payload.model_copy(update={"request_id": uuid4().hex}), actor
        )
    assert first["id"] not in str(caught.value) and payload.mobile not in str(
        caught.value
    )
    assert (
        await db.applications.count_documents({}) == 1
        and await db.customers.count_documents({}) == 1
    )
    assert await db.users.count_documents({"role": "customer"}) == 1


async def test_api_partner_owner_boundaries_and_private_document_access(portal, client):
    from app.config.database import get_database
    from app.features.auth.dependencies import get_current_active_user

    db, owner = portal
    partner, actor = await approved_partner(db, owner)
    app = client._transport.app
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: actor
    for path in (
        "/partner-management/metrics",
        "/partner-management/report",
        "/partner-management/payments",
        "/partner-management/commission-exceptions",
        f"/partner-management/kyc/{partner.id}",
    ):
        assert (await client.get("/api/v1" + path)).status_code == 403
    own = await client.get("/api/v1/partner-portal/kyc")
    assert own.status_code == 200 and own.json()["data"]["partner"]["id"] == partner.id
    product_id = await product_form(db)
    await save_rule(
        db,
        CreateCommissionRuleRequest(
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            label="Visible own rule",
            calculation_type="flat",
            rate_or_amount=100,
            trigger_event="loan_disbursed",
            product_category="loan",
            product_id=product_id,
            fixed_event_policy="per_event",
            fixed_contract_confirmed=True,
        ),
        owner,
    )
    rules = await client.get("/api/v1/partner-portal/rules")
    assert rules.status_code == 200
    rule = rules.json()["data"][0]
    assert rule["product_name"] == "Synthetic Partner Loan"
    assert rule["trigger_event"] == "loan_disbursed"
    assert (
        rule["product_category"] == "loan" and rule["fixed_event_policy"] == "per_event"
    )
    foreign = await db.partner_kyc_documents.insert_one(
        {"partner_id": str(ObjectId()), "s3_key": "never-read"}
    )
    assert (
        await client.get(f"/api/v1/partner-portal/documents/{foreign.inserted_id}")
    ).status_code == 404
    from app.features.referral_partner_management.models import CommissionEntry

    entry = CommissionEntry(
        partner_id=partner.id,
        lead_id="",
        case_id=str(ObjectId()),
        case_type="loan",
        rule_id=str(ObjectId()),
        calculation_type="percentage",
        rate_or_amount=2,
        base_amount=5000,
        commission_amount=100,
        additional_earned_amount=20,
        outstanding_amount=120,
    )
    own_entry = await db.commission_entries.insert_one(entry.model_dump(exclude={"id"}))
    await db.commission_entry_events.insert_one(
        {
            "entry_id": str(own_entry.inserted_id),
            "kind": "adjustment",
            "amount": 20,
            "reason": "Synthetic private Owner reason",
            "authorized_by": owner.id,
        }
    )
    history = await client.get(
        f"/api/v1/commission-entries/{own_entry.inserted_id}/history"
    )
    assert (
        history.status_code == 200
        and history.json()["data"]["original"]["amount"] == 100
    )
    assert "reason" not in history.json()["data"]["events"][0]
    assert "authorized_by" not in history.json()["data"]["events"][0]
    foreign_entry = await db.commission_entries.insert_one(
        entry.model_copy(
            update={"partner_id": str(ObjectId()), "case_id": str(ObjectId())}
        ).model_dump(exclude={"id"})
    )
    assert (
        await client.get(
            f"/api/v1/commission-entries/{foreign_entry.inserted_id}/history"
        )
    ).status_code == 404
    app.dependency_overrides[get_current_active_user] = lambda: owner.model_copy(
        update={"role": "employee"}
    )
    assert (await client.get("/api/v1/partner-portal/kyc")).status_code == 403
    assert (await client.get("/api/v1/partner-management/report")).status_code == 403
    assert (
        await client.get(f"/api/v1/commission-entries/{own_entry.inserted_id}/history")
    ).status_code == 403


async def test_attribution_correction_audited_without_rewriting_earnings(portal):
    from app.features.referral_partner_management.management import (
        AttributionCorrection,
        correct_attribution,
    )
    from app.features.referral_partner_management.referrals import (
        PartnerReferrals,
        ReferralDraft,
    )

    db, owner = portal
    first, actor = await approved_partner(db, owner)
    second = await create_account(
        db,
        account().model_copy(
            update={"mobile": "9000000066", "request_id": uuid4().hex}
        ),
        owner,
    )
    await db.referral_partners.update_one(
        {"_id": ObjectId(second.id)},
        {"$set": {"kyc_status": "approved", "approval_status": "active"}},
    )
    referral = await PartnerReferrals(db).manual(
        ReferralDraft(
            product_id=await product_form(db),
            full_name="Synthetic referral",
            mobile="9000000055",
            request_id=uuid4().hex,
        ),
        actor,
    )
    earning = {
        "case_id": str(ObjectId()),
        "application_id": referral["id"],
        "partner_id": first.id,
        "commission_amount": 100,
        "paid_amount": 20,
        "status": "approved",
    }
    await db.commission_entries.insert_one(earning)
    payload = AttributionCorrection(
        version=referral["version"],
        partner_id=second.id,
        reason="Synthetic verified attribution correction",
        acknowledge_financial_history=True,
    )
    with pytest.raises(ForbiddenError):
        await correct_attribution(db, referral["id"], payload, actor)
    result = await correct_attribution(db, referral["id"], payload, owner)
    assert result["financial_history_unchanged"]
    original_earning = await db.commission_entries.find_one({})
    assert (
        original_earning["partner_id"] == first.id
        and original_earning["paid_amount"] == 20
    )
    audit = await db.audit_logs.find_one(
        {"event_type": "partner_referral_attribution_corrected"}
    )
    assert audit["metadata"]["before"]["partner_id"] == first.id
    assert audit["metadata"]["after"]["partner_id"] == second.id
    with pytest.raises(ConflictError):
        await correct_attribution(db, referral["id"], payload, owner)


async def test_current_agreement_notifications_are_bounded_and_idempotent(portal):
    from app.features.referral_partner_management.notifications import (
        notify_updated_agreements,
    )

    db, owner = portal
    partner, _actor = await approved_partner(db, owner)
    service = PartnerKyc(db)
    agreement = await db.partner_kyc_documents.insert_one(
        {"partner_id": "agreement", "status": "available"}
    )
    form = KycConfiguration.model_validate(await service.configuration())
    form.required_agreement_ids = [str(agreement.inserted_id)]
    await service.publish(form, owner)
    result = await notify_updated_agreements(db)
    assert result == {"notified": 1, "processed": 1}
    assert (await notify_updated_agreements(db))["notified"] == 0
    # A label-only new form version does not repeat the same required-terms notice.
    form = KycConfiguration.model_validate(await service.configuration())
    form.fields[0].label = "Birth date"
    await service.publish(form, owner)
    assert (await notify_updated_agreements(db))["notified"] == 0
    notices = [
        row
        async for row in db.notifications.find(
            {"title": "Partner agreement acceptance required"}
        )
    ]
    assert len(notices) == 1 and notices[0]["recipient_user_id"] == partner.user_id
    assert partner.mobile not in notices[0]["message"]
