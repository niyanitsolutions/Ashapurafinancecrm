"""Final Phase — pure unit coverage for the Product Schema Engine's Phase 3.1 validation
engine (`app/features/customer/field_validation.py`). No DB, no HTTP: these are plain
functions, and this was previously verified only via a one-off scratch script during
development — this file gives the conditional-visibility/format-validation/required
logic permanent regression protection, since it's the one piece every portal's dynamic
form relies on to reject bad data.
"""

from app.features.customer.field_validation import is_field_visible, validate_field_value, validate_form_data
from app.features.customer.models import FieldCondition, FieldValidation, FormFieldDefinition


def _field(key: str, **kwargs) -> FormFieldDefinition:
    return FormFieldDefinition(key=key, label=kwargs.pop("label", key), field_type=kwargs.pop("field_type", "text"), **kwargs)


def test_field_with_no_condition_is_always_visible():
    field = _field("full_name")
    assert is_field_visible(field, {}) is True
    assert is_field_visible(field, {"anything": "x"}) is True


def test_equals_condition_visibility():
    field = _field("partner_name", visible_when=FieldCondition(field_key="business_type", operator="equals", value="Partnership"))
    assert is_field_visible(field, {"business_type": "Partnership"}) is True
    assert is_field_visible(field, {"business_type": "Proprietorship"}) is False
    assert is_field_visible(field, {}) is False  # controlling field unset never satisfies equals


def test_not_equals_condition_visibility():
    field = _field("other_reason", visible_when=FieldCondition(field_key="purpose", operator="not_equals", value="Other"))
    assert is_field_visible(field, {"purpose": "Medical"}) is True
    assert is_field_visible(field, {"purpose": "Other"}) is False


def test_in_condition_visibility():
    field = _field("gst_number", visible_when=FieldCondition(field_key="business_type", operator="in", value=["LLP", "Pvt. Ltd."]))
    assert is_field_visible(field, {"business_type": "LLP"}) is True
    assert is_field_visible(field, {"business_type": "Proprietorship"}) is False
    assert is_field_visible(field, {"business_type": None}) is False


def test_required_field_blank_is_invalid():
    field = _field("full_name", required=True)
    assert validate_field_value(field, None) == "full_name is required."
    assert validate_field_value(field, "   ") == "full_name is required."
    assert validate_field_value(field, "Vijay") is None


def test_optional_field_blank_is_valid():
    field = _field("remarks", required=False)
    assert validate_field_value(field, None) is None
    assert validate_field_value(field, "") is None


def test_format_validation_pan():
    field = _field("pan_number", validation=FieldValidation(format="pan"))
    assert validate_field_value(field, "ABCDE1234F") is None
    assert validate_field_value(field, "invalid-pan") is not None


def test_format_validation_mobile():
    field = _field("mobile", validation=FieldValidation(format="mobile"))
    assert validate_field_value(field, "9876543210") is None
    assert validate_field_value(field, "1234567890") is not None  # must start 6-9
    assert validate_field_value(field, "98765") is not None  # too short


def test_format_validation_aadhaar_and_pincode():
    aadhaar = _field("aadhaar", validation=FieldValidation(format="aadhaar"))
    assert validate_field_value(aadhaar, "123456789012") is None
    assert validate_field_value(aadhaar, "12345") is not None

    pincode = _field("pincode", validation=FieldValidation(format="pincode"))
    assert validate_field_value(pincode, "560001") is None
    assert validate_field_value(pincode, "56001") is not None


def test_min_max_length_validation():
    field = _field("code", validation=FieldValidation(min_length=3, max_length=5))
    assert validate_field_value(field, "ab") is not None
    assert validate_field_value(field, "abcdef") is not None
    assert validate_field_value(field, "abcd") is None


def test_validate_form_data_skips_hidden_fields_required_check():
    fields = [
        _field("business_type", required=True),
        _field("partner_name", required=True, visible_when=FieldCondition(field_key="business_type", operator="equals", value="Partnership")),
    ]
    # partner_name is required=True but hidden (business_type != Partnership) — must not
    # block submission even though it has no value.
    errors = validate_form_data(fields, {"business_type": "Proprietorship"})
    assert errors == []

    # Once visible, it must be enforced.
    errors = validate_form_data(fields, {"business_type": "Partnership"})
    assert errors == ["partner_name is required."]
