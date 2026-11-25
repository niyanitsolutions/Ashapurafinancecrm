"""Explicit applicant-name keys verified against seed_product_schemas.py."""

from typing import Any

NAME_KEYS = ("full_name", "full_name_as_per_pan_card", "applicant_name_as_per_pan_card")


def actual_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned: str = " ".join(value.split())
    if not cleaned or len(cleaned) > 200 or cleaned.casefold() in {"customer", "name unavailable"}:
        return None
    return cleaned


def application_name(application: Any, schema: dict[str, Any] | None) -> str | None:
    keys = {f.get("key") for f in (schema or {}).get("fields", []) if not f.get("hidden")}
    for key in NAME_KEYS:
        if key in keys and (name := actual_name(application.form_data.get(key))):
            return name
    # Existing model's persisted inline applicant profile, never a user/phone lookup.
    return actual_name((application.pending_profile or {}).get("full_name"))


async def current_application_name(db: Any, application: Any) -> str:
    from bson import ObjectId

    customer = (
        await db.customers.find_one(
            {
                "_id": ObjectId(application.customer_id),
                "user_id": application.user_id,
                "is_deleted": False,
            }
        )
        if application.customer_id
        else None
    )
    if customer and (name := actual_name(customer.get("full_name"))):
        return name
    schema = await db.application_form_definitions.find_one(
        {"_id": ObjectId(application.form_definition_id)}
    )
    return application_name(application, schema) or "Name unavailable"


async def batch_application_names(db: Any, ids: list[str]) -> dict[str, str]:
    from types import SimpleNamespace

    from bson import ObjectId

    apps = await db.applications.find(
        {
            "_id": {"$in": [ObjectId(value) for value in ids if ObjectId.is_valid(value)]},
            "is_deleted": False,
        }
    ).to_list(len(ids) or 1)
    customer_ids = {
        a.get("customer_id") for a in apps if ObjectId.is_valid(a.get("customer_id", ""))
    }
    customers = {
        str(c["_id"]): c
        for c in await db.customers.find(
            {"_id": {"$in": [ObjectId(value) for value in customer_ids]}, "is_deleted": False}
        ).to_list(len(customer_ids) or 1)
    }
    schema_ids = {
        a.get("form_definition_id")
        for a in apps
        if ObjectId.is_valid(a.get("form_definition_id", ""))
    }
    schemas = {
        str(s["_id"]): s
        for s in await db.application_form_definitions.find(
            {"_id": {"$in": [ObjectId(value) for value in schema_ids]}}
        ).to_list(len(schema_ids) or 1)
    }
    names = {}
    for app in apps:
        customer = customers.get(app.get("customer_id"))
        profile = (
            actual_name(customer.get("full_name"))
            if customer and customer.get("user_id") == app.get("user_id")
            else None
        )
        names[str(app["_id"])] = (
            profile
            or application_name(
                SimpleNamespace(
                    form_data=app.get("form_data", {}), pending_profile=app.get("pending_profile")
                ),
                schemas.get(app.get("form_definition_id")),
            )
            or "Name unavailable"
        )
    return names


def mongo_application_name() -> dict[str, Any]:
    """Aggregation equivalent of explicit-schema name resolution (no identity guessing)."""

    def actual(value: str) -> dict[str, Any]:
        text = {"$convert": {"input": value, "to": "string", "onError": "", "onNull": ""}}
        return {
            "$and": [
                {"$eq": [{"$type": value}, "string"]},
                {"$gt": [{"$strLenCP": {"$trim": {"input": text}}}, 0]},
                {"$lte": [{"$strLenCP": text}, 200]},
                {"$not": [{"$in": [{"$toLower": text}, ["customer", "name unavailable"]]}]},
            ]
        }

    keys = {
        "$map": {
            "input": {
                "$filter": {
                    "input": {"$ifNull": ["$schema.fields", []]},
                    "as": "field",
                    "cond": {"$ne": ["$$field.hidden", True]},
                }
            },
            "as": "field",
            "in": "$$field.key",
        }
    }
    fallback: Any = {
        "$cond": [
            actual("$pending_profile.full_name"),
            "$pending_profile.full_name",
            "Name unavailable",
        ]
    }
    for key in reversed(NAME_KEYS):
        value = "$form_data." + key
        fallback = {"$cond": [{"$and": [{"$in": [key, keys]}, actual(value)]}, value, fallback]}
    return {"$cond": [actual("$customer.full_name"), "$customer.full_name", fallback]}
