"""Schema-bound staff corrections. Application answers never mutate shared identity."""

import json
import math
from datetime import date
from typing import TYPE_CHECKING, Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import OperationFailure

from app.constants.roles import EMPLOYEE, OWNER
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.customer.field_validation import (
    is_field_visible,
    normalize_field_value,
    validate_field_value,
)
from app.features.customer.models import Application
from app.security.encryption import encrypt
from app.shared.audit_log import AuditLog
from app.utils.datetime import utc_now

if TYPE_CHECKING:
    from app.features.customer.service import CustomerService


def validate_fields(
    fields: Any, values: dict[str, Any], errors: dict[str, str], prefix: str = ""
) -> None:
    for field in fields:
        if not is_field_visible(field, values):
            continue
        value = normalize_field_value(field, values.get(field.key))
        if field.key in values:
            values[field.key] = value
        path = prefix + field.key
        if value is not None and value != "":
            kind = field.field_type
            if kind == "number" and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                errors[path] = "Enter a finite number."
            elif kind == "checkbox" and not isinstance(value, bool):
                errors[path] = "Choose a valid checkbox value."
            elif kind not in {"number", "checkbox"} and not isinstance(value, str):
                errors[path] = "Enter a text value."
            elif kind == "date":
                try:
                    date.fromisoformat(value)
                except (ValueError, TypeError):
                    errors[path] = "Enter a valid date."
        if path not in errors and (error := validate_field_value(field, value)):
            errors[path] = error


async def update_details(
    service: "CustomerService", application_id: str, payload: Any, actor: Any
) -> Application:
    db = service._db
    if actor.role not in {OWNER, EMPLOYEE} or not await PermissionEngine(db).has_permission(
        actor, module="customer", resource="customers", action="edit"
    ):
        raise ForbiddenError("Customer edit permission is required.")
    app = await service.get_application_for_staff(application_id, actor)
    if not ObjectId.is_valid(app.user_id) or not await db.users.find_one(
        {"_id": ObjectId(app.user_id), "role": "customer", "is_deleted": False}, {"_id": 1}
    ):
        raise ForbiddenError("The application account relationship requires Owner review.")
    if app.customer_id and (
        not ObjectId.is_valid(app.customer_id)
        or not await db.customers.find_one(
            {"_id": ObjectId(app.customer_id), "user_id": app.user_id, "is_deleted": False},
            {"_id": 1},
        )
    ):
        raise ForbiddenError("The application customer relationship requires Owner review.")
    if app.status not in {"draft", "submitted"}:
        raise ConflictError("This application cannot be edited.")
    if payload.version is None or not payload.reason or not payload.reason.strip():
        raise ValidationError("Version and correction reason are required.")
    if "pending_profile" in payload.model_fields_set or payload.form_data is None:
        raise ValidationError("Only submitted application answers can be updated here.")
    schema = await service.get_form_definition_by_id(app.form_definition_id)
    if schema.product_id != app.product_id or schema.product_category != app.product_category:
        raise ConflictError("Application schema relationship requires Owner review.")
    fields = {field.key: field for field in schema.fields}
    groups = {group.key: group for group in schema.repeatable_groups}
    patch = payload.form_data
    if any("." in key or key.startswith("$") for key in patch) or set(patch) - (
        fields.keys() | groups.keys()
    ):
        raise ValidationError("Unknown or protected application field.")
    values = {**app.form_data, **patch}
    for key in patch:
        if key in fields and not is_field_visible(fields[key], values):
            raise ValidationError(
                "Hidden fields cannot be changed.",
                details={"field_errors": {key: "This field is read-only."}},
            )
    errors: dict[str, str] = {}
    validate_fields(schema.fields, values, errors)
    for key, group in groups.items():
        blocks = values.get(key, [])
        if blocks is None and key not in patch:
            blocks = []
        if (
            not isinstance(blocks, list)
            or len(blocks) < group.min_count
            or len(blocks) > (group.max_count if group.max_count is not None else 100)
        ):
            errors[key] = "Check the number of entries in this section."
            continue
        allowed = {f.key for f in group.fields}
        old_blocks = app.form_data.get(key) or []
        for index, block in enumerate(blocks):
            if not isinstance(block, dict):
                errors[key] = "Invalid section fields."
                continue
            previous_block = (
                old_blocks[index]
                if index < len(old_blocks) and isinstance(old_blocks[index], dict)
                else {}
            )
            if any(
                field not in allowed
                and (field not in previous_block or value != previous_block[field])
                for field, value in block.items()
            ):
                errors[key] = "Unknown or protected section fields."
                continue
            for field in group.fields:
                if not is_field_visible(field, block) and field.key in block:
                    previous = old_blocks[index].get(field.key) if index < len(old_blocks) else None
                    if block[field.key] != previous:
                        errors[f"{key}.{index}.{field.key}"] = "This field is read-only."
            validate_fields(group.fields, block, errors, f"{key}.{index}.")
    if errors:
        raise ValidationError(
            "Check the highlighted application fields.", details={"field_errors": errors}
        )
    changed = {key: values[key] for key in patch if values.get(key) != app.form_data.get(key)}
    if not changed:
        if app.version != payload.version:
            raise ConflictError("Application changed. Reload before saving.")
        return app
    current = await db.applications.find_one(
        {"_id": ObjectId(application_id)}, {"answer_history": 1}
    )
    if len((current or {}).get("answer_history", [])) >= 250:
        raise ConflictError("History limit reached; request Owner archival review.")
    before = {key: app.form_data.get(key) for key in changed}
    now = utc_now()
    event = {
        "actor_id": actor.require_id(),
        "at": now,
        "reason": payload.reason.strip(),
        "version": payload.version + 1,
        "fields": list(changed),
        "before_encrypted": encrypt(json.dumps(before, default=str)),
        "after_encrypted": encrypt(json.dumps(changed, default=str)),
    }
    audit = AuditLog(
        event_type="application_details_edited",
        user_id=actor.require_id(),
        metadata={
            "application_id": application_id,
            "customer_id": app.customer_id,
            "fields": list(changed),
            "version": payload.version + 1,
        },
    )
    query = {
        "_id": ObjectId(application_id),
        "version": payload.version,
        "is_deleted": False,
        "customer_id": app.customer_id,
        "user_id": app.user_id,
        "form_definition_id": app.form_definition_id,
        "status": app.status,
    }
    if actor.role == EMPLOYEE:
        query["assigned_to"] = app.assigned_to
    # Patch individual fields so unknown historical answers are never erased.
    updates = {"form_data." + key: value for key, value in changed.items()}
    updates.update(updated_at=now, updated_by=actor.require_id())
    try:
        async with await db.client.start_session() as session, session.start_transaction():
            row = await db.applications.find_one_and_update(
                query,
                {"$set": updates, "$inc": {"version": 1}, "$push": {"answer_history": event}},
                return_document=ReturnDocument.AFTER,
                session=session,
            )
            if not row:
                raise ConflictError("Application changed. Reload before saving.")
            await db.audit_logs.insert_one(
                audit.model_dump(by_alias=True, exclude={"id"}), session=session
            )
    except OperationFailure as error:
        if error.code == 112 or error.has_error_label("TransientTransactionError"):
            raise ConflictError(
                "Application changed during another request. Reload before saving."
            ) from None
        raise
    return Application.model_validate(row)
