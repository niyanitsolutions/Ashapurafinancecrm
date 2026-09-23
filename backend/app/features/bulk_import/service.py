import hashlib
import json
import math
from datetime import date
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError as SchemaError
from redis.asyncio import Redis

from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.bulk_import.files import MODELS, fields
from app.features.insurance_management.schemas import CreateManualInsuranceCaseRequest
from app.features.insurance_management.service import InsuranceCaseService
from app.features.leads.schemas import CreateLeadRequest
from app.features.leads.service import LeadService
from app.features.system_settings.repository import (
    InsuranceCategoryRepository,
    InsuranceProductRepository,
    LeadSourceRepository,
    LoanProductRepository,
)

TTL = 86400
ROWS_PER_CONFIRM = 25


class BulkImportService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self.db = db
        self.redis = redis
        self._lookups: dict[str, dict[str, list[dict[str, str]]]] = {}

    async def lookups(self, kind: str) -> dict[str, list[dict[str, str]]]:
        if kind in self._lookups:
            return self._lookups[kind]
        repositories: dict[str, Any] = {
            "insurance_products": InsuranceProductRepository,
            "categories": InsuranceCategoryRepository,
        }
        if kind == "leads":
            repositories.update(
                {"sources": LeadSourceRepository, "loan_products": LoanProductRepository}
            )
        result = {}
        for name, repository in repositories.items():
            items = await repository(self.db).find_many({"status": "active"}, limit=10000)
            result[name] = [
                {
                    "id": item.require_id(),
                    "name": item.name,
                    "category_id": getattr(item, "category_id", None) or "",
                }
                for item in items
            ]
        self._lookups[kind] = result
        return result

    @staticmethod
    def resolve(value: str, items: list[dict[str, str]], label: str) -> str:
        matches = [item for item in items if value == item["id"] or value == item["name"]]
        if len(matches) != 1:
            raise ValidationError(
                f"{label}: use a valid name or ID from the sample Lookups sheet; ambiguous names require an ID."
            )
        return matches[0]["id"]

    async def validate(
        self, kind: str, values: dict[str, Any], actor: User, *, resolve: bool = False
    ) -> dict[str, Any]:
        data = {key: value for key, value in values.items() if value != "" and value is not None}
        for key, value in data.items():
            if isinstance(value, str) and (
                any(ord(char) < 32 and char not in "\n\r\t" for char in value)
                or value.lstrip().startswith(("=", "+", "-", "@"))
            ):
                raise ValidationError(
                    f"{fields(kind).get(key, key)}: formulas and control characters are not supported."
                )
        if not str(data.get("full_name", "")).strip():
            raise ValidationError("Full Name is required.")
        for key in ("next_follow_up_date", "nominee_dob"):
            if key in data and isinstance(data[key], str):
                try:
                    value = data[key]
                    if len(value) == 10 and value[2] == "-":
                        day, month, year = value.split("-")
                        value = f"{year}-{month}-{day}"
                    data[key] = date.fromisoformat(value).isoformat()
                except ValueError:
                    raise ValidationError(
                        f"{fields(kind)[key]}: invalid date; use YYYY-MM-DD or DD-MM-YYYY."
                    ) from None
        if kind == "insurance" and data.get("gender") not in (None, "male", "female", "other"):
            raise ValidationError("Gender must be male, female or other.")
        if resolve:
            lookup = await self.lookups(kind)
            if kind == "leads":
                data["source_id"] = self.resolve(
                    str(data.get("source_id", "")), lookup["sources"], "Lead Source"
                )
                category = data.get("product_category")
                if category not in ("loan", "insurance"):
                    raise ValidationError("Product Category must be loan or insurance.")
                data["product_id"] = self.resolve(
                    str(data.get("product_id", "")), lookup[f"{category}_products"], "Product"
                )
                if data.get("assigned_to") == "self":
                    data["assigned_to"] = "__self__"
            else:
                data["insurance_category_id"] = self.resolve(
                    str(data.get("insurance_category_id", "")),
                    lookup["categories"],
                    "Insurance Category",
                )
                data["product_id"] = self.resolve(
                    str(data.get("product_id", "")), lookup["insurance_products"], "Product"
                )
        payload = MODELS[kind].model_validate(data)
        normalized = payload.model_dump(mode="json", exclude_none=True)
        if any(
            isinstance(value, float) and not math.isfinite(value) for value in normalized.values()
        ):
            raise ValidationError("Numeric values must be finite numbers.")
        if kind == "leads":
            lead_payload = CreateLeadRequest.model_validate(normalized)
            if lead_payload.assigned_to and not await PermissionEngine(self.db).has_permission(
                actor, module="leads", resource="leads", action="assign"
            ):
                raise ForbiddenError(
                    "Assign To requires Leads Assign permission. Leave it empty to create Fresh Leads."
                )
            await LeadService(self.db).validate_create_lead(lead_payload, actor)
        else:
            await InsuranceCaseService(self.db).validate_manual_case(
                CreateManualInsuranceCaseRequest.model_validate(normalized)
            )
        return normalized

    @staticmethod
    def row_error(exc: Exception, kind: str) -> tuple[str, str]:
        if isinstance(exc, SchemaError):
            return "invalid", "; ".join(
                f"{fields(kind).get(str(error['loc'][0]), str(error['loc'][0]))}: {error['msg']}"
                for error in exc.errors(include_input=False, include_url=False)
            )
        if isinstance(exc, ConflictError) and kind == "leads":
            return "duplicate", "An active lead with this mobile already exists."
        if isinstance(exc, AppError):
            return "invalid", exc.message
        return "invalid", "Invalid value. Check the sample format and reference IDs."

    @staticmethod
    def response(batch: dict[str, Any]) -> dict[str, Any]:
        rows = batch["rows"]
        return {
            "batch_id": batch["batch_id"],
            "state": batch["state"],
            "total": len(rows),
            **{
                status: sum(row["status"] == status for row in rows)
                for status in ("valid", "invalid", "duplicate", "imported", "failed", "processing")
            },
            "rows": [
                {key: value for key, value in row.items() if key != "payload"} for row in rows
            ],
        }

    async def preview(
        self,
        kind: str,
        rows: list[tuple[int, dict[str, str]]],
        actor: User,
    ) -> dict[str, Any]:
        batch_id = hashlib.sha256(
            actor.require_id().encode() + kind.encode() + json.dumps(rows, sort_keys=True).encode()
        ).hexdigest()
        key = f"bulk-import:{batch_id}"
        existing = await self.redis.get(key)
        if existing:
            return self.response(json.loads(existing))
        batch: dict[str, Any] = {
            "batch_id": batch_id,
            "actor_id": actor.require_id(),
            "kind": kind,
            "state": "preview",
            "rows": [],
        }
        seen: set[str] = set()
        for number, values in rows:
            row: dict[str, Any] = {
                "number": number,
                "values": values,
                "status": "valid",
                "error": "",
            }
            try:
                payload = await self.validate(kind, values, actor, resolve=True)
                if kind == "leads" and payload["mobile"] in seen:
                    raise ConflictError("Duplicate mobile in this file.")
                seen.add(payload["mobile"])
                row["payload"] = payload
            except (AppError, SchemaError, ValueError) as exc:
                row["status"], row["error"] = self.row_error(exc, kind)
            batch["rows"].append(row)
        # Concurrent previews of the same file share a single immutable batch.
        await self.redis.set(key, json.dumps(batch), ex=TTL, nx=True)
        return self.response(json.loads(await self.redis.get(key)))

    async def confirm(self, kind: str, batch_id: str, actor: User) -> dict[str, Any]:
        key = f"bulk-import:{batch_id}"
        raw = await self.redis.get(key)
        if raw is None:
            raise NotFoundError("Preview expired. Upload and validate the file again.")
        batch = json.loads(raw)
        if batch["actor_id"] != actor.require_id() or batch["kind"] != kind:
            raise NotFoundError("Import preview not found.")
        if batch["state"] == "completed":
            return self.response(batch)
        if batch["state"] != "preview" or not await self.redis.set(
            f"{key}:lock", "1", nx=True, ex=TTL
        ):
            raise ConflictError(
                "This import is already processing or was interrupted. Reopen the same file to review its progress; do not start another import."
            )
        # Another request may have checkpointed a chunk between our first read and
        # acquiring the lock. Never operate on that stale snapshot.
        current = await self.redis.get(key)
        if current is None:
            raise NotFoundError("Preview expired. Upload and validate the file again.")
        batch = json.loads(current)
        if batch["state"] == "completed":
            return self.response(batch)
        if batch["state"] != "preview":
            raise ConflictError("This import requires review before it can continue.")
        batch["state"] = "processing"
        await self.redis.set(key, json.dumps(batch), ex=TTL)
        processed = 0
        for row in batch["rows"]:
            if row["status"] != "valid":
                continue
            if processed >= ROWS_PER_CONFIRM:
                break
            processed += 1
            try:
                payload = await self.validate(kind, row["payload"], actor)
            except (AppError, SchemaError, ValueError) as exc:
                row["status"], row["error"] = self.row_error(exc, kind)
                continue
            # Persist intent before any business writes. Interrupted work is never automatically replayed.
            row["status"] = "processing"
            await self.redis.set(key, json.dumps(batch), ex=TTL)
            try:
                if kind == "leads":
                    record = await LeadService(self.db).create_lead(
                        CreateLeadRequest.model_validate(payload), actor
                    )
                    record_id = record.require_id()
                else:
                    case = await InsuranceCaseService(self.db).create_manual_case(
                        CreateManualInsuranceCaseRequest.model_validate(payload), actor
                    )
                    record_id = case.require_id()
                row.update(status="imported", record_id=record_id)
            except Exception:  # noqa: BLE001 -- do not replay uncertain writes or expose customer data
                # Creation may have made partial writes. Never retry this row or log customer values.
                row.update(
                    status="failed",
                    error="Creation could not be confirmed. Check the existing records before retrying this row.",
                )
            await self.redis.set(key, json.dumps(batch), ex=TTL)
        # Bounded requests avoid keeping hundreds of customer-account creations in a
        # single HTTP request. Only fully checkpointed batches can resume; a process
        # interrupted during creation remains locked for manual reconciliation.
        batch["state"] = (
            "preview" if any(row["status"] == "valid" for row in batch["rows"]) else "completed"
        )
        await self.redis.set(key, json.dumps(batch), ex=TTL)
        if batch["state"] == "preview":
            await self.redis.delete(f"{key}:lock")
        return self.response(batch)
