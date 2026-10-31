"""Same-identity revisions. Snapshots and the effective pointer commit in one invoice CAS.

No numbering utility, counter mutation, or second invoice insertion is used here.
Only the pending proposal is editable; effective revision entries are append-only.
"""

from copy import deepcopy
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from bson import BSON

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.invoices.calculations import calculate
from app.features.invoices.schemas import InvoiceConfig, InvoiceItem, ReissueInput, RevisionInput
from app.utils.datetime import utc_now

if TYPE_CHECKING:
    from app.features.invoices.service import InvoiceService


def snapshot(current: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(
        {
            k: v
            for k, v in current.items()
            if k
            not in {
                "revisions",
                "revision_proposal",
                "history",
                "source_status",
                "correction_resumed",
                "same_number_revision_enabled",
            }
        }
    )


def original_record(current: dict[str, Any]) -> dict[str, Any]:
    return {
        "revision_number": 1,
        "previous_revision": None,
        "status": "issued",
        "snapshot": snapshot(current),
        "reason": "Original issued snapshot",
        "reissued_at": current.get("issued_at"),
        "changed_by": current.get("updated_by"),
        "captured_at": utc_now(),
        "historical_capture": True,
    }


class InvoiceRevisionService:
    def __init__(self, invoices: "InvoiceService") -> None:
        self.invoices = invoices
        self.db = invoices.db

    async def policy(self) -> InvoiceConfig:
        company = await self.invoices.company.get_or_create()
        policy = InvoiceConfig.model_validate(company.invoice_config)
        if not (
            policy.same_number_reissue_enabled
            and policy.same_number_policy_approved_by
            and policy.same_number_policy_approved_at
        ):
            raise ConflictError(
                "Same-number reissue is disabled. The accounting owner must approve the invoice policy in Invoice Settings. Use the required formal accounting document if same-number changes are not permitted."
            )
        return policy

    async def editable(self, invoice_id: str, actor: User) -> dict[str, Any]:
        current = await self.invoices.get(invoice_id, actor)
        if current["status"] != "issued" or current.get("is_archived"):
            raise ConflictError(
                "Only active, unsettled issued invoices can enter same-number revision mode."
            )
        if await self.db.invoices.find_one({"replacement_for": invoice_id, "is_deleted": False}):
            raise ConflictError(
                "A legacy separately numbered correction exists. Review that record before requesting a same-number revision; it will not be converted or discarded."
            )
        await self.policy()
        return current

    @staticmethod
    def capacity(current: dict[str, Any], updates: dict[str, Any]) -> None:
        if len(BSON.encode(current | updates)) > 12 * 1024 * 1024:
            raise ConflictError(
                "Invoice revision history reached its safe storage limit. Contact the accounting owner; no revision was overwritten."
            )

    async def request(self, invoice_id: str, payload: RevisionInput, actor: User) -> dict[str, Any]:
        current = await self.editable(invoice_id, actor)
        if not payload.reason.strip():
            raise ValidationError("Correction reason is required.")
        await self.invoices.customer_validate(payload.invoice, actor)
        business = payload.invoice.model_dump(mode="json", exclude={"request_key", "version"})
        proposed = (
            snapshot(current)
            | business
            | calculate(payload.invoice.items, payload.invoice.tax_type)
        )
        # Preserve original issue date, company/bank/images and statutory identity.
        proposed["company"] = deepcopy(current["company"])
        proposed["invoice_number"] = current["invoice_number"]
        proposed["issued_at"] = current.get("issued_at")
        from app.features.invoices.service import payment_qr

        proposed["qr_value"] = payment_qr(proposed["company"], proposed)
        old_business = {key: current.get(key) for key in business}
        old_business["items"] = [
            {key: row[key] for key in InvoiceItem.model_fields} for row in current["items"]
        ]
        proposal = {
            "id": uuid4().hex,
            "status": "pending_owner_approval",
            "snapshot": proposed,
            "reason": payload.reason.strip(),
            "requested_by": actor.require_id(),
            "requested_at": utc_now(),
            "base_revision": current.get("effective_revision", 1),
            "changed_fields": [k for k in business if business[k] != old_business.get(k)],
        }
        updates = {
            "revision_proposal": proposal,
            "revisions": current.get("revisions") or [original_record(current)],
        }
        self.capacity(current, updates)
        return await self.invoices.replace(
            invoice_id, current, payload.version, updates, actor, "revision_requested"
        )

    async def reissue(self, invoice_id: str, payload: ReissueInput, actor: User) -> dict[str, Any]:
        if actor.role != OWNER:
            raise ForbiddenError("Accounting-owner approval is required to reissue.")
        current = await self.editable(invoice_id, actor)
        policy = await self.policy()
        proposal = current.get("revision_proposal")
        if not proposal or proposal["id"] != payload.proposal_id:
            raise ConflictError("Revision proposal changed. Reload and review it before approving.")
        if not payload.approval_reason.strip():
            raise ValidationError("Accounting approval reason is required.")
        if proposal["base_revision"] != current.get("effective_revision", 1):
            raise ConflictError("The effective invoice revision changed. Review a new proposal.")
        now = utc_now()
        number = current.get("effective_revision", 1) + 1
        approved = deepcopy(proposal["snapshot"])
        approved.update(
            effective_revision=number,
            reissued_at=now,
            updated_by=actor.require_id(),
            updated_at=now,
            version=current["version"] + 1,
        )
        record = {
            "revision_number": number,
            "previous_revision": number - 1,
            "status": "issued",
            "snapshot": snapshot(approved),
            "reason": proposal["reason"],
            "changed_fields": proposal["changed_fields"],
            "changed_by": proposal["requested_by"],
            "changed_at": proposal["requested_at"],
            "approved_by": actor.require_id(),
            "approved_at": now,
            "approval_reason": payload.approval_reason.strip(),
            "policy_approved_by": policy.same_number_policy_approved_by,
            "policy_approved_at": policy.same_number_policy_approved_at,
            "reissued_at": now,
        }
        # Update only business/PDF fields; never replace identity/lifecycle/audit metadata.
        fields = set(proposal["changed_fields"]) | {
            "items",
            "subtotal",
            "gst_total",
            "igst_total",
            "cgst_total",
            "sgst_total",
            "grand_total",
            "amount_in_words",
            "hsn_summary",
            "qr_value",
        }
        updates = {key: approved[key] for key in fields}
        updates.update(
            effective_revision=number,
            reissued_at=now,
            revision_proposal=None,
            revisions=[*current["revisions"], record],
        )
        self.capacity(current, updates)
        return await self.invoices.replace(
            invoice_id, current, payload.version, updates, actor, "same_number_reissued"
        )

    async def history(self, invoice_id: str, actor: User) -> list[dict[str, Any]]:
        current = await self.invoices.get(invoice_id, actor)
        records = current.get("revisions") or (
            [original_record(current)] if current.get("issued_at") else []
        )
        return [
            {k: v for k, v in record.items() if k != "snapshot"}
            | {"current": record["revision_number"] == current.get("effective_revision", 1)}
            for record in records
        ]

    async def historical(self, invoice_id: str, number: int, actor: User) -> dict[str, Any]:
        current = await self.invoices.get(invoice_id, actor)
        records = current.get("revisions") or (
            [original_record(current)] if current.get("issued_at") else []
        )
        for record in records:
            if record["revision_number"] == number:
                return deepcopy(record["snapshot"])
        raise NotFoundError("Invoice revision not found.")
