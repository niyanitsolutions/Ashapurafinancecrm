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
from app.features.invoices.numbering import never_issued_draft
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
        if current["status"] not in {"issued", "cancelled"} or current.get("is_archived"):
            raise ConflictError(
                "Only non-archived issued or previously issued cancelled invoices can enter same-number revision mode."
            )
        if current["status"] == "cancelled":
            if not current.get("issued_at"):
                raise ConflictError(
                    "This cancelled draft was never issued and cannot use issued-invoice reissue."
                )
            settled = any(
                event.get("new_status") in {"paid", "partially_paid"}
                or event.get("action") in {"paid", "partially_paid"}
                for event in current.get("history", [])
            )
            if settled or await self.db.audit_logs.find_one(
                {
                    "metadata.invoice_id": invoice_id,
                    "event_type": {"$in": ["invoice_paid", "invoice_partially_paid"]},
                }
            ):
                raise ConflictError(
                    "This cancelled invoice has settlement history and requires an accounting adjustment, not same-number reissue."
                )
        await self.policy()
        return current

    async def legacy_conflicts(
        self, invoice_id: str, actor: User
    ) -> dict[str, list[dict[str, Any]]]:
        if actor.role != OWNER:
            raise ForbiddenError(
                "Accounting-owner access is required to review replacement conflicts."
            )
        await self.invoices.get(invoice_id, actor)
        docs = await self.db.invoices.find(
            {"replacement_for": invoice_id, "is_deleted": False}
        ).to_list(None)
        result: dict[str, list[dict[str, Any]]] = {"drafts": [], "blockers": []}
        for doc in docs:
            # Cancelled, never-issued copies cannot be issued again and reserve their numbers.
            if (
                doc["status"] == "cancelled"
                and not doc.get("issued_at")
                and not doc.get("revisions")
                and not any(
                    event.get("new_status") in {"issued", "paid", "partially_paid"}
                    or event.get("action") in {"issued", "paid", "partially_paid"}
                    for event in doc.get("history", [])
                )
                and not await self.db.audit_logs.find_one(
                    {
                        "metadata.invoice_id": str(doc["_id"]),
                        "event_type": {
                            "$in": ["invoice_issued", "invoice_paid", "invoice_partially_paid"]
                        },
                    }
                )
            ):
                continue
            item = {
                "id": str(doc["_id"]),
                "invoice_number": doc["invoice_number"],
                "status": doc["status"],
                "version": doc["version"],
            }
            result["drafts" if never_issued_draft(doc) else "blockers"].append(item)
        return result

    async def retire_legacy_drafts(
        self, invoice_id: str, payload: ReissueInput, actor: User, source_number: str
    ) -> list[dict[str, Any]]:
        conflicts = await self.legacy_conflicts(invoice_id, actor)
        if conflicts["blockers"]:
            numbers = ", ".join(doc["invoice_number"] for doc in conflicts["blockers"])
            raise ConflictError(
                f"Replacement {numbers} was issued or finalized and cannot be retired automatically. Review that financial record before reissuing this invoice."
            )
        if conflicts["drafts"] and not payload.retire_legacy_drafts:
            raise ConflictError(
                "Confirm retirement of the listed unissued replacement drafts before approving same-number reissue. Your proposal has been saved."
            )
        expected = {doc["id"]: doc["version"] for doc in conflicts["drafts"]}
        if expected and payload.legacy_draft_versions != expected:
            raise ConflictError(
                "Older replacement drafts changed. Refresh the replacement records and confirm again. Your proposal remains saved."
            )
        retired = []
        for item in conflicts["drafts"]:
            current = await self.invoices.get(item["id"], actor)
            if current["version"] != item["version"] or not never_issued_draft(current):
                raise ConflictError("Replacement changed. Reload and review it before approving.")
            now = utc_now()
            reason = f"Retired for same-number reissue of {source_number}: {payload.approval_reason.strip()}"
            # This CAS races on the SAME legacy document as issue. Only retirement or issue can win.
            await self.invoices.replace(
                item["id"],
                current,
                item["version"],
                {
                    "status": "cancelled",
                    "cancelled_by": actor.require_id(),
                    "cancelled_at": now,
                    "cancellation_reason": reason,
                    "is_archived": True,
                    "archived_by": actor.require_id(),
                    "archived_at": now,
                    "archive_reason": reason,
                    "retired_for_revision_of": invoice_id,
                },
                actor,
                "legacy_draft_retired",
            )
            retired.append({"id": item["id"], "invoice_number": item["invoice_number"]})
        return retired

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
            "base_status": current["status"],
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
        if payload.version != current["version"]:
            raise ConflictError("Invoice changed. Reload and review before approving.")
        proposal = current.get("revision_proposal")
        if not proposal or proposal["id"] != payload.proposal_id:
            raise ConflictError("Revision proposal changed. Reload and review it before approving.")
        if proposal.get("base_status", "issued") != current["status"]:
            raise ConflictError(
                "Invoice status changed. Save and review a new proposal before approving."
            )
        if not payload.approval_reason.strip():
            raise ValidationError("Accounting approval reason is required.")
        if proposal["base_revision"] != current.get("effective_revision", 1):
            raise ConflictError("The effective invoice revision changed. Review a new proposal.")
        now = utc_now()
        number = current.get("effective_revision", 1) + 1
        approved = deepcopy(proposal["snapshot"])
        approved.update(
            status="issued",
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
        if current["status"] == "cancelled":
            record["previous_status"] = "cancelled"
            record["cancellation"] = {
                key: current.get(key)
                for key in (
                    "cancelled_by",
                    "cancelled_at",
                    "cancellation_reason",
                )
            }
        # Reissue restores the active issued state; historical cancellation metadata stays intact.
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
            status="issued",
            effective_revision=number,
            reissued_at=now,
            revision_proposal=None,
            revisions=[*current["revisions"], record],
        )
        self.capacity(current, updates)
        retired = await self.retire_legacy_drafts(
            invoice_id, payload, actor, current["invoice_number"]
        )
        if retired:
            record["retired_legacy_drafts"] = retired
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
