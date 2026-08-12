from typing import Any

from bson import ObjectId


def to_object_id(value: str) -> ObjectId:
    return ObjectId(value)


def is_valid_object_id(value: str) -> bool:
    return ObjectId.is_valid(value)


def serialize_id(doc: dict[str, Any]) -> dict[str, Any]:
    """Replaces Mongo's `_id` (ObjectId) with a JSON-friendly string `id` field."""
    if "_id" in doc:
        doc = {**doc, "id": str(doc["_id"])}
        del doc["_id"]
    return doc
