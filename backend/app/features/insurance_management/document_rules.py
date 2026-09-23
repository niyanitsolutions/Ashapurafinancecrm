"""Insurance document defaults for existing schemas; no persisted schema rewrite."""

import re

from app.features.customer.models import ApplicationDocument, RequiredDocumentDefinition


def document_kind(name: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return {
        "pan": "pan", "pancard": "pan", "aadhaar": "aadhaar", "aadhaarcard": "aadhaar",
        "aadhar": "aadhaar", "aadharcard": "aadhaar", "addressproof": "address",
        "bankstatement": "bank", "cancelledcheque": "cheque", "canceledcheque": "cheque",
        "passportphotograph": "photo", "passportsizephotograph": "photo", "passportphoto": "photo",
    }.get(key, "")


def password_supported(name: str, configured: bool) -> bool:
    kind = document_kind(name)
    return kind != "photo" and (bool(kind) or configured)


def front_back_supported(name: str) -> bool:
    return document_kind(name) in {"pan", "aadhaar", "address", "bank", "cheque"}


def requirements_status(
    requirements: list[RequiredDocumentDefinition], names: dict[str, str],
    documents: list[ApplicationDocument], *, verified: bool,
) -> tuple[int, list[str]]:
    """Count bank alternatives once; a chosen two-sided upload needs both sides."""
    visible = [r for r in requirements if not r.hidden]
    bank = [r for r in visible if document_kind(names.get(r.document_type_id, "")) in {"bank", "cheque"}]
    bank_ids = {r.document_type_id for r in bank}

    def complete(rd: RequiredDocumentDefinition) -> bool:
        current = [d for d in documents if d.document_type_id == rd.document_type_id and d.is_current]
        eligible = [d for d in current if d.document_status == "uploaded" and (not verified or d.verification_status == "verified")]
        name = names.get(rd.document_type_id, "")
        configured_pair = rd.front_back_upload and not front_back_supported(name) and document_kind(name) != "photo"
        if configured_pair or any(d.side for d in current):
            return {"front", "back"}.issubset({d.side for d in eligible})
        return bool(eligible)

    required = [r for r in visible if r.required and r.document_type_id not in bank_ids]
    missing = [r.document_type_id for r in required if not complete(r)]
    if bank and not any(complete(r) for r in bank):
        missing.append(bank[0].document_type_id)
    # Optional documents must not leave a selected front/back pair incomplete either.
    for rd in visible:
        if rd not in required and any(d.document_type_id == rd.document_type_id and d.side for d in documents) and not complete(rd) and rd.document_type_id not in missing:
            required.append(rd)
            missing.append(rd.document_type_id)
    return len(required) + bool(bank), missing
