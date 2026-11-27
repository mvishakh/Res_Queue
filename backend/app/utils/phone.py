import phonenumbers

from app.core.errors import ValidationFailed


def normalize_phone(raw: str, default_region: str = "IN") -> str:
    """Return the phone number in E.164 format (e.g. +919876543210) or raise."""
    cleaned = (raw or "").strip()
    if not cleaned:
        raise ValidationFailed("WhatsApp number is required", details={"field": "phone"})
    try:
        parsed = phonenumbers.parse(cleaned, default_region.upper())
    except phonenumbers.NumberParseException as exc:
        raise ValidationFailed("Enter a valid WhatsApp number", details={"field": "phone"}) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValidationFailed("Enter a valid WhatsApp number", details={"field": "phone"})
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
