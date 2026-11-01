"""Same-identity revisions. Snapshots and the effective pointer commit in one invoice CAS.

No numbering utility, counter mutation, or second invoice insertion is used here.
Owners can save directly; staff proposals remain available. Effective revision entries
are append-only.
"""

from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from bson import BSON, ObjectId

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.invoices.calculations import calculate
from app.features.invoices.numbering import never_issued_draft
from app.features.invoices.schemas import (
    DirectRevisionInput,
    InvoiceConfig,
    InvoiceItem,
    ReissueInput,
    RevisionInput,
)
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
                "same_number_save_in_progress",
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

    async def can_supersede(self, doc: dict[str, Any]) -> bool:
        if never_issued_draft(doc):
            return True
        if doc["status"] not in {"issued", "cancelled"} or not doc.get("issued_at"):
            return False
        if any(
            event.get("new_status") in {"paid", "partially_paid"}
            or event.get("action") in {"paid", "partially_paid"}
            for event in doc.get("history", [])
        ):
            return False
        return not bool(
            await self.db.audit_logs.find_one(
                {
                    "metadata.invoice_id": str(doc.get("_id", doc.get("id"))),
                    "event_type": {"$in": ["invoice_paid", "invoice_partially_paid"]},
                }
            )
        )

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
            if (
                doc.get("retired_for_revision_of") == invoice_id
                and doc["status"] == "cancelled"
                and doc.get("is_archived")
            ):
                continue
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
                "can_supersede": await self.can_supersede(doc),
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

    async def supersede_replacements(
        self,
        invoice_id: str,
        actor: User,
        source_number: str,
        reason: str,
        expected_versions: dict[str, int],
        save_lock: str,
    ) -> list[dict[str, Any]]:
        context = await self.legacy_conflicts(invoice_id, actor)
        copies = context["drafts"] + context["blockers"]
        if any(not copy["can_supersede"] for copy in copies):
            numbers = ", ".join(
                copy["invoice_number"] for copy in copies if not copy["can_supersede"]
            )
            raise ConflictError(
                f"Replacement {numbers} is settled or restricted. It cannot be cancelled by Save & Reissue."
            )
        if {copy["id"]: copy["version"] for copy in copies} != expected_versions:
            raise ConflictError(
                "Linked replacement invoices changed. Refresh the linked records and save again; your edits are retained."
            )
        superseded = []
        for item in copies:
            if not await self.db.invoices.find_one(
                {"_id": ObjectId(invoice_id), "revision_save_lock": save_lock}
            ):
                raise ConflictError("Save ownership changed. Reload before saving.")
            current = await self.invoices.get(item["id"], actor)
            if current["version"] != item["version"] or not await self.can_supersede(current):
                raise ConflictError(
                    "Linked replacement changed. Refresh the linked records before saving."
                )
            now = utc_now()
            explanation = f"Superseded by direct same-number save of {source_number}: {reason}"
            updates: dict[str, Any] = {
                "status": "cancelled",
                "is_archived": True,
                "archived_by": actor.require_id(),
                "archived_at": now,
                "archive_reason": explanation,
                "retired_for_revision_of": invoice_id,
            }
            if current["status"] != "cancelled":
                updates.update(
                    cancelled_by=actor.require_id(),
                    cancelled_at=now,
                    cancellation_reason=explanation,
                )
            if current.get("issued_at") and not current.get("revisions"):
                updates["revisions"] = [original_record(current)]
            self.capacity(current, updates)
            await self.invoices.replace(
                item["id"], current, item["version"], updates, actor, "replacement_superseded"
            )
            superseded.append(
                {
                    "id": item["id"],
                    "invoice_number": item["invoice_number"],
                    "previous_status": current["status"],
                }
            )
        return superseded

    @staticmethod
    def capacity(current: dict[str, Any], updates: dict[str, Any]) -> None:
        if len(BSON.encode(current | updates)) > 12 * 1024 * 1024:
            raise ConflictError(
                "Invoice revision history reached its safe storage limit. Contact the accounting owner; no revision was overwritten."
            )

    async def prepare(
        self, current: dict[str, Any], payload: RevisionInput, actor: User
    ) -> dict[str, Any]:
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
        return updates

    async def request(self, invoice_id: str, payload: RevisionInput, actor: User) -> dict[str, Any]:
        current = await self.editable(invoice_id, actor)
        updates = await self.prepare(current, payload, actor)
        return await self.invoices.replace(
            invoice_id, current, payload.version, updates, actor, "revision_requested"
        )

    async def save(
        self, invoice_id: str, payload: DirectRevisionInput, actor: User
    ) -> dict[str, Any]:
        if actor.role != OWNER:
            raise ForbiddenError("Only the owner can directly save and reissue an invoice.")
        current = await self.editable(invoice_id, actor)
        if payload.version != current["version"]:
            raise ConflictError("Invoice changed. Reload before saving; no changes were applied.")
        token = uuid4().hex
        now = utc_now()
        claimed = await self.db.invoices.find_one_and_update(
            {
                "_id": ObjectId(invoice_id),
                "version": payload.version,
                "status": current["status"],
                "is_deleted": False,
                "is_archived": {"$ne": True},
                "$or": [{"revision_save_lock": None}, {"revision_save_lock_until": {"$lt": now}}],
            },
            {
                "$set": {
                    "revision_save_lock": token,
                    "revision_save_lock_until": now + timedelta(minutes=5),
                }
            },
        )
        if not claimed:
            raise ConflictError(
                "Another save is in progress or this invoice changed. Retry after reloading."
            )
        try:
            # Build only in memory: no pending proposal or separate approval is persisted.
            prepared = current | await self.prepare(current, payload, actor)
            decision = ReissueInput(
                version=payload.version,
                proposal_id=prepared["revision_proposal"]["id"],
                approval_reason=payload.reason,
            )
            return await self.apply(
                invoice_id,
                prepared,
                decision,
                actor,
                direct_versions=payload.legacy_replacement_versions,
                save_lock=token,
            )
        finally:
            await self.db.invoices.update_one(
                {"_id": ObjectId(invoice_id), "revision_save_lock": token},
                {"$unset": {"revision_save_lock": "", "revision_save_lock_until": ""}},
            )

    async def reissue(self, invoice_id: str, payload: ReissueInput, actor: User) -> dict[str, Any]:
        if actor.role != OWNER:
            raise ForbiddenError("Accounting-owner approval is required to reissue.")
        current = await self.editable(invoice_id, actor)
        return await self.apply(invoice_id, current, payload, actor)

    async def apply(
        self,
        invoice_id: str,
        current: dict[str, Any],
        payload: ReissueInput,
        actor: User,
        *,
        direct_versions: dict[str, int] | None = None,
        save_lock: str | None = None,
    ) -> dict[str, Any]:
        if actor.role != OWNER:
            raise ForbiddenError("Only the owner can save an effective issued revision.")
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
            "authorization_mode": "owner_save"
            if direct_versions is not None
            else "separate_owner_approval",
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
        if direct_versions is not None:
            retired = await self.supersede_replacements(
                invoice_id,
                actor,
                current["invoice_number"],
                payload.approval_reason.strip(),
                direct_versions,
                save_lock or "",
            )
        else:
            retired = await self.retire_legacy_drafts(
                invoice_id, payload, actor, current["invoice_number"]
            )
        if retired:
            record["retired_legacy_drafts"] = retired
        return await self.invoices.replace(
            invoice_id,
            current,
            payload.version,
            updates,
            actor,
            "same_number_reissued",
            **({"save_lock": save_lock} if save_lock else {}),
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
